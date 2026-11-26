from pathlib import Path

import pytest

from database.models import _db_path
from paths import resolve_runtime_paths
from core.release import UpdateManager


ROOT = Path(__file__).resolve().parents[1]


class _TestUpdateManager(UpdateManager):
    def __init__(self, state_dir: Path):
        self._test_state_dir = state_dir
        super().__init__()


def test_status_env(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_BUILD", "build-123")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": None, "update_available": False}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["current_version"] == "0.1.3"
    assert res["current_tag"] == "v0.1.3"
    assert res["build_id"] == "build-123"
    assert res["runtime_status"] == "ready"
    assert res["status"] == "up_to_date"


def test_status_current(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.1.3", "update_available": False}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["status"] == "up_to_date"
    assert res["update_available"] is False
    assert res["update_command"] is None
    assert res["manual_update_required"] is False


def test_unwritable_root(monkeypatch, tmp_path):
    blocked = tmp_path / "blocked-home" / ".zetatech" / "zetatech.db"
    monkeypatch.delenv("ZETATECH_DB", raising=False)
    monkeypatch.setattr("database.models.DEFAULT_DB_PATH", blocked)
    monkeypatch.setattr("database.models._dir_writable", lambda p: p != blocked.parent)

    with pytest.raises(PermissionError, match=str(blocked.parent)):
        _db_path(None)


def test_runtime_roots():
    paths = resolve_runtime_paths()

    assert paths.root == Path("/home/appuser/.zetatech")
    assert paths.db_file == paths.root / "zetatech.db"
    assert paths.logs_dir == paths.root / "logs"
    assert paths.plugins_dir == paths.root / "plugins"
    assert paths.semgrep_dir == paths.root / "semgrep"
    assert paths.semgrep_outputs_dir == paths.root / "semgrep-results"
    assert paths.approvals_dir == paths.root / "approvals"


def test_runtime_stable():
    p1 = resolve_runtime_paths()
    p2 = resolve_runtime_paths()

    assert p1 is p2
    assert p1 == p2


def test_unwritable_db(monkeypatch, tmp_path):
    db = tmp_path / "blocked" / "zetatech.db"
    monkeypatch.setattr("database.models._dir_writable", lambda p: False)

    try:
        _db_path(db)
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert str(db.parent) in str(exc)


def test_env_db(monkeypatch, tmp_path):
    db = tmp_path / "state" / "zetatech.db"
    monkeypatch.setenv("ZETATECH_DB", str(db))

    got = _db_path(None)

    assert got == db
    assert db.parent.exists()


def test_status_update(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {
            "tag_name": "v0.2.0",
            "name": "v0.2.0",
            "body": "Bug fixes",
            "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0",
            "published_at": "2026-04-16T00:00:00Z",
            "update_available": True,
        }

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["status"] == "update_available"
    assert res["update_available"] is True
    assert res["manual_update_required"] is True
    assert "docker pull Hugnd-UIT/Zetatech:latest" in res["update_command"]
    assert "-v zetatech-data:/home/appuser/.zetatech" in res["update_command"]
    assert "zetatech-plugins" not in res["update_command"]
    assert "zetatech-semgrep" not in res["update_command"]
    assert "/app/Plugins" not in res["update_command"]
    assert "/app/semgrep_results" not in res["update_command"]


def test_status_degraded(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")
    monkeypatch.setattr(mgr, "_fetch_release", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))

    res = mgr.get_status(force=True)

    assert res["status"] == "degraded"
    assert res["update_available"] is False
    assert res["update_command"] is None
    assert res["last_error"] == "RuntimeError: boom"
    assert "temporarily unavailable" in res["message"]


def test_status_malformed(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.delenv("ZETATECH_IMAGE_TAG", raising=False)
    monkeypatch.delenv("ZETATECH_IMAGE_BUILD", raising=False)

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": None, "update_available": False}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["current_version"] == "unknown"
    assert res["current_tag"] == "unknown"
    assert res["runtime_status"] == "degraded"
    assert res["status"] == "degraded"
    assert "Runtime version metadata is incomplete" in res["message"]


def test_no_update_file(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "update_available": True}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status(force=True)

    assert res["update_available"] is True
    assert not (tmp_path / ".zetatech" / "update_state.json").exists()


def test_manual_notify(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def status(*args, **kwargs):
        del args, kwargs
        return {
            "status": "update_available",
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "latest_version": "v0.2.0",
            "update_available": True,
            "update_command": "docker pull Hugnd-UIT/Zetatech:latest",
            "manual_update_required": True,
        }

    monkeypatch.setattr(mgr, "get_status", status)

    res = mgr.manual_payload()

    assert res == {
        "status": "update_available",
        "message": "Automatic updates are no longer supported. Pull the latest image and rerun the container manually.",
        "current_version": "0.1.3",
        "current_tag": "v0.1.3",
        "latest_version": "v0.2.0",
        "update_available": True,
        "update_command": "docker pull Hugnd-UIT/Zetatech:latest",
        "manual_update_required": True,
        "manual_update_only": True,
        "deprecated": True,
    }


def test_manual_degraded(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    def status(*args, **kwargs):
        del args, kwargs
        return {
            "status": "degraded",
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "latest_version": None,
            "update_available": False,
            "update_command": None,
            "manual_update_required": False,
        }

    monkeypatch.setattr(mgr, "get_status", status)

    res = mgr.manual_payload()

    assert res["status"] == "degraded"
    assert res["deprecated"] is True
    assert res["manual_update_only"] is True
    assert res["update_command"] is None
    assert res["latest_version"] is None
    assert res["current_tag"] == "v0.1.3"


def test_legacy_removed():
    assert not (ROOT / "run.sh").exists()
    assert not (ROOT / "infrastructure" / "host_update_watcher.sh").exists()
    assert not (ROOT / "infrastructure" / "update_docker_install.sh").exists()


def test_readme_install():
    txt = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docker pull Hugnd-UIT/Zetatech:latest" in txt
    assert "docker run -d --name zetatech -p 8080:8080" in txt
    assert "-v zetatech-data:/home/appuser/.zetatech" in txt
    assert "This is a hard cutover to the canonical runtime root." in txt
    assert "only `zetatech-data` mounted at `/home/appuser/.zetatech`" in txt
    assert "three named Docker volumes" not in txt
    assert "-v zetatech-plugins:/app/Plugins" not in txt
    assert "-v zetatech-semgrep:/app/semgrep_results" not in txt
    assert "./run.sh" not in txt
    assert "host-side update watcher" not in txt
    assert "rebuild and restart everything" not in txt
    assert "git clone https://github.com/Hugnd-UIT/Zetatech.git" not in txt


def test_manual_cmd(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    cmd = mgr._update_cmd()

    assert cmd.count("-v ") == 1
    assert "docker pull Hugnd-UIT/Zetatech:latest" in cmd
    assert "-v zetatech-data:/home/appuser/.zetatech" in cmd
    assert "zetatech-plugins" not in cmd
    assert "zetatech-semgrep" not in cmd
    assert "/app/Plugins" not in cmd
    assert "/app/semgrep_results" not in cmd
    assert "run.sh" not in cmd
    assert "update_docker_install.sh" not in cmd
    assert "host_update_watcher.sh" not in cmd
    assert "docker build" not in cmd
    assert "git pull" not in cmd
    assert "update_state.json" not in cmd
    assert "update-runtime.json" not in cmd


def test_metadata_fallback(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.delenv("ZETATECH_IMAGE_VERSION", raising=False)
    monkeypatch.delenv("ZETATECH_IMAGE_TAG", raising=False)
    monkeypatch.delenv("ZETATECH_IMAGE_BUILD", raising=False)

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": None, "update_available": False}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["current_version"] == "0.2.0"
    assert res["current_tag"] == "0.2.0"
    assert res["runtime_status"] == "fallback"
    assert res["status"] == "up_to_date"
    assert not (tmp_path / ".zetatech" / "update-runtime.json").exists()


def test_status_compare(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.2")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.2")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {
            "tag_name": "v0.1.3",
            "name": "v0.1.3",
            "body": "Bug fixes",
            "html_url": "https://github.com/Hugnd-UIT/Zetatech/releases/tag/v0.1.3",
            "published_at": "2026-04-16T00:00:00Z",
        }

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["current_version"] == "0.1.2"
    assert res["current_tag"] == "v0.1.2"
    assert res["latest_version"] == "v0.1.3"
    assert res["release_url"] == "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3"
    assert res["update_available"] is True
    assert res["status"] == "update_available"


def test_reject_html_host(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    with pytest.raises(ValueError, match="Unsupported release URL host"):
        mgr._release_metadata.release_payload(
            {
                "tag_name": "v0.1.3",
                "name": "v0.1.3",
                "body": "Bug fixes",
                "html_url": "https://example.com/releases/v0.1.3",
                "published_at": "2026-04-16T00:00:00Z",
            }
        )


def test_reject_api_host(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    mgr._release_metadata.release_api_url = "https://example.com/tags"

    with pytest.raises(ValueError, match="Unsupported release API host"):
        mgr._release_metadata.fetch_release()


def test_pick_semver(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag(
        [
            {"name": "v0.1.9"},
            {"name": "v0.2.0"},
            {"name": "main"},
            {"name": "v0.10.0"},
        ]
    )

    assert tag == "v0.10.0"


def test_ignore_non_semver(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag(
        [
            {"name": "latest"},
            {"name": "main"},
            {"name": "release-candidate"},
        ]
    )

    assert tag is None


def test_fetch_tags(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "main"}, {"name": "v0.2.0"}, {"name": "v0.1.3"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    res = mgr._release_metadata.fetch_release()

    assert res == {
        "tag_name": "v0.2.0",
        "name": "v0.2.0",
        "body": "",
        "published_at": None,
        "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0",
    }


def test_fetch_empty(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "main"}, {"name": "latest"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    res = mgr._release_metadata.fetch_release()

    assert res == mgr._release_metadata.empty_payload()


def test_tag_url(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    assert mgr._release_metadata.tag_url("v0.2.0") == "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0"
    assert mgr._release_metadata.tag_url("release/test") == "https://github.com/Hugnd-UIT/Zetatech/tree/release/test"


def test_tags_api(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    assert mgr.RELEASE_API_URL.endswith("/tags")
    assert mgr._release_metadata.release_api_url.endswith("/tags")


def test_current_url(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {
            "tag_name": "v0.1.3",
            "name": "v0.1.3",
            "body": "",
            "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3",
            "published_at": None,
            "update_available": False,
        }

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["release_url"] == "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3"
    assert res["release_notes"] == ""
    assert res["release_published_at"] is None
    assert res["status"] == "up_to_date"


def test_update_url(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.2")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.2")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {
            "tag_name": "v0.1.3",
            "name": "v0.1.3",
            "body": "",
            "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3",
            "published_at": None,
        }

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["release_url"] == "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3"
    assert res["update_available"] is True
    assert res["status"] == "update_available"


def test_degraded_keys(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")
    monkeypatch.setattr(mgr, "_fetch_release", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))

    res = mgr.get_status(force=True)

    assert res["status"] == "degraded"
    assert res["latest_version"] is None
    assert res["release_name"] is None
    assert res["release_notes"] == ""
    assert res["release_url"] is None
    assert res["release_published_at"] is None
    assert res["last_error"] == "RuntimeError: boom"


def test_tag_headers(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    assert mgr._release_metadata.tag_headers() == mgr._release_metadata.release_headers()


def test_prefer_tag(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.2")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.2")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["latest_version"] == "v0.2.0"
    assert res["update_available"] is True


def test_unknown_tag(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.2")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "unknown")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["update_available"] is True
    assert res["latest_version"] == "v0.2.0"


def test_empty_tag(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return manager_empty(mgr)

    def manager_empty(m):
        return m._release_metadata.empty_payload()

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["latest_version"] is None
    assert res["update_available"] is False
    assert res["status"] == "up_to_date"


def test_tree_url(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    res = mgr._release_metadata.release_payload(
        {
            "tag_name": "v0.1.3",
            "name": "v0.1.3",
            "body": "",
            "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3",
            "published_at": None,
        }
    )

    assert res["html_url"] == "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3"


def test_longer_semver(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag(
        [{"name": "v0.2"}, {"name": "v0.2.1"}, {"name": "v0.2.0"}]
    )

    assert tag == "v0.2.1"


def test_upper_v(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag([{"name": "V0.2.0"}, {"name": "v0.1.0"}])

    assert tag == "V0.2.0"


def test_skip_rc(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag([{"name": "v0.2.0-rc1"}, {"name": "v0.1.9"}])

    assert tag == "v0.1.9"


def test_reject_tree_host(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    with pytest.raises(ValueError, match="Unsupported release URL host"):
        mgr._release_metadata.release_payload(
            {
                "tag_name": "v0.2.0",
                "name": "v0.2.0",
                "body": "",
                "html_url": "https://example.com/tree/v0.2.0",
                "published_at": None,
            }
        )


def test_reject_shape(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": True}

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    with pytest.raises(ValueError, match="Unexpected tags API response shape"):
        mgr._release_metadata.fetch_release()


def test_tags_request(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    seen = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "v0.2.0"}]

    def get(url, headers, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("core.release.requests.get", get)

    mgr._release_metadata.fetch_release()

    assert seen["url"].endswith("/tags")
    assert seen["headers"]["User-Agent"] == "Zetatech Update Agent"
    assert seen["timeout"] == 15


def test_slash_tag(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    assert mgr._release_metadata.tag_url("release/test") == "https://github.com/Hugnd-UIT/Zetatech/tree/release/test"


def test_manual_msg(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["manual_update_required"] is True
    assert res["manual_update_message"] == mgr.MESSAGE_MANUAL_UPDATE_ONLY


def test_empty_notes(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.1.3", "name": "v0.1.3", "body": None, "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["release_notes"] == ""


def test_fallback_name(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": None, "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["release_name"] == "v0.2.0"


def test_missing_url(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": None, "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["release_url"] is None


def test_missing_tag(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": None, "name": None, "body": "", "html_url": None, "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["latest_version"] is None
    assert res["update_available"] is False
    assert res["status"] == "up_to_date"


def test_helper_url(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    def status(*args, **kwargs):
        del args, kwargs
        return {
            "status": "update_available",
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "latest_version": "v0.2.0",
            "release_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0",
            "update_available": True,
            "update_command": "docker pull Hugnd-UIT/Zetatech:latest",
            "manual_update_required": True,
        }

    monkeypatch.setattr(mgr, "get_status", status)

    res = mgr.manual_payload()

    assert res["latest_version"] == "v0.2.0"
    assert res["update_command"] == "docker pull Hugnd-UIT/Zetatech:latest"


def test_empty_body(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    res = mgr._release_metadata.release_payload(
        {"tag_name": "v0.2.0", "name": "v0.2.0", "body": None, "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}
    )

    assert res["body"] == ""


def test_payload_name(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    res = mgr._release_metadata.release_payload(
        {"tag_name": "v0.2.0", "name": None, "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}
    )

    assert res["name"] == "v0.2.0"


def test_empty_list(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    res = mgr._release_metadata.fetch_release()

    assert res == mgr._release_metadata.empty_payload()


def test_version_order(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    assert mgr._release_metadata.normalized_version("v0.2.0") > mgr._release_metadata.normalized_version("v0.1.9")


def test_blank_tags(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag([{"name": ""}, {"name": "v0.1.0"}])

    assert tag == "v0.1.0"


def test_reject_bad_host(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    with pytest.raises(ValueError, match="Unsupported release URL host"):
        mgr._release_metadata.release_payload(
            {"tag_name": "v0.1.3", "name": "v0.1.3", "body": "", "html_url": "https://bad.example/tree/v0.1.3", "published_at": None}
        )


def test_preserve_name(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "v0.2.0"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    res = mgr._release_metadata.fetch_release()

    assert res["name"] == "v0.2.0"


def test_no_published_at(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "v0.2.0"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    res = mgr._release_metadata.fetch_release()

    assert res["published_at"] is None


def test_empty_tag_body(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "v0.2.0"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    res = mgr._release_metadata.fetch_release()

    assert res["body"] == ""


def test_semver_over_lexical(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag([{"name": "v0.9.0"}, {"name": "v0.10.0"}])

    assert tag == "v0.10.0"


def test_docker_msg(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert "Pull the latest image" in res["message"] or res["status"] == "update_available"


def test_current_msg(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.3")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.3")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.1.3", "name": "v0.1.3", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.3", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["message"] == mgr.MESSAGE_UP_TO_DATE


def test_patchless_semver(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag([{"name": "v1.2"}, {"name": "v1.2.1"}])

    assert tag == "v1.2.1"


def test_stable_fields(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.2.0")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.2.0")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["release_name"] == "v0.2.0"
    assert res["release_url"] == "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0"
    assert res["release_notes"] == ""
    assert res["release_published_at"] is None


def test_unknown_version(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.2.0")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "unknown")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.1", "name": "v0.2.1", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.1", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["update_available"] is True


def test_empty_pick(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    assert mgr._release_metadata._pick_tag([]) is None


def test_pick_called(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "v0.1.0"}, {"name": "v0.2.0"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(mgr._release_metadata, "_pick_tag", lambda tags: "v0.2.0")

    res = mgr._release_metadata.fetch_release()

    assert res["tag_name"] == "v0.2.0"


def test_empty_url(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    res = mgr._release_metadata.release_payload(
        {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": None, "published_at": None}
    )

    assert res["html_url"] is None


def test_extra_segments(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag([{"name": "v1.2.3.4"}, {"name": "v1.2.3"}])

    assert tag == "v1.2.3.4"


def test_release_name(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")
    monkeypatch.setenv("ZETATECH_IMAGE_VERSION", "0.1.0")
    monkeypatch.setenv("ZETATECH_IMAGE_TAG", "v0.1.0")

    def resolve(*args, **kwargs):
        del args, kwargs
        return {"tag_name": "v0.2.0", "name": "v0.2.0", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.2.0", "published_at": None}

    monkeypatch.setattr(mgr, "_resolve_release", resolve)

    res = mgr.get_status()

    assert res["release_name"] == "v0.2.0"


def test_manual_deprecated(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    def status(*args, **kwargs):
        del args, kwargs
        return {
            "status": "update_available",
            "current_version": "0.1.3",
            "current_tag": "v0.1.3",
            "latest_version": "v0.2.0",
            "update_available": True,
            "update_command": "docker pull Hugnd-UIT/Zetatech:latest",
            "manual_update_required": True,
        }

    monkeypatch.setattr(mgr, "get_status", status)

    res = mgr.manual_payload()

    assert res["deprecated"] is True
    assert res["manual_update_only"] is True


def test_tag_case(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "release"}, {"name": "V0.2.0"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())

    res = mgr._release_metadata.fetch_release()

    assert res["tag_name"] == "V0.2.0"


def test_missing_name(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    tag = mgr._release_metadata._pick_tag([{}, {"name": "v0.1.0"}])

    assert tag == "v0.1.0"


def test_none_pick(monkeypatch, tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "main"}]

    monkeypatch.setattr("core.release.requests.get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(mgr._release_metadata, "_pick_tag", lambda tags: None)

    res = mgr._release_metadata.fetch_release()

    assert res == mgr._release_metadata.empty_payload()


def test_allow_github(tmp_path):
    mgr = _TestUpdateManager(tmp_path / ".zetatech")

    res = mgr._release_metadata.release_payload(
        {"tag_name": "v0.1.0", "name": "v0.1.0", "body": "", "html_url": "https://github.com/Hugnd-UIT/Zetatech/tree/v0.1.0", "published_at": None}
    )

    assert res["tag_name"] == "v0.1.0"
