"""Injected-reader tests only; never constructs Held against an OS process."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import ctypes as C
import unittest
import readonly as ro
from frozen import BUILD,b
from test_client import bound_status

def header(timestamp=123,size=0x100000):
    d=bytearray(8192);d[:2]=b'MZ';d[60:64]=(128).to_bytes(4,'little');d[128:132]=b'PE\0\0';d[132:134]=(0x8664).to_bytes(2,'little');d[136:140]=timestamp.to_bytes(4,'little');d[152:154]=(0x20b).to_bytes(2,'little');d[208:212]=size.to_bytes(4,'little');return bytes(d)

class ReadOnlyTests(unittest.TestCase):
    def test_header_offsets_and_bad_types(self):
        self.assertEqual(ro.pe_header(header()),dict(machine=0x8664,timestamp=123,size_of_image=0x100000))
        for at,value in [(0,b'NO'),(60,(8192).to_bytes(4,'little')),(128,b'NOPE'),(132,b'\x4c\x01'),(152,b'\x0b\x01')]:
            raw=bytearray(header());raw[at:at+len(value)]=value
            with self.assertRaises(ValueError):ro.pe_header(bytes(raw))
    def test_held_creation_exit_and_path(self):
        h=ro.Held.__new__(ro.Held);h.handle=1;h.identity=bound_status()['identity'];h.injector=SimpleNamespace(GAME=Path('C:/fixed/eu4.exe'),_canonical=lambda p:str(p).replace('\\','/').lower(),_query_process_path=lambda k,p:'C:/fixed/eu4.exe')
        def times(handle,created,exited,kernel,user):created._obj.dwLowDateTime=1;return True
        h.kernel=SimpleNamespace(GetProcessTimes=times,WaitForSingleObject=lambda *_:0x102)
        self.assertEqual(h.identity_check(),'C:/fixed/eu4.exe')
        for creation in ('0000000000000002',True,1.0):
            h.identity['creation']=creation
            with self.assertRaises(ValueError):h.identity_check()
        h.identity['creation']='0000000000000001';h.kernel.WaitForSingleObject=lambda *_:0
        with self.assertRaises(ValueError):h.identity_check()
    def test_module_base_window_and_header_binding(self):
        h=ro.Held.__new__(ro.Held);s=bound_status();h.identity=s['identity'];path='C:/fixed/eu4.exe';dll=str((BUILD/b.DLL).resolve())
        s.update(image_base=0x140000000,installation_module_base=0x7ff800000000,owner_thread=456,installation_process_path=path,manifest_pe=dict(machine=0x8664,timestamp=123,size_of_image=0x100000),installation_load_library=dict(load_library_owner='C:/Windows/System32/kernelbase.dll',load_library_rva='0x1234',load_library_remote_address='0x7ff900001234'))
        h.injector=SimpleNamespace(GAME=Path(path),_canonical=lambda p:str(p).replace('\\','/').lower());h.identity_check=lambda:path
        good_modules=[(s['image_base'],path),(s['installation_module_base'],dll),(0x7ff900000000,'C:/Windows/System32/kernelbase.dll')];h.modules=lambda:good_modules;h.memory=lambda *_:header();h.window_thread=lambda:456
        with patch.object(ro,'disk_identity',return_value=ro.pe_header(header())):
            result=h.check(s,BUILD);self.assertTrue(result['pe_headers_verified']);self.assertFalse(result['whole_loaded_image_hash_verified'])
            for modules in [good_modules[:1],good_modules+[(0x500000000,dll)],[(s['image_base']+65536,path),good_modules[1]],good_modules+[(0x500000000,'C:/fake/eu4_spy_old.dll')]]:
                h.modules=lambda:modules
                with self.assertRaises(ValueError):h.check(s,BUILD)
            h.modules=lambda:good_modules;h.window_thread=lambda:457
            with self.assertRaises(ValueError):h.check(s,BUILD)
            h.window_thread=lambda:456;h.memory=lambda *_:header(timestamp=124)
            with self.assertRaises(ValueError):h.check(s,BUILD)
    def test_read_budget_and_partial_read(self):
        h=ro.Held.__new__(ro.Held);h.handle=1;h.reads=h.bytes=0
        def read(handle,address,buffer,size,actual):C.memset(buffer,0,size);actual._obj.value=size;return True
        h.kernel=SimpleNamespace(ReadProcessMemory=read)
        for _ in range(4):self.assertEqual(len(h.memory(0x10000,8192)),8192)
        with self.assertRaises(ValueError):h.memory(0x10000,1)
        h.reads=h.bytes=0
        def partial(handle,address,buffer,size,actual):actual._obj.value=size-1;return True
        h.kernel.ReadProcessMemory=partial
        with self.assertRaises(ValueError):h.memory(0x10000,64)
        for address,size in [(True,1),(65536.0,1),(65536,True),(65536,8193)]:
            with self.assertRaises(ValueError):h.memory(address,size)

if __name__=='__main__':unittest.main()
