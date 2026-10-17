"""Durable request and evidence journal for the diplomacy bridge.

This module is deliberately independent of the native bridge.  It records the
state of a request and the evidence observed at each layer, but it does not
submit anything to a game process.  A request is scoped by an experiment and
session, so a request id can safely be reused in a new experiment session.

The journal uses only SQLite from the standard library.  State transitions and
the submission claim are committed transactions; a caller can therefore use
``claim_submission`` as the one hand-off point before invoking a native
submitter and ``mark_submitted`` to record its receipt.  An acceptance entry is
evidence about an intermediate native path,
not an accepted business result.  ``mark_accepted`` requires a consequence
evidence event instead.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import uuid
from typing import Any, Iterator, Mapping


REQUEST_STATES = frozenset(
    {
        "received",
        "queued",
        "consumed",
        "constructed",
        "submitted",
        "executing",
        "waiting_response",
        "executed",
        "accepted",
        "rejected",
        "cancelled",
        "expired",
        "invalidated",
        "unknown",
    }
)

# Public aliases make the contract easy to discover without requiring callers
# to duplicate the state list.
STATUSES = REQUEST_STATES
VALID_STATUSES = REQUEST_STATES
VALID_REQUEST_STATES = REQUEST_STATES

_TERMINAL_STATES = frozenset(
    {"executed", "accepted", "rejected", "cancelled", "expired", "invalidated"}
)
_TRANSITIONS: dict[str, frozenset[str]] = {
    "received": frozenset({"queued", "invalidated", "cancelled", "expired", "unknown"}),
    "queued": frozenset({"consumed", "invalidated", "cancelled", "expired", "unknown"}),
    "consumed": frozenset({"constructed", "invalidated", "cancelled", "expired", "unknown"}),
    "constructed": frozenset({"invalidated", "cancelled", "expired", "unknown"}),
    "submitted": frozenset(
        {
            "executing",
            "waiting_response",
            "executed",
            "accepted",
            "rejected",
            "invalidated",
            "cancelled",
            "expired",
            "unknown",
        }
    ),
    "executing": frozenset(
        {
            "waiting_response",
            "executed",
            "accepted",
            "rejected",
            "invalidated",
            "cancelled",
            "expired",
            "unknown",
        }
    ),
    "waiting_response": frozenset(
        {
            "executed",
            "accepted",
            "rejected",
            "invalidated",
            "cancelled",
            "expired",
            "unknown",
        }
    ),
    # An unknown result may be reconciled after a later observation.  This is
    # the only non-terminal state that can be resolved after it was unknown.
    "unknown": frozenset(
        {"executed", "accepted", "rejected", "invalidated", "cancelled", "expired"}
    ),
    "executed": frozenset(),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "cancelled": frozenset(),
    "expired": frozenset(),
    "invalidated": frozenset(),
}

_ENTRY_ONLY_WORDS = frozenset(
    {
        "accept",
        "accepted",
        "acceptance",
        "entry",
        "dispatch",
        "queue",
        "queued",
        "submit",
        "submitted",
        "transport",
    }
)
_CONSEQUENCE_LAYERS = frozenset(
    {
        "consequence",
        "game_state",
        "native_consequence",
        "postcondition",
        "response_consequence",
        "save_reload",
        "actual_result",
    }
)
_REJECTION_LAYERS = frozenset(
    {
        "native_response",
        "native_rejection",
        "native_execution",
        "native_consequence",
        "game_state",
        "response",
    }
)


class JournalError(RuntimeError):
    """Base class for durable journal errors."""


class RequestConflictError(JournalError):
    """The request id is already registered with another payload."""


class ContextMismatchError(JournalError):
    """An operation attempted to cross experiment or session boundaries."""


class AmbiguousRequestError(JournalError):
    """A request id resolves to more than one historical scoped record."""


class UnknownRequestError(JournalError):
    """The requested journal record does not exist in the selected session."""


class InvalidTransitionError(JournalError):
    """A request state transition is not valid for the current state."""


class SubmissionClaimRequired(JournalError):
    """The submitted state can only be entered through mark_submitted."""


class AcceptanceEvidenceRequired(JournalError):
    """An accepted result requires evidence of an actual consequence."""


class ExecutionEvidenceRequired(AcceptanceEvidenceRequired):
    """An executed result requires submission and actual consequence evidence."""


class EvidenceConflictError(JournalError):
    """An event id was reused with different evidence."""


class SubmissionBusyError(JournalError):
    """The experiment/session already has another active submission claim."""


_MISSING = object()


def _canonical_json(value: Any) -> str:
    """Return deterministic JSON or raise a useful journal error."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise JournalError(f"value is not canonical JSON: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_fingerprint(payload_json: str) -> str:
    return _sha256(payload_json.encode("utf-8"))


def _validate_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise JournalError(f"{label} must be a non-empty string")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _content(value: Any) -> tuple[str, str, str]:
    """Return stored text, format, and hash of the original content bytes."""

    if isinstance(value, bytes):
        return (
            base64.b64encode(value).decode("ascii"),
            "bytes_base64",
            _sha256(value),
        )
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return value, "text", _sha256(encoded)
    serialized = _canonical_json(value)
    return serialized, "json", _sha256(serialized.encode("utf-8"))


def _decode_content(text: str, content_format: str) -> Any:
    if content_format == "bytes_base64":
        return base64.b64decode(text.encode("ascii"))
    if content_format == "json":
        return json.loads(text)
    return text


def _word_set(value: str) -> set[str]:
    return {word for word in value.lower().replace("-", "_").split("_") if word}


def _looks_like_timeout(value: Any) -> bool:
    """Recognize timeout markers in strings and structured result objects."""

    if isinstance(value, str):
        normalized = value.lower().replace("-", "_")
        return "timeout" in normalized or "timed_out" in normalized
    if isinstance(value, Mapping):
        return any(
            _looks_like_timeout(key) or _looks_like_timeout(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_looks_like_timeout(item) for item in value)
    return False


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: int
    event_id: str
    experiment_id: str
    request_id: str
    session_id: str
    arrival_layer: str
    evidence_type: str
    content: Any
    content_format: str
    content_sha256: str
    observed_at: str
    recorded_at: str

    @property
    def id(self) -> int:
        return self.evidence_id

    @property
    def sha256(self) -> str:
        return self.content_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "experiment_id": self.experiment_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "arrival_layer": self.arrival_layer,
            "evidence_type": self.evidence_type,
            "content": self.content,
            "content_format": self.content_format,
            "content_sha256": self.content_sha256,
            "observed_at": self.observed_at,
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True)
class RequestRecord:
    experiment_id: str
    request_id: str
    session_id: str
    payload: Any
    payload_json: str
    payload_sha256: str
    status: str
    result: Any
    result_json: str | None
    created_at: str
    updated_at: str
    submission_id: str | None
    submission_token: str | None
    claimed_at: str | None
    submitted_at: str | None
    native_receipt: Any
    native_receipt_json: str | None
    evidence_count: int
    last_evidence_type: str | None
    last_evidence_layer: str | None
    last_evidence_sha256: str | None

    @property
    def payload_fingerprint(self) -> str:
        return self.payload_sha256

    @property
    def result_updated_at(self) -> str:
        return self.updated_at

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "payload": self.payload,
            "payload_json": self.payload_json,
            "payload_sha256": self.payload_sha256,
            "payload_fingerprint": self.payload_sha256,
            "status": self.status,
            "result": self.result,
            "result_json": self.result_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result_updated_at": self.updated_at,
            "submission_id": self.submission_id,
            "submission_token": self.submission_token,
            "claimed_at": self.claimed_at,
            "submitted_at": self.submitted_at,
            "native_receipt": self.native_receipt,
            "native_receipt_json": self.native_receipt_json,
            "evidence_count": self.evidence_count,
            "last_evidence_type": self.last_evidence_type,
            "last_evidence_layer": self.last_evidence_layer,
            "last_evidence_sha256": self.last_evidence_sha256,
        }


