"""Independent source/retained-VM-byte review; never loads JS/Frida/game/host."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import types

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/frida-owned-body-probe-1375-v1'
R18=ROOT/'work/reports/war-peace-api-20261015-r18-body-probe-contract/war'
FFI=ROOT/'work/reports/rea-frida-owned-ffi-live-review-20261015'
OUT=ROOT/'work/reports/frida-owned-body-component-review-20261015-r1'


def pin(path):
    count=0;sha=hashlib.sha256()
    with path.open('rb') as stream:
        while raw:=stream.read(65536):count+=len(raw);sha.update(raw)
    return {'bytes':count,'sha256':sha.hexdigest()}


def load(path):
    assert path.stat().st_size<=1024*1024
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


def check():
    m=load(OUT/'manifest.json');assert m['sealed'] is True
    for name,wanted in m['source_pins'].items():assert pin(ROOT/name)==wanted,name
    for name,wanted in m['selected_runtime_pins'].items():assert pin(Path(name))==wanted,name
    print(json.dumps({'status':'pass','local_pins':len(m['source_pins']),'runtime_pins':len(m['selected_runtime_pins']),
        'game_accessed':False,'Frida_loaded':False,'suite_reexecuted':False}))


def main():
    manifest_path=HERE/'source-manifest.json'
    assert pin(manifest_path)=={'bytes':3118,'sha256':'941c5a281151f1d47579c39514b89ba06dee4f0ce4faa08f2107ec7efff818f9'}
    assert pin(HERE/'body_probe.js')=={'bytes':20908,'sha256':'98047207a4e5fd9560eaad2b29ab2a0006a1b8174346d9cc1851ff9c589590bc'}
    assert pin(HERE/'body_parser.py')=={'bytes':22921,'sha256':'d04bf897fc14053e5678431c2d20785c631102ff749d0107b74df7c5d8f5418a'}
    m=load(manifest_path);selected={}
    assert m['sealed'] is m['runtime_executed'] is m['native_ready'] is False
    def add(path,wanted=None):
        value=pin(path);assert wanted is None or value==wanted,str(path)
        assert path.resolve().is_relative_to(ROOT.resolve())
        selected[path.relative_to(ROOT).as_posix()]=value
    for group in ('sources','origins'):
        assert len(m[group])==6
        for name,wanted in m[group].items():assert '..' not in Path(name).parts;add(ROOT/name,wanted)
    runtimes={row['path']:row['pin'] for row in m['runtimes'].values()}
    assert len(runtimes)==2
    for name,wanted in runtimes.items():assert pin(Path(name))==wanted,name
    baseline_dir=HERE/'source-snapshots/offline-r1';baseline_path=baseline_dir/'source-manifest.json'
    assert pin(baseline_path)==m['tested_source_manifest']
    baseline=load(baseline_path)
    for name in ('body_probe.js','body_parser.py','test_body_probe.js','test_body_parser.py'):
        key=(HERE/name).relative_to(ROOT).as_posix();assert m['sources'][key]==baseline['sources'][key]
    assert m['origins']==baseline['origins'] and m['runtimes']==baseline['runtimes']
    for name in ('PROTOCOL.md','verify_offline.py'):
        add(baseline_dir/name,baseline['sources'][(HERE/name).relative_to(ROOT).as_posix()])
    add(baseline_path)
    receipt_path=HERE/'offline-r1/receipt.json'
    assert pin(receipt_path)=={'bytes':3401,'sha256':'ec46f859dabe7899a25889d52aef633b35627e0fb912271ad68e6bb9f4dbadf3'}
    receipt=load(receipt_path)
    assert receipt['passed'] is True and receipt['source_postcheck'] is True and receipt['total_new_tests']==27
    assert receipt['source_manifest']==m['tested_source_manifest']
    assert [(s['name'],s['tests']) for s in receipt['suites']]==[('node',15),('python',12)]
    for suite in receipt['suites']:
        job=suite['job'];assert suite['passed'] is True and job['exit_code']==0 and job['error'] is None
        assert job['job_active_processes_final']==0 and job['direct_child_collected'] is True
        assert job['completed_command_descendants_terminated'] is False and job['peak_job_commit']<=768*1024*1024
    for name,wanted in receipt['output_pins'].items():add(HERE/'offline-r1'/name,wanted)
    assert re.search(rb'Ran 12 tests in [0-9.]+s\r?\n\r?\nOK\r?\n?\Z',(HERE/'offline-r1/python.stderr.txt').read_bytes())
    node=(HERE/'offline-r1/node.stdout.txt').read_bytes()
    assert all(re.search(p,node,re.M) for p in (rb'^# tests 15\r?$',rb'^# pass 15\r?$',rb'^# fail 0\r?$'))
    assert (HERE/'offline-r1/node.stderr.txt').stat().st_size==(HERE/'offline-r1/python.stdout.txt').stat().st_size==0
    assert receipt['old_suites_reexecuted'] is receipt['game_accessed'] is receipt['Frida_loaded'] is receipt['REA_executed'] is False
    assert receipt['actual_game_calls']==0
    assert pin(R18/'manifest.json')=={'bytes':5175,'sha256':'edca1b873c18c4fb126fd8bb31a63f147e744e45008b6f6c710c2c6c24f9e870'}
    r18=load(R18/'body-probe-contract.json');guard=load(R18/'required-loaded-bytes.json')
    assert r18['sealed'] is True and r18['normative_guard_profile']=='complete_functions_211'
    assert pin(R18/'required-loaded-bytes.json')==r18['loaded_guard_file_pin']
    assert pin(FFI/'independent-file-audit.json')=={'bytes':4777,'sha256':'ab32a9010424f8cacd10f61ca2aba4119f98eaf4f5430a6a5af5c114eae00419'}
    assert load(FFI/'independent-file-audit.json')['status']=='owned_system_FFI_observed_file_evidence_verified'
    js=(HERE/'body_probe.js').read_text(encoding='utf-8')
    parser_source=(HERE/'body_parser.py').read_text(encoding='utf-8');tree=ast.parse(parser_source)
    imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
    assert all(isinstance(n,ast.Import) for n in imports)
    assert {alias.name for n in imports for alias in n.names}=={'json','re'}
    parser=types.ModuleType('independent_pure_body_probe_parser')
    exec(compile(parser_source,str(HERE/'body_parser.py'),'exec'),parser.__dict__)
    js_code=json.loads(re.search(r'const CODE = (\[.*?\]);',js).group(1))
    assert len(js_code)==len(parser.CODE)==len(guard['mandatory_code_ranges'])==3
    for j,p,g in zip(js_code,parser.CODE,guard['mandatory_code_ranges']):
        assert (j['rva'],j['offset'],j['size'],j['raw_hex'])==p
        assert j['rva']==g['rva'] and j['size']==g['bytes'] and j['raw_hex']==g['raw_hex']
        assert hashlib.sha256(bytes.fromhex(g['raw_hex'])).hexdigest()==g['sha256']
    assert [row['size'] for row in js_code]==[109,91,3] and sum(row['size'] for row in js_code)+8==211
    assert guard['mandatory_pointer_slots'][0]['rva']=='0x1d20870'
    assert guard['mandatory_pointer_slots'][0]['runtime_expected_pointer']=='authenticated_module_base+0x8f450'
    assert js.count('new NativeFunction(')==1 and "new NativeFunction(ptr(plus(state.base, 0x500560)), 'void', ['pointer'], OPTIONS)" in js
    assert "Object.freeze({abi: 'win64', scheduling: 'exclusive', exceptions: 'propagate', traps: 'none'})" in js
    probe_body=js[js.index('  function runBodyProbe()'):js.index('  function envelope(')]
    assert probe_body.index('state.probe.spent = true')<probe_body.index('Memory.alloc(152)')<probe_body.index('new NativeFunction(')
    assert js.count('Memory.alloc(')==2 and 'state.owned.A = Memory.alloc(152)' in js and 'state.owned.G = Memory.alloc(96)' in js
    assert "a.endsWith('0')" in js and "g.endsWith('0')" in js and "plus(a, 152) <= g || plus(g, 96) <= a" in js
    assert probe_body.count('writeOwned(')==4
    assert "writeOwned(a, '00'.repeat(152))" in js and "writeOwned(g, '00'.repeat(96))" in js
    assert "writeOwned(plus(a, 0x48), raw64(g))" in js and "writeOwned(g, raw64(plus(state.base, 0x1d207f8)))" in js
    assert probe_body.index("codeSnapshot('code_before')")<probe_body.index('nativeBody(state.owned.A)')
    assert probe_body.index("ownedSnapshot('owned_before')")<probe_body.index('nativeBody(state.owned.A)')
    assert probe_body.index('++state.probe.call.attempted')<probe_body.index('nativeBody(state.owned.A)')<probe_body.index('++state.probe.call.returned')
    assert probe_body.index('++state.probe.call.returned')<probe_body.index("ownedSnapshot('owned_after')")<probe_body.index("codeSnapshot('code_after')")
    assert js.count('send(payload)')==1 and js.count('.readByteArray(')==1 and js.count('.writeByteArray(')==1
    assert not re.search(r'\b(?:NativeCallback|Stalker|Thread\.runOnThread)\s*[(.]|\.free\s*\(',js)
    assert not any(x in probe_body for x in ('0x500480','0x500520','0x50b8f0','0xd9a050'))
    assert "state.done && category !== 'prefix_cleanup'" in js
    assert "setImmediate(function ()" in js and "read(state.target, 32, 'prefix_cleanup')" in js
    assert "if (state.busy) { finish('unknown', 'callback_reentered', null); return; }" in js
    assert "payload.native_game_calls_attempted = state.probe.call.attempted" in js and "payload.native_game_calls_returned = state.probe.call.returned" in js
    corpus=load(HERE/'offline-r1/vm-corpus.json');config=corpus['config'];replays=[]
    false_flags=('native_ready','native_entry_authenticated','lifetime_lease','atomic_snapshot','native_Cpp_object_verified',
        'constructor_equivalence','full_native_lifecycle','AI_acceptance_verified','gameplay_effects_verified','host_identity_authenticated')
    def evaluate(label,row,expected_status,expected_counts=None):
        result=parser.evaluate(row,config)
        assert result['status']==expected_status,(label,result)
        assert all(result[k] is False for k in false_flags)
        assert result['requires_host_authentication'] is result['requires_rea_evidence'] is result['requires_independent_code_restore_verification'] is True
        if expected_counts is not None:
            assert (result.get('native_game_calls_attempted'),result.get('native_game_calls_returned'))==expected_counts,(label,result)
        return result
    for name,status,reads,nbytes,counts in (
        ('optional','raw_abi_postcondition_match',60,1322,(1,1)),
        ('null','raw_abi_postcondition_match',56,1290,(1,1)),
        ('sixteenth','raw_abi_postcondition_match',135,1922,(1,1)),
        ('native_exception','unknown',None,None,(1,0)),
        ('cleanup_unknown','unknown',None,None,(1,1))):
        r=evaluate(name,corpus['samples'][name],status,counts)
        if reads is not None:
            assert r['explicit_reads']==reads and r['explicit_exact_bytes']==nbytes
            assert r['script_owned_write_requested_bytes']==r['script_owned_write_completed_bytes']==264
        replays.append({'name':name,'status':status,'native_attempted':counts[0],'native_returned':counts[1],
                        'reads':reads,'bytes':nbytes,'authority_false':True})
    # New owned-data boundary cases. They exercise parser consistency only;
    # no new JS VM run or real allocator/native-call claim is made.
    cases=[]
    def case(label,row,status,counts=None):
        r=evaluate(label,row,status,counts);cases.append({'name':label,'status':status,'authority_false':True});return r
    def move_g(row,value):
        row['probe']['allocations']['G']['address']=parser.h(value)
        for phase in ('before','after'):
            raw=bytearray.fromhex(row['probe'][phase]['owned']['A_hex']);raw[0x48:0x50]=value.to_bytes(8,'little')
            row['probe'][phase]['owned']['A_hex']=raw.hex()
    row=copy.deepcopy(corpus['samples']['null']);g=int(row['probe']['allocations']['G']['address'],16)
    row['probe']['allocations']['A']['address']=parser.h(g+96)
    case('reverse_exact_adjacent_owned_spans_allowed',row,'raw_abi_postcondition_match',(1,1))
    row=copy.deepcopy(corpus['samples']['null']);a=int(row['probe']['allocations']['A']['address'],16)
    move_g(row,a+0xa0);case('forward_minimum_aligned_gap_allowed',row,'raw_abi_postcondition_match',(1,1))
    row=copy.deepcopy(corpus['samples']['null']);move_g(row,a+0x90)
    case('aligned_eight_byte_overlap_refused',row,'unknown',(1,1))
    row=copy.deepcopy(corpus['samples']['null']);row['probe']['allocations']['A']['address']=parser.h(parser.MAX_ADDRESS-0x90)
    case('aligned_span_crossing_canonical_end_refused',row,'unknown',(1,1))
    row=copy.deepcopy(corpus['samples']['null']);row['probe']['call']['returned']=row['native_game_calls_returned']=0
    case('success_label_with_consistent_one_zero_call_cannot_match',row,'unknown',(1,0))
    row=copy.deepcopy(corpus['samples']['native_exception']);row['probe']['spent']=False
    r=case('unknown_attempt_before_spent_is_invalid_not_zero_native_claim',row,'unknown')
    assert 'native_game_calls_attempted' not in r and 'native_game_calls_returned' not in r
    row=copy.deepcopy(corpus['samples']['cleanup_unknown']);row['probe']['call']['returned']=True
    r=case('unknown_bool_return_counter_is_invalid_not_zero_native_claim',row,'unknown')
    assert 'native_game_calls_attempted' not in r and 'native_game_calls_returned' not in r
    report={'schema':'EU4-OWNED-BODY-COMPONENT-INDEPENDENT-SOURCE-REVIEW/1','status':'component_source_ready_not_runtime_authorized',
        'findings':[],'source_manifest':pin(manifest_path),'JS':pin(HERE/'body_probe.js'),'parser':pin(HERE/'body_parser.py'),
        'R18_manifest':pin(R18/'manifest.json'),'owned_FFI_live_audit':pin(FFI/'independent-file-audit.json'),
        'retained_author_offline_receipt':pin(receipt_path),'retained_author_new_tests':27,'suite_reexecuted':False,
        'documentation_checker_delta_only':True,'retained_actual_JS_VM_corpus_replayed':replays,
        'new_independent_pure_cases':cases,'static_component_contract':{
            'explicit_top_level_game_target':'0x500560','signature':'void(pointer)','maximum_explicit_attempts':1,
            'spent_before_allocation_and_NativeFunction':True,'attempted_before_call_returned_after_normal_wrapper_return':True,
            'owned_buffer_bytes':[152,96],'alignment':16,'pairwise_disjoint':True,'owner_refs_through_postimages_and_cleanup':True,
            'explicit_owned_write_requests':4,'explicit_owned_write_bytes':264,'each_owned_snapshot_bytes':248,
            'loaded_full_code_sizes':[109,91,3],'relocated_slot':'B+1d20870==B+8f450','each_code_slot_guard_bytes':211,
            'five_returns_mainholder_two_world_projections':True,'cleanup_uses_only_owned_data_and_fixed_module_prefix':True,
            'ctor_clone_deleting_free_game_sender_calls':False,'single_Frida_evidence_send':True},
        'limits':[
            'Only component sources/fixed artifacts are read; only the pure Python parser evaluates supplied owned records. No host import, process, fixture, JS VM, REA, Frida or game function is run.',
            'Retained27 author tests and5 actualJS-in-VM outputs are offline capability-model evidence. Replayed/mutated records demonstrate parser consistency, not real Memory.alloc provenance, NativeFunction execution or current game state.',
            'This review covers JS/parser only. capture_body_once.py and its tests/host manifest are intentionally excluded and separately reviewed. Root must authenticate held identity/source/render/REA, enforce no retry and independently verify cleanup/code restoration.',
            'Native attempted/returned count only the single explicit NativeFunction invocation/normal JS wrapper return, not nested static helper/leaf calls. Unknown1/0 is not SEH-safe recovery; malformed counters are not silently relabeled zero.',
            'Snapshots match all owned bytes; they do not dynamically trace the intermediate two native stores, exclude transient mutations or prove total-world write counts. Owned byte sources are associated by allocation metadata and fixed script implementation, not a general memory-read instruction trace.',
            'Complete109/91/3 code and ASLR-slot equality before/after are non-atomic guards. No module/world/header lifetime lease, ABA exclusion or safe exceptional unwind follows; R18 pdata/unwind gap stays unknown.',
            'A/G are raw ABI test doubles, not legal constructed C++ objects or a full native lifecycle. No constructor/deleting/free/sender entry is called explicitly; the static selected body contains nested calls whose expected counts are not dynamically measured.',
            'Timer1000ms is a soft JS callback deadline, not a native-call timeout. Scheduling exclusive is a JS lock, not a game-world lock. Framework/code-hook/native stores are outside explicit264B JS-owned-write counters.',
            'The accepted owned-system FFI audit only establishes its two simple kernel32 calls/options and pointer input. It does not establish EU4 ABI/native readiness, this game-body invocation, TLS/thread/unwind/xstate or gameplay effects.',
            'R18 manifest/contract/loaded guards are pinned and their selected normative bytes matched here; this is not a rerun of their complete static dependency graph or a new PE decode.'
        ],
        'game_accessed':False,'Frida_loaded':False,'REA_executed':False,'actual_game_calls_by_auditor':0,
        'native_ready':False,'native_ABI_ready':False,'native_entry_authenticated':False,'world_lease':False,
        'lifetime_lease':False,'sentinel_header_lease':False,'atomic_snapshot':False,'gameplay_effect_verified':False,
        'host_source_review_included':False,'new_decode_bytes':0}
    assert not OUT.exists();OUT.mkdir(parents=True)
    write_new(OUT/'component-source-ready.json',report)
    write_new(OUT/'component-source-ready.md',
        '# Owned body 组件独立源码审查\n\n通过，未发现阻断问题。唯一显式 target 为 500560/void(pointer)，永久 spent 先于分配/构造；'
        '四个 owned 写请求共 264B、前后各 248B 全图，109/91/3B 完整代码与 ASLR slot 两侧守卫匹配固定 R17/R18。无 ctor、clone、deleting、free 或 game sender；只有单条 Frida 证据 send。\n\n'
        '保留 27 项作者离线结果；独立重放 5 份真实 JS VM 产物，并验证 7 个新增纯数据边界。1/0 和 1/1 unknown 保留，畸形计数不改称 0 次调用。未重跑 suite、未启动 JS/Frida/进程或游戏。\n\n'
        '仅 JS/parser 组件 source-ready。宿主另审；不授予实际运行权限，不证明 C++ 合法对象、异常 unwind、ABI 整体、world/header lease 或 gameplay effect。所有 native ready/auth/lease/atomic 标记保持 false。\n')
    for path in (manifest_path,receipt_path,R18/'manifest.json',R18/'body-probe-contract.json',R18/'required-loaded-bytes.json',
                 FFI/'independent-file-audit.json',FFI/'manifest.json',Path(__file__).resolve(),OUT/'component-source-ready.json',OUT/'component-source-ready.md'):
        add(path)
    write_new(OUT/'manifest.json',{'schema':'EU4-OWNED-BODY-COMPONENT-INDEPENDENT-REVIEW-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'selected_runtime_pins':runtimes})
    print(json.dumps({'status':report['status'],'report':pin(OUT/'component-source-ready.json'),
        'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),'runtime_pins':len(runtimes)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    check() if args.check else main()
