import json
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from infrastructure.semgrep_runtime import get_semgrep_command, semgrep_install_hint
from paths import resolve_runtime_paths


SEMGREP_REGISTRY_RULESETS = {
    "owasp-top-ten": {
        "config": "p/owasp-top-ten",
        "description": "OWASP Top 10 vulnerabilities (2021)",
        "url": "https://semgrep.dev/p/owasp-top-ten",
    },
    "php-security": {
        "config": "p/php",
        "description": "PHP security best practices",
        "url": "https://semgrep.dev/p/php",
    },
    "security-audit": {
        "config": "p/security-audit",
        "description": "Comprehensive security audit rules",
        "url": "https://semgrep.dev/p/security-audit",
    },
}


DEFAULT_ENABLED_RULESETS = ["owasp-top-ten", "php-security", "security-audit"]


SEMGREP_COMMUNITY_SOURCES = [
    {
        "name": "Semgrep Registry",
        "url": "https://semgrep.dev/r",
        "description": "Official Semgrep rule registry with 3000+ rules",
    },
    {
        "name": "OWASP Top 10 Rules",
        "url": "https://semgrep.dev/p/owasp-top-ten",
        "description": "Rules for OWASP Top 10 2021 vulnerabilities",
    },
    {
        "name": "PHP Security Rules",
        "url": "https://semgrep.dev/p/php",
        "description": "PHP-specific security patterns",
    },
    {
        "name": "Security Audit Pack",
        "url": "https://semgrep.dev/p/security-audit",
        "description": "Comprehensive security audit rules",
    },
]

RUNTIME_PATHS = resolve_runtime_paths()
SEMGREP_TIMEOUT_SECONDS = 3600
SAFE_SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
DANGEROUS_PATH_CHARS = [";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r"]
LEGACY_SEMGREP_RESULTS_DIR = Path("./semgrep_results")
LEGACY_PACKAGE_SEMGREP_RESULTS_DIR = Path(__file__).resolve().parents[1] / "semgrep_results"
SHARED_DISABLED_CONFIG_PATH = RUNTIME_PATHS.semgrep_dir / "disabled_config.json"
CANONICAL_CUSTOM_RULES_PATH = RUNTIME_PATHS.semgrep_dir / "custom_rules.yaml"
DEFAULT_SEMGREP_OUTPUT_DIR = RUNTIME_PATHS.semgrep_outputs_dir


@dataclass
class SemgrepResult:
    slug: str
    findings: List[Dict[str, Any]]
    errors: List[str]
    success: bool
    partial: bool = False


@dataclass
class SemgrepTarget:
    slug: str
    plugin_target_path: str
    output_file: Path


@dataclass
class SemgrepExecutionResult:
    findings: List[Dict[str, Any]]
    errors: List[str]
    success: bool
    partial: bool = False


