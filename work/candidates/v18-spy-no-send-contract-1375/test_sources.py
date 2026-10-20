"""Small static projection checks; no PE scans or process/native calls."""
import ast
import hashlib
import json
from pathlib import Path
import unittest
import model
import prepare
import protocol

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


class SourceContractTests(unittest.TestCase):
    def test_family_projection_exactly_matches_pinned_static_report(self):
        pins=json.loads(prepare.bounded(HERE/'source-pins.json',128*1024))
        path='work/candidates/spy-action-contracts-1375/report.json'
        raw=prepare.bounded(ROOT/path,2*1024*1024)
        self.assertEqual(pins[path],dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        report=json.loads(raw);self.assertEqual(report['game_sha256'].lower(),protocol.GAME_SHA256)
        rows=report['families'];self.assertEqual([x['name'] for x in rows],list(protocol.FAMILIES))
        for expected,row in zip(model.FAMILY_ROWS,rows):
            self.assertEqual(expected,(row['name'],row['token'],row['vtable_rva'],row['slots']['0x88']))
            self.assertEqual(model.action_fields(row['name'])['date_primary'],row['factory_date_sentinel'])
            self.assertEqual(row['size'],64);self.assertIs(row['factory_value'],True)
            self.assertEqual(row['factory_envoy'],-1);self.assertEqual(row['factory_state'],0)
            self.assertIn('destination+0x2c=source+0x28',row['clone_special'])
            self.assertIn('destination+0x39=0',row['clone_special'])
        self.assertEqual([row['initialization_normal_caller_verified'] for row in rows],[True,False,False,False,False])
    def test_contract_and_descriptor_do_not_create_execution_authority(self):
        contract=json.loads(prepare.bounded(HERE/'log-contract.json',64*1024))
        self.assertEqual(contract['event_extra_fields'],{k:sorted(v) for k,v in model.EXTRA.items()})
        self.assertEqual(contract['stage_steps'],{k:list(v) for k,v in model.STEPS.items()})
        self.assertFalse(contract['native_schema_exists']);self.assertFalse(contract['native_authentication'])
        desc=protocol.descriptor()
        for key in ('deployed','native_host_implemented','native_log_replay_implemented','publisher_implemented',
                    'native_call_authorized','send_supported','runtime_verified','production_ready'):
            self.assertIs(desc[key],False)
        plan=json.loads(prepare.bounded(HERE/'plan.json',64*1024))
        self.assertEqual(plan['protocol'],desc);self.assertFalse(plan['implementation']['cpp_authorization'])
    def test_pure_runtime_modules_have_no_dynamic_import_or_os_surface(self):
        allowed={'re','copy','hashlib','json','protocol'}
        for filename in ('protocol.py','model.py'):
            tree=ast.parse(prepare.bounded(HERE/filename,64*1024))
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):self.assertTrue({n.name for n in node.names}<=allowed)
                if isinstance(node,ast.ImportFrom):self.assertIn(node.module,allowed)
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                    self.assertNotIn(node.func.id,{'exec','eval','compile','__import__','open'})
    def test_clone_special_contract_is_not_whole_object_equality(self):
        session=model.Session(dict(pid=1,creation='0000000000000001',session='a'*32,dll_sha256='b'*64,
            manifest_sha256='c'*64,thread=2,world_cookie='0x1',raw_date=56456976))
        session.original=session.allocate(1,'action')
        session.fields=dict(model.action_fields('corrupt_officials'),date_primary=20,date_secondary=30,flag39=True)
        result=dict(object_id=2,source_id=1,source_fields=dict(session.fields),
            fields=dict(session.fields,date_secondary=20,flag39=False))
        session.step_result('clone',result,'corrupt_officials')
        self.assertEqual(session.clone,2)


if __name__=='__main__':unittest.main()
