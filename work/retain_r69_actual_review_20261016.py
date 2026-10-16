"""R69 actual-package retained intake only; original source designer is disclosed."""
from pathlib import Path
import hashlib,json,ctypes
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1];B='work/reports/war-peace-api-20261016-r69-generator-divisor-source/';O='work/reports/war-peace-api-20261016-r69-actual-independent-review/';OUT=ROOT/O
LIMIT=24*1024*1024;MEMORY=768*1024*1024;reads=[];files={};peak=0
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
def write(n,x):
 r=(json.dumps(x,indent=2,ensure_ascii=True)+'\n').encode('ascii');assert len(r)<4*1024*1024
 with(OUT/n).open('xb')as f:f.write(r)
 return pin(r)
def main():
 OUT.mkdir(exist_ok=False)
 m=json.loads(read(B+'manifest.json',dict(bytes=27579,sha256='3ca9f6aff9c0ceffd0d0096a4ace1a1f7ff294b36acb0f88ed0c3a0f9f9ec69b')))
 assert len(m['source_pins'])==45 and len(m['decoder_expected_witness_pins'])==38
 for path,pn in m['source_pins'].items():read(path,pn)
 final=json.loads(read(B+'actual-delivery-manifest.json',dict(bytes=4048,sha256='f1c11ff522afffd0d3e46af8459fd3eed3ec66f88666f4189d24d665a40da1ef')))
 for key in('source_pins','pins'):
  for path,pn in final.get(key,{}).items():
   full=path if path.startswith('work/')else B+path
   if full not in files:read(full,pn)
 rp=write('retained-files.json',dict(schema='EU4-R69-INDEPENDENT-ACTUAL-RETAINED/1',files=files,source_reads=reads,source_bytes=sum(x['bytes']for x in reads),
  prior_initial_inspection_bytes=27579+7825,own_peak_bytes=peak,no_PE_engine_decoder_author_program_execution=True,recursive_closure=False,
  role='Reviewerpreparedoriginalsource; actualauthorVal and sourcepeerD independent; thisphase onlyactualraw/retainedpackage review.'))
 print(json.dumps(dict(retained=rp,files=len(files),source_bytes=sum(x['bytes']for x in reads),peak=peak)))
 print('FINAL',json.dumps(final))
 c=json.loads(bytes.fromhex(files[B+'capture.json']['raw_hex']))
 print('EDGES',json.dumps(c['analysis']['edges']));print('TERM',json.dumps(c['analysis']['terminals']));print('NEXT',json.dumps(c['next']))
 for row in c['analysis']['instructions']:print(row['rva'],row['bytes'],row['mnemonic'],row['operands'])
 for name in('retained-seal-failure-r1.json','actual-delivery-receipt.json','filecheck.json'):
  path=B+name
  if path in files:print(name,json.dumps(json.loads(bytes.fromhex(files[path]['raw_hex'])))[:18000])
 print('PATHS',json.dumps(list(files)))
if __name__=='__main__':main()
