"""Loopback HTTP interface to the actual TAG-command native host."""
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from urllib.parse import parse_qs, urlsplit

from bridge.tag_command_backend import PublicationUnknownError, decode, require, validate_identity
from bridge.tag_action_conditions import action_conditions
from bridge.tag_action_lookup import lookup_action, search_actions


def search_parameters(query):
    require(len(query) <= 2048, 'Search query string too long')
    fields = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=5)
    require(set(fields) <= {'q','category','support','offset','limit'}
            and all(len(values) == 1 for values in fields.values()), 'Unknown or repeated search parameter')
    result = {'query':fields.get('q',[''])[0]}
    for key in ('category','support'):
        if key in fields:
            result[key] = fields[key][0]
    for key in ('offset','limit'):
        if key in fields:
            value = fields[key][0]
            require(value.isascii() and value.isdecimal() and len(value) <= 3,
                    'Invalid numeric search parameter')
            result[key] = int(value)
    return result


def make_server(backend, identity, *, port=8774, token):
    identity = validate_identity(identity)
    require(type(token) is str and 16 <= len(token) <= 256 and token.isascii(), "Token must contain 16..256 ASCII characters")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        def setup(self):
            super().setup()
            self.connection.settimeout(5)
        def log_message(self,*args):
            pass
        def send_json(self,status,value):
            data = json.dumps(value,ensure_ascii=False,allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(data)
        def authorized(self):
            if self.headers.get("Origin"):
                return False
            hosts = self.headers.get_all("Host",[])
            if len(hosts) != 1 or urlsplit("//"+hosts[0]).hostname not in ("127.0.0.1","localhost"):
                return False
            supplied = self.headers.get_all("Authorization",[])
            return len(supplied) == 1 and hmac.compare_digest(supplied[0].encode("utf-8"),("Bearer "+token).encode("ascii"))
        def body(self):
            require(not self.headers.get("Transfer-Encoding"), "Transfer-Encoding is unsupported")
            lengths = self.headers.get_all("Content-Length",[])
            require(len(lengths) == 1 and lengths[0].isdigit(), "One Content-Length required")
            length = int(lengths[0])
            require(0 < length <= 65536, "Body size bound")
            require(self.headers.get_content_type() == "application/json", "Use application/json")
            raw = self.rfile.read(length)
            require(len(raw) == length, "Truncated body")
            return decode(raw)
        def dispatch(self,method):
            try:
                if not self.authorized():
                    return self.send_json(403,{"error":"unauthorized"})
                path = urlsplit(self.path)
                require(not path.fragment, "Fragments are unsupported")
                if method == "GET" and path.path == "/native/v1/actions":
                    return self.send_json(200,search_actions(backend,**search_parameters(path.query)))
                require(not path.query, "Query strings are unsupported for this endpoint")
                if method == "GET" and path.path.startswith("/native/v1/actions/"):
                    action = path.path.removeprefix("/native/v1/actions/")
                    return self.send_json(200,lookup_action(backend,action))
                if method == "GET" and path.path == "/native/v1/capabilities":
                    return self.send_json(200,backend.capabilities())
                if method == "GET" and path.path.startswith("/native/v1/conditions/"):
                    action = path.path.removeprefix("/native/v1/conditions/")
                    return self.send_json(200,action_conditions(backend,action))
                if method == "GET" and path.path.startswith("/native/v1/commands/"):
                    key = path.path.removeprefix("/native/v1/commands/")
                    return self.send_json(200,backend.status(identity,key))
                if method == "POST" and path.path == "/native/v1/commands":
                    result = backend.publish(identity,[self.body()])
                    return self.send_json(200 if result["reused"] else 202,result)
                if method == "POST" and path.path == "/native/v1/batches":
                    result = backend.publish(identity,self.body())
                    return self.send_json(200 if result["reused"] else 202,result)
                return self.send_json(404,{"error":"not_found"})
            except PublicationUnknownError as error:
                self.send_json(409,error.result)
            except FileNotFoundError:
                self.send_json(404,{"error":"not_found"})
            except (ValueError,KeyError,TypeError,UnicodeError) as error:
                self.send_json(422,{"error":"invalid_or_refused","message":str(error)})
            except (OSError,RuntimeError) as error:
                self.send_json(409,{"error":"native_unavailable_or_unknown","message":str(error),"automatic_retry":False})
        def do_GET(self):
            self.dispatch("GET")
        def do_POST(self):
            self.dispatch("POST")
    return HTTPServer(("127.0.0.1",port),Handler)
