"""Record final file-only checks without repeating tests or opening a process."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_live_observer import live_source_pins, live_catalog
from bridge.diplomacy_effect_observer import pins as r1_pins
from bridge.diplomacy_reply_observer import reply_source_pins
from bridge.knowledge_effect_reader import verify_manifest as old_knowledge_pins
from bridge.knowledge_effect_reader_v2 import verify_manifest as knowledge_v2_pins
from bridge.tag_command_backend import digest, read


def main():
    graphs = {"live": live_source_pins(), "knowledge_v2": knowledge_v2_pins(),
        "knowledge_R1": old_knowledge_pins(), "reply_R2": reply_source_pins(), "effects_R1": r1_pins()}
    all_pins = {}
    for graph in graphs.values():
        for name, pin in graph.items():
            assert name not in all_pins or all_pins[name] == pin
            all_pins[name] = pin
    frozen = {
        "bridge/diplomacy_effect_observer.py": "9eafecba34e74a6bf1cc3d081b9ce4dee10395cf6bae7da233f915328ec876d1",
        "bridge/diplomacy_reply_observer.py": "7a7fdea49ee86b888336089b4982f1d2ff719d3eab9c530fb92f84c19a225761",
        "bridge/knowledge_effect_reader.py": "cc5a67b4ff23ed421bc8a58acf4a433178f22069f1b7d67d8962b36fb344d663",
        "bridge/knowledge_effect_reader_manifest_1375.json": "c380455fcfb80ea872a3c3776cbc2922587a069cf2481cecf057faab870d11db"}
    assert all(all_pins[name]["sha256"] == sha for name, sha in frozen.items())
    catalog = live_catalog()
    report = dict(schema="EU4DIPLOMACY-LIVE-OBSERVER-OFFLINE-VERIFICATION/1",
        recorded_utc=datetime.now(timezone.utc).isoformat(), source_pins=all_pins,
        graph_pin_counts={name: len(pins) for name, pins in graphs.items()}, unique_source_pins=len(all_pins),
        tests=dict(command="python -m unittest bridge.tests.test_knowledge_effect_reader_v2 bridge.tests.test_diplomacy_live_observer",
            observed_exit_code=0, observed_tests=34, observed_seconds=0.583,
            observation="Previously completed final tool execution; this recorder does not rerun tests",
            pure_synthetic_only=True, loopback_threads_shutdown_joined=True),
        syntax_compile_observed_exit_code=0,
        CLI_catalog_observed=dict(exit_code=0, profiles=len(catalog["profiles"]),
            knowledge_pair_profiles=catalog["knowledge_pair_profiles"], source_pins=len(catalog["source_pins"])),
        live_check_observed_exit_code=0, knowledge_v2_check_observed_exit_code=0,
        frozen_sources_unchanged=frozen, game_process_accessed=False, native_calls=0,
        requests_published=0, memory_written=False, saves_written=0, cold_reload_verified=False,
        actual_runtime_pair_evidence_verified=False,
        producer={"path": str(Path(__file__).relative_to(ROOT)).replace("\\", "/"),
            "sha256": digest(read(Path(__file__), 65536))}, running_shell_sessions_remaining=0,
        limitations=["Runtime prepare/dispatch/effect acceptance belongs to a separate parent-run receipt.",
            "Active sharing is not institution adoption completion or exact external-request causality."])
    path = ROOT/"work/reports/diplomacy-live-observer-20261015-r1/offline-verification.json"
    raw = (json.dumps(report, ensure_ascii=True, indent=2)+"\n").encode("ascii")
    with path.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"path": str(path), "bytes": len(raw), "sha256": digest(raw),
        "graph_pin_counts": report["graph_pin_counts"], "unique_source_pins": len(all_pins),
        "game_process_accessed": False}))


if __name__ == "__main__":
    main()
