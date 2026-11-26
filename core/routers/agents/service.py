from pathlib import Path
from typing import Any, Callable, Dict, List

from fastapi import HTTPException, status

from core.routers.agents.bridge import build_bridge_payload
from core.routers.agents.intent import (
    recent_context,
    resolve_message_intent,
    summarize_intent_decision,
)
from core.routers.agents.memory import (
    next_memory,
    summarize_thread_memory,
)
from core.routers.agents.runtime import (
    arm_approval,
    auto_approve,
    cleanup_workspace,
    persist_completed_run,
    prep_context,
    prep_thread,
    raise_ai_error,
    start_run,
)
from core.routers.agents.serialize import serialize_message, serialize_thread, thread_events


def resolve_active_provider(*, repo, payload) -> Dict[str, Any]:
    key = str(getattr(payload, "profile_key", "") or "").strip()
    prov = (
        repo.get_provider_by_profile_key(key)
        if key
        else repo.get_active_provider()
    )
    if prov is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active AI provider configured.",
        )

    model = str(getattr(payload, "model", "") or "").strip()
    if model:
        prov = {**prov, "model": model}
    return prov


def prepare_message_execution(*, repo, payload, active_provider: Dict[str, Any] | None = None) -> Dict[str, Any]:
    thread, last_sid = prep_thread(
        repo=repo,
        payload=payload,
    )
    recent = recent_context(repo, payload.thread_id)
    mem = summarize_thread_memory(repo, payload.thread_id)
    summary = "\n".join(
        part for part in [mem, recent] if part
    )
    intent = resolve_message_intent(
        content=payload.content,
        repo=repo,
        thread_id=payload.thread_id,
        thread=thread,
        context_summary=summary,
        active_provider=active_provider,
    )
    strat = str(getattr(payload, "strategy", "auto") or "auto").strip().lower()
    if strat and strat != "auto":
        intent["strategy"] = strat
        intent["team_mode"] = "single_agent" if strat == "agent" else strat
    if getattr(payload, "output_schema", None):
        intent["structured_output_requested"] = True
    mode = str(intent.get("strategy") or "agent")
    return {
        "thread": thread,
        "last_scan_session_id": last_sid,
        "intent_info": intent,
        "execution_mode": "raw_open_multi_agent",
        "team_mode": "single_agent" if mode == "agent" else mode,
        "strategy": mode,
        "context_summary": summary,
    }


