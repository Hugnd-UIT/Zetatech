from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Optional

import requests

from analyzers.risk import label_risk
from analyzers.score import score_vps
from config import (
    FEATURE_KEYWORDS,
    RISKY_TAGS,
    SECURITY_KEYWORDS,
    USER_FACING_TAGS,
)
from infrastructure.http_client import get_session
from logger import setup_logger
from models import PluginResult, ScanConfig
from utils.date_utils import days_ago

logger = setup_logger(__name__)

WORDPRESS_PLUGIN_API_URL = "https://api.wordpress.org/plugins/info/1.2/"
WORDPRESS_PLUGIN_PAGE_SIZE = 100
DEFAULT_FETCH_RETRIES = 3
FETCH_TIMEOUT_SECONDS = 30
RATE_LIMIT_BACKOFF_SECONDS = 5
NETWORK_RETRY_DELAY_SECONDS = 2
AGGRESSIVE_SCAN_THREADS = 50
DEFAULT_SCAN_THREADS = 5
TRUSTED_AUTHOR_KEYWORDS = ("automattic", "wordpress.org")


def analyze_changelog(sections: Dict[str, str]) -> tuple[list[str], list[str]]:
    log = str(sections.get("changelog", "") or "").lower()
    if not log:
        return [], []

    recent = log[:2000]
    sec = [kw for kw in SECURITY_KEYWORDS if kw in recent]
    feat = [kw for kw in FEATURE_KEYWORDS if kw in recent]
    return sec, feat


def _plugin_query_params(page: int, browse: str) -> Dict[str, Any]:
    return {
        "action": "query_plugins",
        "request[browse]": browse,
        "request[page]": page,
        "request[per_page]": WORDPRESS_PLUGIN_PAGE_SIZE,
        "request[fields][active_installs]": True,
        "request[fields][short_description]": True,
        "request[fields][last_updated]": True,
        "request[fields][download_link]": True,
        "request[fields][ratings]": True,
        "request[fields][num_ratings]": True,
        "request[fields][support_threads]": True,
        "request[fields][support_threads_resolved]": True,
        "request[fields][tested]": True,
        "request[fields][author]": True,
        "request[fields][version]": True,
        "request[fields][tags]": True,
        "request[fields][sections]": True,
        "request[fields][donate_link]": True,
    }


def _rate_limit(attempt: int) -> None:
    wait = RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1)
    logger.error("Rate limited, waiting %ss...", wait)
    time.sleep(wait)


def _net_retry(error: Exception) -> None:
    logger.error("Network error (%s), retrying...", error)
    time.sleep(NETWORK_RETRY_DELAY_SECONDS)


