import json

import yaml
from fastapi import BackgroundTasks

from paths import resolve_runtime_paths
from core.routers.semgrep import task as semgrep_task_service

from database.models import get_db, init_db
from database.repos import ScanRepository
from scanners.semgrep import SemgrepScanner
from core.routers.semgrep.service import start_scan


class _ScanRequest:
    def __init__(self, slug: str, download_url: str):
        self.slug = slug
        self.download_url = download_url


class _RecordingRepo:
    def __init__(self, version=None):
        self.version = version
        self.created = []

    def get_catalog_latest_version(self, slug, is_theme=False):
        assert slug == "akismet"
        assert is_theme is False
        return self.version

    def create_semgrep_scan(self, slug, version=None):
        self.created.append((slug, version))
        return 41


def test_catalog_version():
    repo = _RecordingRepo(version="5.3.1")
    bg = BackgroundTasks()

    res = start_scan(
        repo=repo,
        scan_request=_ScanRequest(
            slug="akismet",
            download_url="https://downloads.wordpress.org/plugin/akismet.5.3.1.zip",
        ),
        background_tasks=bg,
    )

    assert res == {"success": True, "scan_id": 41, "status": "pending"}
    assert repo.created == [("akismet", "5.3.1")]
    assert len(bg.tasks) == 1


def test_fallback_latest():
    repo = _RecordingRepo(version=None)
    bg = BackgroundTasks()

    start_scan(
        repo=repo,
        scan_request=_ScanRequest(
            slug="akismet",
            download_url="https://downloads.wordpress.org/plugin/akismet.latest.zip",
        ),
        background_tasks=bg,
    )

    assert repo.created == [("akismet", "latest")]


def test_lookup_version(tmp_path):
    db = tmp_path / "semgrep_version_lookup.db"
    init_db(db)
    repo = ScanRepository(db_path=db)

    with get_db(db) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO plugin_catalog (
                slug, is_theme, first_seen_session_id, last_seen_session_id,
                first_seen_at, last_seen_at, seen_count,
                latest_version, latest_score, max_score_ever,
                latest_installations, latest_days_since_update, latest_semgrep_findings
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("akismet", 0, 1, 1, 1, "5.3.1", 0, 0, 0, 0, None),
        )
        conn.commit()

    assert repo.get_catalog_latest_version("akismet") == "5.3.1"
    assert repo.get_catalog_latest_version("missing-plugin") is None


def test_output_dir(monkeypatch, tmp_path):
    paths = resolve_runtime_paths()
    root = tmp_path / "runtime-root" / "semgrep-results"
    monkeypatch.setattr(semgrep_task_service, "SEMGREP_OUTPUTS_DIR", root)

    out = semgrep_task_service.prepare_out(slug="akismet", scan_id=41)

    assert out == root / "akismet_41"
    assert out.exists()
    assert paths.semgrep_outputs_dir.name == "semgrep-results"


def test_filter_rules(tmp_path):
    out_dir = tmp_path / "semgrep-output"
    out_dir.mkdir(parents=True, exist_ok=True)

    rules = {
        "rules": [
            {"id": "enabled-rule", "pattern": "eval($X)", "message": "Enabled", "languages": ["php"], "severity": "ERROR"},
            {"id": "disabled-rule", "pattern": "exec($X)", "message": "Disabled", "languages": ["php"], "severity": "WARNING"},
        ]
    }
    with open(out_dir / "custom_rules.yaml", "w", encoding="utf-8") as fh:
        yaml.dump(rules, fh, sort_keys=False)
    with open(out_dir / "disabled_rules.json", "w", encoding="utf-8") as fh:
        fh.write('["disabled-rule"]')

    scanner = SemgrepScanner(
        output_dir=str(out_dir),
        use_registry_rules=True,
        registry_rulesets=["php-security", "php-security", "p/php", "security-audit"],
    )

    args = scanner._cfg_args()

    assert args[0] == "--config"
    path = args[1]
    assert path.endswith("active_custom_rules.yaml")

    with open(path, "r", encoding="utf-8") as fh:
        filtered = yaml.safe_load(fh)

    assert [rule["id"] for rule in filtered["rules"]] == ["enabled-rule"]
    assert args == [
        "--config",
        path,
        "--config",
        "p/php",
        "--config",
        "p/security-audit",
    ]


def test_json_errors(tmp_path):
    out_dir = tmp_path / "semgrep-error-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    file = out_dir / "akismet_results.json"
    file.write_text(
        '{"results": [], "errors": [{"message": "Invalid rule schema"}]}',
        encoding="utf-8",
    )

    scanner = SemgrepScanner(output_dir=str(out_dir))
    res = scanner._parse_output(file, "")

    assert res.success is False
    assert res.findings == []
    assert res.errors == ["Invalid rule schema"]


