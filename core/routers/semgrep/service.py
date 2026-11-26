from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import BackgroundTasks, HTTPException

from core.routers.semgrep.helper import (
    CORE_RULESET_CONFIGS,
    CORE_RULESET_KEYS,
    CUSTOM_RULES_PATH,
    SEMGREP_REGISTRY_RULESETS,
    _canonicalize_ruleset_value,
    _validate_rule_id_or_raise,
    _validate_semgrep_rules_config,
    _validate_slug_or_raise,
    get_disabled_config,
    load_custom_rules_document,
    save_custom_rules_document,
    save_disabled_config,
    validate_ruleset_or_raise,
)
from core.routers.semgrep.tasks import (
    active_bulk_scans,
    run_bulk_semgrep_task,
    run_plugin_semgrep_scan,
)

SEMGREP_BULK_RESULT_LIMIT = 9999


def require_valid_slug(slug: str) -> str:
    try:
        return _validate_slug_or_raise(slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid slug format") from exc


def require_valid_rule_id(rule_id: str) -> str:
    try:
        return _validate_rule_id_or_raise(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid rule ID format") from exc


def require_valid_ruleset(ruleset: str) -> str:
    try:
        return validate_ruleset_or_raise(ruleset)
    except ValueError as exc:
        detail = (
            "Ruleset cannot be empty"
            if not str(ruleset or "").strip()
            else str(exc)
        )
        raise HTTPException(status_code=400, detail=detail) from exc


def _resolve_single_scan_version(*, repo, slug: str) -> str:
    try:
        resolved = repo.get_catalog_latest_version(slug, is_theme=False)
    except Exception:
        resolved = None
    return str(resolved or "latest")


def start_semgrep_scan_for_plugin(*, repo, scan_request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    safe = require_valid_slug(scan_request.slug)
    ver = _resolve_single_scan_version(repo=repo, slug=safe)
    scan_id = repo.create_semgrep_scan(safe, version=ver)
    background_tasks.add_task(
        run_plugin_semgrep_scan,
        scan_id,
        safe,
        str(scan_request.download_url),
        repo,
    )
    return {"success": True, "scan_id": scan_id, "status": "pending"}


def get_latest_semgrep_scan(*, repo, slug: str) -> Dict[str, Any]:
    safe = require_valid_slug(slug)
    scan = repo.get_semgrep_scan(safe)
    return scan or {"status": "none"}


def add_custom_rule(rule) -> Dict[str, Any]:
    rule_id = require_valid_rule_id(rule.id)
    doc = load_custom_rules_document()
    for existing in doc.get("rules", []):
        if existing.get("id") == rule_id:
            raise HTTPException(
                status_code=400,
                detail=f"Rule with ID '{rule_id}' already exists",
            )

    item = {
        "id": rule_id,
        "pattern": rule.pattern,
        "message": rule.message,
        "languages": rule.languages,
        "severity": rule.severity,
    }
    doc.setdefault("rules", []).append(item)

    err = _validate_semgrep_rules_config(doc)
    if err:
        raise HTTPException(
            status_code=400,
            detail=(
                "Rule validation failed. Please check your Semgrep pattern syntax. "
                f"Details: {err}"
            ),
        )

    try:
        save_custom_rules_document(doc)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save rule: {exc}",
        ) from exc
    return {"success": True, "rule_id": rule_id}


def delete_custom_rule(rule_id: str) -> Dict[str, Any]:
    rule_id = require_valid_rule_id(rule_id)
    if not CUSTOM_RULES_PATH.exists():
        raise HTTPException(status_code=404, detail="No custom rules file found")

    try:
        data = load_custom_rules_document()
        orig = len(data.get("rules", []))
        data["rules"] = [
            rule for rule in data.get("rules", []) if rule.get("id") != rule_id
        ]
        if len(data["rules"]) == orig:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        save_custom_rules_document(data)
        return {"success": True, "deleted": rule_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete rule: {exc}",
        ) from exc


def toggle_custom_rule(rule_id: str) -> Dict[str, Any]:
    rule_id = require_valid_rule_id(rule_id)
    cfg = get_disabled_config()
    if rule_id in cfg["rules"]:
        cfg["rules"].remove(rule_id)
        save_disabled_config(cfg)
        return {"success": True, "rule_id": rule_id, "enabled": True}

    cfg["rules"].append(rule_id)
    save_disabled_config(cfg)
    return {"success": True, "rule_id": rule_id, "enabled": False}


def toggle_all_custom_rules(*, enabled: bool) -> Dict[str, Any]:
    data = load_custom_rules_document()
    ids: List[str] = []
    for rule in data.get("rules", []):
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str):
            continue
        try:
            ids.append(_validate_rule_id_or_raise(rule_id))
        except ValueError:
            continue

    if not ids:
        return {"success": True, "enabled": enabled, "changed": 0, "total": 0}

    cfg = get_disabled_config()
    disabled = set(cfg.get("rules", []))
    changed = 0

    if enabled:
        for rule_id in ids:
            if rule_id in disabled:
                disabled.remove(rule_id)
                changed += 1
    else:
        for rule_id in ids:
            if rule_id not in disabled:
                disabled.add(rule_id)
                changed += 1

    cfg["rules"] = sorted(disabled)
    save_disabled_config(cfg)
    return {
        "success": True,
        "enabled": enabled,
        "changed": changed,
        "total": len(ids),
    }


def add_ruleset(ruleset: str) -> Dict[str, Any]:
    rid = require_valid_ruleset(ruleset)
    cfg = get_disabled_config()
    if (
        rid not in cfg["extra_rulesets"]
        and rid not in SEMGREP_REGISTRY_RULESETS
    ):
        cfg["extra_rulesets"].append(rid)

    if rid in cfg["rulesets"]:
        cfg["rulesets"].remove(rid)

    save_disabled_config(cfg)
    return {"success": True, "ruleset_id": rid, "enabled": True}


def toggle_ruleset(ruleset_id: str) -> Dict[str, Any]:
    rid = require_valid_ruleset(ruleset_id)
    cfg = get_disabled_config()
    avail = set(CORE_RULESET_KEYS) | set(cfg.get("extra_rulesets", []))
    if rid not in avail:
        raise HTTPException(status_code=404, detail=f"Ruleset '{rid}' not found")

    if rid in cfg["rulesets"]:
        cfg["rulesets"].remove(rid)
        save_disabled_config(cfg)
        return {"success": True, "ruleset_id": rid, "enabled": True}

    cfg["rulesets"].append(rid)
    save_disabled_config(cfg)
    return {"success": True, "ruleset_id": rid, "enabled": False}


def delete_ruleset(ruleset_id: str) -> Dict[str, Any]:
    rid = require_valid_ruleset(ruleset_id)
    canonical = _canonicalize_ruleset_value(rid)
    if canonical in CORE_RULESET_KEYS or canonical in CORE_RULESET_CONFIGS:
        raise HTTPException(status_code=400, detail="Built-in rulesets cannot be deleted")

    cfg = get_disabled_config()
    extras = cfg.get("extra_rulesets", [])
    if rid not in extras:
        raise HTTPException(status_code=404, detail=f"Ruleset '{rid}' not found")

    cfg["extra_rulesets"] = [item for item in extras if item != rid]
    cfg["rulesets"] = [item for item in cfg.get("rulesets", []) if item != rid]
    save_disabled_config(cfg)
    return {"success": True, "deleted": rid}


def start_bulk_semgrep_scan(*, repo, session_id: int, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    if session_id in active_bulk_scans:
        raise HTTPException(status_code=400, detail="Bulk scan already running for this session")

    results = repo.get_session_results(session_id, limit=SEMGREP_BULK_RESULT_LIMIT)
    if not results:
        raise HTTPException(status_code=404, detail="No plugins found in this session")

    stop = asyncio.Event()
    active_bulk_scans[session_id] = stop
    background_tasks.add_task(run_bulk_semgrep_task, session_id, results, repo, stop)
    return {"success": True, "count": len(results), "status": "started"}


def stop_bulk_semgrep_scan(session_id: int) -> Dict[str, Any]:
    if session_id not in active_bulk_scans:
        raise HTTPException(status_code=404, detail="No active bulk scan found for this session")

    active_bulk_scans[session_id].set()
    return {"success": True, "status": "stopping"}


def get_bulk_semgrep_scan_stats(*, repo, session_id: int) -> Dict[str, Any]:
    results = repo.get_session_results(session_id, limit=SEMGREP_BULK_RESULT_LIMIT)
    slugs = [result["slug"] for result in results]
    stats = repo.get_semgrep_stats_for_slugs(slugs)

    total = len(slugs)
    scanned = int(stats.get("scanned_count", 0) or 0)
    progress = int((scanned / total) * 100) if total > 0 else 0

    return {
        "session_id": session_id,
        "total_plugins": total_plugins,
        "scanned_count": scanned_count,
        "progress": progress,
        "total_findings": stats.get("total_findings", 0),
        "breakdown": stats.get("breakdown", {}),
        "running_count": stats.get("running_count", 0),
        "pending_count": stats.get("pending_count", 0),
        "failed_count": stats.get("failed_count", 0),
        "completed_count": stats.get("completed_count", 0),
        "is_running": session_id in active_bulk_scans,
    }
