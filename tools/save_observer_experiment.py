"""Operator-only paused-scene autosave archivist for an observer session.

The only native request emitted by this script is the fixed TEST_ONLY autosave
token.  A successful console result is only a transport signal; the real save
file, its POR metadata, size, stability, and before/after paused state must
also verify before the archive is reported successful.  Save recovery backs up
and restores only the three native rotating autosaves; other save files remain
in the report as size/mtime metadata and are never copied or overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "work"))

from bridge.diplomacy import ObserverSession
from bridge.diplomacy_session import probe_identity
from local_config import game_exe, get_value, user_data


AUTOSAVE_TOKEN = b"TEST_ONLY autosave\n"
MAX_TIMEOUT = 300
POLL_SECONDS = 0.25
STABLE_SECONDS = 2.0
MIN_SAVE_BYTES = 100_000
SAVE_NAME = re.compile(r"^llm_diplomacy_[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.eu4$", re.IGNORECASE)
ROTATING_AUTOSAVE_NAMES = ("autosave.eu4", "old_autosave.eu4", "older_autosave.eu4")
ROTATING_AUTOSAVE_KEYS = frozenset(name.casefold() for name in ROTATING_AUTOSAVE_NAMES)


class ExperimentError(RuntimeError):
    """A failed experiment that left its backup and independent report."""


def _emit(state: str, **details: object) -> None:
    message = {"state": state, **details}
    print(json.dumps(message, ensure_ascii=False, sort_keys=True), flush=True)


def _sha256_stream(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_new_file(source: Path, destination: Path) -> None:
    """Copy an archive without allowing a preexisting destination to be replaced."""

    with source.open("rb") as source_stream, destination.open("xb") as destination_stream:
        shutil.copyfileobj(source_stream, destination_stream, length=1024 * 1024)
    try:
        shutil.copystat(source, destination)
    except OSError:
        # Save contents and the exclusive destination are the safety boundary;
        # metadata preservation is useful but not required for the archive.
        pass


def _save_paths(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ExperimentError(f"SAVE_DIRECTORY_MISSING:{directory}")
    return sorted(
        (path for path in directory.iterdir()
         if path.is_file() and path.suffix.lower() == ".eu4"),
        key=lambda path: path.name.casefold(),
    )


def _find_casefold(directory: Path, name: str) -> Path | None:
    matches = [path for path in _save_paths(directory) if path.name.casefold() == name.casefold()]
    if len(matches) > 1:
        raise ExperimentError(f"DUPLICATE_CASE_INSENSITIVE_SAVE:{name}")
    return matches[0] if matches else None


def _stat_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _snapshot_metadata(directory: Path) -> dict[str, dict[str, object]]:
    """Capture bounded filesystem metadata without opening save contents."""

    snapshot: dict[str, dict[str, object]] = {}
    for path in _save_paths(directory):
        # The game can rotate an autosave between directory enumeration and
        # stat().  That one file is absent from this snapshot; other I/O
        # failures must remain visible to the caller.
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        snapshot[path.name.casefold()] = {
            "name": path.name,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "signature": [stat.st_size, stat.st_mtime_ns],
        }
    return snapshot


def _snapshot_saves(directory: Path) -> dict[str, dict[str, object]]:
    """Record every save's metadata and hash only the rotating autosaves."""

    snapshot = _snapshot_metadata(directory)
    for key, record in snapshot.items():
        if key in ROTATING_AUTOSAVE_KEYS:
            record["sha256"] = _sha256_stream(directory / str(record["name"]))
    return snapshot


