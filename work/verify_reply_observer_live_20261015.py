"""Verify already-recorded pending -> applied effect and real read-only HTTP.

No game command publication, native game calls, UI input, save or reload.
Output is exclusive so an old acceptance receipt cannot be overwritten.
"""
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import DEFAULT_STORE
from bridge.diplomacy_reply_observer import ReplyAwareEffectObserver, reply_source_pins
from bridge.diplomacy_observer_service import make_server
from bridge.tag_command_backend import DEFAULT_MANIFEST
from bridge.tag_command_audit import recorded_snapshot

REQUEST = "tag31-corrective-20261015-4-ask_for_march"
OUT = ROOT / "work/reports/diplomacy-reply-observer-20261015"


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    identity = json.loads((ROOT / "work/reports/diplomacy-corrective-20261014-r3/runtime/session-42600.json").read_text())["identity"]
    observer = ReplyAwareEffectObserver(identity, store=DEFAULT_STORE, allow_tag_host=True)
    directory = observer.directory(REQUEST)
    before_path = directory / "reply-observation-1792000084529775400.json"
    after_path = directory / "reply-observation-1792000124812991000.json"
    before, after = (json.loads(p.read_text()) for p in (before_path, after_path))
    assert before["request_state"] == before["completion_state"] == "waiting_for_recipient"
    assert before["reply"]["native_request_id"] == 55
    assert before["effect"]["status"] == "not_observed"
    assert after["effect"]["selected_effect_verified"] is True
    assert after["effect"]["changes"]["dependency_type"] == dict(before="vassal", after="march")
    assert after["reply"]["selected"]["pending"]["selected_matches"] == []
    assert before["identity"] == after["identity"] == identity
    assert before["audit_sha256"] == after["audit_sha256"]
    initial_pins = reply_source_pins()
    audit_before = recorded_snapshot(DEFAULT_MANIFEST, identity).status(REQUEST)["audit_sha256"]
    token = secrets.token_urlsafe(32)
    server = make_server(observer, port=0, token=token)
    worker = threading.Thread(target=server.serve_forever, kwargs=dict(poll_interval=0.05), daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
    try:
        connection.request("GET", "/observer/v1/effects/"+REQUEST, headers={"Authorization":"Bearer "+token})
        response = connection.getresponse()
        code, body = response.status, response.read(256*1024+1)
        assert code == 200 and len(body) <= 256*1024
        result = json.loads(body)
        assert result["transport_state"] == "dispatched"
        assert result["effect"]["selected_effect_verified"] is True
        assert result["completion_state"] == "selected_effect_observed"
    finally:
        connection.close()
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()
    assert not worker.is_alive() and server.socket.fileno() == -1
    assert recorded_snapshot(DEFAULT_MANIFEST, identity).status(REQUEST)["audit_sha256"] == audit_before
    assert reply_source_pins() == initial_pins
    response_path = OUT / "live-http-response.json"
    with response_path.open("xb") as f:
        f.write(body)
    receipt = dict(schema="EU4DIPLOMACY-REPLY-LIVE-VERIFICATION/1", request_id=REQUEST, identity=identity,
        source_pins=initial_pins, before=pin(before_path), after=pin(after_path),
        reply_baseline=pin(directory/"reply-baseline.json"),
        captures=[pin(Path(x["reply"]["capture_record"]["path"])) for x in (before, after)],
        pending_native_request_id=55, pending_before=1, pending_after=0,
        selected_effect=dict(dependency_before="vassal", dependency_after="march", verified=True),
        response_action="One normal-game-UI acceptance of original pending ORL request; no original action resend",
        request_state_after=after["request_state"], correlated_notifications_after=after["reply"]["correlated_notifications"],
        AI_acceptance_verified=False, exact_external_request_id_causality_verified=False,
        persistence_verified=False, all120_verified=False,
        http_status=code, http_response=pin(response_path), native_audit_unchanged=True, audit_sha256=audit_before,
        observer_native_calls=0, observer_memory_writes=0, requests_published=0, saves_written=0, reloads=0,
        listener_closed=True, thread_joined=True,
        timings_ms={"effect_before":before["capture"]["duration_ms"],"reply_before":before["reply"]["duration_ms"],
            "effect_after":after["capture"]["duration_ms"],"reply_after":after["reply"]["duration_ms"]})
    with (OUT/"live-verification.json").open("x", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    print(json.dumps({k:receipt[k] for k in ("request_id","pending_native_request_id","selected_effect", "http_status",
        "native_audit_unchanged","observer_native_calls","saves_written","reloads","listener_closed","thread_joined")}))


if __name__ == "__main__":
    main()
