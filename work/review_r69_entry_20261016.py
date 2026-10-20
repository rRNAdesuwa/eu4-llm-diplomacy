"""Retained raw caller review only; never load decoder or callee bytes."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/war-peace-api-20261016-r69-generator-divisor-source/"
ORIGIN = "work/reports/war-peace-api-20261016-r62-gold-recipient-generator/"
OUT = ROOT / "work/reports/war-peace-api-20261016-r69-entry-root-review"
COUNT = 0
RAW = {}


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(rel, expected=None):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and not rel.startswith("work/deps/")
    assert p.suffix.lower() not in (".exe", ".dll", ".pyd") and p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 16 * 1024 * 1024
    if expected is not None:
        assert pin(raw) == expected, rel
    return raw


def obj(rel):
    return json.loads(RAW[rel])


def save(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    with (OUT / name).open("xb") as f:
        f.write(raw)
    return pin(raw)


assert not OUT.exists()
OUT.mkdir()
RAW[BASE + "source-manifest.json"] = read(BASE + "source-manifest.json", {"bytes": 21501, "sha256": "f0540a54cc50a6bf1024863b818dcb61e5a506567e77bbd9a2c5d4af40e853f9"})
manifest = obj(BASE + "source-manifest.json")
paths = [BASE + n for n in ("entry-seed.json", "produce.py", "budget.json", "inventory.json")]
paths += [ORIGIN + n for n in ("manifest.json", "capture.json", "owned-code.json", "selected-evidence.json")]
paths += ["work/reports/war-peace-api-20261016-r62-independent-review/" + n for n in ("findings.json", "manifest.json")]
for rel in paths:
    RAW[rel] = read(rel, manifest["source_pins"][rel])
seed = obj(BASE + "entry-seed.json")
assert seed["entry_rva"] == "0x993570" and seed["call_site_rva"] == "0x98453d"
assert seed["raw_call"] == "e82ef00000"
owned = obj(ORIGIN + "owned-code.json")
capture = obj(ORIGIN + "capture.json")
selected = obj(ORIGIN + "selected-evidence.json")
code = bytes.fromhex(owned["raw_hex"])
assert len(code) == 684 and selected["raw_hex"] == owned["raw_hex"]
assert hashlib.sha256(code).hexdigest() == owned["sha256"] == selected["raw_sha256"]
rows = capture["analysis"]["instructions"]
assert selected["instructions"] == rows
table = {int(x["rva"], 16): x for x in rows}
minimal = seed["minimal_continuous_caller_rows"]
assert len(minimal) == 14
next_rva = 0x984519
for row in minimal:
    at = int(row["rva"], 16)
    raw = bytes.fromhex(row["bytes"])
    assert at == next_rva and row == table[at]
    assert raw == code[at - 0x9844D0:at - 0x9844D0 + len(raw)]
    next_rva += len(raw)
assert next_rva == 0x984561 and seed["minimal_window_bytes"] == 72
assert seed["pre_and_CALL_bytes"] == 41 and seed["post_CALL_bytes"] == 31
raw_map = {int(x["rva"], 16): x["bytes"] for x in minimal}
assert raw_map == {0x984519:"498b1e", 0x98451c:"0f57c0", 0x98451f:"f30f7f442438",
    0x984525:"4533ff", 0x984528:"4c897c2448", 0x98452d:"4c8d442438", 0x984532:"488d9424a8000000",
    0x98453a:"488bce", 0x98453d:"e82ef00000", 0x984542:"49b9abaaaaaaaaaaaaaa", 0x98454c:"4c8b642438",
    0x984551:"4863b424a8000000", 0x984559:"85f6", 0x98455b:"0f8e83010000"}
call = bytes.fromhex(seed["raw_call"])
assert 0x98453D + 5 + struct.unpack("<i", call[1:])[0] == 0x993570
prologue = seed["retained_prologue_for_frame"]
assert all(x == table[int(x["rva"], 16)] for x in prologue)
pushes = [x for x in prologue if x["mnemonic"] == "push"]
assert [x["bytes"] for x in pushes] == ["55", "56", "57", "4154", "4155", "4156", "4157"]
assert table[0x9844E5]["bytes"] == "4883ec50" and table[0x9844EC]["bytes"] == "488bf1"
assert 7 * 8 + 0x50 == 0x88 and -0x88 + 0xA8 == 0x20 and -0x88 + 0x38 == -0x50
for row in minimal[2:8]:
    assert row["mnemonic"] not in ("call", "xorps", "movaps", "movdqu") or int(row["rva"], 16) == 0x98451F
assert seed["XMM0_at_call"] == "zero128_from_98451c_XORPS_no_XMM_write_or_CALL_before_98453d"
assert seed["callee_XMM_consumption_proved"] is False
assert table[0x984551]["memory_operands"][0]["width_bytes"] == 4
jle = bytes.fromhex(raw_map[0x98455B])
assert 0x98455B + 6 + struct.unpack("<i", jle[2:])[0] == 0x9846E4
for at, raw in ((0x9845E1, "f7fe"), (0x9845F3, "48f7fe")):
    assert table[at]["bytes"] == raw
    assert code[at - 0x9844D0:at - 0x9844D0 + len(bytes.fromhex(raw))].hex() == raw
review = obj("work/reports/war-peace-api-20261016-r62-independent-review/findings.json")
assert review["sealed"] is True and review["passed"] is True and review["blocking_findings"] == []
assert review["subject_manifest"] == seed["upstream_R62_manifest"] == pin(RAW[ORIGIN + "manifest.json"])
assert seed["upstream_R62_capture"] == pin(RAW[ORIGIN + "capture.json"])
assert seed["upstream_R62_owned"] == pin(RAW[ORIGIN + "owned-code.json"])
assert seed["upstream_R62_selected"] == pin(RAW[ORIGIN + "selected-evidence.json"])
assert not (0x9844D0 <= int(seed["entry_rva"], 16) < 0x98477C)
assert obj(BASE + "inventory.json")["target_body_owned_in_these_sources"] is False
before = {rel: pin(raw) for rel, raw in RAW.items()}
after = {rel: pin(read(rel, value)) for rel, value in before.items()}
assert before == after
resources = {"selected_read_bytes": COUNT, "prior_manual_allowance": 1048576,
             "bounded_upper": COUNT + 1048576, "maximum": 16 * 1024 * 1024}
assert resources["bounded_upper"] <= resources["maximum"]
fp = save("findings.json", {"schema": "EU4-R69-INDEPENDENT-RAW-ENTRY-REVIEW/1", "sealed": True,
    "passed": True, "blocking_findings": [], "entry_seed_pin": before[BASE + "entry-seed.json"],
    "entry_rva": "0x993570", "call_site_rva": "0x98453d", "raw_call": "e82ef00000",
    "scope": "raw_call_entry_seed_only", "subject_source_manifest": before[BASE + "source-manifest.json"],
    "subject_producer": before[BASE + "produce.py"], "subject_entry_seed": before[BASE + "entry-seed.json"],
    "rows_replayed": 14, "continuous_raw_bytes": 72, "callee_body_read": False,
    "registers": {"steady_RSP": "Q62-0x88", "callee_entry_RSP": "Q62-0x90",
        "RCX": "RSI original opaque W, conditional on prior normal callee nonvolatile-register behavior; contents unknown",
        "RDX": "Q62+0x20 borrowed address; no preinitialization or callee outwrite proved",
        "R8": "Q62-0x50, three QWORDs locally zero immediately before CALL",
        "R9": "Unknown; AAAA constant assigned after CALL", "XMM0": "Locally zero128; no consumption proof",
        "flags": "Last XOR R15D,R15D: ZF1/SF0/PF1/CF0/OF0, AF undefined, DF unknown",
        "D": "Fresh post-CALL signed DWORD A8 to RSI; caller D>0 gate, not RAX return or a callee input invariant"},
    "resources": resources, "selected_files_before_after": len(before),
    "limits": ["Three fixed retained R62 JSONs own only 9844d0..98477c. No target body here; no whole-repository absence claim.",
               "No formal native type, safe call, output initialization, unit, recipient, actual effect or lifecycle follows.",
               "No decoder, engine, PE, producer, fixture, game or native access. Source peer plus separate one-shot root grant still required."],
    "native_ready": False, "runtime_capture_authorized": False, "authorizes_retry": False})
mp = save("manifest.json", {"sealed": True, "before": before, "after": after, "findings": fp, "resources": resources})
print(json.dumps({"passed": True, "findings": fp, "manifest": mp, "resources": resources}, ensure_ascii=True))
