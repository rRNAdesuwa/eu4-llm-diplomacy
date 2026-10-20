"""Two explicitly selected normal input functions; disk-only, <=16KiB."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    pe = PE(ROOT.parent/"eu4.exe")
    sha = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
    assert hashlib.sha256(pe.data).hexdigest() == sha
    drafts = ROOT/"work/candidates/offered-fleet-ai-response-1375"
    replay = json.loads((drafts/"draft-10-console-ui.json").read_text())
    replay_rows = [i for f in replay.values() for i in f["instructions"]]
    for i in replay_rows:
        raw = bytes.fromhex(i["bytes"])
        assert pe.bytes_at(int(i["rva"], 16), len(raw)) == raw
    owners = json.loads((drafts/"draft-08-console-callers.json").read_text())
    for row in owners:
        observed = pe.function(int(row["rva"], 16))
        assert observed and list(observed) == [int(x, 16) for x in row["owner"]]
    md, cs = make_disassembler(ROOT/"work/deps/capstone-5.0.7")
    assert md and cs.__version__ == "5.0.7"
    functions = []
    total = 0
    for start in (0x74A260, 0x758430):
        interval = pe.function(start)
        assert interval and interval[0] == start
        _, end, _ = interval
        total += end-start
        assert total <= 16*1024
        raw = pe.bytes_at(start, end-start)
        rows = []
        for i in md.disasm(raw, start):
            row = dict(rva=hex(i.address), bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str)
            for o in i.operands:
                if o.type == cs.x86.X86_OP_MEM and o.mem.base == cs.x86.X86_REG_RIP:
                    target = i.address+i.size+o.mem.disp
                    reference = dict(rva=hex(target))
                    try:
                        data = pe.bytes_at(target, 96).split(b"\0", 1)[0]
                        if data and all(32 <= b < 127 for b in data):
                            reference["ascii_candidate"] = data.decode("ascii")
                    except (KeyError, ValueError):
                        pass
                    row.setdefault("rip_references", []).append(reference)
                if o.type == cs.x86.X86_OP_IMM and (i.mnemonic == "call" or i.mnemonic.startswith("j")):
                    row["direct_target"] = hex(o.imm)
            rows.append(row)
        functions.append(dict(start_rva=hex(start), end_rva_exclusive=hex(end),
            range_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=raw.hex(), instructions=rows,
            disassembled_bytes=sum(len(bytes.fromhex(i["bytes"])) for i in rows)))
    directory = ROOT/"work/reports/console-shortcut-static-20261015"
    directory.mkdir(parents=True, exist_ok=True)
    asm = "\n".join("FUNCTION "+f["start_rva"]+"\n"+"\n".join(
        f"{int(i['rva'], 16):08x} {i['bytes']:22} {i['mnemonic']:9} {i['operands']} "+
        " ".join(x.get("ascii_candidate", "") for x in i.get("rip_references", [])) for i in f["instructions"])
        for f in functions)+"\n"
    with (directory/"disassembly.txt").open("x", encoding="utf-8") as stream:
        stream.write(asm)
    report = dict(schema="EU4-CONSOLE-SHORTCUT-STATIC/1", game_sha256=sha, image_base=hex(pe.base),
        evidence_kind="ordinary_capstone_fixed_PE_only", capstone_version=cs.__version__,
        functions=functions, new_decoded_range_bytes=total, new_decoded_budget_bytes=16*1024,
        replayed_ui_instruction_count=len(replay_rows),
        replayed_ui_bytes=sum(len(bytes.fromhex(i["bytes"])) for i in replay_rows),
        replayed_ui_matches_current_fixed_PE=True, caller_owners_match_current_pdata=True,
        source_pins={p.relative_to(ROOT).as_posix(): pin(p) for p in
            (Path(__file__), ROOT/"work/discover_diplomacy.py", drafts/"draft-10-console-ui.json",
             drafts/"draft-08-console-callers.json", drafts/"draft-04-console-start.json")},
        peak_committed_bytes=check_memory_budget(), game_process_accessed=False,
        native_calls=0, memory_written=False, keys_sent=0,
        limitations=["Only two explicit input caller functions; no whole-file disassembly or native invocation.",
            "Static key IDs and predicates are not proof of a current keyboard layout or input delivery."])
    raw = (json.dumps(report, ensure_ascii=True, indent=2)+"\n").encode("ascii")
    with (directory/"static.json").open("xb") as stream:
        stream.write(raw)
    print(json.dumps(dict(path=str(directory/"static.json"), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
        decoded_range_bytes=total, peak_committed_bytes=report["peak_committed_bytes"])))


if __name__ == "__main__":
    main()
