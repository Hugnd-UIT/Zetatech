import asyncio
import logging
from typing import Any, Dict, List, Optional

from database.repos import ScanRepository
from core.routers.semgrep.task import (
    copy_custom_rules_if_available,
    download_plugin_for_semgrep,
    execute_semgrep_scan,
    mark_semgrep_scan_stopped,
    pause_between_bulk_items,
    persist_semgrep_findings,
    prepare_semgrep_output_dir,
    stop_requested,
    validate_bulk_plugin,
    validate_single_scan_slug,
    write_disabled_rules_snapshot,
)

logger = logging.getLogger("zetatech")

active_bulk_scans: Dict[int, asyncio.Event] = {}


async def run_plugin_semgrep_scan(
    scan_id: int,
    slug: str,
    download_url: str,
    repo: ScanRepository,
    stop_event: Optional[asyncio.Event] = None,
):
    safe = slug
    try:
        safe = validate_single_scan_slug(slug)
        if stop_requested(stop_event):
            mark_semgrep_scan_stopped(repo=repo, scan_id=scan_id)
            return

        repo.update_semgrep_scan(scan_id, "running")
        path = await download_plugin_for_semgrep(
            slug=safe,
            download_url=download_url,
        )
        if not path:
            raise Exception("Failed to download plugin")

        if stop_requested(stop_event):
            mark_semgrep_scan_stopped(repo=repo, scan_id=scan_id)
            return

        out = prepare_semgrep_output_dir(slug=safe, scan_id=scan_id)
        copy_custom_rules_if_available(out)

        write_disabled_rules_snapshot(out)

        res = await execute_semgrep_scan(
            output_dir=out,
            plugin_path=str(path),
            slug=safe,
        )
        summary = persist_semgrep_findings(
            repo=repo,
            scan_id=scan_id,
            findings=res.findings,
            stop_event=stop_event,
            errors=res.errors,
        )
        if summary is None:
            mark_semgrep_scan_stopped(repo=repo, scan_id=scan_id)
            return

        if stop_requested(stop_event):
            mark_semgrep_scan_stopped(repo=repo, scan_id=scan_id)
            return

        if not res.success and not res.findings:
            raise Exception(f"Semgrep failed: {', '.join(res.errors)}")

        err = ", ".join(res.errors) if res.errors else None
        status = "completed" if res.success else "failed"
        repo.update_semgrep_scan(
            scan_id,
            status,
            summary=summary,
            error=err,
        )
    except Exception as exc:
        if stop_requested(stop_event):
            mark_semgrep_scan_stopped(repo=repo, scan_id=scan_id)
            return
        repo.update_semgrep_scan(scan_id, "failed", error=str(exc))
        logger.error("Semgrep scan error for %s: %s", safe, exc, exc_info=True)


async def run_bulk_semgrep_task(
    session_id: int,
    plugins: List[Dict[str, Any]],
    repo: ScanRepository,
    stop_event: asyncio.Event,
):
    try:
        for idx, plugin in enumerate(plugins):
            if stop_event.is_set():
                logger.info("Bulk scan stopped by user at [%s/%s]", idx, len(plugins))
                break

            meta = validate_bulk_plugin(plugin)
            if not meta:
                continue

            slug = meta["slug"]
            ver = meta["version"]
            url = meta["download_url"]
            logger.info("Bulk scan [%s/%s]: %s", idx + 1, len(plugins), slug)

            try:
                scan_id = repo.create_semgrep_scan(slug, version=ver)
                await run_plugin_semgrep_scan(
                    scan_id,
                    slug,
                    url,
                    repo,
                    stop_event,
                )
                await pause_between_bulk_items(stop_event)
            except Exception as exc:
                logger.error("Bulk scan error for %s: %s", slug, exc)
    finally:
        active_bulk_scans.pop(session_id, None)
        logger.info("Bulk scan for session %s finished", session_id)