def _rotating_baseline(baseline: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Return only baseline records that have an on-disk recovery copy."""

    return {
        key: record for key, record in baseline.items()
        if key in ROTATING_AUTOSAVE_KEYS and isinstance(record.get("sha256"), str)
    }


def _metadata_record(record: dict[str, object] | None) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "name": record.get("name"),
        "size": record.get("size"),
        "mtime_ns": record.get("mtime_ns"),
        "signature": record.get("signature"),
    }


def _metadata_changes(baseline: dict[str, dict[str, object]],
                      current: dict[str, dict[str, object]],
                      target_name: str) -> list[dict[str, object]]:
    """Report known-save metadata changes without reading save contents."""

    target_key = target_name.casefold()
    changes: list[dict[str, object]] = []
    for key in sorted(set(baseline) | set(current)):
        if key == target_key or key not in baseline:
            continue
        if key not in current:
            changes.append({
                "name": str(baseline[key].get("name", key)),
                "before": _metadata_record(baseline[key]),
                "after": None,
            })
            continue
        before_signature = tuple(baseline[key].get("signature", ()))
        after_signature = tuple(current[key].get("signature", ()))
        if before_signature != after_signature:
            changes.append({
                "name": str(current[key].get("name", baseline[key].get("name", key))),
                "before": _metadata_record(baseline[key]),
                "after": _metadata_record(current[key]),
            })
    return changes


def _write_json_exclusive(path: Path, payload: dict) -> Path:
    """Write a new JSON artifact without ever replacing an existing artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    suffix = path.suffix
    for index in range(1000):
        candidate = path if index == 0 else path.with_name(f"{stem}-{index}{suffix}")
        try:
            with candidate.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            return candidate
        except FileExistsError:
            continue
    raise ExperimentError(f"REPORT_PATH_ALLOCATION_FAILED:{path}")


def _read_log_events(path: Path, offset: int):
    if not path.exists():
        return
    with path.open("rb") as stream:
        stream.seek(offset)
        while True:
            line_offset = stream.tell()
            raw = stream.readline()
            if not raw:
                return
            end_offset = stream.tell()
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(event, dict):
                yield line_offset, end_offset, event


def _state_signature(state: dict) -> dict[str, object]:
    required = ("date_raw", "player_slot", "paused_flag")
    if any(key not in state for key in required):
        raise ExperimentError("CONTROL_STATE_FIELDS_MISSING")
    result = {key: state[key] for key in required}
    if result["player_slot"] != 189 or result["paused_flag"] != 1:
        raise ExperimentError("CONTROL_STATE_NOT_PAUSED_POR")
    return result


def _probe_control_state(pid: int, output: Path, deadline: float) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ExperimentError("EXPERIMENT_TIMEOUT_BEFORE_CONTROL_PROBE")
    python = get_value("EU4_PYTHON")
    timeout = min(30.0, remaining)
    command = [python, "-B", str(ROOT / "work/probe_control_state.py"),
               "--pid", str(pid), "--output", str(output)]
    try:
        subprocess.run(command, check=True, timeout=timeout,
                       capture_output=True, text=True)
    except subprocess.TimeoutExpired as error:
        raise ExperimentError("CONTROL_STATE_PROBE_TIMEOUT") from error
    except subprocess.CalledProcessError as error:
        raise ExperimentError(f"CONTROL_STATE_PROBE_FAILED:{error.returncode}") from error
    try:
        return json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExperimentError("CONTROL_STATE_OUTPUT_INVALID") from error


def _verify_session(installation: Path) -> tuple[ObserverSession, dict, dict, dict]:
    try:
        record = json.loads(installation.read_text(encoding="utf-8"))
        pid = int(record["pid"])
        expected_creation = int(record["creation_filetime"])
        expected_session = str(record["session_id"])
        expected_dll = str(record["dll_sha256"]).lower()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ExperimentError("INSTALLATION_RECORD_INVALID") from error
    if record.get("installation_returncode") != 0:
        raise ExperimentError("INSTALLATION_NOT_CONFIRMED")
    executable = game_exe()
    try:
        actual = probe_identity(pid, executable)
    except Exception as error:
        raise ExperimentError("OBSERVER_PROCESS_IDENTITY_UNAVAILABLE") from error
    if actual.get("pid") != pid or actual.get("creation_filetime") != expected_creation:
        raise ExperimentError("OBSERVER_PID_OR_CREATION_CHANGED")
    if actual.get("session_id") != expected_session:
        raise ExperimentError("OBSERVER_SESSION_CHANGED")
    modules = actual.get("modules") or []
    if len(modules) != 1 or str(modules[0].get("sha256", "")).lower() != expected_dll:
        raise ExperimentError("OBSERVER_DLL_HASH_MISMATCH")
    session = ObserverSession(installation, executable)
    health = session.health()
    if health.get("status") != "ready":
        raise ExperimentError("OBSERVER_FRAME_HEALTH_NOT_READY")
    evidence = {
        "pid": pid,
        "creation_filetime": expected_creation,
        "session_id": expected_session,
        "dll_sha256": expected_dll,
        "actual_modules": modules,
        "health": health,
    }
    return session, record, actual, evidence


def _read_meta_text(stream, limit: int = 4 * 1024 * 1024) -> str:
    data = bytearray()
    while len(data) < limit:
        chunk = stream.read(min(1024 * 1024, limit - len(data)))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data).decode("utf-8", errors="replace")


