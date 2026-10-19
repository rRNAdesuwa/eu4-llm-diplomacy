"""Pure owned-data parser review, using candidate JS-in-VM byte fixtures."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/frida-entry-observer-1375-v1'
OUT=ROOT/'work/reports/entry-observation-parser-review-20261015-r1'

def pin(path):
    raw=path.read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def load(path):return json.loads(path.read_bytes())
def check():
    graph=load(OUT/'manifest.json')['source_pins']
    for name,wanted in graph.items():assert pin(ROOT/name)==wanted,name
    print(json.dumps(dict(status='pass',pins=len(graph),game_accessed=False,Frida_loaded=False)))

def main():
    source=HERE/'entry_observation_parser.py';tests=HERE/'test_entry_observation_parser.py'
    assert pin(source)==dict(bytes=17315,sha256='56639f22de638696388ee7862feb050d800a4797633c25f366812dd5e034c32c')
    assert pin(tests)==dict(bytes=25826,sha256='457630457a09707d8862428e66dc15fc6ef942d272c7ed2f1d3329665bd79186')
    spec=importlib.util.spec_from_file_location('review_pure_entry_parser',source)
    parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
    tree=ast.parse(source.read_text())
    imports=[name.name for node in ast.walk(tree) if isinstance(node,ast.Import) for name in node.names]
    assert imports==['json','re'] and not any(isinstance(node,ast.ImportFrom) for node in ast.walk(tree))
    fixture=load(OUT/'crossvm-fixtures.json');assert len(fixture['cases'])==5
    def closed(result):
        for name in ('requires_host_authentication','requires_rea_evidence','requires_independent_code_restore_verification'):
            assert result[name] is True,(name,result)
        for name in ('host_identity_authenticated','creation_authenticated','image_sha_verified','code_restore_verified',
            'native_ready','native_entry_authenticated','lifetime_lease','atomic_snapshot',
            'AI_acceptance_verified','gameplay_effects_verified','pure_RPM','parser_dereferences_addresses'):
            assert result[name] is False,(name,result)
    positive=[]
    original=copy.deepcopy(fixture)
    for row in fixture['cases']:
        result=parser.evaluate(row['payload'],row['config']);closed(result)
        assert result['status']=='structural_match' and result['structural_match'] is True,result
        counts=(result['explicit_reads'],result['explicit_requested_bytes'])
        assert counts==({'null':(44,372),'sixteenth':(123,1004)}.get(row['case'],(48,404)))
        positive.append(dict(case=row['case'],status=result['status'],explicit_reads=counts[0],explicit_bytes=counts[1],
            optional_nonnull_count=result['optional_nonnull_count'],code_restore_verified=False,host_authenticated=False))
    assert fixture==original,'Parser mutated owned input'
    base=fixture['cases'][0];null=fixture['cases'][1]
    def projects(payload):return (payload['observation']['first'],payload['observation']['second'])
    def mutate_field(payload,name,value):
        for project in projects(payload):
            project['fields'][name]=value
            for row in project['reads']:
                if row['field']==name:
                    number=value if row['size']==1 else int(value,16)
                    row['raw_hex']=int(number).to_bytes(row['size'],'little').hex()
    def source_address(payload):
        for project in projects(payload):
            project['slots'][2]['address']=parser.h(int(project['slots'][2]['address'],16)+8)
    def field_address(payload):
        for project in projects(payload):
            next(row for row in project['reads'] if row['field']=='game_server')['address']=parser.h(0x600000)
    def raw_slot(payload):
        for project in projects(payload):project['slots'][4]['raw8_hex']='00'*8
    def nullable_vtable(payload):
        for project in projects(payload):project['fields']['pending_vtable']='0x0000000000000000'
    def bad_counter(payload):payload['counters']['categories']['world']['reads']=True
    def cycle(payload):payload['observation']=payload
    class PoisonString(str):
        calls=0
        def __str__(self):
            PoisonString.calls+=1
            raise AssertionError('untrusted scalar conversion must not execute')
    cases=[
        ('selected_slot_source_plus8',source_address,base),
        ('selected_slot_raw_contradicts_value',raw_slot,base),
        ('game_server_read_source_is_object_base_not_1e00',field_address,base),
        ('game_server_value_is_field_address_not_pointee',lambda p:mutate_field(p,'game_server',parser.h(0x601e00)),base),
        ('typed_update_coherently_wrong_raw',lambda p:mutate_field(p,'current_update',parser.h(0x1410a6ec0)),base),
        ('transition_bool_with_matching_raw1',lambda p:mutate_field(p,'transition_byte',True),base),
        ('null_optional_rawvt_zero_instead_None',nullable_vtable,null),
        ('thread_float',lambda p:p['observation'].__setitem__('thread_id',4412.0),base),
        ('category_bool',bad_counter,base),
        ('attempts_inconsistent_with_prefilter5',lambda p:p.__setitem__('attempts',2),base),
        ('successful_exact_bytes_short1',lambda p:p['counters'].__setitem__('exact_bytes',p['counters']['requested_bytes']-1),base),
        ('producer_authority_int1',lambda p:p.__setitem__('native_ready',1),base),
        ('producer_unknown_with_valid_raw',lambda p:p.__setitem__('status','unknown'),base),
        ('cleanup_prefix_not_restored',lambda p:p['cleanup'].__setitem__('original_prefix32_matches',False),base),
        ('cyclic_input_depth_bounded',cycle,base),
        ('poison_str_subclass_refused_without_conversion',lambda p:p.__setitem__('reason',PoisonString('safe-looking')),base),
    ]
    negative=[]
    for name,change,item in cases:
        payload=copy.deepcopy(item['payload']);config=copy.deepcopy(item['config']);change(payload)
        result=parser.evaluate(payload,config);closed(result)
        assert result['status']=='unknown' and result['structural_match'] is False,(name,result)
        if name=='producer_unknown_with_valid_raw':assert result['reason']=='producer_unknown'
        negative.append(dict(case=name,status=result['status'],reason=result['reason'],failure=result.get('failure')))
    payload=copy.deepcopy(base['payload']);config=copy.deepcopy(base['config']);config['observer_nonce']='f'*32
    result=parser.evaluate(payload,config);closed(result)
    assert result['status']=='unknown'
    negative.append(dict(case='different_expected_nonce',status=result['status'],reason=result['reason'],failure=result.get('failure')))
    assert PoisonString.calls==0
    # Retain exact schema/input bounds and per-stream owner-child provenance.
    own=load(OUT/'own-node-job-receipt.json')
    assert own['error'] is None and own['exit_code']==0 and own['job_active_processes_final']==0
    assert own['peak_job_commit']<=own['memory_limit']==256*1024*1024
    report=dict(schema='EU4-ENTRY-OBSERVATION-PARSER-INDEPENDENT-SOURCE-REVIEW/1',
        status='ready_for_source_seal_at_reviewed_pins',findings=[],source=pin(source),tests=pin(tests),
        original41_tests=dict(author_reported_passed=True,reported_seconds=0.454,independently_reexecuted=False,
            formal_receipt_supplied=False),
        independent_cross_language_positive_cases=positive,independent_negative_cases=negative,
        input_mutated=False,untrusted_scalar_conversion_calls=0,imports_only=imports,
        reviewed_boundaries=[
            'Exactly six source-address/raw8/value slots replayed with literalQ offsets and module-relative return identities; holder must equal fresh outer',
            'World raw reads/order/sizes/addresses matched to root and object fields; current40/optional70/78/game1e00 pointee/server330/holder360 linked to originalR8/RCX',
            'Typed outer/game/server/update identities strict; optional uint64vt may be noncanonical and optional pointers may alias current, without deduplicating actual read counts',
            'Config8/schema/fixednonce/creation/PID/base/prefix and strict int/bool/string types; all selected source evidence remains owned numeric/hex data',
            'Compact envelope16384B/node1024/depth10/scalar bounds before projection; cyclic input and Pythonstr subclass fail without custom conversion or dereference',
            'Successful classifiedcounter totals require48/404,44/372 or boundedprefilter-derived equivalents, including123/1004 worst case; exact=requested',
            'Unknown producer status is never upgraded; successful replay still requires external host/REA/independent code-restoration verification and all authority staysfalse'],
        limitations=[
            'Cross-language positives are candidateJS running only in controlledNodeVM fake memory; no actualFrida/onEnter/process observation',
            'Pure parser checks supplied structured data consistency, not authenticity; arbitrary coherent synthetic records can match and are not native_entry_authenticated',
            'Ordered two-pass equality does not prove atomicworld or lifetime; repeated pointers are not assumed distinct and optionalvt is not upgraded into ownership/typeextent',
            'Prefix32 raw bytes are absent from payload, so cleanup booleans/counters are producer statements; code_restore_verified remainsfalse',
            'API expects an already decoded ordinaryPython payload/config; external transport framing, duplicateJSON-key refusal, hostmanifest and sender/session authentication remain futurehost duties',
            'No futurehostmanifest or capture_once review; no source/timer wall-clock guarantee inferred from counters',
            'Author41 suite was not repeated; test source is pinned, while no formal41-result file was supplied at review time'],
        own_Node_fixture_generation=dict(peak_job_commit=own['peak_job_commit'],job_active_final=0,
            direct_child_collected=True,memory_limit=own['memory_limit']),
        parser_dereferences_addresses=False,REA_invoked=False,Frida_loaded=False,game_accessed=False,
        native_game_calls=0,requests_published=0,new_API_effects=0,native_ready=False)
    pins={}
    for path in (source,tests,HERE/'entry_observer.js',HERE/'test_entry_observer.js',HERE/'CONTRACT.md',HERE/'job_tree.py',
        OUT/'crossvm-fixtures.json',OUT/'crossvm-stderr.txt',OUT/'own-node-job-receipt.json',
        ROOT/'work/review_entry_parser_crossvm_20261015.js',Path(__file__),
        ROOT/'work/reports/frida-entry-script-review-20261015-r1/independent-source-ready.json',
        ROOT/'work/reports/frida-entry-script-review-20261015-r1/manifest.json'):
        pins[path.relative_to(ROOT).as_posix()]=pin(path)
    path=OUT/'independent-source-ready.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    pins[path.relative_to(ROOT).as_posix()]=pin(path)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-REVIEW-MANIFEST/1',source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],positive_cases=len(positive),negative_cases=len(negative),
        pins=len(pins),report=pin(path),game_accessed=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true')
    if p.parse_args().check:check()
    else:main()
