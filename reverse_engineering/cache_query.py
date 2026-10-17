"""Query a completed persistent Ghidra project through REA's public CLI."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import psutil


from .catalog import project_root
from .ghidra_cache import (CacheError, _CacheLock, _complete_evidence, _hash_file,
                           _load_config, _read_json, _resolve_target, _target_from_cache, _write_json)
from .rea import _capture_logs, _owned_children, _stop_process

PRESET = "eu4-persistent-default-analysis-v1"


def database_commitment(cache: Path) -> str:
    """Commit the project files in streaming chunks, excluding OS lock files."""
    project = (cache / "project").resolve(strict=True)
    files = sorted(path for path in project.rglob("*") if path.is_file()
                   and not path.name.endswith((".lock", ".lock~")))
    if not files or len(files) > 8192:
        raise CacheError("Unexpected/unbounded persistent database file inventory")
    digest = hashlib.sha256()
    for path in files:
        if not path.resolve(strict=True).is_relative_to(project):
            raise CacheError("Database file escapes the selected project")
        digest.update(path.relative_to(project).as_posix().encode("utf-8"))
        digest.update(b"\0" + _hash_file(path).encode("ascii") + b"\n")
    return digest.hexdigest()


def latest_cache() -> Path | None:
    pointer = project_root() / "work/runtime/ghidra-full/latest.json"
    if not pointer.is_file():
        return None
    value = _read_json(pointer, max_bytes=65536)
    cache = Path(value["cache"])
    if not cache.is_absolute():
        raise CacheError("Latest cache pointer must be absolute")
    if _hash_file(cache / "build.json") != value["build_manifest_sha256"]:
        raise CacheError("Latest cache manifest changed; explicitly select and verify the cache")
    return cache


def publish_cache(cache: Path) -> None:
    metadata = _read_json(cache / "build.json")
    if metadata.get("status") != "complete" or not _complete_evidence(cache, metadata):
        raise CacheError("Refuse to publish an incomplete analysis cache")
    pointer = project_root() / "work/runtime/ghidra-full/latest.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    _write_json(pointer, {"cache": str(cache.resolve()), "target_sha256": metadata["target_sha256"],
                          "build_manifest_sha256": _hash_file(cache / "build.json")})


def query(args) -> int:
    target, registry, digest = _resolve_target(args.binary)
    cache = (args.cache or latest_cache()).resolve(strict=True)
    with _CacheLock(cache):
        _, _, cached_digest, metadata = _target_from_cache(cache)
        if cached_digest != digest or metadata.get("status") != "complete" or not _complete_evidence(cache, metadata):
            raise CacheError("缓存与目标不匹配，或默认自动分析尚未完整保存")
        if metadata["ghidra_version"] != "12.1.4":
            raise CacheError("缓存查询适配器仅验证了 Ghidra 12.1.4")
        database_sha = database_commitment(cache)
        manifest_sha = _hash_file(cache / "build.json")
        image_base = int(str(registry["binary"]["image_base"]), 0)
        selected = next((node for node in registry["nodes"] if node["id"] == args.node), None)
        if selected is not None:
            if selected.get("address_role") != "procedure_entry":
                raise CacheError("所选节点不是函数入口")
            procedure = f"{image_base + int(str(selected['rva']), 0):#x}"
        elif args.node.startswith("0x"):
            address = int(args.node, 16)
            procedure = f"{address if address >= image_base else image_base + address:#x}"
        else:
            # REA resolves exact analyzed names. Names are passed as argv, never shell text.
            procedure = args.node
        config = _load_config(args.config)
        cli = config["args"]
        if Path(config["command"]).name.lower() not in {"node", "node.exe"} or cli[-1] != "mcp":
            raise CacheError("缓存入口需要直接 Node + public scripts/rea.mjs 注册")
        entry = Path(cli[0]).resolve(strict=True)
        package = entry.parent.parent
        if _read_json(package / "package.json")["version"] != "6.4.0":
            raise CacheError("缓存入口只验证了 REA 6.4.0")
        loader = Path(__file__).with_name("rea_cache_loader.mjs").resolve(strict=True)
        environment = os.environ.copy()
        environment.update(config.get("env", {}))
        environment.pop("REA_GHIDRA_SEED_FILE", None)
        environment.update({"EU4_REA_PACKAGE_ROOT": str(package), "EU4_REA_CACHE_PROJECT": str(cache / "project"),
                            "EU4_REA_CACHE_MANIFEST": str(cache / "build.json"),
                            "EU4_REA_CACHE_DATABASE_SHA256": database_sha,
                            "REA_GHIDRA_STARTUP_TIMEOUT_MS": str(args.timeout * 1000), "GHIDRA_HEADLESS_MAXMEM": "512M"})
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = (args.output or project_root() / "work/runtime" / f"rea-cache-{stamp}-{uuid.uuid4().hex[:8]}").resolve()
        if output.is_relative_to(cache / "project"):
            raise CacheError("查询输出不能写入分析工程内部")
        output.mkdir(parents=True, exist_ok=False)
        command = [config["command"], "--import", loader.as_uri(), *cli[:-1], "function", str(target), procedure,
                   "--provider", "ghidra", "--format", "json"]
        request = {"target_sha256": digest, "node": args.node, "procedure": procedure, "cache": str(cache),
                   "preset": PRESET, "adapter_sha256": _hash_file(loader), "completed_manifest_sha256": manifest_sha,
                   "completed_database_sha256": database_sha, "query_reanalysis": False,
                   "java_heap": "512M", "process_memory_limit_bytes": 1024**3, "timeout_seconds": args.timeout}
        _write_json(output / "request.json", request)
        print(f"REA 持久化库查询：{procedure}；输出 {output}", flush=True)
        peaks = {}
        started = time.monotonic()
        reason = "completed"
        with (output / "evidence.json").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
            process = psutil.Popen(command, env=environment, stdout=stdout, stderr=stderr)
            last_report = 0
            try:
                while process.poll() is None:
                    for child in _owned_children(process, psutil):
                        try:
                            arguments = " ".join(child.cmdline()).lower()
                            if child.name().lower() not in {"java.exe", "javaw.exe"} or "ghidra" not in arguments or "analyzeheadless" not in arguments:
                                continue
                            private = getattr(child.memory_info(), "private", child.memory_info().vms)
                            row = peaks.setdefault(child.pid, {"pid": child.pid, "create_time": child.create_time(), "peak_committed_bytes": 0})
                            row["peak_committed_bytes"] = max(row["peak_committed_bytes"], private)
                            _capture_logs(child, output)
                            if private > 1024**3:
                                reason = "memory_limit"
                                _stop_process(child, psutil)
                        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                            continue
                    elapsed = time.monotonic() - started
                    if elapsed - last_report >= 30:
                        print(f"缓存查询等待 {elapsed:.0f}s", flush=True)
                        last_report = elapsed
                    if elapsed > args.timeout + 35:
                        reason = "supervisor_deadline"
                        break
                    time.sleep(1)
            finally:
                if process.poll() is None:
                    for child in reversed(_owned_children(process, psutil)):
                        _stop_process(child, psutil)
                    _stop_process(process, psutil)
            exit_code = process.wait(timeout=15)
        for row in peaks.values():
            try:
                remaining = psutil.Process(row["pid"])
                if remaining.create_time() == row["create_time"]:
                    arguments = " ".join(remaining.cmdline()).lower()
                    if "ghidra" in arguments and "analyzeheadless" in arguments:
                        _stop_process(remaining, psutil)
                row["still_running_same_process"] = remaining.is_running() and remaining.create_time() == row["create_time"]
            except psutil.NoSuchProcess:
                row["still_running_same_process"] = False
        evidence = _read_json(output / "evidence.json") if (output / "evidence.json").stat().st_size else None
        if exit_code == 0:
            profile = evidence.get("analysis_profile", {}).get("parameters", {}) if isinstance(evidence, dict) else {}
            result = evidence.get("raw_result", {}).get("value", {}) if isinstance(evidence, dict) else {}
            valid = profile.get("analyzer_preset") == PRESET and profile.get("local_adapter_sha256") == request["adapter_sha256"] and profile.get("completed_manifest_sha256") == manifest_sha and profile.get("completed_database_sha256") == database_sha
            valid = valid and evidence.get("subject", {}).get("digest", {}).get("sha256") == digest
            valid = valid and evidence.get("provider", {}).get("version") == metadata["ghidra_version"]
            valid = valid and result.get("assembly") and result.get("pseudocode") and result.get("procedure", {}).get("body", {}).get("contains_entry")
            if not valid:
                exit_code, reason = 1, "cached_result_readback_failed"
        if database_commitment(cache) != database_sha:
            exit_code, reason = 1, "read_only_database_changed"
        if any(row.get("still_running_same_process") for row in peaks.values()):
            exit_code, reason = 1, "process_cleanup_incomplete"
        if exit_code and reason == "completed":
            reason = "provider_failed"
        summary = {**request, "exit_code": exit_code, "reason": reason, "elapsed_seconds": round(time.monotonic() - started, 2),
                   "processes": list(peaks.values()), "database_unchanged": reason != "read_only_database_changed",
                   "evidence_id": evidence.get("evidence_id") if isinstance(evidence, dict) else None}
        _write_json(output / "run.json", summary)
        print(json.dumps({key: summary[key] for key in ["exit_code", "reason", "elapsed_seconds", "evidence_id"]}), flush=True)
        return exit_code
