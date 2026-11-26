import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterator, List


TIMEOUT = 120
RUNNER = Path(__file__).resolve().parent / "nodejs" / "dist" / "index.js"


class BridgeError(RuntimeError):
    pass


class BridgeTimeoutError(BridgeError):
    pass


class BridgeProtocolError(BridgeError):
    pass


def _check_env() -> None:
    if shutil.which("node") is None:
        raise BridgeError("AI agent bridge requires Node.js in the runtime environment.")
    if not RUNNER.exists():
        raise BridgeError("AI agent bridge runner is missing. Build agents/nodejs before use.")


def _parse_line(raw: str) -> Dict[str, Any]:
    line = raw.strip()
    if not line:
        return {}
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise BridgeProtocolError("AI agent bridge returned malformed output.") from exc


def _build_child_env(payload: Dict[str, Any]) -> Dict[str, str]:
    env = os.environ.copy()
    env.pop("ZETATECH_AI_API_KEY", None)

    extra = payload.get("runtimeEnv") or {}
    if isinstance(extra, dict):
        for key, val in extra.items():
            if val is None:
                env.pop(str(key), None)
            else:
                env[str(key)] = str(val)
    return env


def _strip_env(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(payload)
    safe.pop("runtimeEnv", None)
    return safe


def run_agent_bridge_stream(
    payload: Dict[str, Any],
    timeout_seconds: int = TIMEOUT,
) -> Iterator[Dict[str, Any]]:
    _check_env()
    env = _build_child_env(payload)
    safe = _strip_env(payload)

    try:
        proc = subprocess.Popen(
            ["node", str(RUNNER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except OSError as exc:
        raise BridgeError(f"AI agent bridge failed to start: {exc}") from exc

    try:
        if proc.stdin is None or proc.stdout is None:
            raise BridgeError("AI agent bridge failed to initialize stdio pipes.")

        proc.stdin.write(json.dumps(safe))
        proc.stdin.close()

        done = False
        fail_msg = ""
        for raw in proc.stdout:
            event = _parse_line(raw)
            if not event:
                continue
            kind = str(event.get("type") or "")
            if kind == "run_completed":
                done = True
            elif kind == "run_failed":
                data = event.get("data") or {}
                if isinstance(data, dict):
                    fail_msg = str(data.get("message") or "").strip()
            yield event

        try:
            code = proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.wait(timeout=5)
            raise BridgeTimeoutError("AI agent bridge timed out.") from exc

        err = (proc.stderr.read() if proc.stderr is not None else "").strip()
        if code != 0:
            raise BridgeError(fail_msg or err or "AI agent bridge failed.")
        if not done:
            raise BridgeProtocolError(fail_msg or "AI agent bridge did not return a completion event.")
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()


def run_agent_bridge(
    payload: Dict[str, Any],
    timeout_seconds: int = TIMEOUT,
) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}
    output = ""

    for event in run_agent_bridge_stream(payload, timeout_seconds=timeout_seconds):
        kind = event.get("type")
        data = event.get("data") or {}
        if kind == "run_completed":
            if isinstance(data, dict):
                result = data
                output = str(data.get("content") or data.get("output") or "")
            else:
                output = str(data)
                result = {"content": output}
            continue
        events.append(event)

    return {
        "output": output,
        "events": events,
        "result": result,
    }
