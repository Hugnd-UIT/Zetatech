"""
Zetatech VPS Scorer

Vulnerability Probability Score calculation.
"""

from typing import Dict, Any, List, Optional

from config import CURRENT_WP_VERSION
from models import CodeAnalysisResult


def score_vps(
    plugin: Dict[str, Any],
    days: int,
    tags: List[str],
    support: int,
    tested: str,
    flags: List[str],
    code: Optional[CodeAnalysisResult] = None,
) -> int:
    """
    Enhanced VPS calculation with code analysis integration.
    High Score = High Probability of Unknown Vulnerabilities (0-day) or Unpatched Code.

    Scoring breakdown:
    - CODE ROT (Maintenance Latency): Max 40 pts
    - ATTACK SURFACE (Intrinsic Risk): Max 30 pts
    - DEVELOPER NEGLECT (Support Health): Max 15 pts
    - TECHNICAL DEBT (Compatibility): Max 15 pts
    - REPUTATION (Quality Signal): Max 10 pts
    - CODE ANALYSIS BONUS: Max 25 pts
    """
    score = 0
    evidence = 0


    if days > 1095:
        score += 24
        evidence += 1
    elif days > 730:
        score += 18
        evidence += 1
    elif days > 365:
        score += 10
    elif days > 180:
        score += 4


    unique = set(tags or [])
    if unique:
        score += min(18, len(unique) * 2)
        if len(unique) >= 2:
            evidence += 1


    if support < 20:
        score += 10
        evidence += 1
    elif support < 50:
        score += 6


    try:
        ver = str(tested).split("-")[0]
        parts = ver.split(".")
        if len(parts) >= 2:
            num = float(f"{parts[0]}.{parts[1]}")
        else:
            num = float(ver)

        gap = CURRENT_WP_VERSION - num
        if gap >= 1.0:
            score += 8
            evidence += 1
        elif gap >= 0.5:
            score += 5
    except (ValueError, TypeError, IndexError):
        score += 2


    raw = plugin.get("rating", 0)
    if not isinstance(raw, (int, float)) or raw < 0:
        raw = 0
    elif raw > 100:
        raw = 100
    rating = raw / 20
    if rating < 2.5:
        score += 8
        evidence += 1
    elif rating < 3.5:
        score += 4
    elif rating < 4.2:
        score += 2


    if flags:
        score += min(20, 10 + len(flags) * 4)
        evidence += 2


    if code:
        if code.sanitization_issues:
            score += min(20, 6 + len(code.sanitization_issues) * 2)
            evidence += 2

        if code.dangerous_functions:
            danger = min(10, len(code.dangerous_functions) * 2)
            if code.sanitization_issues:
                danger += 4
            score += min(14, danger)
            evidence += 1

        if code.ajax_endpoints and not code.nonce_usage:
            score += 10
            evidence += 1

        if code.file_operations and code.sanitization_issues:
            score += 4
            evidence += 1


    inputs = {
        "form",
        "contact",
        "input",
        "chat",
        "comment",
        "review",
        "upload",
        "profile",
    }
    if any(tag in unique for tag in inputs):
        score += 3


    author = str(plugin.get("author", "")).lower()
    if "automattic" in author or "wordpress.org" in author:
        score = max(0, score - 6)

    if days < 30:
        score = max(0, score - 4)

    if (
        code
        and code.nonce_usage
        and not code.sanitization_issues
    ):
        score = max(0, score - 4)


    if score >= 65 and evidence < 3:
        score = min(score, 54)
    elif score >= 40 and evidence < 2:
        score = min(score, 34)

    return max(0, min(score, 100))
