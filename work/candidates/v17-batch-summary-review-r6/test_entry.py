"""Explicit-file entry boundaries. No live case, process or publisher."""
from copy import deepcopy
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import reviewer as r


class EntryBoundaryTests(unittest.TestCase):
    def test_unfinalized_template_cannot_run_dependencies_or_game(self):
        with patch.object(r,'dependencies',side_effect=AssertionError('must reject before imports')):
            with self.assertRaisesRegex(ValueError,'finalized'):r.review(r.template())
    def test_no_public_checker_or_native_callback_parameter(self):
        self.assertEqual(set(inspect.signature(r.review).parameters),{'case','root'})
    def test_canonical_paths_reject_traversal_and_aliases(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('../x','/x','C:/x','a/../x','a\\b','a//b'):
                with self.subTest(name=name),self.assertRaises(ValueError):r.safe_path(Path(d),name)
    def test_explicit_stopped_inventory_cannot_hide_request_or_extra_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);scope={'plan':{'pid':123,'creation':'0000000000000001'}}
            base='work/runtime/native1375-v17/session-123-0000000000000001';path=root/base;path.mkdir(parents=True)
            names=['session.json','install.claim','research-1375.jsonl']
            for phase in ('lifecycle','owned-peace-lifecycle','preview','command'):
                names += ['phase-'+phase+'.claim','phase-'+phase+'.claim.host-intent']
            files={n:base+'/'+n for n in names};raw={p:b'x' for p in files.values()}
            for n in names:(path/n).write_bytes(b'x')
            a=r.ledger.Artifacts(raw,{p:{'bytes':1,'sha256':r.ledger.digest(b'x')} for p in raw})
            r.session_inventory(a,files,scope,root)
            (path/'00000000000000000002.request').write_bytes(b'remaining')
            with self.assertRaisesRegex(ValueError,'hides'):r.session_inventory(a,files,scope,root)
    def test_read_bound_applies_to_bytes_not_only_stat(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'file';p.write_bytes(b'12345')
            with self.assertRaises(ValueError):r.bounded(p,4)
    def test_recorded_40s_completion_cannot_be_enabled_by_case_flag(self):
        case=r.template();case['finalized']=True;case['actual_completion_elapsed_verified']=True
        with patch.object(r,'dependencies',side_effect=AssertionError('no imports')):
            with self.assertRaises(ValueError):r.review(case)
    def test_cached_foreign_module_rejected_before_native_review(self):
        adapter,lab,experiment,modules=r.dependencies()
        with patch.object(lab,'__file__',str(r.ROOT/'wrong.py')):
            with self.assertRaisesRegex(ValueError,'Foreign formal module'):r.dependencies()


if __name__=='__main__':unittest.main()
