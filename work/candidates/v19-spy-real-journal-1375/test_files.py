import tempfile
from pathlib import Path
import unittest
from fixed import wire
from files import inspect_files
from fixture import fixture,encode

class PassiveFiles(unittest.TestCase):
    def make(self,root):
        rows,outer,identity,claims=fixture(6);p=wire.session_path(root,identity);p.mkdir()
        (p/'raw-events.jsonl').write_bytes(encode(rows));(p/'bootstrap-events.jsonl').write_bytes(encode(outer))
        for name,raw in claims.items():(p/(name+'.claim')).write_bytes(raw);(p/(name+'.request')).write_bytes(raw)
        return p,identity
    def test_file_only_partial(self):
        with tempfile.TemporaryDirectory() as temp:
            p,i=self.make(temp);s=inspect_files(p,i)
            self.assertEqual(s['next_sequence'],4);self.assertFalse(s['build_loader_verified'])
    def test_request_diff_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p,i=self.make(temp);(p/'2.request').write_bytes(b'x')
            with self.assertRaises(ValueError):inspect_files(p,i)
    def test_claim_inventory_and_truncated_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            p,i=self.make(temp);(p/'raw-events.jsonl').write_bytes((p/'raw-events.jsonl').read_bytes()[:-1])
            with self.assertRaises(ValueError):inspect_files(p,i)

if __name__=='__main__':unittest.main()