def prepare_execution_workspace(
    *,
    repo,
    thread: Dict[str, Any],
    last_scan_session_id: int | None,
    path_cwd: Callable[[], Path],
    existing_source,
    source_context,
    runtime_events: List[Dict[str, Any]],
    intent_info: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    src, root, src_path = prep_context(
        repo=repo,
        thread=thread,
        last_scan_session_id=last_scan_session_id,
        path_cwd=path_cwd,
        existing_source=existing_source,
        runtime_events=runtime_events,
    )
    ctx = source_context(
        db_path=repo.db_path,
        plugin_slug=thread["plugin_slug"],
        is_theme=bool(thread.get("is_theme")),
        source_dir=src,
        last_scan_session_id=last_scan_session_id,
    )

    ctx = {**ctx, "intent_info": dict(intent_info or {})}
    return {
        "source_dir": src,
        "workspace_root": root,
        "workspace_source_path": src_path,
        "context": ctx,
    }


def effective_summary(*, intent_info: Dict[str, Any], context_summary: str) -> str:
    del intent_info
    return context_summary


def build_bridge_request(
    *,
    active_provider: Dict[str, Any],
    payload,
    context: Dict[str, Any],
    workspace_root: Path,
    source_dir: Path | None,
    execution_mode: str,
    team_mode: str,
    strategy: str,
    context_summary: str,
    approval_control_path: str | None = None,
) -> Dict[str, Any]:
    effective_provider = dict(active_provider)
    if getattr(payload, "output_schema", None):
        effective_provider["output_schema"] = payload.output_schema
    return build_bridge_payload(
        active_provider=effective_provider,
        prompt=payload.content,
        context=context,
        workspace_root=workspace_root,
        source_dir=source_dir,
        execution_mode=execution_mode,
        team_mode=team_mode,
        strategy=strategy,
        context_summary=context_summary,
        needs_tools=bool(context.get("intent_info", {}).get("needs_tools", True)),
        trace_enabled=bool(getattr(payload, "trace_enabled", True)),
        agents=getattr(payload, "agents", None) or None,
        tasks=getattr(payload, "tasks", None) or None,
        fanout=getattr(payload, "fanout", None) or None,
        loop_detection=getattr(payload, "loop_detection", None) or None,
        approval_mode=getattr(payload, "approval_mode", None) or None,
        approval_control_path=approval_control_path,
        before_run=getattr(payload, "before_run", None) or None,
        after_run=getattr(payload, "after_run", None) or None,
    )


def save_memory(
    *,
    repo,
    payload,
    assistant_message: Dict[str, Any],
    source_dir: Path | None,
    runtime_events: List[Dict[str, Any]],
    run_events: List[Dict[str, Any]],
    run_tasks: List[Dict[str, Any]],
) -> None:
    repo.update_thread_memory(
        payload.thread_id,
        **next_memory(
            repo=repo,
            thread_id=payload.thread_id,
            user_content=payload.content,
            assistant_output=str(assistant_message.get("content") or ""),
            source_dir=source_dir,
            run_events=[*(runtime_events or []), *(run_events or [])],
            run_tasks=run_tasks,
        ),
    )


def build_final_response(
    *,
    repo,
    payload,
    user_message: Dict[str, Any] | None,
    assistant_message: Dict[str, Any] | None,
    run,
    team_events: List[Dict[str, Any]],
    persisted_tasks: List[Dict[str, Any]],
    bridge_result: Dict[str, Any],
) -> Dict[str, Any]:
    thread = repo.get_thread(payload.thread_id)
    result_payload = bridge_result.get("result", {}) if isinstance(bridge_result.get("result"), dict) else {}
    return {
        "user_message": serialize_message(user_message),
        "assistant_message": serialize_message(assistant_message),
        "events": thread_events(repo, payload.thread_id),
        "run_id": int(run["id"]) if run is not None else None,
        "team_events": team_events,
        "tasks": persisted_tasks,
        "agents": result_payload.get("agents", []) if isinstance(result_payload, dict) else [],
        "structured": result_payload.get("structured") if isinstance(result_payload, dict) else None,
        "thread": serialize_thread(thread) if thread is not None else None,
    }


def execute_ai_message(
    *,
    repo,
    payload,
    path_cwd: Callable[[], Path],
    source_context,
    existing_source,
    cleanup_run_workspace: Callable[[Path], None],
    run_agent_bridge,
) -> Dict[str, object]:
    prov = resolve_active_provider(repo=repo, payload=payload)
    exec_ctx = prepare_message_execution(repo=repo, payload=payload, active_provider=prov)
    thread = exec_ctx["thread"]

    root: Path | None = None
    src: Path | None = None
    run = None
    user_msg = None
    bot_msg = None
    res: Dict[str, object] = {"events": []}
    team: List[Dict[str, object]] = []
    tasks: List[Dict[str, object]] = []
    evts: List[Dict[str, object]] = []

    try:
        ws = prepare_execution_workspace(
            repo=repo,
            thread=thread,
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

        user_msg, run = start_run(
            repo=repo,
            thread_id=payload.thread_id,
            content=payload.content,
            active_provider=prov,
            workspace_source_path=ws["workspace_source_path"],
        )
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
        res = run_agent_bridge(req)
        bot_msg, team, tasks = persist_completed_run(
            repo=repo,
            thread_id=payload.thread_id,
            run_id=run["id"],
            bridge_result=res,
            source_dir=src,
            runtime_events=evts,
        )
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
            run_events=res.get("events", []) or [],
            run_tasks=tasks,
        )
    except Exception as exc:
        raise_ai_error(
            repo=repo,
            exc=exc,
            run=run,
            thread_id=payload.thread_id,
        )
    finally:
        cleanup_workspace(
            source_dir=src,
            workspace_root=root,
            cleanup_run_workspace=cleanup_run_workspace,
        )

    return build_final_response(
        repo=repo,
        payload=payload,
        user_message=user_msg,
        assistant_message=bot_msg,
        run=run,
        team_events=team,
        persisted_tasks=tasks,
        bridge_result=res,
    )
