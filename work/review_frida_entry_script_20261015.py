"""Source/retained/raw/own-VM review only. Never attaches or loads Frida."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/frida-entry-observer-1375-v1'
OUT=ROOT/'work/reports/frida-entry-script-review-20261015-r1'

def pin(path):
    count=0;sha=hashlib.sha256()
    with path.open('rb') as stream:
        while raw:=stream.read(65536):count+=len(raw);sha.update(raw)
    return dict(bytes=count,sha256=sha.hexdigest())
def load(path):return json.loads(path.read_bytes())
def check():
    graph=load(OUT/'manifest.json')['source_pins']
    for name,wanted in graph.items():assert pin(ROOT/name)==wanted,name
    print(json.dumps(dict(status='pass',pins=len(graph),Frida_loaded=False,game_accessed=False)))

def main():
    pins={}
    def fixed(path,wanted=None):
        value=pin(path)
        if wanted is not None:assert value==wanted,path
        key=path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
        pins[key]=value
    corrected=HERE/'offline-verification-r2.json'
    fixed(corrected,dict(bytes=1823,sha256='450f7868693437ed61ac880c57171cc640bc1e05768f226fc90a0106ca4cb424'))
    receipt=load(corrected)
    for name,wanted in receipt['source_pins'].items():fixed(HERE/name,wanted)
    source=HERE/'entry_observer.js';tests=HERE/'test_entry_observer.js'
    assert pin(source)==dict(bytes=14601,sha256='4b2107d0a912280c271be66e5436482f1e89bfb348b326dfd25daf2d3308820e')
    assert pin(tests)==dict(bytes=16327,sha256='30afc138b6b98b1fb4d5ddc0790e74ff9f385ca2457561ff27a7fc748eac654e')
    provenance=load(HERE/'source-pins.json')
    assert len(provenance['inputs'])==8 and provenance['new_native_disassembly_bytes']==0
    for name,wanted in provenance['inputs'].items():fixed(Path(name),wanted)
    old=load(HERE/'offline-receipt.json');fixed(HERE/'offline-receipt.json',receipt['original_receipt_pin'])
    fixed(HERE/'offline-tests.stdout.tap',receipt['unchanged_stdout_pin'])
    assert old['passed'] is False and old['exit_code']==0 and old['runner_error'] is None
    assert old['source_unchanged'] and old['child_collected']
    output=(HERE/'offline-tests.stdout.tap').read_text(encoding='utf-8')
    for name,number in [('tests',18),('pass',18),('fail',0),('cancelled',0),('skipped',0)]:
        assert re.search(r'^\u2139 '+name+' '+str(number)+'$',output,re.M),name
    for field in ('node','memory_helper'):
        value=old[field];fixed(Path(value['path']),{k:value[k] for k in ('bytes','sha256')})
    script=source.read_text()
    assert len(re.findall(r'\.readByteArray\s*\(',script))==1
    for token in (r'\bNativeFunction\s*\(',r'\bNativeCallback\s*\(',r'\.write[A-Z]\w*\s*\(',
        r'\bMemory\.alloc\s*\(',r'Interceptor\.detachAll\s*\('):assert not re.search(token,script),token
    assert 'DEADLINE_MS = 1000, MAX_READS = 128, MAX_BYTES = 8192' in script
    for field in ('native_ready','native_entry_authenticated','creation_authenticated_in_script',
        'image_sha_verified_in_script','lifetime_lease','atomic_snapshot'):
        assert re.search(r'\b'+field+r'\s*:\s*false',script),field
    # Replay retained original PE byte rows without Capstone or new decoding.
    dis=load(ROOT/'work/reports/war-peace-api-20261015-r4/war/disassembly.json')
    assert dis['game_sha256']==provenance['game_sha256'] and dis['runtime_verified'] is False
    function=next(x for x in dis['functions'] if x['entry_rva']=='0x10a6ec0')
    at=0x10a6ec0;raw=b''
    for row in function['instructions']:
        assert int(row['rva'],16)==at
        value=bytes.fromhex(row['bytes']);raw+=value;at+=len(value)
        if len(raw)>=32:break
    assert raw[:32].hex()==provenance['entry_prefix32_hex']
    # Closed-form maximum: all15 rejected callbacks reach fifth slot,16th matches.
    math_rows=[('prefix_before',1,32),('prefilter16x5',80,640),
        ('first_holder_plus_world',18,130),('second_six_slots_plus_world',23,170),('prefix_cleanup',1,32)]
    assert sum(row[1] for row in math_rows)==123 and sum(row[2] for row in math_rows)==1004
    own=load(OUT/'independent-vm.stdout.json');job=load(OUT/'own-node-job-receipt.json')
    assert own['passed'] is True and len(own['cases'])==7 and own['original18_tests_reexecuted'] is False
    assert job['error'] is None and job['exit_code']==0 and job['job_active_processes_final']==0
    assert job['direct_child_collected'] and job['peak_job_commit']<=job['memory_limit']==256*1024*1024
    for name in ('independent-vm.stdout.json','independent-vm.stderr.txt','own-node-job-receipt.json'):fixed(OUT/name)
    assert (OUT/'independent-vm.stderr.txt').stat().st_size==0
    job_source=HERE/'job_tree.py';fixed(job_source,dict(bytes=8615,sha256='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'))
    fixed(ROOT/'work/review_frida_entry_vm_20261015.js');fixed(Path(__file__))
    for path in (ROOT/'work/reports/frida-entry-job-review-20261015-r1/independent-r3-source-ready.json',
                 ROOT/'work/reports/frida-entry-job-review-20261015-r1/manifest.json'):fixed(path)
    report=dict(schema='EU4-FRIDA-ENTRY-SCRIPT-INDEPENDENT-SOURCE-REVIEW/1',
        status='source_ready_with_explicit_timer_contract_clarification',code_findings=[],
        source=dict(path=source.relative_to(ROOT).as_posix(),**pin(source)),
        timer_contract_precision=dict(priority=3,original_contract=pin(HERE/'CONTRACT.md'),
            original_phrase='whole-script固定1000ms deadline',
            clarification='Attach后注册1000ms等待timer；timer不能抢占同步onEnter/readByteArray，回调与清理可能晚于该时间。实际宿主超时、卸载/脱离和恢复另需独立验收。',
            code_change_required=False,does_not_authorize_attachment=True),
        original18_retained_result=dict(exit_code=0,tests=18,pass_count=18,fail_count=0,
            original_false_wrapper_preserved=True,corrected_receipt=pin(corrected),tests_reexecuted=False),
        independent_VM_cases=own['cases'],own_VM_job=dict(exit_code=0,active_members_final=0,
            peak_job_commit=job['peak_job_commit'],memory_limit=job['memory_limit'],
            new_own_Node_child=True,Frida_loaded=False,game_accessed=False),
        budget_math=[dict(category=name,reads=reads,requested_bytes=count) for name,reads,count in math_rows],
        maximum_explicit_reads=123,maximum_explicit_requested_bytes=1004,
        hard_script_read_count_limit=128,hard_script_requested_byte_limit=8192,
        normal_optional=dict(reads=48,bytes=404),normal_null_optional=dict(reads=44,bytes=372),
        fixed_entry_prefix32_retained_PE_replay=True,new_native_disassembly_bytes=0,
        source_boundary_checks=[
            'Exact8-field config, pid uint32, x64/windows/pointerSize8, modulebase/extent, entryRVA10a6ec0 and fixed prefix32 before hook attempt',
            'No arbitrary entry/callback/continuation/NativeFunction/allocator/gamefield writer; Interceptor code hook is explicit, not pureRPM',
            'Direct onEnter Q/RCX/R8/thread/depth; five literal returns bounded16 callbacks; mismatches alone may await another callback under same hook',
            'Matching first five slots reused only synchronously in same callback; holder/world copied, secondpass six slots/fresh roots independently read',
            'Slots/raw8/address and world/raw/address/scalar retain replayable owned values; unmapping borrowed slots/world after callback does not affect delayed result',
            'Typed mainholder/outer/game/current/server/update/map path verified; optional vt is only uint64diagnostic, not ownership/typeextent proof',
            'Global explicitread budget covers prefilter/prefix/setup/finalprefix; failed branded ArrayBuffer reads remain unknown',
            'After terminal no Q/heap reads; deferred cleanup only listenerdetach/flush/fixed prefix32; cleanup mismatch lowers match to unknown',
            'One ASCII send envelope≤16KiB; header lease/atomic/creation/SHA/nativeauthority remain false'],
        API_documentation=dict(primary='https://frida.re/docs/javascript-api/',checked_date='2026-10-15',
            notes='API documents invocation context/returnAddress/threadId/depth, listener.detach, readByteArray ArrayBuffer, and scheduled timing callbacks. This is documentation compatibility only.'),
        limitations=[
            'No actual Frida17 load, game attachment, real entry context, nativecall or request dispatch; NodeVM controls all fake memory/APIs',
            'Hostcapture_once, original PIDcreation/image verification, script unload/session detach, independent post-hook code restoration and target liveness are unreviewed/not yet implemented in this scope',
            'setTimeout is a scheduled callback, not a hard whole-script wall-clock interruption; external1500ms release remains an unverified proposed host condition',
            'Only selected six stack slots are retained, no full1200B stackwindow; static chain and selected current binding do not establish outer/sentinel/header lifetime lease or atomicworld',
            'Prefix32 equality proves only selected bytes; listenerdetach/flush flags do not prove all injected runtime or hook resources released',
            'Explicit read counters exclude Frida internals/JIT/module APIs and all CPU reads;8KiB is not an agent or whole-game memory cap',
            'The seven independent cases are newVM probes, not seven real API effects or a repeat of the original18 suite'],
        actual_Frida_loaded=False,REA_invoked=False,game_accessed=False,native_game_calls=0,
        requests_published=0,new_API_effects=0,native_ready=False,native_entry_authenticated=False,
        header_lifetime_lease=False,atomic_snapshot=False)
    path=OUT/'independent-source-ready.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    fixed(path)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-REVIEW-MANIFEST/1',source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],report=pin(path),pins=len(pins),actual_Frida_loaded=False,game_accessed=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true')
    if p.parse_args().check:check()
    else:main()
