"""Operator-only install of one immutable observer build into one game process.

Startup can expose the country database before the world and load-warning
dialog are ready. The ready loop probes the same verified PID and creation
time. Repeated missing confirmations permit one window minimize/restore to
release the observed D3D/DWM startup wait. Once installation is recorded, the
native installer is called exactly once and its error is terminal.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "work"))
from local_config import game_exe, get_value
from bridge.diplomacy_session import file_hash, probe_identity
from acknowledge_startup_error import acknowledge_startup_error
from work.observer_runtime_ready import (
    _enumerate_windows_for_pid, _is_iconic, _show_window_async,
)


MAX_WAIT_READY = 300
PREFLIGHT_TIMEOUT = 30.0
DIALOG_SCAN_TIMEOUT = 22.0
DIALOG_ATTEMPT_TIMEOUT = 52.0
READY_POLL_SECONDS = 3.0
IDENTITY_POLL_SECONDS = 1.0
STARTUP_ERROR_SCAN_SECONDS = 5.0
TRANSIENT_IDENTITY_WINERRORS = frozenset((6, 299))


def _recover_startup_render_window(pid: int) -> dict:
    """Reset one identified game's presentation once; no game data changes."""
    windows = _enumerate_windows_for_pid(pid)
    if len(windows) != 1:
        return {"attempted": False, "reason": "GAME_WINDOW_NOT_UNIQUE"}
    hwnd = windows[0]
    iconic = _is_iconic(hwnd)
    minimized = False
    if not iconic:
        minimized = _show_window_async(hwnd, 6)
        if not minimized:
            return {"attempted": True, "window": hwnd,
                    "minimize_requested": False, "restore_requested": False}
        time.sleep(0.5)
    restored = _show_window_async(hwnd, 4)
    return {"attempted": True, "window": hwnd, "initially_iconic": iconic,
            "minimize_requested": minimized, "restore_requested": restored}


