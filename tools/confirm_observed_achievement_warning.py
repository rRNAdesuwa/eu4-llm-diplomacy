"""Operator-only confirmation of the observed test-save achievement warning."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--pid", type=int, required=True)
p.add_argument("--hwnd", type=int, required=True)
p.add_argument("--observed-achievement-warning", action="store_true", required=True)
args = p.parse_args()
u = C.WinDLL("user32", use_last_error=True)
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u.PostMessageW.restype = W.BOOL
pid = W.DWORD()
u.GetWindowThreadProcessId(W.HWND(args.hwnd), C.byref(pid))
if pid.value != args.pid or not u.IsWindowVisible(W.HWND(args.hwnd)):
    raise SystemExit("GAME_WINDOW_IDENTITY_DIFFERS")
# Clausewitz consumes WM_CHAR for this C shortcut. SendInput and WM_KEYDOWN
# alone did not activate the observed button in the recorded R70 experiment.
sent = bool(u.PostMessageW(W.HWND(args.hwnd), 0x102, ord("c"), 0x002e0001))
print(json.dumps({"pid": args.pid, "hwnd": args.hwnd, "message": "WM_CHAR",
                  "character": "c", "sent": sent, "load_verified": False}))
if not sent:
    raise SystemExit("SHORTCUT_MESSAGE_NOT_QUEUED")