@dataclass(frozen=True)
class SubmissionClaim:
    experiment_id: str
    request_id: str
    session_id: str
    claimed: bool
    submission_id: str | None
    claim_token: str | None
    status: str
    claimed_at: str | None
    blocked_by_request_id: str | None = None

    @property
    def acquired(self) -> bool:
        return self.claimed

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "claimed": self.claimed,
            "acquired": self.claimed,
            "submission_id": self.submission_id,
            "claim_token": self.claim_token,
            "status": self.status,
            "claimed_at": self.claimed_at,
            "blocked_by_request_id": self.blocked_by_request_id,
        }

    @property
    def busy(self) -> bool:
        return self.blocked_by_request_id is not None


class DurableJournal:
    """SQLite-backed request state and evidence journal.

    ``experiment_id`` and ``session_id`` may be supplied at construction or
    per call.  Supplying them at construction is recommended because it makes
    accidental cross-session evidence writes fail immediately.
    """

    def __init__(
        self,
        path: str | Path,
        experiment_id: str | None = None,
        session_id: str | None = None,
        global_request_ids: bool = False,
    ) -> None:
        self.path = str(path)
        self.experiment_id = (
            _validate_text(experiment_id, "experiment_id")
            if experiment_id is not None
            else None
        )
        self.session_id = (
            _validate_text(session_id, "session_id") if session_id is not None else None
        )
        self.global_request_ids = bool(global_request_ids)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def __enter__(self) -> "DurableJournal":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        # A best-effort close keeps WAL sidecars from holding temporary test
        # directories open when a caller forgets an explicit close.
        try:
            self.close()
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None  # type: ignore[assignment]

    @staticmethod
    def _create_requests_table(
        connection: sqlite3.Connection, table_name: str
    ) -> None:
        connection.execute(
            f"""
            CREATE TABLE "{table_name}" (
                experiment_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN (
                    'received', 'queued', 'consumed', 'constructed',
                    'submitted', 'executing', 'waiting_response', 'executed',
                    'accepted', 'rejected', 'cancelled', 'expired',
                    'invalidated', 'unknown'
                )),
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                submission_id TEXT,
                submission_token TEXT,
                claimed_at TEXT,
                submitted_at TEXT,
                native_receipt_json TEXT,
                PRIMARY KEY (experiment_id, session_id, request_id)
            )
            """
        )

    @staticmethod
    def _create_evidence_table(
        connection: sqlite3.Connection, table_name: str
    ) -> None:
        connection.execute(
            f"""
            CREATE TABLE "{table_name}" (
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
                    REFERENCES diplomacy_requests_executed_migration(
                        experiment_id, session_id, request_id
                    ) ON DELETE CASCADE,
                UNIQUE (experiment_id, session_id, request_id, event_id)
            )
            """
        )

    def _migrate_status_constraint(self) -> None:
        """Rebuild an old request table whose CHECK lacks ``executed``.

        SQLite cannot alter a CHECK constraint in place.  The migration uses
        ordinary table creation/copy/rename operations so request rows,
        evidence rows, foreign keys, and evidence ids remain durable.  It is
        intentionally separate from the additive column migration above.
        """

        row = self._connection.execute(
            """
            SELECT sql FROM sqlite_master
             WHERE type = 'table' AND name = 'diplomacy_requests'
            """
        ).fetchone()
        schema_sql = str(row[0]) if row is not None and row[0] is not None else ""
        if "executed" in schema_sql.lower():
            return

        request_tmp = "diplomacy_requests_executed_migration"
        evidence_tmp = "diplomacy_evidence_executed_migration"
        for table_name in (request_tmp, evidence_tmp):
            existing = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if existing is not None:
                raise JournalError(
                    f"migration staging table already exists: {table_name}"
                )

        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            self._create_requests_table(connection, request_tmp)
            self._create_evidence_table(connection, evidence_tmp)
            connection.execute(
                f"""
                INSERT INTO "{request_tmp}" (
                    experiment_id, session_id, request_id, payload_json,
                    payload_sha256, status, result_json, created_at,
                    updated_at, submission_id, submission_token, claimed_at,
                    submitted_at, native_receipt_json
                )
                SELECT experiment_id, session_id, request_id, payload_json,
                       payload_sha256, status, result_json, created_at,
                       updated_at, submission_id, submission_token, claimed_at,
                       submitted_at, native_receipt_json
                  FROM diplomacy_requests
                """
            )
            connection.execute(
                f"""
                INSERT INTO "{evidence_tmp}" (
                    evidence_id, experiment_id, session_id, request_id,
                    event_id, arrival_layer, evidence_type, content_text,
                    content_format, content_sha256, observed_at, recorded_at
                )
                SELECT evidence_id, experiment_id, session_id, request_id,
                       event_id, arrival_layer, evidence_type, content_text,
                       content_format, content_sha256, observed_at, recorded_at
                  FROM diplomacy_evidence
                """
            )
            connection.execute("DROP TABLE diplomacy_evidence")
            connection.execute("DROP TABLE diplomacy_requests")
            connection.execute(
                f'ALTER TABLE "{request_tmp}" RENAME TO diplomacy_requests'
            )
            # Renaming the parent first lets SQLite update the temporary
            # evidence table's foreign-key reference before it is published.
            connection.execute(
                f'ALTER TABLE "{evidence_tmp}" RENAME TO diplomacy_evidence'
            )
            connection.execute(
                """
                CREATE INDEX diplomacy_evidence_request_idx
                    ON diplomacy_evidence (
                        experiment_id, session_id, request_id, evidence_id
                    )
                """
            )
            max_evidence_id = connection.execute(
                "SELECT COALESCE(MAX(evidence_id), 0) FROM diplomacy_evidence"
            ).fetchone()[0]
            connection.execute(
                "INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                ("diplomacy_evidence", int(max_evidence_id)),
            )
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()

    def _create_schema(self) -> None:
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS diplomacy_requests (
                    experiment_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'received', 'queued', 'consumed', 'constructed',
                        'submitted', 'executing', 'waiting_response', 'executed',
                        'accepted', 'rejected', 'cancelled', 'expired',
                        'invalidated', 'unknown'
                    )),
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    submission_id TEXT,
                    submission_token TEXT,
                    claimed_at TEXT,
                    submitted_at TEXT,
                    native_receipt_json TEXT,
                    PRIMARY KEY (experiment_id, session_id, request_id)
                );

                CREATE TABLE IF NOT EXISTS diplomacy_evidence (
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

                CREATE INDEX IF NOT EXISTS diplomacy_evidence_request_idx
                    ON diplomacy_evidence (experiment_id, session_id, request_id, evidence_id);
                """
            )
            # Keep databases created by older journal revisions readable.  The
            # migration is additive for columns and rebuilds only the request
            # CHECK constraint when it predates the executed terminal state.
            columns = {
                row[1]
                for row in self._connection.execute(
                    "PRAGMA table_info(diplomacy_requests)"
                ).fetchall()
            }
            for name, definition in (
                ("claimed_at", "TEXT"),
                ("native_receipt_json", "TEXT"),
            ):
                if name not in columns:
                    self._connection.execute(
                        f"ALTER TABLE diplomacy_requests ADD COLUMN {name} {definition}"
                    )
            self._migrate_status_constraint()

    def _context(
        self,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> tuple[str, str]:
        if self.experiment_id is not None and experiment_id is not None:
            if experiment_id != self.experiment_id:
                raise ContextMismatchError(
                    f"experiment_id {experiment_id!r} does not match journal context"
                )
        if self.session_id is not None and session_id is not None:
            if session_id != self.session_id:
                raise ContextMismatchError(
                    f"session_id {session_id!r} does not match journal context"
                )
        resolved_experiment = (
            experiment_id if experiment_id is not None else self.experiment_id
        )
        resolved_session = session_id if session_id is not None else self.session_id
        if resolved_experiment is None or resolved_session is None:
            raise ContextMismatchError(
                "experiment_id and session_id are required for journal operations"
            )
        return (
            _validate_text(resolved_experiment, "experiment_id"),
            _validate_text(resolved_session, "session_id"),
        )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._connection is None:
                raise JournalError("journal is closed")
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    def _key(
        experiment_id: str,
        session_id: str,
        request_id: str,
    ) -> tuple[str, str, str]:
        return experiment_id, session_id, _validate_text(request_id, "request_id")

    def _fetch_row(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        session_id: str,
        request_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM diplomacy_evidence e
                    WHERE e.experiment_id = r.experiment_id
                      AND e.session_id = r.session_id
                      AND e.request_id = r.request_id) AS evidence_count,
                   (SELECT e.evidence_type FROM diplomacy_evidence e
                    WHERE e.experiment_id = r.experiment_id
                      AND e.session_id = r.session_id
                      AND e.request_id = r.request_id
                    ORDER BY e.evidence_id DESC LIMIT 1) AS last_evidence_type,
                   (SELECT e.arrival_layer FROM diplomacy_evidence e
                    WHERE e.experiment_id = r.experiment_id
                      AND e.session_id = r.session_id
                      AND e.request_id = r.request_id
                    ORDER BY e.evidence_id DESC LIMIT 1) AS last_evidence_layer,
                   (SELECT e.content_sha256 FROM diplomacy_evidence e
                    WHERE e.experiment_id = r.experiment_id
                      AND e.session_id = r.session_id
                      AND e.request_id = r.request_id
                    ORDER BY e.evidence_id DESC LIMIT 1) AS last_evidence_sha256
              FROM diplomacy_requests r
             WHERE r.experiment_id = ? AND r.session_id = ? AND r.request_id = ?
            """,
            (experiment_id, session_id, request_id),
        ).fetchone()

    @staticmethod
    def _record(row: sqlite3.Row) -> RequestRecord:
        payload_json = str(row["payload_json"])
        result_json = row["result_json"]
        return RequestRecord(
            experiment_id=str(row["experiment_id"]),
            request_id=str(row["request_id"]),
            session_id=str(row["session_id"]),
            payload=json.loads(payload_json),
            payload_json=payload_json,
            payload_sha256=str(row["payload_sha256"]),
            status=str(row["status"]),
            result=json.loads(result_json) if result_json is not None else None,
            result_json=str(result_json) if result_json is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            submission_id=row["submission_id"],
            submission_token=row["submission_token"],
            claimed_at=row["claimed_at"],
            submitted_at=row["submitted_at"],
            native_receipt=(
                json.loads(str(row["native_receipt_json"]))
                if row["native_receipt_json"] is not None
                else None
            ),
            native_receipt_json=(
                str(row["native_receipt_json"])
                if row["native_receipt_json"] is not None
                else None
            ),
            evidence_count=int(row["evidence_count"] or 0),
            last_evidence_type=row["last_evidence_type"],
            last_evidence_layer=row["last_evidence_layer"],
            last_evidence_sha256=row["last_evidence_sha256"],
        )

    def _require_row(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        session_id: str,
        request_id: str,
    ) -> sqlite3.Row:
        row = self._fetch_row(connection, experiment_id, session_id, request_id)
        if row is None:
            raise UnknownRequestError(
                f"request {request_id!r} is not registered in experiment/session "
                f"{experiment_id!r}/{session_id!r}"
            )
        return row

    def register(
        self,
        request_id: str,
        payload: Any,
        *,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Register a request, or return the existing identical registration.

        Registration is idempotent for the same scoped id and canonical
        payload.  Reusing the id with a different payload raises
        ``RequestConflictError``.
        """

        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        payload_json = _canonical_json(payload)
        fingerprint = _payload_fingerprint(payload_json)
        now = _utc_now()
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT * FROM diplomacy_requests
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                """,
                (experiment, session, request),
            ).fetchone()
            if existing is not None:
                if existing["payload_sha256"] != fingerprint:
                    raise RequestConflictError(
                        f"request {request!r} already has payload fingerprint "
                        f"{existing['payload_sha256']}; got {fingerprint}"
                    )
                return self._record(self._require_row(connection, experiment, session, request))
            if self.global_request_ids:
                historical = connection.execute(
                    """
                    SELECT experiment_id, session_id, payload_sha256
                      FROM diplomacy_requests
                     WHERE request_id = ?
                     ORDER BY created_at, experiment_id, session_id
                    """,
                    (request,),
                ).fetchall()
                if historical:
                    first = historical[0]
                    raise ContextMismatchError(
                        "GLOBAL_REQUEST_ID_CONTEXT_CONFLICT: request_id "
                        f"{request!r} already belongs to experiment/session "
                        f"{first['experiment_id']!r}/{first['session_id']!r}"
                    )
            connection.execute(
                """
                INSERT INTO diplomacy_requests (
                    experiment_id, session_id, request_id, payload_json,
                    payload_sha256, status, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'received', NULL, ?, ?)
                """,
                (experiment, session, request, payload_json, fingerprint, now, now),
            )
            return self._record(self._require_row(connection, experiment, session, request))

    # Common spelling used by callers that treat registration as receipt.
    receive = register
    register_request = register

    def get_request(
        self,
        request_id: str,
        *,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        with self._lock:
            if self._connection is None:
                raise JournalError("journal is closed")
            return self._record(self._require_row(self._connection, experiment, session, request))

    get = get_request
    get_result = get_request

    def lookup_request(self, request_id: str) -> RequestRecord:
        """Resolve a request id across all experiment/session namespaces.

        This is intentionally read-only and does not use the journal's fixed
        context.  A legacy database may contain the same id in more than one
        namespace; silently choosing one would make result lookup unsafe, so
        that case raises ``AmbiguousRequestError``.
        """

        request = _validate_text(request_id, "request_id")
        with self._lock:
            if self._connection is None:
                raise JournalError("journal is closed")
            rows = self._connection.execute(
                """
                SELECT experiment_id, session_id
                  FROM diplomacy_requests
                 WHERE request_id = ?
                 ORDER BY created_at, experiment_id, session_id
                """,
                (request,),
            ).fetchall()
            if not rows:
                raise UnknownRequestError(f"REQUEST_ID_NOT_FOUND: {request!r}")
            if len(rows) > 1:
                contexts = ", ".join(
                    f"{row['experiment_id']!r}/{row['session_id']!r}" for row in rows
                )
                raise AmbiguousRequestError(
                    f"AMBIGUOUS_REQUEST_ID: {request!r} exists in {contexts}"
                )
            experiment = str(rows[0]["experiment_id"])
            session = str(rows[0]["session_id"])
            return self._record(self._require_row(self._connection, experiment, session, request))

    def list_evidence_for_record(self, record: RequestRecord) -> list[EvidenceRecord]:
        """Read all evidence for a historical record without changing context."""

        if not isinstance(record, RequestRecord):
            raise JournalError("record must be a RequestRecord returned by this journal")
        with self._lock:
            if self._connection is None:
                raise JournalError("journal is closed")
            self._require_row(
                self._connection,
                record.experiment_id,
                record.session_id,
                record.request_id,
            )
            rows = self._connection.execute(
                """
                SELECT * FROM diplomacy_evidence
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                 ORDER BY evidence_id
                """,
                (record.experiment_id, record.session_id, record.request_id),
            ).fetchall()
            return [self._evidence_from_row(row) for row in rows]

    def list_requests(
        self,
        *,
        experiment_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[RequestRecord]:
        experiment, session = self._context(experiment_id, session_id)
        if status is not None and status not in REQUEST_STATES:
            raise JournalError(f"unknown request status {status!r}")
        with self._lock:
            if self._connection is None:
                raise JournalError("journal is closed")
            query = (
                "SELECT r.* FROM diplomacy_requests r "
                "WHERE r.experiment_id = ? AND r.session_id = ?"
            )
            params: list[Any] = [experiment, session]
            if status is not None:
                query += " AND r.status = ?"
                params.append(status)
            query += " ORDER BY r.created_at, r.request_id"
            rows = self._connection.execute(query, params).fetchall()
            return [
                self._record(self._require_row(self._connection, experiment, session, row["request_id"]))
                for row in rows
            ]

    def _normalize_evidence(
        self,
        request_id: str,
        evidence_type: str,
        content: Any,
        arrival_layer: str | None,
        layer: str | None,
        event_id: str | None,
        observed_at: str | None,
    ) -> dict[str, Any]:
        if arrival_layer is not None and layer is not None and arrival_layer != layer:
            raise JournalError("arrival_layer and layer must match when both are supplied")
        resolved_layer = arrival_layer or layer
        if resolved_layer is None:
            raise JournalError("arrival_layer is required for evidence")
        content_value = _content(content)
        if event_id is None:
            # Replayed events without a transport event id should still be
            # idempotent.  Distinct occurrences must provide their own event
            # id when they carry identical content.
            result_event_id = "auto_" + _sha256(
                (
                    str(resolved_layer).encode("utf-8")
                    + b"\0"
                    + str(evidence_type).encode("utf-8")
                    + b"\0"
                    + content_value[2].encode("ascii")
                )
            )
        else:
            result_event_id = event_id
        return {
            "request_id": _validate_text(request_id, "request_id"),
            "evidence_type": _validate_text(evidence_type, "evidence_type"),
            "arrival_layer": _validate_text(resolved_layer, "arrival_layer"),
            "event_id": _validate_text(result_event_id, "event_id"),
            "content": content_value,
            "observed_at": observed_at or _utc_now(),
        }

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=int(row["evidence_id"]),
            event_id=str(row["event_id"]),
            experiment_id=str(row["experiment_id"]),
            request_id=str(row["request_id"]),
            session_id=str(row["session_id"]),
            arrival_layer=str(row["arrival_layer"]),
            evidence_type=str(row["evidence_type"]),
            content=_decode_content(str(row["content_text"]), str(row["content_format"])),
            content_format=str(row["content_format"]),
            content_sha256=str(row["content_sha256"]),
            observed_at=str(row["observed_at"]),
            recorded_at=str(row["recorded_at"]),
        )

    def _insert_evidence(
        self,
        connection: sqlite3.Connection,
        experiment: str,
        session: str,
        evidence: Mapping[str, Any],
    ) -> EvidenceRecord:
        request = evidence["request_id"]
        self._require_row(connection, experiment, session, request)
        content_text, content_format, content_sha = evidence["content"]
        existing = connection.execute(
            """
            SELECT * FROM diplomacy_evidence
             WHERE experiment_id = ? AND session_id = ?
               AND request_id = ? AND event_id = ?
            """,
            (experiment, session, request, evidence["event_id"]),
        ).fetchone()
        if existing is not None:
            if (
                existing["arrival_layer"] != evidence["arrival_layer"]
                or existing["evidence_type"] != evidence["evidence_type"]
                or existing["content_sha256"] != content_sha
            ):
                raise EvidenceConflictError(
                    f"event {evidence['event_id']!r} was reused with different evidence"
                )
            return self._evidence_from_row(existing)
        recorded_at = _utc_now()
        connection.execute(
            """
            INSERT INTO diplomacy_evidence (
                experiment_id, session_id, request_id, event_id,
                arrival_layer, evidence_type, content_text, content_format,
                content_sha256, observed_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment,
                session,
                request,
                evidence["event_id"],
                evidence["arrival_layer"],
                evidence["evidence_type"],
                content_text,
                content_format,
                content_sha,
                evidence["observed_at"],
                recorded_at,
            ),
        )
        # Evidence arrival is itself an update to the request record.  It does
        # not imply a state transition.
        connection.execute(
            """
            UPDATE diplomacy_requests SET updated_at = ?
             WHERE experiment_id = ? AND session_id = ? AND request_id = ?
            """,
            (recorded_at, experiment, session, request),
        )
        row = connection.execute(
            """
            SELECT * FROM diplomacy_evidence
             WHERE experiment_id = ? AND session_id = ?
               AND request_id = ? AND event_id = ?
            """,
            (experiment, session, request, evidence["event_id"]),
        ).fetchone()
        assert row is not None
        return self._evidence_from_row(row)

    def record_evidence(
        self,
        request_id: str,
        evidence_type: str,
        content: Any = None,
        *,
        arrival_layer: str | None = None,
        layer: str | None = None,
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> EvidenceRecord:
        """Persist one evidence event without inferring a business result."""

        experiment, session = self._context(experiment_id, session_id)
        evidence = self._normalize_evidence(
            request_id,
            evidence_type,
            content,
            arrival_layer,
            layer,
            event_id,
            observed_at,
        )
        with self._transaction() as connection:
            return self._insert_evidence(connection, experiment, session, evidence)

    append_evidence = record_evidence

    def record_event(self, event: Mapping[str, Any]) -> EvidenceRecord:
        """Record a structured event and enforce all three scope identifiers.

        Accepted aliases are ``type``/``evidence_type`` and
        ``layer``/``arrival_layer``.  If the journal has a fixed context, any
        identifiers in the event must match it exactly.
        """

        if not isinstance(event, Mapping):
            raise JournalError("event must be a mapping")
        request_id = event.get("request_id")
        experiment_id = event.get("experiment_id")
        session_id = event.get("session_id")
        if request_id is None or experiment_id is None or session_id is None:
            raise ContextMismatchError(
                "evidence event must contain experiment_id, request_id, and session_id"
            )
        evidence_type = event.get("evidence_type", event.get("type"))
        arrival_layer = event.get("arrival_layer", event.get("layer"))
        if evidence_type is None or arrival_layer is None:
            raise JournalError("evidence event requires evidence_type and arrival_layer")
        return self.record_evidence(
            str(request_id),
            str(evidence_type),
            event.get("content"),
            arrival_layer=str(arrival_layer),
            event_id=str(event["event_id"]) if event.get("event_id") is not None else None,
            observed_at=str(event["observed_at"]) if event.get("observed_at") is not None else None,
            experiment_id=str(experiment_id),
            session_id=str(session_id),
        )

    def list_evidence(
        self,
        request_id: str,
        *,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> list[EvidenceRecord]:
        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        with self._lock:
            if self._connection is None:
                raise JournalError("journal is closed")
            self._require_row(self._connection, experiment, session, request)
            rows = self._connection.execute(
                """
                SELECT * FROM diplomacy_evidence
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                 ORDER BY evidence_id
                """,
                (experiment, session, request),
            ).fetchall()
            return [self._evidence_from_row(row) for row in rows]

    evidence_for = list_evidence

    def _apply_result_json(
        self,
        connection: sqlite3.Connection,
        experiment: str,
        session: str,
        request: str,
        result: Any,
        now: str,
    ) -> None:
        connection.execute(
            """
            UPDATE diplomacy_requests SET result_json = ?, updated_at = ?
             WHERE experiment_id = ? AND session_id = ? AND request_id = ?
            """,
            (_canonical_json(result), now, experiment, session, request),
        )

    def record_result(
        self,
        request_id: str,
        result: Any,
        *,
        evidence_type: str | None = None,
        evidence_content: Any = _MISSING,
        arrival_layer: str | None = None,
        layer: str | None = None,
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Store a result and optionally an evidence event atomically."""

        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        evidence: dict[str, Any] | None = None
        if evidence_type is not None:
            evidence = self._normalize_evidence(
                request,
                evidence_type,
                result if evidence_content is _MISSING else evidence_content,
                arrival_layer,
                layer,
                event_id,
                observed_at,
            )
        elif evidence_content is not _MISSING:
            raise JournalError("evidence_content requires evidence_type")
        now = _utc_now()
        with self._transaction() as connection:
            self._require_row(connection, experiment, session, request)
            self._apply_result_json(connection, experiment, session, request, result, now)
            if evidence is not None:
                self._insert_evidence(connection, experiment, session, evidence)
            return self._record(self._require_row(connection, experiment, session, request))

    set_result = record_result

    def transition(
        self,
        request_id: str,
        status: str,
        *,
        result: Any = _MISSING,
        reason: str | None = None,
        evidence_type: str | None = None,
        evidence_content: Any = _MISSING,
        arrival_layer: str | None = None,
        layer: str | None = None,
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Apply one checked state transition.

        ``submitted`` is reserved for ``mark_submitted``; ``executed`` is
        reserved for ``mark_executed``; and ``accepted`` is reserved for
        ``mark_accepted``.  These restrictions prevent a claim, queue, entry,
        or intermediate native callback from being mistaken for a real result.
        """

        if status not in REQUEST_STATES:
            raise InvalidTransitionError(f"unknown request status {status!r}")
        if status == "submitted":
            raise SubmissionClaimRequired("use mark_submitted after native delivery")
        if status == "accepted":
            raise AcceptanceEvidenceRequired("use mark_accepted with consequence evidence")
        if status == "executed":
            raise ExecutionEvidenceRequired(
                "use mark_executed with submission and consequence evidence"
            )
        if status == "rejected":
            if _looks_like_timeout(reason) or _looks_like_timeout(evidence_type):
                raise InvalidTransitionError(
                    "a timeout is not a business rejection; use mark_expired or mark_unknown"
                )
            if evidence_type is None:
                raise InvalidTransitionError(
                    "a business rejection requires an explicit native response evidence event"
                )
            if arrival_layer is None and layer is None:
                raise InvalidTransitionError(
                    "a business rejection requires native response arrival_layer"
                )
        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        evidence: dict[str, Any] | None = None
        if evidence_type is not None:
            evidence = self._normalize_evidence(
                request,
                evidence_type,
                reason if evidence_content is _MISSING else evidence_content,
                arrival_layer,
                layer,
                event_id,
                observed_at,
            )
        elif evidence_content is not _MISSING:
            raise JournalError("evidence_content requires evidence_type")
        if result is not _MISSING:
            result_json = _canonical_json(result)
        else:
            result_json = None
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            current = str(row["status"])
            if status == "rejected" and (
                row["submitted_at"] is None or row["native_receipt_json"] is None
            ):
                raise InvalidTransitionError(
                    "a business rejection requires recorded native submission evidence"
                )
            if current == status:
                if evidence is not None:
                    self._insert_evidence(connection, experiment, session, evidence)
                if result is not _MISSING:
                    self._apply_result_json(
                        connection, experiment, session, request, result, _utc_now()
                    )
                return self._record(self._require_row(connection, experiment, session, request))
            if status not in _TRANSITIONS[current]:
                raise InvalidTransitionError(f"cannot transition {current!r} to {status!r}")
            now = _utc_now()
            connection.execute(
                """
                UPDATE diplomacy_requests
                   SET status = ?, result_json = COALESCE(?, result_json), updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                """,
                (status, result_json, now, experiment, session, request),
            )
            if evidence is not None:
                self._insert_evidence(connection, experiment, session, evidence)
            return self._record(self._require_row(connection, experiment, session, request))

    advance = transition

    def claim_submission(
        self,
        request_id: str,
        *,
        submission_id: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> SubmissionClaim:
        """Atomically reserve the single native submission for a request.

        The first caller that sees ``constructed`` records a claim while
        leaving the request in ``constructed``.  A separate
        ``mark_submitted`` call must record the native transport receipt before
        the request can enter ``submitted``.  Concurrent or repeated callers
        receive the same durable claim with ``claimed=False`` and must not call
        the native submitter again.  A claim also reserves the one native
        submission channel for this experiment/session until its request is
        terminal or explicitly reconciled.
        """

        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        requested_submission_id = (
            _validate_text(submission_id, "submission_id")
            if submission_id is not None
            else uuid.uuid4().hex
        )
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            if row["submission_id"] is not None:
                return SubmissionClaim(
                    experiment,
                    request,
                    session,
                    False,
                    row["submission_id"],
                    row["submission_token"],
                    str(row["status"]),
                    row["claimed_at"],
                )
            if row["status"] != "constructed":
                return SubmissionClaim(
                    experiment,
                    request,
                    session,
                    False,
                    None,
                    None,
                    str(row["status"]),
                    None,
                )
            # The claim itself is the channel mutex.  A request in unknown is
            # intentionally still active: it may not be retried merely because
            # the process was restarted or a transport timeout elapsed.
            active = connection.execute(
                """
                SELECT request_id
                  FROM diplomacy_requests
                 WHERE experiment_id = ? AND session_id = ?
                   AND request_id <> ?
                   AND submission_id IS NOT NULL
                   AND status NOT IN ('executed', 'accepted', 'rejected', 'cancelled',
                                      'expired', 'invalidated')
                 ORDER BY claimed_at, request_id
                 LIMIT 1
                """,
                (experiment, session, request),
            ).fetchone()
            if active is not None:
                return SubmissionClaim(
                    experiment,
                    request,
                    session,
                    False,
                    None,
                    None,
                    str(row["status"]),
                    None,
                    str(active["request_id"]),
                )
            now = _utc_now()
            token = uuid.uuid4().hex
            updated = connection.execute(
                """
                UPDATE diplomacy_requests
                   SET submission_id = ?, submission_token = ?,
                       claimed_at = ?, updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                   AND status = 'constructed' AND submission_id IS NULL
                """,
                (
                    requested_submission_id,
                    token,
                    now,
                    now,
                    experiment,
                    session,
                    request,
                ),
            )
            if updated.rowcount == 1:
                return SubmissionClaim(
                    experiment,
                    request,
                    session,
                    True,
                    requested_submission_id,
                    token,
                    "constructed",
                    now,
                )
            row = self._require_row(connection, experiment, session, request)
            return SubmissionClaim(
                experiment,
                request,
                session,
                False,
                row["submission_id"],
                row["submission_token"],
                str(row["status"]),
                row["claimed_at"],
            )

    claim = claim_submission

    def mark_submitted(
        self,
        request_id: str,
        claim_token: str,
        native_receipt: Any,
        *,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Record actual native delivery and move a claimed request to submitted.

        ``claim_submission`` alone is never delivery evidence.  The receipt is
        persisted as both request metadata and an evidence event so a restart
        can distinguish a claimed-but-never-submitted request from one that
        reached the native transport.
        """

        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        token = _validate_text(claim_token, "claim_token")
        receipt_json = _canonical_json(native_receipt)
        evidence = self._normalize_evidence(
            request,
            "native_submission",
            native_receipt,
            "native_submit",
            None,
            "native_submission:" + token,
            None,
        )
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            if row["submission_token"] != token:
                raise InvalidTransitionError("claim token does not belong to this request")
            if row["status"] == "submitted":
                if row["native_receipt_json"] != receipt_json:
                    raise EvidenceConflictError("native receipt differs from the recorded receipt")
                return self._record(row)
            if row["status"] != "constructed":
                raise InvalidTransitionError(
                    f"cannot mark {row['status']!r} request as submitted"
                )
            now = _utc_now()
            connection.execute(
                """
                UPDATE diplomacy_requests
                   SET status = 'submitted', native_receipt_json = ?,
                       submitted_at = ?, updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                   AND status = 'constructed' AND submission_token = ?
                """,
                (
                    receipt_json,
                    now,
                    now,
                    experiment,
                    session,
                    request,
                    token,
                ),
            )
            self._insert_evidence(connection, experiment, session, evidence)
            return self._record(self._require_row(connection, experiment, session, request))

    def mark_executed(
        self,
        request_id: str,
        consequence: Any,
        *,
        evidence_type: str = "native_consequence",
        arrival_layer: str = "native_consequence",
        event_id: str | None = None,
        observed_at: str | None = None,
        result: Any = _MISSING,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Mark a request executed only after submitted consequence evidence.

        ``executed`` records completion of the requested native operation.  It
        is deliberately separate from ``accepted``: a request can have been
        executed while the business-level acceptance remains a different
        result.  Repeating this method after the terminal state is reached is
        an idempotent read and does not emit another submission or evidence
        event.
        """

        evidence_words = _word_set(evidence_type)
        if arrival_layer not in _CONSEQUENCE_LAYERS:
            raise ExecutionEvidenceRequired(
                "executed requires consequence arrival_layer, not a native acceptance entry"
            )
        if evidence_words & _ENTRY_ONLY_WORDS and not evidence_words & {
            "consequence",
            "postcondition",
            "game",
            "state",
            "result",
            "save",
            "reload",
        }:
            raise ExecutionEvidenceRequired(
                "native acceptance/queue evidence is not an actual consequence"
            )
        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        evidence = self._normalize_evidence(
            request,
            evidence_type,
            consequence,
            arrival_layer,
            None,
            event_id,
            observed_at,
        )
        stored_result = consequence if result is _MISSING else result
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            current = str(row["status"])
            if row["submitted_at"] is None or row["native_receipt_json"] is None:
                raise ExecutionEvidenceRequired(
                    "executed requires submitted_at and native submission evidence"
                )
            if current == "executed":
                return self._record(row)
            if "executed" not in _TRANSITIONS[current]:
                raise InvalidTransitionError(
                    f"cannot transition {current!r} to 'executed'"
                )
            self._insert_evidence(connection, experiment, session, evidence)
            now = _utc_now()
            connection.execute(
                """
                UPDATE diplomacy_requests
                   SET status = 'executed', result_json = ?, updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                """,
                (_canonical_json(stored_result), now, experiment, session, request),
            )
            return self._record(self._require_row(connection, experiment, session, request))

    def reconcile_executed(
        self,
        request_id: str,
        result: Any,
        native_receipt: Any,
        *,
        expected_reason_code: str,
        expected_payload: Any,
        evidence_type: str = "native_rival_reconciliation",
        evidence_content: Any = _MISSING,
        arrival_layer: str = "actual_result",
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Repair one invalidated Rival request from verified native evidence.

        This path is intentionally narrower than :meth:`transition`: it only
        resolves the exact consumer-side submission-validation failure after a
        later, independently validated Rival submission receipt and execution
        result.  It never publishes a request and never opens a general
        terminal-state transition.  The prior invalidation remains in the
        evidence table; the new evidence records both verified native facts.
        """

        if (not isinstance(result, Mapping)
                or result.get("event") != "native_rival_execution_result"
                or result.get("family") != "rival"
                or result.get("status") != "executed"
                or result.get("native_outcome") != "executed"
                or result.get("executed") is not True
                or result.get("request_binding_verified") is not True
                or result.get("native_rule_verified") is not True
                or result.get("relationship_verified") is not True
                or not isinstance(native_receipt, Mapping)
                or native_receipt.get("event") != "native_rival_submission_result"
                or native_receipt.get("family") != "rival"
                or native_receipt.get("submitted") is not True
                or native_receipt.get("request_binding_verified") is not True
                or native_receipt.get("protocol_verified") is not True):
            raise InvalidTransitionError(
                "reconciliation evidence is not a verified Rival execution"
            )
        if (not isinstance(expected_reason_code, str)
                or expected_reason_code != "NATIVE_RIVAL_SUBMISSION_RESULT_INVALID"
                or not isinstance(expected_payload, Mapping)):
            raise InvalidTransitionError(
                "Rival reconciliation requires the recorded submission validation error"
            )
        payload_json = _canonical_json(expected_payload)
        receipt_json = _canonical_json(native_receipt)
        result_json = _canonical_json(result)
        request = _validate_text(request_id, "request_id")
        if (result.get("request_id") != request
                or native_receipt.get("request_id") != request
                or result.get("action_id") != expected_payload.get("action_id")
                or result.get("actor") != expected_payload.get("actor")
                or result.get("recipient") != expected_payload.get("recipient")
                or result.get("phase") != expected_payload.get("phase")
                or native_receipt.get("action_id") != expected_payload.get("action_id")
                or native_receipt.get("actor") != expected_payload.get("actor")
                or native_receipt.get("recipient") != expected_payload.get("recipient")
                or native_receipt.get("phase") != expected_payload.get("phase")):
            raise InvalidTransitionError(
                "Rival reconciliation evidence is not bound to the durable payload"
            )
        if evidence_content is _MISSING:
            evidence_content = {
                "reconciled_from": "invalidated",
                "original_reason_code": expected_reason_code,
                "native_receipt": dict(native_receipt),
                "native_response": dict(result),
            }
        evidence = self._normalize_evidence(
            request,
            evidence_type,
            evidence_content,
            arrival_layer,
            None,
            event_id,
            observed_at,
        )
        experiment, session = self._context(experiment_id, session_id)
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            if row["payload_json"] != payload_json:
                raise InvalidTransitionError(
                    "Rival reconciliation payload does not match the durable request"
                )
            previous = (
                json.loads(str(row["result_json"]))
                if row["result_json"] is not None else None
            )
            current = str(row["status"])
            if current == "executed":
                if (row["native_receipt_json"] != receipt_json
                        or row["result_json"] != result_json):
                    raise EvidenceConflictError(
                        "Rival reconciliation differs from the recorded execution"
                    )
                return self._record(row)
            previous_reason = None
            if isinstance(previous, Mapping):
                previous_reason_value = previous.get("reason")
                if isinstance(previous_reason_value, Mapping):
                    previous_reason = previous_reason_value.get("code")
            if (previous_reason != expected_reason_code
                    or not isinstance(previous, Mapping)
                    or previous.get("submitted") is not False):
                raise InvalidTransitionError(
                    "Rival reconciliation is restricted to the recorded invalid submission"
                )
            if current != "invalidated":
                raise InvalidTransitionError(
                    f"cannot reconcile {current!r} request as executed"
                )
            if row["submission_id"] is None:
                raise InvalidTransitionError(
                    "Rival reconciliation requires the original submission claim"
                )
            now = _utc_now()
            self._insert_evidence(connection, experiment, session, evidence)
            connection.execute(
                """
                UPDATE diplomacy_requests
                   SET status = 'executed', result_json = ?,
                       native_receipt_json = ?,
                       submitted_at = COALESCE(submitted_at, ?),
                       updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                   AND status = 'invalidated'
                """,
                (
                    result_json, receipt_json, now, now,
                    experiment, session, request,
                ),
            )
            return self._record(self._require_row(connection, experiment, session, request))

    def reconcile_declare_war_executed(
        self,
        request_id: str,
        result: Any,
        native_receipt: Any,
        *,
        expected_reason_code: str,
        expected_payload: Any,
        evidence_type: str = "native_declare_war_reconciliation",
        evidence_content: Any = _MISSING,
        arrival_layer: str = "actual_result",
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Repair one Declare War receipt-projection failure from native evidence.

        The method is intentionally narrower than :meth:`transition`: it only
        resolves the known bridge failure where a valid raw submission receipt
        was projected twice and the request was consequently invalidated.  It
        accepts a fully reduced Declare War receipt and a fully bound executed
        consequence.  It never publishes a request or reopens a general
        terminal-state transition; the original invalidation remains in the
        evidence table.
        """

        if (not isinstance(result, Mapping)
                or result.get("event") != "native_declare_war_execution_result"
                or result.get("family") != "declare_war"
                or result.get("outcome") != "executed"
                or result.get("native_outcome") != "executed"
                or result.get("execution_verified") is not True
                or result.get("request_binding_verified") is not True
                or result.get("war_before") is not False
                or result.get("war_after") is not True
                or not isinstance(native_receipt, Mapping)
                or native_receipt.get("event") != "native_declare_war_submission_result"
                or native_receipt.get("family") != "declare_war"
                or native_receipt.get("submitted") is not True
                or native_receipt.get("transport_verified") is not True
                or native_receipt.get("request_binding_verified") is not True):
            raise InvalidTransitionError(
                "reconciliation evidence is not a verified Declare War execution"
            )
        if (not isinstance(expected_reason_code, str)
                or expected_reason_code != "NATIVE_DECLARE_WAR_SUBMISSION_RECEIPT_INVALID"
                or not isinstance(expected_payload, Mapping)):
            raise InvalidTransitionError(
                "Declare War reconciliation requires the recorded receipt validation error"
            )

        payload_action = expected_payload.get("action_id")
        payload_actor = expected_payload.get("actor")
        payload_recipient = expected_payload.get("recipient")
        payload_phase = expected_payload.get("phase")
        payload_parameters = expected_payload.get("parameters")
        payload_war_goal = (
            payload_parameters.get("war_goal")
            if isinstance(payload_parameters, Mapping) else None
        )
        if (payload_action != "declare_war" or payload_actor != "FRA"
                or not isinstance(payload_recipient, str)
                or not re.fullmatch(r"[A-Z]{3}", payload_recipient)
                or payload_recipient == "FRA"
                or payload_phase != "initiate"
                or not isinstance(payload_parameters, Mapping)
                or not isinstance(payload_war_goal, Mapping)):
            raise InvalidTransitionError(
                "Declare War reconciliation payload is outside the supported scope"
            )
        request = _validate_text(request_id, "request_id")
        expected = dict(expected_payload)
        payload_json = _canonical_json(expected)
        receipt_json = _canonical_json(dict(native_receipt))
        result_json = _canonical_json(dict(result))

        def same(field: str, value: Any) -> bool:
            return (result.get(field) == value
                    and native_receipt.get(field) == value)

        if (result.get("request_id") != request
                or native_receipt.get("request_id") != request
                or not same("action_id", "declare_war")
                or not same("actor", "FRA")
                or not same("recipient", payload_recipient)
                or not same("phase", "initiate")
                or result.get("casus_belli") != payload_parameters.get("casus_belli")
                or native_receipt.get("casus_belli") != payload_parameters.get("casus_belli")
                or result.get("war_goal_province") != payload_war_goal.get("province_id")
                or native_receipt.get("war_goal_province") != payload_war_goal.get("province_id")
                or result.get("war_goal_beneficiary") != payload_war_goal.get("beneficiary")
                or native_receipt.get("war_goal_beneficiary") != payload_war_goal.get("beneficiary")
                or result.get("date_raw") != native_receipt.get("date_raw")):
            raise InvalidTransitionError(
                "Declare War reconciliation evidence is not bound to the durable payload"
            )

        for field in ("war_identity_verified", "stability_verified"):
            if not isinstance(result.get(field), bool):
                raise InvalidTransitionError(
                    "Declare War reconciliation is missing verification flags"
                )
        int32_fields = ("war_id", "stability_before_raw", "stability_after_raw")
        for field in int32_fields:
            value = result.get(field)
            if value is not None and (
                    isinstance(value, bool) or not isinstance(value, int)
                    or value < -2147483648 or value > 2147483647):
                raise InvalidTransitionError(
                    "Declare War reconciliation contains an invalid optional integer"
                )
        if ((result["war_identity_verified"] is True) != (result.get("war_id") is not None)
                or (result["stability_verified"] is True)
                != (result.get("stability_before_raw") is not None
                    and result.get("stability_after_raw") is not None)):
            raise InvalidTransitionError(
                "Declare War reconciliation optional fields disagree with verification flags"
            )

        if evidence_content is _MISSING:
            evidence_content = {
                "reconciled_from": "invalidated",
                "original_reason_code": expected_reason_code,
                "native_receipt": dict(native_receipt),
                "native_response": dict(result),
            }
        evidence = self._normalize_evidence(
            request,
            evidence_type,
            evidence_content,
            arrival_layer,
            None,
            event_id,
            observed_at,
        )
        experiment, session = self._context(experiment_id, session_id)
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            if row["payload_json"] != payload_json:
                raise InvalidTransitionError(
                    "Declare War reconciliation payload does not match the durable request"
                )
            previous = (
                json.loads(str(row["result_json"]))
                if row["result_json"] is not None else None
            )
            current = str(row["status"])
            if current == "executed":
                if (row["native_receipt_json"] != receipt_json
                        or row["result_json"] != result_json):
                    raise EvidenceConflictError(
                        "Declare War reconciliation differs from the recorded execution"
                    )
                return self._record(row)
            previous_reason = None
            if isinstance(previous, Mapping):
                previous_reason_value = previous.get("reason")
                if isinstance(previous_reason_value, Mapping):
                    previous_reason = previous_reason_value.get("code")
            if (previous_reason != expected_reason_code
                    or not isinstance(previous, Mapping)
                    or previous.get("submitted") is not False):
                raise InvalidTransitionError(
                    "Declare War reconciliation is restricted to the recorded invalid submission"
                )
            if current != "invalidated":
                raise InvalidTransitionError(
                    f"cannot reconcile {current!r} request as executed"
                )
            if row["submission_id"] is None:
                raise InvalidTransitionError(
                    "Declare War reconciliation requires the original submission claim"
                )
            now = _utc_now()
            self._insert_evidence(connection, experiment, session, evidence)
            connection.execute(
                """
                UPDATE diplomacy_requests
                   SET status = 'executed', result_json = ?,
                       native_receipt_json = ?,
                       submitted_at = COALESCE(submitted_at, ?),
                       updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                   AND status = 'invalidated'
                """,
                (
                    result_json, receipt_json, now, now,
                    experiment, session, request,
                ),
            )
            return self._record(self._require_row(connection, experiment, session, request))

    def mark_accepted(
        self,
        request_id: str,
        consequence: Any,
        *,
        evidence_type: str = "native_consequence",
        arrival_layer: str = "native_consequence",
        event_id: str | None = None,
        observed_at: str | None = None,
        result: Any = _MISSING,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Mark a request accepted only with actual post-submit consequence evidence."""

        evidence_words = _word_set(evidence_type)
        if arrival_layer not in _CONSEQUENCE_LAYERS:
            raise AcceptanceEvidenceRequired(
                "accepted requires consequence arrival_layer, not a native acceptance entry"
            )
        if evidence_words & _ENTRY_ONLY_WORDS and not evidence_words & {
            "consequence",
            "postcondition",
            "game",
            "state",
            "result",
            "save",
            "reload",
        }:
            raise AcceptanceEvidenceRequired(
                "native acceptance/queue evidence is not an actual consequence"
            )
        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        evidence = self._normalize_evidence(
            request,
            evidence_type,
            consequence,
            arrival_layer,
            None,
            event_id,
            observed_at,
        )
        stored_result = consequence if result is _MISSING else result
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            current = str(row["status"])
            if row["submitted_at"] is None or row["native_receipt_json"] is None:
                raise AcceptanceEvidenceRequired(
                    "accepted requires submitted_at and native submission evidence"
                )
            if current != "accepted" and "accepted" not in _TRANSITIONS[current]:
                raise InvalidTransitionError(f"cannot transition {current!r} to 'accepted'")
            self._insert_evidence(connection, experiment, session, evidence)
            now = _utc_now()
            connection.execute(
                """
                UPDATE diplomacy_requests
                   SET status = 'accepted', result_json = ?, updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                """,
                (_canonical_json(stored_result), now, experiment, session, request),
            )
            return self._record(self._require_row(connection, experiment, session, request))

    accept = mark_accepted

    def mark_rejected(
        self,
        request_id: str,
        reason: Any = None,
        *,
        evidence_type: str = "native_rejection",
        arrival_layer: str = "native_response",
        event_id: str | None = None,
        observed_at: str | None = None,
        result: Any = _MISSING,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Record an explicit business rejection; timeout is never rejection."""

        if _looks_like_timeout(reason) or _looks_like_timeout(evidence_type):
            raise InvalidTransitionError(
                "a timeout is not a business rejection; use mark_expired or mark_unknown"
            )
        return self.transition(
            request_id,
            "rejected",
            result=(reason if result is _MISSING else result),
            evidence_type=evidence_type,
            evidence_content=reason,
            arrival_layer=arrival_layer,
            event_id=event_id,
            observed_at=observed_at,
            experiment_id=experiment_id,
            session_id=session_id,
        )

    reject = mark_rejected

    def reconcile_rejected(
        self,
        request_id: str,
        result: Any,
        native_receipt: Any,
        *,
        expected_reason_code: str,
        expected_payload: Any,
        evidence_type: str = "native_response_reconciliation",
        evidence_content: Any = _MISSING,
        arrival_layer: str = "native_response_reconcile",
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        """Resolve one invalidated record after a strictly bound native receipt.

        This is deliberately narrower than a normal transition.  It only
        repairs the consumer-side ``NATIVE_SUBMISSION_RESULT_INVALID`` case:
        the original payload and error code must match exactly, the current
        state must be ``invalidated``, and the caller must already have
        validated the native transport and business response.  The old
        invalidation evidence remains in the journal; the reconciliation adds
        one new evidence event and records the verified receipt before moving
        the request to ``rejected``.
        """

        if (not isinstance(expected_reason_code, str)
                or not expected_reason_code
                or not isinstance(expected_payload, Mapping)
                or not isinstance(result, Mapping)
                or result.get("native_outcome") != "rejected"
                or not isinstance(native_receipt, Mapping)):
            raise InvalidTransitionError("reconciliation evidence is not a verified rejection")
        previous_reason = None
        receipt_json = _canonical_json(native_receipt)
        result_json = _canonical_json(result)
        expected_payload_json = _canonical_json(expected_payload)
        if evidence_content is _MISSING:
            evidence_content = {
                "reconciled_from": "invalidated",
                "native_receipt": dict(native_receipt),
                "native_response": dict(result),
                "original_reason_code": expected_reason_code,
            }
        evidence = self._normalize_evidence(
            request_id,
            evidence_type,
            evidence_content,
            arrival_layer,
            None,
            event_id,
            observed_at,
        )
        experiment, session = self._context(experiment_id, session_id)
        request = _validate_text(request_id, "request_id")
        with self._transaction() as connection:
            row = self._require_row(connection, experiment, session, request)
            if row["payload_json"] != expected_payload_json:
                raise InvalidTransitionError(
                    "reconciliation payload does not match the durable request"
                )
            previous = (
                json.loads(str(row["result_json"]))
                if row["result_json"] is not None
                else None
            )
            if isinstance(previous, Mapping):
                previous_reason_value = previous.get("reason")
                if isinstance(previous_reason_value, Mapping):
                    previous_reason = previous_reason_value.get("code")
            if previous_reason != expected_reason_code:
                raise InvalidTransitionError(
                    "reconciliation is restricted to the recorded submission validation error"
                )
            current = str(row["status"])
            if current == "rejected":
                if (row["native_receipt_json"] != receipt_json
                        or row["result_json"] != result_json):
                    raise EvidenceConflictError(
                        "reconciliation differs from the recorded native rejection"
                    )
                return self._record(row)
            if current != "invalidated":
                raise InvalidTransitionError(
                    f"cannot reconcile {current!r} request as rejected"
                )
            now = _utc_now()
            self._insert_evidence(connection, experiment, session, evidence)
            connection.execute(
                """
                UPDATE diplomacy_requests
                   SET status = 'rejected', result_json = ?,
                       native_receipt_json = ?, submitted_at = COALESCE(submitted_at, ?),
                       updated_at = ?
                 WHERE experiment_id = ? AND session_id = ? AND request_id = ?
                   AND status = 'invalidated'
                """,
                (result_json, receipt_json, now, now, experiment, session, request),
            )
            return self._record(self._require_row(connection, experiment, session, request))

    def mark_unknown(
        self,
        request_id: str,
        reason: Any = None,
        *,
        evidence_type: str | None = None,
        arrival_layer: str | None = None,
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        return self.transition(
            request_id,
            "unknown",
            result=reason if reason is not None else _MISSING,
            evidence_type=evidence_type,
            evidence_content=reason if evidence_type is not None else _MISSING,
            arrival_layer=arrival_layer,
            event_id=event_id,
            observed_at=observed_at,
            experiment_id=experiment_id,
            session_id=session_id,
        )

    def mark_expired(
        self,
        request_id: str,
        reason: Any = "deadline elapsed",
        *,
        evidence_type: str = "timeout",
        arrival_layer: str = "bridge_timeout",
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        return self.transition(
            request_id,
            "expired",
            result=reason,
            evidence_type=evidence_type,
            evidence_content=reason,
            arrival_layer=arrival_layer,
            event_id=event_id,
            observed_at=observed_at,
            experiment_id=experiment_id,
            session_id=session_id,
        )

    expire = mark_expired

    def mark_cancelled(
        self,
        request_id: str,
        reason: Any = "cancelled",
        *,
        evidence_type: str = "cancellation",
        arrival_layer: str = "bridge_control",
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        return self.transition(
            request_id,
            "cancelled",
            result=reason,
            evidence_type=evidence_type,
            evidence_content=reason,
            arrival_layer=arrival_layer,
            event_id=event_id,
            observed_at=observed_at,
            experiment_id=experiment_id,
            session_id=session_id,
        )

    cancel = mark_cancelled

    def mark_invalidated(
        self,
        request_id: str,
        reason: Any = "invalidated",
        *,
        evidence_type: str = "invalidation",
        arrival_layer: str = "bridge_validation",
        event_id: str | None = None,
        observed_at: str | None = None,
        experiment_id: str | None = None,
        session_id: str | None = None,
    ) -> RequestRecord:
        return self.transition(
            request_id,
            "invalidated",
            result=reason,
            evidence_type=evidence_type,
            evidence_content=reason,
            arrival_layer=arrival_layer,
            event_id=event_id,
            observed_at=observed_at,
            experiment_id=experiment_id,
            session_id=session_id,
        )

    invalidate = mark_invalidated


__all__ = [
    "AcceptanceEvidenceRequired",
    "AmbiguousRequestError",
    "ContextMismatchError",
    "DurableJournal",
    "EvidenceConflictError",
    "EvidenceRecord",
    "ExecutionEvidenceRequired",
    "InvalidTransitionError",
    "JournalError",
    "REQUEST_STATES",
    "STATUSES",
    "SubmissionClaim",
    "SubmissionClaimRequired",
    "SubmissionBusyError",
    "RequestConflictError",
    "RequestRecord",
    "UnknownRequestError",
    "VALID_STATUSES",
    "VALID_REQUEST_STATES",
]
