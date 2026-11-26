from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.repos import ScanRepository
from downloaders.plugin import PluginDownloader
from paths import resolve_runtime_paths
from scanners.semgrep import SemgrepScanner
from core.routers.semgrep.helper import (
    CUSTOM_RULES_PATH,
    _bulk_meta,
    _check_slug,
    get_active_rulesets,
    get_disabled_config,
)

RUNTIME_PATHS = resolve_runtime_paths()
SEMGREP_OUTPUTS_DIR = RUNTIME_PATHS.semgrep_outputs_dir

logger = logging.getLogger("zetatech")
BULK_SCAN_PAUSE_ITERATIONS = 5
BULK_SCAN_PAUSE_SECONDS = 0.1


def stop_requested(stop_event: Optional[asyncio.Event]) -> bool:
    return bool(stop_event and stop_event.is_set())


def mark_stopped(*, repo: ScanRepository, scan_id: int) -> None:
    repo.update_semgrep_scan(scan_id, "failed", error="Stopped by user")


async def download_plugin(
    *,
    slug: str,
    download_url: str,
) -> str | None:
    dl = PluginDownloader()
    loop = asyncio.get_running_loop()
    path = await loop.run_in_executor(
        None,
        dl.download_and_extract,
        str(download_url),
        slug,
        False,
    )
    return str(path) if path is not None else None


def prepare_out(*, slug: str, scan_id: int) -> Path:
    out = SEMGREP_OUTPUTS_DIR / f"{slug}_{scan_id}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def copy_rules(output_dir: Path) -> None:
    if not CUSTOM_RULES_PATH.exists():
        return
    try:
        shutil.copy2(CUSTOM_RULES_PATH, output_dir / "custom_rules.yaml")
    except Exception:
        logger.warning("Failed to copy custom Semgrep rules into scan directory.")


def write_disabled(output_dir: Path) -> None:
    rules = get_disabled_config().get("rules", [])
    if not rules:
        return
    try:
        with open(output_dir / "disabled_rules.json", "w") as f:
            json.dump(rules, f)
    except Exception:
        logger.warning("Failed to write disabled rules for Semgrep scan.")


async def exec_scan(*, output_dir: Path, plugin_path: str, slug: str):
    scanner = SemgrepScanner(
        output_dir=str(output_dir),
        use_registry_rules=True,
        registry_rulesets=get_active_rulesets(),
    )
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, scanner.scan_plugin, str(plugin_path), slug)


def build_summary(findings: List[Dict[str, Any]], errors: Optional[List[str]] = None) -> Dict[str, Any]:
    summary = {
        "total_findings": len(findings),
        "breakdown": {"ERROR": 0, "WARNING": 0, "INFO": 0},
    }
    if errors:
        summary["errors"] = list(errors)
    for finding in findings:
        severity = finding.get("extra", {}).get("severity", "INFO")
        summary["breakdown"][severity] = summary["breakdown"].get(severity, 0) + 1
    return summary


def save_findings(
    *,
    repo: ScanRepository,
    scan_id: int,
    findings: List[Dict[str, Any]],
    stop_event: Optional[asyncio.Event],
    errors: Optional[List[str]] = None,
) -> Dict[str, Any] | None:
    for finding in findings:
        if stop_requested(stop_event):
            return None
        repo.save_semgrep_finding(scan_id, finding)
    return build_summary(findings, errors=errors)


def check_plugin(plugin: Dict[str, Any]) -> Dict[str, Any] | None:
    raw_slug = plugin.get("slug")
    try:
        plugin_meta = _bulk_meta(plugin)
    except ValueError:
        logger.warning("Skipping plugin with invalid slug: %s", raw_slug)
        return None
    return plugin_meta


async def pause_bulk(stop_event: asyncio.Event) -> None:
    for _ in range(BULK_SCAN_PAUSE_ITERATIONS):
        if stop_event.is_set():
            break
        await asyncio.sleep(BULK_SCAN_PAUSE_SECONDS)


def check_slug(slug: str) -> str:
    return _check_slug(slug)
