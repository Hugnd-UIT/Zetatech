import json
import sqlite3

from agents.repos import AIRepository
from database.models import init_db


def test_migrate_threads(tmp_path):
    db = tmp_path / "ai_state.db"

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE ai_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_slug TEXT NOT NULL,
                is_theme INTEGER NOT NULL DEFAULT 0,
                title TEXT,
                last_scan_session_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(plugin_slug, is_theme)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE ai_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES ai_threads(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE ai_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES ai_threads(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            "INSERT INTO ai_threads (plugin_slug, is_theme, title) VALUES (?, ?, ?)",
            ("akismet", 0, "Akismet"),
        )
        cur.execute(
            "INSERT INTO ai_messages (thread_id, role, content) VALUES (?, ?, ?)",
            (1, "user", "hello"),
        )
        cur.execute(
            "INSERT INTO ai_runs (thread_id, provider, model, status) VALUES (?, ?, ?, ?)",
            (1, "anthropic", "claude-3-7-sonnet", "completed"),
        )
        conn.commit()

    init_db(db)

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_threads_legacy'"
        )
        assert cur.fetchone() is None
        cur.execute("PRAGMA index_list(ai_threads)")
        assert all(not row[2] for row in cur.fetchall())
        cur.execute("SELECT plugin_slug, is_theme, title FROM ai_threads")
        assert cur.fetchall() == [("akismet", 0, "Akismet")]
        cur.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ai_messages'")
        assert 'ai_threads_legacy' not in (cur.fetchone()[0] or "")
        cur.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ai_runs'")
        assert 'ai_threads_legacy' not in (cur.fetchone()[0] or "")
        cur.execute("SELECT thread_id, role, content FROM ai_messages")
        assert cur.fetchall() == [(1, "user", "hello")]
        cur.execute("SELECT thread_id, provider, model, status FROM ai_runs")
        assert cur.fetchall() == [(1, "anthropic", "claude-3-7-sonnet", "completed")]


def test_rebuild_events(tmp_path):
    db = tmp_path / "ai_state.db"

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE ai_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE ai_run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                agent_name TEXT,
                task_id TEXT,
                payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES ai_runs_legacy(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE ai_run_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                assignee TEXT,
                depends_on_json TEXT,
                result_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_id, task_id),
                FOREIGN KEY (run_id) REFERENCES ai_runs_legacy(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            "INSERT INTO ai_runs (id, thread_id, provider, model, status) VALUES (?, ?, ?, ?, ?)",
            (1, 1, "anthropic", "claude-3-7-sonnet", "completed"),
        )
        cur.execute(
            "INSERT INTO ai_run_events (run_id, event_type) VALUES (?, ?)",
            (1, "agent_started"),
        )
        cur.execute(
            "INSERT INTO ai_run_tasks (run_id, task_id, title, status) VALUES (?, ?, ?, ?)",
            (1, "task-1", "Inspect plugin", "completed"),
        )
        conn.commit()

    init_db(db)

    with sqlite3.connect(db) as conn:
        cur = conn.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ai_run_events'")
        assert 'ai_runs_legacy' not in (cur.fetchone()[0] or "")
        cur.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ai_run_tasks'")
        assert 'ai_runs_legacy' not in (cur.fetchone()[0] or "")
        cur.execute("SELECT run_id, event_type FROM ai_run_events")
        assert cur.fetchall() == [(1, "agent_started")]
        cur.execute("SELECT run_id, task_id, title, status FROM ai_run_tasks")
        assert cur.fetchall() == [(1, "task-1", "Inspect plugin", "completed")]


