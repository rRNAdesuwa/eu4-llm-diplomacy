"""Exact source-to-PE pins and version substitution boundaries; no process access."""
from copy import deepcopy
import hashlib,json,unittest
from pathlib import Path
import prepare,pin_contract
from test_candidate import HERE,ROOT,lab
import test_integration as integration

class ExactPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pe=pin_contract.game()
        cls.source=(HERE/'files/work/native/v17/test-acceptance-1375.cpp').read_text()
        cls.old=(ROOT/'work/native/v16/test-acceptance-1375.cpp').read_bytes()

    def test_all_actual_shared_code_data_and_header_pins_match(self):
        result=pin_contract.check(self.source,self.pe)
        self.assertEqual((result['code_pin_count'],result['code_bytes'],len(result['data_checks'])),(8,945,13))
        self.assertTrue(result['all_match']);self.assertTrue(all(result['header_checks'].values()))
        self.assertEqual(pin_contract.code_pins(self.source)[0][2],self.pe.bytes_at(0xe50180,648))

    def test_frozen_v16_rejects_and_original_bad_port_replacement_is_exact_origin(self):
        with self.assertRaises(ValueError):pin_contract.check(self.old.decode(),self.pe)
        result=pin_contract.check(self.old.decode(),self.pe,False)
        self.assertEqual(result['code_pins'][0]['differences'],[{'offset':162,'rva':'0xe50222','source':32,'game':16}])
        old15=(ROOT/'work/native/v15/test-acceptance-1375.cpp').read_text()
        corrupted=old15.replace('v15','v16').replace('V15','V16').replace('8771','8772')
        self.assertEqual(corrupted,self.old.decode())

    def test_native_is_not_subject_to_port_replacement_and_only_one_pin_byte_changes(self):
        normalized=prepare.renamed(self.old,'work/native/v16/test-acceptance-1375.cpp')
        self.assertEqual(normalized,self.old.decode().replace('v16','v17').replace('V16','V17'))
        self.assertEqual(normalized.replace('483bd87720488d0419','483bd87710488d0419'),self.source)
        oldpin=pin_contract.code_pins(normalized)[0][2];newpin=pin_contract.code_pins(self.source)[0][2]
        self.assertEqual([i for i,(a,b) in enumerate(zip(oldpin,newpin)) if a!=b],[162])
        self.assertEqual((oldpin[162],newpin[162]),(32,16))

    def test_only_two_exact_port_configuration_lines_change(self):
        decoys='hex="d8771048d8772048"\nid=8772\nlong_id=187722\nurl="http://127.0.0.1:8772/research/v16"\n'
        for source,(before,after) in prepare.PORT_DEFAULTS.items():
            text=before+'\n'+decoys
            wanted=after+'\n'+decoys.replace('v16','v17')
            self.assertEqual(prepare.renamed(text.encode(),source),wanted)
            with self.assertRaises(ValueError):prepare.renamed((before+'\n'+before).encode(),source)
            with self.assertRaises(ValueError):prepare.renamed(b'id=8772',source)
        self.assertEqual(prepare.renamed(decoys.encode(),'work/native/v16/random.cpp'),decoys.replace('v16','v17'))
        self.assertEqual(prepare.renamed(b'8771 8772 18772 87720'), '8771 8772 18772 87720')

    def test_mutated_source_pin_cannot_pass_exact_disk_check(self):
        for pattern,replacement in [('483bd87710488d0419','483bd87720488d0419'),('40534883ec20488bd941ffd0','40534883ec20488bd941ffd1')]:
            self.assertEqual(self.source.count(pattern),1)
            with self.subTest(pattern=pattern),self.assertRaises(ValueError):pin_contract.check(self.source.replace(pattern,replacement),self.pe)

    def test_shortened_or_missing_full_handler_pin_rejected(self):
        # The actual final handler literal must remain complete including error tails.
        for damaged in (self.source.replace('e86518bf00cc"','e86518bf00"'),self.source.replace('{0x6e9149, "0fb6b9d0240000"},','')):
            self.assertNotEqual(damaged,self.source)
            with self.assertRaises(ValueError):pin_contract.check(damaged,self.pe)

    def test_stopped_failure_complete_only_remains_failure_in_full_pipeline(self):
        p=ROOT/'work/runtime/native1375-v16/session-23700-01dd56bb81f60fc9/research-1375.jsonl'
        raw=p.read_bytes();self.assertEqual(len(raw),363136)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'b15cc8d0fafa4054bd91dde44da81744b36ce364cdfc609f76b713d24703457f')
        events=[json.loads(x) for x in raw.splitlines()]
        c=next(e['record'] for e in events if e['event']=='lab_native_record' and e.get('sequence')==4)
        self.assertEqual((c['reason'],c['stage']),(6,1));self.assertIs(c['native_invoked'],False)
        fixture=integration.Integration();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.full_window()
        fixture.events=[e for e in fixture.events if not(e.get('sequence')==2 and e['event']=='lab_native_record' and e['record']['event']=='test_acceptance_begin')]
        target=next(e for e in fixture.events if e.get('sequence')==2 and e['event']=='lab_native_record')
        target['record']=deepcopy(c);target['record']['thread_id']=fixture.f.metadata['window_thread']
        with self.assertRaisesRegex(ValueError,'exactly one begin and one complete'):fixture.read()

    def test_python_strict_reader_is_exact_version_rename_and_native_guard_unchanged(self):
        old=ROOT/'tools/verify_diplomacy_acceptance_v16.py';new=HERE/'files/tools/verify_diplomacy_acceptance_v17.py'
        self.assertEqual(new.read_text(),prepare.renamed(old.read_bytes(),'tools/verify_diplomacy_acceptance_v16.py'))
        self.assertEqual(self.source.split('bool image(',1)[1],self.old.decode().split('bool image(',1)[1])
        self.assertEqual((HERE/'native-core/test-acceptance-1375.cpp').read_text(),self.source)

if __name__=='__main__':unittest.main()