def fetch_plugins(
    page: int,
    browse: str,
    retries: int = DEFAULT_FETCH_RETRIES,
) -> list[Dict[str, Any]]:
    session = get_session()
    params = _plugin_query_params(page, browse)

    for attempt in range(retries):
        try:
            resp = session.get(
                WORDPRESS_PLUGIN_API_URL,
                params=params,
                timeout=FETCH_TIMEOUT_SECONDS,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            _net_retry(exc)
            continue
        except Exception as exc:
            logger.error("Unexpected API Error: %s", exc)
            break

        if resp.status_code == 200:
            data = resp.json()
            return data.get("plugins", []) if data else []

        if resp.status_code == 429:
            _rate_limit(attempt)
            continue

        logger.warning(
            "Plugin API request returned non-success status",
            extra={"status_code": resp.status_code, "page": page, "browse_type": browse},
        )
        break

    return []


def _match_tags(
    candidates: set[str],
    tags: list[str],
    name: str,
    desc: str,
) -> list[str]:
    return [
        tag for tag in candidates if tag in tags or tag in name or tag in desc
    ]


def _check_facing(
    config: ScanConfig,
    tags: list[str],
    name: str,
    desc: str,
) -> tuple[bool, bool]:
    matched = _match_tags(USER_FACING_TAGS, tags, name, desc)
    if config.user_facing and not matched:
        return False, False
    return True, bool(matched)


def _support_rate(plugin: Dict[str, Any]) -> int:
    total = int(plugin.get("support_threads", 0) or 0)
    resolved = int(plugin.get("support_threads_resolved", 0) or 0)
    if total <= 0:
        return 0
    return int((resolved / total) * 100)


def _trusted_author(raw: str) -> bool:
    text = raw.lower()
    return any(kw in text for kw in TRUSTED_AUTHOR_KEYWORDS)


def _build_result(
    *,
    plugin: Dict[str, Any],
    slug: str,
    installs: int,
    days: int,
    tested: str,
    tags: list[str],
    sec: list[str],
    feat: list[str],
    score: int,
    facing: bool,
    trusted: bool,
) -> PluginResult:
    return PluginResult(
        name=plugin.get("name", "Unknown"),
        slug=slug,
        version=plugin.get("version", "?"),
        score=score,
        installations=installs,
        days_since_update=days,
        tested_wp_version=tested,
        author_trusted=trusted,
        is_risky_category=bool(tags),
        is_user_facing=facing,
        is_theme=False,
        risk_tags=tags,
        security_flags=sec,
        feature_flags=feat,
        download_link=plugin.get("download_link", ""),
        wp_org_link=f"https://wordpress.org/plugins/{slug}/",
        cve_search_link=f"https://cve.mitre.org/cgi-bin/cvekey.cgi?keyword={slug}",
        wpscan_link=f"https://wpscan.com/plugin/{slug}",
        trac_link=f"https://plugins.trac.wordpress.org/log/{slug}/",
    )


class PluginScanner:
    def __init__(
        self,
        config: ScanConfig,
        on_result: Optional[Callable[[PluginResult], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ):
        self.config = config
        self.on_result = on_result
        self.on_progress = on_progress
        self.results: list[PluginResult] = []
        self.found_count = 0
        self.stop_event = threading.Event()
        self._results_lock = threading.Lock()

    def stop(self) -> None:
        self.stop_event.set()

    def _limit_reached(self) -> bool:
        with self._results_lock:
            return self.config.limit > 0 and self.found_count >= self.config.limit

    def _should_stop(self) -> bool:
        return self.stop_event.is_set() or self._limit_reached()

    def _store_result(self, result: PluginResult) -> bool:
        with self._results_lock:
            if self.config.limit > 0 and self.found_count >= self.config.limit:
                return False
            self.found_count += 1
            self.results.append(result)
            return True

    def _passes_install_filters(self, installs: int) -> bool:
        if installs < self.config.min_installs:
            return False
        if self.config.max_installs > 0 and installs > self.config.max_installs:
            return False
        return True

    def _passes_age(self, days: int) -> bool:
        if self.config.min_days > 0 and days < self.config.min_days:
            return False
        if self.config.max_days > 0 and days > self.config.max_days:
            return False
        if self.config.abandoned and days < 730:
            return False
        return True

    def process_plugin(self, plugin: Dict[str, Any]) -> Optional[PluginResult]:
        installs = int(plugin.get("active_installs", 0) or 0)
        if not self._passes_install_filters(installs):
            return None

        days = days_ago(plugin.get("last_updated"))
        if not self._passes_age(days):
            return None

        tags = list((plugin.get("tags") or {}).keys())
        name = str(plugin.get("name", "") or "").lower()
        desc = str(plugin.get("short_description", "") or "").lower()
        matched = _match_tags(RISKY_TAGS, tags, name, desc)
        if self.config.smart and not matched:
            return None

        ok, facing = _check_facing(
            self.config,
            tags,
            name,
            desc,
        )
        if not ok:
            return None

        sec, feat = analyze_changelog(plugin.get("sections", {}))
        tested = str(plugin.get("tested", "?") or "?")
        slug = str(plugin.get("slug", "") or "")
        author = str(plugin.get("author", "Unknown") or "Unknown")
        score = score_vps(
            plugin,
            days,
            matched,
            _support_rate(plugin),
            tested,
            sec,
            None,
        )

        return _build_result(
            plugin=plugin,
            slug=slug,
            installs=installs,
            days=days,
            tested=tested,
            tags=matched,
            sec=sec,
            feat=feat,
            score=score,
            facing=facing,
            trusted=_trusted_author(author),
        )

    def scan_page(self, page: int) -> list[PluginResult]:
        if self._should_stop():
            return []

        plugins = fetch_plugins(page, self.config.sort)
        items: list[PluginResult] = []
        for plugin in plugins:
            if self._should_stop():
                break

            result = self.process_plugin(plugin)
            if result is None:
                continue
            if not self._store_result(result):
                break

            items.append(result)
            if self.on_result:
                self.on_result(result)
        return items

    def _notify_progress(self, current: int, total: int) -> None:
        if self.on_progress:
            self.on_progress(current, total)

    def _scan_seq(self, pages: list[int]) -> list[PluginResult]:
        total = len(pages)
        for index, page in enumerate(pages, start=1):
            if self._should_stop():
                break
            self.scan_page(page)
            self._notify_progress(index, total)
        return self.results

    def _drain(
        self,
        futures: Dict[Future[list[PluginResult]], int],
        total: int,
        executor: ThreadPoolExecutor,
    ) -> list[PluginResult]:
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                future.result()
            except Exception as exc:
                page = futures[future]
                logger.error("Page scan failed for page %s: %s", page, exc)

            self._notify_progress(index, total)
            if self.stop_event.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
        return self.results

    def _scan_pool(
        self,
        pages: list[int],
        workers: int,
    ) -> list[PluginResult]:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.scan_page, page): page for page in pages
            }
            return self._drain(futures, len(pages), executor)

    def scan(self) -> list[PluginResult]:
        pages = list(range(1, self.config.pages + 1))
        workers = (
            AGGRESSIVE_SCAN_THREADS if self.config.aggressive else DEFAULT_SCAN_THREADS
        )
        if self.config.aggressive:
            logger.info("Using aggressive scan mode", extra={"max_threads": workers})

        results = (
            self._scan_seq(pages)
            if self.config.limit > 0
            else self._scan_pool(pages, workers)
        )
        self._label_risk()
        return results

    def _label_risk(self) -> None:
        label_risk(
            self.results,
            get_score=lambda item: item.score,
            set_label=lambda item, label: setattr(item, "relative_risk", label),
        )
