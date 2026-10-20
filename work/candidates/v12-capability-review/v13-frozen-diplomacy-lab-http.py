"""Local EU4LAB/2 v9 research transport; never registers a production backend.

Importing this module does not open a process, bind a socket, or write a mailbox.
The only publishing method delegates to the existing pinned v9 CLI protocol.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time

from bridge.diplomacy_api import APIError, canonical, decode_json
from bridge.native_pair_backend import MailboxError, publish_exclusive, read_bounded
from work.native import lab_protocol_v9_1375 as lab

PREFIX = "/research/v9"
HTTP_KIND = "eu4_lab_v9_research_http"
MAX_BODY = 4096
MAX_INTENTS = 4096
REQUEST_FIELDS = {"protocol", "pid", "creation", "sequence", "mode", "action", "actor", "target", "ttl_ms"}
BASE = {"research_only": True, "production": False, "production_backend_registered": False,
        "protocol": lab.PROTOCOL, "purpose": lab.PURPOSE, "automatic_retry": False,
        "applied_verified": False, "strict_live_single_player_verified": False,
        "world_generation_verified": False}


class ResearchError(APIError):
    def as_dict(self):
        return {**BASE, **super().as_dict()}


def require(condition, code, message, status=409):
    if not condition:
        raise ResearchError(code, message, status)


class V9ResearchRuntime:
    """Fixed output/profile; the HTTP caller cannot select a DLL or mailbox."""
    protocol = lab

    def __init__(self, pid: int, creation: str):
        lab = self.protocol
        require(lab.integer(pid, 1, 2**32 - 1) and isinstance(creation, str)
                and re.fullmatch(r"[0-9a-f]{16}", creation) and int(creation, 16) > 0,
                "invalid_binding", "Explicit PID and canonical creation time are required", 422)
        self.pid, self.creation = pid, creation
        self.manifest_sha = None
        self.metadata = None

    @contextmanager
    def observation(self):
        lab = self.protocol
        manifest, digest = lab.verify_build()
        require(self.manifest_sha is None or digest == self.manifest_sha,
                "build_changed", "The bound research manifest changed; no rebind or retry")
        with lab.LiveLabProcess(self.pid, expected_creation=self.creation) as process:
            session = lab.session_path(lab.OUTPUT, self.pid, self.creation)
            metadata = lab.read_session_metadata(session, self.pid, self.creation)
            require(self.metadata is None or self.metadata == metadata,
                    "session_changed", "Native installation identity changed")

            def refresh():
                _, current_digest = lab.verify_build()
                require(current_digest == digest, "build_changed", "Research manifest changed during observation")
                require(lab.read_session_metadata(session, self.pid, self.creation) == metadata,
                        "session_changed", "Native installation identity changed during observation")
                fixture = lab.verify_installed_fixture(manifest, self.pid, self.creation)
                evidence = lab.read_evidence(session, metadata)
                require(evidence["latest_frame"].get("running_speed_enabled") is manifest["running_speed_enabled"],
                        "build_changed", "Native running-speed gate differs from the pinned build")
                return evidence, process.snapshot(), fixture

            evidence, live, fixture = refresh()
            self.manifest_sha, self.metadata = digest, metadata
            snapshot = {"session": session, "metadata": metadata, "manifest_sha256": digest,
                        "dll_sha256": manifest["dll_sha256"], "fixture_disk_evidence": fixture,
                        "evidence": evidence, "live": live, "now": lab.uptime_ms()}
            yield snapshot, refresh

    def inspect(self):
        with self.observation() as (snapshot, _):
            return snapshot

    def publish(self, original, request):
        lab = self.protocol
        with self.observation() as (current, refresh):
            require(current["manifest_sha256"] == original["manifest_sha256"]
                    and current["metadata"] == original["metadata"]
                    and current["evidence"]["last_sequence"] == original["evidence"]["last_sequence"]
                    and all(current["live"][key] == original["live"][key]
                            for key in ("pid", "creation", "world_cookie", "player_handle")),
                    "session_changed", "Session/world/sequence changed before publication; retained intent forbids retry")

            def recheck():
                evidence, live, _fixture = refresh()
                return evidence, live

            return lab.publish_research(current["session"], current["metadata"], current["manifest_sha256"],
                current["evidence"], current["live"], sequence=request["sequence"], operation="pair",
                mode=request["mode"], action=request["action"], actor=request["actor"], target=request["target"],
                speed=0, ttl_ms=request["ttl_ms"], recheck=recheck)


class ResearchService:
    """Sequence idempotency is durable and shared with the native mailbox.

    A .http-intent is never deleted, including after a failure before publication.
    It is not a native acknowledgement. A duplicate only reads evidence; it cannot
    renew a TTL or recreate a request. There is no reset/unfreeze HTTP operation.
    """
    protocol = lab
    prefix = PREFIX
    kind = HTTP_KIND
    base = BASE
    historical_action_ids = frozenset(lab.ACTIONS)

    def __init__(self, runtime, *, capability_reader=None):
        require(getattr(runtime, "protocol", self.protocol) is self.protocol,
                "profile_mismatch", "Service and runtime must use the same fixed research protocol module", 422)
        self.runtime = runtime
        self.pid, self.creation = runtime.pid, runtime.creation
        self._lock = threading.Lock()
        if capability_reader is None:
            from bridge.diplomacy_research_capabilities import capabilities
            capability_reader = capabilities
        self._capability_reader = capability_reader

    @contextmanager
    def _exclusive(self):
        require(self._lock.acquire(blocking=False), "service_busy", "Another session operation is active; query status later")
        try:
            yield
        finally:
            self._lock.release()

    def _inspect(self):
        lab = self.protocol
        try:
            return self.runtime.inspect()
        except ResearchError:
            raise
        except (lab.LabError, MailboxError, APIError, OSError, ValueError) as error:
            raise ResearchError("session_guard_failed", str(error) + "; no automatic retry", 409) from error

    def initialize(self):
        """Read-only startup preflight. Does not require three phases to pass yet."""
        with self._exclusive():
            snapshot = self._inspect()
            return self._summary(snapshot)

    def _summary(self, snapshot):
        lab = self.protocol
        evidence = snapshot["evidence"]
        try:
            lab.check_ready(evidence, snapshot["live"], snapshot["now"], operation="pair")
            ready, reason = True, None
        except (lab.LabError, KeyError, TypeError) as error:
            ready, reason = False, str(error)
        holds = self._holds(snapshot, self._intents(snapshot))
        if holds:
            ready, reason = False, "A mailbox publication is unresolved; query its evidence and never republish"
        return {**self.base, "pid": self.pid, "creation": self.creation,
                "manifest_sha256": snapshot["manifest_sha256"], "dll_sha256": snapshot["dll_sha256"],
                "fixture_disk_evidence": snapshot["fixture_disk_evidence"],
                "latest_frame": evidence["latest_frame"], "phases": evidence["phases"],
                "last_sequence": evidence["last_sequence"], "pending": evidence["pending"],
                "lease_pending": evidence["lease_pending"], "log_sha256": evidence["log_sha256"],
                "pair_publication_ready": ready, "not_ready_reason": reason, "mailbox_holds": holds,
                "read_only": True, "readiness_is_snapshot_only": True}

    def capabilities(self):
        lab = self.protocol
        from bridge.diplomacy_research_capabilities import DISCOVERY_CATALOG_ACTIONS
        history = self._capability_reader(research_only=True)
        rows = history["actions"]
        identifiers = {row["action_id"] for row in rows}
        require(len(identifiers) == len(rows) and self.historical_action_ids <= identifiers <= DISCOVERY_CATALOG_ACTIONS,
                "capability_mismatch", "Research history does not match the reviewed versioned action scope", 503)
        rows = [row for row in rows if row["action_id"] in lab.ACTIONS]
        return {**self.base, "kind": self.kind, "pid": self.pid, "creation": self.creation,
                "live_readiness": None, "live_process_inspected": False,
                "discovery_source": history["discovery_source"], "summary": history["summary"],
                "catalog_sha256": history["catalog_sha256"], "research_index_sha256": history["research_index_sha256"],
                "history_actions": rows,
                # History for a different native purpose never supplies this server's preflight proof.
                "historical_preflights": [record for record in history.get("historical_preflights", [])
                    if record.get("purpose") == lab.PURPOSE and record.get("protocol") == lab.PROTOCOL
                    and record.get("action_ids") == sorted(lab.ACTIONS)],
                "http_pair_contract": {"actions": sorted(lab.ACTIONS), "modes": ["legality_only", "submit"],
                    "actor_tags": list(lab.TAGS), "target_tags": list(lab.TAGS), "submit_actor": "FRA",
                    "actor_must_differ_from_target": True, "sequence_range": [1, lab.MAX_SEQUENCE],
                    "ttl_ms_range": [1, lab.MAX_TTL], "required_fields": sorted(REQUEST_FIELDS),
                    "additional_properties": False, "sequence_selection": "caller_supplied_exact_next_only"},
                "routes": {"GET": [self.prefix + "/capabilities", self.prefix + "/status", self.prefix + "/requests/{sequence}"],
                           "POST": [self.prefix + "/pair"]},
                "unavailable_http_operations": ["fixture", "speed", "stage", "load", "reset", "production_submit"],
                "semantics": {"legality_only": "Publishes a main-thread native legality experiment; not AI acceptance or a pure JSON preview",
                    "submit": "Publishes once; a native return is not an applied effect",
                    "status": "Read-only verified snapshot; missing completion is never a rejection or permission to retry"}}

    def _validate_request(self, request):
        lab = self.protocol
        require(isinstance(request, dict) and set(request) == REQUEST_FIELDS,
                "invalid_request", "Supply exactly the documented pair request fields", 422)
        require(request["protocol"] == lab.PROTOCOL, "wrong_protocol", "Only this bound EU4LAB/2 research protocol is accepted", 422)
        require(type(request["pid"]) is int and request["pid"] == self.pid and request["creation"] == self.creation,
                "wrong_session", "Request PID/creation differs from this bound service", 409)
        require(lab.integer(request["sequence"], 1, lab.MAX_SEQUENCE)
                and lab.integer(request["ttl_ms"], 1, lab.MAX_TTL),
                "invalid_request", "Sequence and TTL must be integers in the advertised bounds", 422)
        require(all(isinstance(request[key], str) for key in ("mode", "action", "actor", "target")),
                "invalid_request", "Mode, action and country tags must be strings", 422)
        try:
            lab.encode_request({key: request[key] for key in ("pid", "creation", "sequence", "mode", "action", "actor", "target")}
                               | {"operation": "pair", "speed": 0, "expires": 1})
            lab.require(request["mode"] != "submit" or request["actor"] == "FRA", "Only current player FRA may submit")
        except lab.LabError as error:
            raise ResearchError("invalid_request", str(error), 422) from error
        return dict(request)

    def _intents(self, snapshot):
        intents = {}
        for path in Path(snapshot["session"]).glob("*.http-intent"):
            require(len(intents) < MAX_INTENTS and re.fullmatch(r"[0-9]{20}\.http-intent", path.name),
                    "invalid_ledger", "Unexpected or excessive HTTP intent files")
            sequence = int(path.name[:20])
            intent = decode_json(read_bounded(path, MAX_BODY).decode("utf-8"))
            require(isinstance(intent, dict) and set(intent) == {"kind", "request", "request_sha256", "manifest_sha256", "automatic_retry"},
                    "invalid_ledger", "Malformed HTTP intent")
            request = self._validate_request(intent["request"])
            require(intent["kind"] == self.kind and intent["automatic_retry"] is False
                    and intent["manifest_sha256"] == snapshot["manifest_sha256"] and request["sequence"] == sequence
                    and intent["request_sha256"] == hashlib.sha256(canonical(request).encode("ascii")).hexdigest(),
                    "invalid_ledger", "HTTP intent binding/hash differs")
            intents[sequence] = intent
        return intents

    def _holds(self, snapshot, intents):
        """Observe CLI publications too; a ready frame can precede file pickup."""
        lab = self.protocol
        session = Path(snapshot["session"])
        sequences = set(intents)
        count = 0
        for path in session.glob("*.host-intent"):
            count += 1
            require(count <= MAX_INTENTS + len(lab.PHASES), "invalid_ledger", "Publication intent budget exceeded")
            if re.fullmatch(r"[0-9]{20}\.host-intent", path.name):
                sequences.add(int(path.name[:20]))
            else:
                require(path.name in {row[1] + ".host-intent" for row in lab.PHASES.values()},
                        "invalid_ledger", "Unknown publication intent filename")
        holds = []
        for sequence in sorted(sequences):
            state = self._sequence(snapshot, sequence, intents.get(sequence))
            if state["state"] != "native_completed":
                holds.append({"sequence": sequence, "state": state["state"]})
        # One pending marker suffices to block; never materialize an unbounded
        # directory listing. The native publisher repeats this check itself.
        if next(session.glob("*.request"), None) is not None and not holds:
            holds.append({"sequence": None, "state": "mailbox_request_pending"})
        return holds

    def _sequence(self, snapshot, sequence, intent=None):
        lab = self.protocol
        session, evidence = Path(snapshot["session"]), snapshot["evidence"]
        path = session / f"{sequence:020}.host-intent"
        native = evidence["requests"].get(sequence)
        common = {**self.base, "pid": self.pid, "creation": self.creation, "sequence": sequence,
                  "read_only": True, "native_dispatch_verified": False, "ai_acceptance_verified": False}
        if not path.exists():
            require(native is None, "invalid_ledger", "Native request lacks its host intent")
            if intent is not None:
                return {**common, "state": "publication_unknown", "reason": "HTTP intent exists; native publication was not observed"}
            raise ResearchError("request_not_found", "No verified request exists; absence never authorizes an old sequence retry", 404)
        host = decode_json(read_bounded(path, MAX_BODY).decode("utf-8"))
        require(isinstance(host, dict) and set(host) == {"protocol", "purpose", "pid", "creation", "manifest_sha256", "request_sha256", "body_ascii", "automatic_retry"},
                "invalid_ledger", "Malformed native publication intent")
        require(isinstance(host["body_ascii"], str), "invalid_ledger", "Native intent body must be ASCII")
        wire = host["body_ascii"].encode("ascii")
        record = lab.decode_request(wire)
        require(host["protocol"] == lab.PROTOCOL and host["purpose"] == lab.PURPOSE
                and type(host["pid"]) is int and host["pid"] == self.pid and host["creation"] == self.creation
                and host["manifest_sha256"] == snapshot["manifest_sha256"] and host["automatic_retry"] is False
                and host["request_sha256"] == hashlib.sha256(wire).hexdigest()
                and record["pid"] == self.pid and record["creation"] == self.creation and record["sequence"] == sequence,
                "invalid_ledger", "Native intent identity/hash differs")
        if intent is not None:
            require(record["operation"] == "pair" and all(record[key] == intent["request"][key]
                    for key in ("pid", "creation", "sequence", "mode", "action", "actor", "target")),
                    "invalid_ledger", "HTTP and native publication intents disagree")
        common.update(request=record, request_sha256=host["request_sha256"])
        if native is not None:
            require(native["request"] == record, "invalid_ledger", "Native claim evidence differs from the exact published request")
            complete = native["complete"]
            if complete is not None:
                return {**common, "state": "native_completed", "native": native,
                        "native_dispatch_verified": complete.get("submit_entered") is True and complete.get("submit_returned") is True}
            return {**common, "state": "native_dispatch_unknown", "native": native,
                    "reason": "Native claim lacks complete validated evidence; no retry"}
        queued = session / f"{sequence:020}.request"
        if queued.exists():
            require(read_bounded(queued, lab.MAX_RECORD) == wire, "invalid_ledger", "Queued request differs from durable intent")
            if snapshot["now"] < record["expires"]:
                return {**common, "state": "queued", "reason": "File is published; native dispatch is not yet verified"}
        return {**common, "state": "publication_unknown", "reason": "No validated native completion and no live queued file; never republish"}

    def status(self, sequence=None):
        with self._exclusive():
            snapshot = self._inspect()
            if sequence is None:
                return self._summary(snapshot)
            return self._sequence(snapshot, sequence, self._intents(snapshot).get(sequence))

    def pair(self, body):
        lab = self.protocol
        request = self._validate_request(body)
        sequence = request["sequence"]
        with self._exclusive():
            snapshot = self._inspect()
            intents = self._intents(snapshot)
            if sequence in intents:
                require(intents[sequence]["request"] == request, "sequence_conflict", "Sequence is permanently bound to a different exact HTTP request")
                return 200, {**self._sequence(snapshot, sequence, intents[sequence]), "replayed": True, "request_written": False}
            session = Path(snapshot["session"])
            require(not any((session / f"{sequence:020}.{suffix}").exists() for suffix in ("host-intent", "request", "claim")),
                    "sequence_reserved", "This sequence was already reserved outside HTTP; query status and do not replace it")
            require(not self._holds(snapshot, intents), "unresolved_sequence",
                    "A previous mailbox publication is unresolved; no next sequence may be sent")
            try:
                lab.check_ready(snapshot["evidence"], snapshot["live"], snapshot["now"], operation="pair")
                lab.prepare_request(snapshot["metadata"], snapshot["evidence"], sequence=sequence, operation="pair",
                    mode=request["mode"], action=request["action"], actor=request["actor"], target=request["target"],
                    speed=0, ttl_ms=request["ttl_ms"], now=snapshot["now"])
            except lab.LabError as error:
                raise ResearchError("not_ready", str(error), 409) from error
            intent = {"kind": self.kind, "request": request, "request_sha256": hashlib.sha256(canonical(request).encode("ascii")).hexdigest(),
                      "manifest_sha256": snapshot["manifest_sha256"], "automatic_retry": False}
            # Exclusivity also protects independent HTTP instances. Losing an
            # intent race cannot invoke the publisher or replace the winner.
            try:
                publish_exclusive(session / f"{sequence:020}.http-intent", (canonical(intent) + "\n").encode("ascii"))
            except OSError as error:
                raise ResearchError("intent_reservation_failed", "Cannot exclusively reserve sequence; query status; no retry", 409) from error
            try:
                publication = self.runtime.publish(snapshot, request)
                require(publication.get("status") == "published" and publication.get("sequence") == sequence
                        and publication.get("pid") == self.pid and publication.get("creation") == self.creation,
                        "publication_unknown", "Publisher did not return its bound publication identity")
            except Exception as error:
                raise ResearchError("publication_unknown", "Publication did not complete with verified acknowledgement; retained intent blocks retry; query status", 502) from error
            return 202, {**self.base, "pid": self.pid, "creation": self.creation, "sequence": sequence,
                         "state": "queued", "request_sha256": publication["request_sha256"],
                         "request_written": True, "replayed": False, "native_dispatch_verified": False}

    def dispatch(self, method, path, body=None):
        """Pure routing boundary; tests need no listening socket or live process."""
        lab = self.protocol
        try:
            require(isinstance(path, str) and not any(c in path for c in ("?", "#", "%", "\\")),
                    "invalid_path", "Only exact research routes are accepted", 400)
            if method == "GET" and path == self.prefix + "/capabilities":
                return 200, self.capabilities()
            if method == "GET" and path == self.prefix + "/status":
                return 200, self.status()
            match = re.fullmatch(re.escape(self.prefix) + r"/requests/([1-9][0-9]{0,18})", path)
            if method == "GET" and match:
                sequence = int(match.group(1))
                require(sequence <= lab.MAX_SEQUENCE, "invalid_sequence", "Sequence exceeds protocol bounds", 422)
                return 200, self.status(sequence)
            if method == "POST" and path == self.prefix + "/pair":
                return self.pair(body)
            raise ResearchError("not_found", "Unknown research route; fixture, speed, phases and production are not exposed", 404)
        except ResearchError as error:
            return error.status, {**error.as_dict(), **self.base}
        except (lab.LabError, MailboxError, APIError, OSError, ValueError) as error:
            failure = ResearchError("evidence_unavailable", str(error) + "; no automatic retry", 409)
            return failure.status, {**failure.as_dict(), **self.base}
        except Exception:
            failure = ResearchError("internal_error", "Cannot verify result; query status; no automatic retry", 500)
            return failure.status, {**failure.as_dict(), **self.base}


def handler_class(service, token):
    require(isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token),
            "invalid_token", "A 32..128 character ASCII bearer token is required", 422)
    response_base = getattr(service, "base", BASE)
    require(isinstance(response_base, dict), "invalid_service", "A fixed research service profile is required", 422)

    class Handler(BaseHTTPRequestHandler):
        server_version = "EU4Research"
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def _authorize(self):
            require(not self.headers.get_all("Origin", []), "origin_forbidden", "Browser origins are not supported", 403)
            hosts = self.headers.get_all("Host", [])
            require(len(hosts) == 1 and hosts[0] in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"),
                    "invalid_host", "Host must name this exact loopback port", 403)
            supplied = self.headers.get_all("Authorization", [])
            require(len(supplied) == 1 and hmac.compare_digest(supplied[0].encode("utf-8"), ("Bearer " + token).encode("ascii")),
                    "unauthorized", "A valid research bearer token is required", 401)

        def _body(self):
            require(not self.headers.get_all("Transfer-Encoding", []), "invalid_framing", "Transfer-Encoding is not supported", 400)
            require(not self.headers.get_all("Expect", []), "invalid_framing", "Expect handshakes are not supported", 417)
            lengths = self.headers.get_all("Content-Length", [])
            require(len(lengths) == 1 and re.fullmatch(r"0|[1-9][0-9]{0,8}", lengths[0]),
                    "invalid_length", "Exactly one canonical Content-Length is required", 411)
            length = int(lengths[0])
            if MAX_BODY < length <= MAX_BODY + 4096:
                # Small excess uploads may already be in flight on Windows;
                # a bounded drain avoids a close/reset hiding the 413 response.
                remaining, deadline = length, time.monotonic() + 0.1
                try:
                    while remaining and (budget := deadline - time.monotonic()) > 0:
                        self.connection.settimeout(budget)
                        chunk = self.rfile.read1(min(remaining, 4096))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                except OSError:
                    pass
            require(length <= MAX_BODY, "body_too_large", "JSON body exceeds 4096 bytes", 413)
            require(len(self.headers.get_all("Content-Type", [])) == 1 and self.headers.get_content_type() == "application/json",
                    "invalid_media_type", "Use application/json", 415)
            chunks, remaining, deadline = [], length, time.monotonic() + 1.0
            while remaining:
                budget = deadline - time.monotonic()
                require(budget > 0, "body_timeout", "Body exceeded its bounded read deadline", 408)
                self.connection.settimeout(budget)
                chunk = self.rfile.read1(min(remaining, 4096))
                require(bool(chunk), "invalid_length", "Truncated body", 400)
                chunks.append(chunk)
                remaining -= len(chunk)
            return decode_json(b"".join(chunks).decode("utf-8"))

        def _send(self, status, value):
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            for key, value in (("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(raw))),
                               ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Connection", "close")):
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def _dispatch(self, method):
            try:
                self._authorize()
                body = self._body() if method == "POST" else None
                status, response = service.dispatch(method, self.path, body)
            except APIError as error:
                status, response = error.status, {**error.as_dict(), **response_base}
            except UnicodeError:
                status, response = 400, {**response_base, "error": {"code": "invalid_json", "message": "Body must be UTF-8 JSON"}}
            except (TimeoutError, ConnectionError, OSError):
                status, response = 408, {**response_base, "error": {"code": "body_timeout", "message": "Transport interrupted; query status; no retry"}}
            self._send(status, response)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


class BoundedResearchServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def make_server(service, *, host="127.0.0.1", port=8766, token):
    require(host == "127.0.0.1", "invalid_bind", "Research HTTP binds only 127.0.0.1", 422)
    require(lab.integer(port, 1, 65535), "invalid_bind", "Port must be 1..65535", 422)
    handler = handler_class(service, token)
    service.initialize()  # Identity/profile preflight precedes binding the socket.
    return BoundedResearchServer((host, port), handler)
