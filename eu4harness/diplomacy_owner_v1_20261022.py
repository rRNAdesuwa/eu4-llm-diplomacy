"""Explicit /v1 facade over the retained cold owner's tools.

No server, backend or owner is created. install_once runs on the product main
thread inside its existing command loop. HTTP workers enqueue onto that SAME
loop; no EU4PAIR, file polling, policy relaxation or implicit Send is provided.
Development and production submissions are explicit separate routes. Both can
execute real game actions and retain all historical/Unknown holds. This facade
does not certify permission or runtime readiness.
"""
from __future__ import annotations

import json
from pathlib import Path
import queue
import re
import sys
import threading
import types
from urllib.parse import unquote, urlsplit

ROOT = Path("E:/work/Programming/eullm")
_RETAINED = []
_ENVELOPE = "v1-owner-tool-dispatch"
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z", re.ASCII)


def _need(value, reason):
    if not value:
        raise RuntimeError(reason)


class OwnerV1Adapter:
    """One bounded queue facade; accepted/timed-out jobs are never resubmitted."""
    def __init__(self, product, messages):
        self.product, self.messages = product, messages
        self.thread = product.thread
        self.binding = (product.owner, product.api_tools, product.effect_observer,
                        product.service, product.backend, product.runtime)
        self.old_command = product.command
        self.old_handler = product.service.httpd.RequestHandlerClass
        self.lock, self.jobs = threading.Lock(), {}
        self.installed = False

    def _current(self):
        p = self.product
        _need(p.connected and getattr(p, "_owner_v1_adapter", None) is self
              and all(a is b for a, b in zip(self.binding,
                  (p.owner, p.api_tools, p.effect_observer, p.service, p.backend, p.runtime)))
              and p._api_tools_bound and not p.owner._invalidated
              and p.owner._owner == self.thread, "Original retained API graph changed")

    @staticmethod
    def _route(method, path, body):
        from .v32_diplomacy_tools_20261020 import (
            CAPABILITIES_TOOL, PREPARE_TOOL, SUBMIT_TOOL, STATUS_TOOL, EFFECT_TOOL,
            PRODUCTION_SUBMIT_TOOL, CANDIDATES_TOOL, REPLIES_CURRENT_TOOL, NATIVE_OBSERVATION_TOOL, OUTCOME_TOOL,
            ACTION_CATALOG_TOOL, QUERY_TOOL, PREVIEW_TOOL, RESPONSE_TOOL)
        parsed = urlsplit(path)
        _need(not parsed.query and not parsed.fragment, "No API query/fragment")
        path = unquote(parsed.path)
        if method == "GET" and path == "/v1/capabilities" and body is None:
            return CAPABILITIES_TOOL, {}, False
        if method == "GET" and path == "/v1/actions" and body is None:
            return ACTION_CATALOG_TOOL, {}, False
        if method == "GET" and path.startswith("/v1/actions/") and body is None:
            action = path[len("/v1/actions/"):]
            _need(re.fullmatch(r"[a-z0-9_.]{1,96}", action), "Exact action name required")
            return ACTION_CATALOG_TOOL, {"action": action}, False
        if method == "POST" and path == "/v1/diplomacy/query" and type(body) is dict and set(body) == {"request"}:
            return QUERY_TOOL, body, False
        if method == "POST" and path == "/v1/diplomacy/preview":
            _need(type(body) is dict and set(body) == {"request", "ttl_ms", "allow_writes"}
                  and body["allow_writes"] is True, "Preview requires request, ttl_ms and allow_writes=True")
            return PREVIEW_TOOL, {k: body[k] for k in ("request", "ttl_ms")}, True
        if method == "POST" and path == "/v1/prepare" and type(body) is dict and set(body) == {"request"}:
            return PREPARE_TOOL, body, False
        if method == "POST" and path == "/v1/candidates" and type(body) is dict:
            if body.get("kind") == "curia_controller":
                # PAP selects the Catholic scope; the current controller is returned.
                # There is no target country for this discovery request.
                if set(body) in ({"kind"}, {"kind", "actor"}) and body.get("actor", "PAP") == "PAP":
                    return CANDIDATES_TOOL, body, False
            elif set(body) == {"kind", "actor", "target"}:
                return CANDIDATES_TOOL, body, False
        if method == "POST" and path == "/v1/replies/current" and type(body) is dict and set(body) == {"actor", "target"}:
            return REPLIES_CURRENT_TOOL, body, False
        if method == "POST" and path == "/v1/requests":
            _need(type(body) is dict and set(body) == {"request", "ttl_ms", "test_only", "allow_writes"}
                  and body["test_only"] is True and body["allow_writes"] is True,
                  "Submit requires explicit test_only=True and allow_writes=True")
            return SUBMIT_TOOL, {k: body[k] for k in ("request", "ttl_ms", "test_only")}, True
        if method == "POST" and path == "/v1/production/requests":
            _need(type(body) is dict and set(body) == {"request", "ttl_ms", "allow_writes"}
                  and body["allow_writes"] is True,
                  "Production submit requires explicit allow_writes=True without a test flag")
            return PRODUCTION_SUBMIT_TOOL, {k: body[k] for k in ("request", "ttl_ms")}, True
        if method == "GET" and path.startswith("/v1/requests/") and body is None:
            identifier = path[len("/v1/requests/"):]
            tool = STATUS_TOOL
            for suffix, selected in (("/effects", EFFECT_TOOL), ("/native", NATIVE_OBSERVATION_TOOL),
                                     ("/outcome", OUTCOME_TOOL), ("/response", RESPONSE_TOOL)):
                if identifier.endswith(suffix):
                    identifier, tool = identifier[:-len(suffix)], selected
                    break
            _need(_ID.fullmatch(identifier), "Exact request ID required")
            return tool, {"request_id": identifier}, False
        raise ValueError("Unknown actual-owner /v1 route")

    @staticmethod
    def _reply(result=None, error=None, *, requested_policy=None):
        value = {"schema": "EU4ACTUALOWNERV1/1", "execution_policy": "unknown",
                 "submission_can_execute_real_game_actions": True,
                 "historical_holds_enforced": True, "runtime_verified": False,
                 "automatic_retry": False}
        if requested_policy is not None:
            value["requested_execution_policy"] = requested_policy  # Intent, never an execution receipt.
        if type(result) is dict:
            if type(result.get("execution_policy")) is str:
                value["execution_policy"] = result["execution_policy"]
            elif type(result.get("test_only")) is bool:
                value["execution_policy"] = "development_test_only" if result["test_only"] else "production"
            for name in ("test_only", "test_only_required"):
                if type(result.get(name)) is bool:
                    value[name] = result[name]
        if error is None:
            value["result"] = result
        else:
            value["error"] = {"type": type(error).__name__, "message": str(error)[:512]}
        return value

    @staticmethod
    def _requested_policy(tool):
        from .v32_diplomacy_tools_20261020 import SUBMIT_TOOL, PRODUCTION_SUBMIT_TOOL
        return ("production" if tool == PRODUCTION_SUBMIT_TOOL else
                "development_test_only" if tool == SUBMIT_TOOL else None)

    def _execute(self, tool, arguments, writes):
        self._current()
        _need(threading.get_ident() == self.thread, "Actual owner main thread required")
        from .v32_diplomacy_tools_20261020 import call_cold_product_api_tool
        result = call_cold_product_api_tool(self.product, {"operation": "api-tool", "name": tool,
            "arguments": arguments, "allow_writes": writes})
        code = 202 if writes and result.get("status") == "queued" else 200
        if result.get("status") in ("dispatch_unknown", "outcome_incomplete"):
            code = 409
        return code, self._reply(result, requested_policy=self._requested_policy(tool))

    def request(self, method, path, body=None):
        """Python clients may call here too; workers always use the main queue."""
        self._current()
        raw = json.dumps(body, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        _need(len(raw) <= 65536, "API body exceeds 64 KiB")
        body = json.loads(raw)  # Retain a caller-independent command copy.
        tool, arguments, writes = self._route(method, path, body)
        requested_policy = self._requested_policy(tool)
        if threading.get_ident() == self.thread:
            return self._execute(tool, arguments, writes)
        with self.lock:
            _need(len(self.jobs) < 2048, "Finite API operation capacity exhausted")
            number = len(self.jobs) + 1
            job = {"tool": tool, "arguments": arguments, "writes": writes,
                   "started": False, "cancelled": False, "done": threading.Event(), "returned": None, "error": None}
            self.jobs[number] = job  # Retain before enqueue/wait; no retry path.
            try:
                self.messages.put_nowait((True, json.dumps({"operation": _ENVELOPE, "ticket": number})))
            except queue.Full:
                job["cancelled"] = True
                return 503, dict(self._reply(requested_policy=requested_policy), adapter_ticket=number,
                                 execution="not_started", error={"type": "QueueFull"})
        if not job["done"].wait(65):
            with self.lock:
                if not job["done"].is_set():
                    if not job["started"]:
                        job["cancelled"] = True  # Prevent a late unstarted write after timeout.
                    return 504, dict(self._reply(requested_policy=requested_policy), adapter_ticket=number,
                                     execution="unknown" if job["started"] else "not_started")
        if job["error"] is not None:
            return 409, dict(self._reply(error=job["error"], requested_policy=requested_policy), adapter_ticket=number)
        return job["returned"]

    def _consume(self, number):
        self._current()
        _need(threading.get_ident() == self.thread and type(number) is int, "Actual queued owner callback required")
        with self.lock:
            job = self.jobs.get(number)
            _need(job is not None and not job["started"] and not job["done"].is_set(), "Missing/consumed API operation")
            if job["cancelled"]:
                job["done"].set()
                return {"adapter_ticket": number, "execution": "not_started", "automatic_retry": False}
            job["started"] = True
        try:
            job["returned"] = self._execute(job["tool"], job["arguments"], job["writes"])
        except BaseException as error:
            job["error"] = error  # Preserve the actual error; never retry the tool.
        finally:
            job["done"].set()
        return {"adapter_ticket": number, "owner_call_returned": True, "automatic_retry": False}


def _command(product, value):
    adapter = product._owner_v1_adapter
    if type(value) is dict and value.get("operation") == _ENVELOPE:
        _need(set(value) == {"operation", "ticket"}, "Exact internal API envelope required")
        return adapter._consume(value["ticket"])
    return adapter.old_command(value)


def install_once(product):
    """Attach to the existing letter HTTP listener and its actual command loop.

    POST /v1/prepare {request}; POST /v1/requests {request,ttl_ms,test_only:true,
    allow_writes:true}; POST /v1/production/requests {request,ttl_ms,allow_writes:true};
    GET /v1/requests/ID[/effects|/native|/outcome] observes either policy through the same owner.
    POST /v1/candidates {kind:"curia_controller",actor?:"PAP"} omits target and
    returns the current controller in candidates[].tag; other kinds keep actor/target.
    No implicit preparation,
    submission, reassessment or effect capture occurs during installation.
    """
    main = sys.modules.get("__main__")
    from .tools import ToolRegistry
    from .v32_diplomacy_tools_20261020 import (
        CAPABILITIES_TOOL, PREPARE_TOOL, SUBMIT_TOOL, STATUS_TOOL, EFFECT_TOOL, PRODUCTION_SUBMIT_TOOL,
        CANDIDATES_TOOL, REPLIES_CURRENT_TOOL, NATIVE_OBSERVATION_TOOL)
    _need(main is not None and Path(main.__file__).resolve() == ROOT / "work/product_cold_letters_20261022.py"
          and type(product) is main.ColdLettersProduct and any(p is product for p in main._RETAINED)
          and product.thread == threading.get_ident() and product.connected
          and not getattr(product, "_owner_v1_attempted", False) and product._api_tools_bound
          and type(product.api_tools) is ToolRegistry and product.owner._resident_publisher is not None
          and product.service is not None and product.service.httpd is not None
          and product.service.broker is product.broker and product.service.thread.is_alive(),
          "Actual connected original product/tools/publisher/listener required once")
    _need({CAPABILITIES_TOOL, PREPARE_TOOL, SUBMIT_TOOL, STATUS_TOOL, EFFECT_TOOL,
           PRODUCTION_SUBMIT_TOOL, CANDIDATES_TOOL, REPLIES_CURRENT_TOOL, NATIVE_OBSERVATION_TOOL} <= set(product.api_tools.names()),
          "First installation requires the complete original-owner tools; do not rebind an older live registry")
    frame, messages = sys._getframe(), None
    for _ in range(32):
        if frame is None:
            break
        if frame.f_code is main._keep_alive.__code__ and frame.f_locals.get("product") is product:
            messages = frame.f_locals.get("messages")
            break
        frame = frame.f_back
    _need(type(messages) is queue.Queue and messages.maxsize == 8,
          "Install from the actual original main command loop")
    product._owner_v1_attempted = True
    adapter = OwnerV1Adapter(product, messages)
    product._owner_v1_adapter = adapter
    _RETAINED.append(adapter)  # Old handler/command and every partial install stay retained.

    class Handler(adapter.old_handler):
        def _owner_v1(self, method):
            try:
                self._talk_guard(token=False)  # Existing loopback Host/Origin protections.
                body = None
                if method == "POST":
                    lengths = self.headers.get_all("Content-Length") or []
                    _need(len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit()
                          and 0 < int(lengths[0]) <= 65536, "One bounded Content-Length required")
                    body = self._talk_body()  # Existing exact/duplicate-key/UTF8 JSON parser.
                status, value = adapter.request(method, self.path, body)
                self._json(status, value)
            except Exception as error:
                self.close_connection = True
                self._json(getattr(error, "status", 400), adapter._reply(error=error))

        def do_GET(self):
            if urlsplit(self.path).path.startswith("/v1/"):
                return self._owner_v1("GET")
            return super().do_GET()

        def do_POST(self):
            if urlsplit(self.path).path.startswith("/v1/"):
                return self._owner_v1("POST")
            return super().do_POST()

    product.command = types.MethodType(_command, product)
    product.service.httpd.RequestHandlerClass = Handler
    adapter.installed = True
    return {"v1_adapter_installed": True, "port": product.service.port,
            "execution_policies": ["development_test_only", "production"],
            "production_interface_source_connected": True, "production_runtime_verified": False,
            "historical_holds_enforced": True,
            "requests_submitted": 0, "new_server_started": False, "automatic_retry": False}
