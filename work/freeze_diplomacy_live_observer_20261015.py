"""Freeze only newly owned observer files; offline, no game/process operation."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import DEFAULT_MANIFEST, GAME_SHA
from bridge.knowledge_effect_reader import verify_manifest as verify_old_knowledge
from bridge.diplomacy_reply_observer import reply_source_pins


def pins(names):
    result = {}
    for name in names:
        path = ROOT/name
        assert path.stat().st_size < 16*1024*1024
        raw = path.read_bytes()
        result[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def save(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2)+"\n").encode("ascii")
    (ROOT/name).write_bytes(raw)
    print(json.dumps({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}))


def main():
    verify_old_knowledge()
    reply_source_pins()
    native_sha = hashlib.sha256(DEFAULT_MANIFEST.read_bytes()).hexdigest()
    save("bridge/knowledge_effect_reader_v2_manifest_1375.json", dict(
        schema="EU4DIPLOMACY-KNOWLEDGE-READER-MANIFEST/2", game_sha256=GAME_SHA,
        native_manifest_sha256=native_sha,
        source_pins=pins(["bridge/knowledge_effect_reader_v2.py", "bridge/tests/test_knowledge_effect_reader_v2.py",
            "bridge/knowledge_effect_reader.py", "bridge/knowledge_effect_reader_manifest_1375.json",
            "work/reports/knowledge-effect-observer-20261015-r1/index-guard/static.json",
            "work/extract_knowledge_index_guard_20261015.py",
            "work/reports/war-peace-api-20261015-r4/peace/lifecycle/analysis.json"]),
        supported_actions=["knowledge_sharing", "ask_knowledge_sharing"], read_only=True,
        typed_index_layout=dict(vtable_rva="0x1c3a538", array=8, capacity=16, used=20, entry_bytes=16),
        new_decoded_bytes=0, game_process_accessed=False, native_calls=0, requests_published=0,
        frozen_R1_modified=False, institution_completion_verified=False))
    save("bridge/diplomacy_live_observer_manifest_1375.json", dict(
        schema="EU4DIPLOMACY-LIVE-OBSERVER-MANIFEST/1", game_sha256=GAME_SHA,
        native_manifest_sha256=native_sha,
        source_pins=pins(["bridge/diplomacy_live_observer.py", "tools/observe_diplomacy_live.py",
            "bridge/tests/test_diplomacy_live_observer.py", "bridge/knowledge_effect_reader_v2.py",
            "bridge/knowledge_effect_reader_v2_manifest_1375.json",
            "bridge/diplomacy_reply_observer.py", "bridge/diplomacy_reply_observer_manifest_1375.json",
            "bridge/diplomacy_effect_observer.py", "bridge/diplomacy_observer_manifest_1375.json",
            "bridge/diplomacy_effect_profiles.py", "bridge/diplomacy_observer_service.py",
            "bridge/tag_command_backend.py", "bridge/tag_command_audit.py",
            "work/freeze_diplomacy_live_observer_20261015.py",
            "work/reports/diplomacy-live-observer-20261015-r1/README.md"]),
        knowledge_pair_profiles=["knowledge_sharing", "ask_knowledge_sharing"],
        recipient_reply_profiles=["ask_for_march"], read_only=True,
        native_calls=0, requests_published=0, saves_written=0,
        R1_core_changes=False, R2_changes=False, frozen_knowledge_R1_changes=False,
        automatic_command_retry=False, AI_acceptance_verified=False,
        exact_external_request_id_causality_verified=False, knowledge_institution_completion_verified=False,
        limits=dict(knowledge_shared_calls=4096, knowledge_shared_bytes=512*1024, response_bytes=256*1024),
        limitations=["Preparation observes intent and publisher-lock absence; it is not an atomic publisher lease.",
            "Selected sharing pair activation is not completed institution adoption.",
            "No atomic world epoch, exact external causality, persistence or AI acceptance is proved."]))


if __name__ == "__main__":
    main()
