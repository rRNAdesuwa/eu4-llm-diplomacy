"""Safe, offline tooling for the EU4 LLM diplomacy bridge.

The package deliberately contains no game automation.  It only parses the
line protocol written to ``game.log`` and compiles a small, fixed action
allow-list to an EU4 ``run`` script.
"""

from .compiler import ALLOWED_ACTIONS, ActionRequest, RequestError, compile_request, compile_requests
from .planner import OpenAICompatiblePlanner, PlannerDisabledError, PlannerResponseError
from .protocol import (
    ACK_STATUSES,
    Ack,
    ParsedLog,
    ProtocolError,
    Snapshot,
    parse_file,
    parse_log,
)

__all__ = [
    "ACK_STATUSES",
    "ALLOWED_ACTIONS",
    "Ack",
    "ActionRequest",
    "ParsedLog",
    "OpenAICompatiblePlanner",
    "ProtocolError",
    "PlannerDisabledError",
    "PlannerResponseError",
    "RequestError",
    "Snapshot",
    "compile_request",
    "compile_requests",
    "parse_file",
    "parse_log",
]

