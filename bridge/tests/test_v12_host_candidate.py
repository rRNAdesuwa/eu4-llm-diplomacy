"""Isolated generation/fixture/version checks. No game, native build or server."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge import diplomacy_lab_http_v11 as prior_http
from bridge import diplomacy_lab_http_v12 as http
from work.native import lab_protocol_v11_1375 as prior
from work.native import lab_protocol_v12_1375 as lab
from tools import verify_diplomacy_lifecycle_v12 as lifecycle
from tools import verify_diplomacy_preview_v12 as preview

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "work/candidates/v12-host-review"
spec = importlib.util.spec_from_file_location("v12_candidate_generator", HERE / "prepare.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class V12CandidateTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        pins = json.loads((HERE / "frozen-templates.json").read_text(encoding="utf-8"))
        for name in generator.FROZEN_FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(generator.bounded(ROOT / name))
        pin_path = root / "pins.json"
        pin_path.write_text(json.dumps(pins), encoding="utf-8")
        return root, pin_path

    def test_version_isolation_exact_source_set_unchanged_wire_and_fixture(self):
        self.assertEqual(lab.PURPOSE, "restricted_pair_lab_1375_v12")
        self.assertEqual(lab.DLL_NAME, "eu4_pair_lab_v12_1375.dll")
        self.assertEqual(lab.OUTPUT, ROOT / "work/runtime/native1375-v12")
        self.assertEqual(lab.SOURCES, tuple(p.replace("v11", "v12") for p in prior.SOURCES))
        self.assertEqual(len(lab.SOURCES), 14)
        self.assertEqual(lab.ACTIONS, prior.ACTIONS)
        self.assertEqual(len(lab.ACTIONS), 36)
        self.assertEqual(lab.FIXED_RESEARCH_PARAMETERS, prior.FIXED_RESEARCH_PARAMETERS)
        self.assertEqual(lab.FIXTURE_PROFILE_SHA256, prior.FIXTURE_PROFILE_SHA256)
        self.assertEqual(lab.fixture_profile(), prior.fixture_profile())
        self.assertEqual(lab.TEST_SAVES, prior.TEST_SAVES)
        self.assertEqual(len(lifecycle.ACTIONS), 20)
        self.assertEqual(len(preview.EXPECTED), 72)
        record=dict(pid=1,creation="01dd568ed7034bcb",sequence=1,expires=9999,
                    operation="pair",mode="submit",action="send_gift",actor="FRA",target="POR",speed=0)
        self.assertEqual(lab.encode_request(record), prior.encode_request(record))
        self.assertEqual(http.PREFIX,"/research/v12")
        with self.assertRaises(prior_http.transport.ResearchError):
            prior_http.ResearchService(http.V12ResearchRuntime(1, "01dd568ed7034bcb"))

    def test_frozen_snapshot_and_generated_candidate_check_without_writes(self):
        with patch.object(lab,"LiveLabProcess",side_effect=AssertionError("No process access")):
            result=generator.generate(check=True)
        self.assertFalse(result["native_sources_generated"])
        self.assertFalse(result["build_performed"])
        self.assertEqual(len(result["generated_sha256"]),15)
        self.assertEqual(set(result["expected_native_sources"]),set(lab.SOURCES))

    def test_generator_rejects_built_dll_manifest_or_session_before_any_write(self):
        for sentinel in ("build.json","eu4_pair_lab_v12_1375.dll","session-123-test"):
            with self.subTest(sentinel=sentinel):
                root,pins=self.fixture()
                output=root/"work/runtime/native1375-v12"
                output.mkdir(parents=True)
                (output/sentinel).write_bytes(b"fixed sentinel")
                with self.assertRaisesRegex(ValueError,"built or used"):
                    generator.generate(root=root,pins_path=pins)
                self.assertFalse((root/"work/native/lab_protocol_v12_1375.py").exists())

    def test_generator_refuses_changed_frozen_source_even_without_build(self):
        root,pins=self.fixture()
        (root/generator.HOST_FILES[0]).write_bytes(b"changed frozen source")
        with self.assertRaisesRegex(ValueError,"frozen v11"):
            generator.generate(root=root,pins_path=pins)
        self.assertFalse((root/"work/native/lab_protocol_v12_1375.py").exists())

    def test_draft_generation_is_exact_and_cannot_repair_after_build(self):
        root,pins=self.fixture()
        generator.generate(root=root,pins_path=pins)
        self.assertEqual(generator.generate(check=True,root=root,pins_path=pins)["action_count"],36)
        generated=root/"tools/request_diplomacy_lab_v12.py"
        generated.write_bytes(b"intentional corrupt draft")
        with self.assertRaisesRegex(ValueError,"Generated v12"):
            generator.generate(check=True,root=root,pins_path=pins)
        (root/"work/runtime/native1375-v12").mkdir(parents=True)
        (root/"work/runtime/native1375-v12/build.json").write_bytes(b"locked")
        with self.assertRaisesRegex(ValueError,"built or used"):
            generator.generate(root=root,pins_path=pins)
        self.assertEqual(generated.read_bytes(),b"intentional corrupt draft")

    def test_missing_build_stays_not_ready_without_process_access(self):
        with tempfile.TemporaryDirectory() as output, patch.object(lab,"LiveLabProcess") as process:
            with self.assertRaises(OSError):
                lab.verify_build(output=Path(output))
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
