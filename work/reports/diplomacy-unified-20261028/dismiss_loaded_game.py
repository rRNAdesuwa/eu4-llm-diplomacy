import ctypes, ctypes.wintypes as W, json, sys, time
pid = int(sys.argv[1])
user32 = ctypes.windll.user32; kernel32 = ctypes.windll.kernel32
def windows():
    rows = []
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
    def cb(h, l):
        owner = W.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(h, title, 256)
            cls = ctypes.create_unicode_buffer(128); user32.GetClassNameW(h, cls, 128)
            rows.append({'hwnd': h, 'title': title.value, 'class': cls.value})
        return True
    user32.EnumWindows(EnumProc(cb), 0); return rows
def dialog_ok(hwnd):
    found = []
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
    def cb(h, l):
        text = ctypes.create_unicode_buffer(64); user32.GetWindowTextW(h, text, 64)
        cls = ctypes.create_unicode_buffer(64); user32.GetClassNameW(h, cls, 64)
        if cls.value.lower() == 'button' and text.value.strip() in ('OK', '确定'): found.append(h)
        return True
    user32.EnumChildWindows(hwnd, EnumProc(cb), 0); return found[0] if found else None
def foreground(hwnd):
    fg = user32.GetForegroundWindow(); fg_thread = user32.GetWindowThreadProcessId(fg, None); this = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(this, fg_thread, True); user32.SetForegroundWindow(hwnd); user32.SetFocus(hwnd); user32.AttachThreadInput(this, fg_thread, False)
def click(hwnd, x, y):
    foreground(hwnd); time.sleep(0.15); user32.SetCursorPos(x, y); time.sleep(0.1)
    user32.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06); user32.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.2)
deadline = time.time() + 180; last_click = 0.0; main_hwnd = None
while time.time() < deadline and main_hwnd is None:
    time.sleep(2)
    for row in windows():
        if row['class'] == 'SDL_app' and row['title'] == 'Europa Universalis IV': main_hwnd = row['hwnd']
        elif row['class'] == '#32770':
            ok = dialog_ok(row['hwnd'])
            if ok: user32.SendMessageW(ok, 0x00F5, 0, 0); print(json.dumps({'event':'modal_ok','hwnd':hex(row['hwnd'])}), flush=True)
if not main_hwnd: print(json.dumps({'event':'error','reason':'no SDL window'})); raise SystemExit(2)
print(json.dumps({'event':'window','hwnd':hex(main_hwnd)}), flush=True)
for i in range(60):
    time.sleep(2)
    for row in windows():
        if row['class'] == '#32770':
            ok = dialog_ok(row['hwnd'])
            if ok: user32.SendMessageW(ok, 0x00F5, 0, 0); print(json.dumps({'event':'modal_ok'}), flush=True)
    if time.time() - last_click > 8:
        click(main_hwnd, 1386, 854); time.sleep(1.2); click(main_hwnd, 1274, 1286); time.sleep(1.2); click(main_hwnd, 1386, 854)
        last_click = time.time(); print(json.dumps({'event':'click_round'}), flush=True)
    # stop once campaign ready via demo runtime
    sys.path.insert(0, r'D:/SteamLibrary/steamapps/common/Europa Universalis IV/eu4-llm-diplomacy')
    DEMO = r'D:/SteamLibrary/steamapps/common/Europa Universalis IV/eu4-llm-diplomacy/work/candidates/v32-common-demo-1375'
    BUILD = DEMO + '/build-3'
    sys.path.insert(0, r'D:/SteamLibrary/steamapps/common/Europa Universalis IV/eu4-llm-diplomacy/work/candidates/v32-parameterized-tag-1375')
    sys.path.insert(0, DEMO)
    import importlib
    demo_backend = importlib.import_module('demo_backend'); tag32_backend = importlib.import_module('tag32_backend')
    manifest = tag32_backend.decode(tag32_backend.read(BUILD + '/build.json', 1024*1024)); runtime = demo_backend.DemoRuntime()
    h = kernel32.OpenProcess(0x1000, False, pid)
    ct, et, kt, ut = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
    creation = None
    if h and kernel32.GetProcessTimes(h, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)):
        creation = (ct.dwHighDateTime << 32) | ct.dwLowDateTime
    if h: kernel32.CloseHandle(h)
    if creation:
        try:
            state = runtime.inspect({'pid': pid, 'creation': f'{creation:016x}'}, BUILD, manifest, loaded=False, world=True)
            print(json.dumps({'event':'ready','pid':pid,'creation':f'{creation:016x}','date':state['world']['native_date']}), flush=True)
            break
        except Exception as error:
            pass
else: print(json.dumps({'event':'error','reason':'world not ready'})); raise SystemExit(3)
