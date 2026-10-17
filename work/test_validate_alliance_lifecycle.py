"""Small contract fixtures for the offline lifecycle validator.

These fixtures are synthetic and never represent a game run.  They exercise
the conservative correlation rules: missing/drop evidence, address reuse,
full protocol flags, and one complete simulated lifecycle chain.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_alliance_lifecycle as validator


SESSION = "fixture-pid-creation"
ACTOR = 0x100000000000001
RECIPIENT = 0x100000000000002
SOURCE = 0x100000
TARGET = 0x200000
WRAPPER = 0x300000


def _shape(address: int, *, actor: int = ACTOR, recipient: int = RECIPIENT,
           state: int = 3, variant: int = 1) -> dict:
    return {
        "addr": hex(address),
        "readable": True,
        "matched": True,
        "handles_canonical": True,
        "tracked": True,
        "vtable_rva": "0x1c80720",
        "discriminator": 0x165,
        "actor10": actor,
        "mirror18": actor,
        "recipient20": recipient,
        "date28": 56459880,
        "date2c": 56459880,
        "envoy30": 0,
        "state34": state,
        "variant38": variant,
        "proposal3c": 0,
    }


def _lifecycle(kind: str, sequence: int, *, source: dict | None = None,
               target: dict | None = None, out_value: int | None = None,
               wrapper_action: int | None = None, origin: int = 0x12,
               protocol_sequence: int = 99, flags: int = 1) -> dict:
    event = {
        "event": "native_alliance_lifecycle",
        "session_id": SESSION,
        "kind": kind,
        "sequence": sequence,
        "source": source or {},
        "target": target or {},
        "wrapper_identity": True,
        "wrapper_readable": True,
        "origin48": origin,
        "seq4c": protocol_sequence,
        "rawflag4a": flags,
        "native_forward_count_by_hook_contract": 1,
        "native_return_observed": kind in {"clone", "wrapper", "destructor_return"},
        "native_result": "0x400000" if kind == "destructor_return" else "0x0",
        "synthetic": False,
    }
    if out_value is not None:
        event["out_value"] = hex(out_value)
    if wrapper_action is not None:
        event["wrapper_action"] = hex(wrapper_action)
    return event


def _valid_events(*, flags: int = 1) -> list[dict]:
    source = _shape(SOURCE)
    target = _shape(TARGET)
    return [
        _lifecycle("clone", 1, source=source, target=target),
        _lifecycle("wrapper", 2, source=source, target=target,
                   out_value=WRAPPER, wrapper_action=TARGET,
                   origin=0xFFFF, protocol_sequence=0, flags=0),
        _lifecycle("serialization_begin", 3, source=target, target=target,
                   out_value=WRAPPER, wrapper_action=TARGET, flags=flags),
        {
            "event": "native_alliance_command_entry_observed",
            "session_id": SESSION,
            "event_sequence": 1,
            "callback_sequence": 4,
            "readable": True,
            "command": hex(WRAPPER),
            "action": hex(TARGET),
            "origin": 0x12,
            "protocol_sequence": 99,
            "protocol_flags": flags,
            "source": _shape(TARGET),
            "actor_handle": ACTOR,
            "recipient_handle": RECIPIENT,
            "state_raw": 3,
            "variant": 1,
            "synthetic": False,
        },
        _lifecycle("destructor", 5, source=target),
        _lifecycle("destructor_return", 6, source=target),
        {
            "event": "native_alliance_lifecycle",
            "session_id": SESSION,
            "kind": "free",
            "address": hex(TARGET),
        },
    ]


def _write_fixture(root: Path, events: list[dict]) -> tuple[Path, Path, Path]:
    installation = root / "installation.json"
    manifest = root / "build-manifest.json"
    probe = root / "control-probe.jsonl"
    lifecycle_source = root / "alliance-lifecycle.inc"
    dll = root / "fixture.dll"
    lifecycle_source.write_text("fixture lifecycle source\n", encoding="utf-8")
    dll.write_bytes(b"fixture observer dll\n")
    source_sha = hashlib.sha256(lifecycle_source.read_bytes()).hexdigest()
    dll_sha = hashlib.sha256(dll.read_bytes()).hexdigest()
    installation.write_text(json.dumps({
        "pid": 1234,
        "creation_filetime": 123,
        "session_id": SESSION,
        "dll_sha256": dll_sha,
        "runtime_verified": True,
        "modules_after_install": [{"name": dll.name, "path": str(dll), "sha256": dll_sha}],
    }), encoding="utf-8")
    manifest.write_text(json.dumps({
        "version": 10,
        "compiled": True,
        "experiment_id": "alliance-lifecycle-fixture",
        "dll_sha256": dll_sha,
        "dll": str(dll),
        "sources": [{"name": "alliance-lifecycle.inc", "sha256": source_sha}],
    }), encoding="utf-8")
    with probe.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({
            "event": "alliance_lifecycle_observer_installed",
            "all_native_returns_preserved": True,
            "authority_enabled": False,
        }) + "\n")
        stream.write(json.dumps({
            "event": "alliance_serializer_observer_installed",
            "submit_receipt": False,
            "authority_enabled": False,
        }) + "\n")
        stream.write(json.dumps({
            "event": "diplomacy_observer_installed",
            "session_id": SESSION,
            "version": 10,
            "all_commands_forwarded": True,
        }) + "\n")
        for event in events:
            stream.write(json.dumps(event) + "\n")
    return installation, manifest, probe


class AllianceLifecycleValidatorTests(unittest.TestCase):
    def _validate(self, events: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            paths = _write_fixture(Path(directory), events)
            return validator.validate_files(*paths, fixture_only=True)

    def test_complete_simulated_fixture_is_correlated_but_marked_non_runtime(self) -> None:
        events = _valid_events()
        # Simulate independent frame flushes: callback ordinal 4 is written
        # before ordinal 3, and the destructor return is written before the
        # destructor.  Native callback order must still correlate the chain.
        events[2], events[3] = events[3], events[2]
        events[4], events[5] = events[5], events[4]
        report = self._validate(events)
        self.assertTrue(report["acceptance_gate"])
        self.assertEqual(report["status"], "accepted")
        self.assertTrue(report["fixture_only"])
        self.assertFalse(report["runtime_this_turn"])
        self.assertEqual(report["event_counts"]["complete_records"], 1)
        record = report["records"][0]
        self.assertEqual(record["serialization_stage"], "serialization_begin_observed")
        self.assertFalse(record["enqueue_verified"])
        self.assertEqual(record["protocol_key"], [0x12, 99, 1])
        self.assertTrue(record["protocol_assignment"]["transport_assignment_not_independently_observed"])
        self.assertEqual(record["verification_components"]["order"]["status"], "verified")
        self.assertTrue(report["callback_order"]["line_flush_disagrees"])
        self.assertEqual(record["destructor_return"]["status"], "verified")
        self.assertFalse(record["destructor_return"]["allocator_free_verified"])

    def test_missing_or_drop_evidence_cannot_complete(self) -> None:
        events = _valid_events()[:-2]  # no destructor/free, and no lifecycle teardown proof
        events.append({
            "event": "native_alliance_lifecycle_drop",
            "dropped": 1,
        })
        report = self._validate(events)
        self.assertFalse(report["acceptance_gate"])
        self.assertIn("PROBE_DROPPED_EVENTS", report["global_incomplete_reasons"])
        self.assertEqual(report["event_counts"]["complete_records"], 0)

    def test_address_reuse_never_crosses_destructor_generation(self) -> None:
        first = _valid_events()[:1] + _valid_events()[4:5]  # clone then destructor
        second = _valid_events()[0:1]
        second[0]["sequence"] = 7
        # Same address after the destructor is a new generation.  Its wrapper
        # is intentionally omitted, so the first clone cannot borrow a later
        # lifecycle event through the reused address.
        events = first + second
        report = self._validate(events)
        self.assertFalse(report["acceptance_gate"])
        self.assertEqual(len(report["records"]), 2)
        self.assertTrue(all(not record["complete"] for record in report["records"]))
        self.assertTrue(any(issue["code"] == "ADDRESS_REUSE_NEW_GENERATION"
                            for issue in report["issues"]))

    def test_same_sequence_with_wrong_flags_is_not_a_protocol_match(self) -> None:
        events = _valid_events(flags=1)
        entry = events[3]
        entry["protocol_flags"] = 2
        report = self._validate(events)
        self.assertFalse(report["acceptance_gate"])
        self.assertEqual(report["event_counts"]["complete_records"], 0)
        reasons = report["records"][0]["incomplete_reasons"]
        self.assertIn("generic_protocol_key_or_fingerprint_mismatch", reasons)
        same_tag = _valid_events()
        # Preserve the low tag bytes while changing the high slot/generation
        # bits in the complete entry source shape.
        same_tag[3]["source"] = _shape(
            TARGET,
            actor=ACTOR | (1 << 40),
            recipient=RECIPIENT | (1 << 40),
        )
        same_tag_report = self._validate(same_tag)
        self.assertFalse(same_tag_report["acceptance_gate"])
        self.assertEqual(same_tag_report["event_counts"]["complete_records"], 0)
        self.assertIn(
            "generic_protocol_key_or_fingerprint_mismatch",
            same_tag_report["records"][0]["incomplete_reasons"],
        )

    def test_version_mismatch_fixture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installation, manifest, probe = _write_fixture(root, _valid_events())
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["version"] = 9
            manifest.write_text(json.dumps(value), encoding="utf-8")
            report = validator.validate_files(installation, manifest, probe, fixture_only=True)
        self.assertFalse(report["acceptance_gate"])
        self.assertIn("BUILD_VERSION_BELOW_NATIVE_OBSERVER", report["global_incomplete_reasons"])

    def test_exclusive_output_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = _write_fixture(root, _valid_events())
            output = root / "report.json"
            report = validator.validate_files(*paths, fixture_only=True)
            validator.write_new_json(output, report)
            with self.assertRaises(FileExistsError):
                validator.write_new_json(output, report)


if __name__ == "__main__":
    unittest.main()
