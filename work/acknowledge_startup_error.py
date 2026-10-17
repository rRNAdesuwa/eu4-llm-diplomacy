"""A bounded acknowledgement for the known EU4 startup error dialog.

The dialog is an already-present process error, not an update workflow.  This
module only posts the dialog's own ``WM_COMMAND`` when every identifying field
has an exact match for the requested process.  It does not launch programs,
download anything, or interact with any other window.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import json
import os
from pathlib import Path
import time
from typing import Callable, Iterable


WM_COMMAND = 0x0111
ERROR_DIALOG_TITLE = "DLL autoupdate failed"
ERROR_DIALOG_CLASS = "#32770"
ERROR_STATIC_TEXT = "DLL autoupdate WAIT_TIMEOUT"
ERROR_BUTTON_TEXT = "确定"
ERROR_BUTTON_ID = 2
ACK_SETTLE_SECONDS = 2.0
ACK_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class WindowInfo:
    """The small amount of window state needed for strict matching."""

    hwnd: int
    parent_hwnd: int
    pid: int
    class_name: str
    title: str
    control_id: int | None = None


@dataclass(frozen=True)
class StartupErrorMatch:
    dialog_hwnd: int
    static_hwnd: int
    button_hwnd: int


def find_startup_error_dialog(windows: Iterable[WindowInfo], pid: int) -> StartupErrorMatch | None:
    """Return one exact dialog match, or ``None`` for zero/multiple matches."""

    captured = tuple(windows)
    dialogs = tuple(
        window for window in captured
        if window.pid == pid
        and window.parent_hwnd == 0
        and window.class_name == ERROR_DIALOG_CLASS
        and window.title == ERROR_DIALOG_TITLE
    )
    matches: list[StartupErrorMatch] = []
    for dialog in dialogs:
        statics = tuple(
            window for window in captured
            if window.pid == pid
            and window.parent_hwnd == dialog.hwnd
            and window.class_name == "Static"
            and window.title == ERROR_STATIC_TEXT
        )
        buttons = tuple(
            window for window in captured
            if window.pid == pid
            and window.parent_hwnd == dialog.hwnd
            and window.class_name == "Button"
            and window.title == ERROR_BUTTON_TEXT
            and window.control_id == ERROR_BUTTON_ID
        )
        if len(statics) == 1 and len(buttons) == 1:
            matches.append(StartupErrorMatch(dialog.hwnd, statics[0].hwnd, buttons[0].hwnd))
    return matches[0] if len(matches) == 1 else None


def acknowledge_collected_windows(
    pid: int,
    windows: Iterable[WindowInfo],
    attempt_directory: Path,
    post_message: Callable[[int, int, int, int], bool],
    *,
    probe_dialog: Callable[[int, int], str] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    settle_seconds: float = ACK_SETTLE_SECONDS,
) -> dict | None:
    """Acknowledge an exact collected match using an injected message sender.

    The injected sender keeps the matching policy testable without touching
    real windows.  A message being accepted by ``PostMessageW`` is only an
    attempt: with ``probe_dialog`` supplied, the exact dialog must disappear
    before ``acknowledged`` becomes true.  A hung dialog is terminal for this
    process, while a responsive dialog is waited on once without reposting.
    """

    evidence_path = attempt_directory / "startup-error-ack.json"
    if evidence_path.exists():
        try:
            existing = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (isinstance(existing, dict)
                and (existing.get("acknowledged") is True
                     or existing.get("attempted") is True)):
            return existing
        return None

    match = find_startup_error_dialog(windows, pid)
    if match is None:
        return None
    if not post_message(match.dialog_hwnd, WM_COMMAND, ERROR_BUTTON_ID, match.button_hwnd):
        return None

    probe_history: list[str] = []
    acknowledged = True
    terminal = False
    reason = "MESSAGE_POSTED_NO_RUNTIME_PROBE"
    if probe_dialog is not None:
        acknowledged = False
        reason = "STARTUP_ERROR_DIALOG_NOT_DISMISSED"
        deadline = monotonic() + max(0.0, float(settle_seconds))
        while True:
            state = probe_dialog(pid, match.dialog_hwnd)
            probe_history.append(state)
            if state == "gone":
                acknowledged = True
                reason = "STARTUP_ERROR_DIALOG_DISMISSED"
                break
            if state == "hung":
                terminal = True
                reason = "STARTUP_ERROR_DIALOG_HUNG_NO_RETRY"
                break
            if state == "changed":
                terminal = True
                reason = "STARTUP_ERROR_DIALOG_IDENTITY_CHANGED_NO_RETRY"
                break
            if state != "responsive":
                terminal = True
                reason = "STARTUP_ERROR_DIALOG_PROBE_INVALID_NO_RETRY"
                break
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(ACK_POLL_SECONDS, remaining))

    evidence = {
        "acknowledged": acknowledged,
        "attempted": True,
        "message_posted": True,
        "dialog_dismissed": acknowledged,
        "terminal": terminal,
        "reason": reason,
        "event": "startup_error_acknowledged" if acknowledged
        else "startup_error_ack_attempted",
        "pid": pid,
        "dialog": {
            "hwnd": hex(match.dialog_hwnd),
            "class_name": ERROR_DIALOG_CLASS,
            "title": ERROR_DIALOG_TITLE,
        },
        "static": {"hwnd": hex(match.static_hwnd), "text": ERROR_STATIC_TEXT},
        "button": {
            "hwnd": hex(match.button_hwnd),
            "class_name": "Button",
            "text": ERROR_BUTTON_TEXT,
            "control_id": ERROR_BUTTON_ID,
        },
        "message": {
            "message": hex(WM_COMMAND),
            "wparam": ERROR_BUTTON_ID,
            "lparam": hex(match.button_hwnd),
        },
        "probe_history": probe_history,
    }
    attempt_directory.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return evidence


def _window_pid(user32: object, hwnd: int) -> int:
    process_id = ctypes.c_ulong()
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id)):
        return 0
    return int(process_id.value)


def _window_text(user32: object, hwnd: int) -> str:
    length = max(0, int(user32.GetWindowTextLengthW(hwnd)))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _class_name(user32: object, hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def _window_present(user32: object, hwnd: int) -> bool:
    is_window = user32.IsWindow
    is_window.argtypes = [ctypes.c_void_p]
    is_window.restype = ctypes.c_bool
    return bool(is_window(hwnd))


def _window_hung(user32: object, hwnd: int) -> bool:
    is_hung = user32.IsHungAppWindow
    is_hung.argtypes = [ctypes.c_void_p]
    is_hung.restype = ctypes.c_bool
    return bool(is_hung(hwnd))


def enumerate_process_windows(pid: int) -> tuple[WindowInfo, ...]:
    """Collect only the requested PID's top-level windows and descendants."""

    if os.name != "nt" or pid <= 0:
        return ()

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    captured: list[WindowInfo] = []

    def collect(hwnd: int, parent_hwnd: int) -> None:
        hwnd_value = int(hwnd)
        captured.append(WindowInfo(
            hwnd=hwnd_value,
            parent_hwnd=int(parent_hwnd),
            pid=pid,
            class_name=_class_name(user32, hwnd_value),
            title=_window_text(user32, hwnd_value),
            control_id=int(user32.GetDlgCtrlID(hwnd_value)),
        ))

    def child_callback(hwnd: int, _lparam: int) -> bool:
        hwnd_value = int(hwnd)
        if _window_pid(user32, hwnd_value) == pid:
            collect(hwnd_value, int(user32.GetParent(hwnd_value) or 0))
        return True

    child_proc = enum_proc_type(child_callback)

    def top_callback(hwnd: int, _lparam: int) -> bool:
        hwnd_value = int(hwnd)
        if _window_pid(user32, hwnd_value) != pid:
            return True
        collect(hwnd_value, 0)
        user32.EnumChildWindows(hwnd_value, child_proc, 0)
        return True

    top_proc = enum_proc_type(top_callback)
    user32.EnumWindows(top_proc, 0)
    return tuple(captured)


