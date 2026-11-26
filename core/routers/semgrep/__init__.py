from fastapi import APIRouter, BackgroundTasks, Request

from database.repos import ScanRepository
from core.limiter import limiter
from core.routers.semgrep.helper import build_semgrep_rules_response
from core.routers.semgrep.service import (
    add_custom_rule,
    add_ruleset,
    delete_custom_rule,
    delete_ruleset,
    get_bulk_semgrep_scan_stats,
    get_latest_semgrep_scan,
    start_bulk_semgrep_scan,
    start_semgrep_scan_for_plugin,
    stop_bulk_semgrep_scan,
    toggle_all_custom_rules,
    toggle_custom_rule,
    toggle_ruleset,
)
from core.schemas import (
    DownloadRequest,
    SemgrepBulkToggleRequest,
    SemgrepRuleRequest,
    SemgrepRulesetRequest,
)

router = APIRouter(prefix="/api/semgrep", tags=["semgrep"])
repo = ScanRepository()


@router.post("/scan")
@limiter.limit("5000/minute")
async def start_semgrep_scan(
    request: Request, scan_request: DownloadRequest, background_tasks: BackgroundTasks
):
    return start_semgrep_scan_for_plugin(
        repo=repo,
        scan_request=scan_request,
        background_tasks=background_tasks,
    )


@router.get("/scan/{slug}")
async def get_semgrep_scan(slug: str):
    return get_latest_semgrep_scan(repo=repo, slug=slug)


@router.get("/rules")
async def get_semgrep_rules():
    return build_semgrep_rules_response()


@router.post("/rules")
async def create_semgrep_rule(rule: SemgrepRuleRequest):
    return add_custom_rule(rule)


@router.delete("/rules/{rule_id}")
async def remove_semgrep_rule(rule_id: str):
    return delete_custom_rule(rule_id)


@router.post("/rules/{rule_id}/toggle")
async def toggle_semgrep_rule(rule_id: str):
    return toggle_custom_rule(rule_id)


@router.post("/rules/actions/toggle-all")
async def toggle_all_semgrep_rules(toggle_request: SemgrepBulkToggleRequest):
    return toggle_all_custom_rules(enabled=toggle_request.enabled)


@router.post("/rulesets")
async def create_ruleset(ruleset_request: SemgrepRulesetRequest):
    return add_ruleset(ruleset_request.ruleset)


@router.post("/rulesets/{ruleset_id:path}/toggle")
async def toggle_semgrep_ruleset(ruleset_id: str):
    return toggle_ruleset(ruleset_id)


@router.delete("/rulesets/{ruleset_id:path}")
async def remove_ruleset(ruleset_id: str):
    return delete_ruleset(ruleset_id)


@router.post("/bulk/{session_id}")
async def run_bulk_semgrep(session_id: int, background_tasks: BackgroundTasks):
    return start_bulk_semgrep_scan(
        repo=repo,
        session_id=session_id,
        background_tasks=background_tasks,
    )


@router.post("/bulk/{session_id}/stop")
async def stop_bulk_semgrep(session_id: int):
    return stop_bulk_semgrep_scan(session_id)


@router.get("/bulk/{session_id}/stats")
async def get_bulk_semgrep_stats(session_id: int):
    return get_bulk_semgrep_scan_stats(repo=repo, session_id=session_id)
