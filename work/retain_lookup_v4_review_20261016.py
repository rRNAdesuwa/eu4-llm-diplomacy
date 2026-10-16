import ctypes,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/candidates/war-peace-api-lookup-1375-v4/'
O=ROOT/'work/reports/war-peace-api-lookup-v4-independent-review-20261016-r1'
LIMIT=24*1024*1024;FILE=4*1024*1024;MEM=768*1024*1024
CORE={
 B+'author-manifest.json':(21442,'206aa754093e3b5c51810473cb04e5fb3461528ea3ecd6cc68841c8850deebfc'),
 B+'verification.json':(44605,'a20a2c3d36e7a394772158a2b0ee39040ebfd2721abf0fede9b16783d474cab2'),
 B+'delivery.json':(1091,'7cd7b0cd1697046f8cfec6eebc346a6c4a299dd02e6c8cf1164dd990a4a6c830')}
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.GetCurrentProcess.restype=ctypes.c_void_p
ps=ctypes.WinDLL('psapi',use_last_error=True);peak=0
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert ps.GetProcessMemoryInfo(ctypes.c_void_p(kernel.GetCurrentProcess()),ctypes.byref(x),x.cb)
 peak=max(peak,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<MEM
def pairs(v):
 d={}
 for k,x in v:
  if k in d:raise ValueError('duplicate key')
  d[k]=x
 return d
def decode(r):return json.loads(r.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in()).throw(ValueError(v)))
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
files={};reads=[]
def read(path,p):
 guard();q=ROOT/path;size=q.stat().st_size;assert size<=FILE and sum(x['bytes']for x in reads)+size<LIMIT
 r=q.read_bytes();assert pin(r)==p;reads.append(dict(path=path,bytes=len(r)))
 files[path]=dict(**p,text=r.decode('utf-8'));return r
def main():
 O.mkdir(exist_ok=False)
 m=decode(read(B+'author-manifest.json',dict(zip(('bytes','sha256'),CORE[B+'author-manifest.json']))))
 assert len(m['local_and_selected_source_pins'])==106
 for path,p in m['local_and_selected_source_pins'].items():
  assert not path.lower().endswith(('.exe','.dll','.pyd','.whl')) and 'capstone'not in path.lower()
  read(path,p)
 for path,v in CORE.items():
  if path not in files:read(path,dict(zip(('bytes','sha256'),v)))
 value=dict(schema='EU4-LOOKUP-V4-REVIEW-RETAINED/1',files=files,read_events=reads,source_bytes=sum(x['bytes']for x in reads),own_peak_bytes=peak,manual_inspection_allowance=1024*1024)
 raw=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8');assert len(raw)<FILE
 with(O/'retained-files.json').open('xb')as f:f.write(raw)
 print(json.dumps(dict(cache=pin(raw),files=len(files),source_bytes=value['source_bytes'],peak=peak)))
if __name__=='__main__':main()
