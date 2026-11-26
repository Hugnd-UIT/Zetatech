import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from infrastructure.semgrep_runtime import get_semgrep_command, is_semgrep_available
from paths import resolve_runtime_paths
from scanners.semgrep import (
    DEFAULT_ENABLED_RULESETS,
    SEMGREP_COMMUNITY_SOURCES,
    SEMGREP_REGISTRY_RULESETS,
)

logger = logging.getLogger("zetatech")

CORE_RULESET_KEYS = {"owasp-top-ten", "php-security", "security-audit"}
CORE_RULESET_CONFIGS = {"p/owasp-top-ten", "p/php", "p/security-audit"}
CORE_RULESET_CONFIG_TO_KEY = {
    "p/owasp-top-ten": "owasp-top-ten",
    "p/php": "php-security",
    "p/security-audit": "security-audit",
}
SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")
RULESET_PATTERN = re.compile(r"^[a-zA-Z0-9_./-]+$")
RULE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

RUNTIME_PATHS = resolve_runtime_paths()
SEM_RESULTS_DIR = RUNTIME_PATHS.semgrep_outputs_dir
SEMGREP_STATE_DIR = RUNTIME_PATHS.semgrep_dir
LEGACY_SEM_RESULTS_DIR = Path("./semgrep_results")
LEGACY_CUSTOM_RULES_PATH = LEGACY_SEM_RESULTS_DIR / "custom_rules.yaml"
LEGACY_DISABLED_CONFIG_PATH = LEGACY_SEM_RESULTS_DIR / "disabled_config.json"
ROOT_CUSTOM_RULES_PATH = Path(__file__).resolve().parents[3] / "rules.yaml"
CUSTOM_RULES_PATH = SEMGREP_STATE_DIR / "custom_rules.yaml"
DISABLED_CONFIG_PATH = SEMGREP_STATE_DIR / "disabled_config.json"
PACKAGE_CUSTOM_RULES_PATH = (
    Path(__file__).resolve().parents[3] / "semgrep_results" / "custom_rules.yaml"
)


def ensure_state() -> bool:
    try:
        SEMGREP_STATE_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        logger.warning("Semgrep state directory is not writable: %s", SEMGREP_STATE_DIR)
        return False


def _has_rules(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("rules", []) if isinstance(data, dict) else []
        return isinstance(rules, list) and len(rules) > 0
    except Exception:
        return False


def bootstrap_rules() -> None:
    if not ensure_state():
        return

    boot = not _has_rules(CUSTOM_RULES_PATH)
    if boot:
        for candidate in (
            ROOT_CUSTOM_RULES_PATH,
            LEGACY_CUSTOM_RULES_PATH,
            PACKAGE_CUSTOM_RULES_PATH,
        ):
            if not _has_rules(candidate):
                continue
            try:
                shutil.copy2(candidate, CUSTOM_RULES_PATH)
                break
            except Exception:
                logger.warning("Failed to bootstrap default Semgrep custom rules from %s.", candidate)

    if not DISABLED_CONFIG_PATH.exists() and LEGACY_DISABLED_CONFIG_PATH.exists():
        try:
            shutil.copy2(LEGACY_DISABLED_CONFIG_PATH, DISABLED_CONFIG_PATH)
        except Exception:
            logger.warning("Failed to migrate disabled Semgrep config.")


def get_disabled_config() -> Dict[str, List[str]]:
    defaults = {"rules": [], "rulesets": [], "extra_rulesets": []}
    legacy = {"cwe-top-25"}
    if DISABLED_CONFIG_PATH.exists():
        try:
            with open(DISABLED_CONFIG_PATH, "r") as f:
                cfg = json.load(f)
                prev_sets = set(cfg.get("rulesets", []))
                prev_extra = set(cfg.get("extra_rulesets", []))
                norm = {
                    "rules": cfg.get("rules", []),
                    "rulesets": cfg.get("rulesets", []),
                    "extra_rulesets": cfg.get("extra_rulesets", []),
                }
                norm["rulesets"] = list(
                    dict.fromkeys(_canon_ruleset(r) for r in norm["rulesets"])
                )
                norm["extra_rulesets"] = list(
                    dict.fromkeys(
                        _canon_ruleset(r)
                        for r in norm["extra_rulesets"]
                    )
                )
                norm["rulesets"] = [
                    r for r in norm["rulesets"] if r not in legacy
                ]
                norm["extra_rulesets"] = [
                    r for r in norm["extra_rulesets"] if r not in legacy
                ]
                if prev_sets != set(norm["rulesets"]) or prev_extra != set(
                    norm["extra_rulesets"]
                ):
                    save_disabled_config(norm)
                return norm
        except Exception:
            pass
    return defaults


def save_disabled_config(config: Dict[str, List[str]]):
    if not ensure_state():
        raise PermissionError("Semgrep persistent state is not writable in the current runtime environment.")
    DISABLED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISABLED_CONFIG_PATH, "w") as f:
        json.dump(config, f)


def get_active_rulesets() -> List[str]:
    cfg = get_disabled_config()
    disabled = set(cfg.get("rulesets", []))
    extras = cfg.get("extra_rulesets", [])
    combined = DEFAULT_ENABLED_RULESETS + extras
    unique = list(dict.fromkeys(combined))
    return [rs for rs in unique if rs not in disabled]


