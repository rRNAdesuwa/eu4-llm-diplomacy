"""Capture one stalled, identified EU4 frame thread and at most 2 KiB stack.

For an observed query timeout only. The exact thread is suspended just long
enough to copy its registers and resumed in finally; no heap walk or dump.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import struct

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pid',type=int,required=True)
p.add_argument('--thread',type=int,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
k=C.WinDLL('kernel32',use_last_error=True)
def bind(name,args,result):
    f=getattr(k,name);f.argtypes=args;f.restype=result;return f
open_thread=bind('OpenThread',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE)
owner=bind('GetProcessIdOfThread',[W.HANDLE],W.DWORD)
close=bind('CloseHandle',[W.HANDLE],W.BOOL)
suspend=bind('SuspendThread',[W.HANDLE],W.DWORD)
resume=bind('ResumeThread',[W.HANDLE],W.DWORD)
get_context=bind('GetThreadContext',[W.HANDLE,C.c_void_p],W.BOOL)
open_process=bind('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE)
read=bind('ReadProcessMemory',[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)],W.BOOL)
enum=bind('K32EnumProcessModulesEx',[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),W.DWORD],W.BOOL)
module_name=bind('K32GetModuleFileNameExW',[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD],W.DWORD)
class ModuleInfo(C.Structure):
    _fields_=[('base',C.c_void_p),('size',W.DWORD),('entry',C.c_void_p)]
module_info=bind('K32GetModuleInformation',[W.HANDLE,W.HMODULE,C.POINTER(ModuleInfo),W.DWORD],W.BOOL)
thread=open_thread(0x4a,False,a.thread)
if not thread:raise C.WinError(C.get_last_error())
try:
    if owner(thread)!=a.pid:raise RuntimeError('THREAD_OWNER_MISMATCH')
    process=open_process(0x410,False,a.pid)
    if not process:raise C.WinError(C.get_last_error())
    try:
        storage=C.create_string_buffer(1232+16)
        pointer=(C.addressof(storage)+15)&~15
        C.c_uint32.from_address(pointer+0x30).value=0x100003
        previous=suspend(thread)
        if previous==0xffffffff:raise C.WinError(C.get_last_error())
        try:
            if not get_context(thread,pointer):raise C.WinError(C.get_last_error())
            body=C.string_at(pointer,1232)
        finally:
            if resume(thread)==0xffffffff:raise C.WinError(C.get_last_error())
        names=('rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15','rip')
        registers=dict(zip(names,struct.unpack_from('<17Q',body,0x78)))
        modules=(W.HMODULE*1024)();needed=W.DWORD()
        if not enum(process,modules,C.sizeof(modules),C.byref(needed),3):raise C.WinError(C.get_last_error())
        if needed.value>C.sizeof(modules):raise RuntimeError('MODULE_LIMIT')
        inventory=[]
        for module in modules[:needed.value//C.sizeof(W.HMODULE)]:
            name=C.create_unicode_buffer(32768);info=ModuleInfo()
            if module_name(process,module,name,len(name)) and module_info(process,module,C.byref(info),C.sizeof(info)):
                inventory.append({'name':name.value,'base':int(info.base),'size':int(info.size)})
        def resolve(address):
            for m in inventory:
                if m['base']<=address<m['base']+m['size']:
                    return {'module':Path(m['name']).name,'rva':hex(address-m['base'])}
            return None
        stack=C.create_string_buffer(2048);copied=C.c_size_t()
        readable=bool(read(process,registers['rsp'],stack,len(stack),C.byref(copied)))
        candidates=[]
        if readable:
            for offset in range(0,copied.value-7,8):
                address=struct.unpack_from('<Q',stack.raw,offset)[0]
                location=resolve(address)
                if location:candidates.append({'offset':offset,**location})
        report={'pid':a.pid,'thread_id':a.thread,'suspend_count_before':previous,
                'thread_resumed':True,'registers':{n:{'value':hex(v),'location':resolve(v)} for n,v in registers.items()},
                'stack_bytes':copied.value if readable else 0,'stack_address_candidates':candidates,
                'note':'Module-address candidates in exactly 2 KiB of the identified thread stack; not an unwound stack.'}
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
        print(json.dumps({'rip':report['registers']['rip'],'candidates':candidates[:30],'output':str(a.output)}))
    finally:close(process)
finally:close(thread)
