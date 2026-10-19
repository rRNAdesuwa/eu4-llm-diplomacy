"""Fixed, offline review of the interrupted v10 experiment in PID 46408.

Validates the healthy prefix with the v10 phase/ownership validators in a
temporary evidence mirror, then independently requires the exact terminal
freeze and supervisor termination. Never opens a process or a live mailbox.
Four selected effects are reviewed; no save/reload or fourteen-action claim.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_api import canonical, decode_json
from work import probe_pair_extension_v10_1375 as observer
from work.native import lab_protocol_v10_1375 as lab

RUNTIME = ROOT / "work/runtime"
PID, CREATION, THREAD = 46408, "01dd568ed7034bcb", 35000
WORLD = "0x1df8d5f6020"
DLL_SHA = "A2345AFE7C3C8CAA8A8EBADDC29B068A90FF35E3E83AF07212A1E18C40CBC9B7"
MANIFEST_SHA = "ae68ffe9b59d6c6fcd4a464eea98d108bf5b700f77459773f1655bdcea7c9d46"
LOG_SHA = "78ae009624ef126d2d2caba975c88272476a7873b4968fb084c9b5319770c4f6"
LOG_BYTES = 906230
SESSION_NAME = f"native1375-v10/session-{PID}-{CREATION}"
FREEZE_REASON = "request_invalid_expired_or_already_claimed"
# Explicit fixed cases, rather than claiming all planned fourteen operations.
CASES = (
    (3, "offer_alliance", "allianceaction", "alliance", "after-alliance-dispatch", "alliance-positive"),
    (6, "ask_military_access", "milaccess", "ask-military", "after-ask-military", "milaccess-positive"),
    (9, "offer_military_access", "offermilaccess", "offer-military", "after-offer-military-submit", "offermilaccess-positive-submit"),
    (12, "ask_fleet_basing_rights", "fleet_access", "ask-fleet", "after-ask-fleet", "fleet-access-positive"),
)
require = lab.require


def same_identity(row, *, creation_key="creation"):
    require(type(row.get("pid")) is int and row["pid"] == PID and row.get(creation_key) == CREATION,
            "Foreign or incomplete process identity")


def validate_terminal(freeze, supervisor, *, claim_exists, lease_claim_exists):
    same_identity(freeze, creation_key="process_creation_filetime")
    require(set(freeze) == {"event", "pid", "process_creation_filetime", "sequence", "reason", "retry_allowed"}
            and freeze["event"] == "lab_session_frozen" and type(freeze["sequence"]) is int
            and freeze["sequence"] == 12 and freeze["reason"] == FREEZE_REASON and freeze["retry_allowed"] is False,
            "Unexpected terminal native event")
    require(not claim_exists and not lease_claim_exists, "Sequence 13 must not have a native or pause claim")
    require(len(supervisor) == 2, "Unexpected aborted supervision history")
    for event in supervisor:
        same_identity(event)
        require(event.get("sequence") == 13 and event.get("speed") == 5 and event.get("retry_allowed") is False,
                "Supervisor sequence/control differs")
    before, stopped = supervisor
    require(before.get("event") == "supervisor_armed" and before.get("deadline_seconds") == 12.0
            and before["before"]["paused"] is True and before["before"]["native_speed_index"] == 0
            and before["before"]["game"] == int(WORLD, 16) and before["before"]["raw_date"] == 56457144,
            "Supervisor was not armed for the matching paused world")
    require(stopped.get("event") == "supervisor_stopped_disposable_process" and stopped.get("stopped") is True
            and stopped.get("reason") == "Native lab session is frozen; no retry: " + FREEZE_REASON,
            "Exact-process termination is not documented")


def validate_pair(row, action, sequence, *, submit):
    request, records, complete = row["request"], row["records"], row["complete"]
    same_identity(request)
    require(request["sequence"] == sequence and request["operation"] == "pair" and request["action"] == action
            and request["actor"] == "FRA" and request["target"] == "POR" and request["speed"] == 0
            and request["mode"] == ("submit" if submit else "legality_only"), "Wrong pair operation")
    require([r["event"] for r in records] == (["pair_engine_begin", "pair_engine_dispatch_intent", "pair_engine_complete"]
            if submit else ["pair_engine_begin", "pair_engine_complete"]), "Unexpected native ownership history")
    final = records[-1]
    require(final["status"] == (2 if submit else 1) and final["reason"] == 0 and final["exception"] == 0
            and final["original_destroyed"] is True and final["ownership_uncertain"] is False
            and final["freeze_session"] is False and final["applied_verified"] is False
            and final["submit_entered"] is submit and final["submit_returned"] is submit
            and final["command_destroyed_before_dispatch"] is (not submit)
            and final["preview_called"] is True and final["preview_allowed"] is True
            and final["gate_called"] is True and final["gate_allowed"] is True,
            "Native legality/dispatch/ownership did not complete")
    require(final["context_submit_return"] is (True if submit else None)
            and final["caller_container_consumed"] is (True if submit else None), "Consumer ownership result differs")
    for record in records:
        same_identity(record, creation_key="process_creation_filetime")
        require(record["thread_id"] == THREAD and record["world"] == WORLD
                and int(record["actor_handle"], 16) == 0x100007A00415246
                and int(record["target_handle"], 16) == 0x10000BD00524F50
                and record["fixed_subsidy_amount_milli"] == 0 and record["fixed_subsidy_duration_years"] == 0,
                "Foreign native pair/thread/world/parameters")
    require(complete["status"] == final["status"] and complete["reason"] == 0
            and complete["submit_entered"] is submit and complete["submit_returned"] is submit
            and complete["ownership_uncertain"] is False, "Host/native completion disagrees")
    return final


def validate_http(report, row, http_intent, host):
    same_identity(report)
    require(report["purpose"] == "v10_real_http_alliance_transport_experiment" and report["token_recorded"] is False
            and report["server_closed"] is True and report["automatic_retry"] is False
            and report["production_backend_registered"] is False and report["observed_effect"] is False,
            "HTTP report overclaims or lacks closeout")
    request = report["request"]
    expected = {"protocol": "EU4LAB/2", "pid": PID, "creation": CREATION, "sequence": 3,
                "mode": "submit", "action": "offer_alliance", "actor": "FRA", "target": "POR", "ttl_ms": 5000}
    require(request == expected and http_intent["request"] == request
            and http_intent["kind"] == "eu4_lab_v10_research_http"
            and http_intent["manifest_sha256"] == MANIFEST_SHA and http_intent["automatic_retry"] is False
            and http_intent["request_sha256"] == hashlib.sha256(canonical(request).encode("ascii")).hexdigest(),
            "HTTP durable intent differs from the fixed request")
    events = report["http_events"]
    require([(e["method"], e["path"], e["status"]) for e in events] == [
        ("GET", "/research/v10/status", 200), ("POST", "/research/v10/pair", 202),
        ("GET", "/research/v10/requests/3", 200), ("POST", "/research/v10/pair", 200)], "HTTP trace differs")
    for event in events:
        response = event["response"]
        same_identity(response)
        require(response["purpose"] == lab.PURPOSE and response["protocol"] == lab.PROTOCOL
                and response["research_only"] is True and response["production"] is False
                and response["production_backend_registered"] is False and response["applied_verified"] is False
                and response["strict_live_single_player_verified"] is False and response["world_generation_verified"] is False,
                "HTTP profile or epistemic boundary differs")
    published, queried, replayed = [e["response"] for e in events[1:]]
    require(published["request_written"] is True and published["replayed"] is False,
            "First HTTP publication not documented")
    require(replayed["request_written"] is False and replayed["replayed"] is True,
            "Duplicate HTTP call wrote another request")
    for response in (published, queried, replayed):
        require(response["sequence"] == 3 and response["request_sha256"] == host["request_sha256"], "HTTP wire hash differs")
    for response in (queried, replayed):
        require(response["state"] == "native_completed" and response["native"] == row
                and response["request"] == row["request"] and response["native_dispatch_verified"] is True,
                "HTTP result differs from validated native evidence")


def review():
    hashes = {}

    def raw(rel, limit=1024 * 1024):
        data = lab.read_bounded(RUNTIME / rel, limit)
        hashes[rel] = hashlib.sha256(data).hexdigest().upper()
        return data

    def document(rel):
        return decode_json(raw(rel).decode("utf-8-sig"))

    def local(name):
        return document("native1375-v10/" + name)

    def session_raw(name):
        return raw(SESSION_NAME + "/" + name)

    manifest, manifest_sha = lab.verify_build()
    require(manifest_sha == MANIFEST_SHA and manifest["dll_sha256"] == DLL_SHA, "Different fixed v10 build")
    raw("native1375-v10/build.json")
    require(hashlib.sha256(raw("native1375-v10/eu4_pair_lab_v10_1375.dll")).hexdigest().upper() == DLL_SHA, "DLL bytes differ")
    session = RUNTIME / SESSION_NAME
    metadata = lab.read_session_metadata(session, PID, CREATION)
    require(metadata["window_thread"] == THREAD, "Foreign main thread")
    loader = local("loader-install-46408.json")
    same_identity(loader)
    require(loader["purpose"] == lab.PURPOSE and loader["manifest_sha256"] == MANIFEST_SHA
            and loader["dll_sha256"] == DLL_SHA and loader["plan_only"] is False
            and loader["installation"]["bridge_thread_exit_status"] == "0x0"
            and loader["live_observation"]["world_cookie"] == WORLD
            and loader["test_save_premise"]["loaded_save_identity_verified"] is False
            and loader["test_save_premise"]["strict_live_single_player_verified"] is False,
            "Loader identity/scope differs")
    statuses = [local("phases-ready-46408.json"), local("fixture-on-status-1-46408.json")]
    pair_statuses = {}
    for seq, action, family, label, after, comparison in CASES:
        legality = local(("alliance-legality" if seq == 3 else label + "-legality_only") + f"-status-{seq-1}-46408.json")
        statuses.append(legality)
        pair_statuses[seq-1] = legality
        if seq != 3:
            submitted = local(label + f"-submit-status-{seq}-46408.json")
            statuses.append(submitted)
            pair_statuses[seq] = submitted
    http = local("http-alliance-submit-3-46408.json")
    statuses.append(http["http_events"][0]["response"])
    wanted = {row["log_sha256"]: row for row in statuses}
    prefix_matches = {}
    # Only a temporary mirror is truncated. Original native evidence is untouched.
    with tempfile.TemporaryDirectory(prefix="eu4-v10-review-") as temporary:
        mirror = Path(temporary)
        names = ["session.json", "install.claim", "00000000000000000001.fixture-profile"]
        names += [row[1] for row in lab.PHASES.values()]
        names += [f"{seq:020}.claim" for seq in range(1, 13)]
        names += [f"{seq:020}.lease-pause.claim" for seq in (4, 7, 10)]
        for name in names:
            (mirror / name).write_bytes(session_raw(name))
        total, healthy_bytes, last_frame, terminal = 0, 0, None, None
        digest = hashlib.sha256()
        with (session / "research-1375.jsonl").open("rb") as source, (mirror / "research-1375.jsonl").open("wb") as target:
            while line := source.readline(lab.MAX_LINE + 1):
                total += len(line)
                require(total <= lab.MAX_LOG and len(line) <= lab.MAX_LINE and line.endswith(b"\n"), "Log framing/budget failed")
                require(terminal is None, "Native events continued after terminal freeze")
                event = decode_json(line.decode("utf-8"))
                digest.update(line)
                if event.get("event") == "lab_session_frozen":
                    terminal = event
                else:
                    target.write(line)
                    healthy_bytes += len(line)
                if event.get("event") == "research_frame":
                    last_frame = event
                current = digest.hexdigest()
                if current in wanted:
                    row = wanted[current]
                    same_identity(row)
                    require(row["latest_frame"] == last_frame and row["manifest_sha256"] == MANIFEST_SHA
                            and row["dll_sha256"] == DLL_SHA, "Status prefix frame/build differs")
                    prefix_matches[current] = total
        require(total == LOG_BYTES and digest.hexdigest() == LOG_SHA and set(prefix_matches) == set(wanted), "Stopped log/status prefixes differ")
        hashes[SESSION_NAME + "/research-1375.jsonl"] = digest.hexdigest().upper()
        evidence = lab.read_evidence(mirror, metadata)
    require(all(evidence["phases"].values()) and evidence["last_sequence"] == 12
            and set(evidence["requests"]) == set(range(1, 13)) and not evidence["pending"] and not evidence["lease_pending"],
            "Healthy prefix has incomplete phases/requests")
    require(evidence["latest_frame"] == last_frame and last_frame["world_cookie"] == WORLD
            and last_frame["paused"] is True and last_frame["raw_date"] == 56457144, "Last healthy world/date differs")
    hosts = {}
    for seq in range(1, 14):
        host = decode_json(session_raw(f"{seq:020}.host-intent").decode("utf-8"))
        same_identity(host)
        wire = host["body_ascii"].encode("ascii")
        request = lab.decode_request(wire)
        require(host["protocol"] == lab.PROTOCOL and host["purpose"] == lab.PURPOSE
                and host["manifest_sha256"] == MANIFEST_SHA and host["automatic_retry"] is False
                and host["request_sha256"] == hashlib.sha256(wire).hexdigest() and request["sequence"] == seq,
                "Host intent wire/build binding differs")
        same_identity(request)
        if seq <= 12:
            require(request == evidence["requests"][seq]["request"] and not (session/f"{seq:020}.request").exists(),
                    "Claimed request differs or remains published")
        else:
            require(request["operation"] == "speed" and request["mode"] == "submit" and request["action"] == "none"
                    and request["speed"] == 5 and request["actor"] == request["target"] == "FRA"
                    and session_raw(f"{seq:020}.request") == wire, "Aborted publication differs from preserved request")
        hosts[seq] = host
    # Refuse any unexpected later native claim instead of interpreting absence loosely.
    actual_claims = {p.name for p in session.glob("*.claim")}
    expected_claims = {"install.claim", *[row[1] for row in lab.PHASES.values()],
                       *[f"{s:020}.claim" for s in range(1, 13)], *[f"{s:020}.lease-pause.claim" for s in (4, 7, 10)]}
    require(actual_claims == expected_claims, "Unexpected/missing permanent claim")
    supervisor13 = [decode_json(line) for line in session_raw("00000000000000000013.supervisor.jsonl").decode("utf-8").splitlines()]
    validate_terminal(terminal, supervisor13, claim_exists=(session/"00000000000000000013.claim").exists(),
                      lease_claim_exists=(session/"00000000000000000013.lease-pause.claim").exists())
    effects = {}
    for seq, action, family, label, after_name, comparison_name in CASES:
        legality = evidence["requests"][seq-1]
        submitted = evidence["requests"][seq]
        validate_pair(legality, action, seq-1, submit=False)
        final = validate_pair(submitted, action, seq, submit=True)
        require(pair_statuses[seq-1]["request"] == legality, "Legality status differs from stopped log")
        if seq != 3:
            require(pair_statuses[seq]["request"] == submitted, "Submit status differs from stopped log")
        before_rel = f"relations-v10-baseline-{family}-POR-46408.json"
        after_rel = f"relations-v10-{after_name}-POR-46408.json"
        comparison_rel = f"relations-v10-{comparison_name}-POR-result-46408.json"
        before, after, comparison = document(before_rel), document(after_rel), document(comparison_rel)
        recomputed = observer.compare_reports(before, after, "positive")
        require(comparison == dict(recomputed, inputs={"before_sha256": hashes[before_rel].lower(), "after_sha256": hashes[after_rel].lower()})
                and recomputed["observed_effect"] is True and recomputed["transition"] == "added_selected_state",
                "Selected pair comparison cannot be reproduced")
        for report in (before, after):
            sample, state, _ = observer.validated_report(report)
            same_identity({"pid": report["source"]["pid"], "creation": f'{report["source"]["process_creation_filetime"]:016x}'})
            require(sample["game"] == WORLD and report["action"] == family and report["target"] == "POR"
                    and int(sample["pair"]["FRA"]["handle"], 16) == 0x100007A00415246
                    and int(sample["pair"]["POR"]["handle"], 16) == 0x10000BD00524F50, "Observation world/country differs")
        require(after["observation"]["passes"][0]["current_raw_date"] == final["raw_date"], "Post-state date differs from native dispatch")
        effects[action] = {"legality_sequence": seq-1, "submit_sequence": seq, "native_legality_checked": True,
                           "native_dispatch_completed": True, "consumer_ownership_reported_consumed": True,
                           "selected_state_observed": True, "saved_state_verified": False, "reload_verified": False,
                           "request_causality_verified": False, "ai_acceptance_verified": False}
    http_intent = decode_json(session_raw("00000000000000000003.http-intent").decode("utf-8"))
    validate_http(http, evidence["requests"][3], http_intent, hosts[3])
    old_before = document("relations-v10-baseline-offermilaccess-POR-46408.json")
    old_after = document("relations-v10-after-offer-military-POR-46408.json")
    old_comparison = document("relations-v10-offermilaccess-positive-POR-result-46408.json")
    old_recomputed = observer.compare_reports(old_before, old_after, "positive")
    require(old_recomputed["status"] == "unknown" and old_recomputed["observed_effect"] is False
            and old_comparison == dict(old_recomputed, inputs={
                "before_sha256": hashes["relations-v10-baseline-offermilaccess-POR-46408.json"].lower(),
                "after_sha256": hashes["relations-v10-after-offer-military-POR-46408.json"].lower()}),
            "Earlier inconclusive military-offer comparison was changed/promoted")
    for seq in (4, 7, 10):
        events = [decode_json(line) for line in session_raw(f"{seq:020}.supervisor.jsonl").decode("utf-8").splitlines()]
        require(len(events) == 2 and events[0]["event"] == "supervisor_armed" and events[1]["event"] == "supervisor_complete", "Incomplete successful supervision")
        for event in events:
            same_identity(event)
            require(event["sequence"] == seq and event["speed"] == 5 and event["retry_allowed"] is False, "Foreign supervision")
        require(events[0]["before"]["paused"] is True and events[1]["after"]["paused"] is True
                and events[1]["native_lease_complete"] == evidence["requests"][seq]["lease_complete"], "Speed pause proof differs")
    require([seq for seq,row in evidence["requests"].items() if row["request"]["operation"] == "pair" and row["request"]["mode"] == "submit"] == [3, 6, 9, 12], "Extra/missing pair submits")
    return {"schema_version": 1, "purpose": "v10_interrupted_experiment_evidence_review", "read_only": True,
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat(), "review_status": "reviewed_interrupted_session",
            "pid": PID, "creation": CREATION, "dll_sha256": DLL_SHA, "manifest_sha256": MANIFEST_SHA,
            "game_sha256": lab.LOCAL_SHA256, "fixture_profile_sha256": lab.FIXTURE_PROFILE_SHA256,
            "phase_checks_passed": True, "phase_case_counts": {"lifecycle": 12, "preview": 48, "command": 48},
            "pair_submits": 4, "actions": effects, "all_planned_fourteen_effects_verified": False,
            "http_alliance_publication_and_readonly_replay_verified": True, "http_server_closed_reported": True,
            "aborted_session": {"terminal_reason": FREEZE_REASON, "specific_failure_cause_verified": False,
                "last_native_claimed_sequence": 12, "unclaimed_published_sequence": 13, "request_preserved": True,
                "native_claim_observed": False, "native_dispatch_observed": False, "supervisor_stopped_exact_process_reported": True,
                "last_healthy_paused_raw_date": 56457144, "automatic_retry": False},
            "inconclusive_observations": [{"family": "offermilaccess", "source": "relations-v10-offermilaccess-positive-POR-result-46408.json", "observed_effect": False}],
            "saved_state_verified": False, "reload_verified": False, "request_id_causality_verified": False,
            "whole_world_unchanged_verified": False, "exact_loaded_file_path_verified": False,
            "strict_live_single_player_verified": False, "world_generation_verified": False, "production_backend_registered": False,
            "complete_log": {"path": SESSION_NAME + "/research-1375.jsonl", "size_bytes": LOG_BYTES, "sha256": LOG_SHA},
            "healthy_prefix_bytes": healthy_bytes, "healthy_prefix_sha256": evidence["log_sha256"],
            "status_prefix_bytes": prefix_matches, "input_sha256": hashes,
            "reviewer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
            "limitations": ["This session stopped after four positive pair submits; remaining operations and all save/reload checks are unverified.",
                "The terminal generic reason does not identify TTL, file sharing or a claim collision as the exact cause.",
                "The healthy prefix is validated separately; it never makes the frozen session ready again.",
                "Selected two-pass state differences are not atomic request-ID causality or proof of AI acceptance, strict SP origin or world generation."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RUNTIME / "native1375-v10/experiment-summary-46408.json")
    args = parser.parse_args(argv)
    result = review()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "review_status": result["review_status"], "pair_submits": 4,
                      "saved_state_verified": False, "reload_verified": False, "inputs": len(result["input_sha256"])}))


if __name__ == "__main__":
    main()