def test_partial_syntax(tmp_path):
    out_dir = tmp_path / "semgrep-partial-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    file = out_dir / "plugin_results.json"
    file.write_text(
        json.dumps(
            {
                "results": [{"check_id": "rule-1", "path": "test.php"}],
                "errors": [
                    {
                        "message": "Syntax error at line /app/Plugins/video-gallery-block/source/public/js/plyr.js:1: `?.5:.0625` was unexpected"
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    scanner = SemgrepScanner(output_dir=str(out_dir))
    res = scanner._parse_output(file, "scan summary on stderr")

    assert res.success is True
    assert len(res.findings) == 1
    assert res.errors == [
        "Syntax error at line /app/Plugins/video-gallery-block/source/public/js/plyr.js:1: `?.5:.0625` was unexpected"
    ]


def test_rule_timeouts(tmp_path):
    out_dir = tmp_path / "semgrep-rule-timeout-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    file = out_dir / "plugin_results.json"
    file.write_text(
        json.dumps(
            {
                "results": [{"check_id": "rule-1", "path": "test.php"}],
                "errors": [
                    {
                        "message": "Timeout when running javascript.aws-lambda.security.tainted-html-response.tainted-html-response on /app/Plugins/example/source/file.js:"
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    scanner = SemgrepScanner(output_dir=str(out_dir))
    res = scanner._parse_output(file, "scan summary on stderr")

    assert res.success is True
    assert len(res.findings) == 1
    assert res.errors == [
        "Timeout when running javascript.aws-lambda.security.tainted-html-response.tainted-html-response on /app/Plugins/example/source/file.js:"
    ]


def test_fatal_syntax(tmp_path):
    out_dir = tmp_path / "semgrep-empty-partial-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    file = out_dir / "plugin_results.json"
    file.write_text(
        json.dumps(
            {
                "results": [],
                "errors": [
                    {
                        "message": "Syntax error at line /app/Plugins/video-gallery-block/source/public/js/plyr.js:1: `?.5:.0625` was unexpected"
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    scanner = SemgrepScanner(output_dir=str(out_dir))
    res = scanner._parse_output(file, "scan summary on stderr")

    assert res.success is False
    assert res.findings == []
    assert res.errors == [
        "Syntax error at line /app/Plugins/video-gallery-block/source/public/js/plyr.js:1: `?.5:.0625` was unexpected",
        "stderr: scan summary on stderr",
    ]


def test_partial_timeout(tmp_path):
    out_dir = tmp_path / "semgrep-timeout-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    file = out_dir / "plugin_results.json"
    file.write_text(
        json.dumps(
            {
                "results": [{"check_id": "rule-1", "path": "test.php"}],
                "errors": [
                    {
                        "message": "Syntax error at line /app/Plugins/big-plugin/source/file.php:10: `$foo` was unexpected"
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    scanner = SemgrepScanner(output_dir=str(out_dir))
    res = scanner._parse_proc(
        output_file=file,
        returncode=1,
        stderr="timed out after long scan",
        timed_out=True,
    )

    assert res.success is True
    assert res.partial is True
    assert len(res.findings) == 1
    assert res.errors == [
        "Scan timeout",
        "Syntax error at line /app/Plugins/big-plugin/source/file.php:10: `$foo` was unexpected",
    ]


def test_failed_timeout(tmp_path):
    out_dir = tmp_path / "semgrep-timeout-empty-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    file = out_dir / "plugin_results.json"

    scanner = SemgrepScanner(output_dir=str(out_dir))
    res = scanner._parse_proc(
        output_file=file,
        returncode=1,
        stderr="timed out after long scan",
        timed_out=True,
    )

    assert res.success is False
    assert res.partial is False
    assert res.findings == []
    assert res.errors == ["Semgrep failed (code 1): timed out after long scan"]


def test_skip_invalid(tmp_path, monkeypatch):
    out_dir = tmp_path / "semgrep-invalid-custom-output"
    out_dir.mkdir(parents=True, exist_ok=True)

    rules = {
        "rules": [
            {"id": "valid-rule", "pattern": "eval(...)", "message": "valid", "languages": ["php"], "severity": "ERROR"},
            {"id": "invalid-rule", "pattern": "echo $_GET[$X]", "message": "invalid", "languages": ["php"], "severity": "ERROR"},
        ]
    }
    with open(out_dir / "custom_rules.yaml", "w", encoding="utf-8") as fh:
        yaml.dump(rules, fh, sort_keys=False)

    scanner = SemgrepScanner(output_dir=str(out_dir), use_registry_rules=False)

    def _valid(rule):
        return rule.get("id") == "valid-rule"

    monkeypatch.setattr(scanner, "_valid_rule", _valid)

    path = scanner._filter_rules()

    assert path is not None
    with open(path, "r", encoding="utf-8") as fh:
        filtered = yaml.safe_load(fh)
    assert [rule["id"] for rule in filtered["rules"]] == ["valid-rule"]

    log = out_dir / "invalid_custom_rules.json"
    assert log.exists()
    assert 'invalid-rule' in log.read_text(encoding='utf-8')
