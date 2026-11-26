"""
Zetatech Theme Scanner

Theme fetching and analysis from WordPress.org API.
"""

import logging
import time
import threading
from typing import List, Dict, Any, Optional, Callable
from config import RISKY_TAGS
from infrastructure.http_client import get_session
from utils.date_utils import calculate_days_ago

logger = logging.getLogger("zetatech.scanners.theme")


class ThemeScanner:
    """WordPress Theme Scanner."""

    def __init__(
        self,
        pages: int = 5,
        limit: int = 0,
        sort: str = "popular",
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ):
        self.pages = pages
        self.limit = limit
        self.sort = sort
        self.on_result = on_result
        self.on_progress = on_progress
        self.results: List[Dict[str, Any]] = []
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def fetch_themes(self, page: int = 1, max_retries: int = 3) -> List[Dict[str, Any]]:
        """Fetch themes from WordPress.org API."""
        session = get_session()
        url = "https://api.wordpress.org/themes/info/1.2/"
        params = {
            "action": "query_themes",
            "request[browse]": self.sort,
            "request[page]": page,
            "request[per_page]": 100,
            "request[fields][description]": True,
            "request[fields][downloaded]": True,
            "request[fields][last_updated]": True,
            "request[fields][download_link]": True,
            "request[fields][version]": True,
            "request[fields][author]": True,
            "request[fields][tags]": True,
            "request[fields][screenshot_url]": True,
        }

        for attempt in range(max_retries):
            if self.stop_event.is_set():
                return []
            try:
                resp = session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("themes", []) if data else []
                elif resp.status_code == 429:
                    wait = 5 * (attempt + 1)
                    logger.warning("Theme API rate limited; waiting before retry", extra={"wait_time_seconds": wait, "page": page})
                    time.sleep(wait)
                    continue
            except Exception as exc:
                logger.warning("Theme API request failed", exc_info=exc)
                time.sleep(2)
                continue
        return []

    def process_theme(self, theme: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single theme and return analysis."""
        name = theme.get("name", "Unknown")
        slug = theme.get("slug", "")
        version = theme.get("version", "?")
        downloads = theme.get("downloaded", 0)
        updated = theme.get("last_updated", "")
        author = theme.get("author", "Unknown")

        days = calculate_days_ago(updated)


        tags = list(theme.get("tags", {}).keys())
        desc = theme.get("description", "").lower()
        matched = [tag for tag in RISKY_TAGS if tag in tags or tag in desc]


        score = 0
        if days > 730:
            score += 40
        elif days > 365:
            score += 25
        if matched:
            score += 20
        if downloads < 1000:
            score += 10


        level = (
            "HIGH" if score >= 40 else ("MEDIUM" if score >= 20 else "LOW")
        )

        return {
            "name": name,
            "slug": slug,
            "version": version,
            "downloads": downloads,
            "days_since_update": days,
            "author": author,
            "risk_score": score,
            "risk_level": level,
            "matched_tags": matched,
            "download_link": theme.get("download_link", ""),
            "wp_org_link": f"https://wordpress.org/themes/{slug}/",
            "trac_link": f"https://themes.trac.wordpress.org/log/{slug}/",
            "wpscan_link": f"https://wpscan.com/theme/{slug}",
            "cve_search_link": f"https://cve.mitre.org/cgi-bin/cvekey.cgi?keyword={slug}",
            "screenshot_url": theme.get("screenshot_url", ""),
        }

    def scan(self) -> List[Dict[str, Any]]:
        """Run the theme scan."""
        found = 0

        for page in range(1, self.pages + 1):
            if self.stop_event.is_set():
                break
            if self.limit > 0 and found >= self.limit:
                break

            themes = self.fetch_themes(page)

            if not themes:
                break

            for theme in themes:
                if self.stop_event.is_set():
                    break
                if self.limit > 0 and found >= self.limit:
                    break

                result = self.process_theme(theme)
                found += 1
                self.results.append(result)

                if self.on_result:
                    self.on_result(result)

            if self.on_progress:
                self.on_progress(page, self.pages)

            if self.stop_event.is_set():
                break
            time.sleep(0.5)

        return self.results
