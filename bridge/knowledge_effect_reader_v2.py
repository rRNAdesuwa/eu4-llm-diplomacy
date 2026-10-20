"""Exact sharing-pair reader with verified typed index allocation guards.

R1 remains immutable. Pure layout helpers and the effect predicate are reused;
the new sample calls this version's index parser without monkeypatching R1.
"""
import json
from pathlib import Path
import struct

from bridge import knowledge_effect_reader as r1
from bridge.diplomacy_effect_observer import roots, country, relation, ptr
from bridge.tag_command_backend import (ROOT, GAME_SHA, DEFAULT_MANIFEST, read,
    digest, decode, require, validate_identity)

ACTIONS = r1.ACTIONS
SOURCE_MANIFEST = ROOT / "bridge/knowledge_effect_reader_v2_manifest_1375.json"
INDEX_VT = 0x1C3A538
MAX_CAPACITY = 4096


def _index(r, base, root, offset, wanted_slot, country_count):
    header = r.read(root+offset, 24)
    vt, array, capacity, count = struct.unpack("<QQii", header)
    require(vt == base+INDEX_VT, "Sharing typed index vtable mismatch")
    require(0 <= count <= r1.MAX_INDEX and count <= capacity <= MAX_CAPACITY,
        "Sharing signed index count/capacity bound")
    require((capacity == 0 and array == 0) or
        (capacity > 0 and 0x10000 <= array < array+capacity*16 <= 2**47),
        "Sharing index allocation metadata mismatch")
    raw = r.read(ptr(array), count*16) if count else b""
    entries = list(struct.iter_unpack("<i4xQ", raw))
    require(all(0 < slot < country_count and 0x10000 <= obj < 2**47 for slot, obj in entries),
        "Sharing index entry invalid")
    require(len({slot for slot, _ in entries}) == count, "Duplicate sharing index counterpart")
    matches = [obj for slot, obj in entries if slot == wanted_slot]
    require(r.read(root+offset, 24) == header, "Sharing typed index header changed")
    return dict(container=hex(root+offset), vtable_rva=hex(INDEX_VT), array=hex(array),
        capacity_signed=capacity, count_signed=count, records_sha256=digest(raw),
        object_pointer=hex(matches[0]) if matches else None, selected_member=bool(matches),
        typed_allocation_metadata_verified=True)


def _sample(r, base, action, actor_handle, target_handle):
    root = roots(r, base)
    require(root["manual_pause"] == 1, "Knowledge observation requires explicit manual pause")
    actor, target = country(r, base, root, actor_handle), country(r, base, root, target_handle)
    provider, recipient = (target, actor) if action == "ask_knowledge_sharing" else (actor, target)
    require(provider["handle"] != recipient["handle"], "Sharing endpoints identical")
    outgoing = relation(r, provider, recipient, base)
    incoming = relation(r, recipient, provider, base)
    left = _index(r, base, outgoing["root"], 0x2D0, recipient["slot"], root["count"])
    right = _index(r, base, incoming["root"], 0x2B8, provider["slot"], root["count"])
    global_state = r1._global(r, base, root, provider, recipient)
    require(r.q(base+r1.TASK_VT+0x40) == base+0xA70470 and r.q(base+r1.TASK_VT+0x48) == base+0x529FA0,
        "Loaded sharing vtable callback identity differs")
    require(r.read(base+0x529FA0, 6).hex() == "b876370000c3"
        and r.read(base+0xA70470, 20).hex() == "488b0501fa8c018b90d01d00003951240f9ec0c3",
        "Loaded sharing kind/expiry code differs")
    same = left["object_pointer"] == right["object_pointer"]
    selected = global_state["selected_objects"]
    status, obj, reason = "unknown", None, "Sharing indexes/global membership are incomplete or disagree"
    if same and left["object_pointer"] is None and not selected:
        status, reason = "pair_absent_observed", "No selected member in either typed index or current provider global bucket"
    elif same and left["object_pointer"] is not None and len(selected) == 1 and selected[0]["address"] == left["object_pointer"]:
        obj = selected[0]
        require(obj["provider_handle"] == provider["handle"] and obj["recipient_handle"] == recipient["handle"],
            "Sharing full direction mismatch")
        if obj["removed_byte_28"] == obj["insertion_failed_byte_29"] == obj["raw_flag_40"] == 0:
            status = "expired_pair_observed" if obj["expired"] else "active_pair_observed"
            reason = "Exact typed pair in both allocation-guarded indexes and a live global node; raw deadline checked"
    require(country(r, base, root, actor_handle) == actor and country(r, base, root, target_handle) == target,
        "Sharing country identity changed")
    require(roots(r, base) == root, "Sharing roots/date/guards changed")
    return dict(status=status, reason=reason, now_raw=root["date"], roots=root,
        pair=dict(actor_tag=actor["tag"], target_tag=target["tag"], actor_handle=actor["handle"], target_handle=target["handle"]),
        provider=provider, recipient=recipient, indexes={"provider": left, "recipient": right}, global_bucket=global_state,
        object=obj, exact_pair_active_verified=status == "active_pair_observed", typed_index_allocation_guards_verified=True,
        special_flag_40_termination_context_unresolved=bool(obj and obj["raw_flag_40"] != 0),
        institution_completion_verified=False, aggregate_counts_used_as_pair_proof=False)


def read_knowledge_pair(reader, base, action, actor_handle, target_handle, identity):
    result = dict(schema="EU4DIPLOMACY-KNOWLEDGE-PAIR/2", action=action, status="unknown", passes=[],
        exact_pair_active_verified=False, native_calls=0, memory_written=False, requests_published=0,
        institution_completion_verified=False, process_handle_opened=False, world_epoch_proven=False)
    r = r1._Reader(reader)
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
    result["read_budget"] = dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest, limits=r1.LIMITS)
    return result


def evaluate_knowledge_effect(action, before, after, receipt):
    for value in (before, after):
        if value is not None and (value.get("schema") != "EU4DIPLOMACY-KNOWLEDGE-PAIR/2"
                or not value.get("snapshot", {}).get("typed_index_allocation_guards_verified")):
            result = r1.evaluate_knowledge_effect(action, None, after, receipt)
            result.update(reason="Typed index allocation evidence unavailable", automatic_command_retry=False)
            return result
    return r1.evaluate_knowledge_effect(action, before, after, receipt)


def verify_manifest():
    raw = read(SOURCE_MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest["schema"] == "EU4DIPLOMACY-KNOWLEDGE-READER-MANIFEST/2"
        and manifest["game_sha256"] == GAME_SHA
        and manifest["native_manifest_sha256"] == digest(read(DEFAULT_MANIFEST, 1024*1024)), "Knowledge v2 build differs")
    result = {}
    for name, expected in manifest["source_pins"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Invalid knowledge v2 source path")
        data = read(ROOT/name, 16*1024*1024)
        actual = {"bytes": len(data), "sha256": digest(data)}
        require(actual == expected, "Knowledge v2 source/evidence changed: "+name)
        result[name] = actual
    require({"bridge/knowledge_effect_reader_v2.py", "bridge/knowledge_effect_reader_manifest_1375.json",
        "work/reports/knowledge-effect-observer-20261015-r1/index-guard/static.json"} <= set(result), "Knowledge v2 graph incomplete")
    r1.verify_manifest()
    result[SOURCE_MANIFEST.relative_to(ROOT).as_posix()] = {"bytes": len(raw), "sha256": digest(raw)}
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Offline typed sharing-index source checks; no game access")
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps({"source_pins": len(verify_manifest()), "native_calls": 0, "game_process_accessed": False}))
