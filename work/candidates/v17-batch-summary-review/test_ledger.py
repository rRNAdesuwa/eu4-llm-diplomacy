"""Full fake adapter journal, no CLI/process; native replay remains required."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

import ledger
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'work/candidates/v17-batch-cli-adapter-r2'))
import adapter
import test_adapter as fixture


def wire(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def census_checker(raw,command,scope):
    """Mock seam only: no synthetic marker is an accepted actual census."""
    marker=ledger.json_value(raw)
    ledger.require(set(marker)=={'synthetic_only','command','receipt'} and marker['synthetic_only'] is True,'Mock marker')
    ledger.require(ledger.same(marker['command'],command),'Mock census command')
    receipt=deepcopy(marker['receipt']);receipt['artifact_sha256']=ledger.digest(raw)
    return receipt


def make_fixture(reject=False):
    case=fixture.AdapterTests();case.setUp()
    try:
        snapshot=case.engine.snapshot
        def status(scope):
            value=snapshot(scope)
            # Explicitly synthetic native prefix boundaries. The production
            # replay gate is absent and must remain false in the result.
            value['evidence'].update(log_bytes=100,log_sha256='b'*64)
            return value
        case.engine.snapshot=status
        observe=case.engine.observer
        def census(command):
            receipt=observe(command)
            raw=wire({'synthetic_only':True,'command':command,'receipt':receipt})
            path=case.root/f"work/runtime/native1375-v17/batch-{command['run_id']}-{command['boundary']}-census.json"
            with path.open('xb') as stream:stream.write(raw)
            receipt['artifact_sha256']=ledger.digest(raw)
            return receipt
        case.adapter.observer=census
        if reject:
            def mutate(capture,entry):
                request=entry['request']
                if request['action']=='insult' and request['mode']=='legality_only':
                    entry['records'][-1].update(status=0,reason=9,preview_allowed=False,gate_called=False,
                        gate_allowed=False,command_destroyed_before_dispatch=False)
            case.engine.mutate=mutate
        summary=case.run_fake();assert summary['state']=='complete',summary
        summary=case.adapter.finish()
        scope=deepcopy(case.adapter.scope)
        journal=(case.adapter.run_dir/'journal.jsonl').read_bytes()
        files={str(p.relative_to(case.root)).replace('\\','/'):p.read_bytes()
               for p in (case.root/'work/runtime/native1375-v17').rglob('*') if p.is_file()}
        return scope,journal,summary,files
    finally:
        if not case.adapter.audit.closed:
            case.adapter.stop('test_cleanup');case.adapter.finish()
        for patch in reversed(case.patches):patch.stop()
        case.tmp.cleanup()


class LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.success=make_fixture();cls.rejected=make_fixture(True)

    def setUp(self):
        self.scope,self.journal,self.summary,self.files=deepcopy(self.success)

    def audit(self):
        inventory={name:{'bytes':len(raw),'sha256':ledger.digest(raw)} for name,raw in self.files.items()}
        return ledger.audit(self.scope,self.journal,self.summary,ledger.Artifacts(self.files,inventory),
                            adapter=adapter,census_checker=census_checker)

    def rows(self):return [ledger.json_value(line) for line in self.journal.splitlines()]
    def save(self,rows):self.journal=b''.join(wire(row) for row in rows)

    def test_full_36_sequence_and_only_two_censuses_not_native_or_effect_proof(self):
        result=self.audit()
        self.assertTrue(result['ledger_consistent']);self.assertEqual(result['matrix_rows'],36)
        self.assertEqual(result['legality_attempt_count'],36);self.assertEqual(result['native_dispatch_count'],34)
        self.assertEqual([x['boundary'] for x in result['censuses']],['initial','final'])
        self.assertTrue(result['native_source_replay_required'])
        for key in ('native_execution_verified','individual_effect_verified','request_causality_verified',
                    'strict_single_player_verified','world_epoch_verified','production_backend_registered',
                    'actual_completion_elapsed_verified'):self.assertIs(result[key],False)

    def test_known_legality_rejection_no_submit_or_sequence_hole(self):
        self.scope,self.journal,self.summary,self.files=deepcopy(self.rejected)
        result=self.audit();self.assertEqual(result['legality_attempt_count'],36)
        self.assertEqual(result['native_dispatch_count'],33)
        rows=[row for row in self.summary['rows'] if row['action']=='insult']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['outcome'],'known_rejection_no_submit')

    def test_terminal_summary_never_complete(self):
        self.summary['state']='terminal';self.summary['failure']='Read-only worker failed'
        with self.assertRaises(ValueError):self.audit()

    def test_missing_final_census_or_truncated_journal_rejected(self):
        path=next(p for p in self.files if p.endswith('-final-census.json'));del self.files[path]
        with self.assertRaises(ValueError):self.audit()
        self.setUp();self.journal=self.journal[:-1]
        with self.assertRaises(ValueError):self.audit()

    def test_summary_effect_or_foreign_helper_never_accepted(self):
        for key,value in [('individual_effect_verified',True),('still_running_helper_pids',[12]),('next_sequence',99.0)]:
            self.setUp();self.summary[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.audit()

    def test_duplicate_intent_no_retry(self):
        rows=self.rows();index=next(i for i,r in enumerate(rows) if r['event']=='resolved_intent')
        rows.insert(index+1,deepcopy(rows[index]));self.save(rows)
        with self.assertRaises(ValueError):self.audit()

    def test_wrong_target_even_rehashed_command_rejected(self):
        rows=self.rows();row=next(r for r in rows if r['event']=='resolved_intent' and r['command']['kind']=='pair')
        row['command']['target']='ENG';row['command_id']=adapter.batch.command_id(row['command']);self.save(rows)
        with self.assertRaises(ValueError):self.audit()

    def test_gap_or_boolean_sequence_rejected(self):
        for value in (3,True):
            self.setUp();rows=self.rows();row=next(r for r in rows if r['event']=='resolved_intent' and r['command']['kind']=='pair')
            row['command']['sequence']=value;row['command_id']=adapter.batch.command_id(row['command']);self.save(rows)
            with self.subTest(value=value),self.assertRaises(ValueError):self.audit()

    def test_capture_missing_or_wrong_hash_rejected(self):
        rows=self.rows();row=next(r for r in rows if r['event']=='publisher_capture');row['sha256']='0'*64;self.save(rows)
        with self.assertRaises(ValueError):self.audit()

    def test_normalized_receipt_cannot_override_wrong_ownership(self):
        rows=self.rows();row=next(r for r in rows if r['event']=='completed' and r['outcome']=='dispatched_not_effect_verified')
        row['evidence']['caller_container_consumed']=False;self.save(rows)
        with self.assertRaises(ValueError):self.audit()

    def test_native_status_cached_receipt_without_publisher_rejected(self):
        rows=self.rows();index=next(i for i,r in enumerate(rows) if r['event']=='publisher_capture');del rows[index];self.save(rows)
        with self.assertRaises(ValueError):self.audit()

    def test_wrong_census_receipt_sha_rejected(self):
        rows=self.rows();row=next(r for r in rows if r['event']=='completed');row['evidence']['artifact_sha256']='f'*64;self.save(rows)
        with self.assertRaises(ValueError):self.audit()

    def test_progress_and_final_are_exact_ordered_records(self):
        rows=self.rows();row=next(r for r in rows if r['event']=='batch_progress');row['completed_rows']=False;self.save(rows)
        with self.assertRaises(ValueError):self.audit()
        self.setUp();self.journal+=wire({'event':'status_snapshot','path':'x','sha256':'a'*64})
        with self.assertRaises(ValueError):self.audit()

    def test_artifact_descriptor_types_and_duplicate_json_reject(self):
        with self.assertRaises(ValueError):ledger.Artifacts({'a':b'x'},{'a':{'bytes':True,'sha256':ledger.digest(b'x')}})
        with self.assertRaises(ValueError):ledger.json_value(b'{"x":1,"x":2}')
        with self.assertRaises(ValueError):ledger.Artifacts({'../a':b'x'},{'../a':{'bytes':1,'sha256':ledger.digest(b'x')}})


if __name__=='__main__':unittest.main()
