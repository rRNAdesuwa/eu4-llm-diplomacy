"""Bounded readiness wait for an already-installed observer session.

The observer can acknowledge installation before its first usable frame
heartbeat.  This helper waits on the bounded control-probe tail and performs
one final session health check after a matching heartbeat appears.  It never
starts a process, installs a DLL, or polls the full game identity repeatedly.
"""

from __future__ import annotations

import json
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import time
from typing import Any
import uuid

from bridge.diplomacy_session import probe_identity


_HEARTBEAT_TAIL_BYTES = 64 * 1024
_HEARTBEAT_FRESH_SECONDS = 5.0
_POLL_SECONDS = 0.2
_MAX_TIMEOUT_SECONDS = 30.0
_GAME_WINDOW_TITLE = "Europa Universalis IV"
_SW_SHOWNOACTIVATE = 4


def _heartbeat_thread_token(event: dict) -> tuple[str, int | str] | tuple[str]:
    """Return the comparable thread identity carried by one heartbeat.

    Older observer builds only emitted ``thread_changed``.  Such records use
    one legacy token and still require the explicit unchanged flag on every
    heartbeat.  Builds that emit a thread number (or ``thread_id``) are
    compared by that value as well.
    """

    if "thread" in event:
        value = event.get("thread")
    elif "thread_id" in event:
        value = event.get("thread_id")
    else:
        return ("legacy",)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return ()
    if isinstance(value, str) and not value:
        return ()
    return ("thread", value)


def _stable_matching_heartbeat(events: list[object], expected_session: str,
                               *, player: str = "POR") -> dict | None:
    """Return the last heartbeat in a consecutive stable pair.

    The pair must carry the same session, thread identity, player and
    ``date_raw``; each event must state a readable world and unchanged frame
    thread; and its integer frame counter must strictly increase.  A later
    same-session heartbeat that breaks those conditions clears the pair, so an
    earlier stable pair cannot make a changed or stale world appear ready.
    """

    if not isinstance(expected_session, str) or not expected_session:
        return None
    previous_context: tuple[object, ...] | None = None
    previous_frames: int | None = None
    stable_event: dict | None = None
    for candidate in events:
        if not isinstance(candidate, dict):
            continue
        if (candidate.get("event") != "diplomacy_observer_health"
                or candidate.get("session_id") != expected_session):
            continue
        frames = candidate.get("frames")
        date_raw = candidate.get("date_raw")
        thread_token = _heartbeat_thread_token(candidate)
        context = (
            thread_token, candidate.get("player"), date_raw,
        )
        valid = (
            candidate.get("state_readable") is True
            and candidate.get("thread_changed") is False
            and candidate.get("player") == player
            and isinstance(date_raw, int) and not isinstance(date_raw, bool)
            and isinstance(frames, int) and not isinstance(frames, bool)
            and thread_token != ()
        )
        if (valid and previous_context == context
                and previous_frames is not None and frames > previous_frames):
            stable_event = candidate
        else:
            stable_event = None
        if valid:
            previous_context = context
            previous_frames = frames
        else:
            previous_context = None
            previous_frames = None
    return stable_event


def _enumerate_windows_for_pid(pid: int, title: str = _GAME_WINDOW_TITLE) -> list[int]:
    """Return top-level windows for one PID with the exact game title."""

    if os.name != "nt" or pid <= 0:
        return []
    try:
        user32 = C.WinDLL("user32", use_last_error=True)
        user32.EnumWindows.argtypes = [C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM), W.LPARAM]
        user32.EnumWindows.restype = W.BOOL
        user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        user32.GetWindowThreadProcessId.restype = W.DWORD
        user32.GetWindowTextLengthW.argtypes = [W.HWND]
        user32.GetWindowTextLengthW.restype = C.c_int
        user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        user32.GetWindowTextW.restype = C.c_int
    except (AttributeError, OSError):
        return []

    matches: list[int] = []
    callback_type = user32.EnumWindows.argtypes[0]

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        owner_pid = W.DWORD()
        if user32.GetWindowThreadProcessId(hwnd, C.byref(owner_pid)) == 0:
            return True
        if owner_pid.value != pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = C.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        if buffer.value == title:
            matches.append(int(hwnd))
        return True

    try:
        user32.EnumWindows(callback, 0)
    except (OSError, TypeError):
        return []
    return matches


def _is_iconic(hwnd: int) -> bool:
    if os.name != "nt":
        return False
    try:
        user32 = C.WinDLL("user32", use_last_error=True)
        user32.IsIconic.argtypes = [W.HWND]
        user32.IsIconic.restype = W.BOOL
        return bool(user32.IsIconic(W.HWND(hwnd)))
    except (AttributeError, OSError, TypeError):
        return False


