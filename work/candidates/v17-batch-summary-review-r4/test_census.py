"""All 22 raw selected observations are synthetic sparse-memory captures."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import reviewer as r
import census_replay as c
from bridge.tests import test_v7_diplomacy_observers as c7
from bridge.tests import test_pair_extension_v10_probe as c10
from bridge.tests import test_pair_extension_v11_probe as c11


def fixture():
    _,lab,_,modules=r.dependencies();census,core,extension,advanced,insult=modules
    t=r.load_source('batch_insult_memory_fixture',r.ROOT/'work/candidates/ordinary-insult-observer-1375/test_observer.py')
    command=dict(kind='observe',boundary='initial',pid=123,creation='01dd000000000001',world_cookie='0x200000',
                 raw_date=c10.DATE,last_sequence=1,run_id='synthetic',issued_uptime_ms=1000)
    reports={};selected={}
    for target,action in census.CORE:
        reports['core:'+target+':'+action]=c7.relation_report(c7.relation_memory(action,target),action,target)
    for target,action in census.EXTENSION:
        reports['extension:'+target+':'+action]=c10.report(c10.fixture(action,target=target),action,target=target)
    for target,action,flow in census.ADVANCED:
        reports['advanced:'+target+':'+action+':'+str(flow)]=c11.report(c11.fixture(action,target=target,flow=flow),action,target=target,flow=flow)
    player=reports['core:NAV:royal_marriage']['observation']['passes'][0]['player']
    for label,report in reports.items():
        report['source'].update(pid=command['pid'],process_creation_filetime=int(command['creation'],16))
        module=core if label.startswith('core:') else (extension if label.startswith('extension:') else advanced)
        selected[label]=module.validated_report(report)[1]
    report=t.Fixture(target='ENG').report()
    report['source']['expected_creation']=command['creation']
    for key in ('before','after'):report['source'][key].update(pid=command['pid'],creation_filetime=int(command['creation'],16))
    for value in report['observation']['passes']:
        value['snapshot']['identity'].update(world=command['world_cookie'],raw_date=command['raw_date'])
    report['observation']['state']=insult.inspect_snapshot(report['observation']['passes'][0]['snapshot'])
    reports['ordinary-insult:ENG']=report;selected['ordinary-insult:ENG']=report['observation']['state']
    live=dict(pid=command['pid'],creation=command['creation'],world_cookie=command['world_cookie'],
              raw_date=command['raw_date'],player_handle='0x0100007a00415246',acceptance_flag=0)
    diagnostic=dict(status='bounded_snapshot',country_identities_verified=True,player=player,game_pointer=command['world_cookie'],
                    current_raw_date=command['raw_date'],memory_bytes_requested=100,
                    snapshot_consistency=dict(globals_unchanged=True,player_unchanged=True,date_unchanged=True,atomic=False),
                    actor_diplomats=dict(entry_count=103,state_zero_count=100,
                        entries=[dict(state_raw_18=0 if i<100 else 2,state_zero_available_candidate=i<100) for i in range(103)]))
    frame=dict(frames=600,uptime_ms=1000,last_sequence=1,raw_date=command['raw_date'],world_cookie=command['world_cookie'],
               player_handle=live['player_handle'],thread=101,paused=True,native_speed_index=0,mailbox_ready=True,lease_active=False,
               acceptance_state='closed',acceptance_flag=0)
    value=dict(schema_version=1,kind='cross_date_selected_state_census',command=command,diagnostic_passes=[diagnostic,deepcopy(diagnostic)],
               reports=reports,selected=selected,identity_before_after=[live,deepcopy(live)],health_before_after=[frame,deepcopy(frame)],
               atomic_snapshot=False,individual_effect_verified=False,request_causality_verified=False,strict_single_player_verified=False,
               world_epoch_verified=False,production_ready=False,observed_uptime_ms=1100)
    return value,command,dict(plan=dict(window_thread=101)),modules,{r.ledger.canonical(frame)}


class CensusReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.seed=fixture()
    def setUp(self):
        value,command,scope,modules,frames=self.seed
        self.doc=deepcopy(value);self.command=deepcopy(command);self.scope=deepcopy(scope);self.modules=modules;self.frames=set(frames)
    def run_replay(self):return c.recompute(json.dumps(self.doc).encode(),self.command,self.scope,self.modules,self.frames)
    def test_all_22_raw_reports_and_resource_count_recomputed(self):
        result=self.run_replay();self.assertEqual(len(self.doc['reports']),22)
        self.assertEqual((result['diplomat_count'],result['idle_state_zero_count']),(103,100));self.assertFalse(result['individual_effect_verified'])
    def test_second_pass_float_date_rejected(self):
        self.doc['reports']['extension:POR:milaccess']['observation']['passes'][1]['current_raw_date']=float(self.command['raw_date'])
        with self.assertRaises(ValueError):self.run_replay()
    def test_stored_state_boolean_alias_rejected(self):
        self.doc['reports']['advanced:POR:giftaction:None']['observation']['state']['treasury_milli']['FRA']=100000.0
        with self.assertRaises(ValueError):self.run_replay()
    def test_final_selected_state_cannot_be_copied_from_elsewhere(self):
        self.doc['selected']['core:NAV:royal_marriage']['state']='active'
        with self.assertRaises(ValueError):self.run_replay()
    def test_missing_or_extra_selected_family_rejected(self):
        self.doc['reports'].pop('ordinary-insult:ENG')
        with self.assertRaises((ValueError,KeyError)):self.run_replay()
    def test_outer_full_player_and_subreport_creation_must_match(self):
        self.doc['identity_before_after'][0]['player_handle']='0x010000bc0056414e';self.doc['identity_before_after'][1]=deepcopy(self.doc['identity_before_after'][0])
        with self.assertRaises(ValueError):self.run_replay()
        self.setUp();self.doc['reports']['core:NAV:royal_marriage']['source']['process_creation_filetime']+=1
        with self.assertRaises(ValueError):self.run_replay()
    def test_raw_diagnostic_consistency_not_just_stored_count(self):
        for value in self.doc['diagnostic_passes']:value['snapshot_consistency']['globals_unchanged']=False
        with self.assertRaises(ValueError):self.run_replay()
    def test_census_frame_must_exist_in_stopped_log(self):
        self.frames.clear()
        with self.assertRaises(ValueError):self.run_replay()
    def test_heartbeat_stale_or_wrong_boundary_sequence_rejected(self):
        for value in self.doc['health_before_after']:value['last_sequence']=2
        self.frames={r.ledger.canonical(self.doc['health_before_after'][0])}
        with self.assertRaises(ValueError):self.run_replay()
    def test_no_game_access_on_recompute(self):
        with patch.object(self.modules[0].lab,'LiveLabProcess',side_effect=AssertionError('NO GAME')):
            self.assertTrue(self.run_replay()['two_pass_consistent'])


if __name__=='__main__':unittest.main()
