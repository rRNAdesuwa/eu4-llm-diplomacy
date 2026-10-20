"""Seal a bounded negative shortcut finding without new native analysis."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/"work/reports/console-shortcut-static-20261015"


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    static = DIRECTORY/"static.json"
    assert pin(static)["sha256"] == "a403532df340039fe332ce61741dbb72a47c8ad1c90061e77cd7f24bbf6c5d39"
    d = json.loads(static.read_text())
    assert d["new_decoded_range_bytes"] == 6980 < 16*1024
    assert len(d["functions"]) == 2
    assert all(x["disassembled_bytes"] == len(bytes.fromhex(x["raw_bytes"])) for x in d["functions"])
    for relative, expected in d["source_pins"].items():
        assert {k: pin(ROOT/relative)[k] for k in ("bytes", "sha256")} == expected
    gui = ROOT.parent/"interface/core.gui"
    gui_text = gui.read_text(encoding="utf-8-sig")
    assert 'name = "console_wnd"' in gui_text and 'name = "console_edit"' in gui_text
    prefix = gui_text.split('name = "console_entry_wnd"', 1)[0]
    assert "shortcut" not in prefix.lower()
    source_paths = [static, DIRECTORY/"disassembly.txt", Path(__file__), gui]
    result = dict(schema="EU4-CONSOLE-SHORTCUT-BOUNDED-REVIEW/1", status="shortcut_unknown",
        game_sha256=d["game_sha256"], evidence_kind="fixed_PE_static_only",
        sources=[pin(p) for p in source_paths], initial_draft_sources=d["source_pins"],
        initial_ui_draft_identity=dict(explicit_SHA_field_present=False,
            all_519_retained_instructions_replayed_against_fixed_current_PE=True,
            replayed_bytes=2167, mismatches=0),
        caller_draft_current_pdata_owners_match=True,
        ranges=[{k: f[k] for k in ("start_rva", "end_rva_exclusive", "range_sha256", "disassembled_bytes")} for f in d["functions"]],
        findings=[dict(status="observed_static", rvas=["0x74b27d", "0x74b282"],
            fact="First selected caller invokes console-manager getter6e74c0 and clears manager+44. This alone is no keyboard dispatch."),
            dict(status="observed_static", rvas=["0x758e1b", "0x758e20", "0x758e2d"],
            fact="Second selected caller gets the same manager, passes token-vector/output to the normal dispatcher1721320. Native shortcut recognition is not established."),
            dict(status="observed_file", path=str(gui),
                fact="Original GUI defines console_wnd, console_list and console_edit. The selected window definition has no shortcut field.")],
        unresolved=["Physical key, Windows VK or native input-key ID used to toggle the console window.",
            "Shift/Alt/keyboard-layout mapping and the automation provider's physical-key token.",
            "All console-window opening conditions, focus and modal/input delivery behavior.",
            "Why grave, Shift+grave and Shift+3 failed in the parent UI observation."],
        key_combination_recommended=None, native_key_ID_proven=None, opening_condition_proven=False,
        command_eligibility_is_window_opening_condition=False,
        new_decoded_function_count=2, new_decoded_bytes=6980, max_decoded_bytes=16384,
        peak_committed_bytes=d["peak_committed_bytes"], game_process_accessed=False,
        keys_sent=0, native_calls=0, memory_written=False, full_file_disassembly_scan=False,
        limitations=["The initial draft files have no own EXE identity field; only retained instruction-byte and pdata replay establish the specifically checked current build match.",
            "Console manager/command dispatch callsites are not keyboard shortcut proof. Nonironman is not a sufficient opening-condition proof.",
            "The search stops at the two explicit caller functions; no third function, process probe, key input or speculative native invocation."])
    destination = DIRECTORY/"findings.json"
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
    markdown = DIRECTORY/"README.md"
    text = ("# Bounded console shortcut review\n\n"
        "Shortcut and console-window opening conditions remain unknown. No new key combination is recommended.\n\n"
        "The existing UI draft has no binary identity field, but all 519 retained instructions (2,167 bytes) match the fixed current EXE SHA9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a. Existing caller ownership also matches current pdata.\n\n"
        "Exactly two existing caller candidates were decoded: RVA74a260–74b2a7 (4,167B) and758430–758f2d (2,813B), total6,980B below16KiB; peak73,752,576B. At74b27d the code gets console manager6e74c0 and clears+44. At758e1b it gets that manager before normal command dispatcher1721320. Neither selected range closes keyboard shortcut recognition.\n\n"
        "Original interface/core.gui defines console_wnd/console_list/console_edit without a shortcut field in the window definition. Ordinary command restrictions such as ironman/multiplayer must not be treated as proven window-opening conditions. Physical key/VK/native input ID, layout modifiers, input focus and automation tokens remain unresolved.\n\n"
        "No third function or whole-file disassembly was scanned. No process, native game function, keyboard input or memory write was used.\n")
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print(json.dumps({"findings": pin(destination), "markdown": pin(markdown),
        "status": "shortcut_unknown", "new_decoded_bytes": 6980, "keys_sent": 0}))


if __name__ == "__main__":
    main()
