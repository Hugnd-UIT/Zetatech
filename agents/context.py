import json
from pathlib import Path
from typing import Any, Dict, Optional

from database.models import get_db, init_db
from agents.workspace import ensure_within_workspace
from downloaders.plugin import PluginDownloader
from downloaders.theme import ThemeDownloader
from paths import resolve_runtime_paths


def _empty_semgrep() -> Dict[str, Any]:
    return {"scan": None, "summary": {}, "findings": []}


def _plugin_row(cursor, slug: str, is_theme: bool, session_id: int):
    cursor.execute(
        """
        SELECT
            pc.slug,
            pc.is_theme,
            pcs.session_id AS last_scan_session_id,
            pcs.score_snapshot AS score,
            pcs.version_snapshot AS latest_version,
            pcs.installations_snapshot AS installations,
            pcs.days_since_update_snapshot AS days_since_update,
            pcs.semgrep_findings_snapshot AS semgrep_findings
        FROM plugin_catalog pc
        INNER JOIN plugin_catalog_sessions pcs ON pcs.catalog_id = pc.id
        WHERE pc.slug = ? AND pc.is_theme = ? AND pcs.session_id = ?
        ORDER BY pcs.seen_at DESC, pcs.id DESC, pc.id DESC
        LIMIT 1
        """,
        (slug, int(is_theme), session_id),
    )
    return cursor.fetchone()


