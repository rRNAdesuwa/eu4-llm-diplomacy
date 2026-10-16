import ctypes,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/server-vtable-current-reference-owner-20261016-r2/'
OUT=ROOT/'work/reports/server-vtable-current-reference-owner-source-independent-review-20261016-r2'
FILE=4*1024*1024;LIMIT=24*1024*1024;MEM=768*1024*1024
CORE={
 'final-manifest.json':dict(bytes=18539,sha256='a03a4ffe545055783bc9e06cf0e134eb99315f9b8219f32a671d9220f5df3a8d'),
 'prepared-delivery.json':dict(bytes=3654,sha256='7a5953a8fa46029bbd03c1aa64a4b705585a9d3fa121b5058dd20e709692dcc5')}
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
 m=json.loads(read(B+'final-manifest.json',CORE['final-manifest.json']))
 assert len(m['source_pins'])==56 and len(m['decoder_expected_witness_pins'])==38
 for path,want in m['source_pins'].items():read(path,want)
 for n,v in CORE.items():
  if B+n not in files:read(B+n,v)
 value=dict(schema='EU4-R72-R2-INDEPENDENT-RETAINED/1',files=files,source_read_events=events,source_bytes=sum(x['bytes']for x in events),engine_metadata_only=38,own_peak=peak)
 r=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode();assert len(r)<=FILE
 with(OUT/'retained-files.json').open('xb')as f:f.write(r)
 print(json.dumps(dict(retained=pin(r),files=len(files),source_bytes=value['source_bytes'],peak=peak)))
if __name__=='__main__':main()
