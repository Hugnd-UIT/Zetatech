"""
Zetatech Theme Downloader

Download and extract themes for analysis.
"""

from pathlib import Path

from downloaders.plugin import PluginDownloader
from paths import resolve_runtime_paths


class ThemeDownloader(PluginDownloader):
    """Theme downloader and extractor reusing the hardened archive flow."""

    def __init__(self, base_dir: str | Path | None = None):
        root = resolve_runtime_paths().plugins_dir
        self.base_dir = Path(base_dir) if base_dir is not None else root
        self.plugins_dir = self.base_dir / "Themes"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
