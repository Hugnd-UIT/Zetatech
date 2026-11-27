import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

from fastapi import HTTPException, status

from agents.bridge import BridgeError, BridgeProtocolError, BridgeTimeoutError
from paths import resolve_runtime_paths
from core.routers.agents.serialize import (
    serialize_run_task,
    serialize_team_event,
    split_tool_activity,
)

logger = logging.getLogger("zetatech.ai.router")


def fail_message(
    *,
    repo,
    run_id: int,
    thread_id: int,
    message: str,
    tool_calls: List[Dict[str, Any]] | None = None,
    tool_results: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    return repo.fail_run_with_assistant_message(
        run_id=run_id,
        thread_id=thread_id,
        content=message,
        error_message=message,
        tool_calls=tool_calls,
        tool_results=tool_results,
    )


def pick_session(
    thread: Dict[str, Any],
    req_sid: int | None,
) -> int | None:
    if req_sid is not None:
        return int(req_sid)
    saved_sid = thread.get("last_scan_session_id")
    if saved_sid is None:
        return None
    return int(saved_sid)


def resolve_source_dir(
    *,
    repo,
    thread: Dict[str, Any],
    last_scan_session_id: int | None,
    path_cwd: Callable[[], Path],
    existing_source: Callable[..., Path | None],
) -> Path | None:
    try:
        return existing_source(
            db_path=repo.db_path,
            plugin_slug=thread["plugin_slug"],
            is_theme=bool(thread.get("is_theme")),
            last_scan_session_id=last_scan_session_id,
            root_path=path_cwd(),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def prep_thread(*, repo, payload) -> tuple[Dict[str, Any], int | None]:
    thread = repo.get_thread(payload.thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI thread not found.",
        )

    last_sid = pick_session(
        thread,
        payload.last_scan_session_id,
    )
    if last_sid is not None:
        repo.update_thread_metadata(
            thread_id=payload.thread_id,
            last_scan_session_id=last_sid,
        )
    return repo.get_thread(payload.thread_id) or thread, last_sid


def prep_context(
    *,
    repo,
    thread: Dict[str, Any],
    last_scan_session_id: int | None,
    path_cwd: Callable[[], Path],
    existing_source: Callable[..., Path | None],
    runtime_events: List[Dict[str, Any]],
) -> tuple[Path | None, Path, str]:
    runtime_events.append(
        {
            "type": "source_prepare_started",
            "data": {
                "slug": str(thread.get("plugin_slug") or ""),
                "is_theme": bool(thread.get("is_theme")),
                "mode": "trusted_source_lookup",
            },
        }
    )
    src_dir = resolve_source_dir(
        repo=repo,
        thread=thread,
        last_scan_session_id=last_scan_session_id,
        path_cwd=path_cwd,
        existing_source=existing_source,
    )
    if src_dir is not None:
        src = src_dir.resolve()
        runtime_events.append(
            {
                "type": "source_prepare_completed",
                "data": {
                    "slug": str(thread.get("plugin_slug") or ""),
                    "is_theme": bool(thread.get("is_theme")),
                    "mode": "source",
                    "source_path": str(src),
                },
            }
        )
        return src, src, str(src)

    root = path_cwd()
    runtime_events.append(
        {
            "type": "source_prepare_failed",
            "data": {
                "slug": str(thread.get("plugin_slug") or ""),
                "is_theme": bool(thread.get("is_theme")),
                "mode": "metadata_only",
                "reason": "trusted_source_unavailable",
            },
        }
    )
    src_path = str(root.resolve())
    return src_dir, root, src_path


def start_run(
    *,
    repo,
    thread_id: int,
    content: str,
    active_provider: Dict[str, Any],
    workspace_source_path: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    msg = repo.create_message(
        thread_id=thread_id,
        role="user",
        content=content,
    )
    run = repo.create_run(
        thread_id=thread_id,
        provider=active_provider["provider"],
        provider_label=active_provider.get("provider_label"),
        model=active_provider.get("model"),
        status="running",
        message_id=msg["id"],
        workspace_path=workspace_source_path,
    )
    return msg, run


def approval_path(*, workspace_root: Path, thread_id: int, run_id: int) -> Path:
    del workspace_root
    dir = resolve_runtime_paths().approvals_dir
    dir.mkdir(parents=True, exist_ok=True)
    return dir / f"thread-{thread_id}-run-{run_id}.json"


def arm_approval(*, repo, payload, run_id: int, workspace_root: Path) -> str | None:
    if str(getattr(payload, "approval_mode", "off") or "off") != "manual":
        return None
    ctrl = str(
        approval_path(
            workspace_root=workspace_root,
            thread_id=payload.thread_id,
            run_id=run_id,
        ).resolve()
    )
    repo.upsert_run_approval(
        run_id,
        payload.thread_id,
        status="armed",
        control_path=ctrl,
        mode="manual",
        request_payload={},
    )
    return ctrl


def auto_approve(*, repo, run_id: int, thread_id: int) -> None:
    approval = repo.get_run_approval(run_id)
    if approval and str(approval.get("status") or "") == "pending":
        repo.upsert_run_approval(
            run_id,
            thread_id,
            status="decided",
            decision="approved",
        )


def persist_run_activity(
    *, repo, run_id: int, events: List[Dict[str, Any]], tasks: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    evts: List[Dict[str, Any]] = []
    for event in events:
        kind = str(event.get("type") or "")
        raw = event.get("data")
        data: Dict[str, Any] = (
            dict(raw) if isinstance(raw, dict) else {"value": raw}
        )
        agent = data.get("from") or data.get("assignee")
        if kind in {"agent_started", "agent_completed", "tool_call"}:
            agent = data.get("name") or agent
        tid = data.get("id") or data.get("taskId")
        evts.append(
            {
                "event_type": kind,
                "agent_name": str(agent) if agent is not None else None,
                "task_id": str(tid) if tid is not None else None,
                "payload": data,
            }
        )

    items = [
        {
            "task_id": str(task.get("id") or ""),
            "title": str(task.get("title") or ""),
            "status": str(task.get("status") or "pending"),
            "assignee": str(task.get("assignee")) if task.get("assignee") is not None else None,
            "depends_on": [
                str(item)
                for item in task.get("dependsOn") or task.get("depends_on") or []
            ],
            "result_text": str(task.get("result")) if task.get("result") is not None else None,
        }
        for task in tasks
    ]

    repo.create_run_events(run_id, evts)
    repo.upsert_run_tasks(run_id, items)

    return (
        [serialize_team_event(item) for item in evts],
        [serialize_run_task(item) for item in items],
    )


def persist_completed_run(
    *,
    repo,
    thread_id: int,
    run_id: int,
    bridge_result: Dict[str, Any],
    source_dir: Path | None,
    runtime_events: List[Dict[str, Any]] | None = None,
) -> tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    evts = [*(runtime_events or []), *(bridge_result.get("events", []) or [])]
    res = (
        bridge_result.get("result")
        if isinstance(bridge_result.get("result"), dict)
        else {}
    )
    tasks = (
        res.get("tasks", [])
        if isinstance(res, dict)
        else []
    )
    team, saved = persist_run_activity(
        repo=repo,
        run_id=run_id,
        events=evts,
        tasks=tasks,
    )
    calls, results = split_tool_activity(evts)
    out = str(bridge_result.get("output") or "").strip()
    if not out:
        if calls:
            out = f"[Run ended after {len(calls)} tool call(s) without a final text summary. Try narrowing the scope or asking a follow-up question in this thread.]"
        else:
            out = "[Model returned an empty response (0 tokens / possible upstream safety filter or provider refusal). Try rephrasing in defensive code-review terms or switching model.]"
    if source_dir is None:
        note = "\n\n[Context note] No trusted local source directory was available, so this response used stored metadata only."
        out = f"{out}{note}" if out else note.strip()
    msg = repo.create_message(
        thread_id=thread_id,
        role="assistant",
        content=out,
        tool_calls=calls or None,
        tool_results=results or None,
    )
    repo.finish_run(run_id=run_id, status="completed")
    return msg, team, saved


def raise_ai_error(
    *, repo, exc: Exception, run: Dict[str, Any] | None, thread_id: int
) -> None:
    if isinstance(exc, BridgeTimeoutError):
        msg = str(exc)
        code = status.HTTP_504_GATEWAY_TIMEOUT
    elif isinstance(exc, (BridgeProtocolError, BridgeError)):
        msg = str(exc)
        code = status.HTTP_502_BAD_GATEWAY
    elif isinstance(exc, OSError):
        msg = f"Failed to prepare AI context: {exc}"
        code = status.HTTP_400_BAD_REQUEST
    else:
        msg = f"AI request failed unexpectedly: {exc}"
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.exception("Unexpected AI request failure", exc_info=exc)

    if run is not None:
        fail_message(
            repo=repo,
            run_id=run["id"],
            thread_id=thread_id,
            message=msg,
        )

    raise HTTPException(status_code=code, detail=msg) from exc


def cleanup_workspace(
    *,
    source_dir: Path | None,
    workspace_root: Path | None,
    cleanup_run_workspace: Callable[[Path], None],
) -> None:
    if source_dir is None or workspace_root is None:
        return
    if workspace_root.resolve() == source_dir.resolve():
        return
    try:
        cleanup_run_workspace(workspace_root)
    except OSError:
        logger.warning(
            "Failed to clean up AI workspace: %s",
            workspace_root,
            exc_info=True,
        )
