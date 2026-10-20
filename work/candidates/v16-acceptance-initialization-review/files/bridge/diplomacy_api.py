"""Version-gated diplomacy contract, durable requests, and backend boundary.

Catalogued or statically identified actions are not executable capabilities.
The shipped API deliberately has no native execution adapter for EU4 1.37.5.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = Path(__file__).with_name("diplomacy_catalog.json")
DEFAULT_DATABASE = ROOT / "work/runtime/diplomacy-api.sqlite3"
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
RECOVERY_IDENTITY_FIELDS = {"store_id", "session_id", "pid", "process_creation_filetime", "world_generation",
                            "game_sha256", "dll_sha256", "experiment_sha256", "whitelist_sha256"}


class APIError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status

    def as_dict(self) -> dict:
        return {"error": {"code": self.code, "message": str(self)}}


def decode_json(text: str) -> Any:
    """Reject ambiguous duplicate keys and non-JSON numeric constants."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise APIError("invalid_json", f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise APIError("invalid_json", f"Invalid JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, APIError):
            raise
        raise APIError("invalid_json", str(exc)) from exc


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_value(value: Any, schema: dict, path: str = "parameters") -> None:
    """Validate the catalog's documented JSON Schema subset, failing closed."""
    supported = {"type", "properties", "required", "additionalProperties", "items", "enum", "const",
                 "pattern", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
                 "description", "title", "default", "examples", "$schema"}
    unknown = set(schema) - supported
    if unknown:
        raise APIError("unsupported_schema", f"Unsupported schema keywords at {path}: {sorted(unknown)}", 422)
    kind = schema.get("type")
    valid_type = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "integer": type(value) is int,
        "number": type(value) in (int, float), "boolean": type(value) is bool,
        "null": value is None,
    }
    if kind not in valid_type or not valid_type[kind]:
        raise APIError("invalid_parameters", f"{path} must be {kind}", 422)
    if type(value) is float and not math.isfinite(value):
        raise APIError("invalid_parameters", f"{path} must be finite", 422)
    if "const" in schema and canonical(value) != canonical(schema["const"]):
        raise APIError("invalid_parameters", f"{path} must equal {schema['const']!r}", 422)
    if "enum" in schema and canonical(value) not in [canonical(v) for v in schema["enum"]]:
        raise APIError("invalid_parameters", f"{path} is outside the allowed values", 422)
    if kind == "object":
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        extra = set(value) - set(properties)
        if missing or extra:
            raise APIError("invalid_parameters", f"{path}: missing={sorted(missing)}, unknown={sorted(extra)}", 422)
        for key, item in value.items():
            validate_value(item, properties[key], f"{path}.{key}")
    elif kind == "array":
        for index, item in enumerate(value):
            validate_value(item, schema.get("items", {}), f"{path}[{index}]")
        for key, compare in (("minItems", lambda n: len(value) < n), ("maxItems", lambda n: len(value) > n)):
            if key in schema and compare(schema[key]):
                raise APIError("invalid_parameters", f"{path} violates {key}", 422)
    elif kind == "string":
        if "pattern" in schema:
            pattern = schema["pattern"]
            # Anchored identifier contracts must not admit Python's final-newline '$' exception.
            match = re.fullmatch(pattern, value) if pattern.startswith("^") and pattern.endswith("$") else re.search(pattern, value)
            if match is None:
                raise APIError("invalid_parameters", f"{path} does not match the required pattern", 422)
        for key, compare in (("minLength", lambda n: len(value) < n), ("maxLength", lambda n: len(value) > n)):
            if key in schema and compare(schema[key]):
                raise APIError("invalid_parameters", f"{path} violates {key}", 422)
    elif kind in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"] or "maximum" in schema and value > schema["maximum"]:
            raise APIError("invalid_parameters", f"{path} is outside the permitted range", 422)


class ExecutionBackend(Protocol):
    """Trusted, explicitly installed adapter. No adapter is inferred from a DLL.

    capability() is read-only and must check live readiness and action-specific
    constraints. submit() must recheck the exact process image and readiness at
    the side-effect boundary. It returns status queued/dispatched, external_id,
    and evidence. status() may report applied only with observed game effects.
    Neither queue insertion nor DLL consumption establishes an applied result.
    """
    name: str

    def capability(self, action: dict, build: dict, parameters: dict | None) -> dict: ...
    def submit(self, request: dict, build: dict) -> dict: ...
    def status(self, request: dict, receipt: dict) -> dict: ...


