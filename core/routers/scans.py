from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from analyzers.risk import label_risk
from core.limiter import limiter
from core.schemas import ScanRequest
from core.websockets import manager
from database.repos import ScanRepository
from models import PluginResult, ScanConfig, ScanStatus
from scanners.plugin import PluginScanner
from scanners.theme import ThemeScanner

router = APIRouter(prefix="/api/scans", tags=["scans"])
repo = ScanRepository()

active_scans: Dict[int, Any] = {}
HIGH_RISK_LABELS = {"HIGH", "CRITICAL"}


def request_scanner_stop(scanner: Any) -> None:
    stop = getattr(scanner, "stop", None)
    if callable(stop):
        stop()


def apply_risk_labels(results: List[Dict[str, Any]]) -> None:
    label_risk(
        results,
        get_score=lambda item: int(item.get("score", 0) or 0),
        set_label=lambda item, label: item.__setitem__("relative_risk", label),
    )


def build_scan_config(scan_request) -> ScanConfig:
    sort = scan_request.sort
    pages = scan_request.pages

    if scan_request.abandoned and sort == "updated":
        sort = "popular"
    if scan_request.abandoned and pages == 5:
        pages = 100

    return ScanConfig(
        pages=pages,
        limit=scan_request.limit,
        min_installs=scan_request.min_installs,
        max_installs=scan_request.max_installs,
        sort=sort,
        smart=scan_request.smart,
        abandoned=scan_request.abandoned,
        user_facing=scan_request.user_facing,
        themes=scan_request.themes,
        min_days=scan_request.min_days,
        max_days=scan_request.max_days,
        aggressive=scan_request.aggressive,
    )


def _theme_result(result: Dict[str, Any]) -> PluginResult:
    return PluginResult(
        slug=result.get("slug", ""),
        name=result.get("name", "Unknown"),
        version=result.get("version", "?"),
        score=result.get("risk_score", 0),
        relative_risk=result.get("risk_level", ""),
        installations=result.get("downloads", 0),
        days_since_update=result.get("days_since_update", 0),
        is_theme=True,
        wp_org_link=result.get("wp_org_link", ""),
        trac_link=result.get("trac_link", ""),
        wpscan_link=result.get("wpscan_link", ""),
        cve_search_link=result.get("cve_search_link", ""),
        download_link=result.get("download_link", ""),
    )


async def _send_event(session_id: int, payload: Dict[str, Any]) -> None:
    await manager.send_to_session(session_id, payload)


def _send_async(
    loop: asyncio.AbstractEventLoop,
    session_id: int,
    payload: Dict[str, Any],
) -> None:
    asyncio.run_coroutine_threadsafe(_send_event(session_id, payload), loop)


def _is_cancelled(session_id: int, repo: ScanRepository) -> bool:
    state = repo.get_session(session_id)
    return bool(
        state and state.get("status") == ScanStatus.CANCELLED.value
    )


async def _handle_cancel(
    *,
    session_id: int,
    repo: ScanRepository,
    found_count: int,
    high_risk_count: int,
) -> bool:
    if not _is_cancelled(session_id, repo):
        return False

    repo.update_session_status(
        session_id,
        ScanStatus.CANCELLED,
        total_found=found_count,
        high_risk_count=high_risk_count,
    )
    await _send_event(
        session_id,
        {
            "type": "cancelled",
            "session_id": session_id,
            "total_found": found_count,
            "high_risk_count": high_risk_count,
        },
    )
    return True


async def _dedup_scan(
    *,
    session_id: int,
    repo: ScanRepository,
    config: ScanConfig,
) -> bool:
    prev_id = repo.get_latest_session_by_config(config.to_dict(), session_id)
    if not prev_id:
        return False

    cur = set(repo.get_result_slugs(session_id))
    prev = set(repo.get_result_slugs(prev_id))
    if cur != prev:
        return False

    repo.delete_session(session_id)
    repo.mark_session_merged(prev_id)
    await _send_event(
        session_id,
        {
            "type": "deduplicated",
            "original_session_id": prev_id,
            "message": "Results identical to previous scan. Merged.",
        },
    )
    return True


def _save_emit(
    *,
    loop: asyncio.AbstractEventLoop,
    session_id: int,
    repo: ScanRepository,
    result: PluginResult,
    found_count: int,
) -> None:
    repo.save_result(session_id, result)
    _send_async(
        loop,
        session_id,
        {
            "type": "result",
            "data": result.to_dict(),
            "found_count": found_count,
        },
    )


def _emit_progress(
    *,
    loop: asyncio.AbstractEventLoop,
    session_id: int,
    current: int,
    total: int,
) -> None:
    _send_async(
        loop,
        session_id,
        {
            "type": "progress",
            "current": current,
            "total": total,
            "percent": int((current / total) * 100),
        },
    )


def _count_high(results: List[PluginResult]) -> int:
    return sum(
        1
        for result in results
        if getattr(result, "relative_risk", "") in HIGH_RISK_LABELS
    )


async def _theme_scan(
    *,
    session_id: int,
    config: ScanConfig,
    repo: ScanRepository,
) -> tuple[int, int]:
    found = 0
    high = 0
    loop = asyncio.get_running_loop()

    def on_theme(result: Dict[str, Any]) -> None:
        nonlocal found, high
        found += 1
        if result.get("risk_level") == "HIGH":
            high += 1

        item = _theme_result(result)
        _save_emit(
            loop=loop,
            session_id=session_id,
            repo=repo,
            result=item,
            found_count=found,
        )

    scanner = ThemeScanner(
        pages=config.pages,
        limit=config.limit,
        sort=config.sort,
        on_result=on_theme,
    )
    active_scans[session_id] = scanner
    await loop.run_in_executor(None, scanner.scan)
    return found, high


