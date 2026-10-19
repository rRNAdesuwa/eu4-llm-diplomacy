import json
from pathlib import Path
import unittest
from trace import decode_unsigned

class Dossier(unittest.TestCase):
    def test_compressed_integer_width_boundaries(self):
        for raw,value in [('00',0),('02',1),('fe',127),('0102',128),('030002',16384),
                          ('07000002',2097152),('0f00000010',268435456),('0fffffffff',4294967295)]:
            with self.subTest(raw=raw):self.assertEqual(decode_unsigned(bytes.fromhex(raw)),(value,len(bytes.fromhex(raw))))
    def test_truncation_rejected(self):
        for raw in ('','01','0300','070000','0f000000'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):decode_unsigned(bytes.fromhex(raw))
    def test_specific_unwind_and_cleanup_contract(self):
        r=json.loads((Path(__file__).parent/'report.json').read_text())
        callee=r['functions']['0x80b4c0'];caller=r['functions']['0x803270']
        self.assertEqual(callee['unwind']['flags'],2)
        self.assertFalse(callee['unwind']['chained'])
        self.assertEqual(sum(c.get('stack_delta',0) for c in callee['unwind']['codes']),-40)
        self.assertEqual(sum(c.get('stack_delta',0) for c in caller['unwind']['codes']),-1160)
        self.assertEqual(callee['fh4']['ip_states'],[{'ip_rva':'0x80b509','state':-1},{'ip_rva':'0x80b517','state':0}])
        e=callee['fh4']['unwind_entries'][0]
        self.assertEqual((e['type'],e['action_rva'],e['object_frame_offset']),(2,'0x956c0',48))
        self.assertEqual(len(caller['fh4']['unwind_entries']),146)
        self.assertEqual(len(caller['fh4']['ip_states']),89)
        self.assertEqual(r['continuation_unwind_chain'][0]['state'],31)
        self.assertNotIn(32,[x['state'] for x in r['continuation_unwind_chain']])
        self.assertEqual(caller['fh4']['unwind_entries'][32]['action_rva'],'0x1ae6890')
    def test_spans_are_only_analysis_and_bounded(self):
        r=json.loads((Path(__file__).parent/'report.json').read_text())
        self.assertLessEqual(r['limits']['decoded_bytes'],8192)
        self.assertEqual([x['span'] for x in r['candidate_spans']],[5,15,12,23])
        self.assertTrue(all(not x['approved_patch'] and not x['all_program_incoming_edges_proved'] for x in r['candidate_spans']))
        self.assertTrue(all(not x for x in r['scope'].values()))

if __name__=='__main__':unittest.main()
