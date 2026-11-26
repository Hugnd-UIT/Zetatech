from __future__ import annotations

import logging
import re
import threading
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import requests

from main import get_runtime_metadata

logger = logging.getLogger("zetatech.update")


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReleaseMetadataService:

    TAG_PATTERN = re.compile(r"^[vV]\d+(?:\.\d+)*$")

    def __init__(
        self,
        *,
        release_api_url: str,
        allowed_release_hosts: set[str],
    ) -> None:
        self.release_api_url = release_api_url
        self.allowed_release_hosts = allowed_release_hosts

    def normalized_version(self, version: Optional[str]) -> Tuple[int, ...]:
        if not version:
            return ()
        cleaned = version.strip().lstrip("vV")
        parts = cleaned.replace("-", ".").replace("_", ".").split(".")
        nums: List[int] = []
        for part in parts:
            digits = "".join(ch for ch in part if ch.isdigit())
            nums.append(int(digits) if digits else 0)
        return tuple(nums)

    def is_newer_release(self, current_version: Optional[str], latest_version: Optional[str]) -> bool:
        cur = self.normalized_version(current_version)
        lat = self.normalized_version(latest_version)
        if not lat:
            return False
        size = max(len(cur), len(lat))
        cur += (0,) * (size - len(cur))
        lat += (0,) * (size - len(lat))
        return lat > cur

    def release_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Zetatech Update Agent",
        }

    def release_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        html_url = data.get("html_url")
        if html_url:
            parsed = urlparse(str(html_url))
            if parsed.hostname not in self.allowed_release_hosts:
                raise ValueError(f"Unsupported release URL host: {parsed.hostname}")
        return {
            "tag_name": data.get("tag_name"),
            "name": data.get("name") or data.get("tag_name"),
            "body": data.get("body") or "",
            "published_at": data.get("published_at"),
            "html_url": html_url,
        }

    def tag_headers(self) -> Dict[str, str]:
        return self.release_headers()

    def tag_url(self, tag_name: str) -> str:
        return f"https://github.com/Hugnd-UIT/Zetatech/tree/{quote(tag_name, safe='/')}"

    def _pick_tag(self, tags: List[Dict[str, Any]]) -> Optional[str]:
        best_tag: Optional[str] = None
        best_ver: Tuple[int, ...] = ()
        for entry in tags:
            name = str(entry.get("name") or "").strip()
            if not self.TAG_PATTERN.fullmatch(name):
                continue
            ver = self.normalized_version(name)
            if ver > best_ver:
                best_tag = name
                best_ver = ver
        return best_tag

    def empty_payload(self) -> Dict[str, Any]:
        return {
            "tag_name": None,
            "name": None,
            "body": "",
            "published_at": None,
            "html_url": None,
            "update_available": False,
        }

    def fetch_release(self) -> Dict[str, Any]:
        parsed = urlparse(self.release_api_url)
        if parsed.hostname not in self.allowed_release_hosts:
            raise ValueError(f"Unsupported release API host: {parsed.hostname}")
        res = requests.get(
            self.release_api_url,
            headers=self.tag_headers(),
            timeout=15,
        )
        res.raise_for_status()
        payload = res.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected tags API response shape")
        tag = self._pick_tag(payload)
        if not tag:
            return self.empty_payload()
        return self.release_payload(
            {
                "tag_name": tag,
                "name": tag,
                "body": "",
                "published_at": None,
                "html_url": self.tag_url(tag),
            }
        )