def _norm_ruleset(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return value
    if value.startswith(("p/", "r/")):
        return value
    if value.startswith("https://semgrep.dev/"):
        parsed = value.split("https://semgrep.dev/", 1)[1].strip("/")
        return parsed
    return value


def _canon_ruleset(raw: str) -> str:
    normalized = _norm_ruleset(raw)
    return CORE_RULESET_CONFIG_TO_KEY.get(normalized, normalized)


def _check_slug(slug: str) -> str:
    value = (slug or "").strip()
    if not SLUG_PATTERN.fullmatch(value):
        raise ValueError("Invalid slug format")
    return value


def _check_rule(rule_id: str) -> str:
    value = (rule_id or "").strip()
    if not RULE_ID_PATTERN.match(value):
        raise ValueError("Invalid rule ID format")
    return value


def check_ruleset(ruleset_id: str) -> str:
    ruleset_id = _canon_ruleset(ruleset_id)
    if not RULESET_PATTERN.match(ruleset_id):
        raise ValueError("Invalid ruleset format")
    return ruleset_id


def _bulk_url(plugin: Dict[str, Any], slug: str) -> str:
    version = plugin.get("version") or "latest"
    return plugin.get("download_link") or (
        f"https://downloads.wordpress.org/plugin/{slug}.{version}.zip"
    )


def _bulk_meta(plugin: Dict[str, Any]) -> Optional[Dict[str, str]]:
    raw_slug = plugin.get("slug")
    if not raw_slug:
        return None

    slug = _check_slug(str(raw_slug))
    version = str(plugin.get("version") or "latest")
    download_url = _bulk_url(plugin, slug)
    return {"slug": slug, "version": version, "download_url": download_url}


def _check_rules(rules_config: Dict[str, Any]) -> Optional[str]:
    cmd = get_semgrep_command()
    if not cmd:
        return "Semgrep is not available for rule validation."

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tmp:
            yaml.dump(rules_config, tmp, default_flow_style=False, sort_keys=False)
            tmp_path = tmp.name

        res = subprocess.run(
            [*cmd, "--validate", "--config", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode == 0:
            return None

        err = (
            res.stderr or res.stdout or "Unknown Semgrep validation error"
        ).strip()
        return err[:800]
    except subprocess.TimeoutExpired:
        return "Semgrep validation timed out."
    except Exception as e:
        return f"Semgrep validation failed: {str(e)}"
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def load_custom_rules() -> List[Dict[str, Any]]:
    bootstrap_rules()
    items: List[Dict[str, Any]] = []
    if CUSTOM_RULES_PATH.exists():
        try:
            with open(CUSTOM_RULES_PATH, "r") as f:
                doc = yaml.safe_load(f)
                if doc and "rules" in doc:
                    for rule in doc["rules"]:
                        rid = rule.get("id", "unknown")
                        pat = rule.get("pattern", "")
                        if not pat and "patterns" in rule:
                            pats = rule["patterns"]
                            if pats:
                                pat = (
                                    str(pats[0])
                                    if isinstance(pats[0], str)
                                    else pats[0].get("pattern", "Complex")
                                )

                        items.append(
                            {
                                "id": rid,
                                "message": rule.get("message", ""),
                                "severity": rule.get("severity", "WARNING"),
                                "pattern": pat,
                                "is_custom": True,
                            }
                        )
        except Exception as e:
            logger.warning("Error loading custom rules", exc_info=e)
    return items


def load_doc() -> Dict[str, Any]:
    bootstrap_rules()
    if CUSTOM_RULES_PATH.exists():
        try:
            with open(CUSTOM_RULES_PATH, "r") as f:
                return yaml.safe_load(f) or {"rules": []}
        except Exception:
            pass
    return {"rules": []}


def save_doc(rules_data: Dict[str, Any]) -> None:
    if not ensure_state():
        raise PermissionError("Semgrep persistent state is not writable in the current runtime environment.")
    CUSTOM_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CUSTOM_RULES_PATH, "w") as f:
        yaml.dump(rules_data, f, default_flow_style=False, sort_keys=False)


def rules_response() -> Dict[str, Any]:
    installed = is_semgrep_available()
    cfg = get_disabled_config()
    disabled_rules = set(cfg["rules"])
    disabled_sets = set(cfg["rulesets"])

    rulesets = []
    for key, info in SEMGREP_REGISTRY_RULESETS.items():
        if key not in CORE_RULESET_KEYS:
            continue
        rulesets.append(
            {
                "id": key,
                "name": info.get("description", key),
                "url": info.get("url", "#"),
                "enabled": key not in disabled_sets,
                "description": info.get("description", ""),
                "deletable": False,
            }
        )

    seen = {r["id"] for r in rulesets}
    for extra in cfg.get("extra_rulesets", []):
        norm = _norm_ruleset(extra)
        if not norm or norm in seen:
            continue
        url = (
            f"https://semgrep.dev/{norm}"
            if norm.startswith(("p/", "r/"))
            else "https://semgrep.dev/explore"
        )
        rulesets.append(
            {
                "id": norm,
                "name": norm,
                "url": url,
                "enabled": norm not in disabled_sets,
                "description": "Custom Semgrep ruleset",
                "deletable": True,
            }
        )

    items = load_custom_rules()
    for rule in items:
        rule["enabled"] = rule["id"] not in disabled_rules

    return {
        "installed": installed,
        "rulesets": rulesets,
        "custom_rules": items,
        "community_sources": SEMGREP_COMMUNITY_SOURCES,
    }
