"""Build the bounded R54 evidence index and checkpoint plan.

This is an indexing/plan step only.  It never invokes the archive helper,
copies runtime artifacts, starts a game, or performs reverse engineering.
Evidence files are hashed with 64 KiB reads while files larger than 8 MiB are
recorded as references without opening them.  The resulting progress JSON
contains the evidence-index link that the existing archive helper can consume
through ``--runtime-json`` later.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
RUNTIME = WORK / "runtime"

PREVIOUS_MANIFEST = (
    RUNTIME
    / "r53-peace-annul-treaties-checkpoint-20261018-001"
    / "archive-manifest.json"
)
CHECKPOINT = "r54-peace-special-terms-checkpoint-20261018-001"
EVIDENCE_INDEX = RUNTIME / "r54-evidence-index-20261018-001.json"
PLAN = RUNTIME / "r54-checkpoint-plan-20261018-001.json"
PROGRESS = RUNTIME / "r54-progress.json"

HASH_CHUNK_BYTES = 64 * 1024
MAX_EVIDENCE_HASH_BYTES = 8 * 1024 * 1024

EXCLUDED_DIR_NAMES = frozenset({"save-backup", "preserved-inputs"})
EXCLUDED_SUFFIXES = frozenset(
    {
        ".dll",
        ".exe",
        ".pdb",
        ".pyc",
        ".eu4",
        ".sav",
        ".save",
        ".sqlite",
        ".sqlite3",
        ".db",
        ".dmp",
    }
)
CONTROL_PROBE_LOG_SUFFIXES = frozenset(
    {".log", ".jsonl", ".json", ".txt", ".csv"}
)
SQLITE_LOG_SUFFIXES = frozenset(
    {".log", ".jsonl", ".json", ".txt", ".csv"}
)


class PlanError(RuntimeError):
    """A bounded plan/index input or output error."""


def workspace_relative(path: Path) -> str:
    """Return a stable workspace-relative POSIX path."""

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as error:
        raise PlanError(f"PATH_OUTSIDE_WORKSPACE:{path}") from error


def resolve_workspace_file(value: str | Path, *, label: str) -> Path:
    raw = Path(value).expanduser()
    path = (raw if raw.is_absolute() else ROOT / raw).resolve()
    if not path.is_file():
        raise PlanError(f"{label}_NOT_FILE:{value}")
    return path


def read_json(path: Path, *, label: str, maximum: int = MAX_EVIDENCE_HASH_BYTES) -> Any:
    """Read a small JSON metadata file after a size guard."""

    path = resolve_workspace_file(path, label=label)
    size = path.stat().st_size
    if size > maximum:
        raise PlanError(f"{label}_TOO_LARGE:{workspace_relative(path)}:{size}")
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            return json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlanError(f"{label}_INVALID:{workspace_relative(path)}:{type(error).__name__}") from error


def stream_sha256(path: Path) -> tuple[int, str]:
    """Hash a file with the required 64 KiB chunk size."""

    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_EVIDENCE_HASH_BYTES:
                    raise PlanError(
                        f"EVIDENCE_RACE_GREW_OVER_LIMIT:{workspace_relative(path)}:{total}"
                    )
                digest.update(chunk)
    except PlanError:
        raise
    except OSError as error:
        raise PlanError(
            f"EVIDENCE_HASH_FAILED:{workspace_relative(path)}:{type(error).__name__}"
        ) from error
    return total, digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    """Atomically write a UTF-8 JSON artifact in the workspace."""

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def previous_allowlist(path: Path) -> list[str]:
    payload = read_json(path, label="PREVIOUS_MANIFEST")
    if not isinstance(payload, dict):
        raise PlanError("PREVIOUS_MANIFEST_NOT_OBJECT")
    values = payload.get("files_excluding_manifest")
    if not isinstance(values, list):
        raise PlanError("PREVIOUS_FILE_ALLOWLIST_MISSING")
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = item.get("path") if isinstance(item, dict) else item
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise PlanError(f"PREVIOUS_FILE_PATH_INVALID:{value}")
        normalized = Path(value).as_posix()
        source = (ROOT / normalized).resolve()
        if workspace_relative(source) != normalized:
            raise PlanError(f"PREVIOUS_FILE_PATH_NOT_NORMALIZED:{value}")
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _is_excluded_component(component: str) -> bool:
    lowered = component.casefold()
    return lowered in EXCLUDED_DIR_NAMES or lowered.startswith("ready-attempt")


def _is_excluded_evidence_path(path: Path) -> tuple[bool, str | None]:
    parts = tuple(part.casefold() for part in path.parts)
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    for component in parts:
        if _is_excluded_component(component):
            return True, "excluded_directory"
    if suffix in EXCLUDED_SUFFIXES:
        return True, "excluded_artifact_suffix"
    if "control-probe" in name and suffix in CONTROL_PROBE_LOG_SUFFIXES:
        return True, "excluded_control_probe_log"
    if "sqlite" in name:
        if suffix in SQLITE_LOG_SUFFIXES or suffix in EXCLUDED_SUFFIXES:
            return True, "excluded_sqlite_artifact"
    return False, None


def _prune_dirs(dirnames: list[str]) -> None:
    dirnames[:] = [name for name in dirnames if not _is_excluded_component(name)]


def discover_install_roots() -> list[Path]:
    return sorted(
        (
            path
            for path in RUNTIME.glob("diplomacy-query-20261018-r54-special-*")
            if path.is_dir()
        ),
        key=lambda path: path.as_posix().casefold(),
    )


def discover_task_roots() -> list[Path]:
    return sorted(
        (path for path in RUNTIME.glob("r54-*") if path.is_dir()),
        key=lambda path: path.as_posix().casefold(),
    )


def discover_native_manifests(roots: Iterable[Path]) -> list[dict[str, Any]]:
    """Collect build manifests without opening any binary or runtime DLL."""

    paths: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for current, dirnames, filenames in os.walk(root, topdown=True):
            _prune_dirs(dirnames)
            if "build-manifest.json" in filenames:
                paths.add(Path(current) / "build-manifest.json")

    result: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: workspace_relative(item).casefold()):
        size = path.stat().st_size
        if size > MAX_EVIDENCE_HASH_BYTES:
            raise PlanError(f"NATIVE_MANIFEST_TOO_LARGE:{workspace_relative(path)}:{size}")
        bytes_read, digest = stream_sha256(path)
        payload = read_json(path, label="NATIVE_MANIFEST")
        if not isinstance(payload, dict):
            raise PlanError(f"NATIVE_MANIFEST_NOT_OBJECT:{workspace_relative(path)}")
        # Keep the complete manifest payload, especially each raw source hash.
        entry: dict[str, Any] = {
            "path": workspace_relative(path),
            "bytes": bytes_read,
            "sha256": digest,
            "manifest": payload,
        }
        result.append(entry)
    return result


def source_hash_map(entry: dict[str, Any]) -> dict[str, str | None]:
    payload = entry.get("manifest")
    sources = payload.get("sources") if isinstance(payload, dict) else None
    result: dict[str, str | None] = {}
    if not isinstance(sources, list):
        return result
    for source in sources:
        if isinstance(source, dict) and isinstance(source.get("name"), str):
            result[source["name"]] = source.get("sha256")
    return result


def source_hash_observations(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report A1/A2 differences while retaining each raw manifest above."""

    by_path = {entry["path"]: entry for entry in manifests}
    observations: list[dict[str, Any]] = []
    for path in sorted(by_path):
        if "-a2" not in path:
            continue
        counterpart = path.replace("-a2", "-a", 1)
        if counterpart not in by_path:
            continue
        left = by_path[counterpart]
        right = by_path[path]
        left_hashes = source_hash_map(left)
        right_hashes = source_hash_map(right)
        names = sorted(set(left_hashes) | set(right_hashes))
        differences = [
            {
                "name": name,
                "a_sha256": left_hashes.get(name),
                "a2_sha256": right_hashes.get(name),
            }
            for name in names
            if left_hashes.get(name) != right_hashes.get(name)
        ]
        observations.append(
            {
                "a_manifest": counterpart,
                "a2_manifest": path,
                "source_hashes_equal": not differences,
                "different_source_count": len(differences),
                "differences": differences,
            }
        )
    return observations


