from pathlib import Path
from typing import Optional

from fastapi.testclient import TestClient

from core.app import create_app


UPDATE_COMMAND = (
    "docker pull Hugnd-UIT/Zetatech:latest\n"
    "docker rm -f zetatech >/dev/null 2>&1 || true\n"
    "docker run -d --name zetatech -p 8080:8080 "
    "-v zetatech-data:/home/appuser/.zetatech "
    "Hugnd-UIT/Zetatech:latest"
)


def test_update_cmd():
    assert UPDATE_COMMAND.count("-v ") == 1
    assert "-v zetatech-data:/home/appuser/.zetatech" in UPDATE_COMMAND
    assert "zetatech-plugins" not in UPDATE_COMMAND
    assert "zetatech-semgrep" not in UPDATE_COMMAND


class _DummyRepo:
    def __init__(self):
        self.calls = []

    def get_catalog_plugins(self, **kwargs):
        self.calls.append(("get_catalog_plugins", kwargs))
        return {"items": [{"slug": "akismet"}], "total": 1}

    def get_catalog_plugin_sessions(self, **kwargs):
        self.calls.append(("get_catalog_plugin_sessions", kwargs))
        return [{"session_id": 7, "score": 90}]

    def get_favorites(self):
        self.calls.append(("get_favorites", {}))
        return [{"slug": "akismet"}]

    def add_favorite(self, payload):
        self.calls.append(("add_favorite", payload))
        return True

    def remove_favorite(self, slug):
        self.calls.append(("remove_favorite", {"slug": slug}))
        return True


class _DummyUpdateManager:
    def __init__(self):
        self.status_calls = []
        self.manual_payload_calls = 0
        self.raise_status: Optional[Exception] = None
        self.raise_manual_payload: Optional[Exception] = None

    def get_status(self, force=False):
        self.status_calls.append(force)
        if self.raise_status:
            raise self.raise_status
        return {
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "build_id": "build-123",
            "runtime_status": "ready",
            "latest_version": "v0.2.0" if force else "v0.1.3",
            "release_name": "v0.2.0" if force else "v0.1.3",
            "release_notes": "Bug fixes" if force else "",
            "release_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0" if force else "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3",
            "release_published_at": "2026-04-16T00:00:00Z" if force else "2026-04-15T00:00:00Z",
            "latest_version": "v0.2.0" if force else "v0.1.3",
            "update_available": force,
            "status": "update_available" if force else "up_to_date",
            "update_command": UPDATE_COMMAND if force else None,
            "message": "A newer release is available." if force else "Zetatech is already running the latest available release.",
            "manual_update_required": force,
            "manual_update_message": "Automatic updates are no longer supported. Pull the latest image and rerun the container manually." if force else None,
            "checked_at": "2026-04-16T00:00:00Z",
            "last_error": None,
        }

    def manual_payload(self):
        self.manual_payload_calls += 1
        if self.raise_manual_payload:
            raise self.raise_manual_payload
        return {
            "status": "update_available",
            "message": "Automatic updates are no longer supported. Pull the latest image and rerun the container manually.",
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "latest_version": "v0.2.0",
            "update_available": True,
            "update_command": UPDATE_COMMAND,
            "manual_update_required": True,
            "manual_update_only": True,
            "deprecated": True,
        }


def _create_test_client(monkeypatch):
    manager = _DummyUpdateManager()
    test_db_path = Path("/Users/Hugnd-UIT/Desktop/zetatech/.pytest-task05-router.db")
    monkeypatch.setattr("core.app.ensure_db_dir", lambda path=None: test_db_path)
    monkeypatch.setattr("core.app.release.manager", manager)
    monkeypatch.setattr("core.routers.system.release.manager", manager)
    return TestClient(create_app(), base_url="http://localhost"), manager


