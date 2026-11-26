import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from agents.context import (
    build_plugin_context_for_source,
    ensure_thread_source_dir,
)
from agents.repos import AIRepository
from agents.bridge import run_agent_bridge, run_agent_bridge_stream
from agents.workspace import cleanup_run_workspace
from paths import resolve_runtime_paths
from core.routers.agents.provider import (
    run_provider_connection_test,
    urllib_request,
)
from core.routers.agents.stream import stream_ai_message_events
from core.routers.agents.serialize import (
    list_latest_thread_team_events,
    list_structured_thread_events,
    serialize_message,
    serialize_run_approval,
    serialize_settings,
    serialize_settings_dashboard,
    serialize_thread,
)
from core.routers.agents.service import execute_ai_message
from core.schemas import (
    AIMessageCreateRequest,
    AIMessageExecutionResponse,
    AIPluginThreadRequest,
    AIRunApprovalDecisionRequest,
    AIRunApprovalResponse,
    AISourcePrepareResponse,
    AISettingsDashboardResponse,
    AISettingsRequest,
    AISettingsTestRequest,
    AISettingsTestResponse,
    AIThreadDeleteRequest,
    AIThreadListResponse,
    AIThreadMessagesResponse,
    AIThreadUpdateRequest,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])
repo = AIRepository()


def _dashboard():
    profiles = repo.list_providers()
    active = repo.get_active_provider()
    return serialize_settings_dashboard(repo, active, profiles)


@router.get("/settings", response_model=AISettingsDashboardResponse)
def get_settings():
    return _dashboard()


@router.post("/settings")
def save_settings(payload: AISettingsRequest):
    settings = repo.upsert_provider_settings(
        provider=payload.provider,
        profile_key=payload.profile_key,
        display_name=payload.display_name,
        api_key=payload.api_key,
        model=payload.model,
        models=payload.models,
        base_url=str(payload.base_url) if payload.base_url else None,
        is_active=payload.is_active,
    )
    return serialize_settings(repo, settings)


@router.post("/settings/test", response_model=AISettingsTestResponse)
def test_settings_profile(payload: AISettingsTestRequest):
    cand = repo.upsert_provider_settings(
        provider=payload.provider,
        profile_key=payload.profile_key,
        display_name=payload.display_name,
        api_key=payload.api_key,
        model=payload.model,
        models=payload.models,
        base_url=str(payload.base_url) if payload.base_url else None,
        is_active=False,
    )
    key = str(cand.get("api_key") or payload.api_key or "").strip()
    url = str(payload.base_url) if payload.base_url else cand.get("base_url")
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is required to test the AI connection.")

    msg = run_provider_connection_test(
        provider=payload.provider,
        api_key=key,
        model=payload.model,
        base_url=url,
    )
    return {
        "ok": True,
        "message": msg,
        "provider": payload.provider,
        "model": payload.model,
        "profile_key": cand.get("profile_key"),
    }


@router.get("/threads/plugin", response_model=AIThreadListResponse)
def list_plugin_threads(plugin_slug: str, is_theme: bool = False):
    threads = repo.list_threads_for_scope(plugin_slug=plugin_slug, is_theme=is_theme)
    return {"threads": [serialize_thread(thread) for thread in threads]}


@router.post("/threads/plugin")
def create_or_get_plugin_thread(payload: AIPluginThreadRequest):
    thread = repo.get_or_create_thread(
        plugin_slug=payload.plugin_slug,
        is_theme=payload.is_theme,
        title=payload.title,
        last_scan_session_id=payload.last_scan_session_id,
    )
    return serialize_thread(thread)


@router.post("/threads/plugin/new")
def create_plugin_thread(payload: AIPluginThreadRequest):
    thread = repo.create_thread(
        plugin_slug=payload.plugin_slug,
        is_theme=payload.is_theme,
        title=payload.title,
        last_scan_session_id=payload.last_scan_session_id,
    )
    return serialize_thread(thread)


@router.get("/threads/{thread_id}/messages", response_model=AIThreadMessagesResponse)
def list_thread_messages(thread_id: int, plugin_slug: str, is_theme: bool = False):
    thread = repo.get_thread_for_scope(thread_id, plugin_slug=plugin_slug, is_theme=is_theme)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI thread not found.",
        )


    repo.fail_stale_thread_runs(thread_id, max_age_seconds=1800)
    msgs = [serialize_message(m) for m in repo.list_messages(thread_id)]
    latest = repo.get_latest_run(thread_id)
    pending = str(latest.get("status") or "").lower() in {"pending", "running"} if latest else False
    team = list_latest_thread_team_events(repo, thread_id)
    approval = repo.get_thread_pending_approval(thread_id)
    return {
        "messages": msgs,
        "has_pending_run": pending,
        "team_events": team,
        "pending_approval": serialize_run_approval(approval),
    }


