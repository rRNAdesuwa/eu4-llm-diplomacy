"""Small stdlib HTTP transport for DiplomacyAPI; does not load/inject DLLs."""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import time
import threading
from urllib.parse import unquote, urlsplit

from .diplomacy_api import APIError, DiplomacyAPI, decode_json

MAX_BODY = 64 * 1024
# Small excess uploads can already be in flight when the headers are rejected.
# Discarding them avoids a Windows TCP reset hiding the 413 response. This is
# a separate transport budget, never an increase to the accepted JSON limit.
MAX_REJECT_DRAIN = MAX_BODY + 16 * 1024
REJECT_DRAIN_SECONDS = 0.25


def submit_http_status(result: dict) -> int:
    if result["status"] == "unsupported":
        return 501
    if result["status"] == "dispatch_unknown":
        return 502
    return 200 if result.get("replayed") or result["status"] in ("applied", "rejected", "failed") else 202


def make_server(api: DiplomacyAPI | None, host: str = "127.0.0.1", port: int = 8765,
                token: str | None = None, *, allow_remote: bool = False) -> ThreadingHTTPServer:
    """Bind loopback unless both explicit remote opt-in and a strong token exist."""
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        raise ValueError("Bind host must be localhost or an IP address") from None
    if not loopback and (not allow_remote or not token or len(token) < 32):
        raise ValueError("Remote binding requires allow_remote=True and a token of at least 32 characters")
    if ":" in host:
        raise ValueError("This server binds IPv4; use 127.0.0.1 for loopback")

    contract_apis = {}
    contract_lock = threading.Lock()

    def contracts(version=2):
        with contract_lock:
            if version not in contract_apis:
                contract_apis[version] = DiplomacyAPI.contract(version=version)
        return contract_apis[version]

    class Handler(BaseHTTPRequestHandler):
        server_version = "EU4Diplomacy/1"
        # HTTP/1.0 closes each connection, so rejected bodies cannot smuggle a next request.
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            # Requests and tokens are not copied into unstructured stderr logs.
            pass

        def _send(self, status: int, value: dict):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _authorize(self):
            # CLI/API clients do not send Origin. No browser cross-origin or DNS-rebinding access.
            if self.headers.get("Origin"):
                raise APIError("origin_forbidden", "Browser Origin requests are not supported", 403)
            if len(self.headers.get_all("Host", [])) != 1:
                raise APIError("invalid_host", "Exactly one Host header is required", 400)
            request_host = urlsplit("//" + self.headers["Host"]).hostname
            if loopback and request_host not in ("127.0.0.1", "localhost", host):
                raise APIError("invalid_host", "Host must identify the loopback service", 403)
            if token:
                supplied = self.headers.get("Authorization", "")
                if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + token).encode("utf-8")):
                    raise APIError("unauthorized", "A valid bearer token is required", 401)

        def _body(self, limit=MAX_BODY):
            if self.headers.get("Transfer-Encoding"):
                raise APIError("unsupported_transfer_encoding", "Chunked request bodies are not supported", 400)
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1:
                raise APIError("invalid_length", "Exactly one Content-Length header is required", 411)
            try:
                length = int(lengths[0])
            except ValueError:
                raise APIError("invalid_length", "Content-Length must be an integer", 400) from None
            if length < 0 or length > limit:
                if limit < length <= MAX_REJECT_DRAIN:
                    self._discard_small_rejected_body(length)
                raise APIError("body_too_large", f"Body must be at most {limit} bytes", 413)
            if self.headers.get_content_type() != "application/json":
                raise APIError("unsupported_media_type", "Use application/json", 415)
            body = self.rfile.read(length)
            if len(body) != length:
                raise APIError("invalid_length", "Truncated body", 400)
            try:
                return decode_json(body.decode("utf-8"))
            except UnicodeDecodeError:
                raise APIError("invalid_json", "Body must be UTF-8", 400) from None

        def _discard_small_rejected_body(self, length: int):
            """Discard a bounded excess upload without waiting on a slow sender."""
            deadline = time.monotonic() + REJECT_DRAIN_SECONDS
            previous_timeout = self.connection.gettimeout()
            remaining = min(length, MAX_REJECT_DRAIN)
            try:
                while remaining:
                    budget = deadline - time.monotonic()
                    if budget <= 0:
                        break
                    self.connection.settimeout(budget)
                    # read1 makes at most one socket read; read(n) could keep
                    # waiting for a trickling sender within a single iteration.
                    chunk = self.rfile.read1(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass  # A partial/stalled upload still receives the same 413.
            finally:
                self.connection.settimeout(previous_timeout)

        def _dispatch(self, method):
            try:
                self._authorize()
                parsed = urlsplit(self.path)
                if parsed.query or parsed.fragment:
                    raise APIError("invalid_path", "Query strings and fragments are not supported", 400)
                path = unquote(parsed.path)
                if path.startswith("/v3/") and not loopback:
                    raise APIError("version_bind", "V3 contract routes require loopback binding", 403)
                if method == "GET" and path == "/v2/actions":
                    return self._send(200, contracts().describe())
                if method == "GET" and path.startswith("/v2/actions/"):
                    return self._send(200, contracts().describe(path.removeprefix("/v2/actions/")))
                if method == "POST" and path == "/v2/validate":
                    return self._send(200, contracts().validate(self._body(limit=16 * 1024)))
                if method == "POST" and path == "/v2/requests":
                    return self._send(501, contracts().request(self._body(limit=16 * 1024)))
                if method == "GET" and path == "/v3/actions":
                    return self._send(200, contracts(3).describe())
                if method == "GET" and path.startswith("/v3/actions/"):
                    return self._send(200, contracts(3).describe(path.removeprefix("/v3/actions/")))
                if method == "POST" and path == "/v3/validate":
                    return self._send(200, contracts(3).validate(self._body(limit=16 * 1024)))
                if method == "POST" and path == "/v3/requests":
                    return self._send(501, contracts(3).request(self._body(limit=16 * 1024)))
                if api is None and path.startswith("/v1/"):
                    raise APIError("version_disabled", "V1 durable service is not enabled", 404)
                if method == "GET" and path == "/v1/capabilities":
                    return self._send(200, api.capabilities())
                if method == "GET" and path.startswith("/v1/actions/"):
                    return self._send(200, api.describe(path.removeprefix("/v1/actions/")))
                if method == "GET" and path.startswith("/v1/requests/"):
                    identifier = path.removeprefix("/v1/requests/")
                    if identifier.endswith("/events"):
                        return self._send(200, api.audit(identifier.removesuffix("/events")))
                    return self._send(200, api.status(identifier))
                if method == "POST" and path == "/v1/preview":
                    return self._send(200, api.preview(self._body()))
                if method == "POST" and path == "/v1/requests":
                    result = api.submit(self._body())
                    return self._send(submit_http_status(result), result)
                if method == "POST" and path.startswith("/v1/requests/") and path.endswith("/reconcile"):
                    if self._body() != {}:
                        raise APIError("invalid_request", "Reconciliation accepts only an empty JSON object; evidence comes from the installed adapter", 422)
                    result = api.reconcile(path.removeprefix("/v1/requests/").removesuffix("/reconcile"))
                    return self._send(submit_http_status(result), result)
                raise APIError("not_found", "Unknown API route", 404)
            except APIError as exc:
                self._send(exc.status, exc.as_dict())
            except (TimeoutError, ConnectionError):
                self.close_connection = True
            except Exception:
                self._send(500, {"error": {"code": "internal_error", "message": "Internal service error; no automatic retry"}})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
