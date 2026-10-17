"""Offline fixtures for the passive wrapper-protocol validator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_alliance_protocol as validator


SESSION = "fixture-protocol-r17c"
SERIAL_WRAPPER = 0x100000000
CLONE_TARGET_WRAPPER = 0x100001000
SERIAL_ACTION = 0x100002000
ENTRY_ACTION = 0x100003000


def _payload(address: int, *, state: int = 1, variant: int = 1) -> dict[str, object]:
    return {
        "addr": hex(address),
        "readable": True,
        "matched": True,
        "handles_canonical": True,
        "tracked": True,
        "vtable_rva": "0x1c80720",
        "discriminator": 357,
        "actor10": "0x10000b900534143",
        "mirror18": "0x10000b900534143",
        "recipient20": "0x10000bd00524f50",
        "date28": 56460720,
        "date2c": 56460720,
        "envoy30": 3,
        "state34": state,
        "variant38": variant,
        "proposal3c": 1,
    }


def _wrapper(address: int, action: int, origin: int, sequence: int,
             *, flags: int = 0, state: int = 1) -> dict[str, object]:
    return {
        "addr": hex(address),
        "identity": True,
        "readable": True,
        "origin": origin,
        "protocol_flags": flags,
        "protocol_sequence": sequence,
        "action": hex(action),
        "payload": _payload(action, state=state),
    }


def _field(callback: int, field_id: int, wrapper: dict[str, object]) -> dict[str, object]:
    return {
        "event": "native_wrapper_field_read_begin",
        "session_id": SESSION,
        "callback_sequence": callback,
        "thread": 1,
        "field_id": field_id,
        "context": "0x200000000",
        "input16_readable": True,
        "input16_hex": "41424300000000000000000000000000",
        "caller_return_rva": "0x15801e2",
        "source": wrapper,
        "native_forward_count_by_hook_contract": 1,
        "native_return_observed": False,
    }


def _serialization(callback: int, wrapper: dict[str, object]) -> dict[str, object]:
    return {
        "event": "native_alliance_lifecycle",
        "session_id": SESSION,
        "kind": "serialization_begin",
        "sequence": callback,
        "source_event_id": callback,
        "source": wrapper["payload"],
        "out_value": wrapper["addr"],
        "wrapper_action": wrapper["action"],
        "wrapper_identity": True,
        "wrapper_readable": True,
        "origin48": wrapper["origin"],
        "seq4c": wrapper["protocol_sequence"],
        "rawflag4a": wrapper["protocol_flags"],
        "native_forward_count_by_hook_contract": 1,
        "native_return_observed": False,
    }


def _clone(begin: int, end: int, source: dict[str, object], target: dict[str, object]) -> dict[str, object]:
    return {
        "event": "native_alliance_wrapper_clone",
        "session_id": SESSION,
        "begin_callback_sequence": begin,
        "callback_sequence": end,
        "thread": 1,
        "caller_return_rva": "0x15801e2",
        "opaque_context": "0x200000000",
        "native_result": target["addr"],
        "source": source,
        "target": target,
        "native_forward_count_by_hook_contract": 1,
        "native_return_observed": True,
        "authorization": "unknown",
        "submit_receipt": False,
    }


def _entry(callback: int, target: dict[str, object], *, sequence: int) -> dict[str, object]:
    payload = dict(target["payload"])
    return {
        "event": "native_alliance_command_entry_observed",
        "session_id": SESSION,
        "event_sequence": callback,
        "callback_sequence": callback,
        "protocol_sequence": sequence,
        "origin": 65535,
        "protocol_flags": 0,
        "command": target["addr"],
        "action": payload["addr"],
        "readable": True,
        "source": payload,
        "action_id": "offer_alliance",
        "decision_country": None,
        "business_result": "unknown",
        "complete": False,
    }


def _write_fixture(root: Path, *, same_sequence: bool = False,
                   drop: bool = False, missing_serialization: bool = False,
                   wrong_command: bool = False, wrong_action: bool = False,
                   wrong_payload: bool = False,
                   missing_native_result: bool = False) -> tuple[Path, Path, Path]:
    source_path = root / "protocol-source.inc"
    dll_path = root / "fixture.dll"
    source_path.write_text("fixture protocol source\n", encoding="utf-8")
    dll_path.write_bytes(b"fixture protocol dll\n")
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    dll_hash = hashlib.sha256(dll_path.read_bytes()).hexdigest()
    installation = {
        "session_id": SESSION,
        "pid": 60892,
        "creation_filetime": "fixture",
        "dll_sha256": dll_hash,
        "game_sha256": "fixture-game",
        "modules_after_install": [{"path": str(dll_path), "sha256": dll_hash}],
    }
    manifest = {
        "version": 10,
        "compiled": True,
        "experiment_id": "protocol-fixture",
        "dll": str(dll_path),
        "dll_sha256": dll_hash,
        "game_sha256": "fixture-game",
        "sources": [{"name": str(source_path), "sha256": source_hash}],
    }
    installation_path = root / "installation.json"
    manifest_path = root / "build-manifest.json"
    probe_path = root / "control-probe.jsonl"
    installation_path.write_text(json.dumps(installation), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    events: list[dict[str, object]] = [
        {"event": "alliance_lifecycle_observer_installed", "session_id": SESSION,
         "all_native_returns_preserved": True, "authority_enabled": False},
        {"event": "alliance_serializer_observer_installed", "session_id": SESSION,
         "submit_receipt": False, "authority_enabled": False},
        {"event": "alliance_field_reader_observer_installed", "session_id": SESSION,
         "native_arguments_preserved": True, "authority_enabled": False},
        {"event": "alliance_wrapper_protocol_observer_installed", "session_id": SESSION,
         "native_arguments_preserved": True, "authority_enabled": False},
        {"event": "diplomacy_observer_installed", "session_id": SESSION,
         "version": 10, "all_commands_forwarded": True},
    ]
    serial = _wrapper(SERIAL_WRAPPER, SERIAL_ACTION, 1933, 41)
    target = _wrapper(CLONE_TARGET_WRAPPER, ENTRY_ACTION, 65535, 0)
    events.append(_field(11, 0xC7, serial))
    events.append(_field(12, 0xCC, serial))
    events.append(_field(13, 0xDB, serial))
    events.append(_field(14, 0x293D, serial))
    if not missing_serialization:
        events.append(_serialization(10, serial))
    clone = _clone(15, 17, serial, target)
    if missing_native_result:
        clone.pop("native_result")
    events.append(clone)
    entry_sequence = 41 if same_sequence else 0
    entry = _entry(18, target, sequence=entry_sequence)
    if wrong_command:
        entry["command"] = hex(0x100004000)
    if wrong_action:
        wrong = hex(ENTRY_ACTION + 0x1000)
        entry["action"] = wrong
        entry["source"] = dict(entry["source"])
        entry["source"]["addr"] = wrong
    if wrong_payload:
        entry["source"] = dict(entry["source"])
        entry["source"]["state34"] = 99
    events.append(entry)
    if drop:
        events.append({"event": "native_wrapper_protocol_dropped", "field_reads": 1, "clones": 0})
    probe_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return installation_path, manifest_path, probe_path


class ValidateAllianceProtocolTests(unittest.TestCase):
    def _run(self, **options: object) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            paths = _write_fixture(Path(directory), **options)
            return validator.validate_files(*paths, fixture_only=True)

    def test_stage_chain_retains_clone_transform_without_authority(self) -> None:
        report = self._run()
        self.assertEqual(report["field_read"]["known_selector_count"], 4)
        self.assertEqual(report["wrapper_clone"]["total"], 1)
        self.assertEqual(report["stage_chains"]["candidate_count"], 1)
        chain = report["stage_chains"]["records"][0]
        self.assertTrue(chain["local_stage_chain_verified"])
        self.assertTrue(chain["payload"]["command_matches_clone_target"])
        self.assertTrue(chain["payload"]["native_result_matches_clone_target"])
        self.assertFalse(chain["protocol"]["continuity_verified"])
        self.assertTrue(chain["protocol"]["clone_origin_changed"])
        self.assertTrue(chain["protocol"]["clone_sequence_changed"])
        self.assertFalse(chain["authority"])
        self.assertFalse(chain["submit_verified"])
        self.assertFalse(report["acceptance_gate"])

    def test_sequence_only_match_is_candidate_not_authorization(self) -> None:
        report = self._run(same_sequence=True)
        chain = report["stage_chains"]["records"][0]
        self.assertTrue(chain["protocol"]["same_sequence_only_candidate"])
        self.assertIn("SEQUENCE_ONLY_CANDIDATE_NOT_AUTHORIZATION",
                      report["global_incomplete_reasons"])
        self.assertFalse(chain["complete"])

    def test_drop_and_missing_stage_remain_incomplete(self) -> None:
        report = self._run(drop=True, missing_serialization=True)
        self.assertEqual(report["stage_chains"]["candidate_count"], 1)
        self.assertIsNone(report["stage_chains"]["records"][0]["serialization"])
        self.assertFalse(report["stage_chains"]["records"][0]["local_stage_chain_verified"])
        self.assertIn("PROBE_DROPPED_EVENTS", report["global_incomplete_reasons"])
        self.assertIn("NO_SERIALIZATION_BEGIN", report["global_incomplete_reasons"])
        self.assertFalse(report["protocol_policy"]["authority_enabled"])
        self.assertEqual(report["command_entry"]["records"][0]["business_result"], "unknown")

    def test_same_action_different_command_is_not_local_causality(self) -> None:
        report = self._run(wrong_command=True)
        chain = report["stage_chains"]["records"][0]
        self.assertIsNone(chain["command_entry"])
        self.assertFalse(chain["payload"]["command_matches_clone_target"])
        self.assertFalse(chain["local_stage_chain_verified"])
        self.assertIn("COMMAND_WRAPPER_ADDRESS_UNMATCHED", chain["incomplete_reasons"])

    def test_same_wrapper_different_action_or_payload_is_not_local_causality(self) -> None:
        for option in ("wrong_action", "wrong_payload"):
            with self.subTest(option=option):
                report = self._run(**{option: True})
                chain = report["stage_chains"]["records"][0]
                self.assertIsNone(chain["command_entry"])
                self.assertFalse(chain["local_stage_chain_verified"])

    def test_missing_native_result_is_incomplete(self) -> None:
        report = self._run(missing_native_result=True)
        chain = report["stage_chains"]["records"][0]
        self.assertIsNotNone(chain["command_entry"])
        self.assertFalse(chain["payload"]["native_result_matches_clone_target"])
        self.assertFalse(chain["local_stage_chain_verified"])
        self.assertIn("CLONE_NATIVE_RESULT_TARGET_UNVERIFIED", chain["incomplete_reasons"])


if __name__ == "__main__":
    unittest.main()
