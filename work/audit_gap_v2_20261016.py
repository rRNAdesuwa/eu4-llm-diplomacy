"""Independent gap-v2 metadata/reference audit retention; no raw/program replay."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SUBJECT='work/reports/war-peace-result-reader-gaps-20261016-v2/'
OUT=ROOT/'work/reports/war-peace-result-reader-gaps-v2-independent-20261016-r1'
EXPECTED=dict(bytes=8135,sha256='5473038352018d1de3ff358bc0605043ee64cb4d054d991044f9b5f4ab64b77e')
LIMIT=16*1024*1024;MEMORY=768*1024*1024
reads=[dict(path=SUBJECT+'manifest.json',bytes=8135,phase='initial_schema_inspection')]
files={};peak=0
class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage',
        'PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]

def guard():
    global peak
    x=PMC();x.cb=ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
    peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage)
    assert peak<=MEMORY

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path,expected=None):
    assert not path.startswith('work/deps/') and 'eu4.exe' not in path.lower()
    guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024
    assert sum(x['bytes'] for x in reads)+a.st_size<=LIMIT
    raw=f.read_bytes();b=f.stat();assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    pn=pin(raw)
    if expected is not None:assert pn==expected,(path,pn,expected)
    files[path]=dict(**pn,raw_hex=raw.hex());reads.append(dict(path=path,**pn));guard();return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode()
    assert len(raw)<=4*1024*1024
    with (OUT/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def main():
    OUT.mkdir(exist_ok=False)
    write('initial-inspection-note.json',dict(schema='EU4-GAP-V2-AUDIT-INITIAL-NOTE/1',
        exception='FileNotFoundError from guessed gap-ledger.json; manifest correctly identifies gap-ledger-v2.json',
        failed_stat_path=SUBJECT+'gap-ledger.json',failed_read_bytes=0,author_sources_unchanged=True))
    try:
        m=json.loads(read(SUBJECT+'manifest.json',EXPECTED))
        assert len(m['local_pins'])==15 and len(m['captured_source_pins'])==22
        for path,pn in {**m['local_pins'],**m['captured_source_pins']}.items():read(path,pn)
        late={
          'work/reports/war-peace-api-20261016-r64-independent-review/findings.json':dict(bytes=6608,sha256='ea1ebea456742277c663a7d0ae200d4b463a7d34d2774037f5fc30611757778f'),
          'work/reports/war-peace-api-20261016-r64-independent-review/manifest.json':dict(bytes=13709,sha256='750267e0b3f657c1c3cc8e33c3c0d052153f922b71e05e4e1a7639d26b668ef8')}
        for path,pn in late.items():read(path,pn)
        ledger=json.loads(bytes.fromhex(files[SUBJECT+'gap-ledger-v2.json']['raw_hex']))
        print('LEDGER_KEYS',list(ledger))
        for key,value in ledger.items():
            if isinstance(value,list):
                print('LIST',key,len(value))
                if key!='gaps':print(json.dumps(value)[:1800])
            else:print(key,json.dumps(value))
        gaps=ledger.get('gaps',ledger.get('items',[]))
        for row in gaps:print('ROW',json.dumps(row))
        rp=write('retained-metadata.json',dict(schema='EU4-GAP-V2-INDEPENDENT-RETAINED/1',files=files,
            source_reads=reads,source_physical_bytes=sum(x['bytes'] for x in reads),late_annotation_pins=late,
            self_peak=peak,no_raw_code_producer_or_CLI_replay=True))
        print(json.dumps(dict(retained=rp,files=len(files),source_bytes=sum(x['bytes'] for x in reads),self_peak=peak)))
    except Exception as exc:
        write('retention-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,self_peak=peak));raise

if __name__=='__main__':main()
