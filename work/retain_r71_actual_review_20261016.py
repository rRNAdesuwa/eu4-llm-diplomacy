import ctypes,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r71-actual-independent-review'
FILE=4*1024*1024;LIMIT=24*1024*1024;MEM=768*1024*1024
CORE={
 'actual-manifest.json':dict(bytes=24771,sha256='df5a1d0e3918347ff95d7199b184adefed4a816b2f08dc3dd2bba4576823777f'),
 'actual-verification.json':dict(bytes=22203,sha256='1a2439242e9ee01857076d6897b7d6d1c3a67797058886867b373164c2f251af'),
 'actual-delivery.json':dict(bytes=1724,sha256='81713319f0f893b64c830367746ad0ae24fc7c86cde71ee32a6e31a8f84f3033')}
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
 OUT.mkdir(exist_ok=True);assert not(OUT/'retained-files.json').exists()
 m=json.loads(read(B+'actual-manifest.json',CORE['actual-manifest.json']))
 assert len(m['actual_source_pins'])==40 and len(m['local_output_pins'])==3 and len(m['pins'])==43 and len(m['engine_metadata_witness_pins'])==38
 for path,want in m['pins'].items():read(path,want)
 for n,v in CORE.items():
  if B+n not in files:read(B+n,v)
 value=dict(schema='EU4-R71-INDEPENDENT-ACTUAL-RETAINED/1',files=files,source_read_events=events,source_bytes=sum(x['bytes']for x in events),engine_metadata_only=38,own_peak=peak)
 r=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode();assert len(r)<=FILE
 with(OUT/'retained-files.json').open('xb')as f:f.write(r)
 print(json.dumps(dict(retained=pin(r),files=len(files),source_bytes=value['source_bytes'],peak=peak)))
if __name__=='__main__':main()