class UpdateManager:
    RELEASE_API_URL = "https://api.github.com/repos/Hugnd-UIT/Zetatech/tags"
    CHECK_INTERVAL = timedelta(minutes=30)
    ALLOWED_RELEASE_HOSTS = {
        "api.github.com",
        "github.com",
        "codeload.github.com",
        "objects.githubusercontent.com",
        "github-releases.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
    HELPER_IMAGE = "Hugnd-UIT/Zetatech:latest"
    HELPER_DATA_VOLUME = "zetatech-data"
    HELPER_PORT = 8080
    MESSAGE_UP_TO_DATE = "Zetatech is already running the latest available release."
    MESSAGE_UPDATE_AVAILABLE = "A newer release is available. Pull the latest image and rerun the container manually."
    MESSAGE_DEGRADED = "Release information is temporarily unavailable. Version details may be incomplete right now."
    MESSAGE_MANUAL_UPDATE_ONLY = (
        "Automatic updates are no longer supported. Pull the latest image and rerun the container manually."
    )

    def __init__(self) -> None:
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._lock = threading.Lock()
        self._last_error: Optional[str] = None
        self._startup_auto_check_done = False
        self._release_metadata = ReleaseMetadataService(
            release_api_url=self.RELEASE_API_URL,
            allowed_release_hosts=self.ALLOWED_RELEASE_HOSTS,
        )

    def _runtime_meta(self) -> Dict[str, Any]:
        meta = get_runtime_metadata()
        return {
            "current_version": meta.current_version,
            "current_tag": meta.current_tag,
            "build_id": meta.build_id,
            "runtime_status": meta.status,
        }

    def _fetch_release(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            now = utc_now()
            if (
                not force
                and self._cache
                and self._cache_time
                and (now - self._cache_time) < self.CHECK_INTERVAL
            ):
                return self._cache

        info = self._release_metadata.fetch_release()
        with self._lock:
            self._cache = info
            self._cache_time = now
        return info

    def _empty_rel(self) -> Dict[str, Any]:
        return self._release_metadata.empty_payload()

    def _resolve_release(self, force: bool) -> Dict[str, Any]:
        fetch = force
        if not force:
            with self._lock:
                if not self._startup_auto_check_done:
                    self._startup_auto_check_done = True
                    fetch = True

        if fetch:
            try:
                rel = self._fetch_release(force)
                self._last_error = None
                return rel
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Unable to refresh release info: %s", exc)
                with self._lock:
                    cached = self._cache
                if cached:
                    return cached
                return self._empty_rel()

        with self._lock:
            cached = self._cache
        if cached:
            return cached
        return self._empty_rel()

    def _update_cmd(self) -> str:
        return (
            f"docker pull {self.HELPER_IMAGE}\n"
            f"docker rm -f zetatech >/dev/null 2>&1 || true\n"
            f"docker run -d --name zetatech -p {self.HELPER_PORT}:8080 "
            f"-v {self.HELPER_DATA_VOLUME}:/home/appuser/.zetatech "
            f"{self.HELPER_IMAGE}"
        )

    def _status_label(
        self,
        *,
        runtime_status: str,
        latest_version: Optional[str],
        update_available: bool,
        release_error: Optional[str],
    ) -> str:
        if runtime_status == "degraded":
            return "degraded"
        if release_error and not latest_version:
            return "degraded"
        if update_available:
            return "update_available"
        return "up_to_date"

    def _status_msg(self, status_label: str, runtime_status: str) -> str:
        if status_label == "update_available":
            return self.MESSAGE_UPDATE_AVAILABLE
        if status_label == "degraded":
            if runtime_status == "degraded":
                return "Runtime version metadata is incomplete. Release information may be unreliable right now."
            return self.MESSAGE_DEGRADED
        return self.MESSAGE_UP_TO_DATE

    def _status_payload(self, release: Dict[str, Any]) -> Dict[str, Any]:
        meta = self._runtime_meta()
        ref = meta["current_tag"]
        if ref == "unknown":
            ref = meta["current_version"]
        latest = release.get("tag_name")
        avail = self._release_metadata.is_newer_release(ref, latest)
        checked = self._cache_time.isoformat().replace("+00:00", "Z") if self._cache_time else None
        label = self._status_label(
            runtime_status=meta["runtime_status"],
            latest_version=latest,
            update_available=avail,
            release_error=self._last_error,
        )
        cmd = self._update_cmd() if avail else None
        raw_url = release.get("html_url")
        url = self._release_metadata.tag_url(latest) if latest and raw_url else raw_url

        return {
            "current_version": meta["current_version"],
            "current_tag": meta["current_tag"],
            "build_id": meta["build_id"],
            "runtime_status": meta["runtime_status"],
            "latest_version": latest,
            "release_name": release.get("name") or latest,
            "release_notes": release.get("body") or "",
            "release_url": url,
            "release_published_at": release.get("published_at"),
            "update_available": avail,
            "status": label,
            "message": self._status_msg(label, meta["runtime_status"]),
            "update_command": cmd,
            "manual_update_required": avail,
            "manual_update_message": self.MESSAGE_MANUAL_UPDATE_ONLY if avail else None,
            "checked_at": checked,
            "last_error": self._last_error,
        }

    def get_status(self, force: bool = False) -> Dict[str, Any]:
        release = self._resolve_release(force)
        return self._status_payload(release)

    def manual_payload(self) -> Dict[str, Any]:
        status = self.get_status(force=True)
        return {
            "status": status["status"],
            "message": self.MESSAGE_MANUAL_UPDATE_ONLY,
            "current_version": status["current_version"],
            "current_tag": status["current_tag"],
            "latest_version": status["latest_version"],
            "update_available": status["update_available"],
            "update_command": status["update_command"],
            "manual_update_required": status["manual_update_required"],
            "manual_update_only": True,
            "deprecated": True,
        }


manager = UpdateManager()
