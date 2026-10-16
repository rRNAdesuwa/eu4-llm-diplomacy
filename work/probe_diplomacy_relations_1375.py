"""Read-only, bounded core diplomacy observations; explicit sample or offline compare.

FRA -> ENG/POR only. No game writes, engine calls, injection or automatic probes.
The original, live-validated single-pair observer remains unchanged. This module
reports selected state transitions; it never attributes them to a request,
infers rejection from missing state, or enables an execution backend.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_pair_effects_1375 as base

PROFILE = "1375_core_relation_observation_v1"
CANCEL_EVIDENCE_SHA256 = "54dc047d85fe8c06528d5fb3824a1928f56fac2c4bbf24c26e205bcfb08e0df3"
HANDLES = {**base.PAIR, "POR": 0x010000BD00524F50}
TOKENS = {"improve_relation": 0x2DDB, "spy_network": 0x3378, "guaranteeaction": 0x2941,
          "royal_marriage": 0x28DF, "vassalaction": 0x2940}
# Directional improve uses outgoing and incoming; the other indexes are visible
# from either country and must be interpreted using the object's full handles.
RELATIONS = {
    "improve_relation": (0x1D0, 0x1DC, 0x1E8, 0x1F4, 0x48, 0x1C81658),
    "guaranteeaction": (0x1A0, 0x1AC, 0x1A0, 0x1AC, 0x48, 0x1C817D8),
    "royal_marriage": (0x68, 0x74, 0x68, 0x74, 0x40, 0x1C80BE0),
    "vassalaction": (0x128, 0x134, 0x128, 0x134, 0x90, 0x1C81758),
}
SPY_TASK_VTABLE = 0x1CE3BA0
MAX_TASKS = 1024
MAX_TYPE_NAME = 128
TYPE_NAME = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
require, integer, address = base.require, base.integer, base.address
LIMITATIONS = base.LIMITATIONS + [
    "Marriage is symmetric; a newly observed marriage does not identify which country initiated it or expose its reply event.",
    "Dependency objects may represent many subject types. An unresolved native type name cannot verify vassalization.",
    "Removal verifies selected indexed state, not which cancellation, war, event, death or other rule caused it.",
    "No pending-reply queue or matching rejection event is captured by this observer.",
]


def read_identity(reader, module_base, target):
    require(target in ("ENG", "POR"), "Only ENG/POR targets are supported")
    database = base.pointer(reader.qword(module_base + base.DATABASE_POINTER_RVA))
    game = base.pointer(reader.qword(module_base + base.GAME_POINTER_RVA))
    countries = base.pointer(reader.qword(database + 0x118))
    date = reader.integer(game + 0x1DD0)
    require(date > 0, "Game date unavailable")
    player_handle = reader.qword(game + 0x1E60)
    player = base.country_identity(reader, countries, (player_handle >> 32) & 0xFFFF, player_handle)
    require(player is not None, "Player country missing")
    pair = {}
    for tag in ("FRA", target):
        handle = HANDLES[tag]
        item = base.country_identity(reader, countries, (handle >> 32) & 0xFFFF, handle)
        require(item is not None and item["tag"] == tag, "Fixed full country identity mismatch")
        pair[tag] = item
    return {"module_base": hex(module_base), "database": hex(database), "game": hex(game), "country_array": hex(countries),
            "current_raw_date": date, "player": player, "pair": pair}


def diplomats(reader, actor, module_base):
    result = base.diplomat_snapshot(reader, actor, module_base)
    # Reuse the established bounded entry/mission reader. Extra fields are read
    # independently and included in both complete repeated passes.
    for entry in result["entries"]:
        mission = entry["mission"]
        if mission is not None:
            location = address(mission["address"])
            mission["task_pointer"] = hex(reader.qword(location + 0xA0))
    return result


def dependency_name(reader, definition):
    """a62b75/86/8d select inline-vs-pointer using name+0x18 capacity.

    b2344f/95140/951a4 establish QWORD length at +0x10. This is
    observation of a type key, not an execution-ready definition registry.
    """
    base.pointer(definition)
    location = definition + 0x10
    header = reader.read(location, 0x20)
    length = struct.unpack_from("<Q", header, 0x10)[0]
    capacity = struct.unpack_from("<Q", header, 0x18)[0]
    require(0 < length <= min(capacity, MAX_TYPE_NAME), "Dependency type name exceeds length/capacity bounds")
    if capacity < 16:
        data = header[:16]
        storage = "inline"
        chars = location
    else:
        chars = base.pointer(struct.unpack_from("<Q", header)[0])
        data = reader.read(chars, length + 1)
        storage = "heap"
    terminator = data.find(b"\0")
    require(terminator == length, "Dependency type name terminator does not match its length")
    name = data[:terminator].decode("ascii")
    require(TYPE_NAME.fullmatch(name) is not None, "Dependency type name is not a bounded ASCII key")
    return {"name": name, "storage": storage, "length": length, "capacity": capacity, "characters": hex(chars),
            "terminator_offset": terminator, "length_field_interpreted": True,
            "evidence": "a62b75/a62b86/a62b8d/b2344f/95140/951a4"}


def relation_snapshot(reader, identity, target, action):
    actor, recipient = identity["pair"]["FRA"], identity["pair"][target]
    aoff, acount, boff, bcount, size, _ = RELATIONS[action]
    left = base.index_snapshot(reader, actor, recipient, aoff, acount)
    right = base.index_snapshot(reader, recipient, actor, boff, bcount)
    a = [x["object"] for x in left["entries"] if x["slot"] == recipient["slot"]]
    b = [x["object"] for x in right["entries"] if x["slot"] == actor["slot"]]
    require(len(a) <= 1 and len(b) <= 1, "Duplicate pair index entries")
    obj = None
    if len(a) == len(b) == 1 and a == b:
        blob = reader.read(address(a[0]), size)
        obj = {"address": a[0], "vtable": hex(struct.unpack_from("<Q", blob)[0]),
               "actor_handle": hex(struct.unpack_from("<Q", blob, 0x10)[0]),
               "target_handle": hex(struct.unpack_from("<Q", blob, 0x18)[0]),
               "started_raw_date": struct.unpack_from("<i", blob, 0x20)[0], "removed": blob[0x28]}
        if action == "improve_relation":
            obj["mission_pointer"] = hex(struct.unpack_from("<Q", blob, 0x30)[0])
        if action == "vassalaction":
            definition = struct.unpack_from("<Q", blob, 0x40)[0]
            obj["type_definition"] = hex(definition)
            obj["type_name"] = dependency_name(reader, definition)
    result = {"left": left, "right": right, "object": obj}
    if action == "vassalaction":
        result["overlords"] = {tag: hex(reader.qword(address(country["address"]) + 0x18F0))
                               for tag, country in identity["pair"].items()}
    return result


def spy_snapshot(reader, identity, target):
    actor, recipient = identity["pair"]["FRA"], identity["pair"][target]
    records = base.pointer(reader.qword(address(actor["address"]) + 0x1510))
    record_address = records + recipient["slot"] * 0x48
    body = reader.read(record_address, 0x48)
    counterpart = struct.unpack_from("<Q", body, 0x10)[0]
    require(counterpart == HANDLES[target], "Spy relation counterpart full handle mismatch")
    owner = base.pointer(reader.qword(address(recipient["address"]) + 0x14B0))
    head, tail, count = struct.unpack("<QQI", reader.read(owner + 0x4F0, 20))
    require(count <= MAX_TASKS, "Target task list exceeds 1024 nodes")
    nodes, seen = [], set()
    current = head
    for _ in range(count):
        base.pointer(current)
        require(current not in seen, "Cycle in target task list")
        seen.add(current)
        node = reader.read(current, 0x20)
        task, previous, following = struct.unpack_from("<QQQ", node)
        item = {"address": hex(current), "task_pointer": hex(task), "previous": hex(previous),
                "next": hex(following), "removed": node[0x18], "task": None}
        # Do not follow a removed node's possibly freed task pointer.
        if item["removed"] == 0:
            base.pointer(task)
            vt = reader.qword(task)
            item["task_vtable"] = hex(vt)
            if vt == address(identity["module_base"]) + SPY_TASK_VTABLE:
                blob = reader.read(task, 0x50)
                item["task"] = {"address": hex(task), "vtable": hex(struct.unpack_from("<Q", blob)[0]),
                                "owner": hex(struct.unpack_from("<Q", blob, 0x10)[0]),
                                "actor_handle": hex(struct.unpack_from("<Q", blob, 0x18)[0]),
                                "target_handle": hex(struct.unpack_from("<Q", blob, 0x20)[0]),
                                "envoy_id": struct.unpack_from("<I", blob, 0x2C)[0]}
        nodes.append(item)
        current = following
    require(current == 0, "Target task list did not terminate at its count")
    return {"records": hex(records), "record": hex(record_address), "counterpart_handle": hex(counterpart),
            "flags_46": body[0x46], "network_raw_i16": struct.unpack_from("<h", body, 0x18)[0],
            "owner": hex(owner), "head": hex(head), "tail": hex(tail), "count": count, "nodes": nodes}


def sample_once(reader, module_base, target, action):
    require(action in TOKENS, "Unsupported action")
    identity = read_identity(reader, module_base, target)
    result = {**identity, "target": target, "action": action}
    if action == "spy_network":
        result["spy"] = spy_snapshot(reader, identity, target)
    else:
        result["relation"] = relation_snapshot(reader, identity, target, action)
    result["diplomats"] = diplomats(reader, identity["pair"]["FRA"], module_base)
    require(read_identity(reader, module_base, target) == identity, "Date, world or country identity changed during sampling")
    return result


def validate_missions(sample):
    data = sample["diplomats"]
    count = integer(data["count"], 0, base.MAX_DIPLOMATS)
    for key in ("holder", "manager"):
        address(data[key])
    begin, end = (address(data[key], nullable=count == 0) for key in ("begin", "end"))
    require(end - begin == count * 8, "Diplomat count/bounds mismatch")
    entries = data["entries"]
    require(isinstance(entries, list) and len(entries) == count, "Diplomat count mismatch")
    pointers, ids, missions = set(), set(), set()
    for index, entry in enumerate(entries):
        require(type(entry["index"]) is int and entry["index"] == index, "Diplomat ordinal mismatch")
        ptr, envoy = address(entry["address"]), integer(entry["envoy_id"], 0, 0xFFFFFFFE)
        integer(entry["state"], 0, 255)
        require(ptr not in pointers and envoy not in ids, "Duplicate envoy pointer or ID")
        pointers.add(ptr)
        ids.add(envoy)
        mission_pointer = address(entry["mission_pointer"], nullable=True)
        mission = entry["mission"]
        if not mission_pointer:
            require(mission is None, "Invented mission for null pointer")
            continue
        require(mission_pointer not in missions and isinstance(mission, dict), "Missing or duplicate mission")
        missions.add(mission_pointer)
        require(address(mission["address"]) == mission_pointer and address(mission["vtable"]) == address(sample["module_base"]) + base.MISSION_VTABLE,
                "Mission identity/vtable mismatch")
        require(address(mission["entry_pointer"]) == ptr and integer(mission["envoy_id"]) == envoy, "Mission envoy linkage mismatch")
        require(mission["actor_handle"] == hex(HANDLES["FRA"]), "Mission actor mismatch")
        integer(mission["action_token"])
        address(mission["task_pointer"], nullable=True)
        for key in ("trip_start_raw_date", "trip_arrival_raw_date"):
            integer(mission[key], -0x80000000, 0x7FFFFFFF)
    return entries


def pair_missions(sample, entries, *, with_task=False):
    selected = []
    for entry in entries:
        mission = entry["mission"]
        if mission is not None and mission["action_token"] == TOKENS[sample["action"]] and mission["target_handle"] == hex(HANDLES[sample["target"]]):
            if not with_task or address(mission["task_pointer"], nullable=True):
                selected.append(entry)
    return selected


def validate_index(idx, other, offsets):
    for key in ("records", "record", "root"):
        address(idx[key])
    require(address(idx["record"]) == address(idx["records"]) + other["slot"] * 0x48, "Relation record address mismatch")
    require(idx["counterpart_handle"] == other["handle"]
            and (idx["array_offset"], idx["count_offset"]) == tuple(map(hex, offsets)), "Relation index identity/profile mismatch")
    count = integer(idx["count"], 0, base.MAX_RELATION_ENTRIES)
    address(idx["array"], nullable=count == 0)
    require(isinstance(idx["entries"], list) and len(idx["entries"]) == count, "Index count mismatch")
    slots, matches = set(), []
    for item in idx["entries"]:
        slot = integer(item["slot"], 0, base.MAX_SLOTS - 1)
        require(slot not in slots, "Duplicate country slot in relation index")
        slots.add(slot)
        address(item["object"])
        if slot == other["slot"]:
            matches.append(item["object"])
    return matches


def relation_state(sample, entries):
    action, target = sample["action"], sample["target"]
    data = sample["relation"]
    aoff, acount, boff, bcount, _, vtable = RELATIONS[action]
    left = validate_index(data["left"], sample["pair"][target], (aoff, acount))
    right = validate_index(data["right"], sample["pair"]["FRA"], (boff, bcount))
    obj = data["object"]
    if left == right == []:
        require(obj is None, "Object is absent from current indexes")
        if action == "vassalaction":
            require(data["overlords"][target] != hex(HANDLES["FRA"]), "Target overlord contradicts absent dependency")
        return {"state": "absent", "object": None, "matching_mission": None}
    require(len(left) == len(right) == 1 and left == right and isinstance(obj, dict), "Relation indexes disagree")
    require(obj["address"] == left[0] and address(obj["vtable"]) == address(sample["module_base"]) + vtable, "Wrong relation object or vtable")
    require(type(obj["removed"]) is int and obj["removed"] == 0, "Indexed relation is removed")
    integer(obj["started_raw_date"], 1, sample["current_raw_date"])
    observed = (obj["actor_handle"], obj["target_handle"])
    forward = (hex(HANDLES["FRA"]), hex(HANDLES[target]))
    require(observed in (forward, forward[::-1]), "Relation full handles differ from selected pair")
    result = {"state": "active", "object": obj, "matching_mission": None,
              "direction": "FRA_to_target" if observed == forward else "target_to_FRA"}
    if action != "royal_marriage" and observed != forward:
        require(action != "improve_relation", "Outgoing improvement has reversed direction")
        result["state"] = "reverse_relation"
    if action == "improve_relation":
        ptr = address(obj["mission_pointer"])
        matching = [entry for entry in pair_missions(sample, entries) if address(entry["mission_pointer"], nullable=True) == ptr]
        require(len(matching) == 1 and matching[0]["state"] in (1, 2), "Improvement has no unique matching envoy mission")
        result["matching_mission"] = matching[0]
    if action == "vassalaction":
        definition = address(obj["type_definition"])
        name = obj["type_name"]
        require(isinstance(name, dict) and isinstance(name["name"], str) and TYPE_NAME.fullmatch(name["name"]) is not None,
                "Missing or unbounded dependency type key")
        capacity = integer(name["capacity"], 0, (1 << 64) - 1)
        length = integer(name["length"], 1, MAX_TYPE_NAME)
        require(type(name["terminator_offset"]) is int and name["terminator_offset"] == length == len(name["name"]) <= capacity
                and name["length_field_interpreted"] is True and name["evidence"] == "a62b75/a62b86/a62b8d/b2344f/95140/951a4",
                "Dependency string bounds/evidence mismatch")
        chars = address(name["characters"])
        require(name["storage"] == ("inline" if capacity < 16 else "heap")
                and (capacity >= 16 or chars == definition + 0x10), "Dependency string storage mismatch")
        subordinate = target if observed == forward else "FRA"
        require(data["overlords"][subordinate] == obj["actor_handle"], "Dependency direction disagrees with overlord field")
        if name["name"] != "vassal":
            result["state"] = "other_dependency_type"
    return result


def spy_state(sample, entries):
    data, target = sample["spy"], sample["target"]
    address(data["records"])
    require(address(data["record"]) == address(data["records"]) + sample["pair"][target]["slot"] * 0x48
            and data["counterpart_handle"] == hex(HANDLES[target]), "Spy relation identity mismatch")
    flags = integer(data["flags_46"], 0, 255)
    integer(data["network_raw_i16"], -32768, 32767)
    owner = address(data["owner"])
    count = integer(data["count"], 0, MAX_TASKS)
    nodes = data["nodes"]
    require(isinstance(nodes, list) and len(nodes) == count, "Task list count mismatch")
    head, tail = address(data["head"], nullable=count == 0), address(data["tail"], nullable=count == 0)
    if not count:
        require(head == tail == 0, "Empty task list has nonnull head/tail")
    seen, task_pointers, matching = set(), set(), []
    for index, node in enumerate(nodes):
        ptr = address(node["address"])
        require(ptr not in seen, "Task list cycle")
        seen.add(ptr)
        require(ptr == (head if index == 0 else address(nodes[index - 1]["next"])), "Task list next linkage mismatch")
        require(address(node["previous"], nullable=True) == (0 if index == 0 else address(nodes[index - 1]["address"])), "Task list previous linkage mismatch")
        removed = integer(node["removed"], 0, 1)
        if removed:
            # owner+0x504 can defer unlinking. Count includes marked nodes;
            # their task objects may already be freed and must not be decoded.
            address(node["task_pointer"], nullable=True)
            require(node["task"] is None and "task_vtable" not in node, "Removed task node was dereferenced")
            continue
        task_ptr = address(node["task_pointer"])
        require(task_ptr not in task_pointers, "Task object duplicated in list")
        task_pointers.add(task_ptr)
        vt = address(node["task_vtable"])
        task = node["task"]
        if vt != address(sample["module_base"]) + SPY_TASK_VTABLE:
            require(task is None, "Unknown task vtable was decoded as spy")
            continue
        require(isinstance(task, dict) and address(task["address"]) == task_ptr and address(task["vtable"]) == vt
                and address(task["owner"]) == owner, "Spy task identity/owner mismatch")
        integer(task["envoy_id"], 0, 0xFFFFFFFE)
        require(task["target_handle"] == hex(HANDLES[target]), "Task target does not match its owning country")
        if task["actor_handle"] == hex(HANDLES["FRA"]):
            matching.append(task)
    if count:
        require(address(nodes[-1]["address"]) == tail and address(nodes[-1]["next"], nullable=True) == 0, "Task tail/termination mismatch")
    linked = pair_missions(sample, entries, with_task=True)
    if not flags & 8 and not matching and not linked:
        return {"state": "absent", "object": None, "matching_mission": None, "network_raw_i16": data["network_raw_i16"]}
    require(flags & 8 and len(matching) == len(linked) == 1, "Spy active bit, task list and missions disagree")
    entry, task = linked[0], matching[0]
    mission = entry["mission"]
    # +0x70 in the native setter is a virtual-function slot, not an instance
    # field. This reader never calls it; exact mission/task vtables and the
    # linked token/owner/identity graph provide the read-only evidence.
    require(entry["state"] == 2, "Spy envoy is not in its ongoing task state")
    require(address(mission["task_pointer"]) == address(task["address"]) and entry["envoy_id"] == task["envoy_id"], "Spy task does not match the linked envoy")
    return {"state": "active", "object": task, "matching_mission": entry, "network_raw_i16": data["network_raw_i16"]}


def inspect_state(sample):
    target, action = sample["target"], sample["action"]
    require(target in ("ENG", "POR") and action in TOKENS, "Unsupported pair/action")
    for key in ("module_base", "database", "game", "country_array"):
        address(sample[key])
    integer(sample["current_raw_date"], 1, 0x7FFFFFFF)
    base.validated_identity(sample["player"])
    for tag in ("FRA", target):
        base.validated_identity(sample["pair"][tag], HANDLES[tag])
    entries = validate_missions(sample)
    result = spy_state(sample, entries) if action == "spy_network" else relation_state(sample, entries)
    result["rejection_observed"] = False
    return result


def capture(reader, module_base, target, action):
    result = {"status": "unknown", "passes": [], "state": None, "errors": [], "atomic_snapshot": False}
    try:
        for _ in range(2):
            value = sample_once(reader, module_base, target, action)
            result["passes"].append(value)
            inspect_state(value)
        require(result["passes"][0] == result["passes"][1], "Repeated samples differ")
        result["state"] = inspect_state(result["passes"][1])
        result["status"] = "consistent_bounded_observation"
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
        return {"schema_version": 1, "kind": "core_relation_snapshot", "profile": PROFILE,
                "static_effect_evidence_sha256": base.EVIDENCE_SHA256, "read_only": True,
                "static_cancel_evidence_sha256": CANCEL_EVIDENCE_SHA256,
                "capture_started_at": started, "capture_finished_at": finished,
                "build": build, "source": source, "action": action, "actor": "FRA", "target": target,
                "observation": observation, "execution_verified": False, "request_causality_verified": False,
                "read_budget": {"bytes_read": reader.bytes_read, "maximum_total": base.MAX_TOTAL_READ,
                                "maximum_single": base.MAX_READ, "maximum_relation_entries": base.MAX_RELATION_ENTRIES,
                                "maximum_diplomats": base.MAX_DIPLOMATS, "maximum_tasks": MAX_TASKS, "passes": 2},
                "limitations": LIMITATIONS}
    finally:
        reader.close()


def validated_report(report):
    require(type(report["schema_version"]) is int and report["schema_version"] == 1 and report["profile"] == PROFILE
            and report["kind"] == "core_relation_snapshot" and report["read_only"] is True
            and report["static_effect_evidence_sha256"] == base.EVIDENCE_SHA256
            and report["static_cancel_evidence_sha256"] == CANCEL_EVIDENCE_SHA256, "Unsupported observation report")
    require(report["build"]["sha256"].upper() == base.LOCAL_SHA256, "Wrong game build")
    require(report["actor"] == "FRA" and report["target"] in ("ENG", "POR") and report["action"] in TOKENS, "Wrong pair/action")
    source = report["source"]
    require(source["kind"] == "live_process" and source["access_rights"] == "QUERY_INFORMATION | VM_READ", "Not a read-only live-process snapshot")
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


def compare_reports(before, after, mode="positive"):
    result = {"schema_version": 1, "kind": "core_relation_comparison", "profile": PROFILE,
              "status": "unknown", "mode": mode, "observed_effect": False, "execution_verified": False,
              "request_causality_verified": False, "ai_acceptance_verified": False,
              "rejection_observed": False, "whole_world_unchanged_verified": False, "errors": [], "limitations": LIMITATIONS}
    try:
        require(mode in ("positive", "cancel"), "Unknown comparison mode")
        prior, old, old_times = validated_report(before)
        current, new, new_times = validated_report(after)
        require(before["source"] == after["source"], "Process identity or loaded base changed")
        require((before["action"], before["target"]) == (after["action"], after["target"]), "Different action/pair reports")
        require(old_times[1] <= new_times[0] and old_times[0] < new_times[1], "Capture intervals overlap or are reversed")
        require(all(prior[key] == current[key] for key in ("pair", "player", "database", "game", "country_array")), "World or country identity changed")
        require(current["current_raw_date"] >= prior["current_raw_date"], "Date moved backwards")
        result.update(source=after["source"], action=after["action"], actor="FRA", target=after["target"],
                      raw_dates={"before": prior["current_raw_date"], "after": current["current_raw_date"]},
                      before_state=old, after_state=new)
        if mode == "positive" and old["state"] == "absent" and new["state"] == "active":
            if before["action"] in ("improve_relation", "spy_network"):
                require(not pair_missions(prior, prior["diplomats"]["entries"]), "Baseline already has a matching mission")
            if before["action"] != "spy_network":
                require(new["object"]["started_raw_date"] >= prior["current_raw_date"], "Newly observed relation predates baseline")
            result.update(status="observed_effect", observed_effect=True, transition="added_active_state")
        elif mode == "cancel" and old["state"] == "active" and new["state"] == "absent":
            if before["action"] in ("improve_relation", "spy_network"):
                envoy = old["matching_mission"]
                matching = [entry for entry in current["diplomats"]["entries"] if entry["envoy_id"] == envoy["envoy_id"]]
                require(len(matching) == 1 and matching[0]["address"] == envoy["address"], "Original envoy identity unavailable after removal")
                mission = matching[0]["mission"]
                if before["action"] == "spy_network":
                    require(mission is None or (mission["task_pointer"] == "0x0" and mission["action_token"] == TOKENS["spy_network"]
                            and mission["target_handle"] == hex(HANDLES[current["target"]])), "Original spy envoy task link was not cleared")
                # No old relation/task pointer is dereferenced by comparison.
            result.update(status="observed_effect", observed_effect=True, transition="removed_active_state")
        else:
            result["reason"] = "No complete requested transition observed; missing state does not establish rejection."
    except (base.ProbeError, KeyError, TypeError, ValueError, AttributeError, UnicodeError) as exc:
        result["errors"].append(str(exc))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--pid", required=True, type=int)
    sample.add_argument("--exe", type=Path)
    sample.add_argument("--target", choices=("ENG", "POR"), required=True)
    sample.add_argument("--action", choices=tuple(TOKENS), required=True)
    sample.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--direction", choices=("positive", "cancel"), required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), "Output already exists; choose a new evidence filename")
        if args.mode == "sample":
            executable = args.exe or base.game_exe()
            result = sample_process(args.pid, executable, args.target, args.action)
            base.write_report(args.output, result, (executable,))
            okay = result["observation"]["status"] == "consistent_bounded_observation"
        else:
            before, bh = base.read_report(args.before)
            after, ah = base.read_report(args.after)
            result = compare_reports(before, after, args.direction)
            result["inputs"] = {"before_sha256": bh, "after_sha256": ah}
            base.write_report(args.output, result, (args.before, args.after))
            okay = result["observed_effect"]
        print(json.dumps({"output": str(args.output), "status": result.get("status", result.get("observation", {}).get("status")),
                          "observed_effect": result.get("observed_effect", False), "execution_verified": False}))
        return 0 if okay else 2
    except (base.ProbeError, base.EvidenceError, OSError, ValueError, RuntimeError) as exc:
        print(f"Core relation observer: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
