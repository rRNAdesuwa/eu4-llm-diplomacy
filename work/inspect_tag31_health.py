"""Bounded read-only guard diagnostics; never invokes native functions."""
import json
import struct
import sys
import ctypes as C
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.tag_command_backend import WindowsRuntime

def main():
    pid,creation=int(sys.argv[1]),sys.argv[2]
    runtime=WindowsRuntime()
    held=runtime.readonly.Held(dict(pid=pid,creation=creation,session='1'*32,dll_sha256='f'*64,manifest_sha256='e'*64))
    try:
        held.identity_check()
        canonical=held.injector._canonical
        bases=[b for b,p in held.modules() if canonical(p)==canonical(held.injector.GAME)]
        assert len(bases)==1
        base=bases[0]
        reads=0
        def v(address,fmt):
            nonlocal reads
            reads+=1
            assert reads<128
            size=struct.calcsize(fmt)
            assert 0x10000<=address<1<<47 and size<=8
            data=C.create_string_buffer(size); got=C.c_size_t()
            assert held.kernel.ReadProcessMemory(held.handle,C.c_void_p(address),data,size,C.byref(got)) and got.value==size
            return struct.unpack(fmt,data.raw)[0]
        game=v(base+0x233fe78,'<Q'); db=v(base+0x233d8d0,'<Q')
        server=v(game+0x1e00,'<Q'); pause=v(server+0x418,'<Q')
        player=v(game+0x1e60,'<Q'); arr=v(db+0x118,'<Q')
        country=v(arr+((player>>32)&65535)*8,'<Q')
        report=dict(pid=pid,creation=creation,native_calls=0,memory_written=False,
                    date=v(game+0x1dd0,'<i'),count=v(db+0x124,'<i'),capacity=v(db+0x120,'<i'),
                    player=hex(player),country_handle=hex(v(country+0x20,'<Q')),
                    manual_pause=v(pause+0x48,'<B'),reset=v(game+0x7485,'<B'),
                    load_source=v(game+0x74c8,'<B'),ironman=v(game+0x24d0,'<B'),
                    selector=v(game+0x1e66,'<B'),alternate_selector=v(game+0x1e6f,'<B'),
                    native_speed_index=v(game+0x1e08,'<B'),server_gate=v(server+0x19f1,'<B'),
                    game_base=hex(base),server_vtable_rva=hex(v(server,'<Q')-base),
                    country_vtable_rva=hex(v(country,'<Q')-base),country_marker=v(country+8,'<I'),
                    pause_backlink_matches=v(pause+0x50,'<Q')==server)
        held.identity_check()
        out=ROOT/f'work/runtime/tag31-health-{pid}.json'
        with out.open('x') as f:json.dump(report,f,indent=2)
        print(json.dumps(report))
    finally:held.close()
if __name__=='__main__':main()
