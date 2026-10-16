"""R67 full retained-file review intake; no PE/decoder/author program."""
from pathlib import Path
import hashlib,json,ctypes
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r67-entry-helper-register-contract/'
O='work/reports/war-peace-api-20261016-r67-actual-independent-review/'
OUT=ROOT/O;LIMIT=24*1024*1024;MEMORY=768*1024*1024;peak=0;reads=[];files={}
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb);peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(path,pn):
 assert 'eu4.exe'not in path.lower()and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024 and sum(x['bytes']for x in reads)+a.st_size<LIMIT
 raw=f.read_bytes();z=f.stat();assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns);assert pin(raw)==pn,(path,pin(raw),pn)
 reads.append(dict(path=path,**pn));files[path]=dict(**pn,raw_hex=raw.hex());guard();return raw
def write(n,o):
 raw=(json.dumps(o,indent=2,ensure_ascii=True)+'\n').encode('ascii');assert len(raw)<4*1024*1024
 with(OUT/n).open('xb')as f:f.write(raw)
 return pin(raw)
def main():
 OUT.mkdir(exist_ok=False)
 try:
  m=json.loads(read(B+'manifest.json',dict(bytes=23396,sha256='127d80f4872757fb06dec003fb8746bbbcb649ed456d769db052c4f6d8b18e79')))
  assert len(m['source_pins'])==37 and len(m['decoder_expected_witness_pins'])==38
  for path,pn in m['source_pins'].items():read(path,pn)
  read(B+'filecheck.json',dict(bytes=6210,sha256='14e16d23bcec6393fb1e42abf45d14e63491f2dab92f60636f2a30a4546216e5'))
  d=json.loads(read(B+'actual-delivery-manifest.json',dict(bytes=2700,sha256='8b7f7ee016d032a8ea46e887ec987e04c2d0c4d4cb74643c2a65904138b545b4')))
  for n,pn in d.get('pins',{}).items():
   path=B+n
   if path not in files:read(path,pn)
  rp=write('retained-files.json',dict(schema='EU4-R67-INDEPENDENT-ACTUAL-RETAINED/1',files=files,source_reads=reads,
   source_bytes=sum(x['bytes']for x in reads),prior_schema_inspection_bytes=23396+6922,own_peak_bytes=peak,engine_witness_files_opened=0,recursive_closure=False))
  print(json.dumps(dict(retained=rp,files=len(files),source_bytes=sum(x['bytes']for x in reads),peak=peak)))
  for n in ('selected-evidence.json','capture.json','actual-delivery-manifest.json','filecheck.json'):
   o=json.loads(bytes.fromhex(files[B+n]['raw_hex']));print('KEYS',n,list(o))
   if n in ('actual-delivery-manifest.json','filecheck.json'):print(n,json.dumps(o)[:14500])
  c=json.loads(bytes.fromhex(files[B+'capture.json']['raw_hex']))
  for row in c['analysis']['instructions']:print(row['rva'],row['bytes'],row['mnemonic'],row['operands'])
 except Exception as exc:
  write('retention-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True));raise
if __name__=='__main__':main()
