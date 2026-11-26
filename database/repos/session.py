import json
from typing import Any, Dict, List, Optional, Set, Tuple

from config import DEFAULT_QUERY_LIMIT, MAX_QUERY_LIMIT
from database.models import get_db
from models import PluginResult, ScanConfig, ScanStatus

SESSION_OVERFETCH_MULTIPLIER = 4
SESSION_OVERFETCH_MINIMUM = 200
SESSION_RESULT_LIMIT = MAX_QUERY_LIMIT * 10 - 1


def _parse_json(raw: Any) -> Any:
    return json.loads(raw) if raw else None


def _parse_csv(raw: Any) -> List[str]:
    return str(raw).split(",") if raw else []


def _serialize_code(result: PluginResult) -> str | None:
    if not result.code_analysis:
        return None
    return json.dumps(
        {
            "dangerous_functions": result.code_analysis.dangerous_functions,
            "ajax_endpoints": result.code_analysis.ajax_endpoints,
            "file_operations": result.code_analysis.file_operations,
            "sql_queries": result.code_analysis.sql_queries,
            "nonce_usage": result.code_analysis.nonce_usage,
            "sanitization_issues": result.code_analysis.sanitization_issues,
        }
    )


def _session_row(row: Dict[str, Any], *, status_override: str | None = None, is_merged: bool = False) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "status": status_override or row["status"],
        "is_merged": is_merged,
        "config": _parse_json(row.get("config_json")),
        "total_found": row["total_found"],
        "high_risk_count": row["high_risk_count"],
        "error_message": row["error_message"],
    }


def _result_row(row: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "version": row["version"],
        "score": row["score"],
        "installations": row["installations"],
        "days_since_update": row["days_since_update"],
        "tested_wp_version": row["tested_wp_version"],
        "author_trusted": bool(row["author_trusted"]),
        "is_risky_category": bool(row["is_risky_category"]),
        "is_user_facing": bool(row["is_user_facing"]),
        "is_duplicate": bool(row["is_duplicate"]) if "is_duplicate" in row.keys() else False,
        "is_theme": bool(row["is_theme"]) if "is_theme" in row.keys() else False,
        "risk_tags": _parse_csv(row["risk_tags"]),
        "security_flags": _parse_csv(row["security_flags"]),
        "feature_flags": _parse_csv(row["feature_flags"]),
        "download_link": row["download_link"],
        "wp_org_link": row["wp_org_link"] if "wp_org_link" in row.keys() else None,
        "cve_search_link": row["cve_search_link"],
        "wpscan_link": row["wpscan_link"],
        "trac_link": row["trac_link"],
    }
    if row["code_analysis_json"]:
        result["code_analysis"] = json.loads(row["code_analysis_json"])
    return result


