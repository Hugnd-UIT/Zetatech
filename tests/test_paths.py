from pathlib import Path

from agents.repos import AIRepository
from database.models import DEFAULT_DB_PATH, get_db_path
from database.repos import ScanRepository
from logger import get_log_file
from paths import CANONICAL_RUNTIME_ROOT, resolve_runtime_paths
from scanners.semgrep import DEFAULT_SEMGREP_OUTPUT_DIR
from core.routers.semgrep import helper as semgrep_helpers
from core.routers.semgrep.task import SEMGREP_OUTPUTS_DIR


def test_canonical_root():
    assert CANONICAL_RUNTIME_ROOT == Path("/home/appuser/.zetatech")


def test_runtime_children():
    paths = resolve_runtime_paths()

    assert paths.root == Path("/home/appuser/.zetatech")
    assert paths.db_file == paths.root / "zetatech.db"
    assert paths.logs_dir == paths.root / "logs"
    assert paths.plugins_dir == paths.root / "plugins"
    assert paths.semgrep_dir == paths.root / "semgrep"
    assert paths.semgrep_outputs_dir == paths.root / "semgrep-results"
    assert paths.approvals_dir == paths.root / "approvals"


def test_runtime_cached():
    first = resolve_runtime_paths()
    second = resolve_runtime_paths()

    assert first is second
    assert first == second


def test_semgrep_paths():
    paths = resolve_runtime_paths()

    assert semgrep_helpers.SEMGREP_STATE_DIR == paths.semgrep_dir
    assert semgrep_helpers.SEM_RESULTS_DIR == paths.semgrep_outputs_dir
    assert semgrep_helpers.CUSTOM_RULES_PATH == paths.semgrep_dir / "custom_rules.yaml"
    assert semgrep_helpers.DISABLED_CONFIG_PATH == paths.semgrep_dir / "disabled_config.json"
    assert SEMGREP_OUTPUTS_DIR == paths.semgrep_outputs_dir
    assert DEFAULT_SEMGREP_OUTPUT_DIR == paths.semgrep_outputs_dir


def test_db_default(monkeypatch):
    monkeypatch.delenv("ZETATECH_DB", raising=False)

    assert DEFAULT_DB_PATH == resolve_runtime_paths().db_file
    assert get_db_path() == resolve_runtime_paths().db_file


def test_log_path():
    assert get_log_file() == resolve_runtime_paths().logs_dir / "zetatech.log"


def test_scan_repo_path(tmp_path):
    db = tmp_path / "runtime-root" / "zetatech.db"
    repo = ScanRepository(db_path=db)

    assert repo.db_path == db
    assert db.exists()


def test_ai_repo_path(tmp_path):
    db = tmp_path / "runtime-root" / "zetatech.db"
    repo = AIRepository(db_path=db)

    assert repo.db_path == db
    assert db.exists()
