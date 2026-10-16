"""Frozen actual frame schema plus strict synthetic v17 replay; no C++ execution."""
from copy import deepcopy
import hashlib
import json
import re
import tempfile
from pathlib import Path
import unittest
from test_candidate import HERE,ROOT,lab,verify
import test_integration as integration
import prepare

SUMMARY="work/runtime/native1375-v15/initial-closed-failure-summary-65368.json"
SUMMARY_SHA="2d667210b7d9960ff614cdc8056038c8106014b63a4c918a5a7f21a667705d00"


def actual_fixture():
    raw=prepare.bounded(ROOT/SUMMARY)
    assert hashlib.sha256(raw).hexdigest()==SUMMARY_SHA
    summary=json.loads(raw)
    descriptor=summary["input_artifacts"]["log"]
    raw=prepare.bounded(ROOT/descriptor["path"])
    assert len(raw)==descriptor["bytes"] and hashlib.sha256(raw).hexdigest()==descriptor["sha256"]
    events=[json.loads(line) for line in raw.splitlines()]
    first=next(e for e in events if e["event"]=="research_frame")
    metadata=json.loads(prepare.bounded(ROOT/summary["input_artifacts"]["metadata"]["path"]))
    return summary,metadata,events[0],first


class Initialization(unittest.TestCase):
    def test_real_stopped_failure_and_printf_schema_are_bound_without_invented_success(self):
        summary,metadata,hook,first=actual_fixture()
        self.assertEqual(summary["frame_count"],108)
        self.assertEqual((summary["phase_count"],summary["native_request_count"],summary["diplomatic_submit_count"]),(0,0,0))
        self.assertEqual((first["acceptance_action"],first["acceptance_target"]),("",""))
        source=(HERE/"files/work/native/v17/research-lab-1375.cpp").read_text()
        health=next(line for line in source.splitlines()
            if 'sprintf_s(line,' in line and '\\"event\\":\\"research_frame\\"' in line)
        self.assertEqual(set(re.findall(r'\\"(\w+)\\":',health)),set(first))
        self.assertIn("acceptance_window.action, acceptance_window.target",source)
        reader=verify.AcceptanceSession(metadata)
        with self.assertRaisesRegex(ValueError,"action binding"):
            reader.frame(first)

    def initial_read(self,normalized):
        _,metadata,hook,first=actual_fixture()
        metadata=deepcopy(metadata);metadata["purpose"]=lab.PURPOSE
        first=deepcopy(first)
        if normalized:first.update(acceptance_action="none",acceptance_target="none")
        # Only proposed initialization fields are changed. This is a synthetic
        # fixture derived from the stopped schema, never a v17 runtime claim.
        with tempfile.TemporaryDirectory() as folder:
            session=Path(folder)
            for name in ("session.json","install.claim"):
                (session/name).write_text(json.dumps(metadata),encoding="utf-8")
            (session/"research-1375.jsonl").write_text("\n".join(json.dumps(e) for e in (hook,first))+"\n",encoding="utf-8")
            return lab.read_evidence(session,metadata)

    def test_proposed_initialized_first_frame_passes_complete_reader_but_old_blank_rejected(self):
        with self.assertRaisesRegex(ValueError,"action binding"):self.initial_read(False)
        evidence=self.initial_read(True)
        self.assertEqual(evidence["acceptance_window"],verify.empty_window())
        self.assertEqual(evidence["last_sequence"],0)
        self.assertEqual(evidence["requests"],{})
        self.assertFalse(any(evidence["phases"].values()))

    def test_closed_historical_binding_is_retained_and_cannot_be_replaced_with_initial_none(self):
        fixture=integration.Integration();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.full_window();evidence=fixture.read()
        self.assertEqual(evidence["acceptance_window"]["state"],"closed")
        self.assertEqual(evidence["acceptance_window"]["action"],"offer_fleet_basing_rights")
        self.assertEqual(evidence["acceptance_window"]["on_sequence"],2)
        good=deepcopy(fixture.events[-1])
        for fields in ({"acceptance_action":"none","acceptance_target":"none"},
                       {"acceptance_action":"","acceptance_target":""},
                       {"acceptance_origin_sequence":0,"acceptance_submit_sequence":0,"acceptance_off_sequence":0}):
            fixture.events[-1]=good|fields
            with self.subTest(fields=fields),self.assertRaises(ValueError):fixture.read()

    def test_explicit_initialization_precedes_every_hook_log_and_single_attempt_guard(self):
        raw=(HERE/"files/work/native/v17/research-lab-bootstrap-1375.inc").read_text()
        start=raw.split('DWORD WINAPI BridgeStart(void*) {',1)[1]
        guard=start.index('InterlockedCompareExchange(&installed, 1, 0)')
        init=start.index('initialize_startup_window(acceptance_window)')
        self.assertLess(guard,init)
        for point in ('game_base =','create_private_session(', 'VirtualProtect(', 'durable_log('):
            self.assertLess(init,start.index(point))
        self.assertEqual(start.count('initialize_startup_window('),1)
        header=(HERE/"files/work/native/v17/lab-request-1375.h").read_text()
        helper=(HERE/"startup-window.inc").read_text()
        self.assertIn(helper,header)
        self.assertIn('if (!startup_window(w, true)) return false;',helper)
        self.assertIn('std::memset(w.action, 0, sizeof(w.action)); std::memcpy(w.action, "none", 5);',helper)
        self.assertIn('std::memset(w.target, 0, sizeof(w.target)); std::memcpy(w.target, "none", 5);',helper)
        self.assertIn('return startup_window(w, false);',helper)

    def test_python_acceptance_validator_is_exact_version_renamed_predecessor(self):
        old=(ROOT/prepare.PREDECESSOR/"files/tools/verify_diplomacy_acceptance_v16.py").read_bytes()
        new=(HERE/"files/tools/verify_diplomacy_acceptance_v17.py").read_bytes()
        self.assertEqual(new,prepare.renamed(old).encode())
        self.assertEqual(verify.empty_window()["action"],"none")
        self.assertEqual(verify.empty_window()["target"],"none")


if __name__=="__main__":unittest.main()