def bounded_wait_ready(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--wait-ready must be an integer") from error
    if seconds < 1 or seconds > MAX_WAIT_READY:
        raise argparse.ArgumentTypeError(f"--wait-ready must be between 1 and {MAX_WAIT_READY} seconds")
    return seconds


def _waiting(attempt: int, reason: str, started: float, phase: str = "readiness") -> None:
    print(json.dumps({
        "state": "waiting",
        "attempt": attempt,
        "phase": phase,
        "reason": reason,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }, ensure_ascii=False, sort_keys=True), flush=True)


def _transient_identity_winerror(error: BaseException) -> int | None:
    """Return the explicitly retryable Win32 identity-probe error, if any.

    ``probe_identity`` raises the ctypes ``OSError`` produced by
    ``K32GetModuleFileNameExW``.  The module can briefly be unavailable while
    the process is starting, which is represented by ERROR_INVALID_HANDLE (6)
    or, on some Windows builds, ERROR_PARTIAL_COPY (299).  Keep this check
    narrow so process termination, image/hash mismatches, and arbitrary probe
    failures remain terminal.
    """

    if not isinstance(error, OSError):
        return None
    winerror = getattr(error, "winerror", None)
    return winerror if winerror in TRANSIENT_IDENTITY_WINERRORS else None


def _attempt_directory(directory: Path, attempt: int) -> Path:
    path = directory / f"ready-attempt-{attempt:03d}-{time.time_ns()}"
    path.mkdir(parents=False, exist_ok=False)
    return path


def _write_attempt_error(path: Path, stdout: str = "", stderr: str = "") -> None:
    path.write_text(stdout + stderr, encoding="utf-8")


def _remaining_timeout(deadline: float, maximum: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("READY_WAIT_DEADLINE_EXPIRED")
    return min(maximum, remaining)


def _assert_same_unloaded_process(expected: dict, current: dict, manifest: dict) -> None:
    if current.get("pid") != expected.get("pid"):
        raise RuntimeError("PID_CHANGED_NO_RETRY")
    if current.get("creation_filetime") != expected.get("creation_filetime"):
        raise RuntimeError("PROCESS_CREATION_CHANGED_NO_RETRY")
    if current.get("session_id") != expected.get("session_id"):
        raise RuntimeError("PROCESS_SESSION_CHANGED_NO_RETRY")
    if current.get("game_sha256") != manifest["game_sha256"]:
        raise RuntimeError("GAME_HASH_CHANGED_NO_RETRY")
    if current.get("modules"):
        raise RuntimeError("BRIDGE_ALREADY_LOADED_NO_RETRY")


def _read_scan_cursor(attempt_directory: Path, fallback: int) -> int:
    try:
        report = json.loads((attempt_directory / "startup-dialogs.json").read_text(encoding="utf-8"))
        if report.get("scan_complete"):
            return 0
        return int(report.get("next_scan_address", hex(fallback)), 0)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return fallback


def confirmation_request(pid: int, state: dict, attempt_directory: Path,
                         resume_address: int = 0) -> str:
    """Find exactly one verified load-warning button within this attempt."""

    python = get_value("EU4_PYTHON")
    dialogs = attempt_directory / "startup-dialogs.json"
    scan_environment = {**os.environ, "EU4_DIALOG_SCAN_START": hex(max(0, resume_address))}
    attempt_deadline = time.monotonic() + DIALOG_ATTEMPT_TIMEOUT
    try:
        subprocess.run([
            python, "-B", str(ROOT / "work/probe_startup_dialogs.py"),
            "--pid", str(pid), "--output", str(dialogs),
        ], check=True, timeout=min(DIALOG_SCAN_TIMEOUT,
                                  _remaining_timeout(attempt_deadline, DIALOG_SCAN_TIMEOUT)),
            stdout=subprocess.DEVNULL, env=scan_environment)
    except subprocess.TimeoutExpired as error:
        _write_attempt_error(attempt_directory / "startup-dialogs.error.txt", "timeout\n")
        raise RuntimeError("LOAD_WARNING_SCAN_TIMEOUT") from error
    base = int(state["module_base"], 16)
    matches = []
    for dialog_index, obj in enumerate(json.loads(dialogs.read_text(encoding="utf-8"))["dialogs"]):
        if obj["name"] != "DefaultConfirm":
            continue
        details_path = attempt_directory / f"popup-details-{dialog_index}.jsonl"
        try:
            completed = subprocess.run([
                python, "-B", str(ROOT / "work/read_popup_details.py"),
                "--pid", str(pid), "--peace-address", obj["object"],
            ], check=True, capture_output=True, text=True, encoding="utf-8",
                timeout=min(30.0, _remaining_timeout(attempt_deadline, 30.0)),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired as error:
            _write_attempt_error(details_path.with_suffix(".error.txt"), "timeout\n")
            raise RuntimeError("POPUP_DETAILS_TIMEOUT") from error
        details_path.write_text(completed.stdout, encoding="utf-8")
        for line in completed.stdout.splitlines():
            child = json.loads(line)
            if child["name"] != "agreebutton" or len(child.get("listeners", [])) != 2:
                continue
            first, second = child["listeners"]
            blob = bytes.fromhex(second["data"])
            owner = int.from_bytes(blob[8:16], "little")
            callback = int.from_bytes(blob[16:24], "little")
            if int(first["listener"], 16) == int(obj["object"], 16) + 0x18 and callback == base + 0x10ef2e0:
                matches.append(f"TEST_ONLY {pid} {int(obj['object'], 16):x} {int(child['child'], 16):x} {owner:x}\n")
    if len(matches) != 1:
        raise RuntimeError("UNIQUE_VERIFIED_LOAD_CONFIRMATION_NOT_FOUND")
    return matches[0]


def _preflight_once(pid: int, python: str, attempt_directory: Path,
                    deadline: float) -> tuple[dict | None, dict]:
    preflight = attempt_directory / "preflight.json"
    command = [python, "-B", str(ROOT / "work/probe_native_state.py"),
               "--pid", str(pid), "--output", str(preflight)]
    try:
        checked = subprocess.run(command, timeout=_remaining_timeout(deadline, PREFLIGHT_TIMEOUT),
                                 capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        _write_attempt_error(attempt_directory / "preflight.error.txt", "timeout\n")
        return None, {"reason": "PREFLIGHT_TIMEOUT", "preflight": str(preflight)}
    if checked.returncode:
        _write_attempt_error(attempt_directory / "preflight.error.txt", checked.stdout, checked.stderr)
        return None, {"reason": f"PREFLIGHT_RETURN_{checked.returncode}", "preflight": str(preflight)}
    try:
        state = json.loads(preflight.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _write_attempt_error(attempt_directory / "preflight.error.txt", str(error) + "\n")
        return None, {"reason": "PREFLIGHT_OUTPUT_INVALID", "preflight": str(preflight)}
    return state, {"reason": "PREFLIGHT_READY", "preflight": str(preflight)}


def _wait_until_ready(pid: int, manifest: dict, directory: Path, confirm_load_warning: bool,
                      wait_ready: int) -> tuple[dict, dict, str | None, str, list[dict]]:
    """Return identity, ready state, optional confirmation and attempt evidence."""

    started = time.monotonic()
    deadline = started + wait_ready
    attempts: list[dict] = []

    # The first module enumeration can race the game's startup loader.  Keep
    # these narrowly classified identity errors inside the same overall
    # readiness deadline; all other probe failures still propagate.
    expected: dict | None = None
    identity_attempt = 0
    while expected is None:
        if time.monotonic() >= deadline:
            raise SystemExit("WORLD_NOT_READY_TIMEOUT_NO_INSTALLATION_ATTEMPTED")
        identity_attempt += 1
        try:
            candidate = probe_identity(pid, game_exe())
        except OSError as error:
            winerror = _transient_identity_winerror(error)
            if winerror is None:
                raise
            reason = f"IDENTITY_PROBE_TRANSIENT_WINERROR_{winerror}"
            attempts.append({
                "attempt": identity_attempt,
                "phase": "identity_probe",
                "outcome": "waiting",
                "reason": reason,
                "winerror": winerror,
            })
            _waiting(identity_attempt, reason, started, phase="identity_probe")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SystemExit("WORLD_NOT_READY_TIMEOUT_NO_INSTALLATION_ATTEMPTED")
            time.sleep(min(IDENTITY_POLL_SECONDS, remaining))
            continue
        if candidate["modules"] or candidate["game_sha256"] != manifest["game_sha256"]:
            raise SystemExit("FRESH_VERIFIED_GAME_PROCESS_REQUIRED")
        expected = candidate

    python = get_value("EU4_PYTHON")
    attempt_number = 0
    scan_resume_address = 0
    startup_error_acknowledged = False
    startup_error_attempted = False
    next_startup_error_scan = 0.0
    missing_confirmations = 0
    render_recovery_attempted = False

    def ready_identity() -> dict:
        current = probe_identity(pid, game_exe())
        _assert_same_unloaded_process(expected, current, manifest)
        return current

    while time.monotonic() < deadline:
        if (directory / "installation.json").exists():
            raise SystemExit("EXPERIMENT_ALREADY_ATTEMPTED_USE_NEW_DIRECTORY_AND_PROCESS")
        attempt_number += 1
        attempt_directory = _attempt_directory(directory, attempt_number)
        try:
            current = probe_identity(pid, game_exe())
            _assert_same_unloaded_process(expected, current, manifest)
            state, evidence = _preflight_once(pid, python, attempt_directory, deadline)
            attempt = {"attempt": attempt_number, "directory": str(attempt_directory), **evidence}
            attempts.append(attempt)
            if state is None:
                now = time.monotonic()
                if (not startup_error_acknowledged and not startup_error_attempted
                        and now >= next_startup_error_scan):
                    next_startup_error_scan = now + STARTUP_ERROR_SCAN_SECONDS
                    try:
                        startup_error = acknowledge_startup_error(pid, attempt_directory)
                    except Exception as error:
                        attempt["startup_error_check_error"] = str(error)
                    else:
                        if startup_error is not None:
                            startup_error_attempted = (
                                startup_error.get("attempted") is True
                                or startup_error.get("acknowledged") is True)
                            startup_error_acknowledged = True
                            if startup_error.get("acknowledged") is True:
                                attempt["startup_error_acknowledged"] = True
                            else:
                                startup_error_acknowledged = False
                                attempt["startup_error_acknowledged"] = False
                            attempt["startup_error_ack_evidence"] = startup_error
                            if startup_error.get("terminal") is True:
                                attempt["startup_error_terminal"] = True
                                raise SystemExit(str(
                                    startup_error.get(
                                        "reason", "STARTUP_ERROR_DIALOG_NO_RETRY")))
                _waiting(attempt_number, evidence["reason"], started)
            else:
                player_tag = state.get("player_tag")
                if player_tag not in ("---", "POR"):
                    raise SystemExit("FIXED_CONTROL_REQUIRES_UNLOADED_OR_POR_TEST_SAVE")
                confirmation = None
                if player_tag == "POR":
                    attempt.update({"outcome": "ready", "ready_reason": "por_already_loaded"})
                    return ready_identity(), state, confirmation, "por_already_loaded", attempts
                if not confirm_load_warning:
                    attempt.update({"outcome": "ready", "ready_reason": "unloaded_no_confirmation_requested"})
                    return ready_identity(), state, confirmation, "unloaded_no_confirmation_requested", attempts
                try:
                    confirmation = confirmation_request(pid, state, attempt_directory, scan_resume_address)
                except Exception as error:
                    scan_resume_address = _read_scan_cursor(attempt_directory, scan_resume_address)
                    attempt.update({"outcome": "not_ready", "reason": str(error)})
                    if str(error) == "UNIQUE_VERIFIED_LOAD_CONFIRMATION_NOT_FOUND":
                        missing_confirmations += 1
                        if missing_confirmations >= 3 and not render_recovery_attempted:
                            render_recovery_attempted = True
                            attempt["render_window_recovery"] = _recover_startup_render_window(pid)
                    _waiting(attempt_number, str(error), started)
                else:
                    scan_resume_address = _read_scan_cursor(attempt_directory, scan_resume_address)
                    attempt.update({"outcome": "ready", "ready_reason": "verified_load_confirmation"})
                    return ready_identity(), state, confirmation, "verified_load_confirmation", attempts
        except SystemExit:
            raise
        except Exception as error:
            # Identity/process failures are terminal; read-only preflight errors
            # are recorded per attempt and may be retried until the deadline.
            if isinstance(error, RuntimeError) and str(error).endswith("NO_RETRY"):
                raise SystemExit(str(error)) from error
            attempt = {"attempt": attempt_number, "directory": str(attempt_directory),
                       "outcome": "not_ready", "reason": str(error)}
            attempts.append(attempt)
            _waiting(attempt_number, str(error), started)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(READY_POLL_SECONDS, remaining))
    raise SystemExit("WORLD_NOT_READY_TIMEOUT_NO_INSTALLATION_ATTEMPTED")


def _install_once(pid: int, manifest: dict, directory: Path, dll: Path, python: str,
                  identity: dict, state: dict, confirmation: str | None,
                  ready_reason: str, attempts: list[dict], native_text_codec: str = "utf8") -> None:
    destination = directory / "installation.json"
    if destination.exists():
        raise SystemExit("EXPERIMENT_ALREADY_ATTEMPTED_USE_NEW_DIRECTORY_AND_PROCESS")
    current = probe_identity(pid, game_exe())
    _assert_same_unloaded_process(identity, current, manifest)
    record = {
        **identity,
        "experiment_id": manifest["experiment_id"],
        "dll_sha256": manifest["dll_sha256"],
        "installation_attempted": True,
        "installation_started": True,
        "installation_returncode": None,
        "runtime_verified": False,
        "ready_reason": ready_reason,
        "ready_attempts": attempts,
        "preflight_player_tag": state.get("player_tag"),
        "native_text_codec": native_text_codec,
        "native_text_codec_module_provenance_verified": False,
    }
    destination.write_text(json.dumps(record, indent=2), encoding="utf-8")
    try:
        result = subprocess.run([
            python, "-B", str(ROOT / "work/native/inject_probe.py"),
            "--pid", str(pid), "--dll", str(dll), "--ack-test-save",
        ], capture_output=True, text=True, timeout=65)
    except subprocess.TimeoutExpired:
        record["installation_timeout"] = True
        (directory / "loader-output.txt").write_text("timeout\n", encoding="utf-8")
        destination.write_text(json.dumps(record, indent=2), encoding="utf-8")
        raise SystemExit("INSTALLATION_TIMEOUT_NO_RETRY")
    (directory / "loader-output.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    record["installation_returncode"] = result.returncode
    destination.write_text(json.dumps(record, indent=2), encoding="utf-8")
    if result.returncode:
        raise SystemExit("INSTALLATION_FAILED_NO_RETRY_IN_THIS_PROCESS")
    record["modules_after_install"] = probe_identity(pid, game_exe())["modules"]
    destination.write_text(json.dumps(record, indent=2), encoding="utf-8")
    if confirmation:
        with (directory / "popup-confirm.request").open("x", encoding="ascii", newline="\n") as stream:
            stream.write(confirmation)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--confirm-load-warning", action="store_true")
    parser.add_argument("--native-text-codec", choices=("utf8", "eu4_escape"), default="utf8",
                        help="operator-bound native text decoder; never inferred from LLM arguments")
    parser.add_argument("--wait-ready", type=bounded_wait_ready, default=120,
                        help="bounded read-only readiness wait in seconds (default: 120, max: 300)")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    directory = args.manifest.resolve().parent
    version = manifest.get("version")
    if type(version) is not int or version not in (10, 21, 22):
        raise SystemExit("BUILD_MANIFEST_MISMATCH")
    dll = directory / f"eu4_bridge_diplomacy_observer_v{version}.dll"
    if not dll.is_file() or file_hash(dll) != manifest["dll_sha256"]:
        raise SystemExit("BUILD_MANIFEST_MISMATCH")
    if (directory / "installation.json").exists():
        raise SystemExit("EXPERIMENT_ALREADY_ATTEMPTED_USE_NEW_DIRECTORY_AND_PROCESS")
    identity, state, confirmation, ready_reason, attempts = _wait_until_ready(
        args.pid, manifest, directory, args.confirm_load_warning, args.wait_ready)
    _install_once(args.pid, manifest, directory, dll, get_value("EU4_PYTHON"),
                  identity, state, confirmation, ready_reason, attempts, args.native_text_codec)
    print(json.dumps({"installed": True, "experiment_id": manifest["experiment_id"],
                      "session_id": identity["session_id"], "confirmation_queued": bool(confirmation),
                      "ready_reason": ready_reason, "ready_attempts": len(attempts),
                      "diplomacy_runtime_verified": False}), flush=True)


if __name__ == "__main__":
    main()
