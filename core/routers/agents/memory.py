from pathlib import Path
from typing import Any, Dict, List


def summarize_thread_memory(repo, thread_id: int) -> str:
    mem = repo.get_thread_memory(thread_id)
    parts: List[str] = []
    if mem.get("conversation_summary"):
        parts.append(f"Conversation memory: {mem['conversation_summary']}")
    if mem.get("analysis_summary"):
        parts.append(f"Analysis memory: {mem['analysis_summary']}")
    files = list(mem.get("important_files") or [])
    if files:
        parts.append(f"Important files: {', '.join(files[:12])}")
    if mem.get("findings_summary"):
        parts.append(f"Findings memory: {mem['findings_summary']}")
    if mem.get("architecture_notes"):
        parts.append(f"Architecture memory: {mem['architecture_notes']}")
    if mem.get("last_source_path"):
        parts.append(f"Previous source path: {mem['last_source_path']}")
    return "\n".join(part for part in parts if part)


def _trim(text: str, limit: int = 500) -> str:
    compact = " ".join(str(text or "").split()).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _file_candidates(event: Dict[str, Any]) -> List[str]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    items: List[str] = []

    def add(val: Any) -> None:
        text = str(val or "").strip()
        if not text or text.startswith("/") or "\n" in text:
            return
        if text not in items:
            items.append(text)

    for key in ("path", "file_path"):
        add(data.get(key))

    for sub in ("input", "result"):
        nested = data.get(sub)
        if isinstance(nested, dict):
            for key in ("path", "file_path"):
                add(nested.get(key))

    return items


def build_updated_thread_memory(
    *,
    repo,
    thread_id: int,
    user_content: str,
    assistant_output: str,
    source_dir: Path | None,
    run_events: List[Dict[str, Any]],
    run_tasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    prev = repo.get_thread_memory(thread_id)
    prior = list(prev.get("important_files") or [])
    found: List[str] = []
    for event in run_events:
        for cand in _file_candidates(event):
            if cand not in found:
                found.append(cand)

    files: List[str] = []
    for item in [*prior, *found]:
        norm = str(item or "").strip()
        if norm and norm not in files:
            files.append(norm)
    files = files[:20]

    tasks = []
    for task in run_tasks[:8]:
        title = str(task.get("title") or "").strip()
        result = str(task.get("result") or "").strip()
        if title and result:
            tasks.append(f"{title}: {result}")
        elif title:
            tasks.append(title)

    conv = _trim(
        " | ".join(
            part
            for part in [
                str(prev.get("conversation_summary") or "").strip(),
                f"User: {user_content}",
                f"Assistant: {assistant_output}",
            ]
            if part
        ),
        700,
    )
    analysis = _trim(
        " | ".join(
            part
            for part in [
                str(prev.get("analysis_summary") or "").strip(),
                assistant_output,
                " ; ".join(tasks),
            ]
            if part
        ),
        900,
    )
    findings = _trim(
        str(prev.get("findings_summary") or "")
        + (" | " if prev.get("findings_summary") and assistant_output else "")
        + assistant_output,
        700,
    )
    arch = _trim(
        " | ".join(
            part
            for part in [
                str(prev.get("architecture_notes") or "").strip(),
                "Files seen: " + ", ".join(files[:8]) if files else "",
            ]
            if part
        ),
        500,
    )
    return {
        "conversation_summary": conv,
        "analysis_summary": analysis,
        "important_files": files,
        "findings_summary": findings,
        "architecture_notes": arch,
        "last_source_path": str(source_dir.resolve()) if source_dir is not None else str(prev.get("last_source_path") or ""),
    }
