"""Create a bounded, non-destructive diplomacy implementation checkpoint.

The previous manifest supplies the source-file allowlist.  Explicit
additional files may be supplied with --add-file.  Native build manifests are
recorded as external immutable references with streamed hashes; native DLLs
and runtime logs/saves are never copied.  The destination checkpoint must be
new and is installed atomically after all files have been copied and checked.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import shutil
import sys
import uuid
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "work" / "runtime"
MAX_SINGLE_FILE_BYTES = 10 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
HASH_CHUNK_BYTES = 64 * 1024
RUNTIME_EXCLUDED_SUFFIXES = frozenset(
    (".dll", ".eu4", ".sav", ".save", ".log", ".jsonl")
)
RUNTIME_EXCLUDED_NAME_PARTS = frozenset(
    ("save games", "savegame", "autosave", "logs", "log")
)


class ArchiveError(RuntimeError):
    """A bounded archive validation or copy failure."""


def _workspace_relative(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError as error:
        raise ArchiveError(f"PATH_OUTSIDE_WORKSPACE:{path}") from error
    return relative.as_posix()


def _resolve_workspace_file(value: str, *, label: str) -> tuple[Path, str]:
    raw = Path(value).expanduser()
    path = (raw if raw.is_absolute() else ROOT / raw).resolve(strict=True)
    if not path.is_file():
        raise ArchiveError(f"{label}_NOT_FILE:{value}")
    return path, _workspace_relative(path)


def _read_json(path: Path, *, label: str, maximum: int = MAX_METADATA_BYTES) -> Any:
    if not path.is_file():
        raise ArchiveError(f"{label}_MISSING:{path}")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ArchiveError(f"{label}_STAT_FAILED:{path}") from error
    if size > maximum:
        raise ArchiveError(f"{label}_TOO_LARGE:{path}:{size}")
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            return json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArchiveError(f"{label}_JSON_INVALID:{path}:{type(error).__name__}") from error


def _stream_hash(path: Path, *, maximum: int = MAX_SINGLE_FILE_BYTES) -> dict[str, object]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise ArchiveError(f"FILE_TOO_LARGE:{path}:{total}")
                digest.update(chunk)
    except ArchiveError:
        raise
    except OSError as error:
        raise ArchiveError(f"FILE_HASH_FAILED:{path}:{type(error).__name__}") from error
    return {"bytes": total, "sha256": digest.hexdigest()}


def _copy_and_hash(source: Path, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_digest = hashlib.sha256()
    total = 0
    try:
        with source.open("rb") as input_stream, destination.open("xb") as output_stream:
            while True:
                chunk = input_stream.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SINGLE_FILE_BYTES:
                    raise ArchiveError(f"FILE_TOO_LARGE:{source}:{total}")
                source_digest.update(chunk)
                output_stream.write(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    except ArchiveError:
        raise
    except OSError as error:
        raise ArchiveError(
            f"FILE_COPY_FAILED:{source}:{destination}:{type(error).__name__}"
        ) from error
    source_sha256 = source_digest.hexdigest()
    copied = _stream_hash(destination)
    if copied["bytes"] != total or copied["sha256"] != source_sha256:
        raise ArchiveError(f"COPY_HASH_MISMATCH:{source}:{destination}")
    return {
        "bytes": total,
        "source_sha256": source_sha256,
        "copy_sha256": copied["sha256"],
    }


def _is_runtime_excluded(relative: str) -> bool:
    parts = tuple(part.lower() for part in Path(relative).parts)
    name = parts[-1]
    if Path(name).suffix == ".dll":
        return True
    if "runtime" not in parts:
        return False
    if Path(name).suffix in RUNTIME_EXCLUDED_SUFFIXES:
        return True
    return any(part in RUNTIME_EXCLUDED_NAME_PARTS for part in parts)


def _validate_copy_candidate(path: Path, relative: str, *, label: str) -> None:
    if _is_runtime_excluded(relative):
        raise ArchiveError(f"RUNTIME_ARTIFACT_EXCLUDED:{label}:{relative}")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ArchiveError(f"FILE_STAT_FAILED:{path}") from error
    if size > MAX_SINGLE_FILE_BYTES:
        raise ArchiveError(f"FILE_TOO_LARGE:{path}:{size}")


def _manifest_files(previous: object) -> list[str]:
    if not isinstance(previous, dict):
        raise ArchiveError("PREVIOUS_MANIFEST_NOT_OBJECT")
    values = previous.get("files_excluding_manifest")
    if not isinstance(values, list):
        raise ArchiveError("PREVIOUS_FILE_ALLOWLIST_MISSING")
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = item.get("path") if isinstance(item, dict) else item
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ArchiveError(f"PREVIOUS_FILE_PATH_INVALID:{value}")
        path = (ROOT / value).resolve()
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError as error:
            raise ArchiveError(f"PREVIOUS_FILE_OUTSIDE_WORKSPACE:{value}") from error
        if relative != Path(value).as_posix():
            raise ArchiveError(f"PREVIOUS_FILE_PATH_NOT_NORMALIZED:{value}")
        if relative not in seen:
            seen.add(relative)
            result.append(relative)
    return result


def _native_reference(value: str) -> dict[str, object]:
    manifest, manifest_relative = _resolve_workspace_file(
        value, label="NATIVE_MANIFEST"
    )
    manifest_hash = _stream_hash(manifest, maximum=MAX_METADATA_BYTES)
    payload = _read_json(manifest, label="NATIVE_MANIFEST")
    if not isinstance(payload, dict):
        raise ArchiveError(f"NATIVE_MANIFEST_NOT_OBJECT:{manifest}")
    dll_value = payload.get("dll")
    dll_path: Path | None = None
    dll_relative: str | None = None
    actual_dll_hash: dict[str, object] | None = None
    if isinstance(dll_value, str) and dll_value:
        raw_dll = Path(dll_value).expanduser()
        dll_path = (
            raw_dll if raw_dll.is_absolute() else manifest.parent / raw_dll
        ).resolve()
        if dll_path.is_file():
            try:
                dll_relative = _workspace_relative(dll_path)
            except ArchiveError:
                dll_relative = None
            actual_dll_hash = _stream_hash(dll_path)
    sources = payload.get("sources")
    source_hashes: list[object] = []
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict):
                source_hashes.append({
                    "name": source.get("name"),
                    "sha256": source.get("sha256"),
                })
            elif isinstance(source, str):
                source_hashes.append(source)
    return {
        "manifest_path": manifest_relative,
        "manifest_sha256": manifest_hash["sha256"],
        "manifest_bytes": manifest_hash["bytes"],
        "dll_path": dll_relative if dll_relative is not None else str(dll_path)
        if dll_path is not None else None,
        "dll_sha256": (
            actual_dll_hash.get("sha256")
            if isinstance(actual_dll_hash, dict) else payload.get("dll_sha256")
        ),
        "dll_bytes": (
            actual_dll_hash.get("bytes")
            if isinstance(actual_dll_hash, dict) else None
        ),
        "declared_dll_sha256": payload.get("dll_sha256"),
        "source_hashes": source_hashes,
        "copied_into_checkpoint": False,
    }


def _runtime_data(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    payload = _read_json(path, label="RUNTIME_JSON")
    if not isinstance(payload, dict):
        raise ArchiveError("RUNTIME_JSON_NOT_OBJECT")
    return payload


def _evidence_links(runtime: dict[str, object], explicit: list[str] | None) -> list[str]:
    result: list[str] = []
    values = runtime.get("evidence_links")
    if values is not None and not isinstance(values, list):
        raise ArchiveError("RUNTIME_EVIDENCE_LINKS_NOT_LIST")
    for value in (values or []) + (explicit or []):
        if not isinstance(value, str) or not value:
            raise ArchiveError(f"EVIDENCE_LINK_INVALID:{value}")
        if value not in result:
            result.append(value)
    return result


def _checkpoint_path(value: str) -> Path:
    raw = Path(value).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    if raw.parts[:2] == ("work", "runtime"):
        return (ROOT / raw).resolve()
    return (RUNTIME_ROOT / raw).resolve()


def _source_entry(relative: str, copied: dict[str, object]) -> dict[str, object]:
    return {
        "path": relative,
        "source": str(ROOT / Path(relative)),
        "bytes": copied["bytes"],
        "sha256": copied["copy_sha256"],
        "source_sha256": copied["source_sha256"],
        "copy_sha256": copied["copy_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-manifest", type=Path, required=True)
    parser.add_argument(
        "--checkpoint", required=True,
        help="New directory name under work/runtime, or an absolute destination path",
    )
    parser.add_argument("--add-file", action="append", default=[], metavar="PATH")
    parser.add_argument("--native-manifest", action="append", default=[], metavar="PATH")
    parser.add_argument("--evidence", action="append", default=[], metavar="PATH")
    parser.add_argument("--runtime-json", type=Path)
    args = parser.parse_args(argv)

    stage: Path | None = None
    try:
        previous_path = args.previous_manifest.expanduser().resolve(strict=True)
        previous = _read_json(previous_path, label="PREVIOUS_MANIFEST")
        allowlist = _manifest_files(previous)
        candidates: list[tuple[Path, str, str]] = []
        seen: set[str] = set()
        for relative in allowlist:
            source = (ROOT / relative).resolve(strict=True)
            if not source.is_file():
                raise ArchiveError(f"ALLOWLIST_NOT_FILE:{relative}")
            _validate_copy_candidate(source, relative, label="allowlist")
            candidates.append((source, relative, "previous_manifest"))
            seen.add(relative)
        for value in args.add_file:
            source, relative = _resolve_workspace_file(value, label="ADD_FILE")
            _validate_copy_candidate(source, relative, label="add_file")
            if relative not in seen:
                candidates.append((source, relative, "explicit_add_file"))
                seen.add(relative)

        native_refs = [_native_reference(value) for value in args.native_manifest]
        native_manifest_paths = {
            item["manifest_path"] for item in native_refs
            if isinstance(item.get("manifest_path"), str)
        }
        if native_manifest_paths.intersection(seen):
            duplicate = sorted(native_manifest_paths.intersection(seen))[0]
            raise ArchiveError(f"NATIVE_REFERENCE_MUST_NOT_BE_COPIED:{duplicate}")

        runtime_path = (
            args.runtime_json.expanduser().resolve(strict=True)
            if args.runtime_json is not None else None
        )
        runtime = _runtime_data(runtime_path)
        evidence_links = _evidence_links(runtime, args.evidence)
        destination = _checkpoint_path(args.checkpoint)
        if destination.exists():
            raise ArchiveError(f"CHECKPOINT_ALREADY_EXISTS:{destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = destination.parent / f".{destination.name}.partial-{uuid.uuid4().hex}"
        stage.mkdir()

        entries: list[dict[str, object]] = []
        total_bytes = 0
        for source, relative, origin in candidates:
            copied = _copy_and_hash(source, stage / Path(relative))
            entry = _source_entry(relative, copied)
            entry["origin"] = origin
            entries.append(entry)
            total_bytes += int(copied["bytes"])

        manifest = {
            "format": 2,
            "checkpoint": destination.name,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "stage_complete_goal_active",
            "file_count": len(entries),
            "total_bytes": total_bytes,
            "files_excluding_manifest": entries,
            "native_build_references": native_refs,
            "source": {
                "workspace_root": str(ROOT),
                "previous_manifest": _workspace_relative(previous_path)
                if previous_path.is_relative_to(ROOT) else str(previous_path),
                "explicit_add_files": [item[1] for item in candidates if item[2] == "explicit_add_file"],
                "native_manifest_count": len(native_refs),
                "native_copied": False,
                "runtime_artifacts_copied": False,
            },
            "validation": runtime.get("validation", {}),
            "evidence_links": evidence_links,
            "next_evidence": runtime.get("next_evidence"),
            "runtime_snapshot": runtime.get("runtime_snapshot"),
            "large_evidence_copied": False,
        }
        manifest_path = stage / "archive-manifest.json"
        with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            raise ArchiveError(f"CHECKPOINT_CREATED_DURING_RUN:{destination}")
        os.replace(stage, destination)
        stage = None
        print(json.dumps({
            "status": "passed",
            "checkpoint": str(destination),
            "manifest": str(destination / "archive-manifest.json"),
            "file_count": len(entries),
            "total_bytes": total_bytes,
        }, ensure_ascii=False), flush=True)
        return 0
    except (ArchiveError, OSError, ValueError, TypeError) as error:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        print(json.dumps({
            "status": "failed",
            "error": {"type": type(error).__name__, "message": str(error)},
        }, ensure_ascii=False), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
