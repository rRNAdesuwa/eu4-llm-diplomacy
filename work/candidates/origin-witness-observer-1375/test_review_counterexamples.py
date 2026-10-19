"""Independent offline regression cases; no native calls or process access.

These assert the documented rejection contract. They intentionally failed on
the initial reducer where candidate-wide booleans could substitute for spans.
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from observer import Observer, SITES, replay
from test_observer import trace, observe, FRONT, HOLDER, SERVER, CTX


def resequence(rows):
    for number, row in enumerate(rows, 1):
        row.update(seq=number, uptime_ms=1000+number)
    return rows


class CounterexampleTests(unittest.TestCase):
    def test_publication_cannot_borrow_server_from_different_frontend_update_span(self):
        rows = trace()
        # Constructor/copy proof belongs to update span6, but publication to10.
        rows[16]['parent'] = 10
        rows[18]['span'] = 10
        split = [dict(event='exit',thread=7,name='frontend_update',span=6,normal_return=True),
                 dict(event='enter',thread=7,name='frontend_update',span=10,parent=0,
                      rva=SITES['frontend_update'],frontend=FRONT)]
        result = observe(resequence(rows[:16]+split+rows[16:])).status()
        self.assertFalse(result['origin_sequence_observed'])
        self.assertFalse(result['production_ready'])

    def test_second_constructor_cannot_borrow_previous_constructor_copy_proof(self):
        rows = trace()
        replacement = SERVER+0x10000
        second_enter = copy.deepcopy(rows[12])
        second_enter.update(span=10,object=replacement)
        second_exit = copy.deepcopy(rows[15])
        second_exit.update(span=10,object=replacement)
        rows[16]['server'] = replacement
        rows[17]['holder_server'] = replacement
        rows[-1]['server'] = replacement
        # No config_copy event exists inside the second constructor instance.
        result = observe(resequence(rows[:16]+[second_enter,second_exit]+rows[16:])).status()
        self.assertFalse(result['origin_sequence_observed'])
        self.assertFalse(result['production_ready'])

    def test_finished_replay_with_missing_opaque_return_cannot_report_origin(self):
        rows = trace()
        rows.append(dict(event='enter',thread=7,name='opaque_dispatch',span=10,parent=0,
                         context=CTX,rva=SITES['opaque_dispatch']))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'truncated-scope.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in resequence(rows)),encoding='utf-8')
            result = replay(path)
        self.assertFalse(result['origin_sequence_observed'])
        self.assertFalse(result['production_ready'])

    def test_identity_numbers_cannot_accept_bool_or_float_aliases(self):
        for index,field,value in ((-1,'same_generation',True),(13,'thread',7.0),(2,'parent',True),
                                  (10,'span',True)):
            with self.subTest(field=field):
                rows = trace();rows[index][field] = value
                self.assertFalse(observe(rows).status()['origin_sequence_observed'])

    def test_line_bound_is_applied_before_reading_an_entire_line(self):
        class BoundedReader(io.BytesIO):
            def readline(self, size=-1):
                if not 0 < size <= 16385:
                    raise AssertionError('A line was read without the declared bounded read size')
                return super().readline(size)

            def __next__(self):
                raw = self.readline()
                if not raw:
                    raise StopIteration
                return raw

        with patch.object(Path,'open',return_value=BoundedReader(b' ' * 16385+b'\n')):
            with self.assertRaisesRegex(ValueError,'trace_bound'):
                replay(Path('synthetic-overlong-trace.jsonl'))


if __name__ == '__main__':
    unittest.main()
