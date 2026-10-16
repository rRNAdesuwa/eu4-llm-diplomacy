"""Finite mock protocol/state/ownership tests. Never calls native code."""
from copy import deepcopy
import hashlib
import json
import unittest
import protocol as p
import model as m


def identity():
    return dict(pid=1234,creation='01dd000000000001',session='a'*32,dll_sha256='b'*64,
        manifest_sha256='c'*64,thread=4321,world_cookie='0x123450000',raw_date=56456976)


def request(stage='lifecycle',expires=61000):
    ident=identity()
    return dict(purpose=p.PURPOSE,game_sha256=p.GAME_SHA256,profile=p.PROFILE,
        **{k:ident[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256')},
        sequence=p.STAGES.index(stage)+1,stage=stage,expires=expires,actor='FRA',target='ENG',value=True,state=0,envoy=-1)


def mock_log(preview=False,gate=True):
    ident=identity();rows=[];clock=1000;frame=1;counter=0
    def add(event,**kw):
        nonlocal clock
        row=dict(ident,event=event,ordinal=len(rows)+1,player_handle=m.FRA,target_handle=m.ENG,
            uptime_ms=clock,frame=frame,paused=True,durable=True,no_send=True,**kw)
        rows.append(row);clock+=1;return row
    add('health',completed_stages=[],owned_count=0)
    for seq,stage in enumerate(p.STAGES,1):
        wire=p.encode(request(stage,clock+60000))
        add('claim',wire_ascii=wire.decode(),wire_sha256=hashlib.sha256(wire).hexdigest(),claim_created=True)
        for family in p.FAMILIES:
            binding=dict(sequence=seq,stage=stage,family=family)
            add('case_begin',**binding);original=clone=command=None;fields=None
            for step in m.STEPS[stage]:
                add('step_begin',step=step,**binding)
                if step=='factory':
                    counter+=1;original=counter;fields=m.action_fields(family)
                    result=dict(object_id=original,fields=deepcopy(fields))
                elif step=='initialize':
                    fields=m.action_fields(family,ident['raw_date']);result=dict(object_id=original,fields=deepcopy(fields))
                elif step=='clone':
                    counter+=1;clone=counter;result=dict(object_id=clone,source_id=original,fields=deepcopy(fields),source_fields=deepcopy(fields))
                elif step=='wrap_owned':
                    counter+=1;command=counter;counter+=1;clone=counter
                    result=dict(source_id=original,source_fields=deepcopy(fields),command_id=command,clone_id=clone,
                        clone_fields=deepcopy(fields),command_size=88,command_vtable_rva='0x1c814b0')
                elif step=='full_preview':
                    result=dict(object_id=original,returned=True,allowed=preview,route='action_vtable_0x88',
                        function_rva=m.FAMILY_ROWS[p.FAMILIES.index(family)][3],string_output=None,mode=False)
                elif step=='command_gate':
                    result=dict(object_id=command,returned=True,allowed=gate,route='command_vtable_0x40',function_rva='0x4e8630')
                else:
                    obj={'destroy_original':original,'destroy_clone':clone,'destroy_command':command}[step]
                    result=dict(object_id=obj,returned=True)
                    if step=='destroy_command':result['owned_clone_id']=clone
                add('step_complete',step=step,exception_code=0,result=result,**binding)
            add('case_complete',owned_count=0,**binding)
        add('stage_complete',sequence=seq,stage=stage,case_count=5,owned_count=0)
        frame+=1;add('health',completed_stages=list(p.STAGES[:seq]),owned_count=0)
    return rows


def wire_log(rows):return b''.join((json.dumps(x,separators=(',',':'))+'\n').encode() for x in rows)


class CodecTests(unittest.TestCase):
    def test_three_canonical_stages_roundtrip(self):
        for stage in p.STAGES:self.assertEqual(p.decode(p.encode(request(stage))),request(stage))
    def test_exact_fixed_inputs_reject_extra_action_pointer_and_mutation(self):
        for key,value in [('action','corrupt_officials'),('rva','0x4e8630'),('actor','ENG'),('target','POR'),
                          ('value',False),('state',1),('envoy',0),('stage','submit'),('profile','arbitrary'),('purpose','restricted_pair_lab_1375_v17')]:
            with self.subTest(key=key):
                row=request();row[key]=value
                with self.assertRaises(ValueError):p.encode(row)
    def test_integer_bool_float_aliases_and_boundaries(self):
        for key in ('pid','sequence','expires','state','envoy'):
            for val in (True,False,1.0,None,'1'):
                with self.subTest(key=key,val=val):
                    row=request();row[key]=val
                    with self.assertRaises(ValueError):p.encode(row)
        for key,value in [('pid',2**32),('expires',2**64),('sequence',0)]:
            row=request();row[key]=value
            with self.assertRaises(ValueError):p.encode(row)
    def test_noncanonical_duplicate_reorder_crlf_and_oversize_rejected(self):
        raw=p.encode(request())
        cases=[raw.replace(b'pid=1234',b'pid=01234'),raw.replace(b'expires=61000',b'expires=+61000'),
               raw.replace(b'\n',b'\r\n'),raw+b'\n',raw[:-1],raw+b'x'*1024,raw.replace(b'actor=FRA',b'actor=FRA\x00'),
               raw.replace(b'actor=FRA\ntarget=ENG',b'target=ENG\nactor=FRA'),raw.replace(b'actor=FRA',b'actor=FRA\nactor=FRA')]
        for value in cases:
            with self.assertRaises(ValueError):p.decode(value)
    def test_claim_scope_strict_future_and_ttl(self):
        session={k:identity()[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256')}
        for delta,valid in ((0,False),(1,True),(60000,True),(60001,False)):
            raw=p.encode(request(expires=1000+delta))
            if valid:p.validate_claim_wire(raw,session,1000,'lifecycle')
            else:
                with self.assertRaises(ValueError):p.validate_claim_wire(raw,session,1000,'lifecycle')
        for key in session:
            other=deepcopy(session);other[key]=4321 if key=='pid' else 'd'*len(other[key])
            with self.assertRaises(ValueError):p.validate_claim_wire(p.encode(request()),other,1000,'lifecycle')


class ModelTests(unittest.TestCase):
    def setUp(self):self.rows=mock_log()
    def rejected(self):
        with self.assertRaises((ValueError,TypeError,KeyError)):m.replay(wire_log(self.rows),identity())
    def result(self,stage,step):
        return next(x['result'] for x in self.rows if x['event']=='step_complete' and x['stage']==stage and x['step']==step)
    def test_all_fifteen_cases_and_distinct_false_true_gates_no_permission(self):
        out=m.replay(wire_log(self.rows),identity())
        self.assertTrue(out['proposed_model_completed'])
        self.assertEqual(out['legality_results']['family_preview'],dict.fromkeys(p.FAMILIES,False))
        self.assertEqual(out['legality_results']['owned_command'],dict.fromkeys(p.FAMILIES,True))
        for key in ('send_supported','native_call_authorized','native_log_authenticated','actual_native_log_replayed','runtime_verified','production_ready','effects_verified'):
            self.assertIs(out[key],False)
        out=m.replay(wire_log(mock_log(True,False)),identity());self.assertTrue(out['proposed_model_completed'])
    def test_generic_preview_cannot_replace_full_family_preview(self):
        self.result('family_preview','full_preview')['route']='action_vtable_0x80';self.rejected()
    def test_command_gate_cannot_masquerade_as_full_preview(self):
        self.result('owned_command','command_gate')['function_rva']='0x4e9d00';self.rejected()
    def test_false_bool_legal_but_integer_alias_rejected(self):
        for stage,step in [('family_preview','full_preview'),('owned_command','command_gate')]:
            for val in (0,1,None,'false'):
                self.setUp();self.result(stage,step)['allowed']=val;self.rejected()
    def test_missing_duplicate_reordered_steps_and_case_family_rejected(self):
        self.rows.pop(4);self.rejected()
        self.setUp();self.rows[4]=deepcopy(self.rows[3]);self.rejected()
        self.setUp();self.rows[3]['step']='destroy_original';self.rejected()
        self.setUp();self.rows[2]['family']='sow_discontent';self.rejected()
    def test_full_world_thread_country_date_bound_on_every_event(self):
        for key,val in [('world_cookie','0x9999'),('thread',4322),('pid',1235),('creation','01dd000000000002'),
                        ('player_handle',m.ENG),('target_handle',m.FRA),('raw_date',56456976.0),('paused',False),('durable',False),('no_send',False)]:
            self.setUp();self.rows[20][key]=val;self.rejected()
    def test_lifecycle_default_and_clone_field_mapping_are_strict(self):
        for step,key,val in [('factory','state',True),('factory','date_primary',0),('clone','flag39',True),('clone','envoy',0)]:
            self.setUp();self.result('lifecycle',step)['fields'][key]=val;self.rejected()
    def test_clone_cannot_alias_source_and_owned_wrapper_must_be_distinct(self):
        result=self.result('lifecycle','clone');result['object_id']=result['source_id'];self.rejected()
        self.setUp();result=self.result('owned_command','wrap_owned');result['clone_id']=result['command_id'];self.rejected()
    def test_command_cleanup_cannot_hide_leaked_owned_clone(self):
        self.result('owned_command','destroy_command')['owned_clone_id']=127;self.rejected()
        self.setUp();self.result('owned_command','destroy_command')['returned']=False;self.rejected()
    def test_pending_stage_needs_strictly_later_clean_health(self):
        complete=next(i for i,x in enumerate(self.rows) if x['event']=='stage_complete')
        self.rows[complete+1]['frame']=self.rows[complete]['frame'];self.rejected()
        self.setUp();self.rows[complete+1]['owned_count']=False;self.rejected()
    def test_expired_fresh_work_rejected_but_destructor_return_can_cross_expiry(self):
        claim=self.rows[1];req=p.decode(claim['wire_ascii'].encode());req['expires']=self.rows[3]['uptime_ms']
        raw=p.encode(req);claim.update(wire_ascii=raw.decode(),wire_sha256=hashlib.sha256(raw).hexdigest());self.rejected()
        # Only model cleanup closure is demonstrated; no elapsed native time is asserted.
        self.setUp();session=m.Session(identity())
        claim=self.rows[1];req=p.decode(claim['wire_ascii'].encode());req['expires']=self.rows[6]['uptime_ms']
        raw=p.encode(req);claim.update(wire_ascii=raw.decode(),wire_sha256=hashlib.sha256(raw).hexdigest())
        for event in self.rows[:12]:session.feed(event)
        self.assertFalse(session.terminal)
        self.assertEqual(session.objects,{})
        with self.assertRaisesRegex(ValueError,'expired'):session.feed(self.rows[12])
    def test_exception_audit_failure_and_foreign_events_terminal_no_resume(self):
        session=m.Session(identity())
        for event in self.rows[:4]:session.feed(event)
        bad=deepcopy(self.rows[4]);bad['exception_code']=0xc0000005
        with self.assertRaises(ValueError):session.feed(bad)
        with self.assertRaisesRegex(ValueError,'terminal'):session.feed(self.rows[4])
        self.assertFalse(session.finish()['proposed_model_completed'])
    def test_incomplete_log_no_final_health_cannot_complete(self):
        out=m.replay(wire_log(self.rows[:-1]),identity());self.assertTrue(out['terminal'])
        self.assertFalse(out['proposed_model_completed'])
    def test_log_budgets_duplicate_keys_and_nonfinite_rejected(self):
        for raw in (b'x'*(m.MAX_LOG+1),b'{}\n'*257,b' '*8192+b'{}\n',b'{"event":"x","event":"x"}\n',b'{"x":NaN}\n'):
            with self.assertRaises((ValueError,TypeError,KeyError)):m.replay(raw,identity())


if __name__=='__main__':unittest.main()
