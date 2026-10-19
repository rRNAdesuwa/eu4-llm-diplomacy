"""R70 raw DATA-seed intake only; never runs scanner/tests/producer."""
from pathlib import Path
import hashlib,json,ctypes
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1];B='work/reports/server-vtable-rip-reference-seeds-20261016-r1/';O='work/reports/server-vtable-rip-entry-independent-review-20261016-r1/';OUT=ROOT/O
LIMIT=16*1024*1024;MEMORY=768*1024*1024;reads=[];files={};peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb);peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(path,pn):
 assert 'eu4.exe'not in path.lower()and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024 and sum(x['bytes']for x in reads)+a.st_size<LIMIT
 r=f.read_bytes();z=f.stat();assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and pin(r)==pn,(path,pin(r),pn)
 reads.append(dict(path=path,**pn));files[path]=dict(**pn,raw_hex=r.hex());guard();return r
def write(n,o):
 r=(json.dumps(o,indent=2,ensure_ascii=True)+'\n').encode('ascii');assert len(r)<4*1024*1024
 with(OUT/n).open('xb')as f:f.write(r)
 return pin(r)
def main():
 OUT.mkdir(exist_ok=False)
 m=json.loads(read(B+'source-manifest.json',dict(bytes=3108,sha256='d26b5aad451b7b54e35aac84b5b7eb69f76268668131d2c2a49b8d42fc8b8963')))
 final=json.loads(read(B+'final-manifest.json',dict(bytes=4739,sha256='ab07eb62a6bac7bdc19d600911decdd78306852702febd96bb0752b74807bf7b')))
 assert len(m['source_pins'])==14 and len(final['source_pins'])==23
 for path,pn in final['source_pins'].items():
  if path not in files:read(path,pn)
 rp=write('retained-files.json',dict(schema='EU4-R70-INDEPENDENT-ENTRY-RETAINED/1',files=files,source_reads=reads,source_bytes=sum(x['bytes']for x in reads),
  prior_initial_inspection_bytes=3108+2792+4739,own_peak_bytes=peak,no_PE_engine_decoder_scanner_producer_tests=True,recursive_closure=False))
 print(json.dumps(dict(retained=rp,files=len(files),source_bytes=sum(x['bytes']for x in reads),peak=peak)))
 for path in ['work/reports/server-vtable-rtti-20261016-r1/capture.json','work/reports/server-vtable-rtti-20261016-r1/data-contract.json','work/reports/server-vtable-rtti-data-independent-review-20261016-r1/findings.json',B+'budget.json',B+'source-preparation-receipt.json']:
  obj=json.loads(bytes.fromhex(files[path]['raw_hex']));print('FILE',path,'KEYS',list(obj));print(json.dumps(obj)[:15500])
 print('PROTOCOL',bytes.fromhex(files[B+'PROTOCOL.md']['raw_hex']).decode('ascii'))
if __name__=='__main__':main()
