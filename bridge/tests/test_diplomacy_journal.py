from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest

from bridge.diplomacy_journal import (
    AcceptanceEvidenceRequired,
    AmbiguousRequestError,
    ContextMismatchError,
    DurableJournal,
    EvidenceConflictError,
    ExecutionEvidenceRequired,
    InvalidTransitionError,
    RequestConflictError,
    SubmissionClaimRequired,
)


class DurableJournalTests(unittest.TestCase):
    def _ready(self, journal: DurableJournal, request_id: str = "req_1") -> None:
        journal.register(request_id, {"action": "offer_alliance", "target": "ENG"})
        journal.transition(request_id, "queued")
        journal.transition(request_id, "consumed")
        journal.transition(request_id, "constructed")

    def test_registration_is_canonical_idempotent_and_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            first = DurableJournal(path, "exp_a", "session_1")
            original = first.register("req_1", {"z": 3, "a": [1, True]})
            identical = first.register("req_1", {"a": [1, True], "z": 3})
            self.assertEqual(original.payload_sha256, identical.payload_sha256)
            self.assertEqual(original.created_at, identical.created_at)
            with self.assertRaises(RequestConflictError):
                first.register("req_1", {"a": [1, False], "z": 3})
            first.close()

            second = DurableJournal(path, "exp_a", "session_1")
            recovered = second.get_request("req_1")
            self.assertEqual(recovered.status, "received")
            self.assertEqual(recovered.payload, {"a": [1, True], "z": 3})
            self.assertEqual(recovered.payload_sha256, original.payload_sha256)
            second.close()

    def test_experiment_and_session_are_part_of_the_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            session_a = DurableJournal(path, "exp_a", "session_a")
            session_b = DurableJournal(path, "exp_a", "session_b")
            other_experiment = DurableJournal(path, "exp_b", "session_a")
            session_a.register("same_id", {"value": "a"})
            session_b.register("same_id", {"value": "b"})
            other_experiment.register("same_id", {"value": "c"})
            self.assertEqual(session_a.get_request("same_id").payload["value"], "a")
            self.assertEqual(session_b.get_request("same_id").payload["value"], "b")
            self.assertEqual(other_experiment.get_request("same_id").payload["value"], "c")
            with self.assertRaises(ContextMismatchError):
                session_a.record_event(
                    {
                        "experiment_id": "exp_a",
                        "session_id": "session_b",
                        "request_id": "same_id",
                        "event_id": "evt_1",
                        "arrival_layer": "bridge",
                        "evidence_type": "received",
                        "content": {},
                    }
                )
            session_a.close()
            session_b.close()
            other_experiment.close()

    def test_global_request_id_survives_restart_and_blocks_a_new_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            first = DurableJournal(
                path, "exp_a", "session_a", global_request_ids=True
            )
            first.register("external_1", {"action": "offer_alliance", "target": "ENG"})
            first.close()

            second = DurableJournal(
                path, "exp_b", "session_b", global_request_ids=True
            )
            with self.assertRaises(ContextMismatchError) as raised:
                second.register("external_1", {"action": "white_peace"})
            self.assertIn("GLOBAL_REQUEST_ID_CONTEXT_CONFLICT", str(raised.exception))
            historical = second.lookup_request("external_1")
            self.assertEqual(historical.experiment_id, "exp_a")
            self.assertEqual(historical.session_id, "session_a")
            self.assertEqual(historical.status, "received")
            second.close()

    def test_global_lookup_reads_archived_evidence_without_switching_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            first = DurableJournal(path, "exp_a", "session_a", global_request_ids=True)
            first.register("external_1", {"action": "offer_alliance"})
            first.record_evidence(
                "external_1",
                "request_received",
                {"source": "bridge"},
                arrival_layer="bridge",
                event_id="received_1",
            )
            first.close()

            second = DurableJournal(path, "exp_b", "session_b", global_request_ids=True)
            record = second.lookup_request("external_1")
            evidence = second.list_evidence_for_record(record)
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0].experiment_id, "exp_a")
            self.assertEqual(evidence[0].session_id, "session_a")
            # The fixed context remains the new operator session after lookup.
            second.register("new_external_1", {"action": "white_peace"})
            self.assertEqual(second.get_request("new_external_1").session_id, "session_b")
            second.close()

    def test_lookup_refuses_ambiguous_legacy_request_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            first = DurableJournal(path, "exp_a", "session_a")
            second = DurableJournal(path, "exp_b", "session_b")
            first.register("legacy_1", {"value": "a"})
            second.register("legacy_1", {"value": "b"})
            with self.assertRaises(AmbiguousRequestError) as raised:
                first.lookup_request("legacy_1")
            self.assertIn("AMBIGUOUS_REQUEST_ID", str(raised.exception))
            first.close()
            second.close()

    def test_claim_submission_is_atomic_and_never_duplicates_native_submit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            setup = DurableJournal(path, "exp_a", "session_a")
            self._ready(setup)
            setup.close()

            def claim() -> object:
                journal = DurableJournal(path, "exp_a", "session_a")
                try:
                    return journal.claim_submission("req_1")
                finally:
                    journal.close()

            with ThreadPoolExecutor(max_workers=8) as pool:
                claims = list(pool.map(lambda _index: claim(), range(8)))
            self.assertEqual(sum(item.claimed for item in claims), 1)
            self.assertEqual({item.submission_id for item in claims}, {claims[0].submission_id})
            self.assertEqual({item.status for item in claims}, {"constructed"})
            check = DurableJournal(path, "exp_a", "session_a")
            try:
                claim_record = check.get_request("req_1")
                self.assertEqual(claim_record.status, "constructed")
                self.assertIsNotNone(claim_record.claimed_at)
                self.assertIsNone(claim_record.submitted_at)
            finally:
                check.close()

    def test_different_requests_are_mutually_exclusive_on_one_native_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            journal = DurableJournal(path, "exp_a", "session_a")
            self._ready(journal, "req_a")
            self._ready(journal, "req_b")
            first = journal.claim_submission("req_a", submission_id="native_a")
            blocked = journal.claim_submission("req_b", submission_id="native_b")
            self.assertTrue(first.claimed)
            self.assertFalse(blocked.claimed)
            self.assertTrue(blocked.busy)
            self.assertEqual(blocked.blocked_by_request_id, "req_a")
            self.assertEqual(journal.get_request("req_b").status, "constructed")
            journal.close()

    def test_claimed_request_survives_restart_without_a_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            first = DurableJournal(path, "exp_a", "session_a")
            self._ready(first)
            claim = first.claim_submission("req_1", submission_id="native_1")
            first.mark_unknown("req_1", {"kind": "transport_timeout", "waited_ms": 1000})
            first.close()

            second = DurableJournal(path, "exp_a", "session_a")
            retry = second.claim_submission("req_1", submission_id="native_retry")
            self.assertFalse(retry.claimed)
            self.assertEqual(retry.status, "unknown")
            self.assertEqual(retry.submission_id, "native_1")
            with self.assertRaises(InvalidTransitionError):
                second.mark_submitted("req_1", claim.claim_token, {"submitted": True})
            second.close()

    def test_native_acceptance_entry_is_not_acceptance_and_consequence_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            journal = DurableJournal(path, "exp_a", "session_a")
            self._ready(journal)
            claim = journal.claim_submission("req_1", submission_id="native_1")
            submitted = journal.mark_submitted(
                "req_1", claim.claim_token, {"native_request": "native_1", "accepted_entry": True}
            )
            self.assertEqual(submitted.status, "submitted")
            entry = journal.record_evidence(
                "req_1",
                "native_acceptance_entry",
                {"entered": True},
                arrival_layer="native_response",
                event_id="evt_entry",
            )
            self.assertEqual(entry.arrival_layer, "native_response")
            self.assertEqual(journal.get_request("req_1").status, "submitted")
            with self.assertRaises(AcceptanceEvidenceRequired):
                journal.mark_accepted(
                    "req_1",
                    {"entry": True},
                    evidence_type="native_acceptance_entry",
                    arrival_layer="native_response",
                    event_id="evt_bad",
                )
            accepted = journal.mark_accepted(
                "req_1",
                {"war_ended": True, "truce_created": True},
                event_id="evt_consequence",
            )
            self.assertEqual(accepted.status, "accepted")
            self.assertEqual(accepted.evidence_count, 3)
            journal.close()

    def test_submitted_native_results_persist_through_accept_and_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            journal = DurableJournal(path, "exp_a", "session_a")
            self._ready(journal, "accepted_1")
            accept_claim = journal.claim_submission("accepted_1", submission_id="native_accept")
            accept_receipt = {
                "event": "native_alliance_submission_result",
                "request_id": "accepted_1", "submitted": True,
                "native_queue_verified": True, "transport_ring": True,
                "native_sequence": 11, "native_origin": "native_submit", "native_flags": 1,
            }
            journal.mark_submitted("accepted_1", accept_claim.claim_token, accept_receipt)
            recorded_accept = journal.record_result(
                "accepted_1",
                {"native_response": "received", "request_id": "accepted_1"},
                evidence_type="native_response",
                evidence_content={"business_result": "pending"},
                arrival_layer="native_response",
                event_id="native-response-accepted",
            )
            self.assertEqual("submitted", recorded_accept.status)
            accepted = journal.mark_accepted(
                "accepted_1", {"alliance_created": True}, event_id="native-consequence-accepted"
            )
            self.assertEqual("accepted", accepted.status)

            self._ready(journal, "rejected_1")
            reject_claim = journal.claim_submission("rejected_1", submission_id="native_reject")
            journal.mark_submitted(
                "rejected_1", reject_claim.claim_token,
                {"event": "native_alliance_submission_result", "submitted": True,
                 "native_queue_verified": True, "transport_ring": True,
                 "native_sequence": 12, "native_origin": "native_submit", "native_flags": 1},
            )
            recorded_reject = journal.record_result(
                "rejected_1",
                {"native_response": "rejected", "request_id": "rejected_1"},
                evidence_type="native_response",
                evidence_content={"business_result": "rejected"},
                arrival_layer="native_response",
                event_id="native-response-rejected",
            )
            self.assertEqual("submitted", recorded_reject.status)
            rejected = journal.mark_rejected(
                "rejected_1", {"business_result": "rejected"}, event_id="native-rejection"
            )
            self.assertEqual("rejected", rejected.status)
            journal.close()

            reopened = DurableJournal(path, "exp_a", "session_a")
            accepted_after_restart = reopened.get_request("accepted_1")
            rejected_after_restart = reopened.get_request("rejected_1")
            self.assertEqual("accepted", accepted_after_restart.status)
            self.assertEqual({"alliance_created": True}, accepted_after_restart.result)
            self.assertTrue(accepted_after_restart.native_receipt["native_queue_verified"])
            self.assertEqual("rejected", rejected_after_restart.status)
            self.assertEqual({"business_result": "rejected"}, rejected_after_restart.result)
            self.assertTrue(rejected_after_restart.native_receipt["native_queue_verified"])
            self.assertEqual(3, accepted_after_restart.evidence_count)
            self.assertEqual(3, rejected_after_restart.evidence_count)
            reopened.close()

    def test_executed_is_distinct_terminal_state_and_persists_without_resubmit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            journal = DurableJournal(path, "exp_a", "session_a")
            self._ready(journal)
            claim = journal.claim_submission("req_1", submission_id="native_1")
            journal.mark_submitted(
                "req_1", claim.claim_token,
                {"event": "native_submission", "submitted": True},
            )
            journal.transition("req_1", "executing")
            executed = journal.mark_executed(
                "req_1",
                {"alliance_after": True, "native_state": 2},
                event_id="native-consequence-executed",
            )
            self.assertEqual("executed", executed.status)
            self.assertTrue(executed.terminal)
            self.assertEqual(
                {"alliance_after": True, "native_state": 2}, executed.result
            )
            self.assertEqual(2, executed.evidence_count)
            with self.assertRaises(ExecutionEvidenceRequired):
                journal.transition("req_1", "executed")
            retry = journal.claim_submission("req_1", submission_id="native_retry")
            self.assertFalse(retry.claimed)
            self.assertEqual("executed", retry.status)
            journal.close()

            reopened = DurableJournal(path, "exp_a", "session_a")
            recovered = reopened.get_request("req_1")
            self.assertEqual("executed", recovered.status)
            self.assertEqual(
                {"alliance_after": True, "native_state": 2}, recovered.result
            )
            self.assertEqual(2, recovered.evidence_count)
            repeated = reopened.mark_executed(
                "req_1", {"different": "ignored"}, event_id="different-event"
            )
            self.assertEqual("executed", repeated.status)
            self.assertEqual(2, repeated.evidence_count)
            reopened.close()

    def test_executed_requires_submission_and_real_consequence_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            journal = DurableJournal(path, "exp_a", "session_a")
            self._ready(journal)
            with self.assertRaises(ExecutionEvidenceRequired):
                journal.mark_executed("req_1", {"alliance_after": True})
            self.assertEqual("constructed", journal.get_request("req_1").status)

            claim = journal.claim_submission("req_1")
            journal.mark_submitted("req_1", claim.claim_token, {"submitted": True})
            journal.record_evidence(
                "req_1",
                "native_acceptance_entry",
                {"entered": True},
                arrival_layer="native_response",
                event_id="entry-only",
            )
            with self.assertRaises(ExecutionEvidenceRequired):
                journal.mark_executed(
                    "req_1",
                    {"entered": True},
                    evidence_type="native_acceptance_entry",
                    arrival_layer="native_response",
                    event_id="bad-executed-entry",
                )
            with self.assertRaises(ExecutionEvidenceRequired):
                journal.transition(
                    "req_1",
                    "executed",
                    result={"alliance_after": True},
                    evidence_type="native_consequence",
                    evidence_content={"alliance_after": True},
                    arrival_layer="native_consequence",
                )
            self.assertEqual("submitted", journal.get_request("req_1").status)
            journal.close()

    def test_legacy_check_migration_preserves_request_evidence_and_foreign_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE diplomacy_requests (
                    experiment_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'received', 'queued', 'consumed', 'constructed',
                        'submitted', 'executing', 'waiting_response',
                        'accepted', 'rejected', 'cancelled', 'expired',
                        'invalidated', 'unknown'
                    )),
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    submission_id TEXT,
                    submission_token TEXT,
                    submitted_at TEXT,
                    PRIMARY KEY (experiment_id, session_id, request_id)
                );
                CREATE TABLE diplomacy_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    arrival_layer TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    content_format TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (experiment_id, session_id, request_id)
                        REFERENCES diplomacy_requests(experiment_id, session_id, request_id)
                        ON DELETE CASCADE,
                    UNIQUE (experiment_id, session_id, request_id, event_id)
                );
                CREATE INDEX diplomacy_evidence_request_idx
                    ON diplomacy_evidence (experiment_id, session_id, request_id, evidence_id);
                """
            )
            connection.execute(
                """
                INSERT INTO diplomacy_requests (
                    experiment_id, session_id, request_id, payload_json,
                    payload_sha256, status, result_json, created_at,
                    updated_at, submission_id, submission_token, submitted_at
                ) VALUES (?, ?, ?, ?, ?, 'received', NULL, ?, ?, NULL, NULL, NULL)
                """,
                (
                    "exp_a", "session_a", "legacy_1",
                    '{"action":"offer_alliance"}', "legacy-payload-sha",
                    "2026-10-15T00:00:00+00:00", "2026-10-15T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO diplomacy_evidence (
                    evidence_id, experiment_id, session_id, request_id,
                    event_id, arrival_layer, evidence_type, content_text,
                    content_format, content_sha256, observed_at, recorded_at
                ) VALUES (7, 'exp_a', 'session_a', 'legacy_1', 'legacy-event',
                          'bridge', 'request_received', '{"legacy":true}',
                          'json', 'legacy-content-sha',
                          '2026-10-15T00:00:00+00:00',
                          '2026-10-15T00:00:00+00:00')
                """
            )
            connection.commit()
            connection.close()

            journal = DurableJournal(path, "exp_a", "session_a")
            legacy = journal.get_request("legacy_1")
            self.assertEqual("received", legacy.status)
            self.assertEqual({"action": "offer_alliance"}, legacy.payload)
            self.assertEqual(1, legacy.evidence_count)
            legacy_evidence = journal.list_evidence("legacy_1")[0]
            self.assertEqual(7, legacy_evidence.evidence_id)
            self.assertEqual("legacy-event", legacy_evidence.event_id)

            journal.transition("legacy_1", "queued")
            journal.transition("legacy_1", "consumed")
            journal.transition("legacy_1", "constructed")
            claim = journal.claim_submission("legacy_1", submission_id="legacy-native")
            journal.mark_submitted(
                "legacy_1", claim.claim_token, {"submitted": True, "legacy": True}
            )
            executed = journal.mark_executed(
                "legacy_1", {"alliance_after": True}, event_id="legacy-consequence"
            )
            self.assertEqual("executed", executed.status)
            self.assertEqual(3, executed.evidence_count)

            check = sqlite3.connect(path)
            try:
                request_sql = check.execute(
                    "SELECT sql FROM sqlite_master WHERE name = 'diplomacy_requests'"
                ).fetchone()[0]
                self.assertIn("executed", request_sql.lower())
                columns = {
                    row[1]
                    for row in check.execute("PRAGMA table_info(diplomacy_requests)")
                }
                self.assertIn("claimed_at", columns)
                self.assertIn("native_receipt_json", columns)
                foreign_keys = check.execute(
                    "PRAGMA foreign_key_list(diplomacy_evidence)"
                ).fetchall()
                self.assertTrue(any(row[2] == "diplomacy_requests" for row in foreign_keys))
                self.assertEqual([], check.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual(
                    1,
                    check.execute(
                        "SELECT COUNT(*) FROM diplomacy_evidence WHERE event_id = 'legacy-event'"
                    ).fetchone()[0],
                )
            finally:
                check.close()
            journal.close()

    def test_timeout_is_not_rejection_and_duplicate_events_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            journal = DurableJournal(path, "exp_a", "session_a")
            self._ready(journal)
            claim = journal.claim_submission("req_1")
            journal.mark_submitted("req_1", claim.claim_token, {"native_request": "native_1"})
            first = journal.record_evidence(
                "req_1",
                "transport_timeout",
                {"waited_ms": 1000},
                arrival_layer="bridge_timeout",
                event_id="evt_timeout",
            )
            duplicate = journal.record_evidence(
                "req_1",
                "transport_timeout",
                {"waited_ms": 1000},
                arrival_layer="bridge_timeout",
                event_id="evt_timeout",
            )
            self.assertEqual(first.evidence_id, duplicate.evidence_id)
            automatic_first = journal.record_evidence(
                "req_1",
                "transport_timeout",
                {"waited_ms": 1000},
                arrival_layer="bridge_timeout",
            )
            automatic_duplicate = journal.record_evidence(
                "req_1",
                "transport_timeout",
                {"waited_ms": 1000},
                arrival_layer="bridge_timeout",
            )
            self.assertEqual(automatic_first.evidence_id, automatic_duplicate.evidence_id)
            with self.assertRaises(EvidenceConflictError):
                journal.record_evidence(
                    "req_1",
                    "transport_timeout",
                    {"waited_ms": 2000},
                    arrival_layer="bridge_timeout",
                    event_id="evt_timeout",
                )
            unknown = journal.mark_unknown("req_1", "response timeout")
            self.assertEqual(unknown.status, "unknown")
            self.assertNotEqual(unknown.status, "rejected")
            journal.close()

    def test_structured_timeout_cannot_be_recorded_as_business_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = DurableJournal(Path(directory) / "journal.sqlite3", "exp_a", "session_a")
            self._ready(journal)
            claim = journal.claim_submission("req_1")
            journal.mark_submitted("req_1", claim.claim_token, {"native_request": "native_1"})
            with self.assertRaises(InvalidTransitionError):
                journal.mark_rejected(
                    "req_1",
                    {"kind": "transport_timeout", "waited_ms": 1000},
                )
            self.assertEqual(journal.get_request("req_1").status, "submitted")
            journal.close()

    def test_unknown_before_native_submission_cannot_be_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = DurableJournal(Path(directory) / "journal.sqlite3", "exp_a", "session_a")
            self._ready(journal)
            claim = journal.claim_submission("req_1")
            journal.mark_unknown("req_1", "submitter crashed before delivery")
            self.assertEqual(journal.get_request("req_1").status, "unknown")
            with self.assertRaises(AcceptanceEvidenceRequired):
                journal.mark_accepted("req_1", {"war_ended": True})
            with self.assertRaises(InvalidTransitionError):
                journal.mark_submitted("req_1", claim.claim_token, {"native_request": "late"})
            journal.close()

    def test_queued_cannot_jump_to_accepted_and_invalid_state_jump_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = DurableJournal(Path(directory) / "journal.sqlite3", "exp_a", "session_a")
            journal.register("req_1", {"action": "white_peace"})
            journal.transition("req_1", "queued")
            with self.assertRaises(AcceptanceEvidenceRequired):
                journal.mark_accepted("req_1", {"peace": True})
            with self.assertRaises(AcceptanceEvidenceRequired):
                journal.transition("req_1", "accepted")
            with self.assertRaises(SubmissionClaimRequired):
                journal.transition("req_1", "submitted")
            journal.close()


if __name__ == "__main__":
    unittest.main()
