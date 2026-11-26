import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from core.routers.semgrep import helper as semgrep_helpers
from core.routers.semgrep.helper import get_disabled_config, save_doc

DB_TEST_PATH = Path(tempfile.gettempdir()) / "zetatech-semgrep-router-tests.db"
os.environ.setdefault("ZETATECH_DB", str(DB_TEST_PATH))

from core.app import create_app


class _DummyRepo:
    def __init__(self):
        self.semgrep_scan_calls = []

    def create_semgrep_scan(self, slug, version=None):
        self.semgrep_scan_calls.append((slug, version))
        return 77

    def get_catalog_latest_version(self, slug, is_theme=False):
        if slug == "akismet" and not is_theme:
            return "5.3.1"
        return None

    def get_semgrep_scan(self, slug):
        if slug == "akismet":
            return {"id": 77, "slug": slug, "status": "completed"}
        return None

    def get_session_results(self, session_id, *args, **kwargs):
        del args, kwargs
        if session_id == 10:
            return [
                {
                    "slug": "akismet",
                    "version": "5.3.1",
                    "download_link": "https://downloads.wordpress.org/plugin/akismet.5.3.1.zip",
                },
                {
                    "slug": "hello-dolly",
                    "version": "1.7.2",
                    "download_link": "https://downloads.wordpress.org/plugin/hello-dolly.1.7.2.zip",
                },
            ]
        return []

    def get_semgrep_stats_for_slugs(self, slugs):
        if not slugs:
            return {
                "scanned_count": 0,
                "total_findings": 0,
                "breakdown": {},
                "running_count": 0,
                "pending_count": 0,
                "failed_count": 0,
                "completed_count": 0,
            }
        return {
            "scanned_count": 1,
            "total_findings": 3,
            "breakdown": {"HIGH": 1, "MEDIUM": 2},
            "running_count": 0,
            "pending_count": 1,
            "failed_count": 0,
            "completed_count": 1,
        }


def _client(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "core.app.release.manager.get_status",
        lambda force=False: {"status": "ok", "force": force},
    )
    test_db_path = tmp_path / "runtime-root" / "zetatech.db"
    monkeypatch.setattr("database.models.DEFAULT_DB_PATH", test_db_path)
    return TestClient(create_app(), base_url="http://localhost")


def _patch_state(monkeypatch, tmp_path: Path):
    from core.routers.semgrep import helper as semgrep_helpers, service as semgrep_service

    state_dir = tmp_path / "runtime-root" / "semgrep"
    custom_rules_path = state_dir / "custom_rules.yaml"
    disabled_config_path = state_dir / "disabled_config.json"
    monkeypatch.setattr(semgrep_helpers, "SEMGREP_STATE_DIR", state_dir)
    monkeypatch.setattr(semgrep_helpers, "CUSTOM_RULES_PATH", custom_rules_path)
    monkeypatch.setattr(semgrep_helpers, "DISABLED_CONFIG_PATH", disabled_config_path)
    monkeypatch.setattr(semgrep_service, "CUSTOM_RULES_PATH", custom_rules_path)
    return state_dir


def _patch_tasks(monkeypatch):

    async def _noop_single(*args, **kwargs):
        del args, kwargs

    async def _noop_bulk(*args, **kwargs):
        del args, kwargs

    monkeypatch.setattr("core.routers.semgrep.service.run_scan", _noop_single)
    monkeypatch.setattr("core.routers.semgrep.service.run_bulk", _noop_bulk)