def test_pending_approval(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")

    thread = repo.create_thread(plugin_slug="akismet", is_theme=False)
    run = repo.create_run(
        thread_id=int(thread["id"]),
        provider="anthropic",
        model="claude-3-7-sonnet",
        status="running",
    )

    repo.upsert_run_approval(
        run_id=int(run["id"]),
        thread_id=int(thread["id"]),
        status="pending",
        mode="manual",
        request_payload={"nextTasks": [{"id": "task-1", "title": "Inspect files"}]},
    )

    assert repo.get_thread_pending_approval(int(thread["id"])) is not None

    repo.finish_run(int(run["id"]), "completed")

    assert repo.get_thread_pending_approval(int(thread["id"])) is None


def test_deactivate_provider(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")

    repo.upsert_provider_settings(
        provider="claude",
        api_key="claude-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )

    repo.upsert_provider_settings(
        provider="openai",
        api_key="openai-key",
        model="gpt-4.1",
        base_url="https://api.openai.com",
        is_active=True,
    )

    act = repo.get_active_provider()
    old = repo.get_provider_by_profile_key("claude-claude-3-7-sonnet")

    assert act is not None
    assert act["provider"] == "openai"
    assert act["is_active"] == 1
    assert old["is_active"] == 0
    assert old["api_key"] == "claude-key"


def test_preserve_provider(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")

    repo.upsert_provider_settings(
        provider="claude",
        api_key="test-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )

    upd = repo.upsert_provider_settings(
        provider="claude",
        profile_key="claude-claude-3-7-sonnet",
        is_active=False,
    )

    assert upd["provider"] == "claude"
    assert upd["api_key"] == "test-key"
    assert upd["model"] == "claude-3-7-sonnet"
    assert upd["base_url"] == "https://api.anthropic.com"
    assert upd["is_active"] == 0
    assert upd["profile_key"] == "claude-claude-3-7-sonnet"


def test_no_aliases(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")

    aliases = [
        "upsert_thread",
        "list_scope_threads",
        "create_scope_thread",
        "get_scope_thread",
        "get_latest_scope_thread",
        "get_thread_messages",
        "list_messages_for_thread",
        "get_thread_record",
        "get_run_record",
        "get_provider_record",
        "get_message_record",
        "get_scoped_thread",
        "set_thread_scan_session",
        "set_thread_name",
        "add_tool_audit",
        "mark_run_completed",
        "mark_run_failed",
        "create_or_get_thread",
        "get_active_provider_settings",
        "get_sanitized_active_provider_settings",
        "get_sanitized_active_provider",
        "list_tool_activity",
        "get_tool_activity",
        "create_structured_tool_audit",
        "set_run_failed_with_message",
        "mark_provider_active",
        "get_thread_runs",
        "create_run_for_message",
        "complete_run",
        "get_sanitized_settings",
        "sanitize_settings_response",
        "create_run_record",
        "complete_run_record",
        "get_masked_active_provider",
        "provider_label_for",
        "set_active_provider",
        "set_run_error_message",
        "set_run_workspace",
        "set_run_message",
        "get_thread_events",
        "list_thread_events",
        "create_assistant_message",
        "create_user_message",
        "create_failed_assistant_message",
        "get_provider_label",
        "get_active_provider_name",
        "get_active_provider_model",
        "get_active_provider_base_url",
        "get_active_provider_api_key",
        "get_active_provider_label",
        "get_active_provider_tuple",
        "get_active_provider_id",
        "set_provider_settings",
        "get_provider_settings",
        "get_sanitized_provider_settings",
        "set_run_status",
        "get_thread_by_scope",
        "fail_run",
        "set_thread_updated",
        "create_message_with_audit",
        "get_thread_last_scan",
        "get_thread_metadata",
        "mask_settings",
        "get_run_workspace",
        "get_scoped_thread_id",
        "list_all_provider_settings",
        "set_run_completed",
        "get_thread_id_by_scope",
        "has_active_provider",
        "thread_exists",
        "provider_exists",
        "run_exists",
        "message_exists",
        "count_messages",
        "count_runs",
        "count_providers",
        "get_run_provider_label",
        "get_run_message_id",
        "get_run_error",
        "get_thread_plugin_slug",
        "get_thread_title",
        "get_last_scan_session_id",
        "get_masked_api_key",
        "list_thread_message_ids",
        "list_thread_roles",
        "list_thread_contents",
        "get_sanitized_provider",
        "count_tool_calls",
        "count_tool_results",
        "get_run_provider",
        "get_thread_is_theme",
        "list_all_threads",
        "list_all_runs",
        "list_all_messages",
        "get_thread_count",
        "get_provider_count",
        "get_message_count",
        "get_run_count",
        "get_tool_activity_count",
        "get_any_provider",
        "get_any_thread",
        "get_any_run",
        "get_any_message",
        "get_thread_lookup_key",
        "get_thread_summary",
        "get_run_summary",
        "get_message_summary",
        "get_provider_summary",
        "get_thread_scope_key",
        "get_thread_last_updated",
        "get_provider_updated_at",
        "get_run_completed_at",
        "get_message_created_at",
        "has_messages",
        "has_runs",
        "has_tool_activity",
        "has_title",
        "has_last_scan",
        "has_workspace_path",
        "has_error_message",
        "is_provider_active",
        "is_message_assistant",
        "is_message_user",
        "is_run_completed",
        "is_run_failed",
        "is_provider_configured",
        "get_thread_scope_tuple",
        "get_run_tuple",
        "get_message_tuple",
        "get_tool_audit_tuple",
        "provider_requires_key",
        "get_provider_api_key_suffix",
        "list_thread_ids",
        "list_provider_names",
        "list_run_ids",
        "list_message_ids",
        "get_provider_id",
        "get_run_id",
        "get_message_id",
    ]

    assert all(not hasattr(repo, name) for name in aliases)


def test_persist_repo(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")

    repo.upsert_provider_settings(
        provider="anthropic",
        api_key="test-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )

    act = repo.get_active_provider()
    assert act is not None
    assert act["provider"] == "anthropic"
    assert act["provider_label"] == "Anthropic"
    assert act["api_key"] == "test-key"
    assert act["model"] == "claude-3-7-sonnet"
    assert act["base_url"] == "https://api.anthropic.com"
    assert act["is_active"] == 1

    t1 = repo.get_or_create_thread(
        plugin_slug="akismet",
        is_theme=False,
        title="Akismet",
        last_scan_session_id=33,
    )
    same = repo.get_or_create_thread(
        plugin_slug="akismet",
        is_theme=False,
        title="Akismet updated",
        last_scan_session_id=34,
    )
    t2 = repo.create_thread(
        plugin_slug="akismet",
        is_theme=False,
        title="Akismet follow-up",
        last_scan_session_id=35,
    )
    th = repo.get_or_create_thread(
        plugin_slug="akismet",
        is_theme=True,
        title="Akismet Theme",
    )
    got = repo.get_thread(t1["id"])
    rows = repo.list_threads_for_scope("akismet", False)

    assert same["id"] == t1["id"]
    assert t2["id"] != t1["id"]
    assert th["id"] != t1["id"]
    assert got is not None
    assert got["plugin_slug"] == "akismet"
    assert got["is_theme"] == 0
    assert got["title"] == "Akismet"
    assert got["last_scan_session_id"] == 33
    assert [item["id"] for item in rows] == [t2["id"], t1["id"]]
    assert rows[0]["title"] == "Akismet follow-up Chat 2"
    last = repo.get_latest_thread_for_scope("akismet", False)
    s2 = repo.get_thread_for_scope(t2["id"], "akismet", False)
    assert last is not None
    assert s2 is not None
    assert last["id"] == t2["id"]
    assert s2["id"] == t2["id"]
    assert repo.get_thread_for_scope(t2["id"], "akismet", True) is None

    m1 = repo.create_message(
        thread_id=t1["id"],
        role="user",
        content="Summarize this plugin.",
        tool_calls=[{"name": "read", "path": "source/plugin.php"}],
    )
    m2 = repo.create_message(
        thread_id=t1["id"],
        role="assistant",
        content="This plugin provides spam filtering.",
        tool_results=[{"name": "read", "status": "ok"}],
    )

    msgs = repo.list_messages(t1["id"])
    assert [msg["id"] for msg in msgs] == [m1["id"], m2["id"]]
    assert [msg["role"] for msg in msgs] == ["user", "assistant"]
    assert json.loads(msgs[0]["tool_calls_json"]) == [{"name": "read", "path": "source/plugin.php"}]
    assert json.loads(msgs[1]["tool_results_json"]) == [{"name": "read", "status": "ok"}]
    assert msgs[1]["content"] == "This plugin provides spam filtering."

    run = repo.create_run(
        thread_id=t1["id"],
        provider="anthropic",
        provider_label="Anthropic",
        model="claude-3-7-sonnet",
        status="pending",
        message_id=m1["id"],
        workspace_path="/tmp/workspace/source",
    )
    assert run["status"] == "pending"
    assert run["provider_label"] == "Anthropic"
    assert run["message_id"] == m1["id"]
    assert run["workspace_path"] == "/tmp/workspace/source"

    repo.finish_run(run_id=run["id"], status="completed")
    done = repo.get_run(run["id"])

    assert done is not None
    assert done["thread_id"] == t1["id"]
    assert done["provider"] == "anthropic"
    assert done["provider_label"] == "Anthropic"
    assert done["model"] == "claude-3-7-sonnet"
    assert done["status"] == "completed"
    assert done["message_id"] == m1["id"]
    assert done["workspace_path"] == "/tmp/workspace/source"
    assert done["completed_at"] is not None


def test_thread_memory(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    repo.update_thread_memory(
        thread["id"],
        conversation_summary="User greeted and then requested analysis.",
        analysis_summary="The plugin registers one main entry file.",
        important_files=["plugin.php", "includes/admin.php"],
        findings_summary="No confirmed vulnerability yet.",
        architecture_notes="Main bootstrap is plugin.php.",
        last_source_path="/tmp/workspace/source",
    )

    mem = repo.get_thread_memory(thread["id"])
    row = repo.get_thread(thread["id"])

    assert mem["conversation_summary"] == "User greeted and then requested analysis."
    assert mem["analysis_summary"] == "The plugin registers one main entry file."
    assert mem["important_files"] == ["plugin.php", "includes/admin.php"]
    assert mem["findings_summary"] == "No confirmed vulnerability yet."
    assert mem["architecture_notes"] == "Main bootstrap is plugin.php."
    assert mem["last_source_path"] == "/tmp/workspace/source"
    assert row["important_files"] == ["plugin.php", "includes/admin.php"]


def test_fail_run(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    msg = repo.create_message(thread_id=thread["id"], role="user", content="Analyze")
    run = repo.create_run(
        thread_id=thread["id"],
        provider="anthropic",
        provider_label="Anthropic",
        model="claude-3-7-sonnet",
        status="running",
        message_id=msg["id"],
        workspace_path="/tmp/workspace/source",
    )

    out = repo.fail_run_with_assistant_message(
        run_id=run["id"],
        thread_id=thread["id"],
        content="AI agent bridge failed.",
        error_message="AI agent bridge failed.",
        tool_calls=[{"name": "read", "path": "source/plugin.php"}],
        tool_results=[{"name": "read", "status": "failed"}],
    )

    assert out["role"] == "assistant"
    assert json.loads(out["tool_calls_json"]) == [{"name": "read", "path": "source/plugin.php"}]
    assert json.loads(out["tool_results_json"]) == [{"name": "read", "status": "failed"}]

    failed = repo.get_run(run["id"])
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_message"] == "AI agent bridge failed."
    assert repo.list_thread_tool_audit(thread["id"]) == [
        {"name": "read", "path": "source/plugin.php"},
        {"name": "read", "status": "failed"},
    ]


def test_run_events(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    msg = repo.create_message(thread_id=thread["id"], role="user", content="Analyze")
    run = repo.create_run(
        thread_id=thread["id"],
        provider="anthropic",
        provider_label="Anthropic",
        model="claude-3-7-sonnet",
        status="running",
        message_id=msg["id"],
        workspace_path="/tmp/workspace/source",
    )

    evt = repo.create_run_event(
        run_id=run["id"],
        event_type="agent_started",
        agent_name="plugin_analyst",
        task_id="task-1",
        payload={"name": "plugin_analyst", "taskId": "task-1"},
    )
    task = repo.upsert_run_task(
        run_id=run["id"],
        task_id="task-1",
        title="Inspect plugin",
        status="completed",
        assignee="plugin_analyst",
        depends_on=["task-0"],
        result_text="done",
    )

    assert evt["event_type"] == "agent_started"
    assert evt["payload"] == {"name": "plugin_analyst", "taskId": "task-1"}
    assert repo.list_run_events(run["id"])[0]["agent_name"] == "plugin_analyst"

    assert task["task_id"] == "task-1"
    assert task["depends_on"] == ["task-0"]
    assert repo.list_run_tasks(run["id"])[0]["status"] == "completed"


def test_mask_key(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")
    repo.upsert_provider_settings(
        provider="anthropic",
        api_key="sk-ant-api-key-1234",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )

    cfg = repo.get_active_provider()
    assert cfg is not None
    clean = repo.sanitize_provider_settings(cfg)

    assert clean is not None
    assert clean["api_key"] is None
    assert clean["api_key_masked"] == "••••1234"
    assert cfg["api_key"] == "sk-ant-api-key-1234"


def test_scope_threads(tmp_path):
    repo = AIRepository(db_path=tmp_path / "ai_state.db")

    p1 = repo.get_or_create_thread(
        plugin_slug="hello-dolly",
        is_theme=False,
        title="Plugin Thread",
        last_scan_session_id=11,
    )
    p2 = repo.create_thread(
        plugin_slug="hello-dolly",
        is_theme=False,
        title="Plugin Thread",
        last_scan_session_id=13,
    )
    th = repo.get_or_create_thread(
        plugin_slug="hello-dolly",
        is_theme=True,
        title="Theme Thread",
        last_scan_session_id=12,
    )

    got_th = repo.get_thread_for_scope(th["id"], "hello-dolly", True)
    got_p1 = repo.get_thread_for_scope(p1["id"], "hello-dolly", False)

    assert p1["id"] != th["id"]
    assert p1["is_theme"] == 0
    assert th["is_theme"] == 1
    assert got_th is not None
    assert got_th["id"] == th["id"]
    assert [t["id"] for t in repo.list_threads_for_scope("hello-dolly", False)] == [p2["id"], p1["id"]]
    assert repo.has_thread_scope("hello-dolly", False) is True
    assert repo.has_thread_scope("missing", False) is False
    assert got_p1 is not None
    assert got_p1["id"] == p1["id"]
    got_p2 = repo.get_thread_for_scope(p2["id"], "hello-dolly", False)
    assert got_p2 is not None
    assert got_p2["id"] == p2["id"]
    assert repo.get_thread_for_scope(p1["id"], "hello-dolly", True) is None
