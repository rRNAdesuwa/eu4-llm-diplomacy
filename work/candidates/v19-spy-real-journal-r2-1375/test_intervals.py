"""Real sealed C++ mock events, explicit synthetic Host wrapping, no native run."""
from copy import deepcopy
import json
import unittest
from fixed import ROOT,wire
from fixture import fixture
from interval import Interval,BASE,EXT

CAPTURE=ROOT/'work/candidates/v19-spy-send-projection-1375/compile-final/build/capture.jsonl'

class IntervalPaths(unittest.TestCase):
    def test_actual_core_mock_normal_paths(self):
        records=[json.loads(x) for x in CAPTURE.read_bytes().splitlines()]
        for scenario,outcomes in [('dispatched',[5]*5),('preview_false',[2]*5),('gate_false',[3]*5),('mixed',[2,3,5,2,3])]:
            with self.subTest(scenario=scenario):
                rows=[r for r in records if r['scenario']==scenario];h=rows[0]['data'];identity=deepcopy(h['identity']);identity['creation']=f"{identity.pop('creation_filetime'):016x}"
                obs=fixture(6)[0][0]['observed'];v=Interval(identity,h['image_base'],h['thread'],obs,3,dict(expires=h['expires']))
                for record in rows:
                    kind,d=record['kind'],record['data']
                    if kind=='operation_begin':v.begin(d['frame'],d['uptime_ms'],4 if d['operation']==1 else 0)
                    elif kind in ('core_event','operation_result'):
                        row=dict(schema='EU4SPYSENDHOST/1',event='send_core' if kind=='core_event' else 'operation_result',ordinal=record['ordinal'],owner_frame=v.frame,uptime_ms=v.now,sequence=4,**identity,
                                 game_sha256=wire.GAME_SHA,owner_thread=h['thread'],mock_environment=False,image_base=h['image_base'],world=v.world,proof_source='same_controller_typed_run_result_and_later_health',
                                 third_stage_health_frame=3,host_state=v.host_state,host_failure=0,operation=v.op,expires=h['expires'],runtime_verified=False,effect_verified=False,strict_sp_verified=False,epoch_verified=False,production_ready=False)
                        if kind=='core_event':
                            e=deepcopy(d['event']);e['mock_resolver']=False;full=e['stamp'];e['stamp']={k:full[k] for k in BASE};e.update({k:full[k] for k in EXT});row['core']=e;row['uptime_ms']=e['uptime_ms']
                        else:row['result']=dict(deepcopy(d['result']),completed_outcomes=d['completed_outcomes'])
                        v.feed(row)
                        if kind=='operation_result':v.end()
                self.assertEqual(v.completed,5);self.assertEqual(v.outcomes,outcomes)
                self.assertTrue(all(x['entry_uptime'] is None for x in v.intervals))

if __name__=='__main__':unittest.main()