def _inspect_save(path: Path) -> dict[str, object]:
    file_size = path.stat().st_size
    if file_size <= MIN_SAVE_BYTES:
        return {"valid": False, "reason": "FILE_TOO_SMALL", "file_size": file_size}
    meta = ""
    payload_size = file_size
    container = "text"
    try:
        if zipfile.is_zipfile(path):
            container = "zip"
            with zipfile.ZipFile(path) as archive:
                with archive.open("meta", "r") as stream:
                    meta = _read_meta_text(stream)
                payload_size = 0
                with archive.open("gamestate", "r") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        payload_size += len(chunk)
        else:
            with path.open("rb") as stream:
                meta = _read_meta_text(stream)
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
        return {"valid": False, "reason": f"SAVE_READ_FAILED:{type(error).__name__}",
                "file_size": file_size, "container": container}
    player_match = re.search(r"(?m)^\s*player\s*=\s*\"?([A-Z]{3})", meta)
    date_match = re.search(r"(?m)^\s*date\s*=\s*\"?([0-9.]+)", meta)
    player = player_match.group(1) if player_match else None
    date = date_match.group(1) if date_match else None
    valid = (player == "POR" and date is not None and re.fullmatch(r"\d+\.\d{1,2}\.\d{1,2}", date) is not None
             and file_size > MIN_SAVE_BYTES and payload_size > MIN_SAVE_BYTES)
    return {
        "valid": valid,
        "reason": None if valid else "META_OR_SIZE_INVALID",
        "file_size": file_size,
        "payload_size": payload_size,
        "container": container,
        "player": player,
        "date": date,
    }


def _restore_originals(directory: Path, backup: Path,
                       baseline: dict[str, dict[str, object]], target_name: str,
                       emit=_emit) -> dict[str, object]:
    restored: list[str] = []
    errors: list[str] = []
    current_metadata = _snapshot_metadata(directory)
    rotating_baseline = _rotating_baseline(baseline)
    current = {path.name.casefold(): path for path in _save_paths(directory)}
    for key, record in rotating_baseline.items():
        original_name = str(record["name"])
        source = backup / original_name
        destination = current.get(key, directory / original_name)
        try:
            if not source.is_file():
                errors.append(f"BACKUP_MISSING:{original_name}")
                continue
            if not destination.is_file() or _sha256_stream(destination) != record["sha256"]:
                shutil.copy2(source, destination)
                restored.append(original_name)
            if _sha256_stream(destination) != record["sha256"]:
                errors.append(f"RESTORE_HASH_MISMATCH:{original_name}")
        except (OSError, KeyError) as error:
            errors.append(f"RESTORE_FAILED:{original_name}:{type(error).__name__}")
    unknown = [
        record["name"] for key, record in current_metadata.items()
        if key not in baseline and key != target_name.casefold()
    ]
    unknown_metadata = [
        _metadata_record(record) for key, record in current_metadata.items()
        if key not in baseline and key != target_name.casefold()
    ]
    metadata_changes = _metadata_changes(baseline, current_metadata, target_name)
    emit("originals_restored", restored=restored, errors=errors,
         unknown_new_save_files=unknown, unknown_new_save_metadata=unknown_metadata,
         metadata_changes=metadata_changes, rotating_restore_count=len(rotating_baseline))
    return {
        "restored": restored,
        "errors": errors,
        "unknown_new_save_files": unknown,
        "unknown_new_save_metadata": unknown_metadata,
        "metadata_changes": metadata_changes,
        "rotating_restore_count": len(rotating_baseline),
    }