def _probe_dialog(pid: int, dialog_hwnd: int) -> str:
    """Classify the exact dialog after one posted acknowledgement.

    Re-enumeration retains the original PID/title/class/static/button match.
    The HWND-only checks distinguish a still-existing but changed window from
    a dialog that really disappeared.
    """

    if os.name != "nt":
        return "gone"
    windows = enumerate_process_windows(pid)
    match = find_startup_error_dialog(windows, pid)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if match is not None and match.dialog_hwnd == dialog_hwnd:
        return "hung" if _window_hung(user32, dialog_hwnd) else "responsive"
    if not _window_present(user32, dialog_hwnd):
        return "gone"
    return "changed"


def _post_message(dialog_hwnd: int, message: int, wparam: int, button_hwnd: int) -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    post = user32.PostMessageW
    post.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    post.restype = ctypes.c_bool
    return bool(post(dialog_hwnd, message, wparam, button_hwnd))


def acknowledge_startup_error(pid: int, attempt_directory: Path) -> dict | None:
    """Find and close the exact known error dialog for ``pid`` once."""

    evidence_path = attempt_directory / "startup-error-ack.json"
    if evidence_path.exists():
        try:
            existing = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (isinstance(existing, dict)
                and (existing.get("acknowledged") is True
                     or existing.get("attempted") is True)):
            return existing
        return None
    windows = enumerate_process_windows(pid)
    return acknowledge_collected_windows(
        pid, windows, attempt_directory, _post_message,
        probe_dialog=_probe_dialog)

