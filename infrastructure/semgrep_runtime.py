import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence


def _works(cmd: Sequence[str]) -> bool:
    try:
        res = subprocess.run(
            [*cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


@lru_cache(maxsize=1)
def get_semgrep_command() -> Optional[List[str]]:
    found = shutil.which("semgrep")
    root = Path(__file__).resolve().parents[1]
    venv = root / ".venv" / "bin" / "semgrep"

    items = [
        ["semgrep"],
        [sys.executable, "-m", "semgrep"],
    ]

    if found:
        items.append([found])

    if venv.exists():
        items.append([str(venv)])

    brew = "/opt/homebrew/bin/semgrep"
    if Path(brew).exists():
        items.append([brew])

    seen: set[tuple[str, ...]] = set()
    for item in items:
        key = tuple(item)
        if key in seen:
            continue
        seen.add(key)
        if _works(item):
            return list(item)

    return None


def is_semgrep_available() -> bool:
    return get_semgrep_command() is not None


def semgrep_install_hint() -> str:
    return (
        "Install dependencies with `pip install -r requirements.txt` "
        "to include Semgrep."
    )
