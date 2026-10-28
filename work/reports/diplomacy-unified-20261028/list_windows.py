import ctypes, ctypes.wintypes as W
pid = int(__import__('sys').argv[1])
user32 = ctypes.windll.user32
rows = []
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
def cb(h, l):
    owner = W.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
    if owner.value == pid:
        title = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(h, title, 256)
        cls = ctypes.create_unicode_buffer(128); user32.GetClassNameW(h, cls, 128)
        rows.append({'hwnd': hex(h), 'title': title.value, 'class': cls.value, 'visible': bool(user32.IsWindowVisible(h))})
    return True
user32.EnumWindows(EnumProc(cb), 0)
import json; print(json.dumps(rows, ensure_ascii=False, indent=1))