def test_semgrep_scan(monkeypatch, tmp_path):
    from core.routers import semgrep

    repo = _DummyRepo()
    monkeypatch.setattr(semgrep, "repo", repo)
    _patch_tasks(monkeypatch)

    cli = _client(monkeypatch, tmp_path)

    res = cli.post(
        "/api/semgrep/scan",
        json={
            "slug": "akismet",
            "download_url": "https://downloads.wordpress.org/plugin/akismet.5.3.1.zip",
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    got = cli.get("/api/semgrep/scan/akismet")
    assert got.status_code == 200
    assert got.json()["status"] == "completed"


def test_semgrep_rules(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    cli = _client(monkeypatch, tmp_path)

    res = cli.get("/api/semgrep/rules")
    assert res.status_code == 200
    assert "rulesets" in res.json()

    created = cli.post(
        "/api/semgrep/rules",
        json={
            "id": "custom_eval_rule",
            "pattern": "eval($X)",
            "message": "Avoid eval",
            "severity": "WARNING",
            "languages": ["php"],
        },
    )
    assert created.status_code == 200
    assert created.json()["success"] is True
    assert (dir / "custom_rules.yaml").exists()

    tog = cli.post("/api/semgrep/rules/custom_eval_rule/toggle")
    assert tog.status_code == 200
    assert tog.json()["rule_id"] == "custom_eval_rule"
    off = json.loads((dir / "disabled_config.json").read_text())
    assert off["rules"] == ["custom_eval_rule"]

    all_new = cli.post("/api/semgrep/rules/actions/toggle-all", json={"enabled": True})
    assert all_new.status_code == 200
    assert all_new.json()["success"] is True

    all_old = cli.post("/api/semgrep/rules/toggle-all", json={"enabled": False})
    assert all_old.status_code == 405

    set_new = cli.post("/api/semgrep/rulesets", json={"ruleset": "r/custom-demo"})
    assert set_new.status_code == 200
    assert set_new.json()["ruleset_id"] == "r/custom-demo"

    set_tog = cli.post("/api/semgrep/rulesets/r/custom-demo/toggle")
    assert set_tog.status_code == 200
    assert set_tog.json()["ruleset_id"] == "r/custom-demo"

    set_del = cli.delete("/api/semgrep/rulesets/r/custom-demo")
    assert set_del.status_code == 200
    assert set_del.json()["deleted"] == "r/custom-demo"

    rule_del = cli.delete("/api/semgrep/rules/custom_eval_rule")
    assert rule_del.status_code == 200
    assert rule_del.json()["deleted"] == "custom_eval_rule"
    assert get_disabled_config()["rules"] == []
    assert "custom_eval_rule" not in [
        rule.get("id") for rule in semgrep_helpers.load_doc().get("rules", [])
    ]


def test_semgrep_bulk(monkeypatch, tmp_path):
    from core.routers import semgrep
    from core.routers.semgrep import tasks as semgrep_tasks

    repo = _DummyRepo()
    monkeypatch.setattr(semgrep, "repo", repo)
    _patch_tasks(monkeypatch)
    semgrep_tasks.active_bulk_scans.clear()

    cli = _client(monkeypatch, tmp_path)

    started = cli.post("/api/semgrep/bulk/10")
    assert started.status_code == 200
    assert started.json()["status"] == "started"
    assert started.json()["count"] == 2

    res = cli.get("/api/semgrep/bulk/10/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["session_id"] == 10
    assert stats["total_plugins"] == 2
    assert stats["scanned_count"] == 1

    stopped = cli.post("/api/semgrep/bulk/10/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopping"


def test_invalid_slug(monkeypatch, tmp_path):
    from core.routers import semgrep

    repo = _DummyRepo()
    monkeypatch.setattr(semgrep, "repo", repo)

    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/semgrep/scan",
        json={
            "slug": "..bad-slug",
            "download_url": "https://downloads.wordpress.org/plugin/akismet.5.3.1.zip",
        },
    )

    assert res.status_code == 422


def test_read_fallback(monkeypatch, tmp_path):
    dir = tmp_path / "blocked-home" / ".zetatech" / "semgrep"
    cfg = tmp_path / "legacy-disabled.json"
    cfg.write_text(json.dumps({"rules": ["rule-a"], "rulesets": [], "extra_rulesets": []}))

    mkdir = Path.mkdir

    def _fail(self, *args, **kwargs):
        if self == dir:
            raise PermissionError("blocked")
        return mkdir(self, *args, **kwargs)

    monkeypatch.setattr(semgrep_helpers, "SEMGREP_STATE_DIR", dir)
    monkeypatch.setattr(semgrep_helpers, "CUSTOM_RULES_PATH", dir / "custom_rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "DISABLED_CONFIG_PATH", dir / "disabled_config.json")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_DISABLED_CONFIG_PATH", cfg)
    monkeypatch.setattr(Path, "mkdir", _fail)

    assert get_disabled_config() == {"rules": [], "rulesets": [], "extra_rulesets": []}


def test_write_blocked(monkeypatch, tmp_path):
    dir = tmp_path / "blocked-home" / ".zetatech" / "semgrep"
    mkdir = Path.mkdir

    def _fail(self, *args, **kwargs):
        if self == dir:
            raise PermissionError("blocked")
        return mkdir(self, *args, **kwargs)

    monkeypatch.setattr(semgrep_helpers, "SEMGREP_STATE_DIR", dir)
    monkeypatch.setattr(semgrep_helpers, "CUSTOM_RULES_PATH", dir / "custom_rules.yaml")
    monkeypatch.setattr(Path, "mkdir", _fail)

    try:
        save_doc({"rules": []})
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not writable" in str(exc)


def test_bootstrap_blocked(monkeypatch, tmp_path):
    dir = tmp_path / "blocked-home" / ".zetatech" / "semgrep"
    mkdir = Path.mkdir

    def _fail(self, *args, **kwargs):
        if self == dir:
            raise PermissionError("blocked")
        return mkdir(self, *args, **kwargs)

    monkeypatch.setattr(semgrep_helpers, "SEMGREP_STATE_DIR", dir)
    monkeypatch.setattr(semgrep_helpers, "CUSTOM_RULES_PATH", dir / "custom_rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "DISABLED_CONFIG_PATH", dir / "disabled_config.json")
    monkeypatch.setattr(Path, "mkdir", _fail)

    semgrep_helpers.bootstrap_rules()

    assert not (dir / "custom_rules.yaml").exists()
    assert not (dir / "disabled_config.json").exists()


def test_write_writable(monkeypatch, tmp_path):
    dir = tmp_path / "writable-home" / ".zetatech" / "semgrep"
    monkeypatch.setattr(semgrep_helpers, "SEMGREP_STATE_DIR", dir)
    monkeypatch.setattr(semgrep_helpers, "CUSTOM_RULES_PATH", dir / "custom_rules.yaml")

    save_doc({"rules": [{"id": "demo-rule"}]})

    assert (dir / "custom_rules.yaml").exists()
    assert semgrep_helpers.load_doc()["rules"] == [{"id": "demo-rule"}]


def test_bootstrap_legacy(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: migrated-rule\n    message: Migrated\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/semgrep/rules")

    assert res.status_code == 200
    body = res.json()
    assert [rule["id"] for rule in body["custom_rules"]] == ["migrated-rule"]
    assert (dir / "custom_rules.yaml").exists()
    assert "migrated-rule" in (dir / "custom_rules.yaml").read_text(encoding="utf-8")


def test_migrate_disabled(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    canon = dir / "custom_rules.yaml"
    canon.parent.mkdir(parents=True, exist_ok=True)
    canon.write_text(
        "rules:\n  - id: canonical-rule\n    message: Canonical\n    severity: WARNING\n    pattern: exec($X)\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "legacy-disabled.json"
    cfg.write_text(json.dumps({"rules": ["canonical-rule"], "rulesets": [], "extra_rulesets": []}), encoding="utf-8")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_DISABLED_CONFIG_PATH", cfg)

    semgrep_helpers.bootstrap_rules()

    assert semgrep_helpers.load_doc()["rules"][0]["id"] == "canonical-rule"
    assert json.loads((dir / "disabled_config.json").read_text(encoding="utf-8"))["rules"] == ["canonical-rule"]


def test_load_doc(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: legacy-doc-rule\n    message: Legacy\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    doc = semgrep_helpers.load_doc()

    assert doc["rules"][0]["id"] == "legacy-doc-rule"
    assert (dir / "custom_rules.yaml").exists()


def test_load_rules(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: legacy-list-rule\n    message: Legacy\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    rules = semgrep_helpers.load_custom_rules()

    assert [rule["id"] for rule in rules] == ["legacy-list-rule"]


def test_bootstrap_idempotent(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    canon = dir / "custom_rules.yaml"
    canon.parent.mkdir(parents=True, exist_ok=True)
    canon.write_text(
        "rules:\n  - id: keep-me\n    message: Canonical\n    severity: WARNING\n    pattern: exec($X)\n",
        encoding="utf-8",
    )
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: old-rule\n    message: Old\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    semgrep_helpers.bootstrap_rules()

    text = canon.read_text(encoding="utf-8")
    assert "keep-me" in text
    assert "old-rule" not in text


def test_empty_rules(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", tmp_path / "missing-legacy-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/semgrep/rules")

    assert res.status_code == 200
    assert res.json()["custom_rules"] == []


def test_package_fallback(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    pkg = tmp_path / "package-semgrep-results" / "custom_rules.yaml"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text(
        "rules:\n  - id: package-rule\n    message: Package\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", tmp_path / "missing-legacy-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", pkg)

    semgrep_helpers.bootstrap_rules()

    assert (dir / "custom_rules.yaml").exists()
    assert "package-rule" in (dir / "custom_rules.yaml").read_text(encoding="utf-8")


def test_root_priority(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    root = tmp_path / "root-custom-rules.yaml"
    root.write_text(
        "rules:\n  - id: root-rule\n    message: Root\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: legacy-rule\n    message: Legacy\n    severity: WARNING\n    pattern: exec($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", root)
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    semgrep_helpers.bootstrap_rules()

    text = (dir / "custom_rules.yaml").read_text(encoding="utf-8")
    assert "root-rule" in text
    assert "legacy-rule" not in text


def test_keep_disabled(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: disabled-after-bootstrap\n    message: Legacy\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "legacy-disabled.json"
    cfg.write_text(json.dumps({"rules": ["disabled-after-bootstrap"], "rulesets": [], "extra_rulesets": []}), encoding="utf-8")
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_DISABLED_CONFIG_PATH", cfg)

    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/semgrep/rules")

    assert res.status_code == 200
    rule = res.json()["custom_rules"][0]
    assert rule["id"] == "disabled-after-bootstrap"
    assert rule["enabled"] is False
    assert json.loads((dir / "disabled_config.json").read_text(encoding="utf-8"))["rules"] == ["disabled-after-bootstrap"]


def test_missing_doc(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", tmp_path / "missing-legacy.yaml")
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package.yaml")

    assert semgrep_helpers.load_doc() == {"rules": []}


def test_empty_legacy(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("rules: []\n", encoding="utf-8")
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    semgrep_helpers.bootstrap_rules()

    assert not (dir / "custom_rules.yaml").exists()


def test_missing_disabled(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    monkeypatch.setattr(semgrep_helpers, "LEGACY_DISABLED_CONFIG_PATH", tmp_path / "missing-disabled.json")

    semgrep_helpers.bootstrap_rules()

    assert not (dir / "disabled_config.json").exists()


def test_preserve_disabled(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    path = dir / "disabled_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rules": ["keep-disabled"], "rulesets": [], "extra_rulesets": []}), encoding="utf-8")
    cfg = tmp_path / "legacy-disabled.json"
    cfg.write_text(json.dumps({"rules": ["old-disabled"], "rulesets": [], "extra_rulesets": []}), encoding="utf-8")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_DISABLED_CONFIG_PATH", cfg)

    semgrep_helpers.bootstrap_rules()

    assert json.loads(path.read_text(encoding="utf-8"))["rules"] == ["keep-disabled"]


def test_endpoint_bootstrap(monkeypatch, tmp_path):
    dir = _patch_semgrep_state(monkeypatch, tmp_path)
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: endpoint-bootstrap\n    message: Legacy\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    client = _client(monkeypatch, tmp_path)
    client.get("/api/semgrep/rules")

    assert (dir / "custom_rules.yaml").exists()
    assert "endpoint-bootstrap" in (dir / "custom_rules.yaml").read_text(encoding="utf-8")


def test_custom_flag(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    save_doc({"rules": [{"id": "demo-rule", "message": "Demo", "severity": "WARNING", "pattern": "eval($X)"}]})

    rules = semgrep_helpers.load_custom_rules()

    assert rules[0]["is_custom"] is True


def test_patterns_extract(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    save_doc({"rules": [{"id": "demo-rule", "message": "Demo", "severity": "WARNING", "patterns": [{"pattern": "eval($X)"}]}]})

    rules = semgrep_helpers.load_custom_rules()

    assert rules[0]["pattern"] == "eval($X)"


def test_default_enabled(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    legacy = tmp_path / "legacy-semgrep-results" / "custom_rules.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "rules:\n  - id: bootstrapped-enabled\n    message: Legacy\n    severity: WARNING\n    pattern: eval($X)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(semgrep_helpers, "ROOT_CUSTOM_RULES_PATH", tmp_path / "missing-root-custom-rules.yaml")
    monkeypatch.setattr(semgrep_helpers, "LEGACY_CUSTOM_RULES_PATH", legacy)
    monkeypatch.setattr(semgrep_helpers, "PACKAGE_CUSTOM_RULES_PATH", tmp_path / "missing-package-custom-rules.yaml")

    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/semgrep/rules")

    assert res.json()["custom_rules"][0]["enabled"] is True