class SessionMixin:

    _VALID_SORT_COLUMNS = {
        "score": "score",
        "installations": "installations",
        "days_since_update": "days_since_update",
        "name": "name",
        "slug": "slug",
    }
    _VALID_SORT_ORDERS = {"ASC", "DESC"}

    def create_session(self, config: ScanConfig) -> int:
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scan_sessions (config_json, status)
                VALUES (?, ?)
            """,
                (json.dumps(config.to_dict()), ScanStatus.PENDING.value),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def update_session_status(
        self,
        session_id: int,
        status: ScanStatus,
        total_found: Optional[int] = None,
        high_risk_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            updates = ["status = ?"]
            params: List[Any] = [status.value]

            if total_found is not None:
                updates.append("total_found = ?")
                params.append(total_found)
            if high_risk_count is not None:
                updates.append("high_risk_count = ?")
                params.append(high_risk_count)
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            params.append(session_id)
            cursor.execute(
                f"""
                UPDATE scan_sessions
                SET {", ".join(updates)}
                WHERE id = ?
            """,
                params,
            )
            conn.commit()

    def _mark_dup(self, cursor: Any, session_id: int, result: PluginResult) -> None:
        cursor.execute(
            """
            SELECT 1 FROM scan_results
            WHERE slug = ? AND session_id != ?
            LIMIT 1
        """,
            (result.slug, session_id),
        )
        if cursor.fetchone():
            result.is_duplicate = True

    def save_result(self, session_id: int, result: PluginResult) -> int:
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            self._mark_dup(cursor, session_id, result)
            code_analysis_json = _serialize_code(result)

            cursor.execute(
                """
                INSERT INTO scan_results (
                    session_id, slug, name, version, score, installations,
                    days_since_update, tested_wp_version, author_trusted,
                    is_risky_category, is_user_facing, is_duplicate, is_theme, risk_tags, security_flags,
                    feature_flags, download_link, wp_org_link, cve_search_link, wpscan_link, trac_link, code_analysis_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session_id,
                    result.slug,
                    result.name,
                    result.version,
                    result.score,
                    result.installations,
                    result.days_since_update,
                    result.tested_wp_version,
                    1 if result.author_trusted else 0,
                    1 if result.is_risky_category else 0,
                    1 if result.is_user_facing else 0,
                    1 if result.is_duplicate else 0,
                    1 if result.is_theme else 0,
                    ",".join(result.risk_tags),
                    ",".join(result.security_flags),
                    ",".join(result.feature_flags),
                    result.download_link,
                    result.wp_org_link,
                    result.cve_search_link,
                    result.wpscan_link,
                    result.trac_link,
                    code_analysis_json,
                ),
            )
            inserted_id = cursor.lastrowid or 0
            session_created_at = self._session_time(cursor, session_id)
            self._upsert_catalog(cursor, session_id, session_created_at, result)
            conn.commit()
            return inserted_id

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            return _session_row(dict(row)) if row else None

    def _recent_rows(self, cursor: Any, limit: int) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT * FROM scan_sessions
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (max(limit * SESSION_OVERFETCH_MULTIPLIER, SESSION_OVERFETCH_MINIMUM),),
        )
        return [dict(row) for row in cursor.fetchall()]

    def _slugs_by_session(self, cursor: Any, session_ids: List[int]) -> Dict[int, Set[str]]:
        if not session_ids:
            return {}
        marks = ",".join(["?"] * len(session_ids))
        cursor.execute(
            f"""
            SELECT session_id, slug
            FROM scan_results
            WHERE session_id IN ({marks})
        """,
            session_ids,
        )
        map: Dict[int, Set[str]] = {}
        for row in cursor.fetchall():
            sid = int(row["session_id"])
            map.setdefault(sid, set()).add(str(row["slug"]))
        return map

    def _signature_counts(
        self,
        rows: List[Dict[str, Any]],
        slugs_by_session: Dict[int, Set[str]],
    ) -> Dict[Tuple[bool, Tuple[str, ...]], int]:
        counts: Dict[Tuple[bool, Tuple[str, ...]], int] = {}
        for row in rows:
            sid = int(row["id"])
            sig_slugs = tuple(sorted(slugs_by_session.get(sid, set())))
            has_res = bool(sig_slugs)
            if row["status"] not in {ScanStatus.COMPLETED.value, ScanStatus.MERGED.value} or not has_res:
                continue
            sig = (has_res, sig_slugs)
            counts[sig] = counts.get(sig, 0) + 1
        return counts

    def get_all_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            rows = self._recent_rows(cur, limit)
            if not rows:
                return []

            by_sid = self._slugs_by_session(
                cur,
                [int(row["id"]) for row in rows],
            )
            counts = self._signature_counts(rows, by_sid)

            sessions: List[Dict[str, Any]] = []
            seen: Set[Tuple[bool, Tuple[str, ...]]] = set()
            for row in rows:
                sid = int(row["id"])
                sig_slugs = tuple(sorted(by_sid.get(sid, set())))
                has_res = bool(sig_slugs)
                sig = (has_res, sig_slugs)
                done = (
                    row["status"] in {ScanStatus.COMPLETED.value, ScanStatus.MERGED.value}
                    and has_res
                )
                if done:
                    if sig in seen:
                        continue
                    seen.add(sig)

                merged = row["status"] == ScanStatus.MERGED.value or (
                    done and counts.get(sig, 0) > 1
                )
                state = ScanStatus.MERGED.value if merged else row["status"]
                sessions.append(
                    _session_row(
                        row,
                        status_override=state,
                        is_merged=merged,
                    )
                )
                if len(sessions) >= limit:
                    break
            return sessions

    def get_session_results(
        self,
        session_id: int,
        sort_by: str = "score",
        sort_order: str = "desc",
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            col = self._VALID_SORT_COLUMNS.get(sort_by, "score")
            req_dir = str(sort_order or "").upper()
            dir = (
                "DESC"
                if req_dir in self._VALID_SORT_ORDERS and req_dir == "DESC"
                else "ASC"
            )
            lim = max(1, min(int(limit or DEFAULT_QUERY_LIMIT), SESSION_RESULT_LIMIT))
            cur.execute(
                f"""
                SELECT * FROM scan_results
                WHERE session_id = ?
                ORDER BY {col} {dir}
                LIMIT ?
            """,
                (session_id, lim),
            )
            return [_result_row(dict(row)) for row in cur.fetchall()]

    def delete_session(self, session_id: int) -> bool:
        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT catalog_id FROM plugin_catalog_sessions WHERE session_id = ?",
                (session_id,),
            )
            cat_ids = [int(row["catalog_id"]) for row in cur.fetchall()]
            cur.execute("DELETE FROM plugin_catalog_sessions WHERE session_id = ?", (session_id,))
            cur.execute("DELETE FROM scan_results WHERE session_id = ?", (session_id,))
            cur.execute("DELETE FROM scan_sessions WHERE id = ?", (session_id,))
            deleted = cur.rowcount > 0
            for cid in set(cat_ids):
                self._refresh_catalog(cur, cid)
            conn.commit()
            return deleted

    def get_latest_session_by_config(
        self,
        config_dict: Dict[str, Any],
        exclude_id: int,
    ) -> Optional[int]:
        cfg_str = json.dumps(config_dict, sort_keys=True)
        with get_db(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, config_json FROM scan_sessions
                WHERE status IN ('completed', 'merged') AND id != ?
                ORDER BY id DESC LIMIT 20
            """,
                (exclude_id,),
            )
            for row in cur.fetchall():
                try:
                    row_cfg = json.loads(row["config_json"])
                except Exception:
                    continue
                if json.dumps(row_cfg, sort_keys=True) == cfg_str:
                    return int(row["id"])
        return None

    def get_result_slugs(self, session_id: int) -> List[str]:
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT slug FROM scan_results WHERE session_id = ?", (session_id,))
            return [str(row["slug"]) for row in cursor.fetchall()]

    def mark_session_merged(self, session_id: int) -> None:
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE scan_sessions
                SET status = ?, created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (ScanStatus.MERGED.value, session_id),
            )
            conn.commit()
