import json
import sqlite3

from fastapi.testclient import TestClient

from agents.repos import AIRepository
from database.models import init_db
from paths import RuntimePaths
from core.app import create_app


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


def _runtime_plugin_source(runtime_root, slug, *, is_theme=False):
    root_dir = "Themes" if is_theme else "Plugins"
    source_dir = runtime_root / "plugins" / root_dir / slug / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "plugin.php").write_text("<?php // plugin", encoding="utf-8")
    return source_dir


def _patch_runtime_paths(monkeypatch, runtime_root):
    runtime_paths = _runtime_paths(runtime_root)
    monkeypatch.setattr("downloaders.plugin.resolve_runtime_paths", lambda: runtime_paths)
    monkeypatch.setattr("downloaders.theme.resolve_runtime_paths", lambda: runtime_paths)
    monkeypatch.setattr("agents.context.resolve_runtime_paths", lambda: runtime_paths)
    monkeypatch.setattr("core.routers.agents.resolve_runtime_paths", lambda: runtime_paths)
    monkeypatch.setattr("core.routers.agents.runtime.resolve_runtime_paths", lambda: runtime_paths)
    monkeypatch.setattr("core.routers.agents.serialize.resolve_runtime_paths", lambda: runtime_paths)
    return runtime_paths


def _insert_scan_result(db_path, session_id, slug, is_theme=False, version="1.0.0"):
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO scan_sessions (id, status, total_found, high_risk_count) VALUES (?, 'completed', 1, 0)",
            (session_id,),
        )
        cursor.execute(
            "INSERT INTO scan_results (session_id, slug, version, is_theme) VALUES (?, ?, ?, ?)",
            (session_id, slug, version, int(is_theme)),
        )
        conn.commit()


def _prepare_thread_source(tmp_path, slug, *, is_theme=False):
    runtime_root = tmp_path / ".zetatech"
    return _runtime_plugin_source(runtime_root, slug, is_theme=is_theme)


def _prepare_trusted_source(monkeypatch, tmp_path, db_path, slug, session_id, *, is_theme=False):
    runtime_root = tmp_path / ".zetatech"
    _patch_runtime_paths(monkeypatch, runtime_root)
    _insert_scan_result(db_path, session_id, slug, is_theme=is_theme)
    return _runtime_plugin_source(runtime_root, slug, is_theme=is_theme)


def _create_test_client(monkeypatch, db_path):
    monkeypatch.setenv("ZETATECH_DB", str(db_path))
    monkeypatch.setattr("core.app.ensure_db_dir", lambda path=None: db_path)
    monkeypatch.setattr(
        "core.app.release.manager.get_status",
        lambda force=False: {"status": "ok"},
    )
    return TestClient(create_app(), base_url="http://localhost")


def test_intent_routes(tmp_path):
    from core.routers.agents.intent import classify_message_intent

    repo = AIRepository(db_path=tmp_path / "ai_router.db")
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    chat = classify_message_intent(content="hello", repo=repo, thread_id=thread["id"])
    assert chat["needs_tools"] is True
    assert chat["needs_workspace_access"] is True

    work = classify_message_intent(content="scan this plugin source code for security issues", repo=repo, thread_id=thread["id"])
    assert work["needs_tools"] is True
    assert work["needs_workspace_access"] is True
    assert work["execution_mode"] == "raw_open_multi_agent"


def test_intent_shape(tmp_path):
    from core.routers.agents.intent import resolve_message_intent

    repo = AIRepository(db_path=tmp_path / "ai_router.db")
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    res = resolve_message_intent(
        content="read the source and summarize the main attack surface",
        repo=repo,
        thread_id=thread["id"],
        thread=thread,
        context_summary="",
        active_provider={"provider": "anthropic", "api_key": "k", "model": "m"},
    )

    assert res["execution_mode"] == "raw_open_multi_agent"
    assert res["team_mode"] == "single_agent"
    assert res["normalized_decision"]["composition_source"] == "raw_open_multi_agent"


def test_thread_summary(tmp_path):
    from core.routers.agents.intent import recent_context

    repo = AIRepository(db_path=tmp_path / "ai_router.db")
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    repo.create_message(thread_id=thread["id"], role="user", content="First message")
    repo.create_message(thread_id=thread["id"], role="assistant", content="First reply")

    out = recent_context(repo, thread["id"])

    assert "- user: First message" in out
    assert "- assistant: First reply" in out


