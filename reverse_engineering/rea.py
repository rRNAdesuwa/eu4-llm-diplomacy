"""Run a hash-bound REA function query with bounded memory.

Reuse a published completed Ghidra project when available. Explicit seeded mode
uses bounded PE unwind ranges in a temporary database with incomplete global
references. Both routes use a process-local adapter and the installed public
REA CLI; the installed packages and the original executable remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
import uuid

from .catalog import load_catalog, project_root, validate_catalog
from .pe_ranges import unwind_ranges

PRESET = "eu4-declared-seeds-pdata-noanalysis-v2"
MEMORY_LIMIT = 1024**3


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture_logs(child, destination: Path) -> None:
    arguments = child.cmdline()
    for flag, filename in (("-log", "ghidra-tail.log"), ("-scriptlog", "script-tail.log")):
        if flag not in arguments:
            continue
        path = Path(arguments[arguments.index(flag) + 1])
        if not path.parent.name.startswith("rea-ghidra-") or not path.is_file():
            continue
        with path.open("rb") as source:
            source.seek(max(0, path.stat().st_size - 65536))
            (destination / filename).write_bytes(source.read(65536))


def _owned_children(process, psutil):
    try:
        return process.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []


def _stop_process(process, psutil) -> None:
    try:
        process.terminate()
        process.wait(timeout=5)
    except psutil.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    except psutil.NoSuchProcess:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("node", help="函数入口节点 ID；完整缓存模式也支持 RVA / 静态 VA / 准确符号名")
    parser.add_argument("--seed", action="append", default=[], help="另一个已确认函数入口节点；可重复")
    parser.add_argument("--cache", type=Path, help="复用完整持久化 Ghidra 分析库；默认选择已发布的最新库")
    parser.add_argument("--seeded", action="store_true", help="显式使用原有按入口有界分析，不读取完整库")
    parser.add_argument("--binary", type=Path, help="默认使用 local.env 的 EU4_GAME_ROOT/eu4.exe")
    parser.add_argument("--config", type=Path, default=Path.home() / ".codex/config.toml")
    parser.add_argument("--output", type=Path, help="新输出目录；已有目录不会覆盖")
    parser.add_argument("--timeout", type=int, default=180, help="首个查询时限，秒；允许 30–900")
    args = parser.parse_args(argv)
    try:
        import psutil
    except ImportError:
        parser.error("按需分析入口需要 psutil 监测实际进程内存；索引查询无需该依赖。")
    if not 30 <= args.timeout <= 900:
        parser.error("--timeout 必须在 30–900 秒之间")
    if args.cache and (args.seeded or args.seed):
        parser.error("缓存只读查询不能同时配置 --seed / --seeded")
    if args.cache or not (args.seeded or args.seed):
        from .cache_query import latest_cache, query
        from .ghidra_cache import CacheError
        try:
            if args.cache or latest_cache() is not None:
                return query(args)
        except (CacheError, OSError, ValueError, KeyError) as error:
            parser.error(str(error))
    registry = load_catalog()
    check = validate_catalog(registry)
    if not check.valid:
        parser.error("索引合同无效：" + "; ".join(check.error_messages))
    index = {node["id"]: node for node in registry["nodes"]}
    selected = list(dict.fromkeys([args.node, *args.seed]))
    if len(selected) > 32:
        parser.error("一次最多声明 32 个函数入口")
    for key in selected:
        node = index.get(key)
        if node is None or node.get("address_role") != "procedure_entry" or "rva" not in node:
            parser.error(f"{key!r} 不是索引中已记录的函数入口")
    if args.binary is None:
        from work.local_config import game_exe
        target = game_exe().resolve(strict=True)
    else:
        target = args.binary.resolve(strict=True)
    binary_check = validate_catalog(registry, binary_path=target)
    if not binary_check.valid:
        parser.error("目标不匹配：" + "; ".join(binary_check.error_messages))
    try:
        ranges = unwind_ranges(target, [int(str(index[key]["rva"]), 0) for key in selected])
    except ValueError as error:
        parser.error(str(error))
    config = tomllib.loads(args.config.read_text(encoding="utf-8-sig"))["mcp_servers"]["rea"]
    node_command = config["command"]
    cli_arguments = config["args"]
    if Path(node_command).name.lower() not in {"node", "node.exe"} or cli_arguments[-1] != "mcp":
        parser.error("此入口需要现有 REA 的直接 Node + public scripts/rea.mjs 注册")
    entry = Path(cli_arguments[0]).resolve(strict=True)
    package = entry.parent.parent
    package_version = json.loads((package / "package.json").read_text(encoding="utf-8"))["version"]
    if package_version != "6.4.0":
        parser.error("本地适配器仅验证 REA 6.4.0；新版本必须重新核对启动实现")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or project_root() / "work/runtime" / f"rea-seeded-{stamp}-{uuid.uuid4().hex[:8]}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    seeds = output / "seeds.tsv"
    range_file = output / "ranges.tsv"
    image_base = int(str(registry["binary"]["image_base"]), 0)
    seed_rows = []
    for key in selected:
        address = image_base + int(str(index[key]["rva"]), 0)
        name = "EU4_" + re.sub(r"[^A-Za-z0-9_]", "_", key)
        seed_rows.append(f"{address:#x}\tfunction\t{name}")
    seeds.write_text("\n".join(seed_rows) + "\n", encoding="utf-8")
    range_file.write_bytes("".join(f"{image_base + begin:#x}\t{image_base + end:#x}\n"
                                 for begin, end in ranges.values()).encode("utf-8"))
    loader = Path(__file__).with_name("rea_seeded_loader.mjs").resolve(strict=True)
    decode_script = Path(__file__).with_name("Eu4ReaDecodeFunctions.java").resolve(strict=True)
    environment = os.environ.copy()
    environment.update(config.get("env", {}))
    environment.update({"EU4_REA_PACKAGE_ROOT": str(package), "REA_GHIDRA_SEED_FILE": str(seeds),
                        "EU4_REA_DECODE_SCRIPT": str(decode_script), "EU4_REA_RANGES": str(range_file),
                        "REA_GHIDRA_STARTUP_TIMEOUT_MS": str(args.timeout * 1000),
                        "GHIDRA_HEADLESS_MAXMEM": "512M"})
    procedure = image_base + int(str(index[args.node]["rva"]), 0)
    command = [node_command, "--import", loader.as_uri(), *cli_arguments[:-1],
               "function", str(target), f"{procedure:#x}", "--provider", "ghidra", "--format", "json"]
    request = {"target_sha256": binary_check.binary_sha256, "node": args.node,
               "procedure_va": f"{procedure:#x}", "declared_nodes": selected,
               "preset": PRESET, "seed_file_sha256": _hash(seeds),
               "adapter_sha256": _hash(loader), "package_version": package_version,
               "decode_script_sha256": _hash(decode_script), "declared_ranges_sha256": _hash(range_file),
               "unwind_ranges_rva": {f"{begin:#x}": f"{end:#x}" for begin, end in ranges.values()},
               "java_heap": "512M", "process_memory_limit_bytes": MEMORY_LIMIT,
               "timeout_seconds": args.timeout, "global_reference_coverage": "incomplete"}
    (output / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    started = time.monotonic()
    observed = {}
    reason = "completed"
    with (output / "evidence.json").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
        process = psutil.Popen(command, env=environment, stdout=stdout, stderr=stderr)
        print(f"REA 按需分析：{args.node}，静态 VA={procedure:#x}；输出 {output}", flush=True)
        last_report = 0.0
        while process.poll() is None:
            for child in _owned_children(process, psutil):
                try:
                    if child.name().lower() not in {"java.exe", "javaw.exe"}:
                        continue
                    argument_text = " ".join(child.cmdline()).lower()
                    if "ghidra" not in argument_text or "analyzeheadless" not in argument_text or "rea" not in argument_text:
                        continue
                    memory = child.memory_info()
                    committed = getattr(memory, "private", memory.vms)
                    row = observed.setdefault(child.pid, {"pid": child.pid, "create_time": child.create_time(),
                        "owned_command_verified": True, "peak_committed_bytes": 0, "stopped_for_limit": False})
                    row["peak_committed_bytes"] = max(row["peak_committed_bytes"], committed)
                    _capture_logs(child, output)
                    if committed > MEMORY_LIMIT or time.monotonic() - started > args.timeout + 20:
                        reason = "memory_limit" if committed > MEMORY_LIMIT else "supervisor_deadline"
                        row["stopped_for_limit"] = committed > MEMORY_LIMIT
                        _stop_process(child, psutil)
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    continue
            elapsed = time.monotonic() - started
            if elapsed - last_report >= 20:
                peak = max((row["peak_committed_bytes"] for row in observed.values()), default=0)
                print(f"等待 {elapsed:.0f}s；Java 进程峰值 {peak / 1024**2:.1f} MiB", flush=True)
                last_report = elapsed
            if elapsed > args.timeout + 35:
                reason = "supervisor_deadline"
                for child in reversed(_owned_children(process, psutil)):
                    _stop_process(child, psutil)
                _stop_process(process, psutil)
            time.sleep(1)
        exit_code = process.wait(timeout=15)
    evidence = None
    path = output / "evidence.json"
    if path.stat().st_size <= 10 * 1024**2 and path.stat().st_size:
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            pass
    if exit_code == 0:
        profile = evidence.get("analysis_profile", {}).get("parameters", {}) if isinstance(evidence, dict) else {}
        if profile.get("analyzer_preset") != PRESET or profile.get("local_adapter_sha256") != request["adapter_sha256"] or profile.get("local_decode_script_sha256") != request["decode_script_sha256"] or profile.get("declared_ranges_sha256") != request["declared_ranges_sha256"]:
            exit_code, reason = 1, "profile_readback_failed"
        elif evidence.get("subject", {}).get("digest", {}).get("sha256") != request["target_sha256"]:
            exit_code, reason = 1, "target_identity_readback_failed"
        else:
            result = evidence.get("raw_result", {}).get("value", {})
            begin, end = ranges[procedure - image_base]
            expected_ranges = [{"start": f"{image_base + begin:#x}", "end": f"{image_base + end - 1:#x}"}]
            if result.get("procedure", {}).get("body", {}).get("ranges") != expected_ranges or not result.get("assembly") or not result.get("pseudocode"):
                exit_code, reason = 1, "bounded_function_readback_failed"
    for row in observed.values():
        try:
            remaining = psutil.Process(row["pid"])
            row["still_running_same_process"] = remaining.create_time() == row["create_time"]
            if row["still_running_same_process"]:
                arguments = " ".join(remaining.cmdline()).lower()
                if "ghidra" in arguments and "analyzeheadless" in arguments and "rea" in arguments:
                    _stop_process(remaining, psutil)
                    row["forced_cleanup"] = True
                    row["still_running_same_process"] = False
        except psutil.NoSuchProcess:
            row["still_running_same_process"] = False
    if any(row["still_running_same_process"] for row in observed.values()):
        exit_code, reason = 1, "analysis_process_cleanup_incomplete"
    elif exit_code and reason == "completed":
        reason = "provider_failed"
    summary = {**request, "exit_code": exit_code, "reason": reason,
               "elapsed_seconds": round(time.monotonic() - started, 2), "processes": list(observed.values()),
               "evidence_id": evidence.get("evidence_id") if isinstance(evidence, dict) else None,
               "analysis_profile_digest": evidence.get("analysis_profile", {}).get("digest") if isinstance(evidence, dict) and evidence.get("analysis_profile") else None}
    (output / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["exit_code", "reason", "elapsed_seconds", "evidence_id"]}, ensure_ascii=False), flush=True)
    if exit_code:
        print(f"诊断见 {output / 'stderr.log'} 与 {path}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