def test_catalog_plugins(monkeypatch):
    from core.routers import catalog

    repo = _DummyRepo()
    monkeypatch.setattr(catalog, "repo", repo)
    client, _ = _create_test_client(monkeypatch)

    res = client.get(
        "/api/catalog/plugins",
        params={"q": "seo", "sort_by": "score", "order": "asc", "limit": 25, "offset": 10},
    )

    assert res.status_code == 200
    assert res.json() == {"items": [{"slug": "akismet"}], "total": 1}
    assert repo.calls == [
        (
            "get_catalog_plugins",
            {"q": "seo", "sort_by": "score", "order": "asc", "limit": 25, "offset": 10},
        )
    ]


def test_catalog_sessions(monkeypatch):
    from core.routers import catalog

    repo = _DummyRepo()
    monkeypatch.setattr(catalog, "repo", repo)
    client, _ = _create_test_client(monkeypatch)

    res = client.get(
        "/api/catalog/plugins/akismet/sessions",
        params={"is_theme": "false", "limit": 5},
    )

    assert res.status_code == 200
    assert res.json() == {
        "slug": "akismet",
        "sessions": [{"session_id": 7, "score": 90}],
    }
    assert repo.calls == [
        (
            "get_catalog_plugin_sessions",
            {"slug": "akismet", "is_theme": False, "limit": 5},
        )
    ]


def test_update_metadata(monkeypatch):
    mgr = _DummyUpdateManager()
    db = Path("/Users/Hugnd-UIT/Desktop/zetatech/.pytest-task05-router.db")
    monkeypatch.setattr("core.app.ensure_db_dir", lambda path=None: db)
    monkeypatch.setattr("core.app.release.manager", mgr)
    monkeypatch.setattr("core.routers.system.release.manager", mgr)
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_BUILD", "build-123")
    client = TestClient(create_app(), base_url="http://localhost")

    res = client.get("/api/system/update")

    assert res.status_code == 200
    assert res.json() == {
        "current_version": "0.1.3",
        "current_tag": "v0.1.3",
        "build_id": "build-123",
        "runtime_status": "ready",
        "latest_version": "v0.1.3",
        "release_name": "v0.1.3",
        "release_notes": "",
        "release_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3",
        "release_published_at": "2026-04-15T00:00:00Z",
        "update_available": False,
        "status": "up_to_date",
        "update_command": None,
        "message": "Zetatech is already running the latest available release.",
        "manual_update_required": False,
        "manual_update_message": None,
        "checked_at": "2026-04-16T00:00:00Z",
        "last_error": None,
    }
    assert client.app.version == "0.1.3"
    assert mgr.status_calls == [False, False]


def test_favorites_routes(monkeypatch):
    from core.routers import favorites

    repo = _DummyRepo()
    monkeypatch.setattr(favorites, "repo", repo)
    client, _ = _create_test_client(monkeypatch)

    list_res = client.get("/api/favorites")
    add_res = client.post(
        "/api/favorites",
        json={
            "slug": "akismet",
            "name": "Akismet",
            "version": "1.0.0",
            "score": 80,
            "installations": 1000,
            "days_since_update": 5,
            "tested_wp_version": "6.8",
            "is_theme": False,
            "download_link": "https://downloads.wordpress.org/plugin/akismet.zip",
            "wp_org_link": "https://wordpress.org/plugins/akismet/",
            "cve_search_link": "https://cve.mitre.org/cgi-bin/cvekey.cgi?keyword=akismet",
            "wpscan_link": "https://wpscan.com/plugin/akismet",
            "trac_link": "https://plugins.trac.wordpress.org/browser/akismet/",
            "author_trusted": False,
            "is_risky_category": False,
            "is_user_facing": True,
            "risk_tags": ["public-input"],
            "security_flags": ["custom-ajax"],
            "feature_flags": ["settings-page"],
            "code_analysis": {"summary": "ok"},
        },
    )
    del_res = client.delete("/api/favorites/akismet")

    assert list_res.status_code == 200
    assert list_res.json() == {"favorites": [{"slug": "akismet"}]}
    assert add_res.status_code == 200
    assert add_res.json() == {"success": True}
    assert del_res.status_code == 200
    assert del_res.json() == {"success": True}

    assert repo.calls[0] == ("get_favorites", {})
    assert repo.calls[1][0] == "add_favorite"
    assert repo.calls[1][1]["slug"] == "akismet"
    assert repo.calls[1][1]["code_analysis"] == {"summary": "ok"}
    assert repo.calls[2] == ("remove_favorite", {"slug": "akismet"})


