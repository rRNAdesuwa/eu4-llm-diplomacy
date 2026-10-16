"""Exercise materialization safeguards only in fresh temporary directories."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v12_contract_prepare', HERE / 'prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
REAL_ROOT, REAL_HERE, REAL_MANIFEST = prepare.ROOT, prepare.HERE, prepare.MANIFEST


class MaterializeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='eu4-v12-contract-offline-')
        self.root = Path(self.temp.name)
        self.here = self.root / 'candidate'
        self.here.mkdir()
        shutil.copyfile(REAL_HERE / 'contract-diagnostic.inc', self.here / 'contract-diagnostic.inc')
        manifest = json.loads(REAL_MANIFEST.read_bytes())
        names = list(manifest['source_sha256']) + [prepare.QUEUE_REPORT,
                  'work/runtime/native1375-v11/build.json',
                  'work/runtime/native1375-v11/eu4_pair_lab_v11_1375.dll']
        for name in names:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REAL_ROOT / name, dest)
        prepare.ROOT, prepare.HERE = self.root, self.here
        prepare.MANIFEST = self.root / 'work/runtime/native1375-v11/build.json'
        self.output = self.root / 'work/runtime/native1375-v12'
        self.native = self.root / 'work/native/v12'

    def tearDown(self):
        prepare.ROOT, prepare.HERE, prepare.MANIFEST = REAL_ROOT, REAL_HERE, REAL_MANIFEST
        self.temp.cleanup()

    def refuse_marker(self, name, directory=False):
        marker = self.output / name
        marker.parent.mkdir(parents=True, exist_ok=True)
        if directory:
            marker.mkdir()
        else:
            marker.write_bytes(b'preserve')
        with self.assertRaises(AssertionError):
            prepare.generate(materialize=True)
        self.assertFalse(self.native.exists())
        self.assertFalse((self.here / 'review.json').exists())
        if not directory:
            self.assertEqual(marker.read_bytes(), b'preserve')

    def test_existing_dll_refused(self):
        self.refuse_marker('eu4_pair_lab_v12_1375.dll')

    def test_existing_manifest_refused(self):
        self.refuse_marker('build.json')

    def test_existing_session_refused(self):
        self.refuse_marker('session-synthetic', True)

    def test_conflicting_late_file_does_not_partially_write(self):
        self.native.mkdir(parents=True)
        path = self.native / 'test-controls-1375.h'
        path.write_bytes(b'preserve different source')
        with self.assertRaises(AssertionError):
            prepare.generate(materialize=True)
        self.assertEqual(list(self.native.iterdir()), [path])
        self.assertFalse((self.root / 'work/native/test-fixture-v12-1375.h').exists())
        self.assertFalse((self.here / 'review.json').exists())

    def test_materialize_complete_and_idempotent_same_bytes(self):
        result = prepare.generate(materialize=True)
        self.assertEqual(result['native_sources'], 14)
        self.assertEqual(result['changed_native_sources'], 4)
        review = json.loads((self.here / 'review.json').read_bytes())
        for name, expected in review['native_source_sha256'].items():
            self.assertEqual(prepare.sha((self.root / name).read_bytes()), expected)
        prepare.generate(materialize=True)
        prepare.generate(check=True)


if __name__ == '__main__':
    unittest.main()