def scan_evidence(roots: Iterable[Path]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    large_references: list[dict[str, Any]] = []
    excluded_count = 0
    excluded_sample: list[dict[str, str]] = []
    scan_roots: list[str] = []
    total_hashed_bytes = 0

    for root in roots:
        if not root.is_dir():
            continue
        scan_roots.append(workspace_relative(root))
        for current, dirnames, filenames in os.walk(root, topdown=True):
            _prune_dirs(dirnames)
            for filename in sorted(filenames, key=str.casefold):
                path = Path(current) / filename
                relative = workspace_relative(path)
                excluded, reason = _is_excluded_evidence_path(path)
                if excluded:
                    excluded_count += 1
                    if len(excluded_sample) < 100:
                        excluded_sample.append({"path": relative, "reason": reason or "excluded"})
                    continue
                try:
                    size = path.stat().st_size
                except OSError as error:
                    raise PlanError(f"EVIDENCE_STAT_FAILED:{relative}:{type(error).__name__}") from error
                if size > MAX_EVIDENCE_HASH_BYTES:
                    large_references.append(
                        {
                            "path": relative,
                            "bytes": size,
                            "indexed": "reference_only",
                            "sha256": None,
                            "reason": "over_8MiB_not_read",
                        }
                    )
                    continue
                bytes_read, digest = stream_sha256(path)
                files.append(
                    {
                        "path": relative,
                        "bytes": bytes_read,
                        "sha256": digest,
                        "indexed": "hashed",
                    }
                )
                total_hashed_bytes += bytes_read

    files.sort(key=lambda item: str(item["path"]).casefold())
    large_references.sort(key=lambda item: str(item["path"]).casefold())
    scan_roots.sort(key=str.casefold)
    return {
        "schema": "r54_evidence_index_v1",
        "status": "passed",
        "scope": "R54 special-term installation directories and top-level R54 task directories",
        "hash_chunk_bytes": HASH_CHUNK_BYTES,
        "max_hashed_bytes": MAX_EVIDENCE_HASH_BYTES,
        "scan_roots": scan_roots,
        "exclusion_rules": {
            "directory_components": ["ready-attempt*", "save-backup", "preserved-inputs"],
            "suffixes": sorted(EXCLUDED_SUFFIXES),
            "control_probe_log": "name contains control-probe and log-like suffix",
            "sqlite_log": "name contains sqlite and log-like suffix",
        },
        "files": files,
        "large_references": large_references,
        "excluded": {"count": excluded_count, "sample": excluded_sample},
        "file_count": len(files),
        "large_reference_count": len(large_references),
        "total_hashed_bytes": total_hashed_bytes,
    }


def _append_candidate(
    candidates: list[str], seen: set[str], previous: set[str], path: Path
) -> None:
    if not path.is_file():
        return
    relative = workspace_relative(path)
    if relative in previous or relative in seen:
        return
    seen.add(relative)
    candidates.append(relative)


def _append_planned_output(
    candidates: list[str], seen: set[str], previous: set[str], path: Path
) -> None:
    """Reserve an output path that this run writes immediately afterward."""

    relative = workspace_relative(path)
    if relative in previous or relative in seen:
        return
    seen.add(relative)
    candidates.append(relative)


def discover_add_files(previous: list[str]) -> tuple[list[str], list[str]]:
    """Select only new R54 code, tests/fixtures, human docs and outputs."""

    previous_set = set(previous)
    candidates: list[str] = []
    seen: set[str] = set()
    missing_required: list[str] = []

    required_paths = [
        WORK / "native" / "peace-special-selection.inc",
        WORK / "native" / "peace-special-state.inc",
        WORK / "run_peace_special_queries.py",
        WORK / "reconcile_peace_execution_result.py",
        RUNTIME / "r54-corrected-reloads-and-sf-queries-20261018-001" / "run.py",
        RUNTIME / "r54-special-fixture-design-20261018-001" / "build_query_fixtures.py",
        RUNTIME / "r54-final-native-source-consistency-20261018-001.json",
        Path(__file__).resolve(),
    ]
    for path in required_paths:
        if not path.is_file():
            missing_required.append(workspace_relative(path))
        else:
            _append_candidate(candidates, seen, previous_set, path)

    optional_root_scripts = (
        "run_native_special_query_probe.py",
        "reproject_peace_special_queries.py",
        "reconcile_peace_special_queries.py",
    )
    for name in optional_root_scripts:
        _append_candidate(candidates, seen, previous_set, WORK / name)

    special_tests = sorted(
        (path for path in (ROOT / "bridge" / "tests").glob("test_peace_special*.py") if path.is_file()),
        key=lambda path: workspace_relative(path).casefold(),
    )
    special_fixtures = sorted(
        (
            path
            for path in (ROOT / "bridge" / "tests" / "fixtures").glob("peace_special*.json")
            if path.is_file()
        ),
        key=lambda path: workspace_relative(path).casefold(),
    )
    if not special_tests:
        missing_required.append("bridge/tests/test_peace_special*.py")
    if not special_fixtures:
        missing_required.append("bridge/tests/fixtures/peace_special*.json")
    for path in special_tests + special_fixtures:
        _append_candidate(candidates, seen, previous_set, path)

    history_docs = sorted(
        (path for path in (ROOT / "docs" / "history").glob("R54*.md") if path.is_file()),
        key=lambda path: workspace_relative(path).casefold(),
    )
    if not history_docs:
        missing_required.append("docs/history/R54*.md")
    for path in history_docs:
        _append_candidate(candidates, seen, previous_set, path)

    runtime_doc_count = 0
    for root in discover_task_roots():
        for current, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [name for name in dirnames if not name.casefold().startswith("rea-")]
            _prune_dirs(dirnames)
            for filename in sorted(filenames, key=str.casefold):
                if not filename.casefold().endswith(".md"):
                    continue
                path = Path(current) / filename
                if path.is_file():
                    runtime_doc_count += 1
                    _append_candidate(candidates, seen, previous_set, path)
    if runtime_doc_count == 0:
        missing_required.append("work/runtime/r54-*/*.md")

    # These generated artifacts are part of the R54 plan itself.  They are
    # reserved before their writers run, and are intentionally not inherited.
    for path in (EVIDENCE_INDEX, PLAN, PROGRESS):
        _append_planned_output(candidates, seen, previous_set, path)

    return candidates, missing_required


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def archive_command(
    previous_manifest: str,
    checkpoint: str,
    add_files: list[str],
    native_manifests: list[dict[str, Any]],
) -> tuple[list[str], str]:
    args = [
        "python",
        "work/archive_diplomacy_checkpoint.py",
        "--previous-manifest",
        previous_manifest,
        "--checkpoint",
        checkpoint,
        "--runtime-json",
        "work/runtime/r54-progress.json",
    ]
    for path in add_files:
        args.extend(("--add-file", path))
    for entry in native_manifests:
        args.extend(("--native-manifest", str(entry["path"])))
    return args, " ".join(ps_quote(value) for value in args)


def build(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-manifest", type=Path, default=PREVIOUS_MANIFEST)
    parser.add_argument("--checkpoint", default=CHECKPOINT)
    args = parser.parse_args(argv)

    previous_path = resolve_workspace_file(args.previous_manifest, label="PREVIOUS_MANIFEST")
    previous = previous_allowlist(previous_path)
    install_roots = discover_install_roots()
    task_roots = discover_task_roots()
    if not install_roots:
        raise PlanError("R54_INSTALL_ROOTS_MISSING")
    if not task_roots:
        raise PlanError("R54_TASK_ROOTS_MISSING")

    native_manifests = discover_native_manifests(install_roots)
    if not native_manifests:
        raise PlanError("R54_NATIVE_MANIFESTS_MISSING")
    evidence = scan_evidence([*install_roots, *task_roots])
    evidence["native_manifests"] = native_manifests
    evidence["source_hash_observations"] = source_hash_observations(native_manifests)
    evidence["generated_at_utc"] = utc_now()

    add_files, missing_required = discover_add_files(previous)
    if missing_required:
        raise PlanError("R54_REQUIRED_INPUTS_MISSING:" + ",".join(missing_required))

    write_json(EVIDENCE_INDEX, evidence)

    native_paths = [str(entry["path"]) for entry in native_manifests]
    evidence_link = workspace_relative(EVIDENCE_INDEX)
    previous_relative = workspace_relative(previous_path)
    command_args, command_ps = archive_command(
        previous_relative, args.checkpoint, add_files, native_manifests
    )
    generated_at = utc_now()
    progress = read_json(PROGRESS, label="EXISTING_PROGRESS") if PROGRESS.exists() else {}
    if not isinstance(progress, dict):
        raise PlanError("EXISTING_PROGRESS_NOT_OBJECT")
    progress.update({
        "checkpoint": args.checkpoint,
        "native_manifests": native_paths,
        "native_manifest_count": len(native_paths),
        "evidence_index": evidence_link,
        "evidence_links": [evidence_link],
        "archive_pending": True,
        "archive_command": command_args,
        "archive_command_powershell": command_ps,
    })
    progress["index_generation"] = {
        "generated_at_utc": generated_at,
        "previous_allowlist_count": len(previous),
        "add_file_count": len(add_files),
        "evidence_index_status": evidence["status"],
        "hash_chunk_bytes": HASH_CHUNK_BYTES,
        "max_hashed_bytes": MAX_EVIDENCE_HASH_BYTES,
        "a1_a2_source_hashes_preserved_raw": True,
        "scope": "metadata generation only; existing runtime facts and goal classification preserved",
    }

    plan: dict[str, Any] = {
        "schema": "r54_checkpoint_plan_v1",
        "generated_at_utc": generated_at,
        "previous_manifest": previous_relative,
        "checkpoint": args.checkpoint,
        "add_files": add_files,
        "native_manifests": native_paths,
        "evidence": [evidence_link],
        "evidence_index": evidence_link,
        "previous_allowlist_count": len(previous),
        "native_manifest_count": len(native_paths),
        "archive_pending": True,
        "archive_command": command_args,
        "archive_command_powershell": command_ps,
    }
    # Progress is an archive runtime JSON.  It deliberately links the compact
    # evidence index rather than expanding every evidence path into argv.
    write_json(PROGRESS, progress)
    write_json(PLAN, plan)

    print(
        json.dumps(
            {
                "status": "passed",
                "archive_not_run": True,
                "previous_manifest": previous_relative,
                "checkpoint": args.checkpoint,
                "evidence_index": evidence_link,
                "plan": workspace_relative(PLAN),
                "progress": workspace_relative(PROGRESS),
                "previous_allowlist_count": len(previous),
                "add_file_count": len(add_files),
                "native_manifest_count": len(native_paths),
                "archive_command": command_ps,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return build(argv)
    except (PlanError, OSError, ValueError, TypeError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "archive_not_run": True,
                    "error": {"type": type(error).__name__, "message": str(error)},
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