def _show_window_async(hwnd: int, command: int = _SW_SHOWNOACTIVATE) -> bool:
    """Show a minimized window without activating it or changing foreground."""

    if os.name != "nt":
        return False
    try:
        user32 = C.WinDLL("user32", use_last_error=True)
        user32.ShowWindowAsync.argtypes = [W.HWND, C.c_int]
        user32.ShowWindowAsync.restype = W.BOOL
        return bool(user32.ShowWindowAsync(W.HWND(hwnd), command))
    except (AttributeError, OSError, TypeError):
        return False


def _record_window_restore(session: Any, pid: int, hwnd: int,
                           show_result: bool, error: str | None = None) -> None:
    directory = getattr(session, "directory", None)
    if not isinstance(directory, (str, Path)):
        return
    evidence = {
        "event": "runtime_window_restore",
        "session_id": getattr(session, "session_id", None),
        "pid": pid,
        "hwnd": hwnd,
        "title": _GAME_WINDOW_TITLE,
        "identity_verified": True,
        "minimized": True,
        "show_command": _SW_SHOWNOACTIVATE,
        "show_window_async_called": 1,
        "show_window_async_result": bool(show_result),
        "foreground_activation": False,
        "status": "requested" if show_result else "failed",
    }
    if error:
        evidence["error"] = error
    path = Path(directory) / f"runtime-window-restore-{uuid.uuid4().hex}.json"
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError:
        return


def restore_minimized_runtime_window(session: Any) -> bool:
    """Restore one verified minimized game window without foreground activation."""

    record = getattr(session, "record", None)
    pid = record.get("pid") if isinstance(record, dict) else None
    expected_session = getattr(session, "session_id", None)
    game_exe = getattr(session, "game_exe", None)
    if (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0
            or not isinstance(expected_session, str) or not expected_session
            or not isinstance(game_exe, (str, Path))):
        return False
    try:
        current = probe_identity(pid, Path(game_exe))
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    if not isinstance(current, dict) or current.get("session_id") != expected_session:
        return False
    windows = _enumerate_windows_for_pid(pid, _GAME_WINDOW_TITLE)
    if len(windows) != 1 or not _is_iconic(windows[0]):
        return False
    hwnd = windows[0]
    try:
        restored = _show_window_async(hwnd, _SW_SHOWNOACTIVATE)
        _record_window_restore(session, pid, hwnd, restored)
        return bool(restored)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        _record_window_restore(session, pid, hwnd, False, type(error).__name__)
        return False


def _fresh_matching_heartbeat(session: Any, log_path: Path) -> bool:
    """Return whether the bounded log tail has a fresh stable heartbeat pair."""

    try:
        stat = log_path.stat()
        if time.time() - stat.st_mtime > _HEARTBEAT_FRESH_SECONDS:
            return False
        tail_size = min(stat.st_size, _HEARTBEAT_TAIL_BYTES)
        with log_path.open("rb") as stream:
            stream.seek(max(0, stat.st_size - tail_size))
            tail = stream.read(tail_size)
    except OSError:
        return False

    expected_session = getattr(session, "session_id", None)
    if not isinstance(expected_session, str) or not expected_session:
        return False
    events: list[object] = []
    for raw_line in tail.splitlines():
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        events.append(event)
    return _stable_matching_heartbeat(events, expected_session) is not None


def wait_runtime_ready(session: Any, timeout: float = _MAX_TIMEOUT_SECONDS,
                       restore_minimized: bool = False) -> dict:
    """Wait for two fresh stable heartbeats, then perform one final health check.

    The initial ``session.health()`` is returned unchanged when the bounded
    wait expires or the session has no usable directory/log.  During the wait
    only the last 64 KiB of ``control-probe.jsonl`` is read; ``health`` is
    deliberately not called on each poll.
    """

    initial_health = session.health()
    if isinstance(initial_health, dict) and initial_health.get("status") == "ready":
        return initial_health

    try:
        bounded_timeout = min(max(float(timeout), 0.0), _MAX_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        bounded_timeout = 0.0
    if restore_minimized:
        restore_minimized_runtime_window(session)
    if bounded_timeout <= 0.0:
        return initial_health

    directory = getattr(session, "directory", None)
    if not isinstance(directory, (str, Path)):
        return initial_health
    log_path = Path(directory) / "control-probe.jsonl"
    deadline = time.monotonic() + bounded_timeout
    while time.monotonic() < deadline:
        if _fresh_matching_heartbeat(session, log_path):
            # This is the only second health call.  It rechecks identity,
            # loaded module and current heartbeat through the real session.
            return session.health()
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            break
        time.sleep(min(_POLL_SECONDS, remaining))
    return initial_health


__all__ = ["restore_minimized_runtime_window", "wait_runtime_ready"]