def test_pending_runs(monkeypatch, tmp_path):
    db_path = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db_path)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    msg = repo.create_message(thread_id=thread["id"], role="user", content="Run a full scan")
    repo.create_run(
        thread_id=thread["id"],
        provider="anthropic",
        provider_label="Anthropic",
        model="claude",
        status="running",
        message_id=msg["id"],
        workspace_path=str(tmp_path),
    )

    client = _create_test_client(monkeypatch, db_path)
    res = client.get(
        f"/api/ai/threads/{thread['id']}/messages",
        params={"plugin_slug": "akismet", "is_theme": False},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["has_pending_run"] is True
    assert data["messages"][0]["role"] == "user"


def test_stale_approval(monkeypatch, tmp_path):
    db_path = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db_path)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    run = repo.create_run(
        thread_id=thread["id"],
        provider="anthropic",
        provider_label="Anthropic",
        model="claude",
        status="running",
        workspace_path=str(tmp_path),
    )
    repo.upsert_run_approval(
        run_id=run["id"],
        thread_id=thread["id"],
        status="pending",
        mode="manual",
        request_payload={"nextTasks": [{"id": "task-1", "title": "Inspect workspace"}]},
    )
    repo.finish_run(run["id"], "completed")

    client = _create_test_client(monkeypatch, db_path)
    res = client.get(
        f"/api/ai/threads/{thread['id']}/messages",
        params={"plugin_slug": "akismet", "is_theme": False},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["has_pending_run"] is False
    assert data["pending_approval"] is None


def test_short_prompt(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="anthropic",
        api_key="test-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    _patch_runtime_paths(monkeypatch, tmp_path / ".zetatech")

    prep_calls = []
    payloads = []

    def _prep(**kwargs):
        prep_calls.append(kwargs)
        return tmp_path, tmp_path, str(tmp_path)

    def _bridge(payload):
        payloads.append(payload)
        return {"output": "Hello!", "events": [], "result": {"content": "Hello!", "agents": [], "tasks": []}}

    monkeypatch.setattr("core.routers.agents.service.prep_context", _prep)
    monkeypatch.setattr("core.routers.agents.run_agent_bridge", _bridge)
    monkeypatch.setattr(
        "core.routers.agents.source_context",
        lambda **kwargs: {"plugin": {"slug": "akismet"}, "source": {"available": True, "mode": "source"}},
    )

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        "/api/ai/messages",
        json={"thread_id": thread["id"], "content": "hello"},
    )

    assert res.status_code == 200
    assert len(prep_calls) == 1
    assert payloads[0]["executionMode"] == "raw_open_multi_agent"
    assert payloads[0]["teamMode"] == "single_agent"
    assert payloads[0]["needsTools"] is True


def test_workspace_payload(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="anthropic",
        api_key="test-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    _prepare_trusted_source(monkeypatch, tmp_path, db, "akismet", 1, is_theme=False)

    got = {}
    monkeypatch.setattr(
        "core.routers.agents.source_context",
        lambda **kwargs: {
            "source_path": str(kwargs["source_dir"]),
            "plugin": {"slug": "akismet"},
            "semgrep": {"scan": None, "summary": {}, "findings": []},
            "source": {"available": True, "mode": "source"},
        },
    )
    monkeypatch.setattr(
        "core.routers.agents.run_agent_bridge",
        lambda payload: got.update(payload) or {"output": "Assistant summary", "events": [], "result": {"content": "Assistant summary", "agents": [], "tasks": []}},
    )

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        "/api/ai/messages",
        json={
            "thread_id": thread["id"],
            "content": "scan this plugin for security issues",
            "last_scan_session_id": 1,
        },
    )

    assert res.status_code == 200
    assert got["executionMode"] == "raw_open_multi_agent"
    assert got["teamMode"] == "single_agent"
    assert got["workspaceRoot"].endswith("/plugins/Plugins/akismet/source")
    assert got["needsTools"] is True
    assert got["runtimeEnv"]["ZETATECH_AI_API_KEY"] == "test-key"
    assert 'Zetatech' in got["systemPrompt"]


def test_assistant_output(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="anthropic",
        api_key="test-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    _prepare_trusted_source(monkeypatch, tmp_path, db, "akismet", 1, is_theme=False)

    monkeypatch.setattr(
        "core.routers.agents.source_context",
        lambda **kwargs: {"source": {"available": True}, "plugin": {"slug": "akismet"}, "source_path": str(kwargs["source_dir"])},
    )

    def _bridge(payload):
        return {
            "output": "Assistant summary",
            "events": [
                {"type": "decision_trace", "data": {"execution_mode": "raw_open_multi_agent"}},
                {"type": "tool_call", "data": {"name": "read", "path": "plugin.php"}},
                {"type": "tool_result", "data": {"name": "read", "status": "ok"}},
            ],
            "result": {
                "content": "Assistant summary",
                "agents": [{"name": "source_agent", "role": "source_code_assistant", "success": True, "output": "Assistant summary"}],
                "tasks": [{"id": "direct-source-conversation", "title": "Direct source conversation", "status": "completed", "assignee": "source_agent", "result": "Assistant summary"}],
            },
        }

    monkeypatch.setattr("core.routers.agents.run_agent_bridge", _bridge)

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        "/api/ai/messages",
        json={
            "thread_id": thread["id"],
            "content": "scan this plugin for security issues",
            "last_scan_session_id": 1,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["assistant_message"]["content"] == "Assistant summary"
    assert data["events"] == [
        {"type": "tool_call", "data": {"name": "read", "path": "plugin.php"}},
        {"type": "tool_result", "data": {"name": "read", "status": "ok"}},
    ]
    assert data["agents"][0]["name"] == "source_agent"
    assert data["tasks"][0]["id"] == "direct-source-conversation"


def test_metadata_mode(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="anthropic",
        api_key="test-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    _insert_scan_result(db, 1, "akismet", is_theme=False)
    _patch_runtime_paths(monkeypatch, tmp_path / ".zetatech")
    monkeypatch.setattr(
        "core.routers.agents.run_agent_bridge",
        lambda payload: {"output": "Assistant summary", "events": [], "result": {"content": "Assistant summary"}},
    )

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        "/api/ai/messages",
        json={
            "thread_id": thread["id"],
            "content": "scan this plugin",
            "last_scan_session_id": 1,
        },
    )

    assert res.status_code == 200
    assert "No trusted local source directory was available" in res.json()["assistant_message"]["content"]


def test_runtime_overrides(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="openai",
        api_key="test-key",
        model="gpt-4.1-mini",
        base_url="http://localhost:11434/v1",
        is_active=True,
    )
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    _prepare_trusted_source(monkeypatch, tmp_path, db, "akismet", 1, is_theme=False)

    got = {}
    monkeypatch.setattr(
        "core.routers.agents.source_context",
        lambda **kwargs: {"source": {"available": True}, "plugin": {"slug": "akismet"}, "source_path": str(kwargs["source_dir"])},
    )
    monkeypatch.setattr(
        "core.routers.agents.run_agent_bridge",
        lambda payload: got.update(payload) or {"output": "Assistant summary", "events": [], "result": {"content": "Assistant summary", "agents": [], "tasks": []}},
    )

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        "/api/ai/messages",
        json={
            "thread_id": thread["id"],
            "content": "inspect this plugin with a task pipeline",
            "last_scan_session_id": 1,
            "strategy": "tasks",
            "trace_enabled": False,
            "output_schema": {"type": "object", "properties": {"summary": {"type": "string"}}},
            "tasks": [{"title": "Inspect source", "description": "Read key files", "assignee": "researcher", "maxRetries": 2}],
            "fanout": {"analysts": [{"name": "optimist", "role": "optimist"}]},
            "loop_detection": {"maxRepetitions": 3, "loopDetectionWindow": 5, "onLoopDetected": "warn"},
            "approval_mode": "auto_approve",
            "before_run": {"promptPrefix": "Use strict evidence."},
            "after_run": {"outputSuffix": "End of reviewed output."},
        },
    )

    assert res.status_code == 200
    assert got["strategy"] == "tasks"
    assert got["teamMode"] == "tasks"
    assert got["traceEnabled"] is False
    assert got["outputSchema"]["properties"]["summary"]["type"] == "string"
    assert got["tasks"][0]["maxRetries"] == 2
    assert got["fanout"]["analysts"][0]["name"] == "optimist"
    assert got["loopDetection"]["onLoopDetected"] == "warn"
    assert got["approvalMode"] == "auto_approve"
    assert got["beforeRun"]["promptPrefix"] == "Use strict evidence."
    assert got["afterRun"]["outputSuffix"] == "End of reviewed output."


def test_stream_events(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="anthropic",
        api_key="test-key",
        model="claude-3-7-sonnet",
        base_url="https://api.anthropic.com",
        is_active=True,
    )
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    _prepare_trusted_source(monkeypatch, tmp_path, db, "akismet", 1, is_theme=False)

    monkeypatch.setattr(
        "core.routers.agents.source_context",
        lambda **kwargs: {"source": {"available": True}, "plugin": {"slug": "akismet"}, "source_path": str(kwargs["source_dir"])},
    )

    def _stream(payload):
        yield {"type": "decision_trace", "data": {"execution_mode": "raw_open_multi_agent"}}
        yield {"type": "tool_call", "data": {"name": "read", "path": "plugin.php"}}
        yield {"type": "run_completed", "data": {"content": "Streamed assistant summary", "agents": [], "tasks": []}}

    monkeypatch.setattr("core.routers.agents.stream_bridge", _stream)

    client = _create_test_client(monkeypatch, db)
    with client.stream(
        "POST",
        "/api/ai/messages/stream",
        json={"thread_id": thread["id"], "content": "scan this plugin", "last_scan_session_id": 1},
    ) as res:
        assert res.status_code == 200
        chunks = [json.loads(line) for line in res.iter_lines() if line]

    types = [chunk["type"] for chunk in chunks]
    assert "runtime_event" in types
    assert "bridge_event" in types
    assert "final" in types
    final = next(chunk for chunk in chunks if chunk["type"] == "final")
    assert final["data"]["assistant_message"]["content"] == "Streamed assistant summary"


def test_settings_dashboard(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="anthropic",
        profile_key="anthropic-main",
        display_name="Anthropic Main",
        api_key="test-key",
        model="claude-3-7-sonnet",
        models=["claude-3-7-sonnet", "claude-3-5-haiku"],
        base_url="https://api.anthropic.com",
        is_active=True,
    )

    client = _create_test_client(monkeypatch, db)
    res = client.get("/api/ai/settings")

    assert res.status_code == 200
    data = res.json()
    assert data["active_profile"]["profile_key"] == "anthropic-main"
    assert data["active_profile"]["provider"] == "anthropic"
    assert data["active_profile"]["is_active"] is True
    assert data["stats"]["total_profiles"] == 1


def test_plugin_threads(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    AIRepository(db_path=db)

    client = _create_test_client(monkeypatch, db)

    post_res = client.post(
        "/api/ai/threads/plugin",
        json={"plugin_slug": "akismet", "is_theme": False, "title": "Chat A"},
    )
    assert post_res.status_code == 200
    created = post_res.json()
    assert created["plugin_slug"] == "akismet"

    list_res = client.get(
        "/api/ai/threads/plugin",
        params={"plugin_slug": "akismet", "is_theme": False},
    )
    assert list_res.status_code == 200
    listed = list_res.json()
    assert listed["threads"]
    assert listed["threads"][0]["id"] == created["id"]


def test_thread_crud(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    client = _create_test_client(monkeypatch, db)

    patch_res = client.patch(
        f"/api/ai/threads/{thread['id']}",
        json={"plugin_slug": "akismet", "is_theme": False, "title": "Renamed Thread"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Renamed Thread"

    del_res = client.request(
        "DELETE",
        f"/api/ai/threads/{thread['id']}",
        json={"plugin_slug": "akismet", "is_theme": False},
    )
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True


def test_prepare_source(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    src = _prepare_thread_source(tmp_path, "akismet", is_theme=False)
    _patch_runtime_paths(monkeypatch, tmp_path / ".zetatech")

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        f"/api/ai/threads/{thread['id']}/source",
        json={
            "plugin_slug": "akismet",
            "is_theme": False,
            "last_scan_session_id": None,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["thread"]["id"] == thread["id"]
    assert data["thread"]["source_available"] is True
    assert data["thread"]["source_context_mode"] == "attached"
    assert data["thread"]["source_path"] == str(src.resolve())


def test_reject_approval(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    run = repo.create_run(
        thread_id=thread["id"],
        provider="anthropic",
        provider_label="Anthropic",
        model="claude",
        status="running",
        workspace_path=str(tmp_path),
    )

    root = tmp_path / ".zetatech"
    _patch_runtime_paths(monkeypatch, root)
    ctrl = root / "approvals" / "decision.json"
    repo.upsert_run_approval(
        run_id=run["id"],
        thread_id=thread["id"],
        status="pending",
        mode="manual",
        control_path=str(ctrl),
        request_payload={"nextTasks": [{"id": "t1", "title": "inspect"}]},
    )

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        f"/api/ai/runs/{run['id']}/approval",
        json={"plugin_slug": "akismet", "is_theme": False, "decision": "rejected"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "decided"
    assert data["decision"] == "rejected"
    assert ctrl.exists()
    assert json.loads(ctrl.read_text(encoding="utf-8"))["decision"] == "rejected"


def test_missing_approval(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    AIRepository(db_path=db)

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        "/api/ai/runs/999/approval",
        json={"plugin_slug": "akismet", "is_theme": False, "decision": "approved"},
    )

    assert res.status_code == 404
    assert res.json()["detail"] == "AI run not found."


def test_escape_approval(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)
    run = repo.create_run(
        thread_id=thread["id"],
        provider="anthropic",
        provider_label="Anthropic",
        model="claude",
        status="running",
        workspace_path=str(tmp_path / "workspace"),
    )

    _patch_runtime_paths(monkeypatch, tmp_path / ".zetatech")
    bad = tmp_path / "somewhere-else" / "approvals" / "decision.json"
    repo.upsert_run_approval(
        run_id=run["id"],
        thread_id=thread["id"],
        status="pending",
        mode="manual",
        control_path=str(bad),
        request_payload={"nextTasks": [{"id": "t1", "title": "inspect"}]},
    )

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        f"/api/ai/runs/{run['id']}/approval",
        json={"plugin_slug": "akismet", "is_theme": False, "decision": "approved"},
    )

    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid approval control path."


def test_update_scope(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    client = _create_test_client(monkeypatch, db)
    res = client.patch(
        f"/api/ai/threads/{thread['id']}",
        json={"plugin_slug": "jetpack", "is_theme": False, "title": "Wrong scope"},
    )

    assert res.status_code == 404
    assert res.json()["detail"] == "AI thread not found."


def test_source_scope(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    thread = repo.get_or_create_thread(plugin_slug="akismet", is_theme=False)

    client = _create_test_client(monkeypatch, db)
    res = client.post(
        f"/api/ai/threads/{thread['id']}/source",
        json={
            "plugin_slug": "jetpack",
            "is_theme": False,
            "last_scan_session_id": None,
        },
    )

    assert res.status_code == 404
    assert res.json()["detail"] == "AI thread not found."


def test_openai_nonstream(monkeypatch):
    from core.routers.agents import provider as mod

    seen = {}

    def _post(url, *, headers, body, timeout=20):
        seen["url"] = url
        seen["headers"] = headers
        seen["body"] = body
        seen["timeout"] = timeout
        return {"choices": [{"message": {"content": "OK"}}]}

    monkeypatch.setattr(mod, "post_json", _post)
    out = mod.test_openai_connection(
        api_key="sk-test",
        model="ag/gemini-3.8-flash",
        base_url="http://host.docker.internal:20128/v1/",
    )

    assert out == "OK"
    assert seen["url"] == "http://host.docker.internal:20128/v1/chat/completions"
    assert seen["body"]["stream"] is False


def test_preserve_active(monkeypatch, tmp_path):
    db = tmp_path / "ai_router.db"
    repo = AIRepository(db_path=db)
    repo.upsert_provider_settings(
        provider="openai",
        profile_key="9router-default",
        display_name="9router",
        api_key="sk-test",
        model="ag/gemini-3.8-flash",
        base_url="http://host.docker.internal:20128/v1",
        is_active=True,
    )

    monkeypatch.setattr("core.routers.agents.test_provider", lambda **_: "OK")
    client = _create_test_client(monkeypatch, db)
    res = client.post(
        "/api/ai/settings/test",
        json={
            "provider": "openai",
            "profile_key": "9router-default",
            "display_name": "9router",
            "model": "ag/gemini-3.8-flash",
            "base_url": "http://host.docker.internal:20128/v1",
        },
    )

    assert res.status_code == 200
    assert res.json()["ok"] is True
    saved = repo.get_active_provider()
    assert saved is not None
    assert saved["profile_key"] == "9router-default"