def test_update_status(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)

    res = client.get("/api/system/update", params={"force": "true"})

    assert res.status_code == 200
    assert res.json() == {
        "current_version": "0.1.3",
        "current_tag": "v0.1.3",
        "build_id": "build-123",
        "runtime_status": "ready",
        "latest_version": "v0.2.0",
        "release_name": "v0.2.0",
        "release_notes": "Bug fixes",
        "release_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0",
        "release_published_at": "2026-04-16T00:00:00Z",
        "update_available": True,
        "status": "update_available",
        "update_command": UPDATE_COMMAND,
        "message": "A newer release is available.",
        "manual_update_required": True,
        "manual_update_message": "Automatic updates are no longer supported. Pull the latest image and rerun the container manually.",
        "checked_at": "2026-04-16T00:00:00Z",
        "last_error": None,
    }
    assert mgr.status_calls[-1] is True


def test_update_degraded(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)

    def _degraded(force=False):
        mgr.status_calls.append(force)
        return {
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "runtime_status": "degraded",
            "latest_version": None,
            "update_available": False,
            "status": "degraded",
            "update_command": None,
            "message": "Release information is temporarily unavailable.",
            "manual_update_required": False,
        }

    mgr.get_status = _degraded

    res = client.get("/api/system/update")

    assert res.status_code == 200
    assert res.json() == {
        "current_version": "0.1.3",
        "current_tag": "v0.1.3",
        "runtime_status": "degraded",
        "latest_version": None,
        "update_available": False,
        "status": "degraded",
        "update_command": None,
        "message": "Release information is temporarily unavailable.",
        "manual_update_required": False,
    }
    assert mgr.status_calls[-1] is False


def test_update_shape(monkeypatch):
    client, _ = _create_test_client(monkeypatch)

    up_res = client.get("/api/system/update")
    new_res = client.get("/api/system/update", params={"force": "true"})

    up = up_res.json()
    new = new_res.json()

    assert up_res.status_code == 200
    assert new_res.status_code == 200
    assert set(up.keys()) == set(new.keys())
    assert up["status"] == "up_to_date"
    assert new["status"] == "update_available"
    assert up["current_version"] == new["current_version"] == "0.1.3"
    assert up["current_tag"] == new["current_tag"] == "v0.1.3"
    assert up["update_command"] is None
    assert new["update_command"] == UPDATE_COMMAND
    assert up["update_available"] is False
    assert new["update_available"] is True
    assert up["manual_update_required"] is False
    assert new["manual_update_required"] is True
    assert up["latest_version"] == "v0.1.3"
    assert new["latest_version"] == "v0.2.0"


def test_degraded_shape(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)

    def _degraded(force=False):
        mgr.status_calls.append(force)
        return {
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "runtime_status": "degraded",
            "latest_version": None,
            "update_available": False,
            "status": "degraded",
            "update_command": None,
            "message": "Release information is temporarily unavailable.",
            "manual_update_required": False,
        }

    mgr.get_status = _degraded

    res = client.get("/api/system/update")
    data = res.json()

    assert res.status_code == 200
    assert set(data.keys()) == {
        "current_version",
        "current_tag",
        "runtime_status",
        "latest_version",
        "update_available",
        "status",
        "update_command",
        "message",
        "manual_update_required",
    }
    assert data["status"] == "degraded"
    assert data["runtime_status"] == "degraded"
    assert data["latest_version"] is None
    assert data["update_command"] is None
    assert data["update_available"] is False


