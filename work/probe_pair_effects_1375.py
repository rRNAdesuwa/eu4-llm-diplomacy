"""Bounded read-only FRA -> ENG improve_relation observation for one exact build.

sample opens QUERY_INFORMATION | VM_READ only; compare reads saved JSON only.
Neither path writes process memory, invokes game code, submits requests, or
infers rejection from an absent relation. A positive comparison observes a new
relation/mission graph, not causality or general diplomacy execution support.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.probe_diplomacy_current import (
    DATABASE_POINTER_RVA, GAME_POINTER_RVA, MAX_DIPLOMATS, MAX_SLOTS,
    MAX_READ, MAX_TOTAL_READ, MemoryReader, ProcessReader, ProbeError,
    country_identity, pointer, verified_executable,
)
from work.local_config import game_exe
from bridge.native_build import LOCAL_SHA256
from tools.verify_diplomacy_lifecycle import decode, EvidenceError

PROFILE = "1375_fra_eng_improve_relation_v1"
EVIDENCE_SHA256 = "b67e9e3ec3d333ad5603c9bcb7a70d614bab1107f283c6f01d99e7c744730ae0"
# Same complete identities as the separate fixed-pair submit experiment.
PAIR = {"FRA": 0x0100007A00415246, "ENG": 0x0100002E00474E45}
MAX_RELATION_ENTRIES = 4096
MAX_REPORT_BYTES = 8 * 1024 * 1024
RELATION_VTABLE = 0x1C81658
MISSION_VTABLE = 0x1C4B2B8
IMPROVE_TOKEN = 0x2DDB
LIMITATIONS = [
    "Repeated consistent reads are not an atomic game-thread snapshot; transient changes and ABA reuse can escape observation.",
    "Only the selected relation indexes and FRA diplomat missions are observed; no whole-world invariance is claimed.",
    "A new matching graph is an observed state difference, not attribution to any particular request or proof of AI acceptance.",
    "Absence, unreadable data or a changed sample is never interpreted as rejection.",
    "The verified on-disk executable hash and loaded PE identity do not hash every in-memory code byte.",
]


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def integer(value, minimum=0, maximum=0xFFFFFFFF):
    require(type(value) is int and minimum <= value <= maximum, "Invalid bounded integer")
    return value


def address(value, *, nullable=False):
    require(isinstance(value, str) and value.startswith("0x") and len(value) <= 18, "Invalid address encoding")
    try:
        result = int(value, 16)
    except ValueError as exc:
        raise ProbeError("Invalid address encoding") from exc
    if result == 0 and nullable:
        return 0
    return pointer(result)


def u32(reader, location):
    return int.from_bytes(reader.read(location, 4), "little")


def index_snapshot(reader, country, other, array_offset, count_offset):
    records = pointer(reader.qword(address(country["address"]) + 0x1510))
    record = records + other["slot"] * 0x48
    blob = reader.read(record, 0x18)
    root, counterpart = struct.unpack_from("<Q", blob)[0], struct.unpack_from("<Q", blob, 0x10)[0]
    pointer(root)
    require(counterpart == int(other["handle"], 16), "Relation record has a different full counterpart handle")
    array = reader.qword(root + array_offset)
    count = u32(reader, root + count_offset)
    require(count <= MAX_RELATION_ENTRIES, "Relation index exceeds 4096 entries")
    entries = []
    if count:
        pointer(array)
        data = reader.read(array, count * 0x10)
        for offset in range(0, len(data), 0x10):
            slot, obj = struct.unpack_from("<I4xQ", data, offset)
            require(slot < MAX_SLOTS, "Relation index contains an invalid country slot")
            pointer(obj)
            entries.append({"slot": slot, "object": hex(obj)})
    elif array:
        pointer(array)
    return {"records": hex(records), "record": hex(record), "root": hex(root),
            "counterpart_handle": hex(counterpart), "array": hex(array), "count": count,
            "array_offset": hex(array_offset), "count_offset": hex(count_offset), "entries": entries}


def diplomat_snapshot(reader, actor, base):
    holder = pointer(reader.qword(address(actor["address"]) + 0x1480))
    manager = pointer(reader.qword(holder + 0x18))
    begin, end = struct.unpack("<QQ", reader.read(manager + 0x20, 16))
    if begin == end == 0:
        count = 0
    else:
        pointer(begin)
        pointer(end)
        require(end >= begin and (end - begin) % 8 == 0, "Invalid diplomat vector bounds")
        count = (end - begin) // 8
    require(count <= MAX_DIPLOMATS, "Diplomat vector exceeds 256 entries")
    data = reader.read(begin, count * 8) if count else b""
    entries = []
    for index in range(count):
        entry = pointer(struct.unpack_from("<Q", data, index * 8)[0])
        blob = reader.read(entry, 0x48)
        mission = struct.unpack_from("<Q", blob, 0x10)[0]
        item = {"index": index, "address": hex(entry), "state": blob[0x18],
                "envoy_id": struct.unpack_from("<I", blob, 0x44)[0], "mission_pointer": hex(mission), "mission": None}
        if mission:
            pointer(mission)
            body = reader.read(mission, 0xF8)
            item["mission"] = {
                "address": hex(mission), "vtable": hex(struct.unpack_from("<Q", body)[0]),
                "actor_handle": hex(struct.unpack_from("<Q", body, 0x80)[0]),
                "target_handle": hex(struct.unpack_from("<Q", body, 0x88)[0]),
                "action_token": struct.unpack_from("<I", body, 0xA8)[0],
                # 4e77bc explicitly writes a QWORD; +0x50 is a DWORD.
                "entry_pointer": hex(struct.unpack_from("<Q", body, 0x48)[0]),
                "envoy_id": struct.unpack_from("<I", body, 0x50)[0],
                "trip_start_raw_date": struct.unpack_from("<i", body, 0x20)[0],
                "trip_arrival_raw_date": struct.unpack_from("<i", body, 0x24)[0],
            }
        entries.append(item)
    return {"holder": hex(holder), "manager": hex(manager), "begin": hex(begin), "end": hex(end),
            "count": count, "entries": entries}


def sample_once(reader: MemoryReader, base: int) -> dict:
    """Resolve all pointers anew. Never carry a relation pointer between passes."""
    pointer(base)
    database = pointer(reader.qword(base + DATABASE_POINTER_RVA))
    game = pointer(reader.qword(base + GAME_POINTER_RVA))
    array = pointer(reader.qword(database + 0x118))
    date = reader.integer(game + 0x1DD0)
    require(date > 0, "Game date is unavailable")
    player_handle = reader.qword(game + 0x1E60)
    player = country_identity(reader, array, (player_handle >> 32) & 0xFFFF, player_handle)
    require(player is not None, "Player identity is unavailable")
    pair = {}
    for tag, handle in PAIR.items():
        identity = country_identity(reader, array, (handle >> 32) & 0xFFFF, handle)
        require(identity is not None and identity["tag"] == tag, "Fixed pair identity mismatch")
        pair[tag] = identity
    outgoing = index_snapshot(reader, pair["FRA"], pair["ENG"], 0x1D0, 0x1DC)
    incoming = index_snapshot(reader, pair["ENG"], pair["FRA"], 0x1E8, 0x1F4)
    out = [item["object"] for item in outgoing["entries"] if item["slot"] == pair["ENG"]["slot"]]
    inc = [item["object"] for item in incoming["entries"] if item["slot"] == pair["FRA"]["slot"]]
    require(len(out) <= 1 and len(inc) <= 1, "Duplicate pair entries in relation index")
    relation = None
    # A disagreeing index is incomplete evidence, not a reason to follow either
    # potentially removed object. Both independent passes re-resolve indexes.
    if len(out) == len(inc) == 1 and out == inc:
        obj = address(out[0])
        body = reader.read(obj, 0x48)
        relation = {"address": hex(obj), "vtable": hex(struct.unpack_from("<Q", body)[0]),
                    "actor_handle": hex(struct.unpack_from("<Q", body, 0x10)[0]),
                    "target_handle": hex(struct.unpack_from("<Q", body, 0x18)[0]),
                    "started_raw_date": struct.unpack_from("<i", body, 0x20)[0],
                    "removed": body[0x28], "mission_pointer": hex(struct.unpack_from("<Q", body, 0x30)[0])}
    result = {"module_base": hex(base), "database": hex(database), "game": hex(game), "country_array": hex(array),
              "current_raw_date": date, "player": player, "pair": pair,
              "outgoing": outgoing, "incoming": incoming, "relation": relation,
              "diplomats": diplomat_snapshot(reader, pair["FRA"], base)}
    # Independently check identity roots/date again before certifying this pass.
    require(reader.qword(base + DATABASE_POINTER_RVA) == database and reader.qword(base + GAME_POINTER_RVA) == game
            and reader.qword(database + 0x118) == array and reader.integer(game + 0x1DD0) == date
            and reader.qword(game + 0x1E60) == player_handle, "Identity roots or date changed during sample")
    for tag, identity in pair.items():
        require(country_identity(reader, array, identity["slot"], PAIR[tag]) == identity, "Country identity changed during sample")
    return result


def validated_identity(item, expected_handle=None):
    require(isinstance(item, dict) and item.get("identity_valid") is True, "Missing verified country identity")
    slot = integer(item["slot"], 0, MAX_SLOTS - 1)
    address(item["address"])
    handle = item["handle"]
    require(isinstance(handle, str) and handle.startswith("0x") and len(handle) <= 18, "Invalid full country handle")
    handle = int(handle, 16)
    require(0 < handle < 1 << 64 and (handle >> 32) & 0xFFFF == slot, "Country handle slot mismatch")
    tag = (handle & 0xFFFFFF).to_bytes(3, "little").decode("ascii")
    require(item["tag"] == tag and len(tag) == 3 and all(c.isupper() or c.isdigit() for c in tag), "Country tag mismatch")
    require(expected_handle is None or handle == expected_handle, "Fixed pair full handle mismatch")
    return handle


def inspect_graph(sample: dict) -> dict:
    """Recheck raw report fields; recorded success booleans are never sufficient."""
    require(isinstance(sample, dict), "Missing sample")
    base = address(sample["module_base"])
    for key in ("database", "game", "country_array"):
        address(sample[key])
    date = integer(sample["current_raw_date"], 1, 0x7FFFFFFF)
    validated_identity(sample["player"])
    for tag, handle in PAIR.items():
        validated_identity(sample["pair"][tag], handle)
    matches = []
    for key, other, offsets in (("outgoing", "ENG", (0x1D0, 0x1DC)), ("incoming", "FRA", (0x1E8, 0x1F4))):
        idx = sample[key]
        for field in ("records", "record", "root"):
            address(idx[field])
        require(address(idx["record"]) == address(idx["records"]) + sample["pair"][other]["slot"] * 0x48,
                "Relation record address does not match counterpart slot")
        require(idx["counterpart_handle"] == hex(PAIR[other]) and (idx["array_offset"], idx["count_offset"]) == tuple(map(hex, offsets)),
                "Wrong relation index identity or offsets")
        count = integer(idx["count"], 0, MAX_RELATION_ENTRIES)
        address(idx["array"], nullable=count == 0)
        entries = idx["entries"]
        require(isinstance(entries, list) and len(entries) == count, "Relation index count mismatch")
        slots = set()
        match = []
        for item in entries:
            slot = integer(item["slot"], 0, MAX_SLOTS - 1)
            require(slot not in slots, "Duplicate slot in relation index")
            slots.add(slot)
            address(item["object"])
            if slot == sample["pair"][other]["slot"]:
                match.append(item["object"])
        matches.append(match)
    diplomats = sample["diplomats"]
    count = integer(diplomats["count"], 0, MAX_DIPLOMATS)
    for field in ("holder", "manager"):
        address(diplomats[field])
    begin = address(diplomats["begin"], nullable=count == 0)
    end = address(diplomats["end"], nullable=count == 0)
    require(end - begin == count * 8, "Diplomat vector bounds do not match count")
    entries = diplomats["entries"]
    require(isinstance(entries, list) and len(entries) == count, "Diplomat entry count mismatch")
    seen_entries, seen_ids, seen_missions = set(), set(), set()
    for index, entry in enumerate(entries):
        require(type(entry["index"]) is int and entry["index"] == index, "Diplomat ordinal mismatch")
        entry_address = address(entry["address"])
        envoy_id = integer(entry["envoy_id"], 0, 0xFFFFFFFE)
        integer(entry["state"], 0, 255)
        require(entry_address not in seen_entries and envoy_id not in seen_ids, "Duplicate envoy pointer or ID")
        seen_entries.add(entry_address)
        seen_ids.add(envoy_id)
        mission_ptr = address(entry["mission_pointer"], nullable=True)
        mission = entry["mission"]
        if not mission_ptr:
            require(mission is None, "Null mission pointer has an invented mission")
            continue
        require(mission_ptr not in seen_missions and isinstance(mission, dict), "Duplicated or missing mission")
        seen_missions.add(mission_ptr)
        require(address(mission["address"]) == mission_ptr and address(mission["vtable"]) == base + MISSION_VTABLE,
                "Mission pointer or vtable mismatch")
        require(address(mission["entry_pointer"]) == entry_address and integer(mission["envoy_id"]) == envoy_id,
                "Mission does not match envoy entry/ID")
        require(mission["actor_handle"] == hex(PAIR["FRA"]), "FRA envoy mission actor mismatch")
        integer(mission["action_token"])
        integer(mission["trip_start_raw_date"], -0x80000000, 0x7FFFFFFF)
        integer(mission["trip_arrival_raw_date"], -0x80000000, 0x7FFFFFFF)
    relation = sample["relation"]
    if matches == [[], []]:
        require(relation is None, "Absent indexes have an invented relation")
        return {"state": "absent_in_both_indexes", "active_relation": None,
                "matching_mission": None, "rejection_observed": False}
    require(len(matches[0]) == len(matches[1]) == 1 and matches[0] == matches[1], "Pair indexes disagree")
    require(isinstance(relation, dict) and relation["address"] == matches[0][0], "Missing indexed relation object")
    require(address(relation["vtable"]) == base + RELATION_VTABLE, "Not an improve-relation object")
    require(relation["actor_handle"] == hex(PAIR["FRA"]) and relation["target_handle"] == hex(PAIR["ENG"]),
            "Relation actor/target full handle mismatch")
    require(type(relation["removed"]) is int and relation["removed"] == 0, "Relation is removed or has invalid flag")
    integer(relation["started_raw_date"], 1, date)
    mission_ptr = address(relation["mission_pointer"])
    linked = [entry for entry in entries if address(entry["mission_pointer"], nullable=True) == mission_ptr]
    require(len(linked) == 1, "Relation has no unique linked envoy mission")
    entry = linked[0]
    mission = entry["mission"]
    require(entry["state"] in (1, 2) and mission["action_token"] == IMPROVE_TOKEN
            and mission["target_handle"] == hex(PAIR["ENG"]), "Linked mission is not an active FRA -> ENG improvement task")
    return {"state": "active_graph_verified", "active_relation": relation,
            "matching_mission": {"entry_address": entry["address"], "envoy_id": entry["envoy_id"], "mission": mission},
            "rejection_observed": False}


def capture(reader, base):
    result = {"status": "unknown", "passes": [], "graph": None, "errors": [], "atomic_snapshot": False}
    try:
        for _ in range(2):
            sample = sample_once(reader, base)
            result["passes"].append(sample)
            inspect_graph(sample)
        require(result["passes"][0] == result["passes"][1], "Repeated samples differ; retry requires a new report")
        result["graph"] = inspect_graph(result["passes"][1])
        result["status"] = "consistent_bounded_observation"
    except (ProbeError, KeyError, TypeError, ValueError, UnicodeError, struct.error) as exc:
        result["errors"].append(str(exc))
    return result


def process_identity(reader, pid):
    kernel = reader.kernel
    kernel.GetProcessTimes.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
    kernel.GetProcessTimes.restype = W.BOOL
    kernel.GetProcessId.argtypes = [W.HANDLE]
    kernel.GetProcessId.restype = W.DWORD
    times = [W.FILETIME() for _ in range(4)]
    require(kernel.GetProcessId(reader.handle) == pid, "Opened handle PID mismatch")
    if not kernel.GetProcessTimes(reader.handle, *(C.byref(value) for value in times)):
        raise C.WinError(C.get_last_error())
    raw = lambda value: (value.dwHighDateTime << 32) | value.dwLowDateTime
    creation, exited = raw(times[0]), raw(times[1])
    require(creation > 0 and exited == 0, "Process has no valid live creation identity")
    return {"kind": "live_process", "pid": pid, "process_creation_filetime": creation,
            "process_exit_filetime": exited, "module_base": hex(reader.base), "access_rights": "QUERY_INFORMATION | VM_READ"}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def sample_process(pid, executable):
    """Explicit CLI entry only. Unit tests never call this function."""
    build, signature = verified_executable(executable)
    reader = ProcessReader(pid, executable, signature)
    try:
        source = process_identity(reader, pid)
        started = timestamp()
        observation = capture(reader, reader.base)
        finished = timestamp()
        require(process_identity(reader, pid) == source, "Process identity changed during capture")
        return {"schema_version": 1, "kind": "pair_effect_snapshot", "profile": PROFILE,
                "static_evidence_sha256": EVIDENCE_SHA256, "read_only": True,
                "capture_started_at": started, "capture_finished_at": finished,
                "build": build, "source": source, "observation": observation,
                "read_budget": {"bytes_read": reader.bytes_read, "maximum_total": MAX_TOTAL_READ,
                                "maximum_single": MAX_READ, "maximum_relation_entries": MAX_RELATION_ENTRIES,
                                "maximum_diplomats": MAX_DIPLOMATS, "passes": 2},
                "execution_verified": False, "request_causality_verified": False, "limitations": LIMITATIONS}
    finally:
        reader.close()


def validated_snapshot(report):
    require(type(report.get("schema_version")) is int and report["schema_version"] == 1
            and report.get("kind") == "pair_effect_snapshot" and report.get("profile") == PROFILE
            and report.get("static_evidence_sha256") == EVIDENCE_SHA256 and report.get("read_only") is True,
            "Not an accepted bounded pair-effects snapshot")
    require(report["build"]["sha256"].upper() == LOCAL_SHA256, "Unsupported game SHA-256")
    source = report["source"]
    require(source["kind"] == "live_process" and source["access_rights"] == "QUERY_INFORMATION | VM_READ", "Not a live read-only process snapshot")
    integer(source["pid"], 1)
    integer(source["process_creation_filetime"], 1, (1 << 64) - 1)
    require(type(source["process_exit_filetime"]) is int and source["process_exit_filetime"] == 0, "Process was exited at capture")
    address(source["module_base"])
    times = [datetime.fromisoformat(report[key]) for key in ("capture_started_at", "capture_finished_at")]
    require(all(value.tzinfo is not None for value in times) and times[0] <= times[1], "Invalid capture time interval")
    observation = report["observation"]
    require(observation["status"] == "consistent_bounded_observation" and observation["errors"] == [], "Incomplete or unstable observation")
    passes = observation["passes"]
    require(isinstance(passes, list) and len(passes) == 2 and passes[0] == passes[1], "Two identical independent passes are required")
    require(passes[0]["module_base"] == source["module_base"], "Process and sample module bases disagree")
    graph = inspect_graph(passes[0])
    require(observation["graph"] == graph, "Recorded graph differs from independently validated fields")
    return passes[0], graph, times


def compare_reports(before, after):
    result = {"schema_version": 1, "kind": "pair_effect_comparison", "profile": PROFILE,
              "status": "unknown", "observed_effect": False, "scope": "new_fra_eng_improve_relation_graph",
              "execution_verified": False, "request_causality_verified": False, "ai_acceptance_verified": False,
              "whole_world_unchanged_verified": False, "rejection_observed": False,
              "errors": [], "limitations": LIMITATIONS}
    try:
        prior, prior_graph, prior_times = validated_snapshot(before)
        current, current_graph, current_times = validated_snapshot(after)
        require(before["source"] == after["source"], "PID, process creation identity or module changed")
        require(prior_times[1] <= current_times[0] and prior_times[0] < current_times[1], "Reports are reversed or overlap")
        require(prior["pair"] == current["pair"] and prior["player"] == current["player"], "Pair or player identity changed")
        require(current["current_raw_date"] >= prior["current_raw_date"], "Raw date moved backwards")
        require(all(prior[key] == current[key] for key in ("database", "game", "country_array")), "World identity roots changed")
        result.update(source=after["source"], game_sha256=LOCAL_SHA256,
                      raw_dates={"before": prior["current_raw_date"], "after": current["current_raw_date"]},
                      before_state=prior_graph["state"], after_state=current_graph["state"])
        if prior_graph["state"] != "absent_in_both_indexes":
            result["reason"] = "Baseline already contained a matching relation; this first-send comparison cannot prove an added relation."
        elif current_graph["state"] != "active_graph_verified":
            result["reason"] = "No new matching active graph observed; pending, delayed, cancelled and rejected outcomes remain unresolved."
        else:
            relation = current_graph["active_relation"]
            require(relation["started_raw_date"] >= prior["current_raw_date"], "Newly seen relation predates the baseline")
            matching = current_graph["matching_mission"]
            prior_missions = [entry["mission"] for entry in prior["diplomats"]["entries"] if entry["mission"] is not None]
            # A pre-existing matching task is insufficient evidence of a new
            # task, even if its relation was temporarily absent from indexes.
            require(not any(mission["action_token"] == IMPROVE_TOKEN
                            and mission["actor_handle"] == hex(PAIR["FRA"])
                            and mission["target_handle"] == hex(PAIR["ENG"]) for mission in prior_missions),
                    "A matching improvement mission already existed in the baseline")
            result.update(status="observed_effect", observed_effect=True, relation=relation, matching_mission=matching,
                          reason="Both indexes newly reference the same active improvement relation and its matching envoy mission.")
    except (ProbeError, KeyError, TypeError, ValueError, AttributeError, UnicodeError) as exc:
        result["errors"].append(str(exc))
    return result


def read_report(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_REPORT_BYTES + 1)
    require(len(data) <= MAX_REPORT_BYTES, "Report exceeds 8 MiB")
    return decode(data), hashlib.sha256(data).hexdigest()


def write_report(path, report, inputs=()):
    path = Path(path)
    for source in inputs:
        source = Path(source)
        require(path.resolve() != source.resolve() and not (path.exists() and source.exists() and path.samefile(source)),
                "Output must not overwrite an input")
    # Reports are evidence snapshots: preserve existing bytes, including hardlinks.
    data = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    require(len(data) <= MAX_REPORT_BYTES, "Output exceeds 8 MiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sample = sub.add_parser("sample", help="Explicit read-only game observation; never runs native code")
    sample.add_argument("--pid", type=int, required=True)
    sample.add_argument("--exe", type=Path)
    sample.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare", help="Offline comparison of two captured reports")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), "Output already exists; choose a new evidence filename")
        if args.mode == "sample":
            executable = args.exe or game_exe()
            report = sample_process(args.pid, executable)
            write_report(args.output, report, (executable,))
            okay = report["observation"]["status"] == "consistent_bounded_observation"
        else:
            before, before_hash = read_report(args.before)
            after, after_hash = read_report(args.after)
            report = compare_reports(before, after)
            report["inputs"] = {"before_sha256": before_hash, "after_sha256": after_hash}
            write_report(args.output, report, (args.before, args.after))
            okay = report["observed_effect"]
        print(json.dumps({"output": str(args.output), "status": report.get("status", report.get("observation", {}).get("status")),
                          "observed_effect": report.get("observed_effect", False), "execution_verified": False}))
        return 0 if okay else 2
    except (ProbeError, EvidenceError, OSError, ValueError, RuntimeError) as exc:
        print(f"Pair effect probe: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
