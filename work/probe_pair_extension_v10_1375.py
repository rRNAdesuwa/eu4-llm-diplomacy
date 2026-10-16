"""Read-only exact-build seven-family observations; sample or offline compare.

No process is opened on import. sample uses QUERY_INFORMATION | VM_READ only.
This profile measures explicit indexed relations and the outgoing embargo bit,
not conditional movement permission, AI acceptance or request causality.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_diplomacy_relations_v7_1375 as core

base = core.base
require, integer, address = base.require, base.integer, base.address
PROFILE = "1375_pair_extension_observation_v10_1"
EVIDENCE_SHA256 = "b6f4b69db38f5e3eae0c3cebf1fa5298701b86a98e8299d6f0e9759b84861f62"
EXTENSION_SHA256 = "0c1731b0b29b296da73dc406fb31544ada59c17c275d17d623677b16998698bd"
HANDLES, TARGETS = core.HANDLES, core.TARGETS
# left/right mean FRA/target indexes. Access objects always store holder at
# +10, grantor at +18; changing family changes indexes and expected direction.
RELATIONS = {
    "allianceaction": (0x80, 0x8C, 0x80, 0x8C, 0x1C7A740, "symmetric"),
    "milaccess": (0xB0, 0xBC, 0xC8, 0xD4, 0x1CDDE60, "forward"),
    "offermilaccess": (0xC8, 0xD4, 0xB0, 0xBC, 0x1CDDE60, "reverse"),
    "fleet_access": (0xE0, 0xEC, 0xF8, 0x104, 0x1CDDEE0, "forward"),
    "offer_fleet_access": (0xF8, 0x104, 0xE0, 0xEC, 0x1CDDEE0, "reverse"),
    "warsubsidy": (0x110, 0x11C, 0x110, 0x11C, 0x1C815D8, "forward"),
}
ACTIONS = tuple(RELATIONS) + ("embargoaction",)
ACCESS = frozenset(("milaccess", "offermilaccess", "fleet_access", "offer_fleet_access"))
LIMITATIONS = [
    "Two complete identical passes are bounded observations, not an atomic game-thread snapshot; transient changes and ABA reuse can escape them.",
    "Only selected pair indexes/objects and embargo flags are observed. World pointers, dates and TAGs do not establish a reliable world epoch.",
    "An indexed military agreement differs from conditional/automatic movement permission; missing agreement does not mean movement is forbidden.",
    "Ask and offer are distinct families. Access objects store holder then grantor, and the observer selects the corresponding opposite indexes.",
    "Alliance presence is symmetric and cannot identify its initiating country; cancellation may have other native effects such as truce.",
    "A new or removed state is not attribution to a request, proof of AI acceptance or proof of complete world invariance.",
    "Absence, unreadable data, mismatched indexes or unstable sampling never imply rejection.",
    "The on-disk EXE hash and loaded PE identity do not hash every in-memory code byte.",
]


def record_snapshot(reader, country, other):
    records = base.pointer(reader.qword(address(country["address"]) + 0x1510))
    location = records + other["slot"] * 0x48
    raw = reader.read(location, 0x48)
    counterpart = struct.unpack_from("<Q", raw, 0x10)[0]
    require(counterpart == int(other["handle"], 16), "Record counterpart full handle mismatch")
    return {"records": hex(records), "record": hex(location), "counterpart_handle": hex(counterpart), "flags_46": raw[0x46]}


def relation_snapshot(reader, identity, target, action):
    actor, recipient = identity["pair"]["FRA"], identity["pair"][target]
    aoff, acount, boff, bcount, vt, _ = RELATIONS[action]
    left = base.index_snapshot(reader, actor, recipient, aoff, acount)
    right = base.index_snapshot(reader, recipient, actor, boff, bcount)
    a = core.validate_index(left, recipient, (aoff, acount))
    b = core.validate_index(right, actor, (boff, bcount))
    require(len(a) <= 1 and len(b) <= 1 and a == b, "Selected relation indexes disagree")
    obj = None
    if a:
        location = address(a[0])
        header = reader.read(location, 0x30)
        require(struct.unpack_from("<Q", header)[0] == address(identity["module_base"]) + vt,
                "Selected object vtable differs from relation profile")
        obj = {"address": a[0], "vtable": hex(struct.unpack_from("<Q", header)[0]),
               "type_marker": struct.unpack_from("<I", header, 8)[0],
               "first_handle": hex(struct.unpack_from("<Q", header, 0x10)[0]),
               "second_handle": hex(struct.unpack_from("<Q", header, 0x18)[0]),
               "started_raw_date": struct.unpack_from("<i", header, 0x20)[0], "removed": header[0x28]}
        if action in ACCESS:
            obj["enforce_peace"] = reader.read(location + 0x40, 1)[0]
        elif action == "warsubsidy":
            obj["monthly_milli"], obj["duration_years"] = struct.unpack("<ii", reader.read(location + 0x40, 8))
    return {"left": left, "right": right, "object": obj}


def sample_once(reader, module_base, target, action):
    require(action in ACTIONS, "Unsupported family")
    identity = core.read_identity(reader, module_base, target)
    result = {**identity, "target": target, "action": action}
    if action == "embargoaction":
        result["embargo"] = {
            "outgoing": record_snapshot(reader, identity["pair"]["FRA"], identity["pair"][target]),
            "incoming": record_snapshot(reader, identity["pair"][target], identity["pair"]["FRA"]),
        }
    else:
        result["relation"] = relation_snapshot(reader, identity, target, action)
    require(core.read_identity(reader, module_base, target) == identity, "Date/world/country identity changed during sampling")
    return result


def inspect_state(sample):
    target, action = sample["target"], sample["action"]
    require(target in TARGETS and action in ACTIONS, "Unsupported pair/family")
    for key in ("module_base", "database", "game", "country_array"):
        address(sample[key])
    integer(sample["current_raw_date"], 1, 0x7FFFFFFF)
    base.validated_identity(sample["player"])
    for tag in ("FRA", target):
        base.validated_identity(sample["pair"][tag], HANDLES[tag])
    result = {"state": "absent", "object": None, "rejection_observed": False}
    if action == "embargoaction":
        for key, other in (("outgoing", target), ("incoming", "FRA")):
            row = sample["embargo"][key]
            require(address(row["record"]) == address(row["records"]) + sample["pair"][other]["slot"] * 0x48
                    and row["counterpart_handle"] == hex(HANDLES[other]), "Embargo record identity mismatch")
            integer(row["flags_46"], 0, 255)
        outgoing, incoming = (bool(sample["embargo"][key]["flags_46"] & 2) for key in ("outgoing", "incoming"))
        return {**result, "state": "active" if outgoing else "absent", "outgoing_embargo": outgoing, "incoming_embargo": incoming}
    aoff, acount, boff, bcount, vt, direction = RELATIONS[action]
    data = sample["relation"]
    left = core.validate_index(data["left"], sample["pair"][target], (aoff, acount))
    right = core.validate_index(data["right"], sample["pair"]["FRA"], (boff, bcount))
    obj = data["object"]
    if left == right == []:
        require(obj is None, "Absent indexes cannot claim an object")
        return result
    require(len(left) == len(right) == 1 and left == right and isinstance(obj, dict), "Relation indexes disagree")
    require(obj["address"] == left[0] and address(obj["vtable"]) == address(sample["module_base"]) + vt,
            "Relation object/vtable identity mismatch")
    require(type(obj["type_marker"]) is int and obj["type_marker"] == 0x165, "Relation type marker mismatch")
    require(type(obj["removed"]) is int and obj["removed"] == 0, "Indexed relation is marked removed")
    integer(obj["started_raw_date"], 1, sample["current_raw_date"])
    forward = (hex(HANDLES["FRA"]), hex(HANDLES[target]))
    actual = (obj["first_handle"], obj["second_handle"])
    require(actual in (forward, forward[::-1]), "Relation full handles differ from pair")
    expected = forward[::-1] if direction == "reverse" else forward
    if direction != "symmetric" and actual != expected:
        # Subsidies share undirected indexes and may validly describe an incoming
        # payment. Directional access indexes must never point at the reverse right.
        require(action == "warsubsidy", "Access relation direction disagrees with family/indexes")
        result["state"] = "reverse_relation"
    else:
        result["state"] = "active"
    result.update(object=obj, object_direction="FRA_to_target" if actual == forward else "target_to_FRA")
    if action in ACCESS:
        flag = integer(obj["enforce_peace"], 0, 1)
        if flag:
            result["state"] = "enforce_peace_relation"
    elif action == "warsubsidy":
        integer(obj["monthly_milli"], 0, 0x7FFFFFFF)
        integer(obj["duration_years"], 1, 0x7FFFFFFF)
        expiry = obj["started_raw_date"] + obj["duration_years"] * 0x2238
        require(expiry <= 0x7FFFFFFF, "Subsidy expiry exceeds signed native date range")
        result["nominal_expiry_raw_date"] = expiry
        # Arithmetic is reported as a selected native formula; no promise that
        # a future running frame will preserve this relation until that date.
    return result


def capture(reader, module_base, target, action):
    result = {"status": "unknown", "passes": [], "state": None, "errors": [], "atomic_snapshot": False}
    try:
        for _ in range(2):
            value = sample_once(reader, module_base, target, action)
            result["passes"].append(value)
            inspect_state(value)
        require(result["passes"][0] == result["passes"][1], "Repeated samples differ")
        result.update(state=inspect_state(result["passes"][1]), status="consistent_bounded_observation")
    except (base.ProbeError, KeyError, TypeError, ValueError, UnicodeError, struct.error) as exc:
        result["errors"].append(str(exc))
    return result


def sample_process(pid, executable, target, action):
    build, signature = base.verified_executable(executable)
    reader = base.ProcessReader(pid, executable, signature)
    try:
        source = base.process_identity(reader, pid)
        started = base.timestamp()
        observation = capture(reader, reader.base, target, action)
        finished = base.timestamp()
        require(base.process_identity(reader, pid) == source, "Process identity changed")
        return {"schema_version": 1, "kind": "pair_extension_snapshot", "profile": PROFILE,
                "static_effect_evidence_sha256": EVIDENCE_SHA256, "static_extension_evidence_sha256": EXTENSION_SHA256,
                "read_only": True, "capture_started_at": started, "capture_finished_at": finished,
                "build": build, "source": source, "action": action, "actor": "FRA", "target": target,
                "observation": observation, "execution_verified": False, "request_causality_verified": False,
                "read_budget": {"bytes_read": reader.bytes_read, "maximum_total": base.MAX_TOTAL_READ,
                                "maximum_single": base.MAX_READ, "maximum_relation_entries": base.MAX_RELATION_ENTRIES,
                                "passes": 2}, "limitations": LIMITATIONS}
    finally:
        reader.close()


def validated_report(report):
    require(type(report["schema_version"]) is int and report["schema_version"] == 1 and report["profile"] == PROFILE
            and report["kind"] == "pair_extension_snapshot" and report["read_only"] is True
            and report["static_effect_evidence_sha256"] == EVIDENCE_SHA256
            and report["static_extension_evidence_sha256"] == EXTENSION_SHA256, "Unsupported observation profile/evidence")
    require(report["build"]["sha256"].upper() == base.LOCAL_SHA256, "Wrong game build")
    require(report["actor"] == "FRA" and report["target"] in TARGETS and report["action"] in ACTIONS, "Wrong pair/family")
    source = report["source"]
    require(source["kind"] == "live_process" and source["access_rights"] == "QUERY_INFORMATION | VM_READ", "Not a read-only process snapshot")
    integer(source["pid"], 1)
    integer(source["process_creation_filetime"], 1, (1 << 64) - 1)
    require(type(source["process_exit_filetime"]) is int and source["process_exit_filetime"] == 0, "Process was exited")
    address(source["module_base"])
    times = [base.datetime.fromisoformat(report[key]) for key in ("capture_started_at", "capture_finished_at")]
    require(all(x.tzinfo is not None for x in times) and times[0] <= times[1], "Invalid capture time interval")
    observation = report["observation"]
    require(observation["status"] == "consistent_bounded_observation" and observation["errors"] == [], "Incomplete/unstable observation")
    passes = observation["passes"]
    require(isinstance(passes, list) and len(passes) == 2 and passes[0] == passes[1], "Two identical complete passes required")
    sample = passes[0]
    require(sample["target"] == report["target"] and sample["action"] == report["action"] and sample["module_base"] == source["module_base"], "Report/sample identity differs")
    state = inspect_state(sample)
    require(state == observation["state"], "Stored state differs from raw fields")
    return sample, state, times


def compare_reports(before, after, direction="positive", expected_subsidy=None):
    result = {"schema_version": 1, "kind": "pair_extension_comparison", "profile": PROFILE,
              "status": "unknown", "direction": direction, "observed_effect": False,
              "execution_verified": False, "request_causality_verified": False, "ai_acceptance_verified": False,
              "rejection_observed": False, "whole_world_unchanged_verified": False, "errors": [], "limitations": LIMITATIONS}
    try:
        require(direction in ("positive", "cancel"), "Unsupported comparison direction")
        prior, old, old_times = validated_report(before)
        current, new, new_times = validated_report(after)
        require(before["source"] == after["source"], "Process identity/creation/base changed")
        require((before["action"], before["target"]) == (after["action"], after["target"]), "Different action/pair reports")
        require(old_times[1] <= new_times[0] and old_times[0] < new_times[1], "Capture intervals overlap/reverse")
        require(all(prior[key] == current[key] for key in ("pair", "player", "database", "game", "country_array")), "World or country identity changed")
        require(current["current_raw_date"] >= prior["current_raw_date"], "Date moved backwards")
        if expected_subsidy is not None:
            require(before["action"] == "warsubsidy" and isinstance(expected_subsidy, tuple) and len(expected_subsidy) == 2,
                    "Expected amount/years apply only to subsidies")
            amount, years = expected_subsidy
            integer(amount, 0, 0x7FFFFFFF)
            integer(years, 1, 0x7FFFFFFF)
            selected = new if direction == "positive" else old
            require(selected["state"] == "active" and selected["object"]["monthly_milli"] == amount
                    and selected["object"]["duration_years"] == years, "Subsidy amount/year expectation mismatch")
            result["expected_subsidy"] = {"monthly_milli": amount, "duration_years": years}
        result.update(source=after["source"], action=after["action"], actor="FRA", target=after["target"],
                      raw_dates={"before": prior["current_raw_date"], "after": current["current_raw_date"]}, before_state=old, after_state=new)
        if direction == "positive" and old["state"] == "absent" and new["state"] == "active":
            if before["action"] != "embargoaction":
                require(new["object"]["started_raw_date"] >= prior["current_raw_date"], "Added indexed relation predates baseline")
            result.update(status="observed_effect", observed_effect=True, transition="added_selected_state")
        elif direction == "cancel" and old["state"] == "active" and new["state"] == "absent":
            result.update(status="observed_effect", observed_effect=True, transition="removed_selected_state")
    except (base.ProbeError, KeyError, TypeError, ValueError) as exc:
        result["errors"].append(str(exc))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--pid", type=int, required=True)
    sample.add_argument("--exe", type=Path)
    sample.add_argument("--target", choices=TARGETS, required=True)
    sample.add_argument("--action", choices=ACTIONS, required=True)
    sample.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--direction", choices=("positive", "cancel"), required=True)
    compare.add_argument("--expected-monthly-milli", type=int)
    compare.add_argument("--expected-duration-years", type=int)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), "Output exists; choose a new evidence filename")
        if args.mode == "sample":
            executable = args.exe or base.game_exe()
            result = sample_process(args.pid, executable, args.target, args.action)
            base.write_report(args.output, result, (executable,))
            okay = result["observation"]["status"] == "consistent_bounded_observation"
        else:
            require((args.expected_monthly_milli is None) == (args.expected_duration_years is None), "Supply both amount and years expectations")
            expected = None if args.expected_monthly_milli is None else (args.expected_monthly_milli, args.expected_duration_years)
            before, bh = base.read_report(args.before)
            after, ah = base.read_report(args.after)
            result = compare_reports(before, after, args.direction, expected)
            result["inputs"] = {"before_sha256": bh, "after_sha256": ah}
            base.write_report(args.output, result, (args.before, args.after))
            okay = result["observed_effect"]
        print(json.dumps({"output": str(args.output), "status": result.get("status", result.get("observation", {}).get("status")),
                          "observed_effect": result.get("observed_effect", False), "execution_verified": False}))
        return 0 if okay else 2
    except (base.ProbeError, base.EvidenceError, OSError, ValueError, RuntimeError) as exc:
        print(f"Pair extension observer: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
