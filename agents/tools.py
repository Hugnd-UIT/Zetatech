from pathlib import Path


def build_tool_policy(root: Path) -> dict[str, object]:
    return {
        "workspace_root": str(root.resolve()),
        "enforcement": "handled_by_open_multi_agent",
    }
