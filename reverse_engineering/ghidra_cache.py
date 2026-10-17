"""Build and inspect a persistent Ghidra project for the EU4 executable.

The cache is deliberately separate from REA's temporary per-query projects.
``build`` imports the hash-verified executable without analysis and then runs
Ghidra's normal default analysis into a durable project.  ``resume`` continues
an imported checkpoint after a timeout or resource stop.  The module never
modifies the installed REA/Ghidra packages or the Codex configuration.

The command is intentionally conservative: a Java process is stopped only
when it is an owned descendant and its command line is verified to be a
Ghidra headless process.  A one-gigabyte committed/private-memory ceiling is
enforced in addition to the 512 MiB Ghidra heap setting.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import time
import tomllib
import uuid
from typing import Any, Iterable, Mapping

import psutil


from .catalog import load_catalog, project_root, validate_catalog


PROJECT_NAME = "EU4Full"
JAVA_HEAP = "512M"
MAX_CPU = 2
JAVA_TOOL_OPTIONS = "-XX:ActiveProcessorCount=2 -XX:ReservedCodeCacheSize=64M -XX:MaxDirectMemorySize=64M"
MEMORY_LIMIT_BYTES = 1024**3
DEFAULT_ANALYSIS_TIMEOUT = 7200
IMPORT_SUPERVISOR_TIMEOUT = 900
MAX_JSON_BYTES = 10 * 1024 * 1024
LOCK_NAME = "cache.lock"
LOCK_SCHEMA_VERSION = 1
STATUS_SCRIPT_NAME = "Eu4FullAnalysisStatus.java"
LOG_TAIL_BYTES = 256 * 1024
ALLOWED_PROGRAM = "eu4.exe"
ALLOWED_PROJECT_NAME = PROJECT_NAME


class CacheError(RuntimeError):
    """Raised for an invalid cache or a refused operation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    size = path.stat().st_size
    if size > max_bytes:
        raise CacheError(f"拒绝读取超过 {max_bytes} 字节的 JSON 文件：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CacheError(f"无法读取有效 JSON：{path} ({exc})") from exc


def _validate_cache_names(metadata: Mapping[str, Any]) -> None:
    """Reject metadata names before using them as filesystem components."""

    program = metadata.get("program")
    project_name = metadata.get("project_name", PROJECT_NAME)
    if program != ALLOWED_PROGRAM:
        raise CacheError(f"缓存 program 必须严格为 {ALLOWED_PROGRAM!r}，收到 {program!r}")
    if project_name != ALLOWED_PROJECT_NAME:
        raise CacheError(f"缓存 project_name 必须严格为 {ALLOWED_PROJECT_NAME!r}，收到 {project_name!r}")


def _bounded_tail(path: Path, limit: int = LOG_TAIL_BYTES) -> str:
    """Read only the tail of a log, keeping large Ghidra logs bounded."""

    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            stream.seek(max(0, size - limit))
            return stream.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _write_json(path: Path, value: Any) -> None:
    """Atomically write a small JSON status file."""

    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with temporary.open("wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _load_config(path: Path) -> dict[str, Any]:
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CacheError(f"无法读取 Codex 配置 {path}: {exc}") from exc
    server = config.get("mcp_servers", {}).get("rea")
    if not isinstance(server, Mapping):
        raise CacheError(f"配置中缺少 mcp_servers.rea：{path}")
    return dict(server)


def _analysis_environment(config: Mapping[str, Any]) -> dict[str, str]:
    environment = {str(key): str(value) for key, value in os.environ.items()}
    configured = config.get("env", {})
    if isinstance(configured, Mapping):
        environment.update({str(key): str(value) for key, value in configured.items()})
    ghidra_dir = Path(environment.get("GHIDRA_INSTALL_DIR", "")).expanduser()
    java_home = Path(environment.get("JAVA_HOME", "")).expanduser()
    if not ghidra_dir.is_dir():
        raise CacheError("GHIDRA_INSTALL_DIR 未配置或目录不存在")
    if not java_home.is_dir():
        raise CacheError("JAVA_HOME 未配置或目录不存在")
    # Do not inherit a user-supplied heap override.  Ghidra's launcher reads
    # these two variables and appends its own -Xmx512M argument.
    for key in ("_JAVA_OPTIONS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "GHIDRA_JAVA_OPTIONS"):
        environment.pop(key, None)
    environment["JAVA_TOOL_OPTIONS"] = JAVA_TOOL_OPTIONS
    environment["GHIDRA_HEADLESS_MAXMEM"] = JAVA_HEAP
    environment["GHIDRA_MAXMEM"] = JAVA_HEAP
    environment["JAVA_HOME"] = str(java_home)
    environment["GHIDRA_INSTALL_DIR"] = str(ghidra_dir)
    environment["PATH"] = str(java_home / "bin") + os.pathsep + environment.get("PATH", "")
    return environment


def _ghidra_details(environment: Mapping[str, str]) -> tuple[Path, str]:
    install = Path(environment["GHIDRA_INSTALL_DIR"])
    launcher = install / "support" / "analyzeHeadless.bat"
    if os.name != "nt":
        launcher = install / "support" / "analyzeHeadless"
    if not launcher.is_file():
        raise CacheError(f"Ghidra headless launcher 不存在：{launcher}")
    properties = install / "Ghidra" / "application.properties"
    version = "unknown"
    if properties.is_file() and properties.stat().st_size <= MAX_JSON_BYTES:
        for line in properties.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("application.version="):
                version = line.partition("=")[2].strip() or version
                break
    return launcher, version


def _resolve_target(binary: Path | None) -> tuple[Path, dict[str, Any], str]:
    if binary is None:
        try:
            from work.local_config import game_exe
        except ImportError as exc:
            raise CacheError("无法从 work.local_config.game_exe 定位 EU4 EXE") from exc
        target = game_exe()
    else:
        target = binary
    target = target.expanduser().resolve(strict=True)
    if target.name.casefold() != ALLOWED_PROGRAM:
        raise CacheError(f"目标文件名必须为 {ALLOWED_PROGRAM!r}，收到 {target.name!r}")
    registry = load_catalog()
    check = validate_catalog(registry, binary_path=target)
    if not check.valid:
        raise CacheError("目标 EXE 与逆向索引不匹配：" + "; ".join(check.error_messages))
    if check.binary_sha256 is None:
        raise CacheError("无法得到目标 EXE SHA-256")
    return target, registry, check.binary_sha256


def _target_from_cache(cache: Path) -> tuple[Path, dict[str, Any], str, dict[str, Any]]:
    metadata_path = cache / "build.json"
    if not metadata_path.is_file():
        raise CacheError(f"缓存缺少 build.json：{cache}")
    metadata = _read_json(metadata_path)
    if not isinstance(metadata, dict):
        raise CacheError("build.json 顶层必须是对象")
    _validate_cache_names(metadata)
    expected = metadata.get("target_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise CacheError("build.json 缺少有效 target_sha256")
    program = metadata["program"]
    input_path = cache / "input" / program
    if not input_path.is_file():
        raise CacheError(f"缓存缺少导入副本：{input_path}")
    actual = _hash_file(input_path)
    if actual.lower() != expected.lower():
        raise CacheError(f"缓存导入副本 SHA-256 不匹配：期望 {expected}，实际 {actual}")
    registry = load_catalog()
    check = validate_catalog(registry, binary_path=input_path)
    if not check.valid:
        raise CacheError("缓存 EXE 与逆向索引不匹配：" + "; ".join(check.error_messages))
    return input_path, registry, actual, metadata


def _lock_owner(lock_path: Path) -> dict[str, Any]:
    try:
        data = _read_json(lock_path, max_bytes=64 * 1024)
    except CacheError as exc:
        return {"read_error": str(exc), "present": True, "alive": None}
    if not isinstance(data, dict):
        return {"raw": data, "present": True, "alive": None}
    owner = dict(data)
    owner["present"] = True
    pid = owner.get("pid")
    expected_create = owner.get("process_create_time")
    alive = False
    identity: dict[str, Any] = {}
    if isinstance(pid, int) and pid > 0:
        try:
            process = psutil.Process(pid)
            actual_create = process.create_time()
            same = expected_create is None or abs(float(expected_create) - actual_create) < 0.01
            alive = same and process.is_running()
            identity = {
                "pid": pid,
                "process_name": process.name(),
                "process_create_time": actual_create,
                "same_process_identity": same,
                "command": process.cmdline(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, OSError):
            alive = False
    owner["alive"] = alive
    owner["identity"] = identity
    return owner


class _CacheLock:
    def __init__(self, cache: Path) -> None:
        self.path = cache / LOCK_NAME
        self.token = uuid.uuid4().hex
        self.held = False

    def acquire(self) -> None:
        payload = {
            "schema_version": LOCK_SCHEMA_VERSION,
            "token": self.token,
            "pid": os.getpid(),
            "process_create_time": psutil.Process(os.getpid()).create_time(),
            "process_name": psutil.Process(os.getpid()).name(),
            "command": sys.argv,
            "cwd": str(Path.cwd()),
            "hostname": socket.gethostname(),
            "created_at": _utc_now(),
        }
        try:
            handle = self.path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            owner = _lock_owner(self.path)
            rendered = json.dumps(owner, ensure_ascii=False, indent=2)
            raise CacheError(f"缓存已被锁定；不会自动删除锁文件 {self.path}\n{rendered}") from exc
        try:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        self.held = True

    def release(self) -> None:
        if not self.held:
            return
        try:
            current = _read_json(self.path, max_bytes=64 * 1024)
            if isinstance(current, Mapping) and current.get("token") == self.token:
                self.path.unlink()
        except (CacheError, FileNotFoundError):
            pass
        finally:
            self.held = False

    def __enter__(self) -> "_CacheLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def _write_initial_metadata(
    cache: Path,
    *,
    program: str,
    digest: str,
    ghidra_version: str,
    analysis_timeout: int,
) -> dict[str, Any]:
    metadata = {
        "directory": str(cache),
        "project_name": PROJECT_NAME,
        "program": program,
        "target_sha256": digest,
        "ghidra_version": ghidra_version,
        "java_heap": JAVA_HEAP,
        "java_tool_options": JAVA_TOOL_OPTIONS,
        "max_cpu": MAX_CPU,
        "memory_limit_bytes": MEMORY_LIMIT_BYTES,
        "analysis_budget_seconds": analysis_timeout,
        "status": "initializing",
        "stages": [],
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    _write_json(cache / "build.json", metadata)
    return metadata


def _update_metadata(cache: Path, metadata: dict[str, Any]) -> None:
    metadata["updated_at"] = _utc_now()
    _write_json(cache / "build.json", metadata)


def _is_ghidra_java(process: psutil.Process) -> tuple[bool, list[str]]:
    try:
        command = process.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False, []
    lowered = " ".join(command).casefold()
    name = process.name().casefold()
    verified = (
        name in {"java.exe", "javaw.exe", "java"}
        and "ghidra.app.util.headless.analyzeheadless" in lowered
        and "-max-cpu" in lowered
    )
    return verified, command


def _process_memory(process: psutil.Process) -> dict[str, int | None]:
    try:
        info = process.memory_full_info()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        # The basic Windows memory record still exposes VMS when USS/private
        # counters are restricted.  Use that conservative value rather than
        # silently dropping supervision.
        info = process.memory_info()
    private = getattr(info, "private", None)
    pagefile = getattr(info, "pagefile", None)
    vms = getattr(info, "vms", None)
    private_int = int(private) if isinstance(private, (int, float)) and private else None
    committed_int = int(pagefile) if isinstance(pagefile, (int, float)) and pagefile else private_int
    vms_int = int(vms) if isinstance(vms, (int, float)) and vms else None
    return {
        "private_bytes": private_int,
        "committed_bytes": committed_int,
        "vms_bytes": vms_int,
    }


def _iter_owned(process: psutil.Popen) -> list[psutil.Process]:
    try:
        return process.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []


def _stop(process: psutil.Process, *, verified_ghidra: bool = False) -> None:
    """Stop an owned process; callers must verify Java command before using it."""

    if verified_ghidra:
        verified, _ = _is_ghidra_java(process)
        if not verified:
            return
    try:
        process.terminate()
        process.wait(timeout=5)
    except psutil.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def _cleanup_owned(root_process: psutil.Popen, known: Mapping[int, Mapping[str, Any]]) -> None:
    # First stop verified Ghidra Java children, then the directly owned launcher
    # process.  Re-check the command line immediately before every Java stop.
    for child in reversed(_iter_owned(root_process)):
        verified, _ = _is_ghidra_java(child)
        if verified:
            _stop(child, verified_ghidra=True)
    if root_process.poll() is None:
        _stop(root_process)
    # A descendant may briefly survive the launcher.  Only kill an exact,
    # identity-matched Ghidra process; unrelated reused PIDs are left alone.
    for pid, row in known.items():
        try:
            process = psutil.Process(pid)
            same = abs(process.create_time() - float(row["create_time"])) < 0.01
            if same:
                verified, _ = _is_ghidra_java(process)
                if verified:
                    _stop(process, verified_ghidra=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError, ValueError):
            continue


def _remaining_owned(known: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    remaining: list[dict[str, Any]] = []
    for pid, row in known.items():
        try:
            process = psutil.Process(pid)
            same = abs(process.create_time() - float(row["create_time"])) < 0.01
            if same:
                verified, command = _is_ghidra_java(process)
                if verified:
                    remaining.append({"pid": pid, "create_time": row["create_time"], "command": command})
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError, ValueError):
            continue
    return remaining


def _stage_paths(cache: Path, stage: str, attempt: int) -> dict[str, Path]:
    suffix = "" if attempt == 1 else f"-{attempt}"
    return {
        "status": cache / f"{stage}{suffix}-status.json",
        "log": cache / f"{stage}{suffix}.log",
        "script_log": cache / f"{stage}{suffix}-scripts.log",
        "console": cache / f"{stage}{suffix}-console.log",
    }


def _next_attempt(metadata: Mapping[str, Any], stage: str) -> int:
    stages = metadata.get("stages", [])
    if not isinstance(stages, list):
        return 1
    return 1 + sum(1 for item in stages if isinstance(item, Mapping) and item.get("stage") == stage)


def _run_stage(
    cache: Path,
    metadata: dict[str, Any],
    *,
    stage: str,
    input_path: Path,
    analysis_timeout: int,
    environment: Mapping[str, str],
    launcher: Path,
    script: Path,
    attempt: int,
) -> tuple[int, str, dict[str, Any], Path]:
    paths = _stage_paths(cache, stage, attempt)
    command = [str(launcher), str(cache / "project"), PROJECT_NAME]
    if stage == "import":
        command.extend(["-import", str(input_path), "-noanalysis"])
        supervisor_timeout = IMPORT_SUPERVISOR_TIMEOUT
    else:
        command.extend(["-process", metadata["program"], "-analysisTimeoutPerFile", str(analysis_timeout)])
        supervisor_timeout = analysis_timeout + 120
    command.extend(
        [
            "-max-cpu",
            str(MAX_CPU),
            "-scriptPath",
            str(script.parent),
            "-postScript",
            str(script),
            str(paths["status"]),
            str(metadata["target_sha256"]),
            stage,
            "-log",
            str(paths["log"]),
            "-scriptlog",
            str(paths["script_log"]),
        ]
    )
    # Avoid truncating a previous checkpoint's logs on resume.
    with paths["console"].open("ab") as console:
        started = time.monotonic()
        process = psutil.Popen(command, env=dict(environment), stdout=console, stderr=console)
        known: dict[int, dict[str, Any]] = {}
        reason = "completed"
        peak_private = 0
        peak_committed = 0
        peak_vms = 0
        stop_requested = False
        last_report = 0.0
        try:
            while process.poll() is None:
                for child in _iter_owned(process):
                    verified, command_line = _is_ghidra_java(child)
                    if not verified:
                        continue
                    try:
                        identity = known.setdefault(
                            child.pid,
                            {
                                "pid": child.pid,
                                "create_time": child.create_time(),
                                "verified_owned_command": True,
                                "command": command_line,
                                "peak_private_bytes": 0,
                                "peak_committed_bytes": 0,
                                "peak_vms_bytes": 0,
                                "stopped_for_limit": False,
                            },
                        )
                        memory = _process_memory(child)
                        private = memory["private_bytes"] or 0
                        committed = memory["committed_bytes"] or 0
                        vms = memory["vms_bytes"] or 0
                        identity["peak_private_bytes"] = max(identity["peak_private_bytes"], private)
                        identity["peak_committed_bytes"] = max(identity["peak_committed_bytes"], committed)
                        identity["peak_vms_bytes"] = max(identity["peak_vms_bytes"], vms)
                        peak_private = max(peak_private, private)
                        peak_committed = max(peak_committed, committed)
                        peak_vms = max(peak_vms, vms)
                        over_limit = max(private, committed, vms) > MEMORY_LIMIT_BYTES
                        elapsed = time.monotonic() - started
                        if over_limit or elapsed > supervisor_timeout:
                            reason = "memory_limit" if over_limit else "supervisor_deadline"
                            identity["stopped_for_limit"] = over_limit
                            stop_requested = True
                            _stop(child, verified_ghidra=True)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                        continue
                elapsed = time.monotonic() - started
                if elapsed - last_report >= 30:
                    print(
                        json.dumps(
                            {
                                "stage": stage,
                                "attempt": attempt,
                                "elapsed_seconds": round(elapsed),
                                "peak_private_bytes": peak_private,
                                "peak_committed_bytes": peak_committed,
                                "peak_vms_bytes": peak_vms,
                                "peak_private_mib": round(peak_private / 1024**2, 1),
                                "peak_committed_mib": round(peak_committed / 1024**2, 1),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    last_report = elapsed
                if elapsed > supervisor_timeout:
                    reason = "supervisor_deadline"
                    stop_requested = True
                if stop_requested:
                    _cleanup_owned(process, known)
                    break
                time.sleep(1)
        finally:
            _cleanup_owned(process, known)
        exit_code = process.poll()
        if exit_code is None:
            try:
                exit_code = process.wait(timeout=10)
            except psutil.TimeoutExpired:
                _stop(process)
                exit_code = process.poll()
        if exit_code is None:
            exit_code = -1
    remaining = _remaining_owned(known)
    if remaining:
        reason = "analysis_process_cleanup_incomplete"
        exit_code = 1
    report: dict[str, Any] | None = None
    if paths["status"].is_file():
        try:
            value = _read_json(paths["status"])
            if isinstance(value, dict):
                report = value
        except CacheError:
            report = None
    if report is None:
        report = {}
    if stage == "analysis" and report.get("analysis_timed_out") is True:
        reason = "analysis_timeout_reported"
    elif stage == "analysis" and report.get("default_auto_analysis_completed") is not True:
        if exit_code == 0 and reason == "completed":
            reason = "analysis_incomplete"
            exit_code = 1
    if exit_code != 0 and reason == "completed":
        reason = "provider_failed"
    result = {
        "stage": stage,
        "attempt": attempt,
        "exit_code": exit_code,
        "reason": reason,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "command": command,
        "java_heap": JAVA_HEAP,
        "max_cpu": MAX_CPU,
        "memory_limit_bytes": MEMORY_LIMIT_BYTES,
        "peak_private_bytes": peak_private,
        "peak_committed_bytes": peak_committed,
        "peak_vms_bytes": peak_vms,
        "processes": list(known.values()),
        "remaining_owned_java": remaining,
        "report_path": str(paths["status"]),
        "log_path": str(paths["log"]),
        "script_log_path": str(paths["script_log"]),
        "console_path": str(paths["console"]),
    }
    return exit_code, reason, {"report": report, "result": result}, paths["status"]


def _stage_complete(metadata: Mapping[str, Any], stage: str) -> bool:
    if stage == "import":
        report = metadata.get("import_report")
        return (
            isinstance(report, Mapping)
            and report.get("analysis_timed_out") is False
            and (metadata.get("status") in {"imported", "analyzing", "complete"})
        )
    report = metadata.get("analysis_report")
    return (
        isinstance(report, Mapping)
        and report.get("analysis_timed_out") is False
        and report.get("default_auto_analysis_completed") is True
        and metadata.get("status") == "complete"
    )


def _project_present(cache: Path, metadata: Mapping[str, Any]) -> bool:
    _validate_cache_names(metadata)
    project = cache / "project"
    name = metadata.get("project_name", PROJECT_NAME)
    return (
        project.is_dir()
        and (project / f"{name}.gpr").is_file()
        and (project / f"{name}.rep").is_dir()
        and (project / f"{name}.rep" / "project.prp").is_file()
    )


def _project_locked(cache: Path, metadata: Mapping[str, Any]) -> bool:
    _validate_cache_names(metadata)
    project = cache / "project"
    name = metadata.get("project_name", PROJECT_NAME)
    return (project / f"{name}.lock").exists() or (project / f"{name}.lock~").exists()


def _cache_path(cache: Path, raw: Any) -> Path | None:
    """Resolve a recorded artifact path only when it remains inside cache."""

    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = cache / candidate
    try:
        candidate = candidate.resolve(strict=False)
        candidate.relative_to(cache.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _analysis_attempt_number(record: Mapping[str, Any]) -> int | None:
    value = record.get("attempt")
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def _latest_analysis_attempt(metadata: Mapping[str, Any]) -> Mapping[str, Any] | None:
    stages = metadata.get("stages", [])
    if not isinstance(stages, list):
        return None
    candidates: list[tuple[tuple[int, int, int], Mapping[str, Any]]] = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, Mapping) or stage.get("stage") != "analysis":
            continue
        attempt = _analysis_attempt_number(stage)
        # New records carry an explicit numeric attempt.  Older scratch
        # records do not, so their list order remains the fallback.
        sort_key = (1, attempt, index) if attempt is not None else (0, -1, index)
        candidates.append((sort_key, stage))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _fallback_analysis_paths(cache: Path, attempt: int | None) -> dict[str, list[Path]]:
    """Return bounded fallback paths for old scratch stage records.

    A record without an ``attempt`` is the format emitted by the original
    scratch runner, whose files use the base names.  An explicit later attempt
    must use its own suffixed files; it may never silently reuse attempt 1.
    """

    suffix = "" if attempt is None or attempt == 1 else f"-{attempt}"
    return {
        "report": [cache / f"analysis{suffix}-status.json"],
        "log": [cache / f"analysis{suffix}.log"],
        "console": [cache / f"analysis{suffix}-console.log"],
        "script_log": [cache / f"analysis{suffix}-scripts.log"],
    }


def _latest_analysis_paths(cache: Path, metadata: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, dict[str, list[Path]]]:
    """Select status/log files from the latest analysis stage record."""

    record = _latest_analysis_attempt(metadata)
    if record is None:
        return None, {"report": [], "log": [], "console": [], "script_log": []}
    attempt = _analysis_attempt_number(record)
    fallbacks = _fallback_analysis_paths(cache, attempt)
    field_names = {
        "report": "report_path",
        "log": "log_path",
        "console": "console_path",
        "script_log": "script_log_path",
    }
    selected: dict[str, list[Path]] = {}
    for kind, field in field_names.items():
        paths: list[Path] = []
        recorded = _cache_path(cache, record.get(field))
        if recorded is not None:
            paths.append(recorded)
        for fallback in fallbacks[kind]:
            if fallback not in paths:
                paths.append(fallback)
        selected[kind] = paths
    return record, selected


_SAVE_SUCCESS_RE = re.compile(r"REPORT:\s*Save succeeded for(?: processed file)?:\s*/([^\s(]+)", re.IGNORECASE)
_SAVE_FAILURE_RE = re.compile(
    r"REPORT:\s*Save failed\b|\b(?:OutOfMemoryError|Java heap space|OOM)\b|"
    r"\bERROR\b[^\r\n]*(?:OOM|OutOfMemory|Java heap|Save failed)",
    re.IGNORECASE,
)


def _save_log_evidence(paths: Iterable[Path], program: str) -> dict[str, Any]:
    """Check bounded log tails for a matching save and fatal markers."""

    expected = f"/{program}".casefold()
    success_lines: list[str] = []
    failure_markers: list[str] = []
    scanned: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        scanned.append(str(path))
        text = _bounded_tail(path)
        for line in text.splitlines():
            match = _SAVE_SUCCESS_RE.search(line)
            if match and f"/{match.group(1)}".casefold() == expected:
                success_lines.append(line.strip())
            elif match:
                failure_markers.append(f"save-target-mismatch: {line.strip()}")
            failure = _SAVE_FAILURE_RE.search(line)
            if failure:
                failure_markers.append(line.strip())
    return {
        "scanned": scanned,
        "save_success_lines": success_lines,
        "failure_markers": failure_markers,
        "save_succeeded": bool(success_lines) and not failure_markers,
    }


def _project_save_evidence(cache: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return file/log evidence that a headless project was actually saved."""

    _validate_cache_names(metadata)
    project = cache / "project"
    name = metadata.get("project_name", PROJECT_NAME)
    latest_attempt, selected_paths = _latest_analysis_paths(cache, metadata)

    def first_existing(paths: list[Path], fallback: Path) -> Path:
        for path in paths:
            if path.is_file():
                return path
        return paths[0] if paths else fallback

    files = {
        "gpr": project / f"{name}.gpr",
        "rep": project / f"{name}.rep",
        "project_prp": project / f"{name}.rep" / "project.prp",
        "analysis_report": first_existing(selected_paths["report"], cache / "analysis-status.json"),
        "analysis_log": first_existing(selected_paths["log"], cache / "analysis.log"),
        "analysis_console": first_existing(selected_paths["console"], cache / "analysis-console.log"),
        "analysis_script_log": first_existing(selected_paths["script_log"], cache / "analysis-scripts.log"),
    }
    file_state = {key: path.is_file() or (key == "rep" and path.is_dir()) for key, path in files.items()}
    # A live/stale Ghidra project lock means the project is not yet safely
    # published as a completed cache.  It is reported separately for status.
    file_state["project_lock_absent"] = not (project / f"{name}.lock").exists()
    file_state["project_lock_tilde_absent"] = not (project / f"{name}.lock~").exists()
    file_state["analysis_log_nonempty"] = files["analysis_log"].is_file() and files["analysis_log"].stat().st_size > 0
    file_state["analysis_console_nonempty"] = files["analysis_console"].is_file() and files["analysis_console"].stat().st_size > 0
    file_state["analysis_script_log_nonempty"] = files["analysis_script_log"].is_file() and files["analysis_script_log"].stat().st_size > 0

    metadata_report = metadata.get("analysis_report")
    latest_report: dict[str, Any] | None = None
    if files["analysis_report"].is_file():
        try:
            loaded = _read_json(files["analysis_report"])
            if isinstance(loaded, dict):
                latest_report = loaded
        except CacheError:
            latest_report = None
    report_matches_metadata = isinstance(metadata_report, Mapping) and latest_report == dict(metadata_report)
    report_target_matches = (
        isinstance(latest_report, Mapping)
        and latest_report.get("target_sha256") == metadata.get("target_sha256")
        and latest_report.get("program") == metadata.get("program")
    )
    report_flags_ok = (
        isinstance(latest_report, Mapping)
        and latest_report.get("stage") == "analysis"
        and latest_report.get("analysis_timed_out") is False
        and latest_report.get("default_auto_analysis_completed") is True
    )
    stage_ok = (
        isinstance(latest_attempt, Mapping)
        and latest_attempt.get("exit_code") == 0
        and latest_attempt.get("reason") == "completed"
    )
    all_log_paths = selected_paths["log"] + selected_paths["console"] + selected_paths["script_log"]
    log_evidence = _save_log_evidence(all_log_paths, str(metadata.get("program", "")))
    required_files = all(
        file_state[key]
        for key in (
            "gpr",
            "rep",
            "project_prp",
            "analysis_report",
            "analysis_log",
            "analysis_console",
            "analysis_script_log",
            "project_lock_absent",
            "project_lock_tilde_absent",
        )
    )
    return {
        "files": {key: str(path) for key, path in files.items()},
        "present": file_state,
        "latest_analysis_attempt": dict(latest_attempt) if isinstance(latest_attempt, Mapping) else None,
        "latest_analysis_report": latest_report,
        "report_matches_metadata": report_matches_metadata,
        "report_target_matches": report_target_matches,
        "report_flags_ok": report_flags_ok,
        "stage_ok": stage_ok,
        "log_evidence": log_evidence,
        "saved": (
            required_files
            and (
                file_state["analysis_log_nonempty"]
                or file_state["analysis_console_nonempty"]
                or file_state["analysis_script_log_nonempty"]
            )
            and stage_ok
            and report_matches_metadata
            and report_target_matches
            and report_flags_ok
            and log_evidence["save_succeeded"]
        ),
    }


def _complete_evidence(cache: Path, metadata: Mapping[str, Any]) -> bool:
    _validate_cache_names(metadata)
    expected_digest = metadata.get("target_sha256")
    input_path = cache / "input" / ALLOWED_PROGRAM
    if not isinstance(expected_digest, str) or not input_path.is_file():
        return False
    try:
        if _hash_file(input_path).casefold() != expected_digest.casefold():
            return False
    except OSError:
        return False
    if not _project_present(cache, metadata):
        return False
    evidence = _project_save_evidence(cache, metadata)
    # Re-read the report selected for the latest analysis attempt.  The nested
    # build.json copy is only accepted when it is byte-for-byte equivalent to
    # that bounded report and the report identifies this exact target.
    return bool(
        evidence["saved"]
        and evidence["report_matches_metadata"]
        and evidence["report_target_matches"]
        and evidence["report_flags_ok"]
        and evidence["stage_ok"]
        and evidence["log_evidence"]["save_succeeded"]
    )


def _analysis_java_gone(metadata: Mapping[str, Any]) -> bool:
    """Require explicit evidence that the latest analysis Java is gone."""

    record = _latest_analysis_attempt(metadata)
    if not isinstance(record, Mapping):
        return False
    remaining = record.get("remaining_owned_java")
    if isinstance(remaining, list):
        if remaining:
            return False
    elif "processes" not in record:
        return False
    processes = record.get("processes")
    if not isinstance(processes, list):
        return False
    return all(
        isinstance(process, Mapping) and process.get("still_running_same_process") is False
        for process in processes
    )


def _latest_pointer_path() -> Path:
    return project_root() / "work" / "runtime" / "ghidra-full" / "latest.json"


def _publish_latest(cache: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically publish a verified completed cache pointer."""

    _validate_cache_names(metadata)
    if metadata.get("status") != "complete" or not _complete_evidence(cache, metadata):
        raise CacheError("拒绝发布未完成或证据不完整的分析缓存")
    if not _analysis_java_gone(metadata):
        raise CacheError("拒绝发布：最新分析尝试没有明确证明 Java 进程已退出")
    manifest = cache / "build.json"
    if not manifest.is_file():
        raise CacheError(f"缓存缺少 build.json：{manifest}")
    pointer = {
        "cache": str(cache.resolve()),
        "target_sha256": metadata["target_sha256"],
        "build_manifest_sha256": _hash_file(manifest),
    }
    latest = _latest_pointer_path()
    latest.parent.mkdir(parents=True, exist_ok=True)
    _write_json(latest, pointer)
    return pointer


def _run_build(*, binary: Path | None, output: Path | None, config_path: Path, analysis_timeout: int) -> int:
    target, _registry, digest = _resolve_target(binary)
    config = _load_config(config_path)
    environment = _analysis_environment(config)
    launcher, ghidra_version = _ghidra_details(environment)
    script = Path(__file__).with_name(STATUS_SCRIPT_NAME).resolve(strict=True)
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = project_root() / "work" / "runtime" / "ghidra-full" / f"{digest[:16]}-{stamp}-{uuid.uuid4().hex[:6]}"
    cache = output.expanduser().resolve()
    if cache.exists():
        raise CacheError(f"--output 必须是全新的目录，拒绝覆盖：{cache}")
    cache.mkdir(parents=True)
    (cache / "project").mkdir()
    (cache / "input").mkdir()
    copy_path = cache / "input" / ALLOWED_PROGRAM
    try:
        with _CacheLock(cache):
            shutil.copyfile(target, copy_path)
            copied_digest = _hash_file(copy_path)
            if copied_digest.lower() != digest.lower():
                raise CacheError(f"导入副本哈希不匹配：期望 {digest}，实际 {copied_digest}")
            metadata = _write_initial_metadata(
                cache,
                program=ALLOWED_PROGRAM,
                digest=digest,
                ghidra_version=ghidra_version,
                analysis_timeout=analysis_timeout,
            )
            metadata["input_path"] = str(copy_path)
            metadata["project_path"] = str(cache / "project")
            _update_metadata(cache, metadata)
            metadata["status"] = "importing"
            _update_metadata(cache, metadata)
            exit_code, _reason, details, _status_path = _run_stage(
                cache,
                metadata,
                stage="import",
                input_path=copy_path,
                analysis_timeout=analysis_timeout,
                environment=environment,
                launcher=launcher,
                script=script,
                attempt=1,
            )
            metadata.setdefault("stages", []).append(details["result"])
            metadata["import_report"] = details["report"]
            metadata["status"] = "imported" if exit_code == 0 and _project_present(cache, metadata) else "incomplete"
            _update_metadata(cache, metadata)
            if exit_code != 0 or metadata["status"] != "imported":
                print(json.dumps({"status": metadata["status"], "directory": str(cache)}, ensure_ascii=False), flush=True)
                return 1
            metadata["status"] = "analyzing"
            _update_metadata(cache, metadata)
            exit_code, _reason, details, _status_path = _run_stage(
                cache,
                metadata,
                stage="analysis",
                input_path=copy_path,
                analysis_timeout=analysis_timeout,
                environment=environment,
                launcher=launcher,
                script=script,
                attempt=1,
            )
            metadata.setdefault("stages", []).append(details["result"])
            metadata["analysis_report"] = details["report"]
            metadata["status"] = (
                "complete"
                if exit_code == 0
                and _complete_evidence(cache, metadata)
                else "incomplete"
            )
            _update_metadata(cache, metadata)
            if metadata["status"] == "complete":
                _publish_latest(cache, metadata)
            print(json.dumps({"status": metadata["status"], "directory": str(cache)}, ensure_ascii=False), flush=True)
            return 0 if metadata["status"] == "complete" else 1
    except Exception as exc:
        if cache.exists():
            try:
                metadata = _read_json(cache / "build.json")
                if isinstance(metadata, dict):
                    metadata["status"] = "incomplete"
                    metadata["error"] = str(exc)
                    _update_metadata(cache, metadata)
            except Exception:
                pass
        raise


def _run_resume(*, cache_path: Path, config_path: Path, analysis_timeout: int | None) -> int:
    cache = cache_path.expanduser().resolve(strict=True)
    input_path, _registry, digest, metadata = _target_from_cache(cache)
    if metadata.get("status") == "complete" and _complete_evidence(cache, metadata):
        with _CacheLock(cache):
            metadata = _read_json(cache / "build.json")
            if not isinstance(metadata, dict):
                raise CacheError("build.json 顶层必须是对象")
            metadata["java_tool_options"] = JAVA_TOOL_OPTIONS
            _update_metadata(cache, metadata)
            _publish_latest(cache, metadata)
        print(json.dumps(_status_payload(cache), ensure_ascii=False), flush=True)
        return 0
    if not _project_present(cache, metadata):
        raise CacheError("缓存没有可恢复的 Ghidra 导入项目；resume 只接受已完成导入的 checkpoint")
    if _project_locked(cache, metadata):
        raise CacheError("Ghidra 项目仍有项目锁文件；请等待原分析进程结束后再 resume")
    if metadata.get("status") not in {"imported", "incomplete", "analyzing"}:
        raise CacheError(f"缓存状态不允许 resume：{metadata.get('status')!r}")
    budget = analysis_timeout if analysis_timeout is not None else int(metadata.get("analysis_budget_seconds", DEFAULT_ANALYSIS_TIMEOUT))
    if budget < 1:
        raise CacheError("analysis-timeout 必须是正整数")
    config = _load_config(config_path)
    environment = _analysis_environment(config)
    launcher, ghidra_version = _ghidra_details(environment)
    script = Path(__file__).with_name(STATUS_SCRIPT_NAME).resolve(strict=True)
    try:
        with _CacheLock(cache):
            metadata["target_sha256"] = digest
            metadata["ghidra_version"] = ghidra_version
            metadata["java_tool_options"] = environment["JAVA_TOOL_OPTIONS"]
            metadata["analysis_budget_seconds"] = budget
            metadata["status"] = "analyzing"
            _update_metadata(cache, metadata)
            attempt = _next_attempt(metadata, "analysis")
            exit_code, _reason, details, _status_path = _run_stage(
                cache,
                metadata,
                stage="analysis",
                input_path=input_path,
                analysis_timeout=budget,
                environment=environment,
                launcher=launcher,
                script=script,
                attempt=attempt,
            )
            metadata.setdefault("stages", []).append(details["result"])
            metadata["analysis_report"] = details["report"]
            metadata["status"] = (
                "complete"
                if exit_code == 0
                and _complete_evidence(cache, metadata)
                else "incomplete"
            )
            _update_metadata(cache, metadata)
            if metadata["status"] == "complete":
                _publish_latest(cache, metadata)
    except Exception as exc:
        if metadata.get("status") == "analyzing":
            metadata["status"] = "incomplete"
            metadata["error"] = str(exc)
            _update_metadata(cache, metadata)
        raise
    print(json.dumps({"status": metadata["status"], "directory": str(cache)}, ensure_ascii=False), flush=True)
    return 0 if metadata["status"] == "complete" else 1


def _status_payload(cache: Path) -> dict[str, Any]:
    metadata = _read_json(cache / "build.json")
    if not isinstance(metadata, dict):
        raise CacheError("build.json 顶层必须是对象")
    _validate_cache_names(metadata)
    lock = _lock_owner(cache / LOCK_NAME) if (cache / LOCK_NAME).exists() else {"present": False}
    save_evidence = _project_save_evidence(cache, metadata)
    report = save_evidence.get("latest_analysis_report")
    payload = dict(metadata)
    payload["cache_exists"] = True
    payload["project_present"] = _project_present(cache, metadata)
    payload["input_present"] = (cache / "input" / str(metadata.get("program", ""))).is_file()
    payload["lock"] = lock
    payload["project_save_evidence"] = save_evidence
    payload["default_auto_analysis_completed"] = bool(
        isinstance(report, Mapping) and report.get("default_auto_analysis_completed") is True
    )
    payload["analysis_timed_out"] = bool(isinstance(report, Mapping) and report.get("analysis_timed_out") is True)
    payload["complete"] = (
        payload["status"] == "complete"
        and _complete_evidence(cache, metadata)
        and not lock.get("present", False)
    )
    return payload


def _run_status(cache_path: Path) -> int:
    cache = cache_path.expanduser().resolve(strict=True)
    payload = _status_payload(cache)
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    return 0


def _run_publish(cache_path: Path) -> int:
    cache = cache_path.expanduser().resolve(strict=True)
    with _CacheLock(cache):
        _input_path, _registry, _digest, metadata = _target_from_cache(cache)
        pointer = _publish_latest(cache, metadata)
    print(json.dumps(pointer, ensure_ascii=False, indent=2), flush=True)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="创建新缓存、导入并完成默认分析")
    build.add_argument("--output", type=Path, help="全新的缓存目录")
    build.add_argument("--binary", type=Path, help="默认使用 work.local_config.game_exe")
    build.add_argument("--config", type=Path, default=Path.home() / ".codex" / "config.toml")
    build.add_argument("--analysis-timeout", type=int, default=DEFAULT_ANALYSIS_TIMEOUT, metavar="秒")

    status = subparsers.add_parser("status", help="只读查看缓存状态")
    status.add_argument("--cache", type=Path, required=True)

    publish = subparsers.add_parser("publish", help="验证并发布已完成缓存为 latest.json")
    publish.add_argument("--cache", type=Path, required=True)

    resume = subparsers.add_parser("resume", help="从已导入 checkpoint 继续默认分析")
    resume.add_argument("--cache", type=Path, required=True)
    resume.add_argument("--config", type=Path, default=Path.home() / ".codex" / "config.toml")
    resume.add_argument("--analysis-timeout", type=int, metavar="秒")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            if args.analysis_timeout < 1:
                parser.error("--analysis-timeout 必须是正整数")
            return _run_build(
                binary=args.binary,
                output=args.output,
                config_path=args.config.expanduser().resolve(),
                analysis_timeout=args.analysis_timeout,
            )
        if args.command == "status":
            return _run_status(args.cache)
        if args.command == "publish":
            return _run_publish(args.cache)
        if args.command == "resume":
            if args.analysis_timeout is not None and args.analysis_timeout < 1:
                parser.error("--analysis-timeout 必须是正整数")
            return _run_resume(
                cache_path=args.cache,
                config_path=args.config.expanduser().resolve(),
                analysis_timeout=args.analysis_timeout,
            )
        parser.error(f"未知命令：{args.command}")
    except (CacheError, OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

