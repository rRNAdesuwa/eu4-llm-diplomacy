import ctypes,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/server-vtable-current-reference-owner-20261016-r1/'
OUT=ROOT/'work/reports/server-vtable-current-reference-owner-source-independent-review-20261016-r1'
FILE=4*1024*1024;LIMIT=24*1024*1024;MEM=768*1024*1024
FINAL=dict(bytes=11870,sha256='d6d3b83ef89a5d07998a320ffbf27b8e4abc12a73827d0b73c9efbc391a0eefe')
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
peak=0;events=[];files={}
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(path,want):
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(x),x.cb)
 peak=max(peak,x.pw,x.ppf,x.private);assert peak<MEM
 assert not path.startswith('work/deps/')and not path.lower().endswith(('.exe','.dll','.pyd','.whl'))
 q=ROOT/path;a=q.stat();assert a.st_size<=FILE and sum(x['bytes']for x in events)+a.st_size<LIMIT
 r=q.read_bytes();z=q.stat();assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and pin(r)==want
 files[path]=dict(**pin(r),text=r.decode('utf-8'));events.append(dict(path=path,bytes=len(r)));return r
def main():
 OUT.mkdir(exist_ok=False)
 final=json.loads(read(B+'final-manifest.json',FINAL))
 for path,want in final['source_pins'].items():read(path,want)
 assert len(final['source_pins'])==26 and len(final['decoder_expected_witness_pins'])==38
 value=dict(schema='EU4-R72-REVIEW-R1-RETAINED/1',files=files,source_read_events=events,source_bytes=sum(x['bytes']for x in events),engine_metadata_only=38,own_peak=peak)
 r=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode();assert len(r)<=FILE
 with(OUT/'retained-files-r1.json').open('xb')as f:f.write(r)
 print(json.dumps(dict(retained=pin(r),files=len(files),source_bytes=value['source_bytes'],peak=peak)))
if __name__=='__main__':main()
