"""Owned entry copies only: limited guard-order inventory, not runtime safety audit."""
import ast,ctypes,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/runtime-manifest-order-intake-20261016-r1/'
O='work/reports/runtime-entry-manifest-order-review-20261016-r1/'
OUT=ROOT/O;LIMIT=8*1024*1024;FILE=4*1024*1024;reads=[];peak=0
INDEX=dict(bytes=4793,sha256='8ea620fe4cbbec454e21a80c5fa6c8c7835b5f0e57e02f6e70fb456a6823e36f')
COPIES=[
('00__runtime-capability-map-1375-v4.json','docs/runtime-capability-map-1375-v4.json'),
('01__eu4_observer.py','tools/eu4_observer.py'),('02__eu4_observer_manifest_1375.json','bridge/eu4_observer_manifest_1375.json'),
('03__integration_task_observer.py','work/candidates/integration-task-observer-1375-v1/integration_task_observer.py'),
('04__source-manifest.json','work/candidates/integration-task-observer-1375-v1/source-manifest.json'),
('05__linked_truce_projection.py','work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py'),
('06__source-manifest.json','work/candidates/linked-truce-projection-1375-v2/source-manifest.json'),
('07__direct_truce_cache.py','work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py'),
('08__source-manifest.json','work/candidates/direct-truce-cache-cli-1375-v1/source-manifest.json'),
('09__war_peace_lookup.py','work/candidates/war-peace-api-lookup-1375-v4/war_peace_lookup.py'),
('10__data-manifest.json','work/candidates/war-peace-api-lookup-1375-v4/data-manifest.json'),
('11__support_heir_current_observer.py','work/candidates/support-heir-current-observer-1375-v1/support_heir_current_observer.py'),
('12__source-manifest.json','work/candidates/support-heir-current-observer-1375-v1/source-manifest.json'),
('13__peace_current_pending.py','work/candidates/peace-current-pending-observer-1375-v1/peace_current_pending.py'),
('14__source-manifest.json','work/candidates/peace-current-pending-observer-1375-v1/source-manifest.json')]
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.pw,c.ppf,c.private);assert peak<768*1024*1024
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def pairs(v):
 d={}
 for a,b in v:
  if a in d:raise ValueError('duplicate_key')
  d[a]=b
 return d
