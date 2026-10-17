"""Small offline fixtures for :mod:`validate_alliance_field_reads`.

The fixtures exercise the validator's evidence boundaries; they never open a
game process or load the bridge/native implementation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_alliance_field_reads as validator


SESSION = "fixture-session-r16c"
ACTION = 0x100000000
ENTRY_ACTION = 0x100001000
CONTEXT = "0x200000000"
ACTOR = "0x10000b900534143"
RECIPIENT = "0x10000bd00524f50"
FIELD_IDS = list(validator.EXPECTED_FIELD_IDS)


def _shape(address: int, *, dummy: bool = False,
           matched: bool = True, canonical: bool = True) -> dict[str, object]:
    handle = "---" if dummy else ACTOR
    return {
        "addr": hex(address),
        "readable": True,
        "matched": matched,
        "handles_canonical": canonical,
        "tracked": True,
        "vtable_rva": hex(validator.ALLIANCE_VTABLE_RVA),
        "discriminator": 357,
        "actor10": handle,
        "mirror18": handle,
        "recipient20": "---" if dummy else RECIPIENT,
        "date28": 56460720,
        "date2c": 56460720,
        "envoy30": 3,
        "state34": 1,
        "variant38": 1,
        "proposal3c": 1,
    }


def _field_event(callback: int, field_id: int, *, action: int = ACTION,
                 context: str = CONTEXT, source: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "event": "native_alliance_field_read_begin",
        "session_id": SESSION,
        "callback_sequence": callback,
        "thread": 1,
        "field_id": field_id,
        "context": context,
        "context_word_readable": True,
        "input16_readable": True,
        "input16_hex": "41424300",
        "caller_return_rva": "0x170697b",
        "source": source if source is not None else _shape(action),
        "native_forward_count_by_hook_contract": 1,
    }


def _entry(callback: int, *, action: int = ENTRY_ACTION,
           source: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "event": "native_alliance_command_entry_observed",
        "session_id": SESSION,
        "event_sequence": callback,
        "callback_sequence": callback,
        "protocol_sequence": 781,
        "origin": 65535,
        "protocol_flags": 0,
        "command": hex(action + 0x400),
        "action": hex(action),
        "readable": True,
        "source": source if source is not None else _shape(action),
        "action_id": "offer_alliance",
        "actor_field": "CAS",
        "recipient_field": "POR",
        "decision_country": None,
        "business_result": "unknown",
        "complete": False,
    }


def _clone(sequence: int, source: int = ACTION, target: int = ENTRY_ACTION,
           *, target_shape: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "event": "native_alliance_lifecycle",
        "session_id": SESSION,
        "kind": "clone",
        "sequence": sequence,
        "source_event_id": sequence,
        "target_event_id": sequence,
        "source": _shape(source),
        "target": target_shape if target_shape is not None else _shape(target),
        "native_forward_count_by_hook_contract": 1,
        "native_return_observed": True,
    }


def _direct(callback: int, caller: int = 0x2AAB24) -> dict[str, object]:
    return {
        "event": "native_direct_break_entry",
        "session_id": SESSION,
        "callback_sequence": callback,
        "caller_return_rva": hex(caller),
        "direct_call_bytes_verified": True,
        "owner": "CAS",
        "owner_handle": ACTOR,
        "input_handle": RECIPIENT,
        "owner_readable": True,
        "owner_is_country": True,
        "input_canonical": True,
        "native_flag": 1,
        "date_readable": True,
        "date_raw": 56460720,
    }


def _write_fixture(root: Path, *, alias_variant: bool = False,
                   drop: bool = False, with_chain: bool = True,
                   unknown_direct: bool = False,
                   layout_mismatch: bool = False) -> tuple[Path, Path, Path]:
    source_path = root / "fixture-source.inc"
    dll_path = root / "fixture.dll"
    source_path.write_text("fixture source\n", encoding="utf-8")
    dll_path.write_bytes(b"fixture dll\n")
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    dll_hash = hashlib.sha256(dll_path.read_bytes()).hexdigest()
    installation = {
        "session_id": SESSION,
        "pid": 6588,
        "creation_filetime": "fixture",
        "game_sha256": validator.EXPECTED_GAME_SHA256,
        "dll_sha256": dll_hash,
        "experiment_id": "alliance-query-fixture",
        "installation_returncode": 0,
        "modules_after_install": [{"name": "fixture.dll", "path": str(dll_path), "sha256": dll_hash}],
    }
    manifest = {
        "version": validator.EXPECTED_MANIFEST_VERSION,
        "compiled": True,
        "experiment_id": "alliance-query-fixture",
        "game_sha256": validator.EXPECTED_GAME_SHA256,
        "dll": str(dll_path),
        "dll_sha256": dll_hash,
        "sources": [{"name": str(source_path), "sha256": source_hash}],
    }
    installation_path = root / "installation.json"
    manifest_path = root / "build-manifest.json"
    probe_path = root / "control-probe.jsonl"
    installation_path.write_text(json.dumps(installation), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    events: list[dict[str, object]] = [
        {"event": name, "session_id": SESSION}
        for name in sorted(validator.REQUIRED_ACKS)
    ]
    for callback, field_id in enumerate(FIELD_IDS, 1):
        source = _shape(ACTION)
        if callback == 1:
            source = _shape(ACTION, dummy=True)
        if field_id == 0x2D87:
            source = _shape(ACTION, matched=False, canonical=False)
            source["actor10"] = ACTOR
            source["mirror18"] = "---"
            source["recipient20"] = "---"
        if alias_variant and field_id == 0x3EC:
            field_id = 0xEC3
        events.append(_field_event(callback, field_id, source=source))
    if with_chain:
        clone_target = _shape(ENTRY_ACTION)
        if layout_mismatch:
            clone_target["date2c"] = 56460719
        events.append(_clone(10, target_shape=clone_target))
    events.append(_entry(11))
    events.append(_direct(12, caller=0x2AAB25 if unknown_direct else 0x2AAB24))
    if drop:
        events.append({"event": "native_alliance_field_read_drop", "session_id": SESSION, "dropped": 1})
    probe_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return installation_path, manifest_path, probe_path


class ValidateAllianceFieldReadsTests(unittest.TestCase):
    def _run(self, **options: object) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            installation, manifest, probe = _write_fixture(Path(directory), **options)
            return validator.validate_files(installation, manifest, probe, fixture_only=True)

    def test_partial_field_and_local_clone_entry_chain(self) -> None:
        report = self._run()
        fields = report["field_reads"]
        self.assertEqual(fields["total"], 9)
        self.assertEqual(fields["group_count"], 1)
        self.assertEqual(fields["actual_variant_field_0x3ec_count"], 1)
        self.assertEqual(fields["legacy_mislabel_0xec3_count"], 0)
        self.assertEqual(set(fields["unresolved_field_counts"]), {"0xe1", "0x2d87"})
        self.assertFalse(fields["groups"][0]["field_decode_complete"])
        self.assertTrue(fields["groups"][0]["latest_endpoint_identity_verified"])
        chain = report["field_to_command_entry"]
        self.assertEqual(chain["causal_local_evidence_count"], 1)
        self.assertFalse(chain["same_sequence_used_for_correlation"])
        self.assertFalse(chain["submit_verified"])
        self.assertEqual(report["direct_break"]["verified_count"], 1)
        self.assertFalse(report["acceptance_gate"])

    def test_missing_chain_stays_unknown(self) -> None:
        report = self._run(with_chain=False)
        chain = report["field_to_command_entry"]
        self.assertEqual(chain["causal_local_evidence_count"], 0)
        self.assertIn("FIELD_ENTRY_CHAIN_NOT_FOUND", {item["code"] for item in report["issues"]})
        self.assertIn("FIELD_TO_COMMAND_ENTRY_CAUSAL_CHAIN_PARTIAL", report["global_incomplete_reasons"])

    def test_layout_mutation_keeps_local_chain_but_stays_partial(self) -> None:
        report = self._run(layout_mismatch=True)
        chain = report["field_to_command_entry"]
        self.assertEqual(chain["causal_local_evidence_count"], 1)
        record = chain["records"][0]
        self.assertFalse(record["layout_continuity_verified"])
        self.assertEqual(record["layout_differences"], ["date2c"])
        self.assertIn("FIELD_ENTRY_LAYOUT_CONTINUITY_PARTIAL", report["global_incomplete_reasons"])

    def test_drop_and_wrong_variant_alias_block_acceptance(self) -> None:
        report = self._run(alias_variant=True, drop=True)
        self.assertEqual(report["field_reads"]["actual_variant_field_0x3ec_count"], 0)
        self.assertEqual(report["field_reads"]["legacy_mislabel_0xec3_count"], 1)
        issues = {item["code"] for item in report["issues"]}
        self.assertIn("PROBE_DROPPED_EVENTS", issues)
        self.assertIn("FIELD_SET_INCOMPLETE", issues)
        self.assertIn("VARIANT_FIELD_ID_MAPPING_UNVERIFIED", report["global_incomplete_reasons"])
        self.assertFalse(report["acceptance_gate"])

    def test_unknown_direct_break_caller_is_not_verified(self) -> None:
        report = self._run(unknown_direct=True)
        self.assertEqual(report["direct_break"]["verified_count"], 0)
        self.assertIn("DIRECT_BREAK_CALLER_UNVERIFIED", {item["code"] for item in report["issues"]})


if __name__ == "__main__":
    unittest.main()