@router.patch("/threads/{thread_id}")
def update_thread(thread_id: int, payload: AIThreadUpdateRequest):
    thread = repo.get_thread_for_scope(thread_id, plugin_slug=payload.plugin_slug, is_theme=payload.is_theme)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI thread not found.",
        )

    repo.set_thread_title(thread_id, payload.title.strip())
    updated = repo.get_thread(thread_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI thread not found after update.",
        )
    return serialize_thread(updated)


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: int, payload: AIThreadDeleteRequest):
    thread = repo.get_thread_for_scope(thread_id, plugin_slug=payload.plugin_slug, is_theme=payload.is_theme)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI thread not found.",
        )

    repo.delete_thread(thread_id)
    return {"ok": True, "thread_id": thread_id}


@router.post("/threads/{thread_id}/source", response_model=AISourcePrepareResponse)
def prepare_thread_source(thread_id: int, payload: AIPluginThreadRequest):
    thread = repo.get_thread_for_scope(thread_id, plugin_slug=payload.plugin_slug, is_theme=payload.is_theme)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI thread not found.",
        )

    src = ensure_thread_source_dir(
        db_path=repo.db_path,
        plugin_slug=payload.plugin_slug,
        is_theme=payload.is_theme,
        last_scan_session_id=payload.last_scan_session_id,
        root_path=Path.cwd(),
    )
    if src is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to prepare source for this plugin.",
        )

    repo.update_thread_memory(
        thread_id,
        last_source_path=str(src.resolve()),
    )
    updated = repo.get_thread(thread_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI thread not found after source prepare.",
        )
    return {"ok": True, "thread": serialize_thread(updated)}


@router.post("/messages", response_model=AIMessageExecutionResponse)
def create_message(payload: AIMessageCreateRequest):
    return execute_ai_message(
        repo=repo,
        payload=payload,
        path_cwd=Path.cwd,
        build_plugin_context_for_source=build_plugin_context_for_source,
        resolve_existing_thread_source_path=ensure_thread_source_dir,
        cleanup_run_workspace=cleanup_run_workspace,
        run_agent_bridge=run_agent_bridge,
    )


@router.post("/messages/stream")
def create_message_stream(payload: AIMessageCreateRequest):
    return StreamingResponse(
        stream_ai_message_events(
            repo=repo,
            payload=payload,
            path_cwd=Path.cwd,
            build_plugin_context_for_source=build_plugin_context_for_source,
            resolve_existing_thread_source_path=ensure_thread_source_dir,
            cleanup_run_workspace=cleanup_run_workspace,
            run_agent_bridge_stream=run_agent_bridge_stream,
        ),
        media_type="application/x-ndjson",
    )


@router.post("/runs/{run_id}/approval", response_model=AIRunApprovalResponse)
def decide_run_approval(run_id: int, payload: AIRunApprovalDecisionRequest):
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found.")
    thread = repo.get_thread_for_scope(int(run.get("thread_id") or 0), plugin_slug=payload.plugin_slug, is_theme=payload.is_theme)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI thread not found.")
    approval = repo.get_run_approval(run_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
    if str(approval.get("status") or "") != "pending":
        return serialize_run_approval(approval)

    ctrl_path = str(approval.get("control_path") or "").strip()
    if not ctrl_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval control path is missing.")

    ws_path = str(run.get("workspace_path") or "").strip()
    if not ws_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run workspace is missing.")

    ctrl_file = Path(ctrl_path).resolve()
    base_dir = resolve_runtime_paths().approvals_dir.resolve()
    try:
        if os.path.commonpath([str(base_dir), str(ctrl_file)]) != str(base_dir):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid approval control path.",
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid approval control path.",
        ) from exc

    ctrl_file.parent.mkdir(parents=True, exist_ok=True)
    ctrl_file.write_text(json.dumps({"decision": payload.decision}), encoding="utf-8")
    updated = repo.upsert_run_approval(
        run_id,
        int(run.get("thread_id") or 0),
        status="decided",
        decision=payload.decision,
    )
    if payload.decision == "rejected":
        repo.finish_run(run_id=run_id, status="failed", error_message="Run stopped by manual approval rejection.")
    return serialize_run_approval(updated)


_serialize_settings = lambda settings: serialize_settings(repo, settings)
_serialize_message = serialize_message
_serialize_thread = serialize_thread
_list_structured_thread_events = lambda thread_id: list_structured_thread_events(repo, thread_id)