class ReconciliationBackend(ExecutionBackend, Protocol):
    """Optional read-only recovery. Never publish, retry, or call native actions.

    Evidence must bind the original request, dispatch build and process/session.
    The adapter remains responsible for verifying the actual durable evidence;
    API validation of its shape is not independent native execution proof.
    """
    def reconcile(self, request: dict, prior_record: dict) -> dict: ...


def default_build_probe(executable: Path | None) -> dict:
    if executable is None:
        return {"status": "not_inspected", "sha256": None, "reason": "No game executable configured"}
    try:
        # native_build owns the version policy; hashing alone cannot enable an adapter.
        from .native_build import inspect_build
        result = inspect_build(executable)
        return result.to_dict() if hasattr(result, "to_dict") else result
    except ImportError:
        if not executable.is_file():
            return {"status": "missing", "sha256": None, "reason": "Game executable not found"}
        digest = hashlib.sha256()
        with executable.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"status": "unverified", "sha256": digest.hexdigest().upper(),
                "reason": "Native build policy unavailable; execution disabled"}


class DiplomacyAPI:
    def __init__(self, catalog_path: Path = DEFAULT_CATALOG, database: Path = DEFAULT_DATABASE,
                 executable: Path | None = None, backend: ExecutionBackend | None = None,
                 build_probe: Callable[[], dict] | None = None):
        self.catalog = decode_json(Path(catalog_path).read_text(encoding="utf-8-sig"))
        if self.catalog.get("schema_version") != 1:
            raise APIError("catalog_version", "Unsupported catalog schema version", 500)
        self.actions = {}
        for original in self.catalog["actions"]:
            entry = dict(original)
            identifier = entry.get("action_id", entry.get("id"))
            if not isinstance(identifier, str) or identifier in self.actions:
                raise APIError("invalid_catalog", "Missing or duplicate action identifier", 500)
            entry["action_id"] = identifier
            entry["parameters"] = entry.get("parameters", entry.get("parameter_schema"))
            if not isinstance(entry["parameters"], dict):
                raise APIError("invalid_catalog", f"No parameter schema for {identifier}", 500)
            self.actions[identifier] = entry
        self.backend = backend
        self.build_probe = build_probe or (lambda: default_build_probe(executable))
        self.lock = threading.RLock()
        database = Path(database)
        database.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(database, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
                created_at TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_holds (
                backend_name TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL, created_at TEXT NOT NULL
            );
        """)
        # Recover holds from older ledgers too. Never infer a missing backend
        # identity from today's catalog; those historical rows need review.
        with self.db:
            for row in self.db.execute("SELECT request_id,result,created_at FROM requests WHERE status IN ('dispatching','dispatch_unknown') ORDER BY created_at"):
                backend_name = json.loads(row["result"]).get("backend")
                if isinstance(backend_name, str) and backend_name:
                    self.db.execute("INSERT OR IGNORE INTO execution_holds VALUES(?,?,?,?)",
                                    (backend_name, row["request_id"], "Unresolved dispatch; explicit reconciliation required", row["created_at"]))

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def _build(self) -> dict:
        try:
            result = self.build_probe()
            if not isinstance(result, dict):
                raise ValueError("Build inspector did not return an object")
            return result
        except Exception as exc:
            return {"status": "inspection_failed", "sha256": None, "reason": str(exc)}

    def _action(self, identifier: str) -> dict:
        if identifier not in self.actions:
            raise APIError("unknown_action", f"Unknown diplomacy action: {identifier}", 404)
        return self.actions[identifier]

    def _readiness(self, action: dict, build: dict, parameters: dict | None = None) -> dict:
        blockers = []
        dispatch_identity = None
        execution = action.get("execution", {})
        if action.get("parameter_status") != "specified":
            blockers.append({"code": "parameters_unresolved", "reason": "Native action arguments have not been fully established"})
        if execution.get("status") not in ("legacy_build_verified", "runtime_verified"):
            blockers.append({"code": "action_unimplemented", "reason": execution.get("reason", "No verified implementation")})
        if parameters is not None:
            for name, expected in execution.get("constraints", {}).items():
                if expected is not None and name in parameters and parameters[name] != expected:
                    blockers.append({"code": "backend_parameter_constraint", "reason": f"Verified backend requires {name}={expected!r}"})
        digest = (build.get("sha256") or build.get("executable_sha256") or "").upper()
        supported = execution.get("supported_builds", [])
        hashes = {(entry.get("sha256", "") if isinstance(entry, dict) else entry).upper() for entry in supported}
        if not digest or digest not in hashes:
            blockers.append({"code": "unsupported_build", "reason": "Executable SHA-256 is outside this action's verified builds"})
        if build.get("status") in ("inspection_failed", "missing", "not_inspected", "unverified"):
            blockers.append({"code": "build_not_verified", "reason": build.get("reason", "Build verification failed")})
        if self.backend is None:
            blockers.append({"code": "backend_unavailable", "reason": "No execution adapter is installed"})
        elif execution.get("backend") != self.backend.name:
            blockers.append({"code": "backend_mismatch", "reason": "Installed adapter does not implement this catalog entry"})
        if self.backend is not None:
            hold = self.db.execute("SELECT request_id,reason FROM execution_holds WHERE backend_name=?",
                                   (self.backend.name,)).fetchone()
            if hold:
                blockers.append({"code": "backend_execution_held", "reason": hold["reason"],
                                 "request_id": hold["request_id"], "automatic_retry": False})
        if self.backend is not None and not blockers:
            try:
                capability = self.backend.capability(action, build, parameters)
                dispatch_identity = capability.get("dispatch_identity")
                if dispatch_identity is not None:
                    if not isinstance(dispatch_identity, dict) or set(dispatch_identity) != RECOVERY_IDENTITY_FIELDS:
                        raise ValueError("Backend dispatch identity has unknown or missing fields")
                    canonical(dispatch_identity)
                if capability.get("ready") is not True:
                    blockers.append({"code": "backend_not_ready", "reason": capability.get("reason", "Backend is not ready")})
            except Exception as exc:
                blockers.append({"code": "backend_not_ready", "reason": str(exc)})
        return {"execution_allowed": not blockers, "blockers": blockers, "dispatch_identity": dispatch_identity}

    def capabilities(self) -> dict:
        build = self._build()
        return {"api_version": 1, "build": build, "backend": self.backend.name if self.backend else None,
                "coverage": self.catalog.get("coverage", {}),
                "actions": [dict(action, **self._readiness(action, build)) for action in self.actions.values()]}

    def describe(self, identifier: str) -> dict:
        action, build = self._action(identifier), self._build()
        return dict(action, build=build, **self._readiness(action, build))

    def validate(self, request: Any) -> dict:
        if not isinstance(request, dict) or set(request) != {"request_id", "action", "parameters"}:
            raise APIError("invalid_request", "Request must contain exactly request_id, action, parameters", 422)
        if not isinstance(request["request_id"], str) or not REQUEST_ID.fullmatch(request["request_id"]):
            raise APIError("invalid_request_id", "request_id must be 1-64 ASCII letters, digits, dots, underscores or hyphens", 422)
        if not isinstance(request["action"], str):
            raise APIError("invalid_request", "action must be a string", 422)
        action = self._action(request["action"])
        validate_value(request["parameters"], action["parameters"])
        return json.loads(canonical(request))

    def preview(self, request: Any) -> dict:
        request = self.validate(request)
        action, build = self._action(request["action"]), self._build()
        return {"request": request, "schema_valid": True, "preview_kind": "contract_only",
                "game_legality_checked": False, "game_effects_verified": False, "build": build,
                **self._readiness(action, build, request["parameters"])}

    def _event(self, request_id: str, event: str, detail: dict, now: str) -> None:
        self.db.execute("INSERT INTO events(request_id,created_at,event,detail) VALUES(?,?,?,?)",
                        (request_id, now, event, canonical(detail)))

    def _record(self, request_id: str) -> dict:
        row = self.db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise APIError("request_not_found", f"Request not found: {request_id}", 404)
        return {"request_id": request_id, "request": json.loads(row["payload"]), "status": row["status"],
                "request_sha256": row["digest"],
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "result": json.loads(row["result"]), "game_effects_verified": row["status"] == "applied"}

    def _transition(self, request_id: str, status: str, result: dict, *, expected_status: str,
                    hold_reason: str | None = None, release_hold: bool = False) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            updated = self.db.execute("UPDATE requests SET status=?,result=?,updated_at=? WHERE request_id=? AND status=?",
                                      (status, canonical(result), now, request_id, expected_status))
            if updated.rowcount:
                self._event(request_id, status, result, now)
                if hold_reason:
                    backend = result["backend"]
                    # An older unknown request must not overwrite another hold.
                    # The request table still preserves every unresolved outcome.
                    self.db.execute("INSERT OR IGNORE INTO execution_holds VALUES(?,?,?,?)",
                                    (backend, request_id, hold_reason, now))
                if release_hold:
                    self.db.execute("DELETE FROM execution_holds WHERE request_id=?", (request_id,))
                    self._restore_pending_hold(result["backend"], now)
            return bool(updated.rowcount)

    def _restore_pending_hold(self, backend: str, now: str) -> None:
        """Keep the backend frozen if another historical request is unresolved."""
        cursor = self.db.execute("SELECT request_id,result FROM requests WHERE status IN ('dispatching','dispatch_unknown') ORDER BY created_at")
        for row in cursor:
            prior = json.loads(row["result"])
            if prior.get("backend") == backend:
                self.db.execute("INSERT OR IGNORE INTO execution_holds VALUES(?,?,?,?)",
                                (backend, row["request_id"], "Unresolved dispatch; explicit reconciliation required", now))
                break

    @staticmethod
    def _validate_receipt(receipt: Any) -> None:
        if (not isinstance(receipt, dict) or receipt.get("status") not in ("queued", "dispatched")
                or not isinstance(receipt.get("external_id"), str) or not 1 <= len(receipt["external_id"]) <= 256
                or not receipt.get("evidence")):
            raise ValueError("Backend returned no trustworthy queue receipt")
        canonical(receipt)

    def _validate_recovery(self, observation: Any, record: dict) -> dict:
        """Bind recovery/unknown evidence; never infer proof from a status string."""
        if not isinstance(observation, dict) or not observation.get("evidence"):
            raise ValueError("Recovery requires evidence")
        canonical(observation)
        evidence = observation["evidence"]
        if not isinstance(evidence, list) or not all(isinstance(item, dict) and item.get("kind")
                and item.get("reference") and isinstance(item.get("sha256"), str)
                and re.fullmatch(r"[0-9A-Fa-f]{64}", item["sha256"]) for item in evidence):
            raise ValueError("Recovery evidence requires artifact kind, reference and SHA-256")
        binding = observation.get("binding")
        required = {"request_id", "request_sha256", "backend", "external_id", "sequence"} | RECOVERY_IDENTITY_FIELDS
        if not isinstance(binding, dict) or set(binding) != required:
            raise ValueError("Recovery requires complete process/session/request binding")
        if (binding["request_id"] != record["request_id"] or binding["request_sha256"] != record["request_sha256"]
                or binding["backend"] != self.backend.name or binding["backend"] != record["result"].get("backend")):
            raise ValueError("Recovery request digest or backend does not match durable dispatch")
        for key in ("external_id", "store_id", "session_id"):
            if not isinstance(binding[key], str) or not 1 <= len(binding[key]) <= 256:
                raise ValueError(f"Recovery binding {key} is invalid")
        for key in ("pid", "world_generation", "sequence"):
            maximum = 0xffffffff if key == "pid" else 0xffffffffffffffff
            if type(binding[key]) is not int or not 1 <= binding[key] <= maximum:
                raise ValueError(f"Recovery binding {key} is invalid")
        if not isinstance(binding["process_creation_filetime"], str) or not re.fullmatch(r"[0-9a-fA-F]{16}", binding["process_creation_filetime"]):
            raise ValueError("Recovery process creation time is invalid")
        for key in ("game_sha256", "dll_sha256", "experiment_sha256", "whitelist_sha256"):
            if not isinstance(binding[key], str) or not re.fullmatch(r"[0-9A-F]{64}", binding[key]):
                raise ValueError(f"Recovery binding {key} must be an uppercase SHA-256")
        prior_result = record["result"]
        identity = (prior_result.get("dispatch_context") or {}).get("identity")
        if not isinstance(identity, dict) or identity != {key: binding[key] for key in RECOVERY_IDENTITY_FIELDS}:
            raise ValueError("Recovery has no matching process/session identity recorded before dispatch")
        receipt = prior_result.get("receipt")
        if receipt and binding["external_id"] != receipt.get("external_id"):
            raise ValueError("Recovery external_id differs from durable receipt")
        prior_binding = (prior_result.get("observation", {}).get("binding") or
                         prior_result.get("binding") or (receipt or {}).get("binding"))
        if prior_binding is not None and binding != prior_binding:
            raise ValueError("Recovery process/session binding changed")
        build = (prior_result.get("dispatch_context") or {}).get("build", {})
        digest = build.get("sha256") or build.get("executable_sha256")
        if not digest or digest.upper() != binding["game_sha256"]:
            raise ValueError("Recovery has no matching durable dispatch build")
        state = observation.get("status")
        if state not in ("queued", "dispatched", "applied", "rejected", "failed", "dispatch_unknown"):
            raise ValueError("Recovery reported an unknown state")
        if state == "dispatch_unknown":
            if (observation.get("reason_code") != "native_dispatch_unknown"
                    or observation.get("automatic_retry") is not False
                    or observation.get("uncertainty") not in ("dispatch_outcome_unknown", "ownership_unknown")):
                raise ValueError("Native unknown requires explicit uncertainty and no-retry evidence")
            if observation.get("game_effects_verified") is True or (observation["uncertainty"] == "ownership_unknown" and observation.get("ownership_known") is True):
                raise ValueError("Unknown outcome cannot claim verified effects or known ownership")
            if observation["uncertainty"] == "dispatch_outcome_unknown" and observation.get("dispatch_outcome_known") is True:
                raise ValueError("Unknown dispatch cannot claim a known dispatch outcome")
        else:
            if observation.get("dispatch_outcome_known") is not True or observation.get("ownership_known") is not True:
                raise ValueError("Recovery must establish both dispatch outcome and ownership")
            if state == "applied" and observation.get("game_effects_verified") is not True:
                raise ValueError("Applied requires verified game effects")
            if state == "queued" and record["status"] in ("dispatched", "dispatch_unknown"):
                raise ValueError("Recovery cannot regress a possible dispatch to queued")
        return binding

    def submit(self, request: Any) -> dict:
        request = self.validate(request)
        payload = canonical(request)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        request_id = request["request_id"]
        with self.lock:
            existing = self.db.execute("SELECT digest FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if existing["digest"] != digest:
                    raise APIError("request_id_conflict", "request_id already identifies different parameters", 409)
                return dict(self._record(request_id), replayed=True)
            preview = self.preview(request)
            status = "dispatching" if preview["execution_allowed"] else "unsupported"
            now = datetime.now(timezone.utc).isoformat()
            context = {"backend": self.backend.name, "build": preview["build"], "request_sha256": digest,
                       "identity": preview.get("dispatch_identity")} if status == "dispatching" else None
            if context:
                context = json.loads(canonical(context))
            initial_result = dict(preview, backend=self.backend.name, dispatch_context=context) if context else preview
            # The unique key also prevents duplicate submissions across processes.
            try:
                with self.db:
                    self.db.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?)",
                                    (request_id, digest, payload, status, canonical(initial_result), now, now))
                    self._event(request_id, status, initial_result, now)
                    if context:
                        self.db.execute("INSERT INTO execution_holds VALUES(?,?,?,?)",
                                        (self.backend.name, request_id, "Dispatch lacks a durable receipt; no parallel dispatch", now))
            except sqlite3.IntegrityError:
                row = self.db.execute("SELECT digest FROM requests WHERE request_id=?", (request_id,)).fetchone()
                if not row:
                    raise APIError("backend_execution_held", "Backend acquired an unresolved dispatch; no request was sent", 409)
                if row["digest"] != digest:
                    raise APIError("request_id_conflict", "request_id was concurrently used for different parameters", 409)
                return dict(self._record(request_id), replayed=True)
            if status == "unsupported":
                return dict(self._record(request_id), replayed=False)
            try:
                receipt = self.backend.submit(json.loads(canonical(request)), json.loads(canonical(preview["build"])))
                self._validate_receipt(receipt)
                if context["identity"] is not None:
                    self._validate_recovery(receipt, self._record(request_id))
                self._transition(request_id, receipt["status"], {"backend": self.backend.name, "receipt": receipt,
                                 "dispatch_context": context}, expected_status="dispatching", release_hold=True)
            except Exception as exc:
                self._transition(request_id, "dispatch_unknown", {"reason": str(exc), "automatic_retry": False,
                                 "backend": self.backend.name,
                                 "dispatch_context": context,
                                 "detail": "Submission may have reached the game; reconcile before creating another request"},
                                 expected_status="dispatching", hold_reason="Dispatch outcome unknown; explicit reconciliation required")
            return dict(self._record(request_id), replayed=False)

    def status(self, request_id: str, *, refresh: bool = True) -> dict:
        with self.lock:
            record = self._record(request_id)
            receipt = record["result"].get("receipt")
            if (refresh and record["status"] in ("queued", "dispatched") and receipt and self.backend
                    and record["result"].get("backend") == self.backend.name):
                try:
                    observation = self.backend.status(record["request"], receipt)
                    state = observation.get("status")
                    if state not in ("queued", "dispatched", "applied", "rejected", "failed", "dispatch_unknown"):
                        raise ValueError("Backend reported an unknown state")
                    if not observation.get("evidence"):
                        raise ValueError("Backend state has no evidence")
                    if state == "applied" and observation.get("game_effects_verified") is not True:
                        raise ValueError("Applied requires verified game effects")
                    if record["status"] == "dispatched" and state == "queued":
                        raise ValueError("Backend state cannot regress")
                    if state == "dispatch_unknown" or (record["result"].get("dispatch_context") or {}).get("identity") is not None:
                        self._validate_recovery(observation, record)
                    result = {"backend": self.backend.name, "receipt": receipt, "observation": observation,
                              "dispatch_context": record["result"].get("dispatch_context")}
                    if state != record["status"] or result != record["result"]:
                        self._transition(request_id, state, result, expected_status=record["status"],
                                         hold_reason="Native dispatch or ownership unknown; explicit reconciliation required" if state == "dispatch_unknown" else None)
                    record = self._record(request_id)
                except Exception as exc:
                    # A failed read does not invent a new execution outcome.
                    record["observation_error"] = str(exc)
            if record["status"] == "dispatching":
                record["recovery_note"] = "Dispatch has no durable receipt yet; never automatically resubmit"
            return record

    def reconcile(self, request_id: str) -> dict:
        """Explicit read-only recovery of an existing request, never resubmission."""
        with self.lock:
            record = self._record(request_id)
            if record["status"] not in ("dispatching", "queued", "dispatched", "dispatch_unknown"):
                return dict(record, reconciled=False, reconciliation_note="Terminal records are immutable")
            backend_name = record["result"].get("backend")
            recover = getattr(self.backend, "reconcile", None)
            if self.backend is None or self.backend.name != backend_name or not callable(recover):
                raise APIError("reconciliation_unavailable", "The original read-only recovery adapter is not installed", 501)
            try:
                observation = recover(json.loads(canonical(record["request"])), json.loads(canonical(record)))
                binding = self._validate_recovery(observation, record)
                state = observation["status"]
                receipt = record["result"].get("receipt")
                recovered_receipt = observation.get("receipt")
                if recovered_receipt is not None:
                    self._validate_receipt(recovered_receipt)
                    if recovered_receipt["external_id"] != binding["external_id"] or recovered_receipt.get("binding") != binding:
                        raise ValueError("Recovered receipt identity differs from recovery evidence")
                    if receipt is not None and canonical(receipt) != canonical(recovered_receipt):
                        raise ValueError("Recovery cannot replace an existing receipt")
                    receipt = recovered_receipt
                if state in ("queued", "dispatched", "applied") and receipt is None:
                    raise ValueError("Recovery requires a trustworthy original publication receipt")
                result = {"backend": backend_name, "receipt": receipt, "observation": observation,
                          "dispatch_context": record["result"].get("dispatch_context"), "reconciled": True}
                changed = self._transition(request_id, state, result, expected_status=record["status"],
                                 hold_reason="Native dispatch or ownership unknown; explicit reconciliation required" if state == "dispatch_unknown" else None,
                                 release_hold=state != "dispatch_unknown")
                current = dict(self._record(request_id), reconciled=changed)
                if not changed:
                    current["reconciliation_note"] = "Concurrent state change won; stale recovery was not applied"
                return current
            except Exception as exc:
                now = datetime.now(timezone.utc).isoformat()
                with self.db:
                    self._event(request_id, "reconciliation_refused", {"reason": str(exc), "automatic_retry": False}, now)
                raise APIError("reconciliation_refused", f"No state change or resubmission: {exc}", 409) from None

    def audit(self, request_id: str) -> dict:
        with self.lock:
            self._record(request_id)
            rows = self.db.execute("SELECT * FROM events WHERE request_id=? ORDER BY event_id", (request_id,)).fetchall()
            return {"request_id": request_id, "events": [dict(row, detail=json.loads(row["detail"])) for row in rows]}