def decode(r):return json.loads(r.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
def read(path,q=None):
 guard();assert path.startswith(B)or path.startswith(O)or path=='work/review_runtime_manifest_order_20261016.py'
 f=ROOT/path;a=f.stat();assert a.st_size<=FILE;r=f.read_bytes();z=f.stat()
 assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and len(r)==a.st_size
 if q:assert pin(r)==q,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(name,obj):
 r=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(OUT/name).open('xb')as f:f.write(r)
 return pin(r)
def main():
 OUT.mkdir(exist_ok=False);index=decode(read(B+'index.json',INDEX));files={};original={};provenance=[]
 assert index['sealed']and index['before_after_equal']and len(index['pins'])==15 and len(index['entries'])==7
 assert set(index['pins'])=={x[1]for x in COPIES}
 for copy,orig in COPIES:
  r=read(B+copy,index['pins'][orig]);files[B+copy]=dict(**pin(r),text=r.decode('utf-8'));original[orig]=r
  provenance.append(dict(owned_path=B+copy,original_path_not_opened=orig,original_pin_from_root_index=index['pins'][orig],owned_pin=pin(r)))
 assert sum(x['bytes']for x in index['pins'].values())*2==index['selected_read_bytes']==335150
 assert all(x['entry']in original and x['manifest']in original for x in index['entries'])
 records=[];excerpts={}
 for entry in index['entries']:
  orig=entry['entry'];raw=original[orig];text=raw.decode('utf-8');tree=ast.parse(text)
  functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
  classes={n.name:n for n in tree.body if isinstance(n,ast.ClassDef)}
  def function(name):return ast.unparse(functions[name])
  def record_function(name):
   n=functions[name];return dict(function=name,line=n.lineno,end_line=n.end_lineno,source=ast.get_source_segment(text,n))
  r=dict(id=entry['id'],entry=orig,entry_copy_pin=pin(raw),manifest=entry['manifest'],manifest_copy_pin=pin(original[entry['manifest']]),
   scope='Entry definitions only; external launcher and unopened imported base behavior unknown',
   original_entry_opened=False,entry_or_guard_executed=False,runtime_safety_judgment='not_assessed',history_or_effect_invalidation=False,tool_blocked=False)
  if 'verify_sources'in functions:
   v=functions['verify_sources'];vt=function('verify_sources');sig=ast.unparse(v.args)
   assert 'expected_manifest_pin'not in sig and 'json_file('in vt and vt.index('json_file(')<vt.index(".get('source_pins')")
   assert 'manifest=pin('in vt and "json.loads(read("in function('json_file')and 'read('in function('pin')
   # Exact-source compile checks the very byte buffer later compiled; no imported code runs here.
   ex=function('exact_compile');assert ex.index('read(')<ex.index('== expected')<ex.index('exec(compile(')
   cl=ast.unparse(classes['Libraries']);ob=function('observe');run=function('run')
   assert 'verify_sources() == self.initial'in cl and 'libraries.guard()'in ob
   assert ob.index('normal_context_exit')<ob.rindex('libraries.guard()')<ob.rindex('commit_after_context_exit')
   r.update(manifest_parsed_before_entry_local_authorized_pin=True,entry_local_expected_manifest_pin_before_parse=False,
    returned_manifest_pin_source='pin(path/MANIFEST) reopens after json_file parsed a separate read buffer',same_parsed_raw_buffer_used_for_returned_manifest_pin=False,
    fixed_source_roots_present=True,selected_import_mechanism='exact_compile: bounded raw read; equality of bytes/SHA to selected source pin; compile that same raw; exec into named ModuleType',
    imported_base_internals='not opened; only visible calls to delegated guard/load functions are inventoried',
    graph_initial_and_later_comparisons='Libraries saves initial graph; guard re-runs verify_sources and compares full result; observer construction and observation postconditions call guard; file commands also call guard',
    guard_lines=dict(verify=[v.lineno,v.end_lineno],exact_compile=[functions['exact_compile'].lineno,functions['exact_compile'].end_lineno],libraries=[classes['Libraries'].lineno,classes['Libraries'].end_lineno],observe=[functions['observe'].lineno,functions['observe'].end_lineno],run=[functions['run'].lineno,functions['run'].end_lineno]),
    optional_future_hardening='New revision could receive an independently authorized manifest pin, verify one raw buffer before JSON parse/source selection, and derive returned manifest pin from that same buffer; preserve existing fixed roots, exact_compile and full graph comparisons.')
   if entry['id']=='directional_truce_cache':
    assert 'self.initial = verify_sources()'in cl and 'exact_compile(HOST' in cl and 'exact_compile(R24'in cl
    r['specific_order']='Libraries constructor verifies graph before exact-compiling HOST/R24; delegates frozen host closure. observer calls host.load_local; that implementation is unopened.'
   else:
    assert "initial = verify_sources(runtime=operation == 'status')"in run and 'exact_compile(DIRECT'in cl
    r['specific_order']='run verifies graph/runtime metadata before constructing Libraries; Libraries exact-compiles DIRECT and calls its Libraries constructor. observer rechecks runtime graph before delegated observer creation.'
   if entry['id']=='peace_current_pending_queue_pending_active_world':
    assert 'source_graph_sha256'in vt and "('independent_source_review', 'production_review')"in vt
    r['additional_visible_graph_gate']='graph_digest(expected), design-owner linkage, review exact CLI/source-graph subjects and current-readonly production boolean; these do not replace a pre-parse expected manifest byte pin.'
   excerpts[orig]=[record_function(n)for n in('json_file','pin','verify_sources','exact_compile','run')]+[dict(function='Libraries',line=classes['Libraries'].lineno,end_line=classes['Libraries'].end_lineno,source=ast.get_source_segment(text,classes['Libraries']))]
  elif entry['id']=='original_effects_and_current_relations_wars':
   v=function('source_pins');assert v.index('from bridge.tag_command_backend')<v.index('raw = read(MANIFEST')<v.index('data = decode(raw)')<v.index("data['source_pins'].items()")
   assert 'dict(bytes=len(raw), sha256=digest(raw))'in v and 'source_pins()'in function('main')
   r.update(manifest_parsed_before_entry_local_authorized_pin=True,entry_local_expected_manifest_pin_before_parse=False,
    returned_manifest_pin_source='bytes/SHA of same local raw variable already parsed',same_parsed_raw_buffer_used_for_returned_manifest_pin=True,
    selected_import_mechanism='ordinary imports of backend and runtime_source_pins occur inside source_pins before own manifest read; normal later specialist/service imports; no entry exact_compile',
    graph_initial_and_later_comparisons='main calls source_pins once; entry does not save/compare a later graph. runtime_source_pins/specialist/service internals and outer launcher are unopened unknown.',
    guard_lines=dict(source_pins=[functions['source_pins'].lineno,functions['source_pins'].end_lineno],main=[functions['main'].lineno,functions['main'].end_lineno]),
    optional_future_hardening='A separately reviewed wrapper/entry revision could bind its manifest and selected import buffers before import; no determination about delegated current guards is made.')
   excerpts[orig]=[record_function('source_pins'),record_function('main')]
  else:
   assert entry['id']=='war_peace_static_contract_lookup_v4'
   assignments={t.id:node.value for node in tree.body if isinstance(node,ast.Assign)for t in node.targets if isinstance(t,ast.Name)}
   data_sha=ast.literal_eval(assignments['DATA_SHA']);base_sha=ast.literal_eval(assignments['BASE_SHA'])
   assert data_sha==pin(original[entry['manifest']])['sha256']and base_sha=='d4237d98c58e89be9419ff736f01d97f5fde0129c07c5c7f778baf010071746e'
   en=function('engine');run=function('run');assert en.index('raw = base_bytes()')<en.index('exec(compile(raw')<en.rindex('base_bytes()')
   assert 'module.SourceGraph(ROOT, HERE, DATA_SHA)'in run and run.index('module.query(')<run.index('base_bytes()',run.index('module.query('))
   r.update(entry_local_expected_manifest_pin_before_parse='not locally parsed; DATA_SHA constant passed to unopened SourceGraph',
    manifest_parsed_before_entry_local_authorized_pin='unknown inside unopened base',returned_manifest_pin_source='delegated result; no local manifest JSON parse or returned manifest pin',same_parsed_raw_buffer_used_for_returned_manifest_pin='unknown inside unopened base',
    selected_import_mechanism='base_bytes bounded read and hardcoded BASE_SHA check; compile/exec the same returned raw; base_bytes recheck after exec and after query',
    graph_initial_and_later_comparisons='SourceGraph receives fixed DATA_SHA and module.query(graph,...); internal graph pin/order/reload behavior not opened in this scope',
    guard_lines={n:[functions[n].lineno,functions[n].end_lineno]for n in('base_bytes','engine','run')},
    optional_future_hardening='No entry-layer manifest change proposed from this scope. Any future guard-order conclusion requires explicit review of pinned SourceGraph base implementation.',
    data_sha_matches_owned_manifest=True,base_engine_source_not_opened=True)
   excerpts[orig]=[record_function(n)for n in('base_bytes','engine','run')]
  records.append(r)
 # All before/after checks are of root-owned copies, never original entry or dependencies.
 for copy,orig in COPIES:read(B+copy,index['pins'][orig])
 read(B+'index.json',INDEX)
 ep=write('entry-excerpts.json',dict(sealed=True,original_paths_are_provenance_only=True,entry_function_excerpts=excerpts))
 sp=write('guard-order-inventory.json',dict(sealed=True,entries=records,provenance=provenance,imported_base_and_external_launcher='unknown unless explicitly visible in these seven entry copies',
  classifications=dict(five_verify_sources=parse_order_summary(records),public_same_buffer_manifest_pin=True,lookup_fixed_DATA_SHA_delegated_base_unknown=True)))
 manual_allowance=1048576;reserve=2097152;upper=sum(x['bytes']for x in reads)+manual_allowance+reserve;assert upper<LIMIT
 findings=dict(schema='EU4-RUNTIME-ENTRY-MANIFEST-ORDER-INDEPENDENT-INVENTORY/1',sealed=True,passed=True,blocking_findings=[],
  scope='Limited owned-copy entry guard-order inventory; not runtime acceptance, exploitability or complete safety audit',
  reviewer_role='Root authored owned-copy intake. Reviewer performed source-peer/retained reviews of some historical tools (including direct/linked/lookup/support-related evidence); this inventory does not rerun or broaden those reviews.',
  subject_intake_index=INDEX,seven_entries=7,fifteen_owned_copies=15,original_paths_not_opened=True,root_original_prepost_335150_bytes_is_witness=True,
  guard_order_inventory=sp,entry_excerpts=ep,summary=dict(five_entries_parse_before_local_expected_manifest_pin=True,five_return_manifest_pin_from_later_read=True,
   public_uses_same_raw_for_returned_manifest_pin_but_no_preparse_expectedpin=True,lookup_hardpins_base_source_and_passes_fixed_DATA_SHA_but_base_internals_unknown=True),
  precision_notes=[
   'All owned copies match the original-path pins in root index; reviewer does not reopen original files. Root original before/after equality is retained intake witness, not new original-file authentication.',
   'Five verify_sources entries parse manifest-derived pins before any local pre-authorized expected manifest byte pin and later call pin() on the manifest path again. Fixed source roots, pin-shape/size constraints, selected review gates and repeated full returned-graph equality are also present.',
   'Exact_compile in those five entries checks the specific raw bytes before compiling/executing that same buffer. This fact does not certify transitive imports or the unopened delegated host/base implementation.',
   'Public source_pins derives its returned manifest pin from the same raw buffer it parsed; it imports backend/runtime helper modules before reading its own manifest. No entry-local later graph compare is visible, but delegated internals remain unknown.',
   'Lookup wrapper binds frozen Python base source SHA and passes fixed DATA_SHA to SourceGraph. The copied wrapper does not show SourceGraph parsing/graph logic; no claim is made about its guard order.',
   'Observed order is a candidate for future versioned source-guard hardening. It does not establish a malicious input/runtime event, historical failed acceptance, invalid effect evidence, current tool blocked state, ABA exclusion, or authority to repair/run frozen tools.'],
  resources=dict(explicit_owned_file_reads=sum(x['bytes']for x in reads),manual_prior_inspection_allowance=manual_allowance,sealing_check_reserve=reserve,complete_stage_upper=upper,limit=LIMIT,own_peak_bytes=peak,complete_OS_IO_claimed=False),
  operations=dict(original_entry_manifest_open=0,recursive_source_closure=0,author_programs=0,tests=0,PE=0,engine=0,decoder=0,runtime=0,game=0,native=0,repairs=0),
  authority={k:False for k in('runtime_accepted','tool_blocked','history_invalidated','effect_invalidated','source_fix_authorized','tests_authorized','actual_authorized','reader_adoption_allowed','native_ready','world_lease','atomic_snapshot')},all_shells_collected=True)
 fp=write('findings.json',findings)
 sourcepin=pin(read('work/review_runtime_manifest_order_20261016.py'))
 mp=write('manifest.json',dict(sealed=True,passed=True,subject_intake_index=INDEX,source_pins={B+'index.json':INDEX,**{B+copy:index['pins'][orig]for copy,orig in COPIES},
  O+'findings.json':fp,O+'guard-order-inventory.json':sp,O+'entry-excerpts.json':ep,'work/review_runtime_manifest_order_20261016.py':sourcepin},actual_authorized=False))
 print(json.dumps(dict(passed=True,findings=fp,manifest=mp,inventory=sp,excerpts=ep,upper=upper,peak_bytes=peak)))
def parse_order_summary(records):return [r['id']for r in records if r.get('same_parsed_raw_buffer_used_for_returned_manifest_pin')is False]
def check():
 m=decode(read(O+'manifest.json'))
 for path,q in m['source_pins'].items():read(path,q)
 r=dict(sealed=True,passed=True,pins=len(m['source_pins']),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak,original_files_opened=0,program_tests_PE_engine_runtime=0,all_shells_collected=True)
 z=write('verification.json',r);print(json.dumps(dict(passed=True,verification=z,pins=len(m['source_pins']),read_bytes=r['read_bytes'],peak_bytes=peak)))
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--review']:main()
  elif sys.argv[1:]==['--check']:check()
  else:raise ValueError('own review/check only')
 except BaseException as e:
  if OUT.exists()and not(OUT/'own-failure-r1.json').exists():write('own-failure-r1.json',dict(error=type(e).__name__,message=str(e),reads=reads,peak_bytes=peak))
  raise
