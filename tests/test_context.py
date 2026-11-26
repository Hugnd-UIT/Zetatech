import json
import sqlite3
from pathlib import Path

from agents.context import (
    build_plugin_context,
    ensure_source,
    thread_source,
)
from agents.repos import AIRepository
from database.models import init_db
from paths import RuntimePaths


def _runtime_paths(runtime_root):
    return RuntimePaths(
        root=runtime_root,
        db_file=runtime_root / "zetatech.db",
        logs_dir=runtime_root / "logs",
        plugins_dir=runtime_root / "plugins",
        semgrep_dir=runtime_root / "semgrep",
        semgrep_outputs_dir=runtime_root / "semgrep-results",
        approvals_dir=runtime_root / "approvals",
    )


def _insert_scan_session(cursor, status, total_found, high_risk_count):
    cursor.execute(
        "INSERT INTO scan_sessions (status, total_found, high_risk_count) VALUES (?, ?, ?)",
        (status, total_found, high_risk_count),
    )
    return cursor.lastrowid


def _insert_plugin_catalog(
    cursor,
    slug,
    session_id,
    version,
    score,
    installations,
    days_since_update,
    semgrep_findings,
):
    cursor.execute(
        """
        INSERT INTO plugin_catalog (
            slug, is_theme, first_seen_session_id, last_seen_session_id,
            first_seen_at, last_seen_at, seen_count, latest_version,
            latest_score, max_score_ever, latest_installations,
            latest_days_since_update, latest_semgrep_findings
        ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            0,
            session_id,
            session_id,
            1,
            version,
            score,
            score,
            installations,
            days_since_update,
            semgrep_findings,
        ),
    )
    return cursor.lastrowid


def _insert_plugin_catalog_session(
    cursor,
    catalog_id,
    session_id,
    score,
    version,
    installations,
    days_since_update,
    semgrep_findings,
):
    cursor.execute(
        """
        INSERT INTO plugin_catalog_sessions (
            catalog_id, session_id, seen_at, score_snapshot, version_snapshot,
            installations_snapshot, days_since_update_snapshot, semgrep_findings_snapshot
        ) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?)
        """,
        (
            catalog_id,
            session_id,
            score,
            version,
            installations,
            days_since_update,
            semgrep_findings,
        ),
    )


def _insert_semgrep_scan(cursor, slug, version, status, summary):
    cursor.execute(
        "INSERT INTO semgrep_scans (slug, version, status, summary_json) VALUES (?, ?, ?, ?)",
        (slug, version, status, json.dumps(summary)),
    )
    return cursor.lastrowid


def _insert_semgrep_finding(
    cursor,
    scan_id,
    rule_id,
    message,
    severity,
    file_path,
    line_number,
    code_snippet,
    metadata,
):
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
            severity,
            file_path,
            line_number,
            code_snippet,
            json.dumps(metadata),
        ),
    )


def test_source_scope(monkeypatch, tmp_path):
    root = tmp_path / ".zetatech"
    monkeypatch.setattr("agents.context.resolve_runtime_paths", lambda: _runtime_paths(root))
    db = tmp_path / "ai_context.db"
    init_db(db)

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()
        sid = _insert_scan_session(cur, "completed", 1, 0)
        cur.execute(
            """
            INSERT INTO scan_results (session_id, slug, version, is_theme)
            VALUES (?, ?, ?, ?)
            """,
            (sid, "hello-dolly", "1.0.0", 0),
        )
        cur.execute(
            """
            INSERT INTO scan_results (session_id, slug, version, is_theme)
            VALUES (?, ?, ?, ?)
            """,
            (sid, "hello-dolly", "2.0.0", 1),
        )
        conn.commit()

    assert sid is not None
    assert thread_source(
        db_path=db,
        plugin_slug="hello-dolly",
        is_theme=False,
        last_scan_session_id=sid,
    ) == str(root / "plugins" / "Plugins" / "hello-dolly" / "source")
    assert thread_source(
        db_path=db,
        plugin_slug="hello-dolly",
        is_theme=True,
        last_scan_session_id=sid,
    ) == str(root / "plugins" / "Themes" / "hello-dolly" / "source")

    assert sid is not None

    miss = sid + 1
    repo = AIRepository(db_path=db)
    p_th = repo.get_or_create_thread(
        plugin_slug="hello-dolly",
        is_theme=False,
        last_scan_session_id=miss,
    )
    t_th = repo.get_or_create_thread(
        plugin_slug="hello-dolly",
        is_theme=True,
        last_scan_session_id=miss,
    )

    assert p_th["id"] != t_th["id"]

    try:
        thread_source(
            db_path=db,
            plugin_slug="hello-dolly",
            is_theme=False,
            last_scan_session_id=miss,
        )
    except LookupError as exc:
        assert str(exc) == "Trusted source path requires a matching scan result for the selected thread scope."
    else:
        raise AssertionError("Expected plugin thread source path lookup to fail for missing scan result")

    try:
        thread_source(
            db_path=db,
            plugin_slug="hello-dolly",
            is_theme=True,
            last_scan_session_id=miss,
        )
    except LookupError as exc:
        assert str(exc) == "Trusted source path requires a matching scan result for the selected thread scope."
    else:
        raise AssertionError("Expected theme thread source path lookup to fail for missing scan result")


def test_plugin_context(
    tmp_path,
):
    db = tmp_path / "ai_context.db"
    init_db(db)

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()

        sid = _insert_scan_session(cur, "completed", 5, 2)
        other_sid = _insert_scan_session(cur, "completed", 1, 0)

        cid = _insert_plugin_catalog(
            cur,
            "target-plugin",
            sid,
            "1.2.3",
            87,
            1000,
            12,
            2,
        )
        other_cid = _insert_plugin_catalog(
            cur,
            "other-plugin",
            other_sid,
            "9.9.9",
            10,
            5,
            90,
            1,
        )

        _insert_plugin_catalog_session(
            cur,
            cid,
            sid,
            87,
            "1.2.3",
            1000,
            12,
            2,
        )
        _insert_plugin_catalog_session(
            cur,
            other_cid,
            other_sid,
            10,
            "9.9.9",
            5,
            90,
            1,
        )

        stale = _insert_semgrep_scan(
            cur,
            "target-plugin",
            "1.0.0",
            "completed",
            {"total_findings": 1, "breakdown": {"WARNING": 1}},
        )
        _insert_semgrep_finding(
            cur,
            stale,
            "stale.rule",
            "Stale issue",
            "WARNING",
            "target-plugin/old.php",
            7,
            "old()",
            {"category": "stale"},
        )

        scan = _insert_semgrep_scan(
            cur,
            "target-plugin",
            "1.2.3",
            "completed",
            {"total_findings": 2, "breakdown": {"ERROR": 1, "WARNING": 1}},
        )
        _insert_semgrep_finding(
            cur,
            scan,
            "security.eval",
            "Use of eval detected",
            "ERROR",
            "target-plugin/includes/danger.php",
            42,
            "eval($payload);",
            {"owasp": "A03"},
        )
        _insert_semgrep_finding(
            cur,
            scan,
            "security.input",
            "Unsanitized input",
            "WARNING",
            "target-plugin/includes/input.php",
            10,
            "$_GET['id']",
            {"source": "querystring"},
        )

        other_scan = _insert_semgrep_scan(
            cur,
            "other-plugin",
            "9.9.9",
            "completed",
            {"total_findings": 1, "breakdown": {"INFO": 1}},
        )
        _insert_semgrep_finding(
            cur,
            other_scan,
            "other.rule",
            "Other plugin issue",
            "INFO",
            "other-plugin/other.php",
            3,
            "$x = 1;",
            {"plugin": "other-plugin"},
        )
        conn.commit()

    assert sid is not None
    ctx = build_plugin_context(
        db_path=db,
        plugin_slug="target-plugin",
        is_theme=False,
        source_path="/tmp/target-plugin",
        last_scan_session_id=sid,
    )

    assert ctx["source_path"] == "/tmp/target-plugin"
    assert ctx["plugin"]["slug"] == "target-plugin"
    assert ctx["plugin"]["is_theme"] == 0
    assert ctx["plugin"]["latest_version"] == "1.2.3"
    assert ctx["plugin"]["last_scan_session_id"] == sid
    assert ctx["plugin"]["score"] == 87
    assert ctx["plugin"]["installations"] == 1000
    assert ctx["plugin"]["days_since_update"] == 12
    assert ctx["plugin"]["semgrep_findings"] == 2
    assert ctx["plugin"]["metrics"] == {
        "risk_score": 87,
        "installations": 1000,
        "days_since_update": 12,
        "latest_version": "1.2.3",
        "semgrep_findings": 2,
    }

    assert ctx["semgrep"]["scan"]["id"] == scan
    assert ctx["semgrep"]["snapshot"] == {
        "findings_count": 2,
        "latest_version": "1.2.3",
        "has_completed_scan": True,
        "summary_total_findings": 2,
    }
    assert ctx["semgrep"]["scan"]["version"] == "1.2.3"
    assert ctx["semgrep"]["summary"] == {
        "total_findings": 2,
        "breakdown": {"ERROR": 1, "WARNING": 1},
    }
    assert [f["rule_id"] for f in ctx["semgrep"]["findings"]] == [
        "security.eval",
        "security.input",
    ]

    raw = json.dumps(ctx)
    assert "other-plugin" not in raw
    assert "Other plugin issue" not in raw
    assert "stale.rule" not in raw


def test_stale_semgrep(
    tmp_path,
):
    db = tmp_path / "ai_context.db"
    init_db(db)

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()

        sid = _insert_scan_session(cur, "completed", 2, 0)
        cid = _insert_plugin_catalog(
            cur,
            "target-plugin",
            sid,
            "2.0.0",
            42,
            500,
            5,
            0,
        )
        _insert_plugin_catalog_session(
            cur,
            cid,
            sid,
            42,
            "2.0.0",
            500,
            5,
            0,
        )

        old = _insert_semgrep_scan(
            cur,
            "target-plugin",
            "1.9.9",
            "completed",
            {"total_findings": 1, "breakdown": {"WARNING": 1}},
        )
        _insert_semgrep_finding(
            cur,
            old,
            "stale.rule",
            "Older version issue",
            "WARNING",
            "target-plugin/legacy.php",
            11,
            "legacy()",
            {"category": "stale"},
        )
        conn.commit()

    assert sid is not None
    ctx = build_plugin_context(
        db_path=db,
        plugin_slug="target-plugin",
        is_theme=False,
        source_path="/tmp/target-plugin",
        last_scan_session_id=sid,
    )

    assert ctx["plugin"]["latest_version"] == "2.0.0"
    assert ctx["plugin"]["metrics"] == {
        "risk_score": 42,
        "installations": 500,
        "days_since_update": 5,
        "latest_version": "2.0.0",
        "semgrep_findings": 0,
    }
    assert ctx["semgrep"] == {
        "scan": None,
        "summary": {},
        "findings": [],
        "snapshot": {
            "findings_count": 0,
            "latest_version": "2.0.0",
            "has_completed_scan": False,
            "summary_total_findings": 0,
        },
    }


def test_source_download(monkeypatch, tmp_path):
    root = tmp_path / ".zetatech"
    monkeypatch.setattr("agents.context.resolve_runtime_paths", lambda: _runtime_paths(root))

    src = root / "plugins" / "Plugins" / "akismet" / "source"
    src.mkdir(parents=True, exist_ok=True)
    (src / "plugin.php").write_text("<?php // ok", encoding="utf-8")

    monkeypatch.setattr(
        "agents.context.existing_source",
        lambda **__: None,
    )
    monkeypatch.setattr(
        "agents.context.download_info",
        lambda **__: {
            "download_url": "https://downloads.wordpress.org/plugin/akismet.latest.zip",
            "version": "1.0.0",
        },
    )

    class _FakeDownloader:
        def __init__(self, base_dir):
            assert Path(base_dir) == root / "plugins"

        def download_and_extract(self, download_url, slug, verbose=False):
            assert download_url == "https://downloads.wordpress.org/plugin/akismet.latest.zip"
            assert slug == "akismet"
            assert verbose is False
            return src

    monkeypatch.setattr("agents.context.PluginDownloader", _FakeDownloader)

    got = ensure_source(
        db_path=tmp_path / "ai_context.db",
        plugin_slug="akismet",
        is_theme=False,
        last_scan_session_id=1,
        root_path=tmp_path / "workspace",
    )

    assert got == src.resolve()


def test_missing_context(tmp_path):
    db = tmp_path / "ai_context.db"
    init_db(db)

    ctx = build_plugin_context(
        db_path=db,
        plugin_slug="missing-plugin",
        is_theme=False,
        source_path="/tmp/missing-plugin",
        last_scan_session_id=999,
    )

    assert ctx == {
        "source_path": "/tmp/missing-plugin",
        "plugin": None,
        "semgrep": {"scan": None, "summary": {}, "findings": []},
    }
