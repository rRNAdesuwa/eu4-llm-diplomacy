"""Pure bounded memory decoder for an exact knowledge-sharing pair.

No process opening, native calls, writes, publication or runtime adapter.
The caller supplies an already-held, identity-verified read-only memory port.
"""
import hashlib
import json
from pathlib import Path
import struct

from bridge.diplomacy_effect_observer import roots, country, relation, full_handle, ptr
from bridge.tag_command_backend import ROOT, GAME_SHA, DEFAULT_MANIFEST, read, digest, decode, require, validate_identity

SOURCE_MANIFEST = ROOT / "bridge/knowledge_effect_reader_manifest_1375.json"
TASK_VT = 0x1CDE0A0
TASK_TOKEN = 0x3776
MAX_INDEX = 256
MAX_GLOBAL = 512
LIMITS = {"calls": 4096, "bytes": 512*1024, "single_read": 65536}
ACTIONS = ("knowledge_sharing", "ask_knowledge_sharing")


class _Reader:
    def __init__(self, port):
        self.port = port
        self.calls = self.bytes = self.largest = 0

    def read(self, address, size):
        ptr(address)
        require(type(size) is int and 0 < size <= LIMITS["single_read"] and address+size <= 2**47, "Knowledge read bound")
        require(self.calls < LIMITS["calls"] and self.bytes+size <= LIMITS["bytes"], "Knowledge shared read budget")
        self.calls += 1
        self.bytes += size
        self.largest = max(self.largest, size)
        raw = self.port.read(address, size)
        require(type(raw) is bytes and len(raw) == size, "Short knowledge memory read")
        return raw

    def q(self, address):
        return struct.unpack("<Q", self.read(address, 8))[0]

    def i(self, address):
        return struct.unpack("<i", self.read(address, 4))[0]

    def b(self, address):
        return self.read(address, 1)[0]


def _index(r, root, offset, wanted_slot, country_count):
    header = r.read(root+offset, 24)
    array = struct.unpack_from("<Q", header, 8)[0]
    count = struct.unpack_from("<i", header, 0x14)[0]
    require(0 <= count <= MAX_INDEX, "Sharing signed index count bound")
    raw = r.read(ptr(array), count*16) if count else b""
    entries = list(struct.iter_unpack("<i4xQ", raw))
    require(all(0 < slot < country_count and 0x10000 <= obj < 2**47 for slot, obj in entries), "Sharing index entry invalid")
    require(len({slot for slot, _ in entries}) == count, "Duplicate sharing index counterpart")
    matches = [obj for slot, obj in entries if slot == wanted_slot]
    require(r.read(root+offset, 24) == header, "Sharing index header changed")
    return dict(container=hex(root+offset), array=hex(array), count_signed=count,
        raw_field_10=struct.unpack_from("<i", header, 0x10)[0], records_sha256=digest(raw),
        object_pointer=hex(matches[0]) if matches else None, selected_member=bool(matches))


def _object(r, base, address, country_count, now):
    raw = r.read(ptr(address), 0x48)
    require(struct.unpack_from("<QI", raw) == (base+TASK_VT, 357), "Sharing object type/marker mismatch")
    provider, recipient = struct.unpack_from("<QQ", raw, 0x10)
    full_handle(provider, country_count)
    full_handle(recipient, country_count)
    require(provider != recipient, "Sharing object identical endpoints")
    start, deadline = struct.unpack_from("<ii", raw, 0x20)
    require(0 < start <= now and deadline >= start, "Sharing object raw dates invalid")
    require(raw[0x28] in (0, 1) and raw[0x29] in (0, 1), "Sharing lifecycle flags invalid")
    return dict(address=hex(address), vtable_rva=hex(TASK_VT), marker=357, token=TASK_TOKEN,
        provider_handle=hex(provider), recipient_handle=hex(recipient), start_raw=start, deadline_raw=deadline,
        removed_byte_28=raw[0x28], insertion_failed_byte_29=raw[0x29], expired=deadline <= now,
        raw_pointer_30=hex(struct.unpack_from("<Q", raw, 0x30)[0]),
        raw_signed_38=struct.unpack_from("<i", raw, 0x38)[0], raw_dword_3c=struct.unpack_from("<I", raw, 0x3c)[0],
        raw_flag_40=raw[0x40], raw_header_hex=raw.hex(), institution_identity_stored_here_proven=False)


