"""Seal exact ordinary console-event predicate evidence; no native invocation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"work"))
from discover_diplomacy import PE, check_memory_budget
DIRECTORY = ROOT/"work/reports/console-shortcut-static-20261015-r2"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def predicate(key, field4, modifier, lowered_c=99):
    """Pure arithmetic transcription for documentation cases only."""
    if key == 0 or modifier == -1:
        return False
    normalized = 99 if lowered_c == -1 else lowered_c
    return (modifier == 3 and key == normalized) or field4 == 0x35


def verify_pe(data):
    pe = PE(ROOT.parent/"eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA == data["game_sha256"]
    assert data["new_decoded_bytes"] == 15840 <= 16384
    for r in data["ranges"]:
        raw = bytes.fromhex(r["raw_bytes"])
        assert pe.bytes_at(int(r["start"], 16), len(raw)) == raw
        assert hashlib.sha256(raw).hexdigest() == r["sha256"]
        assert b"".join(bytes.fromhex(i["bytes"]) for i in r["instructions"]) == raw
    return check_memory_budget()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = json.loads((DIRECTORY/"static.json").read_text())
    peak = verify_pe(data)
    if args.check:
        manifest = json.loads((DIRECTORY/"manifest.json").read_text())
        for relative, expected in manifest["source_pins"].items():
            assert pin(ROOT/relative) == expected, relative
        print(json.dumps(dict(status="passed", source_pins=len(manifest["source_pins"]),
            replayed_PE_bytes=15840, new_decoded_bytes=0, game_process_accessed=False)))
        return
    cases = []
    for key, field4, modifier, lowered, expected in ((99,0,3,99,True), (99,0,0,99,False),
            (65,53,0,99,True), (0,53,0,99,False), (99,53,-1,99,False),
            (99,52,0,99,False), (98,0,3,99,False), (99,0,3,-1,True)):
        value = predicate(key,field4,modifier,lowered)
        assert value is expected
        cases.append(dict(key_raw=key, field4_raw=field4, modifier_raw=modifier,
            helper_lowercase_c_result=lowered, predicate_model=value, native_executed=False))
    result = dict(schema="EU4-CONSOLE-KEYBOARD-PREDICATE-FINDINGS/1", game_sha256=SHA,
        status="ordinary_UI_consumer_and_native_predicate_resolved_mapping_pending",
        evidence_kind="fixed_PE_static_only", runtime_verified=False,
        consumer=dict(function_rva="0x1253d80", end_rva="0x125541a",
            event_kind_field="DWORD event+0x50", selected_kind=1, kind_gate_rva="0x12552dd",
            predicate_call_rva="0x125532a", predicate_rva="0x1560b60",
            console_object_global_rva="0x23496d0", open_state_byte_offset="0x7c",
            state_gate_rva="0x1255337", closed_show_call_rva="0x125535c",
            show_function_rva="0x166d1f0", show_state_write_rva="0x166d221",
            shown_hide_virtual_call_rva="0x1255349", hidden_state_write_rva="0x125534f",
            constructor_state_zero_rva="0x166cdc9"),
        exact_native_predicate=dict(key_field="DWORD event+0", scan_or_code_field="DWORD event+4",
            modifier_field="DWORD event+8", preconditions=["event+0 != 0", "event+8 != -1"],
            alternatives=["event+8 == 3 AND event+0 == helper_lowercase(0x63), falling back to0x63 for -1",
                "event+4 == 0x35"], modifier_comparison="exact equality3",
            lowercase_helper_rva="0x1a4ae3c", helper_bytes=42,
            helper_ascii_path="A..Z add0x20; all other input integers preserved",
            helper_locale_path="Conditional call1a4abc4 remains outside this scope"),
        UI_object=dict(constructor_rva="0x166cb30", gui_window_string_rva="0x1da8928",
            gui_edit_string_rva="0x1da8958", window_pointer_offset="0x68", edit_pointer_offset="0x70",
            show_path="window+30 virtual+88, edit+88 WORD1, window virtual+60, own+7c BYTE1",
            hide_path="window+30 virtual+90, own+7c BYTE0"),
        static_arithmetic_boundary_cases=cases,
        unresolved=["Generation and enum meaning of event+8 value3 (Alt/Shift/Ctrl mapping).",
            "Generation/type of event+4 value0x35 and its actual physical-key mapping.",
            "Sky/automation key token and current keyboard-layout/input delivery.",
            "Current runtime execution of this consumer and every outer focus/modal/mode gate."],
        ordinary_UI_shortcut_token_recommended=None, direct_native_call_authorized=False,
        local_ironman_open_gate_observed=False, all_opening_conditions_proven=False,
        statement_on_ironman="No direct ironman test occurs in the selected local toggle branch; broader routing remains unresolved.",
        dispatcher_pdata=dict(start="0x1721320", end="0x1721c5c", bytes=2364,
            newly_decoded_here=False, reason="Command dispatcher is independent of the UI key-toggle predicate"),
        resources=dict(new_decoded_bytes=15840, budget_bytes=16384,
            trace_peak_committed_bytes=data["peak_committed_bytes"], replay_peak_committed_bytes=peak),
        game_process_accessed=False, keys_sent=0, native_calls=0, memory_written=False,
        limitations=["Byte-pattern candidates outside decoded ranges remain unvalidated instruction boundaries.",
            "A proved native input predicate does not prove an automation token or current keyboard layout.",
            "Pure boundary cases model the retained code; they are not native or UI tests."])
    (DIRECTORY/"findings.json").write_text(json.dumps(result, indent=2)+"\n", encoding="ascii")
    text = ("# Ordinary console UI predicate\n\n"
        "A real ordinary UI input consumer is resolved at RVA1253d80. Event-kind DWORD+50==1 reaches125532a→1560b60. Its exact predicate requires key DWORD+0 nonzero and modifier DWORD+8 different from−1, then either modifier==3 with key==lowercase(0x63), or DWORD+4==0x35. Modifier comparison is exact equality.\n\n"
        "When accepted, console object global23496d0/+7c selects the normal show/hide path: closed calls166d1f0 and sets+7c=1; shown invokes window+30 virtual+90 and sets+7c=0. Constructor166cb30 resolves actual console_wnd/console_edit and initializes+7c=0. Thus this is window toggling, not merely console command dispatch.\n\n"
        "Field+8 value3 and field+4 value0x35 still need producer/enum mapping. No Sky token or new physical key is recommended. The selected local toggle has no direct ironman test; full upstream input routing, focus/modal/mode conditions and current runtime execution remain unproved.\n\n"
        "13 narrowly selected ranges total15,840B below16KiB. Exact .rdata seeds and exact direct-call candidates guided the chain; command dispatcher1721320 is2,364B by pdata and was not newly decoded. All retained instruction bytes replay against fixed EXE SHA9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a. Old6,980B evidence is unchanged. No game process, key input, native invocation or memory write was used.\n")
    (DIRECTORY/"README.md").write_text(text, encoding="utf-8")
    files = [DIRECTORY/name for name in ("static.json", "disassembly.txt", "seed-xrefs.json", "caller-xrefs.json", "findings.json", "README.md")]
    files += [ROOT/"work"/name for name in ("probe_console_ui_seeds_r2_20261015.py",
        "trace_console_keyboard_r2_20261015.py", "trace_console_caller_xrefs_r2_20261015.py",
        "finalize_console_keyboard_r2_20261015.py", "discover_diplomacy.py")]
    manifest = dict(schema="EU4-CONSOLE-KEYBOARD-STATIC-MANIFEST/1", game_sha256=SHA,
        source_pins={p.relative_to(ROOT).as_posix(): pin(p) for p in files},
        newly_decoded_bytes=15840, game_process_accessed=False, keys_sent=0, native_calls=0)
    with (DIRECTORY/"manifest.json").open("x", encoding="ascii") as stream:
        json.dump(manifest,stream,indent=2)
    print(json.dumps(dict(manifest=pin(DIRECTORY/"manifest.json"), findings=pin(DIRECTORY/"findings.json"),
        decoded_bytes=15840, source_pins=len(files), game_process_accessed=False)))


if __name__ == "__main__":
    main()