def _wait_for_autosave(directory: Path, baseline: dict[str, dict[str, object]],
                       log: Path, start_offset: int, deadline: float,
                       emit=_emit) -> tuple[Path, dict, list[dict[str, object]]]:
    autosave_key = "autosave.eu4"
    baseline_autosave = baseline.get(autosave_key)
    seen_offsets: set[int] = set()
    observed: list[dict[str, object]] = []
    console_success = False
    stable_signature: tuple[int, int] | None = None
    stable_since: float | None = None
    last_candidate_signature: tuple[int, int] | None = None

    def reset_stability() -> None:
        """Discard a stability window after an autosave candidate is lost."""

        nonlocal stable_signature, stable_since, last_candidate_signature
        stable_signature = None
        stable_since = None
        last_candidate_signature = None

    while time.monotonic() < deadline:
        if log.exists() and log.stat().st_size < start_offset:
            raise ExperimentError("CONTROL_LOG_TRUNCATED")
        for line_offset, end_offset, event in _read_log_events(log, start_offset):
            if line_offset in seen_offsets:
                continue
            seen_offsets.add(line_offset)
            if event.get("event") != "control_console_result" or event.get("command") != "autosave":
                continue
            record = {
                "offset": line_offset,
                "end_offset": end_offset,
                "event": "control_console_result",
                "command": "autosave",
                "success": bool(event.get("success")),
            }
            observed.append(record)
            emit("autosave_console_result", **record)
            if not event.get("success"):
                raise ExperimentError("AUTOSAVE_CONSOLE_REJECTED")
            console_success = True
        candidate = _find_casefold(directory, "autosave.eu4") if console_success else None
        if candidate is None:
            reset_stability()
        else:
            try:
                signature = _stat_signature(candidate)
                changed = baseline_autosave is None or tuple(baseline_autosave["signature"]) != signature
                if not changed:
                    reset_stability()
                else:
                    inspection = _inspect_save(candidate)
                    if signature != last_candidate_signature:
                        last_candidate_signature = signature
                        emit("autosave_candidate_checked", path=str(candidate), **inspection)
                    if not inspection.get("valid"):
                        reset_stability()
                    elif signature != stable_signature:
                        stable_signature = signature
                        stable_since = time.monotonic()
                        emit("autosave_candidate_valid", path=str(candidate), signature=list(signature))
                    elif stable_since is not None and time.monotonic() - stable_since >= STABLE_SECONDS:
                        emit("autosave_stable", path=str(candidate), signature=list(signature))
                        return candidate, inspection, observed
            except FileNotFoundError:
                # Autosave rotation can remove the candidate after lookup or
                # while inspection opens it.  Its previous window is invalid;
                # retry the next poll without masking permission or other I/O
                # errors.
                reset_stability()
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(POLL_SECONDS, remaining))
    if not console_success:
        raise ExperimentError("AUTOSAVE_CONSOLE_SUCCESS_NOT_OBSERVED")
    raise ExperimentError("AUTOSAVE_FILE_NOT_VERIFIED")


def _validate_name(name: str) -> None:
    if not SAVE_NAME.fullmatch(name):
        raise ExperimentError("NAME_MUST_MATCH_llm_diplomacy_<unique>.eu4")


def _validate_timeout(timeout: int) -> int:
    if timeout < 1 or timeout > MAX_TIMEOUT:
        raise ExperimentError(f"TIMEOUT_MUST_BE_1_TO_{MAX_TIMEOUT}")
    return timeout


def _backup_directory(experiment_dir: Path, report_base: Path) -> Path:
    """Choose a non-overwriting backup directory for this report."""
    legacy = experiment_dir / "save-backup"
    if not legacy.exists():
        return legacy
    report_stamp = report_base.stem.removeprefix("save-observer-report-")
    return experiment_dir / f"save-backup-{report_stamp}"


