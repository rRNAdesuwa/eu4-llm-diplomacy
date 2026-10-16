"""Non-author fixed-file proposal review, without subject/CLI/native execution."""
import ast
import ctypes
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/war-peace-api-lookup-v6-plan-20261016-r1/'
OUT=ROOT/'work/reports/war-peace-api-lookup-v6-plan-independent-review-20261016-r1'
PINS={};RAWS={};READS=[];PEAK=0


class PMC(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t)for n in('pw','w','pp','p','pn','n','pf','ppf','private')]


k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;ps=ctypes.WinDLL('psapi')


def memory():
    global PEAK
    x=PMC();x.cb=ctypes.sizeof(x);assert ps.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(x),x.cb)
    PEAK=max(PEAK,x.pw,x.ppf,x.private);assert PEAK<1024*1024*1024 and PEAK<=768*1024*1024


def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def pair(n,sha):return dict(bytes=n,sha256=sha)
def doc(rel):return json.loads(RAWS[rel])
def csha(value):return hashlib.sha256(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def read(rel,expected):
    memory();p=(ROOT/rel).resolve();assert p.is_relative_to(ROOT)and not p.is_relative_to((ROOT/'work/deps').resolve())
    assert p.suffix.lower()not in('.exe','.dll','.pyd');a=p.stat();assert a.st_size<=4*1024*1024
    assert sum(x['bytes']for x in READS)+a.st_size+1024*1024<8*1024*1024
    raw=p.read_bytes();b=p.stat();READS.append(dict(path=rel,**pin(raw)))
    assert(len(raw),a.st_size,a.st_mtime_ns)==(b.st_size,b.st_size,b.st_mtime_ns)
    assert pin(raw)==expected and(rel not in PINS or PINS[rel]==expected),rel
    PINS[rel]=expected;RAWS[rel]=raw;return json.loads(raw)if rel.endswith('.json')else raw


def pointer(obj,path):
    assert path==''or path.startswith('/')
    for s in path.split('/')[1:]if path else[]:
        s=s.replace('~1','/').replace('~0','~');obj=obj[int(s)]if isinstance(obj,list)else obj[s]
    return obj


def save(name,value):
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    with(OUT/name).open('xb')as f:f.write(raw)
    return pin(raw)


assert not OUT.exists()
manifest=read(BASE+'manifest.json',pair(5938,'47d6c6829378d736f39eda39c0092d01c334ca1b045848b1f793d8b61cb27628'))
assert manifest['sealed']and manifest['author_proposal_only']and manifest['pin_count']==len(manifest['source_pins'])==29
assert not manifest['candidate_built']and not manifest['queries_executed']and not manifest['actual_authorized']
for rel,p in manifest['source_pins'].items():
    read(rel,p)
plan,inventory,refs,old,resources=[doc(BASE+n)for n in('plan.json','source-inventory.json','reference-plan.json','old-entry-preservation.json','resources.json')]
assert pin(RAWS[BASE+'plan.json'])==pair(8375,'2ee490e3ac1c0780666b3edf13e8aef3b959dceabd6aa8419e76ded27e410051')
assert all(x['sealed']for x in(plan,inventory,refs,old,resources))
assert plan['plan_is_not_full_v6_review_or_permission']and plan['old_files_modified']is plan['v6_candidate_created']is False
assert all(v is False for v in plan['authority'].values())
v5='work/candidates/war-peace-api-lookup-1375-v5/'
index,data,source=[doc(v5+n)for n in('index.json','data-manifest.json','source-manifest.json')]
for key,name in(('index_pin','index.json'),('data_manifest_pin','data-manifest.json'),('source_manifest_pin','source-manifest.json'),('wrapper_pin','war_peace_lookup.py'),('engine_pin','query_engine.py')):
    assert plan['baseline'][key]==pin(RAWS[v5+name])
assert len(index['entries'])==59 and len(data['sources'])==74
assert inventory['old74_JSON_source_pins_unchanged']==data['sources']
assert inventory['old_source_bytes_metadata_sum']==sum(q['bytes']for q in data['sources'].values())==2321371
newpins=inventory['new15_accepted_JSON_pins'];assert len(newpins)==15 and not set(newpins)&set(data['sources'])
assert inventory['new15_bytes']==sum(q['bytes']for q in newpins.values())==246472
assert inventory['current_direct_source_count_if_integrated']==89 and inventory['future_count_after_exact5_R80_sources']==94
assert inventory['accepted_engine_source_cap']==96 and inventory['cap_expansion_allowed']is False
assert inventory['old74_bodies_read_or_reaudited_by_this_proposal']is inventory['recursive_closure_claimed']is False
assert len(inventory['future_R80_five_roles'])==5
assert not any('r80-'in r.lower()for r in manifest['source_pins'])
for rel,q in newpins.items():assert PINS[rel]==q
assert refs['reference_count']==len(refs['references'])==len(refs['resolved'])==58 and refs['source_count']==15
used=set();replay=[]
for ref,result in zip(refs['references'],refs['resolved']):
    assert set(ref)=={'path','json_pointer','bytes','sha256'}
    assert {k:ref[k]for k in('bytes','sha256')}==newpins[ref['path']]
    v=pointer(doc(ref['path']),ref['json_pointer'])
    assert result==dict(path=ref['path'],json_pointer=ref['json_pointer'],value_type=type(v).__name__,canonical_value_sha256=csha(v))
    replay.append(result);used.add(ref['path'])
assert used==set(newpins)
gen=next(r for r in index['entries']if r['id']=='peace.generator_divisor_source')
old58=[r for r in index['entries']if r['id']!=gen['id']]
assert len(old58)==58 and old['v5_index_pin']==pin(RAWS[v5+'index.json'])
assert old['old58_canonical_rows']=={r['id']:dict(rva=r['rva'],canonical_sha256=csha(r))for r in old58}
assert old['generator_base_row_canonical_sha256']==csha(gen)and old['generator_base_field_names']==list(gen)
assert old['generator_only_allowed_append_fields']==['later_checked_context','historical_base_scope']
assert old['generator_original_fields_must_equal_v5_except_evidence_append']and old['old_later_conditional_context_unchanged']
scope=plan['planned_scope'];assert scope['append_only_fields']==old['generator_only_allowed_append_fields']
assert [x['report']for x in scope['later_checked_context']]==['R75','R77','R79']
assert scope['planned_final_entry_count']==60 and scope['planned_final_JSON_sources']==94
future=scope['new_entry_after_R80_full_only'];assert future['rva']=='0x97bd30'and future['whole_function_closed']is False and future['complete_prototype']=='unknown'
engine=RAWS[v5+'query_engine.py'];assert pin(engine)==pair(16583,'ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466')
assert len([n for n in ast.walk(ast.parse(engine))if isinstance(n,ast.Constant)and n.value==96])==1
assert plan['engine_wrapper_plan']['engine_file_to_reuse']==v5+'query_engine.py'and plan['engine_wrapper_plan']['copy_or_new_engine_fork_planned']is False
assert plan['future_verification_plan']['first_queries']==['check','catalog','lookup 0x993570','lookup 0x97bd30']
assert plan['future_verification_plan']['execute_now']is False and plan['future_verification_plan']['each_once_only']
b=plan['future_budgets']
assert b['conditional_perpass_bytes']==2321371+246472+1048576+524288+65536==4206243
assert b['conditional_fourquery_plus_controller_upper']==4*b['conditional_perquery_including_two_passes_three_enginepins_and_wrapper_allowance']+8388608==42303084<67108864
assert b['build_plus_seal_bytes']==33554432 and b['first_four_query_batch_bytes']==67108864 and b['not_universal_OS_IO_bound']
assert resources['explicit_read_bytes']==sum(x['bytes']for x in resources['read_events'])==1186480
assert resources['conservative_upper']==1186480+1048576+2097152==4332208<8388608
for event in resources['read_events']:
    assert set(event)=={'phase','path','bytes'} and event['phase']in('before','after')
    assert PINS[event['path']]['bytes']==event['bytes']
for rel,q in dict(PINS).items():read(rel,q)
memory();assert sum(x['bytes']for x in READS)+2097152+701831+131072<8388608
OUT.mkdir()
fp=save('findings.json',dict(schema='ROOT-V6-SOURCE-SCOPE-PROPOSAL-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
    scope='conditional_plan_only_not_v6_source_ready_or_build_query_permission',subject_manifest=PINS[BASE+'manifest.json'],subject_plan=PINS[BASE+'plan.json'],
    checks=dict(flat_pins=30,new15_JSON_sources=15,new_JSON_pointer_refs=58,old58_canonical_hashes_equal=True,
        original_generator_fields_preserved_except_future_append=True,old74_source_pins_equal=True,
        engine16583_ea030_unchanged=True,engine96cap_unchanged=True,planned94sources_within96=True,
        future_R80_five_roles_unresolved=True,no_R80_mutable_files_read=True,old_tests_fixtures_queries_repeated=0),
    required_next='R80 final actual package and complete non-author acceptance, then root explicit bounded v6 build/firstquery scope. This proposal does not authorize that work.',
    precision_notes=['Own R1 failed at an incorrect expectation that author resource events contain SHA. Source/trace and derived701831B read bound are preserved in the sibling r1-failure directory; R2 verifies actual phase/path/bytes against independently hashed filepins. No author program, CLI or test was repeated.',
        'Old74 source values are compared from the accepted pinned data manifest; their74 bodies are not reread or recursively authenticated here.',
        'The59th row will append separate later_checked_context/evidence and historical_base_scope; original v5 and old historical unknown fields remain frozen. Only one new CALL-known machine entry can follow accepted R80 facts.',
        'A kind=function machine entry label grants no callable prototype, wholefunction, units, lifetime, currentprocess or gameplay proof.',
        'Future source/query estimates are conditional; actual file sizes and all referenced source paths/pointers must be frozen and checked before first queries. No parser or engine changes justify new guard fixtures.'],
    independent_resources=dict(explicit_read_bytes=sum(x['bytes']for x in READS),manual_inspection_allowance=1048576,
        retained_reserve=1048576,combined_upper=sum(x['bytes']for x in READS)+2097152+701831+131072,limit=8388608,
        R1_failed_selected_reads_derived_upper=701831,repair_metadata_allowance=131072,
        peak_bytes=PEAK,software_memory_guard=805306368,hard_Job_claimed=False),
    authority={k:False for k in('v6_source_ready','build_authorized','query_authorized','native_ready','callable','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')},
    operations=dict(PE=0,engine_binary=0,decoder=0,author_programs=0,tests=0,queries=0,game=0,native=0)))
mp=save('manifest.json',dict(sealed=True,passed=True,source_pins=PINS,findings=fp,read_journal=READS,
    before_after_equal=True,scope='30 selected flat files including proposal manifest; no recursive closure',actual_authorized=False))
print(json.dumps(dict(findings=fp,manifest=mp,read_bytes=sum(x['bytes']for x in READS),peak_bytes=PEAK),ensure_ascii=True))
