"""Finite offline tests. Host metadata below is explicitly fabricated mock input, never game evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import projection as x

HERE = Path(__file__).resolve().parent
CAPTURES = HERE / 'mock-attempt-1'


def fixtures(name='mixed'):
    capture = x.read_records(CAPTURES / (name+'.jsonl'))
    # These are model fixtures, not observed game process/session/build facts.
    identity = dict(pid=777, creation='0000000000000001', session='1'*32, dll_sha256='2'*64,
                    manifest_sha256='3'*64, thread=capture[0]['thread'], world_cookie='0x200010000', raw_date=56456976)

    def common(frame, clock):
        return dict(identity, frame=frame, uptime_ms=clock, player_handle=x.model.FRA, target_handle=x.model.ENG,
                    paused=True, durable=True, no_send=True)

    def health(frame, clock, completed):
        return dict(origin='isolated_mock', kind='host', event=dict(common(frame, clock),
                    event='health', completed_stages=list(completed), owned_count=0))

    records = [health(1, 10000, [])]
    completed = []
    for raw in capture:
        require_keys = {'kind', 'frame', 'uptime_ms', 'thread', 'image_base', 'event' if raw['kind']=='core' else 'result'}
        if set(raw) != require_keys:
            raise ValueError('Actual mock capture shape differs')
        if raw['kind']=='core' and raw['event']['kind']==0:
            stage = x.STAGES[raw['event']['stage']]
            wire = x.p.encode(dict(purpose=x.p.PURPOSE, game_sha256=x.p.GAME_SHA256, profile=x.p.PROFILE,
                **{k: identity[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256')},
                sequence=raw['event']['stage'], expires=70000, stage=stage, actor='FRA', target='ENG', value=True, state=0, envoy=-1))
            records.append(dict(origin='isolated_mock', kind='host', event=dict(common(raw['frame'],raw['uptime_ms']),
                event='claim', wire_ascii=wire.decode('ascii'), wire_sha256=hashlib.sha256(wire).hexdigest(), claim_created=True)))
        envelope = dict(common(raw['frame'],raw['uptime_ms']), image_base=raw['image_base'])
        records.append(dict(origin='isolated_mock', kind=raw['kind'], envelope=envelope,
                            **{k: deepcopy(raw[k]) for k in ('event','result') if k in raw}))
        if raw['kind']=='result' and raw['result']['completed']:
            completed.append(x.STAGES[raw['result']['stage']])
            records.append(health(raw['frame']+1,raw['uptime_ms']+1,completed))
    return identity, records


def event_at(records, *, kind=2, step=1, stage=1, family=0):
    return next(r for r in records if r['kind']=='core' and r['event']['kind']==kind
                and r['event']['stage']==stage and r['event']['step']==step and r['event']['family']==family)


class ProjectionTests(unittest.TestCase):
    def test_actual_mock_three_runs_project_to_unchanged_model(self):
        for name, preview, gate in [('false',False,False),('mixed',True,False),('true',True,True)]:
            with self.subTest(name=name):
                identity, records=fixtures(name)
                raw,result=x.project(records,identity)
                self.assertTrue(result['proposed_model_completed'])
                self.assertEqual(result['output_events'],180)
                self.assertEqual(result['input_records'],171)
                self.assertEqual(result['completed_stages'],list(x.p.STAGES))
                self.assertTrue(all(v is preview for v in result['legality_results']['family_preview'].values()))
                self.assertTrue(all(v is gate for v in result['legality_results']['owned_command'].values()))
                again=x.model.replay(raw,identity)
                self.assertTrue(again['proposed_model_completed'])
                for key in ('send_supported','native_call_authorized','native_log_authenticated','actual_native_log_replayed',
                            'runtime_verified','production_ready','effects_verified','strict_single_player_verified','world_epoch_verified',
                            'actual_core_log_authenticated','host_evidence_authenticated'):
                    self.assertIs(result[key],False)
                self.assertTrue(result['synthetic_host_assertions_used'])

    def test_raw_core_alone_is_missing_host_evidence(self):
        identity,records=fixtures()
        raw=[r for r in records if r['kind']=='core']
        with self.assertRaisesRegex(ValueError,'without explicit health|Missing explicit'):
            x.project(raw,identity)
        self.assertFalse(x.availability()['raw_event_only_projection'])
        self.assertIn('country array count and target-overlord profile guard evidence',x.availability()['missing_host_contract'])

    def test_single_run_is_consistent_but_not_three_stage_complete(self):
        identity,records=fixtures()
        stop=next(i for i,r in enumerate(records) if r['kind']=='result')+2
        _,result=x.project(records[:stop],identity)
        self.assertFalse(result['proposed_model_completed'])
        self.assertEqual(result['completed_stages'],['lifecycle'])

    def test_missing_independent_post_stage_health(self):
        identity,records=fixtures()
        _,result=x.project(records[:-1],identity)
        self.assertTrue(result['terminal'])
        self.assertFalse(result['proposed_model_completed'])

    def test_missing_result_cannot_turn_callback_into_complete(self):
        identity,records=fixtures()
        records=[r for r in records if r['kind']!='result']
        with self.assertRaisesRegex(ValueError,'interrupted'):
            x.project(records,identity)

    def test_final_audit_failure_actual_mock_is_not_complete(self):
        identity,records=fixtures('final_audit_failure')
        self.assertTrue(any(r['kind']=='core' and r['event']['kind']==4 for r in records))
        self.assertFalse(next(r['result']['completed'] for r in records if r['kind']=='result'))
        with self.assertRaisesRegex(ValueError,'Terminal core diagnostic'):
            x.project(records,identity)

    def test_actual_exception_is_not_guessed_cleanup(self):
        identity,records=fixtures('factory_exception')
        last=next(r['result'] for r in records if r['kind']=='result')
        self.assertTrue(last['ownership_uncertain'])
        self.assertNotEqual(last['exception_code'],0)
        with self.assertRaisesRegex(ValueError,'Terminal core diagnostic'):
            x.project(records,identity)

    def test_actual_late_cleanup_model_allows_but_new_work_stops(self):
        identity,records=fixtures('late_cleanup')
        session=x.Projection(identity)
        for record in records:
            if record['kind']=='core' and record['event']['kind']==5:
                break
            session.feed(record)
        output=[json.loads(line) for line in session.output]
        late=[e for e in output if e.get('stage')=='family_preview' and e.get('step')=='destroy_original']
        self.assertEqual(len(late),2)
        self.assertEqual([e['uptime_ms'] for e in late],[70000,70000])
        self.assertEqual(session.model.pending['expires'],70000)
        self.assertEqual(session.model.objects,{})
        with self.assertRaisesRegex(ValueError,'Terminal core diagnostic'):
            session.feed(record)
        with self.assertRaisesRegex(ValueError,'stopped'):
            session.feed(records[-1])

    def test_intent_never_claims_actual_entry(self):
        for key in ('call_entered','call_returned','allowed_observed','allowed'):
            identity,records=fixtures();event_at(records,kind=1)['event'][key]=True
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'intent'):
                x.project(records,identity)

    def test_initialize_is_owned_write_not_engine_call(self):
        for key in ('call_entered','call_returned'):
            identity,records=fixtures();event_at(records,step=4,stage=2)['event'][key]=True
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'semantics'):
                x.project(records,identity)

    def test_all_fields_and_retained_snapshots_strict(self):
        cases=[('marker',357.0),('actor',True),('primary_date',43808760.0),('envoy',4294967295),
               ('state',False),('value',True),('flag39',False),('identifier',-1),('value',2),('marker',356)]
        for key,value in cases:
            identity,records=fixtures();event_at(records)['event']['original_fields'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):x.project(records,identity)
        for key in ('actor','controller','target','state','primary_date','secondary_date'):
            identity,records=fixtures();event_at(records,step=2)['event']['original_fields'][key]+=1
            with self.subTest(retained=key),self.assertRaises(ValueError):x.project(records,identity)

    def test_object_ids_owned_graph_and_destroy_flags(self):
        for key,value in [('clone_id',1),('clone_id',0),('clone_id',True),('clone_destroyed',True),('command_id',3)]:
            identity,records=fixtures();event_at(records,step=2)['event'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):x.project(records,identity)
        for key in ('command_destroyed','clone_destroyed'):
            identity,records=fixtures();event_at(records,step=9,stage=3)['event'][key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):x.project(records,identity)

    def test_result_crosscheck_rejects_cleanup_or_false_vector_tamper(self):
        for key,value in [('audit_complete',False),('completed',False),('freeze_session',True),('ownership_uncertain',True),
                          ('reason',1),('reads',True),('bytes_read',0),('runtime_verified',True),('send_supported',True)]:
            identity,records=fixtures();next(r for r in records if r['kind']=='result')['result'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):x.project(records,identity)
        for value in (True,1,None):
            identity,records=fixtures();next(r for r in records if r['kind']=='result')['result']['allowed'][0]=value
            with self.subTest(value=value),self.assertRaises(ValueError):x.project(records,identity)

    def test_missing_bad_duplicate_steps_and_family_order(self):
        for change in ('missing','duplicate','family','token','step','stage','origin'):
            identity,records=fixtures();selected=event_at(records,step=2);index=records.index(selected)
            if change=='missing':records.pop(index)
            elif change=='duplicate':records.insert(index,deepcopy(selected))
            elif change=='origin':selected['origin']='actual_game'
            else:selected['event'][change]+=1
            with self.subTest(change=change),self.assertRaises(ValueError):x.project(records,identity)

    def test_host_identity_and_selected_root_stamp_exact(self):
        for key,value in [('thread',True),('pid',778),('world_cookie','0x200010008'),('raw_date',56457000),
                          ('durable',False),('paused',False),('frame',2),('uptime_ms',9999),('image_base',0x100000008)]:
            identity,records=fixtures();event_at(records)['envelope'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):x.project(records,identity)
        for key in x.STAMP_KEYS:
            identity,records=fixtures();event_at(records)['event']['stamp'][key]+=8
            with self.subTest(stamp=key),self.assertRaises(ValueError):x.project(records,identity)

    def test_result_later_clock_does_not_allow_old_health(self):
        identity,records=fixtures();index=next(i for i,r in enumerate(records) if r['kind']=='result')
        records[index]['envelope']['uptime_ms']+=2
        with self.assertRaisesRegex(ValueError,'Host clock regressed'):
            x.project(records,identity)
        # Known return may be recorded later in the same frame, with later health.
        for r in records[index+1:]:
            if r['kind']=='host':r['event']['uptime_ms']+=2
            else:r['envelope']['uptime_ms']+=2
        _,result=x.project(records,identity)
        self.assertTrue(result['proposed_model_completed'])

    def test_claims_are_explicit_and_bound(self):
        for change in ('omit','expire','foreign','duplicate'):
            identity,records=fixtures();index=next(i for i,r in enumerate(records) if r['kind']=='host' and r['event']['event']=='claim')
            if change=='omit':records.pop(index)
            elif change=='duplicate':records.insert(index,deepcopy(records[index]))
            else:
                claim=records[index]['event'];wire=x.p.decode(claim['wire_ascii'].encode())
                if change=='expire':wire['expires']=10000
                else:wire['pid']+=1
                raw=x.p.encode(wire);claim['wire_ascii']=raw.decode();claim['wire_sha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(change=change),self.assertRaises(ValueError):x.project(records,identity)

    def test_raw_parser_bounded_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.jsonl'
            for raw in (b'{"a":1,"a":2}\n',b'{"a":NaN}\n',b'{}',b'x'*8193+b'\n',b'{}\n'*193,b'x'*(x.MAX_INPUT+1)):
                path.write_bytes(raw)
                with self.subTest(size=len(raw)),self.assertRaises(ValueError):x.read_records(path)

    def test_incremental_overflow_latches_after_complete_valid_prefix(self):
        identity,records=fixtures();session=x.Projection(identity)
        for record in records:session.feed(record)
        last=deepcopy(records[-1])
        for _ in range(21):
            last['event']['frame']+=1;last['event']['uptime_ms']+=1
            session.feed(deepcopy(last))
        self.assertEqual(session.source_index,192)
        last['event']['frame']+=1;last['event']['uptime_ms']+=1
        with self.assertRaisesRegex(ValueError,'count budget'):session.feed(last)
        self.assertTrue(session.closed)
        with self.assertRaisesRegex(ValueError,'terminal'):session.finish()
        with self.assertRaisesRegex(ValueError,'stopped'):session.feed(records[-1])

    def test_premature_finish_cannot_resume_same_instance(self):
        identity,records=fixtures();session=x.Projection(identity)
        for record in records[:4]:session.feed(record)
        with self.assertRaisesRegex(ValueError,'Incomplete'):session.finish()
        self.assertTrue(session.closed)
        for record in (records[4],records[-1]):
            with self.assertRaisesRegex(ValueError,'stopped'):session.feed(record)
        with self.assertRaisesRegex(ValueError,'terminal'):session.finish()

    def test_all_incremental_invalid_entry_shapes_are_terminal(self):
        identity,records=fixtures()
        for invalid in (None,[],{},dict(origin='actual_game'),dict(origin='isolated_mock',kind='unknown')):
            session=x.Projection(identity)
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):session.feed(invalid)
            self.assertTrue(session.closed)
            with self.assertRaises(ValueError):session.feed(records[0])
            with self.assertRaises(ValueError):session.finish()
        # A clean but incomplete EOF is terminal as well, even without an exception.
        session=x.Projection(identity);session.feed(records[0]);_,result=session.finish()
        self.assertTrue(result['terminal']);self.assertTrue(session.closed)
        with self.assertRaises(ValueError):session.feed(records[1])

    def test_output_budget_error_latches_eof(self):
        identity,records=fixtures();session=x.Projection(identity)
        for record in records:session.feed(record)
        # Private corruption seam: force the final serialization bound without
        # introducing a second public log format or weakening the original limit.
        session.output.append(b'x'*(x.model.MAX_LOG+1))
        with self.assertRaisesRegex(ValueError,'byte budget'):session.finish()
        self.assertTrue(session.closed)
        with self.assertRaisesRegex(ValueError,'stopped'):session.feed(records[-1])


if __name__=='__main__':
    unittest.main()
