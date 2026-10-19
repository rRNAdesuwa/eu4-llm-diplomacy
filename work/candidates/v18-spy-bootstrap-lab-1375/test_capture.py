"""Synthetic-only complete private stream; no process/native calls or loader."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import build_manifest as b
import wire
import real_capture as r
import client

MOCK=b.ROOT/'work/candidates/v18-spy-restricted-host-1375/validation-attempt-7/mock-events.jsonl'


def pack(rows):return b''.join(b.canonical(row)+b'\n' for row in rows)


def synthetic():
    # Test-only conversion, never accepted as source-bound disk provenance by
    # inspect(). No caller-facing fixture/record conversion API is exposed.
    rows=[b.json_value(line) for line in b.bounded(MOCK,1048576).splitlines()]
    for row in rows:
        row['mock_environment']=False
        if row['event']=='core_event':row['core']['mock_resolver']=False
    return rows


def envelope(rows,footer=True):
    identity={k:rows[0][k] for k in wire.IDENTITY};owner=rows[0]['thread'];image=rows[0]['image_base'];outside=[]
    def add(event,**fields):
        e=dict(identity,schema='EU4SPYBOOTSTRAP/1',event=event,game_sha256=wire.p.GAME_SHA256,image_base=image,
               owner_thread=owner,thread=owner,ordinal=len(outside)+1,uptime_ms=10000,send_supported=False,
               strict_sp_verified=False,world_epoch_verified=False,production_ready=False,**fields)
        outside.append(e)
    add('bootstrap_verified',disposable_test_premise=True,native_environment_initialized=True,automatic_stage=False,runtime_verified=False)
    add('install_attempt',detail=dict(event='hook_install_attempt',attempt=1,result=0,prefix_unchanged=False,retrying=False,failure_stage=0,error=0,
                                    failure_thread=0,collected=20,suspended=20,resume_failures=0,resume_error=0,resume_thread=0,rip=0,send_supported=False))
    add('hook_installed',frame_rva=0x10a6ec0,prefix_bytes=20,stage_limit=3,health_interval_ms=1000,poll_interval_ms=100,hot_unload_supported=False)
    raw=b'';ordinal=0;claims={};claimed=0;complete=0;frame=0
    for f in sorted({x['frame'] for x in rows}):
        group=[x for x in rows if x['frame']==f];claim=[x for x in group if x['event']=='claim']
        sequence=claim[0]['sequence'] if claim else 0
        add('owner_call_begin',owner_entry=f*100,controller_frame_before=frame,raw_start=len(raw),raw_first_ordinal=ordinal+1,request_sequence=sequence)
        segment=pack(group);raw+=segment;ordinal+=len(group);frame=f
        if sequence:claimed=complete=sequence;claims[sequence]=bytes.fromhex(claim[0]['wire_hex'])
        add('owner_call_return',owner_entry=f*100,controller_frame_after=frame,raw_end=len(raw),raw_last_ordinal=ordinal,
            raw_segment_sha256=b.sha(segment),controller_returned=True,input_closed=True,state=3 if sequence else (4 if complete==3 else 1),failure=0,
            claimed=claimed,completed=complete,success=True)
    if footer:add('completed_no_send',owner_entry=frame*100,controller_frame=frame,stages=3,owned_objects_remaining=0,individual_effect_verified=False)
    return raw,pack(outside),identity,claims


class Capture(unittest.TestCase):
    def check(self,rows=None,complete=True):
        rows=synthetic() if rows is None else rows
        raw,out,identity,claims=envelope(rows,complete)
        return r.validate_stream(raw,out,identity,claims,complete)

    def test_complete_and_false_is_normal(self):
        result=self.check();self.assertTrue(result['completed']);self.assertEqual(result['completed_stages'],3)
        self.assertFalse(result['send_supported']);self.assertFalse(result['actual_host_authenticated'])
        self.assertEqual(result['legality_results']['family_preview'],dict.fromkeys(wire.p.FAMILIES,False))

    def test_initial_partial_not_completed(self):
        first=synthetic()[0];raw,out,identity,claims=envelope([first],False)
        result=r.validate_stream(raw,out,identity,claims,False)
        self.assertFalse(result['completed']);self.assertEqual(result['claimed_sequence'],0)

    def test_raw_core_semantics_reject(self):
        for mutation in ('mock','begin_as_return','owned_alias','thread','full_handle','root','flag'):
            rows=synthetic();core=next(x for x in rows if x['event']=='core_event')
            if mutation=='mock':core['core']['mock_resolver']=True
            elif mutation=='begin_as_return':core['core']['call_entered']=True
            elif mutation=='owned_alias':core['core']['clone_id']=core['core']['original_id']=44
            elif mutation=='thread':core['thread']+=1
            elif mutation=='full_handle':core['observed']['target']=0
            elif mutation=='root':core['observed']['game']+=8
            else:core['observed']['manual_pause']=True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.check(rows)

    def test_all_second_health_types_are_strict(self):
        for key in ('frame','uptime_ms','claimed_sequence','completed_stages','image_base','ordinal','thread'):
            for bad in (True,1.0,'1'):
                rows=synthetic();health=next(x for x in rows if x['event']=='health' and x['frame']==2);health[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises((ValueError,TypeError,KeyError)):self.check(rows)

    def test_segment_pairing_and_all_outer_types(self):
        raw,out,i,c=envelope(synthetic());source=[b.json_value(x) for x in out.splitlines()]
        variants=[]
        for key,value in (('owner_entry',True),('controller_frame_after',1.0),('raw_end',0),('raw_last_ordinal',999),('raw_segment_sha256','0'*64),
                          ('controller_returned',False),('input_closed',False),('failure',1),('completed',True),('thread',1)):
            rows=copy.deepcopy(source);rows[4][key]=value;variants.append(rows)
        variants.extend([source[:-1],source+source[-1:],source[:4]+source[5:],source[:3]+source[4:]])
        for rows in variants:
            with self.subTest(row=rows[4] if len(rows)>4 else rows),self.assertRaises(ValueError):r.validate_stream(raw,pack(rows),i,c,True)

    def test_claim_exact_bytes_and_no_extra(self):
        raw,out,i,c=envelope(synthetic())
        for bad in ({},dict(c,**{}),{**c,4:b'evil'}):
            if bad==c:bad=dict(c);bad[1]=bad[1].replace(b'actor=FRA',b'actor=ENG')
            with self.assertRaises(ValueError):r.validate_stream(raw,out,i,bad,True)

    def test_future_clock_and_bad_tail(self):
        raw,out,i,c=envelope(synthetic());rows=[b.json_value(x) for x in out.splitlines()]
        for k,value in ((3,10001),(4,9999)):
            altered=copy.deepcopy(rows);altered[k]['uptime_ms']=value
            with self.assertRaises(ValueError):r.validate_stream(raw,pack(altered),i,c,True)
        for value in (raw+b'{}\n',raw[:-1],b' '*(1048577),b'{"x":1,"x":2}\n'):
            with self.assertRaises(ValueError):r.validate_stream(value,out,i,c,True)

    def test_full_raw_validation_before_health_compaction(self):
        rows=synthetic();health=copy.deepcopy(rows[2] if rows[2]['event']=='health' else rows[0])
        # Many real raw health rows can exceed the projection's input limit;
        # only valid health is compactable, never a core event or bad tail.
        base=[copy.deepcopy(rows[0]) for _ in range(200)]
        for n,x in enumerate(base,1):x['frame']=n;x['ordinal']=n
        raw,out,i,c=envelope(base,False)
        result=r.validate_stream(raw,out,i,c,False);self.assertEqual(result['input_records'],200)
        base[150]['observed']['target_overlord']=True
        with self.assertRaises(ValueError):self.check(base,False)

    def test_strict_manifest_equality(self):
        self.assertFalse(b.exact({'bytes':1},{'bytes':True}));self.assertFalse(b.exact({'rva':1},{'rva':1.0}))

    def test_codec_closed_namespace(self):
        _,_,identity,_=envelope(synthetic());raw=wire.encode_boot(identity)
        self.assertEqual(wire.decode_boot(raw),identity)
        for value in (raw+b'\n',raw.replace(b'\n',b'\r\n'),raw.replace(b'no_send=1',b'no_send=0'),raw.replace(b'pid=1234',b'pid=01234'),raw+b'\0'):
            with self.assertRaises(ValueError):wire.decode_boot(value)

    def test_stage_proposal_uses_later_health_and_explicit_next(self):
        rows=synthetic();raw,out,i,c=envelope([rows[0]],False)
        status=r.validate_stream(raw,out,i,c,False);status.update(identity=i,source_manifest_verified=True)
        request=client.proposed_request(status,i,'lifecycle',10000)
        self.assertEqual(request['expires'],70000);self.assertEqual(wire.p.decode(wire.p.encode(request)),request)
        for stage,now in (('owned_command',10000),('lifecycle',12501),('lifecycle',9999),('lifecycle',True)):
            with self.assertRaises(ValueError):client.proposed_request(status,i,stage,now)

    def test_unbound_files_cannot_become_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises((ValueError,OSError)):r.inspect(Path(td),envelope(synthetic())[2])

    def test_complete_disk_chain_with_synthetic_loader_and_exact_claims(self):
        # Inject only a synthetic verified-build result; real inspect has no
        # caller-supplied verifier seam. Every file provenance check below runs.
        raw,out,i,claims=envelope(synthetic())
        manifest={'dll_sha256':i['dll_sha256'],'pe':{'bridge_start_rva':0x7000}}
        with tempfile.TemporaryDirectory() as td,patch.object(b,'verify_build',return_value=(manifest,i['manifest_sha256'])):
            directory=Path(td);packet=wire.encode_boot(i)
            (directory/f'bootstrap-{i["pid"]}-{i["creation"]}.request').write_bytes(packet)
            session=wire.session_path(directory,i);session.mkdir()
            (session/'raw-events.jsonl').write_bytes(raw);(session/'bootstrap-events.jsonl').write_bytes(out)
            for n,value in claims.items():
                for suffix in ('claim','request'):(session/f'{n}.{suffix}').write_bytes(value)
            load=dict(schema='EU4SPYLOAD/1',purpose=b.PURPOSE,identity=i,plan_only=False,disposable_test_premise=True,held_identity_checked_after=True,
                strict_sp_verified=False,world_epoch_verified=False,production_ready=False,automatic_stage=False,send_supported=False,stage_request_written=False,
                bootstrap_sha256=b.sha(packet),bootstrap_bytes=len(packet),installation=dict(pid=i['pid'],dll=str((directory/b.DLL).resolve()),bridge_rva='0x7000',
                bridge_thread_exit_status='0x0',dll_unloaded=False,test_save_acknowledged=True,dll_module_base='0x7fff00000000',bridge_remote_address='0x7fff00007000'))
            path=directory/f'loader-{i["pid"]}-{i["creation"]}.json'
            path.write_bytes(b.canonical(load));result=r.inspect(directory,i,True)
            self.assertTrue(result['source_manifest_verified']);self.assertTrue(result['completed'])
            for key,value in (('plan_only',True),('held_identity_checked_after',1),('bootstrap_bytes',float(len(packet))),('stage_request_written',True)):
                bad=copy.deepcopy(load);bad[key]=value;path.write_bytes(b.canonical(bad))
                with self.subTest(key=key),self.assertRaises(ValueError):r.inspect(directory,i,True)
            for key,value in (('bridge_thread_exit_status','0x1'),('bridge_rva','0x7001'),('dll',str(directory/'other.dll')),('pid',True),('dll_module_base','0x1')):
                bad=copy.deepcopy(load);bad['installation'][key]=value;path.write_bytes(b.canonical(bad))
                with self.subTest(key=key),self.assertRaises(ValueError):r.inspect(directory,i,True)
            path.write_bytes(b.canonical(load));(session/'1.request').write_bytes(claims[1]+b'\n')
            with self.assertRaises(ValueError):r.inspect(directory,i,True)

    def test_installer_retry_only_before_patch(self):
        raw,out,i,c=envelope(synthetic());rows=[b.json_value(x) for x in out.splitlines()]
        failed=copy.deepcopy(rows[1]);failed['detail'].update(result=21,prefix_unchanged=True,retrying=True,failure_stage=41)
        rows.insert(1,failed);rows[2]['detail']['attempt']=2
        for n,x in enumerate(rows,1):x['ordinal']=n
        self.assertTrue(r.validate_stream(raw,pack(rows),i,c,True)['completed'])
        for key,value in (('result',24),('prefix_unchanged',False),('retrying',False),('resume_failures',1),('collected',513)):
            bad=copy.deepcopy(rows);bad[1]['detail'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_stream(raw,pack(bad),i,c,True)


if __name__=='__main__':unittest.main()
