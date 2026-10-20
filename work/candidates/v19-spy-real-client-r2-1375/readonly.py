"""Explicit bounded query/VM_READ guard. Importing never opens a process.
Only the four methods named below are used from the pinned legacy injector;
its old build constant and all loader/remote-thread entrypoints are unused.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import os
from pathlib import Path
from frozen import loader,b,wire,require,same,integer,readonly_injector

def windows():require(os.name=='nt' and C.sizeof(C.c_void_p)==8,'Windows x64 only')
def now_ms():
    windows();k=C.WinDLL('kernel32',use_last_error=True);k.GetTickCount64.restype=C.c_uint64;return int(k.GetTickCount64())

def disk_identity(path):
    path=b.no_links(path);digest=hashlib.sha256();total=0
    with path.open('rb') as f:
        head=f.read(8192);digest.update(head);total+=len(head)
        while True:
            block=f.read(1024*1024)
            if not block:break
            total+=len(block);require(total<=256*1024*1024,'EXE bound');digest.update(block)
    same(digest.hexdigest(),wire.GAME_SHA);return pe_header(head)

def pe_header(data):
    require(type(data)is bytes and len(data)>=64 and data[:2]==b'MZ','PE DOS header')
    nt=int.from_bytes(data[60:64],'little');require(64<=nt<=4096 and nt+264<=len(data),'PE header bound')
    require(data[nt:nt+4]==b'PE\0\0' and int.from_bytes(data[nt+4:nt+6],'little')==0x8664 and int.from_bytes(data[nt+24:nt+26],'little')==0x20b,'PE x64 signature')
    return dict(machine=0x8664,timestamp=int.from_bytes(data[nt+8:nt+12],'little'),size_of_image=int.from_bytes(data[nt+80:nt+84],'little'))

class Held:
    def __init__(self,identity):
        windows();self.identity=wire.identity(identity);self.injector=readonly_injector();self.kernel=self.injector._configure_kernel32();k=self.kernel
        k.GetProcessTimes.argtypes=[W.HANDLE,*([C.POINTER(W.FILETIME)]*4)];k.GetProcessTimes.restype=W.BOOL
        k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)];k.ReadProcessMemory.restype=W.BOOL
        self.handle=k.OpenProcess(0x0400|0x1000|0x0010|0x00100000,False,identity['pid'])
        if not self.handle:raise C.WinError(C.get_last_error())
        self.reads=self.bytes=0
        try:self.identity_check()
        except BaseException:self.close();raise
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None
    def identity_check(self):
        require(self.handle is not None,'Held process closed');k=self.kernel;times=[W.FILETIME() for _ in range(4)]
        require(k.GetProcessTimes(self.handle,*[C.byref(x) for x in times]),'Exact creation unavailable')
        created=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        same(f'{created:016x}',self.identity['creation']);require(not times[1].dwHighDateTime and not times[1].dwLowDateTime,'Exited process')
        require(k.WaitForSingleObject(self.handle,0)==0x102,'Process exited')
        path=self.injector._query_process_path(k,self.handle)
        same(self.injector._canonical(path),self.injector._canonical(self.injector.GAME));return path
    def memory(self,address,size):
        integer(address,0x10000,2**47-1);integer(size,1,8192)
        require(self.reads<16 and self.bytes+size<=32768,'RO header budget');self.reads+=1;self.bytes+=size
        data=C.create_string_buffer(size);actual=C.c_size_t()
        require(self.kernel.ReadProcessMemory(self.handle,C.c_void_p(address),data,size,C.byref(actual)) and actual.value==size,'Read-only PE header unavailable')
        return data.raw
    def modules(self):
        # Exact fixed upper bound; no iterative unbounded list expansion.
        values=(W.HMODULE*512)();needed=W.DWORD()
        require(self.kernel.K32EnumProcessModulesEx(self.handle,values,C.sizeof(values),C.byref(needed),3),'Module enumeration')
        require(0<needed.value<=C.sizeof(values) and needed.value%C.sizeof(W.HMODULE)==0,'Module count bound')
        return [(int(values[i]),self.injector._module_path(self.kernel,self.handle,int(values[i]))) for i in range(needed.value//C.sizeof(W.HMODULE))]
    def window_thread(self):
        user=C.WinDLL('user32',use_last_error=True);callbacktype=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        user.EnumWindows.argtypes=[callbacktype,W.LPARAM];user.EnumWindows.restype=W.BOOL
        user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];user.GetWindowThreadProcessId.restype=W.DWORD
        user.IsWindowVisible.argtypes=[W.HWND];user.IsWindowVisible.restype=W.BOOL
        user.GetWindow.argtypes=[W.HWND,W.UINT];user.GetWindow.restype=W.HWND
        found=set();count=0
        @callbacktype
        def callback(hwnd,_):
            nonlocal count
            count+=1
            if count>2048:return False
            pid=W.DWORD();thread=user.GetWindowThreadProcessId(hwnd,C.byref(pid))
            if pid.value==self.identity['pid'] and user.IsWindowVisible(hwnd) and not user.GetWindow(hwnd,4):found.add(int(thread))
            return True
        require(user.EnumWindows(callback,0) and count<=2048 and len(found)==1 and 0 not in found,'Unique visible unowned window thread')
        return next(iter(found))
    def check(self,status,directory):
        self.reads=self.bytes=0;path=self.identity_check();same(status['identity'],self.identity)
        same(self.injector._canonical(path),self.injector._canonical(status['installation_process_path']))
        game_pe=disk_identity(self.injector.GAME);modules=self.modules();canonical=self.injector._canonical
        game=[base for base,name in modules if canonical(name)==canonical(path)]
        dllpath=str((Path(directory)/b.DLL).resolve());dll=[base for base,name in modules if canonical(name)==canonical(dllpath)]
        require(len(game)==len(dll)==1,'Exact game and research module')
        same([game[0],dll[0]],[status['image_base'],status['installation_module_base']])
        load=status['installation_load_library'];owners=[base for base,name in modules if canonical(name)==canonical(load['load_library_owner'])]
        require(len(owners)==1,'Exact loader system-module owner')
        same(hex(owners[0]+int(load['load_library_rva'],16)),load['load_library_remote_address'])
        research=[name for _,name in modules if Path(name).name.casefold().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_'))]
        require(len(research)==1 and canonical(research[0])==canonical(dllpath),'No other research module')
        same(pe_header(self.memory(game[0],8192)),game_pe)
        same(pe_header(self.memory(dll[0],8192)),{k:status['manifest_pe'][k] for k in ('machine','timestamp','size_of_image')})
        same(self.window_thread(),status['owner_thread']);self.identity_check()
        return dict(held_identity_verified=True,module_paths_bases_verified=True,pe_headers_verified=True,window_thread_verified=True,
                    whole_loaded_image_hash_verified=False,strict_sp_verified=False,world_epoch_verified=False,read_calls=self.reads,read_bytes=self.bytes)
