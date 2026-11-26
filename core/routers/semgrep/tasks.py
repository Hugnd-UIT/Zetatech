import asyncio
import logging
from typing import Any, Dict, List, Optional

from database.repos import ScanRepository
from core.routers.semgrep.task import (
    check_plugin,
    check_slug,
    copy_rules,
    download_plugin,
    exec_scan,
    mark_stopped,
    pause_bulk,
    prepare_out,
    save_findings,
    stop_requested,
    write_disabled,
)

logger = logging.getLogger("zetatech")

active_bulk_scans: Dict[int, asyncio.Event] = {}


async def run_scan(
    scan_id: int,
    slug: str,
    download_url: str,
    repo: ScanRepository,
    stop_event: Optional[asyncio.Event] = None,
):
    safe = slug
    try:
        safe = check_slug(slug)
        if stop_requested(stop_event):
            mark_stopped(repo=repo, scan_id=scan_id)
            return

        repo.update_semgrep_scan(scan_id, "running")
        path = await download_plugin(
            slug=safe,
            download_url=download_url,
        )
        if not path:
            raise Exception("Failed to download plugin")

        if stop_requested(stop_event):
            mark_stopped(repo=repo, scan_id=scan_id)
            return

        out = prepare_out(slug=safe, scan_id=scan_id)
        copy_rules(out)

        write_disabled(out)

        res = await exec_scan(
            output_dir=out,
            plugin_path=str(path),
            slug=safe,
        )
        summary = save_findings(
            repo=repo,
            scan_id=scan_id,
            findings=res.findings,
            stop_event=stop_event,
            errors=res.errors,
        )
        if summary is None:
            mark_stopped(repo=repo, scan_id=scan_id)
            return

        if stop_requested(stop_event):
            mark_stopped(repo=repo, scan_id=scan_id)
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
            mark_stopped(repo=repo, scan_id=scan_id)
            return
        repo.update_semgrep_scan(scan_id, "failed", error=str(exc))
        logger.error("Semgrep scan error for %s: %s", safe, exc, exc_info=True)


async def run_bulk(
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

            meta = check_plugin(plugin)
            if not meta:
                continue

            slug = meta["slug"]
            ver = meta["version"]
            url = meta["download_url"]
            logger.info("Bulk scan [%s/%s]: %s", idx + 1, len(plugins), slug)

            try:
                scan_id = repo.create_semgrep_scan(slug, version=ver)
                await run_scan(
                    scan_id,
                    slug,
                    url,
                    repo,
                    stop_event,
                )
                await pause_bulk(stop_event)
            except Exception as exc:
                logger.error("Bulk scan error for %s: %s", slug, exc)
    finally:
        active_bulk_scans.pop(session_id, None)
        logger.info("Bulk scan for session %s finished", session_id)