async def _plugin_scan(
    *,
    session_id: int,
    config: ScanConfig,
    repo: ScanRepository,
) -> tuple[int, int]:
    found = 0
    loop = asyncio.get_running_loop()
    scanner = PluginScanner(config)
    active_scans[session_id] = scanner

    def on_res(result: PluginResult) -> None:
        nonlocal found
        found += 1
        _save_emit(
            loop=loop,
            session_id=session_id,
            repo=repo,
            result=result,
            found_count=found,
        )

    def on_prog(current: int, total: int) -> None:
        _emit_progress(
            loop=loop,
            session_id=session_id,
            current=current,
            total=total,
        )

    scanner.on_result = on_res
    scanner.on_progress = on_prog
    await loop.run_in_executor(None, scanner.scan)
    return found, _count_high(scanner.results)


async def _scan_mode(
    *,
    session_id: int,
    config: ScanConfig,
    repo: ScanRepository,
) -> tuple[int, int]:
    if config.themes:
        return await _theme_scan(session_id=session_id, config=config, repo=repo)
    return await _plugin_scan(session_id=session_id, config=config, repo=repo)


async def _finalize_scan(
    *,
    session_id: int,
    config: ScanConfig,
    repo: ScanRepository,
    found_count: int,
    high_risk_count: int,
) -> bool:
    if await _handle_cancel(
        session_id=session_id,
        repo=repo,
        found_count=found_count,
        high_risk_count=high_risk_count,
    ):
        return False

    repo.update_session_status(
        session_id,
        ScanStatus.COMPLETED,
        total_found=found_count,
        high_risk_count=high_risk_count,
    )

    if await _dedup_scan(
        session_id=session_id,
        repo=repo,
        config=config,
    ):
        return False

    await _send_event(
        session_id,
        {
            "type": "complete",
            "session_id": session_id,
            "total_found": found_count,
            "high_risk_count": high_risk_count,
        },
    )
    return True


async def run_scan_task(session_id: int, config: ScanConfig, repo: ScanRepository) -> None:
    try:
        repo.update_session_status(session_id, ScanStatus.RUNNING)
        await _send_event(session_id, {"type": "start", "session_id": session_id})

        found, high = await _scan_mode(
            session_id=session_id,
            config=config,
            repo=repo,
        )

        await _finalize_scan(
            session_id=session_id,
            config=config,
            repo=repo,
            found_count=found,
            high_risk_count=high,
        )
    except Exception as exc:
        repo.update_session_status(session_id, ScanStatus.FAILED, error_message=str(exc))
        await _send_event(session_id, {"type": "error", "message": str(exc)})
    finally:
        active_scans.pop(session_id, None)


def list_scan_sessions(*, repo: ScanRepository, limit: int) -> Dict[str, Any]:
    return {"sessions": repo.get_all_sessions(limit)}


def create_scan_session(
    *,
    repo: ScanRepository,
    scan_request,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    config = build_scan_config(scan_request)
    session_id = repo.create_session(config)
    background_tasks.add_task(run_scan_task, session_id, config, repo)
    return {
        "session_id": session_id,
        "status": "started",
        "websocket_url": f"/ws/scans/{session_id}",
    }


def get_scan_session(*, repo: ScanRepository, session_id: int) -> Dict[str, Any]:
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Scan session not found")
    return session


def get_scan_session_results(
    *,
    repo: ScanRepository,
    session_id: int,
    sort_by: str,
    sort_order: str,
    limit: int,
) -> Dict[str, Any]:
    get_scan_session(repo=repo, session_id=session_id)
    results = repo.get_session_results(session_id, sort_by, sort_order, limit)
    apply_risk_labels(results)

    slugs = [result["slug"] for result in results]
    statuses = repo.get_semgrep_statuses_for_slugs(slugs)
    for result in results:
        result["semgrep"] = statuses.get(result["slug"])

    return {"session_id": session_id, "total": len(results), "results": results}


def delete_scan_session(*, repo: ScanRepository, session_id: int) -> Dict[str, Any]:
    scanner = active_scans.pop(session_id, None)
    if scanner is not None:
        request_scanner_stop(scanner)

    ok = repo.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Scan session not found")
    return {"status": "deleted"}


@router.get("")
@limiter.limit("10000/minute")
async def list_scans(request: Request, limit: int = 50):
    return list_scan_sessions(repo=repo, limit=limit)


@router.post("")
@limiter.limit("5000/minute")
async def create_scan(
    request: Request, scan_request: ScanRequest, background_tasks: BackgroundTasks
):
    return create_scan_session(
        repo=repo,
        scan_request=scan_request,
        background_tasks=background_tasks,
    )


@router.get("/{session_id}")
async def get_scan(session_id: int):
    return get_scan_session(repo=repo, session_id=session_id)


@router.get("/{session_id}/results")
async def get_scan_results(
    session_id: int,
    sort_by: str = "score",
    sort_order: str = "desc",
    limit: int = 100,
):
    return get_scan_session_results(
        repo=repo,
        session_id=session_id,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
    )


@router.delete("/{session_id}")
async def delete_scan(session_id: int):
    return delete_scan_session(repo=repo, session_id=session_id)
