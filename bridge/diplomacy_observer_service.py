"""Authenticated, loopback-only, read-only effect observation API."""
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
from urllib.parse import urlsplit

from bridge.diplomacy_effect_profiles import profile_catalog
from bridge.tag_command_backend import require


def make_server(observer, *, port=8775, token):
    require(type(port) is int and 0 <= port <= 65535, "Port bound")
    require(type(token) is str and token.isascii() and 16 <= len(token) <= 256, "Token must be 16..256 ASCII characters")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *unused):
            pass

        def send_json(self, code, value):
            raw = json.dumps(value, ensure_ascii=True, allow_nan=False).encode("ascii")
            require(len(raw) <= 256*1024, "Response bound")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            if self.headers.get_all("Origin", []):
                return False
            host = self.headers.get_all("Host", [])
            auth = self.headers.get_all("Authorization", [])
            valid_host = len(host) == 1 and re.fullmatch(r"(?:127\.0\.0\.1|localhost)(?::([0-9]{1,5}))?", host[0])
            return (bool(valid_host) and len(auth) == 1
                and (valid_host.group(1) is None or int(valid_host.group(1)) == self.server.server_port)
                and hmac.compare_digest(auth[0].encode("utf-8"), ("Bearer "+token).encode("ascii")))

        def do_GET(self):
            try:
                if not self.authorized():
                    return self.send_json(403, {"error": "unauthorized"})
                require(len(self.path) <= 512 and self.path.startswith("/"), "Path bound")
                path = urlsplit(self.path)
                require(not path.query and not path.fragment, "Query/fragment unsupported")
                if path.path == "/observer/v1/capabilities":
                    return self.send_json(200, {"schema": "EU4DIPLOMACY-OBSERVER-CATALOG/1",
                        "read_only": True, "profiles": profile_catalog(), "all120_effect_profiles_complete": False,
                        "native_calls": 0, "saves_written": 0, "requests_published": 0})
                prefix = "/observer/v1/effects/"
                if path.path.startswith(prefix):
                    request_id = path.path[len(prefix):]
                    require(re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", request_id), "Invalid request ID")
                    return self.send_json(200, observer.observe(request_id))
                return self.send_json(404, {"error": "not_found"})
            except FileNotFoundError:
                self.send_json(404, {"error": "request_not_found"})
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                self.send_json(422, {"error": "invalid_or_refused", "message": str(exc)})
            except (OSError, RuntimeError) as exc:
                self.send_json(409, {"status": "unknown", "message": str(exc), "automatic_command_retry": False})

        def refuse_write(self):
            allowed = self.authorized()
            # Discard a small, complete advertised body without interpreting
            # it. This avoids Windows resetting a short connection before the
            # caller receives the refusal. No publisher exists in this service.
            if allowed and not self.headers.get("Transfer-Encoding") and not self.headers.get("Expect"):
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit() and len(lengths[0]) <= 5:
                    length = int(lengths[0])
                    if length <= 65536:
                        try:
                            self.rfile.read(length)
                        except OSError:
                            pass
            self.send_json(405 if allowed else 403,
                {"error": "read_only_observer", "requests_published": 0})

        do_POST = refuse_write
        do_PUT = refuse_write
        do_DELETE = refuse_write
        do_PATCH = refuse_write

    return HTTPServer(("127.0.0.1", port), Handler)