def _global(r, base, root, provider, recipient):
    manager = int(root["game"], 16)+0x1BB8
    header = r.read(manager+0x10, 16)
    begin, end = struct.unpack("<QQ", header)
    if begin == end == 0:
        return dict(manager=hex(manager), begin=hex(begin), end=hex(end), buckets=0, selected_objects=[], count=0, nodes_sha256=digest(b""))
    ptr(begin)
    require(begin <= end <= begin+root["count"]*24 and (end-begin) % 24 == 0, "Global task bucket vector bound")
    total = (end-begin)//24
    result = dict(manager=hex(manager), begin=hex(begin), end=hex(end), buckets=total, selected_objects=[], count=0)
    if provider["slot"] >= total:
        result["nodes_sha256"] = digest(b"")
        require(r.read(manager+0x10, 16) == header, "Global task vector changed")
        return result
    bucket = begin+provider["slot"]*24
    bucket_header = r.read(bucket, 21)
    head, tail, count, iteration = struct.unpack("<QQIB", bucket_header)
    require(count <= MAX_GLOBAL and iteration == 0, "Global task bucket count/iteration bound")
    current, previous, seen, objects, nodes = head, 0, set(), set(), []
    for _ in range(count):
        ptr(current)
        require(current not in seen, "Global task list cycle")
        seen.add(current)
        raw = r.read(current, 25)
        obj, prior, following, deleted = struct.unpack("<QQQB", raw)
        require(prior == previous and deleted in (0, 1), "Global task links/deleted flag invalid")
        node = {"node": hex(current), "object_raw": hex(obj), "previous": hex(prior), "next": hex(following), "deleted": bool(deleted)}
        if not deleted:
            ptr(obj)
            require(obj not in objects, "Aliased active global task")
            objects.add(obj)
            vt = r.q(obj)
            node["vtable_raw"] = hex(vt)
            if vt == base+TASK_VT:
                value = _object(r, base, obj, root["count"], root["date"])
                require(value["provider_handle"] == provider["handle"], "Global provider generation differs")
                node["knowledge_object"] = value
                if value["recipient_handle"] == recipient["handle"]:
                    result["selected_objects"].append(value)
        nodes.append(node)
        previous, current = current, following
    require(current == 0 and previous == tail and bool(head) == bool(tail) == bool(count), "Global task count/tail mismatch")
    require(r.read(bucket, 21) == bucket_header and r.read(manager+0x10, 16) == header, "Global task headers changed")
    result.update(bucket=hex(bucket), head=hex(head), tail=hex(tail), count=count, iteration=iteration,
                  nodes_sha256=digest(json.dumps(nodes, sort_keys=True).encode("ascii")))
    return result


def _sample(r, base, action, actor_handle, target_handle):
    root = roots(r, base)
    require(root["manual_pause"] == 1, "Knowledge observation requires explicit manual pause")
    actor, target = country(r, base, root, actor_handle), country(r, base, root, target_handle)
    provider, recipient = (target, actor) if action == "ask_knowledge_sharing" else (actor, target)
    require(provider["handle"] != recipient["handle"], "Sharing endpoints identical")
    outgoing = relation(r, provider, recipient, base)
    incoming = relation(r, recipient, provider, base)
    left = _index(r, outgoing["root"], 0x2D0, recipient["slot"], root["count"])
    right = _index(r, incoming["root"], 0x2B8, provider["slot"], root["count"])
    global_state = _global(r, base, root, provider, recipient)
    require(r.q(base+TASK_VT+0x40) == base+0xA70470 and r.q(base+TASK_VT+0x48) == base+0x529FA0,
            "Loaded sharing vtable callback identity differs")
    require(r.read(base+0x529FA0, 6).hex() == "b876370000c3"
        and r.read(base+0xA70470, 20).hex() == "488b0501fa8c018b90d01d00003951240f9ec0c3", "Loaded sharing kind/expiry code differs")
    same = left["object_pointer"] == right["object_pointer"]
    selected = global_state["selected_objects"]
    status, obj, reason = "unknown", None, "Sharing indexes/global membership are incomplete or disagree"
    if same and left["object_pointer"] is None and not selected:
        status, reason = "pair_absent_observed", "No selected member in either index or current provider global bucket"
    elif same and left["object_pointer"] is not None and len(selected) == 1 and selected[0]["address"] == left["object_pointer"]:
        obj = selected[0]
        require(obj["provider_handle"] == provider["handle"] and obj["recipient_handle"] == recipient["handle"], "Sharing full direction mismatch")
        if obj["removed_byte_28"] == obj["insertion_failed_byte_29"] == obj["raw_flag_40"] == 0:
            status = "expired_pair_observed" if obj["expired"] else "active_pair_observed"
            reason = "Exact typed pair in both indexes and a live global node; expiry evaluated from raw deadline"
    require(country(r, base, root, actor_handle) == actor and country(r, base, root, target_handle) == target,
            "Sharing country identity changed")
    require(roots(r, base) == root, "Sharing roots/date/guards changed")
    return dict(status=status, reason=reason, now_raw=root["date"], roots=root,
        pair=dict(actor_tag=actor["tag"], target_tag=target["tag"], actor_handle=actor["handle"], target_handle=target["handle"]),
        provider=provider, recipient=recipient, indexes={"provider": left, "recipient": right}, global_bucket=global_state,
        object=obj, exact_pair_active_verified=status == "active_pair_observed",
        special_flag_40_termination_context_unresolved=bool(obj and obj["raw_flag_40"] != 0),
        institution_completion_verified=False, aggregate_counts_used_as_pair_proof=False)