def run_experiment(installation: Path, name: str, timeout: int = MAX_TIMEOUT,
                   expected_date: str | None = None) -> dict:
    """Run one operator-only archive experiment and return its report."""

    _validate_name(name)
    timeout = _validate_timeout(timeout)
    installation = installation.resolve()
    if not installation.is_file():
        raise ExperimentError("INSTALLATION_FILE_MISSING")
    experiment_dir = installation.parent
    report_base = experiment_dir / f"save-observer-report-{time.time_ns()}.json"
    request = experiment_dir / "game-control.request"
    log = experiment_dir / "control-probe.jsonl"
    backup = _backup_directory(experiment_dir, report_base)
    baseline: dict[str, dict[str, object]] = {}
    restore_info: dict[str, object] | None = None
    target: Path | None = None
    report_path: Path | None = None
    log_start: int | None = None
    request_created = False
    state: dict[str, object] = {
        "status": "failure",
        "name": name,
        "installation": str(installation),
        "request_token": AUTOSAVE_TOKEN.decode("ascii"),
        "child_processes": {"completed_or_stopped": True},
    }
    deadline = time.monotonic() + timeout
    try:
        session, installation_record, identity, session_evidence = _verify_session(installation)
        state["session"] = session_evidence
        emit = _emit
        emit("session_verified", pid=identity["pid"], creation_filetime=identity["creation_filetime"],
             dll_sha256=session_evidence["dll_sha256"], date_raw=session_evidence["health"].get("date_raw"))
        saves = user_data() / "save games"
        existing_target = _find_casefold(saves, name)
        if existing_target is not None:
            raise ExperimentError("TARGET_ALREADY_EXISTS_NO_OVERWRITE")
        if request.exists():
            raise ExperimentError("CONTROL_REQUEST_ALREADY_EXISTS")
        if not log.is_file():
            raise ExperimentError("CONTROL_LOG_MISSING")
        log_start = log.stat().st_size
        before_output = experiment_dir / f"probe-before-{time.time_ns()}.json"
        before_state = _probe_control_state(identity["pid"], before_output, deadline)
        before_signature = _state_signature(before_state)
        state["probe_before"] = {"path": str(before_output), "signature": before_signature}
        emit("paused_por_state_verified", phase="before", **before_signature)
        baseline = _snapshot_saves(saves)
        rotating_baseline = _rotating_baseline(baseline)
        metadata_only_baseline = {
            key: record for key, record in baseline.items()
            if key not in rotating_baseline
        }
        backup.mkdir(parents=False)
        for record in rotating_baseline.values():
            shutil.copy2(saves / str(record["name"]), backup / str(record["name"]))
        backup_manifest = {
            "created": True,
            "saves": baseline,
            "rotating_autosaves": rotating_baseline,
            "metadata_only_saves": metadata_only_baseline,
        }
        _write_json_exclusive(backup / "manifest.json", backup_manifest)
        state["backup"] = {
            "path": str(backup),
            "saves": baseline,
            "rotating_autosaves": rotating_baseline,
            "metadata_only_saves": metadata_only_baseline,
        }
        emit("original_saves_backed_up", path=str(backup),
             count=len(rotating_baseline), metadata_only_count=len(metadata_only_baseline),
             rotating_autosaves=list(ROTATING_AUTOSAVE_NAMES))
        # Recheck the destination and request immediately before the exclusive queue.
        if _find_casefold(saves, name) is not None:
            raise ExperimentError("TARGET_APPEARED_BEFORE_REQUEST_NO_OVERWRITE")
        with request.open("xb") as stream:
            stream.write(AUTOSAVE_TOKEN)
        request_created = True
        state["request"] = {"path": str(request), "offset": log_start,
                             "token": AUTOSAVE_TOKEN.decode("ascii")}
        emit("autosave_request_queued", path=str(request), log_start_offset=log_start)
        autosave, save_inspection, console_events = _wait_for_autosave(
            saves, baseline, log, log_start, deadline, emit=emit)
        state["console_events"] = console_events
        if expected_date is not None and save_inspection["date"] != expected_date:
            raise ExperimentError("SAVE_DATE_DIFFERS_FROM_EXPLICIT_EXPERIMENT_DATE")
        log_end = log.stat().st_size
        state["log_offsets"] = {"start": log_start, "end": log_end}
        after_output = experiment_dir / f"probe-after-{time.time_ns()}.json"
        after_state = _probe_control_state(identity["pid"], after_output, deadline)
        after_signature = _state_signature(after_state)
        state["probe_after"] = {"path": str(after_output), "signature": after_signature}
        emit("paused_por_state_verified", phase="after", **after_signature)
        if before_signature != after_signature:
            raise ExperimentError("CONTROL_STATE_CHANGED_DURING_AUTOSAVE")
        health_after = session.health()
        if health_after.get("status") != "ready":
            raise ExperimentError("OBSERVER_FRAME_HEALTH_LOST")
        state["session"]["health_after"] = health_after
        target = saves / name
        if _find_casefold(saves, name) is not None:
            raise ExperimentError("TARGET_APPEARED_BEFORE_ARCHIVE_NO_OVERWRITE")
        source_hash = _sha256_stream(autosave)
        _copy_new_file(autosave, target)
        target_inspection = _inspect_save(target)
        if not target_inspection.get("valid"):
            raise ExperimentError("ARCHIVE_COPY_FAILED_VALIDATION")
        target_hash = _sha256_stream(target)
        if target_hash != source_hash or _sha256_stream(autosave) != source_hash:
            raise ExperimentError("AUTOSAVE_CHANGED_OR_ARCHIVE_COPY_HASH_MISMATCH")
        emit("archive_created", path=str(target), sha256=target_hash)
        restore_info = _restore_originals(saves, backup, baseline, name, emit=emit)
        if restore_info["errors"]:
            raise ExperimentError("ORIGINAL_SAVE_RESTORE_FAILED")
        if _sha256_stream(target) != target_hash:
            raise ExperimentError("ARCHIVE_HASH_CHANGED")
        state.update({
            "status": "success",
            "save": {"path": str(target), "sha256": target_hash,
                     "source": str(autosave), "inspection": target_inspection},
            "native_save": {"path": str(autosave), "inspection": save_inspection},
            "restore": restore_info,
            "finished_at_unix": time.time(),
        })
        report_path = _write_json_exclusive(report_base, state)
        state["report"] = str(report_path)
        emit("experiment_complete", report=str(report_path), target=str(target))
        return state
    except Exception as error:
        state["error"] = str(error)
        state["error_type"] = type(error).__name__
        if log_start is not None and log.exists():
            try:
                current_events = [
                    {"offset": offset, "end_offset": end, "event": event.get("event"),
                     "command": event.get("command"), "success": event.get("success")}
                    for offset, end, event in _read_log_events(log, log_start)
                    if event.get("event") == "control_console_result"
                    and event.get("command") == "autosave"
                ]
                state.setdefault("console_events", current_events)
                state.setdefault("log_offsets", {"start": log_start, "end": log.stat().st_size})
            except OSError as log_error:
                state["log_read_error"] = str(log_error)
        if baseline and backup.is_dir():
            try:
                restore_info = _restore_originals(saves, backup, baseline, name, emit=_emit)  # type: ignore[name-defined]
                state["restore"] = restore_info
            except Exception as restore_error:
                state["restore"] = {"errors": [str(restore_error)]}
        if request_created and request.exists():
            try:
                with request.open("rb") as request_stream:
                    request_token = request_stream.read(len(AUTOSAVE_TOKEN) + 1)
                if request_token == AUTOSAVE_TOKEN:
                    request.unlink()
                    state["request_cleaned"] = True
            except OSError as cleanup_error:
                state["request_cleanup_error"] = str(cleanup_error)
        state["finished_at_unix"] = time.time()
        try:
            report_path = _write_json_exclusive(report_base, state)
            state["report"] = str(report_path)
        except Exception as report_error:
            state["report_error"] = str(report_error)
        _emit("experiment_failed", error=str(error), report=str(report_path) if report_path else None)
        raise ExperimentError(str(error)) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="r3 installation.json for the already running observer")
    parser.add_argument("--name", required=True,
                        help="llm_diplomacy_<unique>.eu4; existing targets are never overwritten")
    parser.add_argument("--timeout", type=int, default=MAX_TIMEOUT)
    parser.add_argument("--expected-date", help="Save metadata date such as 1445.3.12 (not the native date_raw integer)")
    args = parser.parse_args(argv)
    try:
        report = run_experiment(args.installation, args.name, args.timeout, args.expected_date)
    except ExperimentError as error:
        print(json.dumps({"status": "failure", "error": str(error)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps({"status": report["status"], "report": report["report"],
                      "save": report["save"], "restored_originals": report["restore"]["restored"]},
                     ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
