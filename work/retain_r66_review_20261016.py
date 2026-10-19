"""Bounded independent R66 retained-file reader. No producer/decoder/PE import."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r66-generated-record-postprocess/'
O='work/reports/war-peace-api-20261016-r66-independent-review/'
OUT=ROOT/O
LIMIT=24*1024*1024;MEMORY=768*1024*1024
reads=[];files={};peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
 peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(path,pn=None):
 assert 'eu4.exe' not in path.lower() and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024
 assert sum(x['bytes'] for x in reads)+a.st_size<LIMIT
 raw=f.read_bytes();z=f.stat();assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)
 actual=pin(raw)
 if pn is not None:assert actual==pn,(path,actual,pn)
 reads.append(dict(path=path,**actual));files[path]=dict(**actual,raw_hex=raw.hex());guard();return raw
def write(name,value):
 raw=(json.dumps(value,ensure_ascii=True,indent=2)+'\n').encode('ascii');assert len(raw)<4*1024*1024
 with (OUT/name).open('xb') as f:f.write(raw)
 return pin(raw)
def main():
 OUT.mkdir(exist_ok=False)
 try:
  m=json.loads(read(B+'manifest.json',dict(bytes=15233,sha256='ccf2263abe0d7b538f6b28dcd8df86afb7f50e7a05931c6b48d1a7e7dda7e6a2')))
  assert len(m['source_pins'])==41 and len(m['decoder_expected_witness_pins'])==38
  for path,pn in m['source_pins'].items():read(path,pn)
  additional={B+'file-check.json':dict(bytes=6858,sha256='33b33d35ba7b4dbd7bdb0475c90eef0c3842b8db5f45c1e0d9b1387374b6bf32'),B+'delivery.json':dict(bytes=4656,sha256='d04c3489d98facc2b8f7e1e412b86bab5d5a9519e2c5b62544471db9b345169c')}
  # Explicit root-delivered filename pins: check schema paths in the retained
  # manifest before touching additional names; use declared delivery if present.
  for path,pn in additional.items():
   if path not in files and (ROOT/path).exists():read(path,pn)
  result=write('retained-files.json',dict(schema='EU4-R66-INDEPENDENT-RETAINED/1',files=files,source_reads=reads,
   source_bytes=sum(x['bytes'] for x in reads),initial_schema_read_upper_bytes=2*15233+8319,
   own_peak_bytes=peak,engine_witness_files_opened=0,recursive_closure=False))
  print(json.dumps(dict(retained=result,files=len(files),source_bytes=sum(x['bytes'] for x in reads),peak=peak)))
  print('PATHS',json.dumps(list(files)))
  for name in ['capture.json','owned-code.json','selected-analysis.json','delivery.json','file-check.json','source-manifest.json','run-authorization.json']:
   if B+name in files:
    obj=json.loads(bytes.fromhex(files[B+name]['raw_hex']));print('KEYS',name,list(obj))
  for path,e in files.items():
   if path.startswith(B) and path.endswith('disassembly.txt'):print(bytes.fromhex(e['raw_hex']).decode('ascii'))
 except Exception as exc:
  write('retention-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True));raise
if __name__=='__main__':main()
