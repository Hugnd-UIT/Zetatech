import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterator

from fastapi import HTTPException

from core.routers.agents.runtime import (
    arm_approval,
    auto_approve,
    cleanup_workspace,
    persist_completed_run,
    raise_ai_error,
    start_run,
)
from core.routers.agents.serialize import serialize_message, serialize_run_approval
from core.routers.agents.service import (
    build_bridge_request,
    build_final_response,
    effective_summary,
    prepare_execution_workspace,
    prepare_message_execution,
    resolve_active_provider,
    save_memory,
)
from core.routers.agents.intent import summarize_intent_decision


def stream_events(
    *,
    repo,
    payload,
    path_cwd: Callable[[], Path],
    source_context: Callable[..., Dict[str, Any]],
    existing_source: Callable[..., Path | None],
    cleanup_run_workspace: Callable[[Path], None],
    stream_bridge: Callable[[Dict[str, Any]], Iterator[Dict[str, Any]]],
):
    try:
        prov = resolve_active_provider(repo=repo, payload=payload)
    except HTTPException as exc:
        yield json.dumps(
            {"type": "error", "data": {"detail": str(exc.detail)}},
            ensure_ascii=False,
        ) + "\n"
        return

    root = None
    src = None
    run = None
    user_msg = None
    evts = []
    stream_evts = []
    res = {"events": [], "result": {}}

    try:
        exec_ctx = prepare_message_execution(repo=repo, payload=payload, active_provider=prov)
        ws = prepare_execution_workspace(
            repo=repo,
            thread=exec_ctx["thread"],
            last_scan_session_id=exec_ctx["last_scan_session_id"],
            path_cwd=path_cwd,
            existing_source=existing_source,
            source_context=source_context,
            runtime_events=evts,
            intent_info=exec_ctx["intent_info"],
        )
        src = ws["source_dir"]
        root = ws["workspace_root"]
        evts.append(
            {
                "type": "intent_resolved",
                "data": {
                    "decision_trace": summarize_intent_decision(exec_ctx["intent_info"]),
                },
            }
        )

        for event in evts:
            yield json.dumps(
                {"type": "runtime_event", "data": event},
                ensure_ascii=False,
            ) + "\n"

        user_msg, run = start_run(
            repo=repo,
            thread_id=payload.thread_id,
            content=payload.content,
            active_provider=prov,
            workspace_source_path=ws["workspace_source_path"],
        )
        yield json.dumps(
            {"type": "user_message", "data": serialize_message(user_msg)},
            ensure_ascii=False,
        ) + "\n"

        ctrl = arm_approval(
            repo=repo,
            payload=payload,
            run_id=run["id"],
            workspace_root=root,
        )

        req = build_bridge_request(
            active_provider=prov,
            payload=payload,
            context=ws["context"],
            workspace_root=root,
            source_dir=src,
            execution_mode=exec_ctx["execution_mode"],
            team_mode=exec_ctx["team_mode"],
            strategy=exec_ctx["strategy"],
            context_summary=effective_summary(
                intent_info=exec_ctx["intent_info"],
                context_summary=exec_ctx["context_summary"],
            ),
            approval_control_path=ctrl,
        )

        for event in stream_bridge(req):
            if event.get("type") == "approval_requested" and run is not None:
                data = event.get("data") or {}
                if isinstance(data, dict):
                    repo.upsert_run_approval(
                        run["id"],
                        payload.thread_id,
                        status="pending",
                        request_payload=data,
                    )
                    yield json.dumps(
                        {
                            "type": "pending_approval",
                            "data": serialize_run_approval(repo.get_run_approval(run["id"])),
                        },
                        ensure_ascii=False,
                    ) + "\n"
            if event.get("type") == "run_completed":
                data = event.get("data") or {}
                if isinstance(data, dict):
                    res = {
                        "output": str(
                            data.get("content") or data.get("output") or ""
                        ),
                        "events": stream_evts,
                        "result": data,
                    }
                else:
                    res = {
                        "output": str(data),
                        "events": stream_evts,
                        "result": {"content": str(data)},
                    }
                yield json.dumps(
                    {"type": "run_completed", "data": res["result"]},
                    ensure_ascii=False,
                ) + "\n"
                continue

            stream_evts.append(event)
            yield json.dumps(
                {"type": "bridge_event", "data": event},
                ensure_ascii=False,
            ) + "\n"

        bot_msg, team, tasks = persist_completed_run(
            repo=repo,
            thread_id=payload.thread_id,
            run_id=run["id"],
            bridge_result=res,
            source_dir=src,
            runtime_events=evts,
        )
        if run is not None:
            auto_approve(
                repo=repo,
                run_id=run["id"],
                thread_id=payload.thread_id,
            )
        save_memory(
            repo=repo,
            payload=payload,
            assistant_message=bot_msg,
            source_dir=src,
            runtime_events=evts,
            run_events=stream_evts,
            run_tasks=tasks,
        )
        final = build_final_response(
            repo=repo,
            payload=payload,
            user_message=user_msg,
            assistant_message=bot_msg,
            run=run,
            team_events=team,
            persisted_tasks=tasks,
            bridge_result=res,
        )
        final["pending_approval"] = serialize_run_approval(repo.get_thread_pending_approval(payload.thread_id))
        yield json.dumps({"type": "final", "data": final}, ensure_ascii=False) + "\n"
    except asyncio.CancelledError:
        if run is not None:
            try:
                repo.fail_run_with_assistant_message(
                    run_id=run["id"],
                    thread_id=payload.thread_id,
                    content="Response stream interrupted because the client disconnected. You can resend the message.",
                    error_message="Run interrupted by client disconnect.",
                    tool_calls=[],
                    tool_results=[],
                )
            except Exception:
                try:
                    repo.finish_run(run["id"], "failed", "Run interrupted by client disconnect.")
                except Exception:
                    pass
        raise
    except Exception as exc:
        if run is not None:
            try:
                raise_ai_error(
                    repo=repo,
                    exc=exc,
                    run=run,
                    thread_id=payload.thread_id,
                )
            except HTTPException as mapped:
                yield json.dumps(
                    {
                        "type": "error",
                        "data": {
                            "detail": str(mapped.detail),
                            "status": mapped.status_code,
                        },
                    },
                    ensure_ascii=False,
                ) + "\n"
                return
        else:
            yield json.dumps(
                {"type": "error", "data": {"detail": str(exc)}},
                ensure_ascii=False,
            ) + "\n"
            return
    finally:
        cleanup_workspace(
            source_dir=src,
            workspace_root=root,
            cleanup_run_workspace=cleanup_run_workspace,
        )
