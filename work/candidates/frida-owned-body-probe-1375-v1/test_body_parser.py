"""New whole-schema parser tests against actual producer JSON from pure Node VM.

No process inspection, Frida, native API or old test-suite execution.
"""
import copy
import json
from pathlib import Path
import unittest

import body_parser as parser

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE/'offline-r1'/'vm-corpus.json').read_text(encoding='utf-8'))


class BodyParserTests(unittest.TestCase):
    def sample(self, name='optional'):
        return copy.deepcopy(CORPUS['samples'][name])

    def check_unknown(self, payload, config=None):
        result = parser.evaluate(payload, config or CORPUS['config'])
        self.assertEqual(result['status'],'unknown',result)
        self.assertIs(result['raw_abi_postcondition_match'],False)
        self.assertIs(result['native_ready'],False)
        self.assertIs(result['requires_host_authentication'],True)
        return result

    def test_actual_vm_whole_payloads_and_non_authority(self):
        for name,reads,nbytes in (('optional',60,1322),('null',56,1290),('sixteenth',135,1922)):
            with self.subTest(name=name):
                result = parser.evaluate(self.sample(name),CORPUS['config'])
                self.assertEqual(result['status'],'raw_abi_postcondition_match',result)
                self.assertEqual((result['explicit_reads'],result['explicit_exact_bytes']),(reads,nbytes))
                self.assertEqual((result['native_game_calls_attempted'],result['native_game_calls_returned']),(1,1))
                self.assertEqual(result['script_owned_write_completed_bytes'],264)
                for flag in ('native_ready','native_entry_authenticated','lifetime_lease','atomic_snapshot',
                             'native_Cpp_object_verified','constructor_equivalence','full_native_lifecycle',
                             'AI_acceptance_verified','gameplay_effects_verified','host_identity_authenticated'):
                    self.assertIs(result[flag],False)

    def test_actual_vm_unknown_retains_call_counts_without_success(self):
        for name,returned in (('native_exception',0),('cleanup_unknown',1)):
            result = self.check_unknown(self.sample(name))
            self.assertEqual(result['reason'],'producer_unknown')
            self.assertEqual((result['native_game_calls_attempted'],result['native_game_calls_returned']),(1,returned))

    def test_old_schema_and_fake_old_zero_call_projection_rejected(self):
        row = self.sample(); row['schema']='EU4-FRIDA-ENTRY-OBSERVATION/1'; self.check_unknown(row)
        row = self.sample(); row['native_game_calls']=0; self.check_unknown(row)

    def test_fixed_identity_and_nonce(self):
        for key,value in (('observer_nonce','f'*32),('configured_creation','01dd5c075fcf8c27'),
                          ('configured_pid',80341),('module_base','0x0000000140000000')):
            row=self.sample(); row[key]=value; self.check_unknown(row)
        for key,value in (('pid',80341),('creation','01dd5c075fcf8c27'),('base','0x0000000140000000')):
            config=dict(CORPUS['config']); config[key]=value; self.check_unknown(self.sample(),config)

    def test_code_actual_source_and_every_scope_final_byte(self):
        for phase in ('before','after'):
            for index in range(3):
                row=self.sample(); scope=row['probe'][phase]['code'][index]
                scope['raw_hex']=scope['raw_hex'][:-2]+'00'; self.check_unknown(row)
                row=self.sample(); scope=row['probe'][phase]['code'][index]
                scope['address']=parser.h(int(scope['address'],16)+8); self.check_unknown(row)

    def test_slot_relocation_raw_and_actual_source(self):
        for phase in ('before','after'):
            row=self.sample(); slot=row['probe'][phase]['slot']
            slot['value']=parser.h(0x14008F450); slot['raw8_hex']=(0x14008F450).to_bytes(8,'little').hex()
            self.check_unknown(row)
            row=self.sample(); row['probe'][phase]['slot']['address']=parser.h(0x10000); self.check_unknown(row)

    def test_all_vector_qwords_and_unmodelled_owned_byte(self):
        for phase in ('before','after'):
            for offset in (0x50,0x58,0x60,0x68,0x70,0x78,0x80,0x88,0x90,0x3f):
                row=self.sample(); raw=bytearray.fromhex(row['probe'][phase]['owned']['A_hex'])
                raw[offset]=1; row['probe'][phase]['owned']['A_hex']=raw.hex(); self.check_unknown(row)
            row=self.sample(); raw=bytearray.fromhex(row['probe'][phase]['owned']['G_hex'])
            raw[95]=1; row['probe'][phase]['owned']['G_hex']=raw.hex(); self.check_unknown(row)

    def test_owned_span_alignment_overlap_and_size(self):
        for key,value in (('address','0x0000000000c00008'),('address','0xffff800000000000'),('size',151)):
            row=self.sample(); row['probe']['allocations']['A'][key]=value; self.check_unknown(row)
        row=self.sample(); row['probe']['allocations']['G']['address']='0x0000000000c00080'; self.check_unknown(row)

    def test_call_counter_options_strict_types_and_consistency(self):
        for value in (True,-1,2,1.0):
            row=self.sample(); row['probe']['call']['attempted']=value; self.check_unknown(row)
        row=self.sample(); row['native_game_calls_returned']=0; self.check_unknown(row)
        row=self.sample(); row['probe']['call']['options']['scheduling']='cooperative'; self.check_unknown(row)
        row=self.sample(); row['probe']['spent']=1; self.check_unknown(row)

    def test_read_and_owned_write_accounting(self):
        for field,value in (('reads',193),('requested_bytes',16385),('exact_bytes',1321)):
            row=self.sample(); row['counters'][field]=value; self.check_unknown(row)
        row=self.sample(); row['counters']['categories']['code_after']['bytes']=210; self.check_unknown(row)
        for field,value in (('attempts',True),('returned',3),('completed_bytes',256)):
            row=self.sample(); row['probe']['owned_writes'][field]=value; self.check_unknown(row)

    def test_entry_actual_sources_and_world_read_raw_not_only_equal_passes(self):
        row=self.sample()
        for phase in ('first','second'):
            row['observation'][phase]['slots'][0]['address']=parser.h(0x100018)
        self.check_unknown(row)
        row=self.sample()
        for phase in ('first','second'):
            row['observation'][phase]['reads'][0]['raw_hex']='00'*8
        self.check_unknown(row)
        row=self.sample(); row['observation']['source']='after_callback'; self.check_unknown(row)

    def test_authority_cleanup_bool_and_wire_bounds(self):
        for field in ('native_ready','lifetime_lease','creation_authenticated_in_script'):
            row=self.sample(); row[field]=True; self.check_unknown(row)
        row=self.sample(); row['cleanup']['listener_detach_returned']=1; self.check_unknown(row)
        row=self.sample(); row['reason']='x'*32769; self.check_unknown(row)
        row=self.sample(); row['probe']['before']['code']*=65; self.check_unknown(row)


if __name__=='__main__':
    unittest.main(verbosity=2)
