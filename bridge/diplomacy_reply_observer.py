"""Independent reply-state observation for fixed EU4 1.37.5 ask-for-march.

Direct module decoder; no dynamic execution/import of work report scripts.
Reads only through the already-held read-only process port. Reply notifications
are correlations, never exact external-request causality or applied effects.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import struct
import time

from bridge.diplomacy_effect_observer import (EffectObserver, RuntimeCapture,
    BudgetReader, HeldRPMPort, roots, country, ptr, pins as observer_pins)
from bridge.tag_command_backend import (ROOT, DEFAULT_MANIFEST, GAME_SHA,
    decode, digest, read, require, validate_command)
from bridge.tag_command_audit import recorded_snapshot

SOURCE_MANIFEST = ROOT / "bridge/diplomacy_reply_observer_manifest_1375.json"
STATIC_FILE = ROOT / "work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/static.json"
STATIC_SHA = "25331327e18c4acf16f9cc9c82f3e19a6f6dfaea7f9fe42d4fa311e8d71fcdda"
MAX_PENDING = 128
MAX_HISTORY = 512
ASK_VT = 0x1C80440
MESSAGE_VTS = (0x1C426E0, 0x1CC1CA0)


def reply_source_pins():
    raw = read(SOURCE_MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest["schema"] == "EU4DIPLOMACY-REPLY-OBSERVER-MANIFEST/1"
        and manifest["game_sha256"] == GAME_SHA
        and manifest["native_manifest_sha256"] == digest(read(DEFAULT_MANIFEST, 1024*1024)),
        "Reply observer/build manifest identity differs")
    result = {}
    for name, expected in manifest["source_pins"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Invalid reply source path")
        data = read(ROOT/name, 2*1024*1024)
        actual = {"bytes": len(data), "sha256": digest(data)}
        require(actual == expected, "Reply source/evidence changed: " + name)
        result[name] = actual
    required = {"bridge/diplomacy_reply_observer.py", "bridge/diplomacy_effect_observer.py",
        "bridge/diplomacy_effect_profiles.py", STATIC_FILE.relative_to(ROOT).as_posix(),
        "work/reports/native-pair-replies-1375.json", "work/reports/native-action-fields-1375.json"}
    require(required <= set(result), "Reply observer evidence set incomplete")
    require(digest(read(STATIC_FILE, 2*1024*1024)) == STATIC_SHA, "Fixed reply static evidence differs")
    result[SOURCE_MANIFEST.relative_to(ROOT).as_posix()] = {"bytes": len(raw), "sha256": digest(raw)}
    return result


def pending(r, base, recipient, actor_handle, target_handle):
    owner = int(recipient["address"], 16)
    header = r.read(owner + 0x18D8, 21)
    head, tail, count, iteration = struct.unpack("<QQIB", header)
    require(count <= MAX_PENDING and iteration == 0, "Pending count/iteration bound")
    nodes, seen, active_actions, current, previous, matches = [], set(), set(), head, 0, []
    for _ in range(count):
        ptr(current)
        require(current not in seen, "Pending list cycle")
        seen.add(current)
        action, prior, following, deleted = struct.unpack("<QQQB", r.read(current, 25))
        require(deleted in (0, 1) and prior == previous, "Pending deleted/link mismatch")
        row = dict(node=hex(current), action_pointer_raw=hex(action), previous=hex(prior),
                   next=hex(following), deleted=bool(deleted), selected_action=None)
        if not deleted:
            ptr(action)
            require(action not in active_actions, "Aliased active pending action")
            active_actions.add(action)
            vt = r.q(action)
            row["vtable_pointer"] = hex(vt)
            if vt == base + ASK_VT:
                raw = r.read(action, 0x40)
                require(struct.unpack_from("<QI", raw) == (base + ASK_VT, 357), "Ask action type changed")
                actor, original, target = struct.unpack_from("<QQQ", raw, 0x10)
                start, queued, envoy, state = struct.unpack_from("<iiii", raw, 0x28)
                mode, native_id = raw[0x38], struct.unpack_from("<i", raw, 0x3C)[0]
                value = dict(actor_handle=hex(actor), original_actor_handle=hex(original),
                    recipient_handle=hex(target), start_raw=start, queued_raw=queued,
                    envoy_id=envoy, state_raw=state, value_raw=mode, native_request_id=native_id,
                    token=0x3021, selected_pair=(actor, original, target) == (actor_handle, actor_handle, target_handle))
                row["selected_action"] = value
                if value["selected_pair"]:
                    require(state in (0, 1, 2) and mode == 1 and native_id != 0,
                            "Unsupported selected reply state/mode/native ID")
                    require(start > 43808760 and queued > 0, "Selected pending date fields unavailable")
                    value["state_label"] = {0: "pending_observed", 1: "rejected_state_object_observed",
                                            2: "accepted_state_object_observed"}[state]
                    matches.append({"node": hex(current), "action": hex(action), **value})
                require(r.read(action, 0x40) == raw, "Pending action changed during read")
        nodes.append(row)
        previous, current = current, following
    require(current == 0 and previous == tail and bool(head) == bool(tail) == bool(count), "Pending tail/count mismatch")
    require(r.read(owner + 0x18D8, 21) == header, "Pending header changed during read")
    return dict(owner=recipient, head=hex(head), tail=hex(tail), count=count, iteration=iteration,
                nodes=nodes, selected_matches=matches)

def key_string(r, location):
    raw = r.read(location, 32)
    length, capacity = struct.unpack_from("<QQ", raw, 0x10)
    require(0 < length <= 96 and length <= capacity <= 4096, "Message key bound")
    if capacity < 16:
        require(length < 16, "Message inline bound")
        data = raw[:16]
    else:
        data = r.read(ptr(struct.unpack_from("<Q", raw)[0]), length + 1)
    require(data.find(b"\0") == length, "Message key NUL mismatch")
    value = data[:length].decode("ascii")
    require(re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", value), "Message key syntax")
    return value

def history(r, base, root, actor_handle, target_handle):
    server = int(root["server"], 16)
    require(r.q(base + 0x1CB8460 + 0x228) == base + 0x80E670, "History forwarder slot changed")
    ui, manager = r.q(server + 0x1178), r.q(server + 0x12D0)
    result = dict(server=hex(server), ui_guard=hex(ui), manager=hex(manager), available=False,
                  nodes=[], selected_notifications=[])
    if ui and manager:
        ptr(ui)
        ptr(manager)
        header = r.read(manager + 0x10, 21)
        head, tail, count, iteration = struct.unpack("<QQIB", header)
        require(count <= MAX_HISTORY and iteration == 0, "History count/iteration bound")
        seen, seen_messages, current, previous, active = set(), set(), head, 0, 0
        for _ in range(count):
            ptr(current)
            require(current not in seen, "History cycle")
            seen.add(current)
            msg, shared, prior, following, removed = struct.unpack("<QQQQB", r.read(current, 33))
            require(removed in (0, 1) and prior == previous, "History removed/link mismatch")
            row = dict(node=hex(current), message_raw=hex(msg), shared_owner_raw=hex(shared),
                       previous=hex(prior), next=hex(following), removed=bool(removed))
            if not removed:
                active += 1
                require(active <= 200 and msg not in seen_messages, "History active bound/alias")
                seen_messages.add(msg)
                ptr(shared)
                vt = r.q(ptr(msg))
                row["vtable_pointer"] = hex(vt)
                if vt in (base + x for x in MESSAGE_VTS):
                    actor, target = struct.unpack("<QQ", r.read(msg + 0x28, 16))
                    row.update(actor_handle=hex(actor), target_handle=hex(target))
                    if {actor, target} == {actor_handle, target_handle}:
                        definition = ptr(r.q(msg + 8))
                        key, date = key_string(r, definition + 0x38), r.i(msg + 0x88)
                        row.update(definition=hex(definition), key=key, raw_date=date)
                        outcome = None
                        if key == "ASK_FOR_MARCH_DENIED" and (actor, target) == (target_handle, actor_handle):
                            outcome = "rejection_notification_present"
                        elif key == "DESIGNATE_MARCH" and (actor, target) == (actor_handle, target_handle):
                            outcome = "march_designation_notification_present"
                        if outcome:
                            require(0 < date <= root["date"], "Message date out of observed world")
                            result["selected_notifications"].append({**row, "outcome": outcome,
                                "exact_external_request_id_causality_proven": False})
            result["nodes"].append(row)
            previous, current = current, following
        require(current == 0 and previous == tail and bool(head) == bool(tail) == bool(count), "History count/tail mismatch")
        require(r.read(manager + 0x10, 21) == header, "History header changed")
        result.update(available=True, head=hex(head), tail=hex(tail), count=count, active_count=active)
    require(r.q(server + 0x1178) == ui and r.q(server + 0x12D0) == manager, "History roots changed")
    return result

def loaded_code(r, base):
    static = decode(read(STATIC_FILE, 2 * 1024 * 1024))
    require(static["game_sha256"] == GAME_SHA, "Static build differs")
    for item in static["ranges"]:
        expected = b"".join(bytes.fromhex(row["bytes"]) for row in item["instructions"])
        require(len(expected) == int(item["end_rva_exclusive"], 16) - int(item["start_rva"], 16)
                and digest(expected) == item["range_sha256"], "Static range identity differs")
        require(r.read(base + int(item["start_rva"], 16), len(expected)) == expected,
                "Selected loaded reply code differs: " + item["name"])


def sample_reply(r, base, identity, command, binding):
    root = roots(r, base)
    require(root["manual_pause"] == 1 and r.i(base + 0x233E064) == -1,
            "Expected explicit manual pause and current Mod -1")
    a, t = binding["actor_handle"], binding["target_handle"]
    actor = country(r, base, root, a, command["actor"])
    recipient = country(r, base, root, t, command["target"])
    value = dict(identity=identity, roots=root, actor=actor, recipient=recipient,
        pending=pending(r, base, recipient, a, t), history=history(r, base, root, a, t))
    require(country(r, base, root, a, command["actor"]) == actor
        and country(r, base, root, t, command["target"]) == recipient,
        "Country identity changed after reply projection")
    require(roots(r, base) == root, "World/date/guards changed after reply projection")
    return value


class ReplyRuntimeCapture(RuntimeCapture):
    """Independent held VM_READ capture, using R1 identity/PE guards unchanged."""

    def __init__(self, identity, backend=None, *, allow_tag_host=False):
        super().__init__(identity, backend)
        require(type(allow_tag_host) is bool, "Explicit tag-host option must be boolean")
        self.allow_tag_host = allow_tag_host

    def capture_reply(self, command, binding):
        command = validate_command(command, self.backend.actions)
        require(command["action"] == "ask_for_march", "Unsupported reply action")
        started = time.perf_counter()
        initial = reply_source_pins()
        r = BudgetReader(HeldRPMPort(self.held))
        canonical = self.held.injector._canonical
        research = [(b, p) for b, p in self.modules if Path(p).name.lower().startswith(
            ("eu4_bridge_", "eu4_pair_", "eu4_spy_", "eu4_tag_command_", "tag_diplomacy"))]
        expected = self.backend.build / self.backend.manifest["DLL"]
        require(not research or (self.allow_tag_host and len(research) == 1
            and canonical(research[0][1]) == canonical(expected)), "Unexpected research module")
        if research:
            header = self.runtime.readonly.pe_header(r.read(ptr(research[0][0]), 8192))
            require(header["machine"] == 0x8664 and header["timestamp"] == self.backend.manifest["PE_timestamp"]
                and header["size_of_image"] == self.backend.manifest["SizeOfImage"], "Loaded build7 header changed")
        loaded_code(r, self.base)
        first = sample_reply(r, self.base, self.identity, command, binding)
        self.held.identity_check()
        second = sample_reply(r, self.base, self.identity, command, binding)
        require(first == second, "Two complete inbox/history passes differ")
        loaded_code(r, self.base)
        self.held.identity_check()
        require(self.held.modules() == self.modules, "Module set changed during reply capture")
        require(observer_pins() == self.initial_pins and reply_source_pins() == initial, "Reply sources changed")
        return dict(schema="EU4DIPLOMACY-REPLY-CAPTURE/1", identity=self.identity, command=command,
            captured_utc=datetime.now(timezone.utc).isoformat(), game_sha256=GAME_SHA,
            two_pass_equal=True, passes=[first, second], snapshot=first,
            source_pins=initial, research_modules=[str(p) for _, p in research],
            duration_ms=round((time.perf_counter()-started)*1000, 3),
            rpm_budget=dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest),
            native_calls=0, memory_written=False, requests_published=0, saves_written=0,
            atomic_main_thread_snapshot=False, world_epoch_proven=False)


def inline_reply(snapshot):
    """Keep HTTP bounded; full unrelated node rows stay in the capture journal."""
    p, h = snapshot["pending"], snapshot["history"]
    pending_summary = {k: p[k] for k in ("owner", "head", "tail", "count", "iteration", "selected_matches")}
    pending_summary["nodes_sha256"] = digest(json.dumps(p["nodes"], sort_keys=True).encode("ascii"))
    history_summary = {k: h[k] for k in ("server", "ui_guard", "manager", "available", "selected_notifications")}
    history_summary.update({k: h[k] for k in ("head", "tail", "count", "active_count") if k in h})
    history_summary["selected_notifications"] = [notification_summary(row) for row in h["selected_notifications"]]
    history_summary["nodes_sha256"] = digest(json.dumps(h["nodes"], sort_keys=True).encode("ascii"))
    return dict(identity=snapshot["identity"], now_raw=snapshot["roots"]["date"],
                actor=snapshot["actor"], recipient=snapshot["recipient"],
                pending=pending_summary, history=history_summary)


def notification_summary(row):
    return {k: row[k] for k in ("node", "message_raw", "shared_owner_raw", "key", "actor_handle",
                                "target_handle", "raw_date", "outcome")}


def evaluate_reply(command, snapshot, baseline=None):
    """Pure selected request-stage evidence; no absent-state outcome inference."""
    result = dict(schema="EU4DIPLOMACY-REPLY-STATE/1", request_state="unknown",
        exact_external_request_id_causality_verified=False, AI_acceptance_verified=False,
        applied_effect_verified=False, persistence_verified=False, world_epoch_proven=False,
        automatic_command_retry=False, baseline_available=baseline is not None,
        correlated_notifications=[], selected=inline_reply(snapshot))
    require(command["action"] == "ask_for_march", "Unsupported reply action")
    actor, recipient = snapshot["actor"], snapshot["recipient"]
    require(actor["tag"] == command["actor"] and recipient["tag"] == command["target"], "Reply pair differs")
    if baseline is not None:
        require(baseline["schema"] == "EU4DIPLOMACY-REPLY-BASELINE/1"
            and baseline["identity"] == snapshot["identity"] and baseline["command"] == command,
            "Reply baseline identity/request mismatch")
        require(baseline["actor"] == actor and baseline["recipient"] == recipient,
                "Reply baseline full country identities differ")
        require(type(baseline["native_request_id"]) is int and baseline["native_request_id"] != 0,
                "Reply baseline lacks native pending ID")
        require(all(snapshot["roots"][k] == baseline["world_roots"][k]
            for k in ("game", "database", "array", "server")), "Reply baseline world roots differ")
        require(type(baseline["now_raw"]) is int and baseline["now_raw"] <= snapshot["roots"]["date"],
                "Reply baseline date order differs")
    matches = snapshot["pending"]["selected_matches"]
    for row in matches:
        require((row["actor_handle"], row["original_actor_handle"], row["recipient_handle"])
            == (actor["handle"], actor["handle"], recipient["handle"])
            and row["token"] == 0x3021 and row["value_raw"] == 1
            and type(row["native_request_id"]) is int and row["native_request_id"] != 0
            and type(row["state_raw"]) is int and row["state_raw"] in (0, 1, 2), "Selected reply identity/state differs")
    if len(matches) == 1 and matches[0]["state_raw"] == 0:
        require(baseline is None or matches[0]["native_request_id"] == baseline["native_request_id"],
                "Selected pending native ID differs from retained baseline")
        result.update(request_state="waiting_for_recipient", native_request_id=matches[0]["native_request_id"],
                      reason="Unique typed state-0 inbox node observed; recipient has not resolved this node")
        return result
    if len(matches) > 1:
        result["reason"] = "Multiple selected inbox objects; external request attribution remains ambiguous"
        return result
    if baseline is None:
        result["reason"] = "No retained pending reply baseline; existing notifications remain historical/unattributed"
        return result
    root = snapshot["roots"]
    h = snapshot["history"]
    require(h["available"] and baseline["history_available"], "History unavailable for reply correlation")
    require(h["manager"] == baseline["history_manager"], "Reply history manager differs")
    old = baseline["history_addresses"]
    seen = {k: {r[k] for r in old} for k in ("node", "message_raw", "shared_owner_raw")}
    selected = []
    for row in h["selected_notifications"]:
        if not all(row[k] not in seen[k] for k in seen):
            continue
        if not baseline["now_raw"] <= row["raw_date"] <= root["date"]:
            continue
        expected = None
        if row["key"] == "ASK_FOR_MARCH_DENIED" and (row["actor_handle"], row["target_handle"]) == (recipient["handle"], actor["handle"]):
            expected = "denied_notification"
        elif row["key"] == "DESIGNATE_MARCH" and (row["actor_handle"], row["target_handle"]) == (actor["handle"], recipient["handle"]):
            expected = "accepted_notification"
        if expected:
            selected.append({**notification_summary(row), "request_state": expected,
                             "correlation": "pair_type_date_new_node_not_request_id"})
    outcomes = {row["request_state"] for row in selected}
    result["correlated_notifications"] = selected
    if len(outcomes) == 1:
        result.update(request_state=outcomes.pop(), native_request_id=baseline["native_request_id"],
            reason="New selected notification since pending baseline; no exact external request or AI-acceptance proof")
    else:
        result["reason"] = "No unambiguous new reply notification; queue disappearance is not an outcome"
    return result


def reply_baseline(command, snapshot, *, source_manifest_sha256):
    matches = snapshot["pending"]["selected_matches"]
    require(len(matches) == 1 and matches[0]["state_raw"] == 0, "Unique pending object required for reply baseline")
    h, root = snapshot["history"], snapshot["roots"]
    return dict(schema="EU4DIPLOMACY-REPLY-BASELINE/1", identity=snapshot["identity"], command=command,
        actor=snapshot["actor"], recipient=snapshot["recipient"], native_request_id=matches[0]["native_request_id"],
        now_raw=root["date"], world_roots={k: root[k] for k in ("game", "database", "array", "server")},
        history_available=h["available"], history_manager=h["manager"],
        history_addresses=[{k: row[k] for k in ("node", "message_raw", "shared_owner_raw")} for row in h["nodes"]],
        source_manifest_sha256=source_manifest_sha256, recorded_utc=datetime.now(timezone.utc).isoformat(),
        exact_external_request_id_causality_verified=False, world_epoch_proven=False)


class ReplyAwareEffectObserver(EffectObserver):
    """Preserve R1 effect facts and add independent, bounded native reply facts."""

    def __init__(self, identity, *, reply_capture_factory=ReplyRuntimeCapture, allow_tag_host=False, **kwargs):
        super().__init__(identity, **kwargs)
        self.reply_capture_factory = reply_capture_factory
        self.allow_tag_host = allow_tag_host

    def observe(self, request_id, *, record=True):
        status = recorded_snapshot(self.backend.manifest_path, self.identity).status(request_id)
        try:
            result = super().observe(request_id, record=False)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError) as exc:
            result = dict(schema="EU4DIPLOMACY-OBSERVATION/1", request_id=request_id,
                identity=self.identity, command=status["command"], transport_state=status["state"],
                audit_sha256=status["audit_sha256"], completion_state="evidence_insufficient",
                native_calls=0, requests_published=0, saves_written=0, memory_written=False,
                automatic_command_retry=False, AI_acceptance_verified=False, persistence_verified=False,
                effect=dict(status="unknown", selected_effect_verified=False,
                    reason="R1 observation unavailable; recorded transport state retained",
                    failure={"type": type(exc).__name__, "message": str(exc)}))
        result["request_state"] = "unknown"
        result["reply"] = dict(status="unsupported", reason="Reply layout is available only for dispatched ask_for_march",
            exact_external_request_id_causality_verified=False, AI_acceptance_verified=False, automatic_command_retry=False)
        if status["command"]["action"] == "ask_for_march" and status["state"] == "dispatched" and status["binding"]:
            try:
                with self.reply_capture_factory(self.identity, self.backend, allow_tag_host=self.allow_tag_host) as reader:
                    capture = reader.capture_reply(status["command"], status["binding"])
                require(capture["two_pass_equal"] is True and len(capture["passes"]) == 2
                    and capture["passes"][0] == capture["passes"][1] == capture["snapshot"], "Reply capture is not two-pass consistent")
                require(capture["identity"] == self.identity and capture["command"] == status["command"], "Reply capture identity differs")
                require(recorded_snapshot(self.backend.manifest_path, self.identity).status(request_id) == status,
                        "Recorded dispatch changed during reply observation")
                directory = self.directory(request_id)
                baseline_path = directory / "reply-baseline.json"
                before = decode(read(baseline_path, 2*1024*1024)) if baseline_path.exists() else None
                manifest_sha = digest(read(SOURCE_MANIFEST, 65536))
                if before is not None:
                    require(before["source_manifest_sha256"] == manifest_sha, "Reply baseline source manifest differs")
                reply = evaluate_reply(status["command"], capture["snapshot"], before)
                reply.update(status="sampled_equal", duration_ms=capture["duration_ms"], rpm_budget=capture["rpm_budget"],
                             source_manifest_sha256=manifest_sha, baseline_record=None, capture_record=None)
                if record:
                    directory.mkdir(parents=True, exist_ok=True)
                    capture_path = directory / f"reply-capture-{time.time_ns()}.json"
                    raw = json.dumps(capture, ensure_ascii=True, indent=2).encode("ascii")
                    require(len(raw) <= 2*1024*1024, "Reply capture journal bound")
                    with capture_path.open("xb") as f:
                        f.write(raw)
                    reply["capture_record"] = {"path": str(capture_path), "bytes": len(raw), "sha256": digest(raw)}
                    if before is None and reply["request_state"] == "waiting_for_recipient":
                        baseline = reply_baseline(status["command"], capture["snapshot"], source_manifest_sha256=manifest_sha)
                        with baseline_path.open("x", encoding="utf-8") as f:
                            json.dump(baseline, f, ensure_ascii=True, indent=2)
                        reply["baseline_record"] = str(baseline_path)
                result["reply"] = reply
                result["request_state"] = reply["request_state"]
                if reply["request_state"] == "waiting_for_recipient" and result.get("effect", {}).get("status") == "not_observed":
                    result["completion_state"] = "waiting_for_recipient"
            except (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError, struct.error) as exc:
                result["reply"] = dict(status="unknown", request_state="unknown",
                    exact_external_request_id_causality_verified=False, AI_acceptance_verified=False,
                    automatic_command_retry=False, failure={"type": type(exc).__name__, "message": str(exc)})
        if record:
            try:
                directory = self.directory(request_id)
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / f"reply-observation-{time.time_ns()}.json"
                with path.open("x", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=True, indent=2)
                result["record"] = str(path)
            except OSError as exc:
                result["record_failure"] = {"type": type(exc).__name__, "message": str(exc)}
        return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Verify independent reply observer source pins; no game access")
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps({"schema": "EU4DIPLOMACY-REPLY-OBSERVER-CHECK/1", "source_pins": len(reply_source_pins()),
                      "native_calls": 0, "requests_published": 0, "game_process_accessed": False}))
