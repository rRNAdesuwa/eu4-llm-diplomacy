"""Independent static ABI/retained-receipt review; never runs the harness."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/native-entry-forward-observer-1375-v1'
OUT=ROOT/'work/reports/native-entry-forward-observer-review-20261015-r1'

def pin(path):
    raw=path.read_bytes()
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def load(path): return json.loads(path.read_bytes())

def check():
    data=load(OUT/'manifest.json')
    for path,expected in data['source_pins'].items(): assert pin(ROOT/path)==expected,path
    print(json.dumps(dict(status='pass',pins=len(data['source_pins']),game_accessed=False,tests_reexecuted=False)))

def main():
    expected={
        'DESIGN.md':(4210,'93fd73fc969813299fbd3c22c08354762558393a1789a34f7d6568e3d3e3c29f'),
        'forward_layout.h':(2426,'ca5a94cbf847344ba79676c1c1a2172eb41c81369fc09b14986ec90d67b260b2'),
        'entry_forward_model.asm':(6574,'aba916a14289d9c48a88a5c7974aec92b3cd370d3bd5ef90e9694ae7688e28d0'),
        'test_forward_model.cpp':(16354,'08aa2a077300b7c133f6b482320e63574cca772ff9e199219c85c36f6863e927'),
        'build_offline.py':(8515,'07d00f61dff8db5b0f622b87ee439a332b551940a9cd25134262f4f8b36dfd2d'),
        'check_prepared.py':(4112,'0414cd8bebbdc8dabd32c97fc66cd6eb5049e9a912fe4c6997e05dcf0100bf1f'),
        'build-attempt-04/receipt.json':(9168,'2473fbf604ab009b97d898fc3f4dad30300cce179d37fb902e74ae43ec7d61ae'),
        'environment-redaction.json':(1826,'ed8026bca17f3fd592b043202c850dcb17c56dbc322a677e4d67f8d44adb76b3'),
        'SELFTEST.md':(2932,'f24032cc2b06af8dc3aab74b5e73a08c57ab4ff1b00d4e42b4a2d42d94166844'),
    }
    pins={}
    def fixed(path,wanted=None):
        actual=pin(path)
        if wanted is not None: assert actual==wanted,path
        pins[path.relative_to(ROOT).as_posix()]=actual
    for name,(size,sha) in expected.items(): fixed(HERE/name,dict(bytes=size,sha256=sha))
    source=load(HERE/'source-pins.json');fixed(HERE/'source-pins.json')
    for name,wanted in source['inputs'].items(): fixed(ROOT/name,wanted)
    assert source['new_disassembly_bytes']==0 and source['native_ready'] is False
    receipt=load(HERE/'build-attempt-04/receipt.json')
    assert receipt['source_pins']==receipt['source_after'] and receipt['source_unchanged']
    for name,wanted in receipt['source_pins'].items(): fixed(HERE/name,wanted)
    for name,wanted in receipt['output_pins'].items(): fixed(HERE/'build-attempt-04'/name,wanted)
    assert receipt['passed'] and receipt['all_children_collected'] and receipt['default_44_and_DLL_unchanged']
    assert [s['name'] for s in receipt['stages']]==['environment','assemble','compile','link','run']
    assert all(s['exit_code']==0 and s['error'] is None and s['collected'] for s in receipt['stages'])
    stored=load(HERE/'build-attempt-04/run.stdout.txt')
    assert stored==receipt['test_result'] and (stored['cases'],stored['checks'])==(14,157)
    assert set(load(HERE/'build-attempt-04/environment.stdout.txt'))=={'PATH','INCLUDE','LIB','LIBPATH'}
    redactions=load(HERE/'environment-redaction.json')
    assert len(redactions['rows'])==3
    old_receipt_shas={'01':'604966caebd618b1c0bd8b892d94fbdea18b079c627e1ccfcb0eb141148d340c',
        '02':'6cf86d6dbd39477f6498875e8628c6d29b4ac22ca3744f4083bb29f04a538447',
        '03':'fc423d30b3752a5e27023c0badfbf3df0fe5a32a806709621ad19979b08ec1df'}
    for row in redactions['rows']:
        path=HERE/row['path'];fixed(path,row['redacted_pin'])
        # Current redacted logs contain only the four allowed keys; values never printed/copied.
        assert set(load(path))=={'PATH','INCLUDE','LIB','LIBPATH'}
        oldpath=path.parent/'receipt.json';fixed(oldpath)
        number=path.parent.name[-2:]
        assert pin(oldpath)['sha256']==old_receipt_shas[number]
        assert load(oldpath)['output_pins'][path.name]==row['original_pin']
    previous=load(HERE/'build-attempt-03/receipt.json')
    for name in ('forward_layout.h','entry_forward_model.asm','test_forward_model.cpp'):
        assert previous['source_pins'][name]==receipt['source_pins'][name]
    build=ROOT/'bridge/native/tag_diplomacy_1375_v31/build-7/build/build.json'
    frozen=load(build);fixed(build)
    assert len(frozen['source_pins'])==44
    for name,wanted in frozen['source_pins'].items(): fixed(ROOT/name,wanted)
    fixed(build.parent/frozen['DLL'],frozen['dll'])
    asm=(HERE/'entry_forward_model.asm').read_text()
    cpp=(HERE/'test_forward_model.cpp').read_text()
    header=(HERE/'forward_layout.h').read_text()
    def proc(name): return re.search(r'^'+name+r' PROC(?: FRAME)?\n(.*?)^'+name+r' ENDP',asm,re.M|re.S).group(1)
    def line(name,needle):
        return next(i for i,text in enumerate((HERE/name).read_text().splitlines(),1) if needle in text)
    adapter=proc('model_adapter')
    assert 'sub rsp, 0e8h' in adapter and 'add rsp, 0e8h\n    ret' in adapter
    gprs=[('rax','20'),('rcx','28'),('rdx','30'),('r8','38'),('r9','40'),('r10','48'),('r11','50')]
    for register,offset in gprs:
        assert f'mov [rsp+{offset}h], {register}' in adapter
        assert f'mov {register}, [rsp+{offset}h]' in adapter
    for index,offset in enumerate(('60','70','80','90','0a0','0b0')):
        assert f'movdqu [rsp+{offset}h], xmm{index}' in adapter
        assert f'movdqu xmm{index}, [rsp+{offset}h]' in adapter
    assert 'call model_capture_entry' in adapter and 'jmp ' not in adapter
    assert proc('model_jump_thunk').strip()=='jmp model_adapter'
    wrapper=proc('model_wrapper')
    assert 'call model_adapter\nmodel_return_to_wrapper_call LABEL BYTE' in wrapper
    assert 'call model_jump_thunk\nmodel_return_to_wrapper_jump LABEL BYTE' in wrapper
    offsets=[0]
    for name,frame,label in [('model_wrapper',0x38,'model_return_to_server'),
        ('model_server_frame',0x328,'model_return_to_relay'),
        ('model_relay',0x78,'model_return_to_loop'),('model_loop',0x48,'model_return_to_main')]:
        body=proc(name)
        literal=format(frame,'x')
        assert f'sub rsp, {literal}h' in body and f'add rsp, {literal}h' in body
        offsets.append(offsets[-1]+frame+8)
    assert offsets==[0,0x40,0x370,0x3f0,0x440]
    assert 'mov [rsp+60h], rax\n    call model_loop' in proc('model_run')
    holder=offsets[-1]+8+0x60
    assert holder==0x4a8
    q=0x100008;s=q-0xe8;t=s-8
    assert (q&15,s&15,t&15)==(8,0,8) and t==q-0xf0
    ranges=[('shadow',0,0x20),('GPR',0x20,0x58),('padding',0x58,0x60),
        ('XMM0_5',0x60,0xc0),('descriptor',0xc0,0xe0),('padding',0xe0,0xe8),('original_return',0xe8,0xf0)]
    assert all(a[2]==b[1] for a,b in zip(ranges,ranges[1:]))
    callback=proc('model_capture_entry')
    assert all(f'mov [rsp+{slot}], rax' in callback for slot in ('8','10h','18h','20h'))
    assert 'call model_capture_impl' in callback and 'call model_clobber_volatiles' in callback
    assert 'std::memcpy(&value, reinterpret_cast<const void*>' in cpp
    for token in ('OpenProcess','ReadProcessMemory','WriteProcessMemory','CreateRemoteThread',
                  'LoadLibrary','GetProcAddress','VirtualAlloc','Frida','WinDLL'):
        assert token not in asm+cpp+header,token
    for name in ('kNativeEntryAuthenticated','kNativeReady','kLifetimeLease','kAtomicSnapshot',
                 'kExceptionUnwindVerified','kAvxXstatePreserved','kGameInstallationProvenance'):
        assert re.search(r'\b'+name+r'\s*=\s*false',header)
    evaluator=re.search(r'bool evaluate_owned\(.*?\n\}',cpp,re.S).group(0)
    assert not any(token in evaluator for token in ('reader.read','reinterpret_cast','memcpy','borrow->'))
    report=dict(schema='EU4-NATIVE-ENTRY-FORWARD-INDEPENDENT-SOURCE-REVIEW/1',
        status='ready_for_offline_candidate_seal_at_reviewed_pins',findings=[],
        adopted_build_attempt='04',source_pins=receipt['source_pins'],
        retained_result=dict(cases=14,checks=157,independently_reexecuted=False,
            compile_reexecuted=False,all_direct_Popen_children_collected=True,
            compiler_driver_observed_peak_committed_bytes=34025472),
        abi_checks=dict(entry_Q_mod16=8,adapter_allocation_bytes=0xe8,call_site_S_mod16=0,
            callback_T_relative_Q=-0xf0,callback_T_mod16=8,
            save_ranges_relative_S=[dict(kind=k,begin=hex(a),end_exclusive=hex(b)) for k,a,b in ranges],
            volatile_GPR_pairs=len(gprs),volatile_XMM_low128_pairs=6,
            shadow_written_bytes=32,descriptor_bytes=32,descriptor_disjoint=True,
            direct_RET=True,tail_JMP_does_not_add_return_frame=True,
            return_offsets_relative_Q=list(map(hex,offsets)),holder_offset_relative_Q=hex(holder)),
        synchronous_ownership_checks=dict(descriptor_copied_before_project=True,
            local_Reader_does_not_escape=True,two_owned_numeric_projections=True,
            no_pointer_typed_members_in_output=True,
            owned_evaluator_dereferences_memory=False,
            owned_evaluator_scope='Anonymous-namespace trusted harness consistency helper, not generic untrusted snapshot validator',
            selected_read_counts=[42,46],selected_read_bytes=[308,340],
            descriptor_and_shadow_reads_outside_selected_counters=True),
        precise_source_locations={
            'adapter_frame':line('entry_forward_model.asm','model_adapter PROC'),
            'callback_shadow':line('entry_forward_model.asm','model_capture_entry PROC'),
            'actual_return_chain':line('entry_forward_model.asm','model_wrapper PROC'),
            'valid_entry':line('test_forward_model.cpp','bool valid_entry('),
            'allowed_spans':line('test_forward_model.cpp','bool allowed ='),
            'typed_project':line('test_forward_model.cpp','bool project('),
            'owned_evaluator':line('test_forward_model.cpp','bool evaluate_owned('),
            'synchronous_copy':line('test_forward_model.cpp','const OwnedEntry entry{borrow->'),
            'own_process_only_monitor':line('build_offline.py','current, observed_peak = child_memory(child._handle)'),
        },
        receipt_replay=dict(source_and_output_hashes_match=True,old_ASM_header_CPP_match04=True,
            redaction_mappings_verified=3,old_environment_hashes_historical_only=True,
            environment_values_printed_or_copied=False,default44_and_DLL_unchanged=True),
        limitations=[
            'Own synthetic EXE labels/storage only; no EU4 callback, thread/entry authentication, image provenance, lease, native execution readiness or new API effect',
            'FRAME/.allocstack compile does not prove unwind correctness; flags, AVX/YMM/ZMM upper state, MXCSR/FPU and arbitrary callback ABI violation are outside scope',
            'valid_entry/project assume synchronous known descriptor and private live fixture/stack spans; no bad arbitrary pointer exception-safety or concurrent/reentrant safety claim',
            'evaluate_owned checks status/two equal projections, not all untrusted scalar fields; never expose it as a general acceptance validator',
            'Only selected Reader operations are counted; CPU save/restore, 32B descriptor copy and32B shadow probe are separate',
            'Observed compiler driver memory and collected direct Popen children do not prove all internal child peaks or generic failure-path descendant cleanup',
            'Original03 SET environment bytes were not retained for replay; only hash history and explicit redaction mapping/current white-list logs are verified',
        ],new_disassembly_bytes=0,game_accessed=False,game_native_calls=0,requests_sent=0,
        native_ready=False,native_entry_authenticated=False,header_lifetime_lease=False,atomic_snapshot=False)
    OUT.mkdir(exist_ok=False)
    path=OUT/'independent-source-ready.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    fixed(Path(__file__));fixed(path)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-REVIEW-MANIFEST/1',source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],report=pin(path),pins=len(pins),tests_reexecuted=False,game_accessed=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true')
    if p.parse_args().check:check()
    else:main()