def read_knowledge_pair(reader, base, action, actor_handle, target_handle, identity):
    """Decode two exact-pair passes from an already guarded read-only port."""
    result = dict(schema="EU4DIPLOMACY-KNOWLEDGE-PAIR/1", action=action, status="unknown", passes=[],
        exact_pair_active_verified=False, native_calls=0, memory_written=False, requests_published=0,
        institution_completion_verified=False, process_handle_opened=False, world_epoch_proven=False)
    r = _Reader(reader)
    try:
        require(action in ACTIONS, "Unsupported knowledge action")
        result["identity"] = validate_identity(identity)
        ptr(base)
        for _ in range(2):
            result["passes"].append(_sample(r, base, action, actor_handle, target_handle))
        require(result["passes"][0] == result["passes"][1], "Two complete knowledge pair passes differ")
        result.update(snapshot=result["passes"][0], status=result["passes"][0]["status"], two_pass_equal=True,
                      exact_pair_active_verified=result["passes"][0]["exact_pair_active_verified"])
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, struct.error, UnicodeError) as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    result["read_budget"] = dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest, limits=LIMITS)
    return result


def evaluate_knowledge_effect(action, before, after, receipt):
    """Require a new exact active pair plus the complete original dispatch receipt."""
    result = dict(schema="EU4DIPLOMACY-KNOWLEDGE-EFFECT/1", action=action, status="unknown", selected_effect_verified=False,
        AI_acceptance_verified=False, exact_external_request_id_causality_verified=False, exclusive_causality_proven=False,
        world_epoch_proven=False, saved_state_verified=False, cold_reload_verified=False, institution_completion_verified=False)
    try:
        require(action in ACTIONS and before is not None and after is not None, "Knowledge baseline/action unavailable")
        require(before["identity"] == after["identity"] == receipt["identity"], "Knowledge session identity differs")
        for value in (before, after):
            require(value["action"] == action and value["two_pass_equal"] is True and len(value["passes"]) == 2
                and value["passes"][0] == value["passes"][1] == value["snapshot"], "Knowledge evidence is not consistent")
        b, a = before["snapshot"], after["snapshot"]
        require(b["pair"] == a["pair"] and b["provider"] == a["provider"] and b["recipient"] == a["recipient"], "Knowledge exact pair differs")
        require(all(b["roots"][k] == a["roots"][k] for k in ("game", "database", "array", "server")) and b["now_raw"] <= a["now_raw"], "Knowledge world/date differs")
        require(receipt["state"] == "dispatched" and receipt["command"]["action"] == action
            and receipt["command"]["actor"] == b["pair"]["actor_tag"] and receipt["command"]["target"] == b["pair"]["target_tag"], "Knowledge dispatched command differs")
        require(receipt["binding"]["actor_handle"] == int(b["pair"]["actor_handle"], 16)
            and receipt["binding"]["target_handle"] == int(b["pair"]["target_handle"], 16), "Knowledge binding differs")
        nr = receipt["native_result"]
        require(all(type(nr[k]) is bool and nr[k] is True for k in ("submitted", "slot_consumed", "ownership_closed")), "Knowledge dispatch/ownership unproven")
        require(type(nr["status"]) is int and nr["status"] == 4
            and all(type(nr[k]) is int and nr[k] == 0 for k in ("owned_live", "quarantined", "adapter_fault", "submit_exception")), "Knowledge transport fault/unclosed")
        require(b["status"] != "unknown" and a["status"] != "unknown", "Knowledge selected pair state unknown")
        observed = b["status"] == "pair_absent_observed" and a["status"] == "active_pair_observed" and a["exact_pair_active_verified"] is True
        result.update(status="observed" if observed else "not_observed", selected_effect_verified=observed,
            completion_stage="active_sharing_pair_observed" if observed else "unverified",
            changes={"pair_status": {"before": b["status"], "after": a["status"]},
                     "object_pointer": {"before": b["object"]["address"] if b["object"] else None, "after": a["object"]["address"] if a["object"] else None}},
            native_known_cleanup_complete=nr.get("known_cleanup_complete"))
    except (ValueError, KeyError, TypeError) as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    return result


def verify_manifest():
    raw = read(SOURCE_MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest["schema"] == "EU4DIPLOMACY-KNOWLEDGE-READER-MANIFEST/1"
        and manifest["game_sha256"] == GAME_SHA and manifest["native_manifest_sha256"] == digest(read(DEFAULT_MANIFEST, 1024*1024)), "Knowledge manifest/build differs")
    result = {}
    for name, expected in manifest["source_pins"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Invalid knowledge source path")
        data = read(ROOT/name, 4*1024*1024)
        actual = {"bytes": len(data), "sha256": digest(data)}
        require(actual == expected, "Knowledge source/evidence changed: "+name)
        result[name] = actual
    require({"bridge/knowledge_effect_reader.py", "bridge/diplomacy_effect_observer.py",
        "work/reports/knowledge-effect-observer-20261015-r1/static.json"} <= set(result), "Knowledge evidence incomplete")
    result[SOURCE_MANIFEST.relative_to(ROOT).as_posix()] = {"bytes": len(raw), "sha256": digest(raw)}
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Offline knowledge reader source checks only; no process access")
    ap.add_argument("--check", action="store_true", required=True)
    ap.parse_args()
    print(json.dumps({"source_pins": len(verify_manifest()), "native_calls": 0, "game_process_accessed": False}))
