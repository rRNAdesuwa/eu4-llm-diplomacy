"""Explicit bounded read-only FRA -> ENG/POR/NAV/FOI reply-notification observer.

sample opens only QUERY_INFORMATION | VM_READ; compare reads saved JSON only.
No native calls, game writes, injection, requests or message-setting changes.
New message evidence is pair/type/date correlation, never exact request-ID
causality or proof that a diplomatic relationship was applied.
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

PROFILE = "1375_pair_reply_history_v7_1"
EVIDENCE_SHA256 = "da3faa061af3d9ee8a3003412151594c6305b765afd8d739b4cb4a4759f63510"
HANDLES = {**base.PAIR, "POR": 0x010000BD00524F50,
           "NAV": 0x010000BC0056414E, "FOI": 0x0100007900494F46}
TARGETS = ("ENG", "POR", "NAV", "FOI")
MAX_HISTORY_NODES = 512  # Includes removed nodes; never follow an unbounded list.
MAX_ACTIVE_MESSAGES = 200
MAX_KEY_BYTES = 96
MAX_KEY_CAPACITY = 4096
SERVER_VTABLE = 0x1CB8460
MESSAGE_VTABLES = (0x1C426E0, 0x1CC1CA0)
PINS = {
    0x80E670: "4883b978110000007410488b89d01200004885c90f856634a300c3",
}
# The exact prefix is additionally checked against the audited disk image by
# the full-SHA ProcessReader before any heap traversal.
KEYS = {}
for action, stem in (("royal_marriage", "ROYMAR"), ("vassalaction", "VASALL")):
    for outcome, suffix in (("accepted", "ACCEPT"), ("rejected", "REJECT")):
        for key in (stem + suffix, stem + "WE" + suffix, stem + suffix + "OTHER"):
            KEYS[key] = (action, outcome)
KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")
require, integer, address = base.require, base.integer, base.address
ERRORS = (base.ProbeError, KeyError, TypeError, ValueError, UnicodeError, struct.error)
LIMITATIONS = [
    "Two consistent passes are not an atomic game-thread snapshot and cannot exclude ABA pointer reuse.",
    "Only fixed FRA -> ENG/POR/NAV/FOI pairs and known message vtables are interpreted; unknown message types are skipped.",
    "Message settings can suppress history and the normal 200-message limit can evict old entries. Absence stays unknown.",
    "New messages correlate by pair, action type, date window and previously absent node/message/shared-owner addresses.",
    "No recovered exact request ID exists in these message fields; request causality and relationship application remain unverified.",
    "PID/creation and stable world roots do not prove a complete world-load generation. Same-process reloads can escape detection.",
    "The disk executable SHA and selected loaded prefixes do not hash every loaded code byte.",
]


def hex64(value):
    require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-f]{1,16}", value) is not None, "Invalid raw QWORD")
    return int(value, 16)


def selected_targets(target):
    require(target in (*TARGETS, "both", "all"), "Only ENG/POR/NAV/FOI, both or all targets are supported")
    if target == "all":
        return list(TARGETS)
    return ["ENG", "POR"] if target == "both" else [target]


def identity(reader, module_base, targets):
    database = base.pointer(reader.qword(module_base + base.DATABASE_POINTER_RVA))
    game = base.pointer(reader.qword(module_base + base.GAME_POINTER_RVA))
    array = base.pointer(reader.qword(database + 0x118))
    date = reader.integer(game + 0x1DD0)
    require(date > 0, "Unavailable game date")
    player = reader.qword(game + 0x1E60)
    require(player == HANDLES["FRA"], "Current player is not the fixed full FRA identity")
    countries = {}
    for tag in ["FRA", *targets]:
        handle = HANDLES[tag]
        country = base.country_identity(reader, array, (handle >> 32) & 0xFFFF, handle)
        require(country is not None and country["tag"] == tag, "Missing fixed full country identity")
        countries[tag] = country
    return {"module_base": hex(module_base), "database": hex(database), "game": hex(game),
            "country_array": hex(array), "raw_date": date, "player_handle": hex(player), "countries": countries}


def key_string(reader, location):
    header = reader.read(location, 32)
    length, capacity = struct.unpack_from("<QQ", header, 0x10)
    require(0 < length <= MAX_KEY_BYTES and length <= capacity <= MAX_KEY_CAPACITY, "Message key length/capacity out of bounds")
    if capacity < 16:
        require(length < 16, "Invalid inline key length")
        data, chars, storage = header[:16], location, "inline"
    else:
        chars = base.pointer(struct.unpack_from("<Q", header)[0])
        data, storage = reader.read(chars, length + 1), "heap"
    require(data.find(b"\0") == length, "Message key length/NUL mismatch")
    name = data[:length].decode("ascii")
    require(KEY_PATTERN.fullmatch(name) is not None, "Message key is not bounded uppercase ASCII")
    return {"name": name, "length": length, "capacity": capacity, "storage": storage, "characters": hex(chars)}


def sample_once(reader, module_base, targets):
    ident = identity(reader, module_base, targets)
    loaded_pins = {hex(rva): reader.read(module_base + rva, len(bytes.fromhex(expected))).hex()
                   for rva, expected in PINS.items()}
    require(loaded_pins == {hex(rva): value for rva, value in PINS.items()}, "Loaded history code prefix mismatch")
    game = address(ident["game"])
    server = base.pointer(reader.qword(game + 0x1E00))
    vt = reader.qword(server)
    require(vt == module_base + SERVER_VTABLE, "Unexpected server vtable")
    forward = reader.qword(vt + 0x228)
    require(forward == module_base + 0x80E670, "Unexpected history forwarding virtual slot")
    ui = reader.qword(server + 0x1178)
    manager = reader.qword(server + 0x12D0)
    result = {"identity": ident, "targets": targets, "loaded_pins": loaded_pins,
              "server": hex(server), "server_vtable": hex(vt), "history_forwarder": hex(forward),
              "ui_guard_pointer": hex(ui), "manager": hex(manager), "history": None}
    if ui and manager:
        base.pointer(ui)
        base.pointer(manager)
        head, tail, count, iteration = struct.unpack("<QQIB", reader.read(manager + 0x10, 21))
        require(count <= MAX_HISTORY_NODES, "History exceeds strict 512-node total limit")
        require(iteration == 0, "History is actively iterating; do not inspect transient nodes")
        nodes, seen, current, prior, active = [], set(), head, 0, 0
        for _ in range(count):
            base.pointer(current)
            require(current not in seen, "History list cycle")
            seen.add(current)
            message, shared, previous, following, removed = struct.unpack("<QQQQB", reader.read(current, 33))
            require(removed <= 1 and previous == prior, "Invalid removed flag or previous link")
            item = {"address": hex(current), "message_pointer": hex(message), "shared_owner": hex(shared),
                    "previous": hex(previous), "next": hex(following), "removed": removed, "message": None}
            if not removed:
                active += 1
                require(active <= MAX_ACTIVE_MESSAGES, "History exceeds normal 200 active messages")
                base.pointer(message)
                base.pointer(shared)
                message_vt = reader.qword(message)
                item["message_vtable"] = hex(message_vt)
                # Unknown subclasses have no verified field contract. Read no further.
                if message_vt in [module_base + known for known in MESSAGE_VTABLES]:
                    actor, recipient = struct.unpack("<QQ", reader.read(message + 0x28, 16))
                    body = {"actor_handle": hex(actor), "target_handle": hex(recipient), "selected_pair": False}
                    for target in targets:
                        if actor == HANDLES["FRA"] and recipient == HANDLES[target]:
                            definition = base.pointer(reader.qword(message + 8))
                            body.update(selected_pair=True, target=target, definition=hex(definition),
                                        key=key_string(reader, definition + 0x38), raw_date=reader.integer(message + 0x88))
                            break
                    item["message"] = body
            nodes.append(item)
            prior, current = current, following
        require(current == 0 and prior == tail, "History count/tail/termination mismatch")
        require(bool(head) == bool(tail) == bool(count), "Empty history header mismatch")
        require(reader.read(manager + 0x10, 21) == struct.pack("<QQIB", head, tail, count, iteration), "History header changed during traversal")
        result["history"] = {"head": hex(head), "tail": hex(tail), "count": count, "iteration": iteration, "nodes": nodes}
    require(identity(reader, module_base, targets) == ident, "World/country/date changed during sample")
    require(reader.qword(game + 0x1E00) == server and reader.qword(server + 0x12D0) == manager
            and reader.qword(server + 0x1178) == ui, "History root changed during sample")
    return result


def inspect_sample(sample):
    """Revalidate saved fields and derive matches; never trust a success flag."""
    targets = sample["targets"]
    require(targets in ([tag] for tag in TARGETS) or targets == ["ENG", "POR"] or targets == list(TARGETS), "Unsupported target set")
    ident = sample["identity"]
    module = address(ident["module_base"])
    for key in ("database", "game", "country_array"):
        address(ident[key])
    date = integer(ident["raw_date"], 1, 0x7FFFFFFF)
    require(ident["player_handle"] == hex(HANDLES["FRA"]), "Wrong current player")
    require(set(ident["countries"]) == {"FRA", *targets}, "Country identity scope mismatch")
    for tag in ["FRA", *targets]:
        base.validated_identity(ident["countries"][tag], HANDLES[tag])
    require(sample["loaded_pins"] == {hex(rva): value for rva, value in PINS.items()}, "Wrong history code pins")
    address(sample["server"])
    require(address(sample["server_vtable"]) == module + SERVER_VTABLE
            and address(sample["history_forwarder"]) == module + 0x80E670, "Server ABI mismatch")
    ui = address(sample["ui_guard_pointer"], nullable=True)
    manager = address(sample["manager"], nullable=True)
    history = sample["history"]
    if not ui or not manager:
        require(history is None, "Invented history with missing owner")
        return {"history_available": False, "matches": [], "unknown_vtable_nodes": 0}
    require(isinstance(history, dict), "Missing history object")
    count = integer(history["count"], 0, MAX_HISTORY_NODES)
    require(type(history["iteration"]) is int and history["iteration"] == 0, "Transient history")
    head, tail = (address(history[key], nullable=count == 0) for key in ("head", "tail"))
    require(isinstance(history["nodes"], list) and len(history["nodes"]) == count, "History count mismatch")
    current, seen, messages, active, unknown, matches, prior = head, set(), set(), 0, 0, [], 0
    for node in history["nodes"]:
        location = address(node["address"])
        require(location == current and location not in seen, "History order/cycle mismatch")
        seen.add(location)
        require(address(node["previous"], nullable=True) == prior, "History previous mismatch")
        removed = integer(node["removed"], 0, 1)
        body = node["message"]
        if removed:
            hex64(node["message_pointer"])
            hex64(node["shared_owner"])
            require(body is None and "message_vtable" not in node, "Removed node was dereferenced")
        else:
            active += 1
            require(active <= MAX_ACTIVE_MESSAGES, "Too many active messages")
            message = address(node["message_pointer"])
            address(node["shared_owner"])
            require(message not in messages, "Duplicate active message pointer")
            messages.add(message)
            vt = address(node["message_vtable"])
            if vt not in [module + known for known in MESSAGE_VTABLES]:
                require(body is None, "Unknown message vtable was interpreted")
                unknown += 1
            else:
                actor, recipient = hex64(body["actor_handle"]), hex64(body["target_handle"])
                pair = next((target for target in targets if actor == HANDLES["FRA"] and recipient == HANDLES[target]), None)
                require(body["selected_pair"] is (pair is not None), "Message pair selection mismatch")
                if pair:
                    require(body["target"] == pair, "Message target mismatch")
                    definition = address(body["definition"])
                    msgdate = integer(body["raw_date"], 1, date)
                    key = body["key"]
                    name = key["name"]
                    require(isinstance(name, str) and KEY_PATTERN.fullmatch(name) is not None, "Invalid message key")
                    length, capacity = integer(key["length"], 1, MAX_KEY_BYTES), integer(key["capacity"], 1, MAX_KEY_CAPACITY)
                    require(len(name.encode("ascii")) == length <= capacity, "Message key length mismatch")
                    chars = address(key["characters"])
                    require((capacity < 16 and length < 16 and key["storage"] == "inline" and chars == definition + 0x38)
                            or (capacity >= 16 and key["storage"] == "heap"), "Message key storage mismatch")
                    if name in KEYS:
                        action, outcome = KEYS[name]
                        matches.append({"node": node["address"], "message": node["message_pointer"], "shared_owner": node["shared_owner"],
                                        "key": name, "action": action, "outcome": outcome, "actor": "FRA", "target": pair,
                                        "actor_handle": body["actor_handle"], "target_handle": body["target_handle"], "raw_date": msgdate})
        prior, current = location, address(node["next"], nullable=True)
    require(current == 0 and prior == tail and bool(head) == bool(tail) == bool(count), "History tail/termination mismatch")
    return {"history_available": True, "matches": matches, "unknown_vtable_nodes": unknown}


def capture(reader, module_base, targets):
    observation = {"status": "unknown", "passes": [], "state": None, "errors": [], "atomic_snapshot": False}
    try:
        for _ in range(2):
            value = sample_once(reader, module_base, targets)
            observation["passes"].append(value)
            inspect_sample(value)
        require(observation["passes"][0] == observation["passes"][1], "Two full snapshots differ")
        observation["state"] = inspect_sample(observation["passes"][1])
        observation["status"] = "consistent_bounded_observation"
    except ERRORS as exc:
        observation["errors"].append(str(exc))
    return observation


def sample_process(pid, executable, target):
    targets = selected_targets(target)
    build, signature = base.verified_executable(executable)
    reader = base.ProcessReader(pid, executable, signature)
    try:
        source = base.process_identity(reader, pid)
        source["verified_executable_path"] = str(Path(executable).resolve())
        started = base.timestamp()
        observation = capture(reader, reader.base, targets)
        finished = base.timestamp()
        require(base.process_identity(reader, pid) == {k: v for k, v in source.items() if k != "verified_executable_path"}, "Process identity changed")
        return {"schema_version": 1, "kind": "diplomatic_reply_snapshot", "profile": PROFILE,
                "static_evidence_sha256": EVIDENCE_SHA256, "read_only": True, "targets": targets,
                "capture_started_at": started, "capture_finished_at": finished,
                "build": build, "source": source, "observation": observation,
                "applied_verified": False, "request_id_causality_verified": False,
                "read_budget": {"bytes_read": reader.bytes_read, "maximum_total": base.MAX_TOTAL_READ,
                                "maximum_single": base.MAX_READ, "maximum_history_nodes_including_removed": MAX_HISTORY_NODES,
                                "maximum_active_messages": MAX_ACTIVE_MESSAGES, "maximum_key_bytes": MAX_KEY_BYTES, "passes": 2},
                "limitations": LIMITATIONS}
    finally:
        reader.close()


def validated_report(report):
    require(type(report["schema_version"]) is int and report["schema_version"] == 1
            and report["kind"] == "diplomatic_reply_snapshot" and report["profile"] == PROFILE
            and report["static_evidence_sha256"] == EVIDENCE_SHA256 and report["read_only"] is True, "Unsupported report")
    digest = report["build"]["sha256"]
    require(isinstance(digest, str) and digest.upper() == base.LOCAL_SHA256, "Wrong executable SHA256")
    source = report["source"]
    require(source["kind"] == "live_process" and source["access_rights"] == "QUERY_INFORMATION | VM_READ", "Wrong observation source")
    integer(source["pid"], 1)
    integer(source["process_creation_filetime"], 1, (1 << 64) - 1)
    require(type(source["process_exit_filetime"]) is int and source["process_exit_filetime"] == 0, "Exited process")
    address(source["module_base"])
    require(isinstance(source["verified_executable_path"], str) and source["verified_executable_path"], "Missing verified process path")
    times = [base.datetime.fromisoformat(report[key]) for key in ("capture_started_at", "capture_finished_at")]
    require(all(t.tzinfo is not None for t in times) and times[0] <= times[1], "Invalid capture times")
    observed = report["observation"]
    require(observed["status"] == "consistent_bounded_observation" and observed["errors"] == [], "Unknown/unstable snapshot")
    passes = observed["passes"]
    require(isinstance(passes, list) and len(passes) == 2 and passes[0] == passes[1], "Two equal full snapshots required")
    sample = passes[0]
    require(sample["identity"]["module_base"] == source["module_base"] and sample["targets"] == report["targets"], "Source/snapshot mismatch")
    state = inspect_sample(sample)
    require(state == observed["state"], "Stored state differs from raw observation")
    return sample, state, times


def compare_reports(before, after, action="both"):
    result = {"schema_version": 1, "kind": "diplomatic_reply_comparison", "profile": PROFILE, "status": "unknown",
              "accepted_correlated": False, "rejected_correlated": False, "correlated_messages": [], "errors": [],
              "correlation": "pair_type_date_new_node_message_owner_not_request_id", "applied_verified": False,
              "request_id_causality_verified": False, "execution_verified": False, "world_generation_verified": False,
              "limitations": LIMITATIONS}
    try:
        require(action in ("both", "royal_marriage", "vassalaction"), "Unsupported reply action")
        old, old_state, old_times = validated_report(before)
        new, new_state, new_times = validated_report(after)
        require(before["source"] == after["source"] and old["targets"] == new["targets"], "Process/target identity changed")
        require(old_times[1] <= new_times[0] and old_times[0] < new_times[1], "Overlapping or reversed captures")
        require(all(old["identity"][key] == new["identity"][key] for key in ("module_base", "database", "game", "country_array", "player_handle", "countries")), "World/country identity changed")
        require(all(old[key] == new[key] for key in ("server", "server_vtable", "ui_guard_pointer", "manager")), "History owner changed")
        lower, upper = old["identity"]["raw_date"], new["identity"]["raw_date"]
        require(lower <= upper, "Date regressed")
        result.update(source=after["source"], targets=new["targets"], action=action, raw_dates={"before": lower, "after": upper})
        if old_state["history_available"] and new_state["history_available"]:
            old_nodes = {node["address"] for node in old["history"]["nodes"]}
            old_messages = {node["message_pointer"] for node in old["history"]["nodes"]}
            old_owners = {node["shared_owner"] for node in old["history"]["nodes"]}
            matches = [m for m in new_state["matches"] if m["node"] not in old_nodes and m["message"] not in old_messages
                       and m["shared_owner"] not in old_owners and lower <= m["raw_date"] <= upper
                       and (action == "both" or m["action"] == action)]
            if matches:
                result.update(status="reply_notifications_correlated", correlated_messages=matches,
                              accepted_correlated=any(m["outcome"] == "accepted" for m in matches),
                              rejected_correlated=any(m["outcome"] == "rejected" for m in matches))
        if result["status"] == "unknown":
            result["reason"] = "No new bounded matching notification observed; no reply outcome is inferred."
    except ERRORS as exc:
        result["errors"].append(str(exc))
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--pid", type=int, required=True)
    sample.add_argument("--exe", type=Path)
    sample.add_argument("--target", choices=(*TARGETS, "both", "all"), default="all")
    sample.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--action", choices=("both", "royal_marriage", "vassalaction"), default="both")
    compare.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        require(not args.output.exists(), "Evidence output already exists")
        if args.mode == "sample":
            executable = args.exe or base.game_exe()
            result = sample_process(args.pid, executable, args.target)
            base.write_report(args.output, result, (executable,))
            okay = result["observation"]["status"] == "consistent_bounded_observation"
        else:
            before, bh = base.read_report(args.before)
            after, ah = base.read_report(args.after)
            result = compare_reports(before, after, args.action)
            result["inputs"] = {"before_sha256": bh, "after_sha256": ah}
            base.write_report(args.output, result, (args.before, args.after))
            okay = result["status"] == "reply_notifications_correlated"
        print(json.dumps({"output": str(args.output), "status": result.get("status", result.get("observation", {}).get("status")),
                          "applied_verified": False, "request_id_causality_verified": False}))
        return 0 if okay else 2
    except (base.ProbeError, base.EvidenceError, OSError, ValueError, RuntimeError) as exc:
        print(f"Diplomatic reply observer: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__": raise SystemExit(main())
