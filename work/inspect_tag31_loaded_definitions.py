"""Read only: bind the live script definition vector without invoking a getter."""
from pathlib import Path
import json
import struct
import sys
import ctypes as C

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.tag_command_backend import WindowsRuntime


def main():
    pid,creation=int(sys.argv[1]),sys.argv[2]
    identity={'pid':pid,'creation':creation,'session':'1'*32,'dll_sha256':'f'*64,'manifest_sha256':'e'*64}
    runtime=WindowsRuntime();held=runtime.readonly.Held(identity)
    try:
        held.identity_check()
        canonical=held.injector._canonical
        matches=[base for base,path in held.modules() if canonical(path)==canonical(held.injector.GAME)]
        assert len(matches)==1;base=matches[0]
        reads=total=0
        def memory(p,n):
            nonlocal reads,total
            assert 0x10000<=p<1<<47 and 0<n<=32768 and p+n<1<<47
            reads+=1;total+=n;assert reads<=8192 and total<=512*1024
            data=C.create_string_buffer(n);got=C.c_size_t()
            assert held.kernel.ReadProcessMemory(held.handle,C.c_void_p(p),data,n,C.byref(got)) and got.value==n
            return data.raw
        def q(p):return struct.unpack('<Q',memory(p,8))[0]
        registry=q(base+0x242bba8)
        before=memory(registry,24);begin,end,capacity=struct.unpack('<QQQ',before)
        assert 0x10000<=begin<=end<=capacity<1<<47 and (capacity-begin)%8==0 and (capacity-begin)//8<=4096
        rows=[]
        for slot in range(begin,end,8):
            p=q(slot);vt=q(p);marker=struct.unpack('<I',memory(p+8,4))[0]
            n,cap=struct.unpack('<QQ',memory(p+0x20,16))
            assert 0<n<=128 and n<=cap and cap<=1048576
            chars=p+0x10 if cap<16 else q(p+0x10)
            raw=memory(chars,n+1);assert raw[-1]==0
            rows.append({'key':raw[:-1].decode('ascii'),'vtable_rva':hex(vt-base),'marker':marker})
        assert memory(registry,24)==before
        held.identity_check()
        cfg=json.loads((ROOT/'bridge/tag_actions_1375_v31.json').read_text())
        requested={x['script_key'] for x in cfg['bindings'] if x.get('script_key')}
        found={x['key'] for x in rows}
        report={'schema':'EU4TAG31-DEFINITIONS/1','pid':pid,'creation':creation,
                'native_calls':0,'memory_written':False,'registry_rva':'0x242bba8',
                'definition_count':len(rows),'definitions':rows,'requested_count':len(requested),
                'missing':sorted(requested-found),'all_types_match':all(x['vtable_rva']=='0x1ce1f70' and x['marker']==0x165 for x in rows)}
        out=ROOT/f'work/runtime/tag31-loaded-definitions-{pid}.json'
        with out.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
        print(json.dumps({k:v for k,v in report.items() if k!='definitions'}))
    finally:held.close()


if __name__=='__main__':main()