def test_update_503(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)
    mgr.raise_status = RuntimeError("boom")

    res = client.get("/api/system/update")

    assert res.status_code == 503
    assert res.json()["detail"] == "Unable to check for releases right now."


def test_unwritable_logs(monkeypatch, tmp_path):
    import logger as mod
    from paths import RuntimePaths

    logs = tmp_path / "blocked-home" / ".zetatech" / "logs"
    root = logs.parent
    paths = RuntimePaths(
        root=root,
        db_file=root / "zetatech.db",
        logs_dir=logs,
        plugins_dir=root / "plugins",
        semgrep_dir=root / "semgrep",
        semgrep_outputs_dir=root / "semgrep-results",
        approvals_dir=root / "approvals",
    )

    def _fail(self, *args, **kwargs):
        if self == logs:
            raise PermissionError("blocked")
        return mkdir(self, *args, **kwargs)

    mkdir = Path.mkdir
    monkeypatch.setattr(mod, "resolve_runtime_paths", lambda: paths)

    def _ok(path=None):
        assert path is None
        root.mkdir(parents=True, exist_ok=True)
        return paths.db_file

    monkeypatch.setattr("core.app.ensure_db_dir", _ok)
    monkeypatch.setattr(Path, "mkdir", _fail)

    client, mgr = _create_test_client(monkeypatch)
    res = client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    assert mgr.status_calls == [False]


def test_unwritable_db(monkeypatch, tmp_path):
    db = tmp_path / "blocked-home" / ".zetatech" / "zetatech.db"

    def _fail(path=None):
        assert path is None
        raise PermissionError(f"Database directory is not writable: {db.parent}")

    monkeypatch.setattr("core.app.ensure_db_dir", _fail)

    try:
        create_app()
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert str(db.parent) in str(exc)


def test_trigger_update(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)

    res = client.post("/api/system/update")

    assert res.status_code == 200
    assert res.json() == {
        "status": "update_available",
        "message": "Automatic updates are no longer supported. Pull the latest image and rerun the container manually.",
        "current_version": "0.1.3",
        "current_tag": "v0.1.3",
        "latest_version": "v0.2.0",
        "update_available": True,
        "update_command": UPDATE_COMMAND,
        "manual_update_required": True,
        "manual_update_only": True,
        "deprecated": True,
    }
    assert mgr.manual_payload_calls == 1


def test_trigger_deprecated(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)

    res = client.post("/api/system/update")
    data = res.json()

    assert res.status_code == 200
    assert data["deprecated"] is True
    assert data["manual_update_only"] is True
    assert data["update_command"] == UPDATE_COMMAND
    assert mgr.manual_payload_calls == 1
    assert mgr.status_calls == [False]


def test_trigger_degraded(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)

    def _degraded():
        mgr.manual_payload_calls += 1
        return {
            "status": "degraded",
            "message": "Automatic updates are no longer supported. Pull the latest image and rerun the container manually.",
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "latest_version": None,
            "update_available": False,
            "update_command": None,
            "manual_update_required": False,
            "manual_update_only": True,
            "deprecated": True,
        }

    mgr.manual_payload = _degraded

    res = client.post("/api/system/update")

    assert res.status_code == 200
    assert res.json() == {
        "status": "degraded",
        "message": "Automatic updates are no longer supported. Pull the latest image and rerun the container manually.",
        "current_version": "0.1.3",
        "current_tag": "v0.1.3",
        "latest_version": None,
        "update_available": False,
        "update_command": None,
        "manual_update_required": False,
        "manual_update_only": True,
        "deprecated": True,
    }
    assert mgr.manual_payload_calls == 1
    assert mgr.status_calls == [False]


def test_trigger_503(monkeypatch):
    client, mgr = _create_test_client(monkeypatch)
    mgr.raise_manual_payload = RuntimeError("boom")

    res = client.post("/api/system/update")

    assert res.status_code == 503
    assert res.json()["detail"] == "Unable to prepare manual update instructions right now."
    assert mgr.manual_payload_calls == 1
