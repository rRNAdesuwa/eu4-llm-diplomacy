"""R69 source-only intake of exactly three fixed old JSONs; no target/engine."""
from pathlib import Path
import hashlib,json,ctypes
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r69-generator-divisor-source'
LIMIT=16*1024*1024;MEMORY=768*1024*1024;reads=[];files={};peak=0
EXPECTED={
 B+'capture.json':dict(bytes=198722,sha256='53d565996a8b79da7cce445a7ae8576856966eb11bfb3362b924159ada7c27fc'),
 B+'owned-code.json':dict(bytes=1868,sha256='b0ef4b734752e052ff5e86456f68d5e52a6eded74ab808bbc3a722c46ac84c06'),
 B+'selected-evidence.json':dict(bytes=231099,sha256='cd2a38590b2e88d7962451ab961a305888a11d606e10bd847629186ea808101c')}
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb);peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def main():
 OUT.mkdir(exist_ok=False)
 try:
  for path,pn in EXPECTED.items():
   guard();f=ROOT/path;a=f.stat();assert a.st_size==pn['bytes']<=4*1024*1024
   assert sum(x['bytes']for x in reads)+a.st_size<LIMIT
   raw=f.read_bytes();z=f.stat();assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and pin(raw)==pn
   files[path]=dict(**pn,raw_hex=raw.hex());reads.append(dict(path=path,**pn));guard()
  c=json.loads(bytes.fromhex(files[B+'capture.json']['raw_hex']));o=json.loads(bytes.fromhex(files[B+'owned-code.json']['raw_hex']));s=json.loads(bytes.fromhex(files[B+'selected-evidence.json']['raw_hex']))
  print('SELECTED_KEYS',list(s));print('OWNED',json.dumps(o));print('SOURCEPINS',json.dumps(c['source_pins'])[:5000])
  rows=c['analysis']['instructions'];target=0x993570
  indices=[i for i,r in enumerate(rows)if r['mnemonic']=='call'and r['immediates']==[target]]
  print('CALL_INDICES',indices)
  for i in indices:
   for j in range(max(0,i-10),min(len(rows),i+16)):
    r=rows[j];print(j,r['rva'],r['bytes'],r['mnemonic'],r['operands'])
  data=dict(schema='EU4-R69-PREPARE-SELECTED-INPUTS/1',files=files,source_reads=reads,source_bytes=sum(x['bytes']for x in reads),old_JSON_files_read=3,
   entry_target='0x993570',retained_CALL_indices=indices,body_exists_in_selected_owned_window=int(o['window'][0],16)<=target<int(o['window'][1],16),
   inventory_scope='Only these three fixed R62JSONs, not repository/global absence.',own_peak_bytes=peak,PE_stat_open=0,engine_body_stat_open=0,decoder=0,actual=0)
  raw=(json.dumps(data,indent=2)+'\n').encode('ascii');assert len(raw)<4*1024*1024
  with(OUT/'preparation-inputs.json').open('xb')as f:f.write(raw)
  print(json.dumps(dict(preparation_inputs=pin(raw),source_bytes=data['source_bytes'],peak=peak)))
 except Exception as exc:
  raw=(json.dumps(dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,actual=0),indent=2)+'\n').encode('ascii')
  with(OUT/'preparation-input-failure.json').open('xb')as f:f.write(raw)
  raise
if __name__=='__main__':main()
