"""Independent bounded file audit of retained R2 pending -> march evidence.

Never constructs a runtime, starts a listener, calls the game or publishes.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_audit import recorded_snapshot
from bridge.tag_command_backend import DEFAULT_MANIFEST
from bridge.diplomacy_effect_profiles import evaluate_profile

OUT = ROOT / "work/reports/diplomacy-reply-observer-20261015"
PINS = {}


def raw_file(path, expected=None, *, limit=2*1024*1024):
    path = Path(path).resolve()
    assert path.is_relative_to(ROOT), path
    assert path.stat().st_size <= limit, path
    raw = path.read_bytes()
    value = {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        assert value["bytes"] == expected["bytes"] and value["sha256"] == expected["sha256"], path
    prior = PINS.get(str(path))
    assert prior is None or prior == value, path
    PINS[str(path)] = value
    return raw


def document(pin):
    return json.loads(raw_file(pin["path"], pin))


def verify_sources(values):
    for name, expected in values.items():
        raw_file(ROOT / name, expected)


def main():
    target = OUT / "independent-live-file-audit.json"
    assert not target.exists(), "Exclusive independent receipt already exists"
    receipt_path = OUT / "live-verification.json"
    receipt = json.loads(raw_file(receipt_path))
    raw_file(ROOT / "work/verify_reply_observer_live_20261015.py")
    raw_file(Path(__file__))
    verify_sources(receipt["source_pins"])
    before, after, baseline, http = (document(receipt[k]) for k in ("before", "after", "reply_baseline", "http_response"))
    identity, request = receipt["identity"], receipt["request_id"]
    status_snapshot = recorded_snapshot(DEFAULT_MANIFEST, identity)  # File-only API.
    status = status_snapshot.status(request)
    assert status["state"] == "dispatched" and status["sequence"] == 4
    assert status["audit_sha256"] == receipt["audit_sha256"] == before["audit_sha256"] == after["audit_sha256"] == http["audit_sha256"]
    assert not status_snapshot.raw[len(status_snapshot.complete):], "Incomplete native audit suffix"
    assert hashlib.sha256(status_snapshot.complete).hexdigest() == "b23b5f163da6cfc6b9b9ffb2e45a2a34585353dfe5ca06e8d787f5bb769abafe"
    native_rows = status_snapshot.rows
    counts = Counter(r["event"] for r in native_rows)
    assert counts["dispatch_intent"] == counts["request_claimed"] == counts["request_result"] == counts["pair_bound"] == 4
    begins = Counter((r["sequence"], r["call"]) for r in native_rows if r["event"] == "native_call_begin")
    returns = Counter((r["sequence"], r["call"]) for r in native_rows if r["event"] == "native_call_return")
    assert begins == returns and len(begins) == 28 and set(begins.values()) == {1}
    assert all(r["normal"] is True and r["exception"] == 0 for r in native_rows if r["event"] == "native_call_return")
    outcomes = [r for r in native_rows if r["event"] == "request_result"]
    assert {r["sequence"] for r in outcomes} == {1, 2, 3, 4}
    assert all(r["submitted"] is True and r["ownership_closed"] is True
        and r["owned_live"] == r["quarantined"] == r["adapter_fault"] == 0
        and r["known_cleanup_complete"] is False for r in outcomes)
    native_prefix_path = OUT / "independent-native-audit-prefix.jsonl"
    native_prefix_pin = {"path": str(native_prefix_path), "bytes": len(status_snapshot.complete), "sha256": status["audit_sha256"]}
    original_baseline = json.loads(raw_file(Path(receipt["before"]["path"]).parent / "baseline.json"))
    assert original_baseline["identity"] == identity and original_baseline["command"] == status["command"]
    captures = []
    for observed in (before, after, http):
        assert observed["identity"] == identity and observed["command"] == status["command"]
        assert observed["transport_state"] == "dispatched"
        assert observed["native_calls"] == observed["requests_published"] == observed["saves_written"] == 0
        assert observed["AI_acceptance_verified"] is False and observed["persistence_verified"] is False
        assert observed["capture"]["two_pass_equal"] is True
        verify_sources(observed["capture"]["source_pins"])
        verify_sources(observed["effect"]["source_pins"])
        capture = document(observed["reply"]["capture_record"])
        assert capture["identity"] == identity and capture["command"] == status["command"]
        assert capture["two_pass_equal"] is True and capture["passes"][0] == capture["passes"][1] == capture["snapshot"]
        assert capture["native_calls"] == capture["requests_published"] == capture["saves_written"] == 0
        assert capture["memory_written"] is False and capture["world_epoch_proven"] is False
        verify_sources(capture["source_pins"])
        assert capture["source_pins"] == receipt["source_pins"]
        s = capture["snapshot"]
        assert s["roots"]["date"] == 56461512 and s["roots"]["manual_pause"] == 1
        assert s["roots"]["reset"] == s["roots"]["load_source"] == s["roots"]["recalculating"] == 0
        assert s["pending"]["selected_matches"] == observed["reply"]["selected"]["pending"]["selected_matches"]
        for name in ("pending", "history"):
            assert hashlib.sha256(json.dumps(s[name]["nodes"], sort_keys=True).encode("ascii")).hexdigest() == observed["reply"]["selected"][name]["nodes_sha256"]
        computed = evaluate_profile("ask_for_march", original_baseline["snapshot"], observed["capture"]["snapshot"], status)
        assert computed == observed["effect"], "Selected effect is not reproducible from retained baseline/receipt/snapshot"
        captures.append(capture)
    assert [document(p) for p in receipt["captures"]] == captures[:2]
    assert baseline["identity"] == identity and baseline["command"] == status["command"] and baseline["native_request_id"] == 55
    assert baseline["actor"] == captures[0]["snapshot"]["actor"] and baseline["recipient"] == captures[0]["snapshot"]["recipient"]
    assert baseline["source_manifest_sha256"] == receipt["source_pins"]["bridge/diplomacy_reply_observer_manifest_1375.json"]["sha256"]
    assert baseline["history_addresses"] == [{k: r[k] for k in ("node", "message_raw", "shared_owner_raw")} for r in captures[0]["snapshot"]["history"]["nodes"]]
    assert all(c["snapshot"]["history"] == captures[0]["snapshot"]["history"] for c in captures)
    selected = before["reply"]["selected"]["pending"]["selected_matches"]
    assert len(selected) == 1 and selected[0]["native_request_id"] == 55 and selected[0]["state_raw"] == 0
    assert ((selected[0]["actor_handle"], selected[0]["original_actor_handle"], selected[0]["recipient_handle"], selected[0]["token"], selected[0]["value_raw"])
        == ("0x100007e004c524f", "0x100007e004c524f", "0x100007a00415246", 0x3021, 1))
    assert before["request_state"] == before["completion_state"] == "waiting_for_recipient"
    assert before["effect"]["status"] == "not_observed" and before["effect"]["selected_effect_verified"] is False
    assert before["capture"]["snapshot"]["pair"]["dependency_type"] == "vassal"
    for observed in (after, http):
        pair = observed["capture"]["snapshot"]["pair"]
        assert pair["dependency_type"] == "march" and pair["dependency_present"] is True
        assert pair["actor_overlord_handle"] == "0x100007a00415246" and pair["target_overlord_handle"] == "0x2d2d2d"
        assert observed["effect"]["selected_effect_verified"] is True and observed["completion_state"] == "selected_effect_observed"
        assert observed["request_state"] == "unknown" and observed["reply"]["correlated_notifications"] == []
        assert observed["reply"]["selected"]["pending"]["selected_matches"] == []
        assert observed["effect"]["saved_state_verified"] is False and observed["effect"]["cold_reload_verified"] is False
        assert observed["effect"]["exclusive_causality_proven"] is False and observed["effect"]["world_epoch_proven"] is False
    assert receipt["http_status"] == 200 and receipt["http_response"]["bytes"] < 256*1024
    assert receipt["listener_closed"] is True and receipt["thread_joined"] is True
    assert receipt["observer_native_calls"] == receipt["observer_memory_writes"] == receipt["requests_published"] == receipt["saves_written"] == receipt["reloads"] == 0
    http_journal = json.loads(raw_file(http["record"]))
    assert http_journal == {k: v for k, v in http.items() if k != "record"}
    report = dict(schema="EU4DIPLOMACY-R2-INDEPENDENT-LIVE-FILE-AUDIT/1", status="verified_selected_live_effect",
        request_id=request, identity=identity, native_request_id=55, now_raw=56461512,
        selected_transition=dict(before="waiting_for_recipient/state0/vassal", after="selected_effect_observed/march",
            full_actor_handle="0x100007e004c524f", full_recipient_handle="0x100007a00415246",
            same_overlord=True, pending_selected_before=1, pending_selected_after=0,
            recipient_inbox_total_before=12, recipient_inbox_total_after=11),
        notifications=dict(history_unchanged=True, active=200, selected_before=0, selected_after=0,
            request_state_after="unknown", queue_disappearance_is_rejection=False),
        native_audit=dict(audit_sha256=status["audit_sha256"], immutable_prefix=native_prefix_pin,
            original_request_sequences=[1, 2, 3, 4], original_dispatch_count=4, normal_call_pairs=28,
            additional_dispatches_in_recorded_acceptance_window=0, all_ownership_closed=True,
            known_cleanup_complete=False, terminal_observed=False),
        http=dict(status=200, response_bytes=receipt["http_response"]["bytes"], body_effect_reproduced=True,
            listener_closed_as_recorded=True, thread_joined_as_recorded=True),
        effect_predicate_reproduced_for=["before", "after", "HTTP"], baseline_identity_and_native_id_verified=True,
        all_source_pins_verified=True, input_pin_count=len(PINS), source_pins=list(PINS.values()),
        observer_native_calls=0, requests_published=0, saves_written=0, reloads=0,
        saved_state_verified=False, cold_reload_verified=False, AI_acceptance_verified=False,
        exact_external_request_id_causality_verified=False, world_epoch_proven=False, exclusive_causality_proven=False,
        runtime_access_by_this_auditor=False, tests_rerun_by_this_auditor=False,
        limitations=["Normal UI acceptance is reported by the root agent; this independent audit reads retained files only.",
            "HTTP status/socket cleanup are recorded receipt facts; the auditor did not reopen the listener.",
            "The native audit proves no additional bridge dispatch within the retained window, not absence of ordinary engine response processing.",
            "No selected saved-state/cold-reload persistence or exact external request causality is established."])
    with native_prefix_path.open("xb") as f:
        f.write(status_snapshot.complete)
    with target.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    text = ("# Independent R2 live-file audit\n\n"
        "Verified the retained pending native ID 55 (typed state 0, ORL→FRA, token 0x3021) and its immutable reply baseline. "
        "The selected dependency changes vassal→march with FRA still the overlord, at the same raw date 56461512. "
        "The effect predicate reproduces exactly from retained evidence for the before, after and HTTP observations.\n\n"
        "The selected inbox node disappears (recipient count 12→11), while all 200 active history entries remain unchanged and no selected notification exists. "
        "After-state request_state remains unknown; selected_effect_observed is independently justified by the type change. "
        "Queue disappearance is not interpreted as refusal.\n\n"
        "The native audit SHA remains b23b5f163da6cfc6b9b9ffb2e45a2a34585353dfe5ca06e8d787f5bb769abafe: four original dispatches, "
        "28 normal paired calls, all transport ownership closed. known_cleanup_complete remains false; terminal is not observed. "
        "There is no additional bridge dispatch in this recorded acceptance window. An immutable audit prefix is preserved separately.\n\n"
        "HTTP receipt status 200, 13,931-byte body and original effect are consistent; the producer records joined worker/closed listener. "
        "All referenced baselines/captures/manifests/source pins are verified. No runtime, UI, HTTP request, old test, save or reload was performed by this auditor. "
        "The root receipt reports one normal UI acceptance and no observer native calls, publication, save or reload. "
        "Saved/cold-reload verification, AI acceptance, exact external request causality and exclusive causality remain false.\n")
    with (OUT / "independent-live-file-audit.md").open("x", encoding="utf-8") as f:
        f.write(text)
    print(json.dumps({k: report[k] for k in ("status", "input_pin_count", "all_source_pins_verified", "observer_native_calls", "saves_written", "cold_reload_verified")}))


if __name__ == "__main__":
    main()
