from pathlib import Path

import pytest

from agents.tools import build_tool_policy
from agents.workspace import ensure_within_workspace


def test_inside_relative(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    inside = root / "source" / "plugin.php"
    inside.parent.mkdir()
    inside.write_text("<?php\n", encoding="utf-8")

    assert ensure_within_workspace(root, inside) == inside.resolve()
    assert ensure_within_workspace(root, Path("source/plugin.php")) == inside.resolve()


def test_reject_outside(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    out = tmp_path / "outside.php"
    out.write_text("<?php\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside workspace"):
        ensure_within_workspace(root, out)


def test_reject_symlink(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    out_dir = tmp_path / "outside"
    out_dir.mkdir()
    out_file = out_dir / "secret.php"
    out_file.write_text("<?php\n", encoding="utf-8")

    link = root / "source" / "linked"
    link.parent.mkdir()
    link.symlink_to(out_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="outside workspace"):
        ensure_within_workspace(root, link / "secret.php")


def test_reject_traversal(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(ValueError, match="outside workspace"):
        ensure_within_workspace(root, Path("../outside/missing.php"))

    with pytest.raises(ValueError, match="outside workspace"):
        ensure_within_workspace(root, Path("source/../../outside/missing.php"))


def test_tool_policy(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    pol = build_tool_policy(root)

    assert pol == {
        "workspace_root": str(root.resolve()),
        "enforcement": "handled_by_open_multi_agent",
    }