class SemgrepScanner:
    def __init__(
        self,
        rules_path: Optional[str] = None,
        output_dir: str | Path = DEFAULT_SEMGREP_OUTPUT_DIR,
        workers: int = 3,
        use_registry_rules: bool = True,
        registry_rulesets: Optional[List[str]] = None,
    ):
        self.rules_path = rules_path
        self.output_dir = Path(output_dir)
        self.workers = workers
        self.stop_event = threading.Event()
        self.use_registry_rules = use_registry_rules
        self.registry_rulesets = registry_rulesets or DEFAULT_ENABLED_RULESETS
        self.semgrep_command = get_semgrep_command()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _result(
        self,
        slug: str,
        *,
        findings: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[str]] = None,
        success: bool = False,
        partial: bool = False,
    ) -> SemgrepResult:
        return SemgrepResult(
            slug=slug,
            findings=findings or [],
            errors=errors or [],
            success=success,
            partial=partial,
        )

    def _disabled_rules(self) -> set[str]:
        ids: set[str] = set()

        legacy = self.output_dir / "disabled_rules.json"
        if legacy.exists():
            try:
                with open(legacy, "r") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, list):
                    ids.update(str(item) for item in loaded)
            except Exception:
                pass

        shared = SHARED_DISABLED_CONFIG_PATH
        if shared.exists():
            try:
                with open(shared, "r") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    ids.update(str(item) for item in loaded.get("rules", []))
            except Exception:
                pass

        return ids

    def _custom_file(self) -> Optional[Path]:
        cands = [
            self.output_dir / "custom_rules.yaml",
            CANONICAL_CUSTOM_RULES_PATH,
            LEGACY_SEMGREP_RESULTS_DIR / "custom_rules.yaml",
            LEGACY_PACKAGE_SEMGREP_RESULTS_DIR / "custom_rules.yaml",
        ]
        return next((path for path in cands if path.exists()), None)

    def _valid_rule(self, rule: Dict[str, Any]) -> bool:
        if not self.semgrep_command:
            return True

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as tmp:
                yaml.dump({"rules": [rule]}, tmp, default_flow_style=False, sort_keys=False)
                tmp_path = tmp.name

            res = subprocess.run(
                [*self.semgrep_command, "--validate", "--config", tmp_path],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return res.returncode == 0
        except Exception:
            return False
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _write_rules(self, rules_data: Dict[str, Any], disabled_ids: set[str]) -> Optional[str]:
        rules = rules_data.get("rules", [])
        if not isinstance(rules, list):
            return None

        active: List[Dict[str, Any]] = []
        invalid: List[str] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rid = str(rule.get("id") or "")
            if not rid or rid in disabled_ids:
                continue
            if self._valid_rule(rule):
                active.append(rule)
            else:
                invalid.append(rid)

        if invalid:
            path = self.output_dir / "invalid_custom_rules.json"
            with open(path, "w") as fh:
                json.dump({"invalid_rule_ids": invalid}, fh)

        if not active:
            return None

        out = self.output_dir / "active_custom_rules.yaml"
        with open(out, "w") as fh:
            yaml.dump(
                {"rules": active},
                fh,
                default_flow_style=False,
                sort_keys=False,
            )
        return str(out)

    def _filter_rules(self) -> Optional[str]:
        file = self._custom_file()
        if not file:
            return None

        disabled = self._disabled_rules()
        try:
            with open(file, "r") as fh:
                data = yaml.safe_load(fh)
            if data and "rules" in data:
                return self._write_rules(data, disabled)
        except Exception:
            return str(file)

        return str(file)

    def _cfg_args(self) -> List[str]:
        vals: List[str] = []

        custom = self._filter_rules()
        if custom:
            vals.append(custom)

        if self.use_registry_rules:
            for key in self.registry_rulesets:
                val = str(
                    SEMGREP_REGISTRY_RULESETS.get(key, {}).get(
                        "config",
                        key,
                    )
                    or ""
                ).strip()
                if val:
                    vals.append(val)

        dedup = list(dict.fromkeys(vals))
        cfgs: List[str] = []
        for val in dedup:
            cfgs.extend(["--config", val])
        return cfgs

    def _check_target(self, plugin_path: str, slug: str) -> SemgrepTarget | SemgrepResult:
        if not slug or not isinstance(slug, str):
            return self._result(slug or "unknown", errors=["Invalid slug"])

        if not SAFE_SLUG_PATTERN.match(slug):
            return self._result(slug, errors=["Invalid slug format"])

        path = Path(plugin_path)
        if not path.exists():
            return self._result(slug, errors=["Plugin path does not exist"])
        if not path.is_dir():
            return self._result(slug, errors=["Plugin path is not a directory"])

        try:
            resolved = path.resolve()
            target = str(resolved)
            if any(char in target for char in DANGEROUS_PATH_CHARS):
                return self._result(slug, errors=["Invalid characters in path"])
        except Exception as exc:
            return self._result(slug, errors=[f"Path validation error: {str(exc)}"])

        return SemgrepTarget(
            slug=slug,
            plugin_target_path=target,
            output_file=self.output_dir / f"{slug}_results.json",
        )

    def _scan_cmd(self, target: SemgrepTarget) -> List[str]:
        command = list(self.semgrep_command or [])
        command.extend(self._cfg_args())
        command.extend(
            [
                "--json",
                "--output",
                str(target.output_file),
                "--no-git-ignore",
                target.plugin_target_path,
            ]
        )
        return command

    def _minor_error(self, message: str) -> bool:
        normalized = str(message or "").lower()
        markers = [
            "syntax error",
            "parse error",
            "partial parsing",
            "could not parse",
            "was unexpected",
            "timeout when running",
            "timed out while running",
        ]
        return any(marker in normalized for marker in markers)

    def _parse_output(self, output_file: Path, stderr: str) -> SemgrepExecutionResult:
        try:
            with open(output_file, "r") as fh:
                data = json.load(fh)
        except json.JSONDecodeError:
            return SemgrepExecutionResult(
                findings=[],
                errors=[f"Invalid JSON output from Semgrep. Stderr: {stderr}"],
                success=False,
            )

        findings = data.get("results", [])
        raw = data.get("errors", [])
        errors = [
            str(error.get("message") or "").strip()
            for error in raw
            if isinstance(error, dict) and str(error.get("message") or "").strip()
        ]
        err = str(stderr or "").strip()

        if errors:
            minor = [item for item in errors if self._minor_error(item)]
            fatal = [item for item in errors if item not in minor]

            if fatal or not findings:
                if err:
                    errors.append(f"stderr: {err}")
                return SemgrepExecutionResult(
                    findings=findings if findings else [],
                    errors=errors,
                    success=False,
                )

            return SemgrepExecutionResult(
                findings=findings,
                errors=minor,
                success=True,
            )

        return SemgrepExecutionResult(
            findings=findings,
            errors=[],
            success=True,
        )

    def _parse_proc(
        self,
        *,
        output_file: Path,
        returncode: int,
        stderr: str,
        timed_out: bool = False,
    ) -> SemgrepExecutionResult:
        if output_file.exists() and output_file.stat().st_size > 0:
            parsed = self._parse_output(output_file, stderr)
            if timed_out:
                errs = ["Scan timeout"] + parsed.errors
                if parsed.findings:
                    return SemgrepExecutionResult(
                        findings=parsed.findings,
                        errors=errs,
                        success=True,
                        partial=True,
                    )
                return SemgrepExecutionResult(
                    findings=parsed.findings,
                    errors=errs,
                    success=False,
                    partial=True,
                )
            return parsed

        if returncode != 0:
            return SemgrepExecutionResult(
                findings=[],
                errors=[f"Semgrep failed (code {returncode}): {stderr}"],
                success=False,
            )

        return SemgrepExecutionResult(
            findings=[],
            errors=[f"No output file generated. Stderr: {stderr}"],
            success=False,
        )

    def _run_scan(self, target: SemgrepTarget) -> SemgrepExecutionResult:
        if not self.semgrep_command:
            return SemgrepExecutionResult(
                findings=[],
                errors=[f"Semgrep not available. {semgrep_install_hint()}"],
                success=False,
            )

        target.output_file.parent.mkdir(parents=True, exist_ok=True)

        process = subprocess.Popen(
            self._scan_cmd(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        max_out = 10 * 1024 * 1024
        try:
            if SEMGREP_TIMEOUT_SECONDS is None:
                stdout, stderr = process.communicate()
            else:
                stdout, stderr = process.communicate(timeout=SEMGREP_TIMEOUT_SECONDS)
            if len(stdout) > max_out:
                stdout = stdout[:max_out]
            if len(stderr) > max_out:
                stderr = stderr[:max_out]
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            if len(stdout) > max_out:
                stdout = stdout[:max_out]
            if len(stderr) > max_out:
                stderr = stderr[:max_out]
            return self._parse_proc(
                output_file=target.output_file,
                returncode=process.returncode,
                stderr=stderr,
                timed_out=True,
            )

        return self._parse_proc(
            output_file=target.output_file,
            returncode=process.returncode,
            stderr=stderr,
        )

    def scan_plugin(self, plugin_path: str, slug: str) -> SemgrepResult:
        target = self._check_target(plugin_path, slug)
        if isinstance(target, SemgrepResult):
            return target

        if self.stop_event.is_set():
            return self._result(target.slug, errors=["Stopped"])

        try:
            res = self._run_scan(target)
            return self._result(
                target.slug,
                findings=res.findings,
                errors=res.errors,
                success=res.success,
                partial=res.partial,
            )
        except subprocess.TimeoutExpired:
            return self._result(target.slug, errors=["Scan timeout"])
        except Exception as exc:
            return self._result(target.slug, errors=[str(exc)])

    def stop(self):
        self.stop_event.set()
