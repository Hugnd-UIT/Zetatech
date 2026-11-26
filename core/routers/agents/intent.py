from typing import Any, Dict, List


SECURITY_MARKERS = {
    "security", "vulnerability", "nonce", "csrf", "xss", "sqli", "ssrf", "rce", "lfi", "auth",
    "authorization", "permission", "capability", "exploit", "güvenlik", "guvenlik", "açık", "acik",
}
STRUCTURED_MARKERS = {
    "json", "structured output", "schema", "fields", "extract as json",
}


def _has_any(text: str, phrases: set[str]) -> bool:
    low = text.casefold()
    return any(str(phrase).casefold() in low for phrase in phrases if str(phrase).strip())


def summarize_recent_thread_context(repo, thread_id: int, limit: int = 6) -> str:
    msgs = repo.list_messages(thread_id)
    if not msgs:
        return ""

    lines: List[str] = []
    for msg in msgs[-limit:]:
        role = str(msg.get("role") or "unknown")
        body = str(msg.get("content") or "").strip()
        if not body:
            continue
        short = " ".join(body.split())
        if len(short) > 300:
            short = f"{short[:297]}..."
        lines.append(f"- {role}: {short}")
    return "\n".join(lines)


def _workspace_intent(*, reason: str, content: str) -> Dict[str, Any]:
    low = str(content or "").casefold()
    return {
        "intent": "workspace_chat",
        "needs_tools": True,
        "needs_workspace_access": True,
        "requires_workspace_access": True,
        "scope": "workspace",
        "confidence": 0.99,
        "reason": reason,
        "execution_mode": "raw_open_multi_agent",
        "team_mode": "single_agent",
        "strategy": "agent",
        "security_focus": _has_any(low, SECURITY_MARKERS),
        "structured_output_requested": _has_any(low, STRUCTURED_MARKERS),
        "should_ask_clarification": False,
        "composition_source": "raw_open_multi_agent",
    }


def classify_message_intent(*, content: str, repo, thread_id: int) -> Dict[str, Any]:
    del repo, thread_id

    return _workspace_intent(
        reason="workspace_default",
        content=content,
    )


def summarize_intent_decision(intent_info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "intent": str(intent_info.get("intent") or ""),
        "needs_tools": bool(intent_info.get("needs_tools")),
        "needs_workspace_access": bool(intent_info.get("needs_workspace_access")),
        "reason": str(intent_info.get("reason") or ""),
        "execution_mode": str(intent_info.get("execution_mode") or "raw_open_multi_agent"),
        "team_mode": str(intent_info.get("team_mode") or "single_agent"),
        "strategy": str(intent_info.get("strategy") or "agent"),
        "composition_source": "raw_open_multi_agent",
    }


def resolve_message_intent(
    *,
    content: str,
    repo,
    thread_id: int,
    thread: Dict[str, Any] | None = None,
    context_summary: str = "",
    active_provider: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del thread, context_summary, active_provider
    resolved = classify_message_intent(content=content, repo=repo, thread_id=thread_id)
    resolved["normalized_decision"] = summarize_intent_decision(resolved)
    return resolved
