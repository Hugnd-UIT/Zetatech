import shutil
from pathlib import Path


def cleanup_run_workspace(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)


def ensure_within_workspace(root: Path, path: Path) -> Path:
    base = root.resolve()
    target = path if path.is_absolute() else base / path
    resolved = target.resolve(strict=False)

    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError("candidate path is outside workspace") from exc

    return resolved