def _scan_row(cursor, slug: str, version: Optional[str]):
    if not version:
        return None

    cursor.execute(
        """
        SELECT * FROM semgrep_scans
        WHERE slug = ? AND version = ? AND status = 'completed'
        ORDER BY completed_at DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (slug, version),
    )
    return cursor.fetchone()


def _source_dir(slug: str, is_theme: bool) -> Path:
    dir_root = resolve_runtime_paths().plugins_dir
    folder = "Themes" if is_theme else "Plugins"
    return dir_root / folder / slug / "source"


def _source_str(slug: str, is_theme: bool) -> str:
    return str(_source_dir(slug, is_theme))


def _wp_url(slug: str, is_theme: bool, version: Optional[str]) -> str:
    kind = "theme" if is_theme else "plugin"
    ver = str(version or "latest").strip() or "latest"
    return f"https://downloads.wordpress.org/{kind}/{slug}.{ver}.zip"


def _download_meta(cursor, slug: str, is_theme: bool, session_id: Optional[int]) -> Dict[str, Optional[str]]:
    if session_id is not None:
        cursor.execute(
            """
            SELECT sr.download_link, sr.version
            FROM scan_results sr
            WHERE sr.session_id = ? AND sr.slug = ? AND sr.is_theme = ?
            ORDER BY sr.id DESC
            LIMIT 1
            """,
            (session_id, slug, int(is_theme)),
        )
        row = cursor.fetchone()
        if row:
            return {
                "download_link": row["download_link"] or None,
                "version": row["version"] or None,
            }

    cursor.execute(
        """
        SELECT sr.download_link, sr.version
        FROM scan_results sr
        WHERE sr.slug = ? AND sr.is_theme = ?
        ORDER BY sr.session_id DESC, sr.id DESC
        LIMIT 1
        """,
        (slug, int(is_theme)),
    )
    row = cursor.fetchone()
    if row:
        return {
            "download_link": row["download_link"] or None,
            "version": row["version"] or None,
        }

    cursor.execute(
        """
        SELECT pc.latest_version
        FROM plugin_catalog pc
        WHERE pc.slug = ? AND pc.is_theme = ?
        ORDER BY pc.id DESC
        LIMIT 1
        """,
        (slug, int(is_theme)),
    )
    row = cursor.fetchone()
    if row:
        return {
            "download_link": None,
            "version": row["latest_version"] or None,
        }

    return {"download_link": None, "version": None}


def download_info(
    db_path: Optional[Path],
    plugin_slug: str,
    is_theme: bool,
    last_scan_session_id: Optional[int],
) -> Dict[str, Optional[str]]:
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        info = _download_meta(cursor, plugin_slug, is_theme, last_scan_session_id)
    url = info.get("download_link") or _wp_url(plugin_slug, is_theme, info.get("version"))
    return {
        "download_url": url,
        "version": info.get("version"),
    }


def ensure_source(
    db_path: Optional[Path],
    plugin_slug: str,
    is_theme: bool,
    last_scan_session_id: Optional[int],
    root_path: Path,
) -> Optional[Path]:
    existing = existing_source(
        db_path=db_path,
        plugin_slug=plugin_slug,
        is_theme=is_theme,
        last_scan_session_id=last_scan_session_id,
        root_path=root_path,
    )
    if existing is not None:
        return existing.resolve()

    info = download_info(
        db_path=db_path,
        plugin_slug=plugin_slug,
        is_theme=is_theme,
        last_scan_session_id=last_scan_session_id,
    )
    url = str(info.get("download_url") or "").strip()
    if not url:
        return None

    base = resolve_runtime_paths().plugins_dir
    downloader = (
        ThemeDownloader(base_dir=base)
        if is_theme
        else PluginDownloader(base_dir=base)
    )
    extracted = downloader.download_and_extract(url, plugin_slug, verbose=False)
    if extracted is None or not extracted.exists() or not extracted.is_dir():
        return None
    return extracted.resolve()


def thread_source(
    db_path: Optional[Path],
    plugin_slug: str,
    is_theme: bool,
    last_scan_session_id: int,
) -> str:
    init_db(db_path)

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT is_theme
            FROM scan_results
            WHERE session_id = ? AND slug = ? AND is_theme = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (last_scan_session_id, plugin_slug, int(is_theme)),
        )
        row = cursor.fetchone()

    if not row:
        raise LookupError(
            "Trusted source path requires a matching scan result for the selected thread scope."
        )

    return _source_str(plugin_slug, bool(row["is_theme"]))


def local_source(plugin_slug: str, is_theme: bool) -> str:
    return _source_str(plugin_slug, is_theme)


def source_fallback(
    db_path: Optional[Path],
    plugin_slug: str,
    is_theme: bool,
    last_scan_session_id: Optional[int],
) -> str:
    if last_scan_session_id is not None:
        try:
            return thread_source(
                db_path=db_path,
                plugin_slug=plugin_slug,
                is_theme=is_theme,
                last_scan_session_id=last_scan_session_id,
            )
        except LookupError:
            pass

    return local_source(plugin_slug, is_theme)


def existing_source(
    db_path: Optional[Path],
    plugin_slug: str,
    is_theme: bool,
    last_scan_session_id: Optional[int],
    root_path: Path,
) -> Optional[Path]:
    rel = source_fallback(
        db_path=db_path,
        plugin_slug=plugin_slug,
        is_theme=is_theme,
        last_scan_session_id=last_scan_session_id,
    )
    target = Path(rel)
    if target.is_absolute():
        candidate = target.resolve(strict=False)
    else:
        try:
            candidate = ensure_within_workspace(root_path, target)
        except ValueError as exc:
            raise LookupError("Trusted source path must stay within the workspace roots.") from exc

    if not candidate.exists() or not candidate.is_dir():
        return None

    return candidate


def context_path(source_dir: Optional[Path]) -> str:
    return str(source_dir.resolve()) if source_dir is not None else ""


def context_session(last_scan_session_id: Optional[int]) -> int:
    return int(last_scan_session_id or 0)


def source_state(source_dir: Optional[Path]) -> Dict[str, Any]:
    return {
        "available": source_dir is not None,
        "mode": "source" if source_dir is not None else "metadata_only",
    }


def semgrep_payload(
    semgrep_payload: Dict[str, Any],
    source_dir: Optional[Path],
) -> Dict[str, Any]:
    return {
        **semgrep_payload,
        "source": source_state(source_dir),
    }


def source_context(
    db_path: Optional[Path],
    plugin_slug: str,
    is_theme: bool,
    source_dir: Optional[Path],
    last_scan_session_id: Optional[int],
) -> Dict[str, Any]:
    context = build_plugin_context(
        db_path=db_path,
        plugin_slug=plugin_slug,
        is_theme=is_theme,
        source_path=context_path(source_dir),
        last_scan_session_id=context_session(last_scan_session_id),
    )
    context["source"] = source_state(source_dir)
    context["semgrep"] = semgrep_payload(context.get("semgrep") or _empty_semgrep(), source_dir)
    return context


def build_plugin_context(
    db_path: Optional[Path],
    plugin_slug: str,
    is_theme: bool,
    source_path: str,
    last_scan_session_id: int,
) -> Dict[str, Any]:
    init_db(db_path)

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        row = _plugin_row(cursor, plugin_slug, is_theme, last_scan_session_id)

        if not row:
            return {
                "source_path": source_path,
                "plugin": None,
                "semgrep": _empty_semgrep(),
            }

        plugin = dict(row)
        scan_row = _scan_row(
            cursor, plugin_slug, plugin.get("latest_version")
        )

        summary = {}
        findings = []
        scan_data = None

        if scan_row:
            scan = dict(scan_row)
            summary = json.loads(scan["summary_json"]) if scan.get("summary_json") else {}
            scan_data = {
                "id": scan["id"],
                "slug": scan["slug"],
                "version": scan["version"],
                "status": scan["status"],
                "created_at": scan["created_at"],
                "completed_at": scan["completed_at"],
            }
            cursor.execute(
                """
                SELECT * FROM semgrep_findings
                WHERE scan_id = ?
                ORDER BY id ASC
                """,
                (scan["id"],),
            )
            findings = [dict(item) for item in cursor.fetchall()]

    snapshot = {
        "findings_count": int(plugin.get("semgrep_findings") or 0),
        "latest_version": plugin.get("latest_version"),
        "has_completed_scan": scan_data is not None,
        "summary_total_findings": int(summary.get("total_findings") or 0),
    }

    plugin["metrics"] = {
        "risk_score": int(plugin.get("score") or 0),
        "installations": int(plugin.get("installations") or 0),
        "days_since_update": int(plugin.get("days_since_update") or 0),
        "latest_version": plugin.get("latest_version"),
        "semgrep_findings": int(plugin.get("semgrep_findings") or 0),
    }

    return {
        "source_path": source_path,
        "plugin": plugin,
        "semgrep": {
            "scan": scan_data,
            "summary": summary,
            "findings": findings,
            "snapshot": snapshot,
        },
    }
