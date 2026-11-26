import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import DEFAULT_QUERY_LIMIT, MAX_CATALOG_SESSION_LIMIT, MAX_QUERY_LIMIT
from database.models import get_db
from models import PluginResult

logger = logging.getLogger("zetatech.database.catalog")


def _csv_field(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value or "")


def _parse_csv_field(value: Any) -> List[str]:
    return str(value).split(",") if value else []


def _to_bool(value: Any) -> bool:
    return bool(value or 0)


class CatalogMixin:

    _VALID_CATALOG_SORT_COLUMNS = {
        "last_seen": "pc.last_seen_at",
        "seen_count": "pc.seen_count",
        "max_score": "pc.max_score_ever",
        "latest_score": "pc.latest_score",
        "installs": "pc.latest_installations",
        "updated_days": "pc.latest_days_since_update",
        "slug": "pc.slug",
    }

    def get_catalog_latest_version(self, slug: str, *, is_theme: bool = False) -> Optional[str]:
        safe = str(slug or "").strip()
        if not safe:
            return None

        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT latest_version
                FROM plugin_catalog
                WHERE slug = ? AND is_theme = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (safe, 1 if is_theme else 0),
            )
            row = cur.fetchone()
            if not row:
                return None
            ver = row["latest_version"]
            return str(ver).strip() or None if ver is not None else None

    def add_favorite(self, result_dict: Dict[str, Any]) -> bool:
        with get_db(self.db_path) as conn:
            cur = conn.cursor()

            rtags = _csv_field(result_dict.get("risk_tags", []))
            sflags = _csv_field(result_dict.get("security_flags", []))
            fflags = _csv_field(result_dict.get("feature_flags", []))

            ca_json = None
            if result_dict.get("code_analysis"):
                ca_json = json.dumps(result_dict.get("code_analysis"))

            try:
                cur.execute(
                    """
                    INSERT INTO favorite_plugins (
                        slug, name, version, score, installations, days_since_update,
                        tested_wp_version, is_theme, download_link, wp_org_link, cve_search_link, wpscan_link,
                        trac_link, author_trusted, is_risky_category, is_user_facing,
                        risk_tags, security_flags, feature_flags, code_analysis_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        result_dict.get("slug"),
                        result_dict.get("name"),
                        result_dict.get("version"),
                        result_dict.get("score"),
                        result_dict.get("installations"),
                        result_dict.get("days_since_update"),
                        result_dict.get("tested_wp_version"),
                        1 if result_dict.get("is_theme") else 0,
                        result_dict.get("download_link"),
                        result_dict.get("wp_org_link"),
                        result_dict.get("cve_search_link"),
                        result_dict.get("wpscan_link"),
                        result_dict.get("trac_link"),
                        1 if result_dict.get("author_trusted") else 0,
                        1 if result_dict.get("is_risky_category") else 0,
                        1 if result_dict.get("is_user_facing") else 0,
                        rtags,
                        sflags,
                        fflags,
                        ca_json,
                    ),
                )
                conn.commit()
                return True
            except Exception as e:
                logger.warning("Error adding favorite", exc_info=e)
                return False

    def remove_favorite(self, slug: str) -> bool:
        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM favorite_plugins WHERE slug = ?", (slug,))
            conn.commit()
            return cur.rowcount > 0

    def get_favorites(self) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM favorite_plugins ORDER BY created_at DESC")
            items = []
            for row in cur.fetchall():
                d = dict(row)
                d["author_trusted"] = _to_bool(d.get("author_trusted"))
                d["is_risky_category"] = _to_bool(d.get("is_risky_category"))
                d["is_user_facing"] = _to_bool(d.get("is_user_facing"))
                d["is_theme"] = _to_bool(d.get("is_theme"))

                d["risk_tags"] = _parse_csv_field(d.get("risk_tags"))
                d["security_flags"] = _parse_csv_field(d.get("security_flags"))
                d["feature_flags"] = _parse_csv_field(d.get("feature_flags"))

                if d.get("code_analysis_json"):
                    d["code_analysis"] = json.loads(d["code_analysis_json"])

                items.append(d)
            return items

    def get_catalog_plugins(
        self,
        q: str = "",
        sort_by: str = "last_seen",
        order: str = "desc",
        limit: int = DEFAULT_QUERY_LIMIT,
        offset: int = 0,
        include_sessions: bool = False,
    ) -> Dict[str, Any]:
        try:
            self.bootstrapper.ensure_catalog_backfill(self.rebuild_plugin_catalog)
        except Exception:
            pass

        col = self._VALID_CATALOG_SORT_COLUMNS.get(
            sort_by, "pc.last_seen_at"
        )
        dir = "DESC" if str(order or "").upper() == "DESC" else "ASC"
        lim = max(1, min(int(limit or DEFAULT_QUERY_LIMIT), MAX_QUERY_LIMIT))
        off = max(0, int(offset or 0))
        term = str(q or "").strip().lower()

        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            where = ""
            params: List[Any] = []
            if term:
                where = "WHERE LOWER(pc.slug) LIKE ?"
                params.append(f"%{term}%")

            cur.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM plugin_catalog pc
                {where}
                """,
                params,
            )
            total = int((cur.fetchone() or {"c": 0})["c"])

            cur.execute(
                f"""
                SELECT
                    pc.id,
                    pc.slug,
                    pc.is_theme,
                    pc.first_seen_session_id,
                    pc.last_seen_session_id,
                    pc.first_seen_at,
                    pc.last_seen_at,
                    pc.seen_count,
                    pc.latest_version,
                    pc.latest_score,
                    pc.max_score_ever,
                    pc.latest_installations,
                    pc.latest_days_since_update,
                    pc.latest_semgrep_findings,
                    pc.created_at,
                    pc.updated_at
                FROM plugin_catalog pc
                {where}
                ORDER BY {col} {dir}
                LIMIT ? OFFSET ?
                """,
                params + [lim, off],
            )

            rows = [dict(r) for r in cur.fetchall()]

            if rows:
                slugs = [
                    str(item.get("slug") or "") for item in rows if item.get("slug")
                ]
                statuses = self.get_semgrep_statuses_for_slugs(slugs)
                for item in rows:
                    sem = statuses.get(str(item.get("slug") or ""))
                    item["semgrep"] = sem
                    if sem:
                        item["latest_semgrep_findings"] = int(
                            sem.get("findings_count") or 0
                        )

            if include_sessions and rows:
                ids = [int(r["id"]) for r in rows]
                marks = ",".join(["?"] * len(ids))
                cur.execute(
                    f"""
                    SELECT catalog_id, session_id, seen_at
                    FROM plugin_catalog_sessions
                    WHERE catalog_id IN ({marks})
                    ORDER BY seen_at DESC
                    """,
                    ids,
                )
                by_cat: Dict[int, List[Dict[str, Any]]] = {}
                for row in cur.fetchall():
                    cid = int(row["catalog_id"])
                    by_cat.setdefault(cid, []).append(
                        {
                            "session_id": row["session_id"],
                            "seen_at": row["seen_at"],
                        }
                    )
                for item in rows:
                    item["sessions"] = by_cat.get(int(item["id"]), [])

            now = datetime.now(timezone.utc)

            def _days_since(ts: Any) -> int:
                if not ts:
                    return 0
                try:
                    norm = str(ts).replace("Z", "+00:00")
                    dt = datetime.fromisoformat(norm)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    delta = now - dt.astimezone(timezone.utc)
                    return max(0, int(delta.total_seconds() // 86400))
                except Exception:
                    return 0

            for item in rows:
                item["is_theme"] = bool(item.get("is_theme"))
                base = item.get("latest_days_since_update")
                if base is None:
                    continue
                try:
                    base_int = max(0, int(base))
                except Exception:
                    base_int = 0

                days = base_int + _days_since(
                    item.get("last_seen_at")
                )
                item["latest_days_since_update_snapshot"] = base_int
                item["latest_days_since_update"] = days

            return {
                "total": total,
                "limit": lim,
                "offset": off,
                "items": rows,
            }

    def rebuild_plugin_catalog(self, reset: bool = False) -> Dict[str, Any]:
        rebuilt = 0
        linked = 0

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            if reset:
                cursor.execute("DELETE FROM plugin_catalog_sessions")
                cursor.execute("DELETE FROM plugin_catalog")

            cursor.execute(
                """
                SELECT
                    sr.session_id,
                    ss.created_at AS session_created_at,
                    sr.slug,
                    sr.name,
                    sr.version,
                    sr.score,
                    sr.installations,
                    sr.days_since_update,
                    sr.tested_wp_version,
                    sr.author_trusted,
                    sr.is_risky_category,
                    sr.is_user_facing,
                    sr.is_theme,
                    sr.risk_tags,
                    sr.security_flags,
                    sr.feature_flags,
                    sr.download_link,
                    sr.wp_org_link,
                    sr.cve_search_link,
                    sr.wpscan_link,
                    sr.trac_link
                FROM scan_results sr
                INNER JOIN scan_sessions ss ON ss.id = sr.session_id
                ORDER BY ss.created_at ASC, sr.id ASC
                """
            )

            for row in cursor.fetchall():
                result = PluginResult(
                    slug=row["slug"] or "",
                    name=row["name"] or "",
                    version=row["version"] or "",
                    score=int(row["score"] or 0),
                    installations=int(row["installations"] or 0),
                    days_since_update=int(row["days_since_update"] or 0),
                    tested_wp_version=row["tested_wp_version"] or "",
                    author_trusted=bool(row["author_trusted"]),
                    is_risky_category=bool(row["is_risky_category"]),
                    is_user_facing=bool(row["is_user_facing"]),
                    is_theme=bool(row["is_theme"]),
                    risk_tags=(row["risk_tags"].split(",") if row["risk_tags"] else []),
                    security_flags=(
                        row["security_flags"].split(",")
                        if row["security_flags"]
                        else []
                    ),
                    feature_flags=(
                        row["feature_flags"].split(",") if row["feature_flags"] else []
                    ),
                    download_link=row["download_link"] or "",
                    wp_org_link=row["wp_org_link"] or "",
                    cve_search_link=row["cve_search_link"] or "",
                    wpscan_link=row["wpscan_link"] or "",
                    trac_link=row["trac_link"] or "",
                )

                prev = conn.total_changes
                self._upsert_catalog_entry(
                    cursor,
                    int(row["session_id"]),
                    row["session_created_at"] or "",
                    result,
                )
                curr = conn.total_changes
                if curr > prev:
                    rebuilt += 1
                    linked += 1

            conn.commit()

        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM plugin_catalog")
            cat_count = int((cur.fetchone() or {"c": 0})["c"])
            cur.execute("SELECT COUNT(*) AS c FROM plugin_catalog_sessions")
            link_count = int((cur.fetchone() or {"c": 0})["c"])

        return {
            "status": "ok",
            "catalog_count": cat_count,
            "link_count": link_count,
            "processed_rows": rebuilt,
            "linked_rows": linked,
        }

    def get_catalog_plugin_sessions(
        self,
        slug: str,
        is_theme: Optional[bool] = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> List[Dict[str, Any]]:
        lim = max(
            1,
            min(int(limit or DEFAULT_QUERY_LIMIT), MAX_CATALOG_SESSION_LIMIT),
        )
        with get_db(self.db_path) as conn:
            cur = conn.cursor()

            where = "WHERE pc.slug = ?"
            params: List[Any] = [slug]
            if is_theme is not None:
                where += " AND pc.is_theme = ?"
                params.append(1 if is_theme else 0)

            cur.execute(
                f"""
                SELECT
                    pcs.session_id,
                    pcs.seen_at,
                    pcs.score_snapshot,
                    pcs.version_snapshot,
                    pcs.installations_snapshot,
                    pcs.days_since_update_snapshot,
                    ss.status,
                    ss.total_found,
                    ss.high_risk_count
                FROM plugin_catalog pc
                INNER JOIN plugin_catalog_sessions pcs ON pcs.catalog_id = pc.id
                INNER JOIN scan_sessions ss ON ss.id = pcs.session_id
                {where}
                ORDER BY pcs.seen_at DESC
                LIMIT ?
                """,
                params + [lim],
            )
            return [dict(row) for row in cur.fetchall()]
