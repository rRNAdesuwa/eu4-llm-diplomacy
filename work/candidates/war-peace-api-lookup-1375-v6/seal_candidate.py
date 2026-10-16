"""Retained-only v6 final author sealing, not independent acceptance."""
import ctypes,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v6-first-queries-20261016-r1'
reads=[];peak=0;LIMIT=16*1024**2;FILE=4*1024**2
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t)for n in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi')
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.private,c.ppf);assert peak<1024**3 and peak<=768*1024**2
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(path):
 guard();assert path.resolve().is_relative_to(ROOT.resolve());size=path.stat().st_size;assert size<=FILE and sum(x['bytes']for x in reads)+size<=LIMIT
 raw=path.read_bytes();assert len(raw)==size;reads.append(dict(path=path.relative_to(ROOT).as_posix(),**pin(raw)));return raw
def write(n,d):
 raw=(json.dumps(d,ensure_ascii=True,indent=2,sort_keys=True)+'\n').encode();assert len(raw)<=FILE
 with(HERE/n).open('xb')as f:f.write(raw)
 return pin(raw)
def main():
 assert len(sys.argv)==3;expected=dict(bytes=int(sys.argv[1]),sha256=sys.argv[2])
 write('seal-claim.json',dict(schema='EU4-LOOKUP-V6-SEAL-CLAIM/1',source_manifest=expected,no_repeated_query=True))
 raw=read(HERE/'source-manifest.json');assert pin(raw)==expected;m=json.loads(raw)
 pins=dict(m['files']);pins['work/candidates/war-peace-api-lookup-1375-v6/source-manifest.json']=expected
 for n,q in pins.items():assert pin(read(ROOT/n))==q
 receipt_raw=read(REPORT/'receipt.json');receipt=json.loads(receipt_raw)
 assert receipt['passed']and receipt['error']is None and receipt['command_count']==4 and receipt['first_only_no_retries']and receipt['all_jobs_and_direct_children_collected']
 for n in ['claim.json','receipt.json',*[f'{i:02d}.{suffix}'for i in range(4)for suffix in('stdout.json','stderr.txt')]]:
  path=REPORT/n;pins[path.relative_to(ROOT).as_posix()]=pin(read(path))
 for n in ['build-receipt.json','source-manifest.json','seal-claim.json']:
  path=HERE/n;pins[path.relative_to(ROOT).as_posix()]=pin(read(path))
 for n,q in pins.items():assert pin(read(ROOT/n))==q
 own_measured=sum(x['bytes']for x in reads)
 author=dict(schema='EU4-LOOKUP-V6-AUTHOR-MANIFEST/1',sealed=True,status='author_final_pending_non_author_full_review',files=pins,file_count=len(pins),source_manifest=expected,
  first_query_receipt=dict(path=(REPORT/'receipt.json').relative_to(ROOT).as_posix(),**pin(receipt_raw)),selected_JSON_sources=94,entry_count=60,
  source_pins_before_after_equal=True,query_calls=4,no_retry=True,independent_review_passed=False,native_ready=False,authority=m['authority'],
  resource_scope='flat explicit owned-source reads; not OS/loader IO or native decoder work',seal_read_journal=reads,seal_completed_bytes=own_measured,seal_budget_bytes=LIMIT,self_peak_bytes=peak)
 ap=write('author-manifest.json',author)
 pubpins={'work/candidates/war-peace-api-lookup-1375-v6/author-manifest.json':ap,**{n:q for n,q in pins.items()if n.startswith('work/candidates/war-peace-api-lookup-1375-v6/')or n.startswith('work/reports/war-peace-api-lookup-v6-first-queries-')}}
 pp=write('publication-manifest.json',dict(schema='EU4-LOOKUP-V6-PUBLICATION-MANIFEST/1',sealed=True,status='research_candidate_not_published',files=pubpins,file_count=len(pubpins),full_author_manifest=ap,independent_review_passed=False,authority=m['authority']))
 upper=own_measured+2*1024**2
 write('delivery.json',dict(schema='EU4-LOOKUP-V6-AUTHOR-DELIVERY/1',sealed=True,source_manifest=expected,author_manifest=ap,publication_manifest=pp,first_query_receipt=pin(receipt_raw),
  source_schema_keys=list(m),author_schema_keys=list(author),publication_schema='files flat map, no recursive source expansion',selected_JSON_sources=94,entry_count=60,
  seal_completed_read_bytes=own_measured,remaining_delivery_check_reserve_bytes=2*1024**2,seal_successful_upper_bytes=upper,seal_limit=LIMIT,
  build_seal_budget=32*1024**2,query_batch_completed_bytes=receipt['combined_physical_explicit_bytes'],query_limit=64*1024**2,all_shells_collected=True,author_not_independent=True,authority=m['authority']))
 assert upper<=LIMIT
 print(json.dumps(dict(status='sealed_author_pending_review',author_manifest=ap,publication_manifest=pp,seal_completed_bytes=own_measured,self_peak_bytes=peak,all_shells_collected=True)))
if __name__=='__main__':main()
