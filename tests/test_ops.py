from pathlib import Path

import yaml

from infrastructure.workflow_validation import (
    CANONICAL_NODE_TEST_COMMAND,
    SMOKE_REQUIRED_UPDATE_FIELDS,
    ValidationWorkflowInputs,
    normalize_workflow_inputs,
    runtime_contract_output,
    validated_image_ref,
)


ROOT = Path(__file__).resolve().parents[1]


def _wf(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def test_normalize_inputs():
    inp = normalize_workflow_inputs(
        image_version=" 0.1.3 ",
        image_tag=" v0.1.3 ",
        image_build=" sha-123 ",
        run_smoke=True,
        release_mode=False,
    )

    assert inp == ValidationWorkflowInputs(
        image_version="0.1.3",
        image_tag="v0.1.3",
        image_build="sha-123",
        run_smoke=True,
        release_mode=False,
    )


def test_required_fields():
    assert SMOKE_REQUIRED_UPDATE_FIELDS == (
        "current_version",
        "current_tag",
        "runtime_status",
        "status",
        "update_available",
        "manual_update_required",
    )


def test_contract_output():
    assert runtime_contract_output(
        ValidationWorkflowInputs("ci", "main", "sha-1", True, False)
    ) == "true"
    assert runtime_contract_output(
        ValidationWorkflowInputs("ci", "main", "sha-1", False, False)
    ) == "false"


def test_image_ref():
    assert validated_image_ref(
        ValidationWorkflowInputs("ci", "main", "sha-1", True, False)
    ) == "zetatech:ci-validation"
    assert validated_image_ref(
        ValidationWorkflowInputs("0.1.3", "v0.1.3", "sha-1", True, True)
    ) == "zetatech:release-validation"


def test_ops_chain():
    wf = _wf("ops.yml")
    call = wf[True]["workflow_call"]
    inp = call["inputs"]
    out = call["outputs"]
    job = wf["jobs"]["validate"]
    steps = job["steps"]
    names = [step["name"] for step in steps]

    assert set(inp) == {
        "version",
        "tag",
        "build",
        "test",
        "release",
    }
    assert set(out) == {"image", "result"}
    assert names == [
        "Checkout repository",
        "Resolve image reference",
        "Set up Python",
        "Set up Node",
        "Install Python dependencies",
        "Install Node dependencies",
        "Build Node",
        "Run Node tests",
        "Run Python tests",
        "Build image",
        "Test image",
        "Emit smoke result for callers",
    ]
    assert steps[7]["run"] == CANONICAL_NODE_TEST_COMMAND


def test_node_cmd():
    wf = _wf("ops.yml")
    step = wf["jobs"]["validate"]["steps"][7]

    assert step["name"] == "Run Node tests"
    assert step["run"] == CANONICAL_NODE_TEST_COMMAND


def test_package_script():
    pkg = yaml.safe_load((ROOT / "agents" / "nodejs" / "package.json").read_text(encoding="utf-8"))

    assert pkg["scripts"]["test"] == "node --import tsx --test --test-force-exit test/nodejs.test.ts"
    assert CANONICAL_NODE_TEST_COMMAND == "npm --prefix agents/nodejs run test"
    assert "--test-force-exit" in pkg["scripts"]["test"]


def test_ci_triggers():
    wf = _wf("ci.yml")
    trig = wf[True]

    assert trig == {
        "pull_request": {"branches": ["main"]},
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }


def test_ci_inputs():
    wf = _wf("ci.yml")
    job = wf["jobs"]["validate"]

    assert job["uses"] == "./.github/workflows/ops.yml"
    assert job["with"] == {
        "version": "ci",
        "tag": "${{ github.ref_name }}",
        "build": "${{ github.sha }}",
        "test": True,
        "release": False,
    }


def test_ci_thin():
    wf = _wf("ci.yml")
    job = wf["jobs"]["validate"]

    assert set(wf["jobs"]) == {"validate"}
    assert "steps" not in job
    assert set(job) == {"uses", "with"}


def test_smoke_health():
    wf = _wf("ops.yml")
    step = wf["jobs"]["validate"]["steps"][-2]
    run = step["run"]

    assert "wait http://127.0.0.1:18080/health" in run
    assert "curl --fail --silent http://127.0.0.1:18080/api/system/update >/tmp/zetatech-system-update.json" in run
    assert run.index("wait http://127.0.0.1:18080/health") < run.index(
        "curl --fail --silent http://127.0.0.1:18080/api/system/update >/tmp/zetatech-system-update.json"
    )


def test_smoke_mounts():
    wf = _wf("ops.yml")
    step = wf["jobs"]["validate"]["steps"][-2]
    run = step["run"]

    assert 'docker run -d --name "$name" -p 18080:8080 \\' in run
    assert '-v zetatech-data:/home/appuser/.zetatech \\' in run
    assert '-v zetatech-plugin:/app/Plugins \\' in run
    assert '-v zetatech-semgrep:/app/semgrep_results \\' in run
    assert "docker volume create zetatech-data" in run
    assert "docker volume create zetatech-plugin" in run
    assert "docker volume create zetatech-semgrep" in run


def test_smoke_writable():
    wf = _wf("ops.yml")
    step = wf["jobs"]["validate"]["steps"][-2]
    run = step["run"]

    assert "check()" in run
    assert "check zetatech-smoke" in run
    assert "check zetatech-smoke-recreated" in run
    assert "touch /home/appuser/.zetatech/write-test" in run
    assert "touch /app/Plugins/write-test" in run
    assert "touch /app/semgrep_results/write-test" in run
    assert run.index("check zetatech-smoke") < run.index(
        "curl --fail --silent http://127.0.0.1:18080/api/system/update >/tmp/zetatech-system-update.json"
    )
    assert run.index("check zetatech-smoke-recreated") < run.index(
        "curl --fail --silent http://127.0.0.1:18080/api/system/update >/tmp/zetatech-system-update-recreated.json"
    )


def test_smoke_persist():
    wf = _wf("ops.yml")
    step = wf["jobs"]["validate"]["steps"][-2]
    run = step["run"]

    assert "docker exec zetatech-smoke python - <<'PY'" in run
    assert "docker restart zetatech-smoke >/dev/null" in run
    assert "docker rm -f zetatech-smoke >/dev/null" in run
    assert "start zetatech-smoke-recreated" in run
    assert "curl --fail --silent http://127.0.0.1:18080/api/system/update >/tmp/zetatech-system-update-recreated.json" in run
    assert "persisted across restart and recreate" in run
    assert "Path('/home/appuser/.zetatech/acceptance/persistence.txt')" in run


def test_smoke_clean():
    wf = _wf("ops.yml")
    step = wf["jobs"]["validate"]["steps"][-2]
    run = step["run"]

    assert "docker rm -f zetatech-smoke zetatech-smoke-recreated >/dev/null 2>&1 || true" in run
    assert "docker volume rm zetatech-data zetatech-plugin zetatech-semgrep >/dev/null 2>&1 || true" in run
    assert "trap clean EXIT" in run
    assert "docker logs zetatech-smoke || true" in run
    assert "docker logs zetatech-smoke-recreated || true" in run
    assert "clean" in run
    assert "trap - EXIT" in run


def test_smoke_update():
    wf = _wf("ops.yml")
    step = wf["jobs"]["validate"]["steps"][-2]
    run = step["run"]

    assert "for name in ('/tmp/zetatech-system-update.json', '/tmp/zetatech-system-update-recreated.json'):" in run
    assert "missing = required - payload.keys()" in run
    assert "manual_update_required" in run
    assert "runtime_status" in run
    assert "current_tag" in run
    assert "current_version" in run
    assert "update_available" in run
    assert "status" in run
    assert "Missing keys from {name}: {sorted(missing)}" in run
    assert run.index("/tmp/zetatech-system-update-recreated.json") > run.index(
        "/tmp/zetatech-system-update.json"
    )


def test_docker_health():
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6" in df
    assert "http://127.0.0.1:8080/health" in df


def test_public_health():
    txt = (ROOT / "core" / "app.py").read_text(encoding="utf-8")

    assert '"/health"' in txt
    assert '@app.get("/health")' in txt
    assert 'JSONResponse({"status": "ok"})' in txt


def test_health_ok(monkeypatch):
    monkeypatch.setattr(
        "core.app.release.manager.get_status",
        lambda force=False: {"status": "ok"},
    )
    monkeypatch.setattr(
        "core.app.ensure_db_dir",
        lambda path=None: Path("/Users/Hugnd-UIT/Desktop/zetatech/.pytest-task05-workflow.db"),
    )
    from fastapi.testclient import TestClient
    from core.app import create_app

    cli = TestClient(create_app(), base_url="http://localhost")
    res = cli.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    assert res.headers["content-type"].startswith("application/json")
    assert res.request.url.path == "/health"
    assert res.request.headers["host"] == "localhost"
    assert res.request.method == "GET"
    assert res.request.url.scheme == "http"
    assert str(res.request.url).startswith("http://localhost/health")
    assert res.request.headers["accept"] == "*/*"
    assert res.request.headers["connection"] == "keep-alive"
    assert res.request.headers["user-agent"]
    assert cli.headers.get("host", "") == ""
