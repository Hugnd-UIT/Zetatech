import json
import sqlite3

from database.models import init_db
from database.repos import ScanRepository


def _insert_semgrep_scan(cursor, slug, version, status, summary):
    cursor.execute(
        "INSERT INTO semgrep_scans (slug, version, status, summary_json) VALUES (?, ?, ?, ?)",
        (slug, version, status, json.dumps(summary)),
    )
    return cursor.lastrowid


def _insert_semgrep_finding(cursor, scan_id, rule_id, message):
    cursor.execute(
        """
        INSERT INTO semgrep_findings (
            scan_id, rule_id, message, severity, file_path, line_number, code_snippet, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_id,
            rule_id,
            message,
            "ERROR",
            "plugin/file.php",
            12,
            "dangerous_call();",
            json.dumps({}),
        ),
    )


def test_latest_semgrep(tmp_path):
    db = tmp_path / "semgrep_repo.db"
    init_db(db)
    repo = ScanRepository(db_path=db)

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()
        old = _insert_semgrep_scan(
            cur,
            "hello-dolly",
            "1.0.0",
            "completed",
            {"total_findings": 0, "breakdown": {}},
        )
        new = _insert_semgrep_scan(
            cur,
            "hello-dolly",
            "1.0.1",
            "completed",
            {"total_findings": 1, "breakdown": {"ERROR": 1}},
        )
        _insert_semgrep_finding(cur, new, "wp.audit.test", "Latest finding")
        conn.commit()

    res = repo.get_semgrep_scan("hello-dolly")

    assert res is not None
    assert res["id"] == new
    assert res["version"] == "1.0.1"
    assert res["summary"] == {"total_findings": 1, "breakdown": {"ERROR": 1}}
    assert [f["rule_id"] for f in res["findings"]] == ["wp.audit.test"]
    assert old != new
