"""Seal a fixed-PE modifier enum and scan-name mapping; never access the game."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget

OUT = ROOT / "work/reports/console-key-mapping-20261015-r1"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
PRIOR = ROOT / "work/reports/console-shortcut-static-20261015-r2"


def pin(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    data = json.loads((OUT / "static.json").read_text())
    assert data["new_decoded_bytes"] == 5718
    for item in data["ranges"]:
        raw = bytes.fromhex(item["raw_bytes"])
        assert pe.bytes_at(int(item["start"], 16), len(raw)) == raw
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert b"".join(bytes.fromhex(i["bytes"]) for i in item["instructions"]) == raw
    for item in data["tables"].values():
        raw = bytes.fromhex(item["raw_hex"])
        assert pe.bytes_at(int(item["rva"], 16), len(raw)) == raw
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    assert pin(PRIOR / "manifest.json")["sha256"] == "7482d46aa6ee8f014f5e793929be32e839900053095ff31a14441083e2fc47a5"
    old = json.loads((PRIOR / "manifest.json").read_text())
    for relative, expected in old["source_pins"].items():
        assert pin(ROOT / relative) == expected, relative
    table = bytes.fromhex(data["tables"]["windows_scan_to_internal"]["raw_hex"])
    assert struct.unpack_from("<I", table, 0x29 * 4)[0] == 0x35
    assert [i for i in range(128) if struct.unpack_from("<I", table, i * 4)[0] == 0x35] == [0x29]
    slot = bytes.fromhex(data["tables"]["scan53_name_slot"]["raw_hex"])
    assert struct.unpack("<Q", slot)[0] == pe.base + 0x1b6c9a8
    assert pe.bytes_at(0x1b6c9a8, 2) == b"`\0"
    enum = bytes.fromhex(data["tables"]["modifier_enum_values"]["raw_hex"])
    assert struct.unpack("<4i", enum) == (2, 1, 4, 8)
    peak = check_memory_budget()
    if args.check:
        manifest = json.loads((OUT / "manifest.json").read_text())
        for relative, expected in manifest["source_pins"].items():
            assert pin(ROOT / relative) == expected, relative
        print(json.dumps({"status": "passed", "source_pins": len(manifest["source_pins"]),
            "new_decoded_bytes": 0, "replayed_instruction_bytes": 5718,
            "game_process_accessed": False}))
        return
    strings = {}
    for name, rva, raw in (("shift", 0x1d94654, b"shift\0"), ("alt", 0x1d9465c, b"alt\0"),
            ("ctrl", 0x1d94660, b"ctrl\0"), ("grave", 0x1b6c9a8, b"`\0")):
        assert pe.bytes_at(rva, len(raw)) == raw
        strings[name] = {"rva": hex(rva), "raw_hex": raw.hex(), "sha256": hashlib.sha256(raw).hexdigest()}
    result = {
        "schema": "EU4-CONSOLE-KEY-MAPPING-FINDINGS/1", "game_sha256": SHA,
        "status": "modifier_enum_resolved_scan_name_resolved_ingress_unresolved",
        "evidence_kind": "fixed_PE_static_only", "runtime_verified": False,
        "modifier_enum": {"parser_rva": "0x155fdb0", "parser_end_rva": "0x156018b",
            "output_size": 16, "key_offset": 0, "field4_zeroed": True,
            "modifier_offset": 8, "field12_zeroed": True,
            "ctrl_or_control": 1, "alt": 2, "shift": 4,
            "write_chain_rva": ["0x1560089", "0x156008e", "0x156009e", "0x15600b2", "0x15600c0"],
            "console_modifier_3": "Ctrl|Alt; Shift is not set",
            "independent_formatter_rva": "0x1560190",
            "formatter_enum_table_rva": "0x1dc2250", "formatter_values_in_table_order": [2, 1, 4, 8],
            "formatter_ctrl_rva": "0x1560237", "formatter_alt_rva": "0x1560240",
            "formatter_shift_rva": "0x1560249",
            "source_path_literal": "C:\\mnt\\gsg\\eu4\\eu4\\clausewitz\\clausewitzlib\\keyevent.cpp",
            "initial_trace_label_note": "event_modifier_serializer is a retained exploratory label; code is a string-to-keyevent parser."},
        "scan_mapping": {"name_accessor_rva": "0x174db30", "name_accessor_max_scan": "0x1ff",
            "name_table_rva": "0x1fb1470", "selected_slot_rva": "0x1fb1618",
            "selected_index": "0x35", "name_string_rva": "0x1b6c9a8", "name": "`",
            "windows_keymap_update_rva": "0x17655a0", "windows_scan_table_rva": "0x1b6e930",
            "windows_native_scan": "0x29", "internal_scan": "0x35",
            "native_scan_inverse_unique_in_128_entries": True,
            "logical_keymap_accessor_rva": "0x174d800", "logical_keymap_rva": "0x233567c",
            "layout_sensitive_logical_key_mapping": True,
            "event_field4_to_scancode_producer_proven": False,
            "ordinary_physical_key_interpretation": "The internal scan name is the grave/backtick key; actual event+4 ingress has not been traced."},
        "strings": strings,
        "unresolved": ["The producer copying or converting platform scancode into the consumer's event+4.",
            "Current Windows key layout, focus/modal routing and actual native event delivery.",
            "Any Sky automation token correspondence or current UI toggle execution."],
        "ordinary_UI_shortcut_token_recommended": None,
        "resources": {"retained_instruction_bytes": 5718, "conservative_failed_inline_table_attempt_bytes": 40,
            "scope_accounted_new_decode_bytes": 5758, "scope_budget_bytes": 8192,
            "remaining_scope_bytes": 2434, "peak_committed_bytes": peak,
            "failed_attempt_note": "Initial complete .pdata linear decode reached embedded jump table after15609e8. Retained valid code stops before the table; all40 table bytes are conservatively charged."},
        "game_process_accessed": False, "keys_sent": 0, "native_calls": 0, "memory_written": False,
        "limitations": ["Native enum mapping is not a demonstration that an automation key sequence reaches the consumer.",
            "Only selected fixed-PE code/data were interpreted; no ordinary UI action was performed by this analysis."]}
    (OUT / "findings.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    (OUT / "README.md").write_text(
        "# Console key mapping (static)\n\n"
        "The keyevent parser155FDB0 writes Ctrl/control=1, Alt=2, Shift=4 into the16B event's DWORD+8. The independent formatter1560190 uses the same1/2/4/8 enum and ctrl/alt/shift names. Thus the selected console predicate's exact modifier3 means Ctrl+Alt, without Shift.\n\n"
        "The scan-name accessor174DB30 reads table1FB1470; slot0x35 points to literal backtick at1B6C9A8. Windows scan conversion table1B6E930 maps native scan0x29 uniquely to internal0x35. The event+4 producer remains unresolved, so this does not prove current event delivery, keyboard layout or a Sky token.\n\n"
        "5718B of retained valid instructions plus a conservative40B charge for a failed initial linear decode into an inline jump table accounts for5758/8192B. Prior15840B scope and its manifest remain unchanged. No game process, UI input, native call or write was used.\n", encoding="utf-8")
    files = [OUT / name for name in ("static.json", "disassembly.txt", "findings.json", "README.md")]
    files += [ROOT / "work" / name for name in ("trace_console_key_mapping_20261015.py",
        "finalize_console_key_mapping_20261015.py", "discover_diplomacy.py")]
    files += [PRIOR / "manifest.json", PRIOR / "findings.json"]
    manifest = {"schema": "EU4-CONSOLE-KEY-MAPPING-MANIFEST/1", "game_sha256": SHA,
        "source_pins": {p.relative_to(ROOT).as_posix(): pin(p) for p in files},
        "new_decode_accounted_bytes": 5758, "scope_budget_bytes": 8192,
        "game_process_accessed": False, "native_calls": 0, "keys_sent": 0}
    with (OUT / "manifest.json").open("x", encoding="ascii") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps({"manifest": pin(OUT / "manifest.json"), "findings": pin(OUT / "findings.json")}))


if __name__ == "__main__":
    main()
