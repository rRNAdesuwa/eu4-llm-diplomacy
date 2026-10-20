"""Seal two narrow ordinary UI consumers without process access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget
OUT = ROOT / "work/reports/console-alternate-consumers-20261015-r1"
PRIOR = ROOT / "work/reports/console-key-mapping-20261015-r1"


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    data = json.loads((OUT / "static.json").read_text())
    assert hashlib.sha256(pe.data).hexdigest() == data["game_sha256"]
    assert data["shared_scope_accounted_bytes"] == 8161 <= 8192
    rows = {}
    for item in data["ranges"]:
        raw = bytes.fromhex(item["raw_bytes"])
        assert pe.bytes_at(int(item["start"], 16), len(raw)) == raw
        assert b"".join(bytes.fromhex(i["bytes"]) for i in item["instructions"]) == raw
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        rows.update({i["rva"]: i for i in item["instructions"]})
    expected = {"0x816c48": "e8139fd400", "0x816c51": "80bef119000000",
        "0x816c58": "0f8556010000", "0x816cad": "c6477c01", "0x816c7c": "c6477c00",
        "0x816dbb": "66896b54", "0x14ea16f": "e8ec690700", "0x14ea176": "0f8530020000"}
    for address, value in expected.items():
        assert rows[address]["bytes"] == value
    assert pin(PRIOR / "manifest.json")["sha256"] == "270fcf8cfbbb638f51da6dc00f5e63981e9f56fb3adbd54560a1312c2b18bec1"
    old = json.loads((PRIOR / "manifest.json").read_text())
    for relative, value in old["source_pins"].items():
        assert pin(ROOT / relative) == value
    peak = check_memory_budget()
    if args.check:
        manifest = json.loads((OUT / "manifest.json").read_text())
        for relative, value in manifest["source_pins"].items():
            assert pin(ROOT / relative) == value
        print(json.dumps(dict(status="passed", source_pins=len(manifest["source_pins"]), new_decoded_bytes=0)))
        return
    result = dict(schema="EU4-CONSOLE-ALTERNATE-CONSUMERS-FINDINGS/1",
        game_sha256=data["game_sha256"], evidence_kind="fixed_PE_static_only", runtime_verified=False,
        ingame_consumer=dict(pdata_start="0x816af6", pdata_end="0x8171e0",
            chained_prologue_and_owner_identity_unresolved=True,
            event_kind_gate_rva="0x816b13", event_kind_required=1,
            key_nonzero_gate_rva="0x816bc5", modifier_not_minus_one_gate_rva="0x816bd0",
            console_global_load_rva="0x816bd9", console_global_rva="0x23496d0",
            predicate_call_rva="0x816c48", predicate_rva="0x1560b60",
            additional_toggle_gate_rva="0x816c51", gate="BYTE[owner_rsi+0x19f1]==0",
            gate_nonzero_branch_rva="0x816c58", gate_nonzero_target_rva="0x816db4",
            gate_nonzero_effect="No show/hide; writes event WORD+54=0xffff at816dbb and continues816e54.",
            gate_field_business_meaning="unknown", gate_current_runtime_value="unknown",
            hide_virtual_call_rva="0x816c6f", hide_virtual_slot="0x90", hide_state_zero_rva="0x816c7c",
            show_virtual_call_rva="0x816c89", show_virtual_slot="0x88",
            edit_active_write_rva="0x816c93", focus_virtual_slot="0x60", focus_call_rva="0x816ca3",
            show_state_one_rva="0x816cad", event_consumed_word="0xffff",
            toggle_proven=True, full_outer_input_routing_proven=False),
        alternate_filter=dict(function_rva="0x14ea150", end_rva="0x14ea3c9",
            predicate_call_rva="0x14ea16f", accepted_branch_rva="0x14ea176",
            accepted_target_rva="0x14ea3ac", accepted_effect="Return without window toggle or event+54 write in this branch.",
            toggle_proven=False, interpretation="Filters the recognized shortcut from this handler's other GUI routing."),
        unresolved=["Owner of rsi and semantic name/current value of BYTE+19f1.",
            "Upstream routing, native keyevent producer, keyboard layout and automation-token delivery.",
            "Which consumer is actually reached by the current game UI sample."],
        attribution="A failed visible automation-token attempt cannot identify the blocking condition.",
        business_meaning_ironman_claimed=False, sky_token_recommended=None,
        resources=dict(this_scope_accounted_bytes=2403, prior_mapping_scope_bytes=5758,
            shared_scope_bytes=8161, shared_scope_limit=8192, peak_committed_bytes=peak),
        game_process_accessed=False, native_calls=0, keys_sent=0, memory_written=False)
    (OUT / "findings.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    (OUT / "README.md").write_text(
        "# Alternate console consumers\n\n"
        "Map-side predicate call816C48 is a real toggle, with an additional BYTE[owner_rsi+19F1]==0 gate at816C51. Nonzero takes816DB4, consumes event WORD+54=FFFF at816DBB, and never calls show/hide. Zero reaches the normal console window show/hide, edit activation and+7C state write. Owner identity, field meaning and current value remain unknown; this evidence does not name the byte as ironman.\n\n"
        "The other call14EA16F is a filter: a true predicate branches directly to return14EA3AC, without toggling the window. Neither selected consumer establishes current upstream event delivery or a Sky key token.\n\n"
        "These two full pdata ranges add2403B. With the already sealed5758B mapping scope, the shared new-decode account is8161/8192B. Exact PE bytes and old manifests replay successfully. No process, key input, native call or write occurred.\n", encoding="utf-8")
    files = [OUT / x for x in ("static.json", "disassembly.txt", "findings.json", "README.md")]
    files += [ROOT / "work" / x for x in ("trace_console_alternate_consumers_20261015.py",
        "finalize_console_alternate_consumers_20261015.py", "discover_diplomacy.py")]
    files += [PRIOR / "manifest.json", PRIOR / "findings.json"]
    manifest = dict(schema="EU4-CONSOLE-ALTERNATE-CONSUMERS-MANIFEST/1", game_sha256=data["game_sha256"],
        source_pins={p.relative_to(ROOT).as_posix(): pin(p) for p in files},
        shared_scope_accounted_bytes=8161, scope_limit_bytes=8192, game_process_accessed=False)
    with (OUT / "manifest.json").open("x", encoding="ascii") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps(dict(manifest=pin(OUT / "manifest.json"), findings=pin(OUT / "findings.json"))))


if __name__ == "__main__":
    main()
