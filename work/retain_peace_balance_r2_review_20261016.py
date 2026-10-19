import ctypes,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/peace-balance-field-crosswalk-20261016-r2/'
OUT=ROOT/'work/reports/peace-balance-field-crosswalk-independent-20261016-r2'
FILE=4*1024*1024;LIMIT=12*1024*1024;MEM=768*1024*1024
CORE={
 'manifest.json':dict(bytes=4997,sha256='ef82b930217484064ff25effdc71ba7031c21ee5b78d18f313e52405f210489c'),
 'verification.json':dict(bytes=5299,sha256='961fa099ab956fc1b0a8165884f6d0f67933ae2fd07bd6b5483b3e68fe6c80d6')}
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
peak=0;events=[];files={}
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(path,want=None):
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(x),x.cb)
 peak=max(peak,x.pw,x.ppf,x.private);assert peak<MEM
 assert not path.startswith('work/deps/')and not path.lower().endswith(('.exe','.dll','.pyd','.whl'))
 q=ROOT/path;a=q.stat();assert a.st_size<=FILE and sum(x['bytes']for x in events)+a.st_size<LIMIT
 r=q.read_bytes();z=q.stat();assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)
 if want is not None:assert pin(r)==want
 files[path]=dict(**pin(r),text=r.decode('utf-8'));events.append(dict(path=path,bytes=len(r)));return r
def main():
 OUT.mkdir(exist_ok=False)
 m=json.loads(read(B+'manifest.json',CORE['manifest.json']))
 assert len(m['source_pins'])==5 and len(m['pins'])==11
 for path,want in m['pins'].items():read(path,want)
 read(B+'verification.json',CORE['verification.json']);read(B+'delivery.json')
 value=dict(schema='EU4-BALANCE-R2-INDEPENDENT-RETAINED/1',files=files,source_read_events=events,source_bytes=sum(x['bytes']for x in events),business_source_count=5,own_peak=peak)
 r=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode();assert len(r)<=FILE
 with(OUT/'retained-files.json').open('xb')as f:f.write(r)
 print(json.dumps(dict(retained=pin(r),files=len(files),source_bytes=value['source_bytes'],peak=peak)))
if __name__=='__main__':main()
