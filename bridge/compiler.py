"""Whitelist compiler for EU4 console ``run`` scripts.

Only fixed actions are accepted.  The compiler never interpolates a caller's
free-form value into an EU4 effect; the only dynamic text in output is a
validated request ID used in an idempotence flag and ACK line.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .protocol import ID_PATTERN


ALLOWED_ACTIONS = frozenset(
    {"snapshot", "lock_diplomacy", "unlock_diplomacy", "improve_relations", "declare_war"}
)
_REQUEST_KEYS = frozenset({"id", "request_id", "action", "target"})


class RequestError(ValueError):
    """Raised when an untrusted action request is outside the allow-list."""


def _request_id(value: Any) -> str:
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        raise RequestError(
            "request id must match [A-Za-z0-9_]{1,32}; "
            f"got {value!r}"
        )
    return value


@dataclass(frozen=True)
class ActionRequest:
    """A validated action request ready for fixed-template compilation."""

    request_id: str
    action: str
    target: str | None = None

    def __post_init__(self) -> None:
        """Keep direct dataclass construction as strict as JSON construction."""

        _request_id(self.request_id)
        if not isinstance(self.action, str) or self.action not in ALLOWED_ACTIONS:
            raise RequestError(f"unsupported action {self.action!r}")
        if self.target is not None and (
            not isinstance(self.target, str) or ID_PATTERN.fullmatch(self.target) is None
        ):
            raise RequestError(f"invalid target {self.target!r}")
        if self.action in ("improve_relations", "declare_war") and self.target != "ENG":
            raise RequestError(f"{self.action} is restricted to target ENG")
        if self.action not in ("improve_relations", "declare_war") and self.target not in (None, "FRA"):
            raise RequestError(f"{self.action} is restricted to target FRA")

    @property
    def id(self) -> str:
        return self.request_id

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ActionRequest":
        if not isinstance(raw, Mapping):
            raise RequestError("request must be a JSON object")
        unknown = set(raw) - _REQUEST_KEYS
        if unknown:
            raise RequestError(f"unknown request field(s): {sorted(unknown)!r}")

        has_id = "id" in raw
        has_request_id = "request_id" in raw
        if not has_id and not has_request_id:
            raise RequestError("request requires id or request_id")
        if has_id and has_request_id:
            first = _request_id(raw["id"])
            second = _request_id(raw["request_id"])
            if first != second:
                raise RequestError("id and request_id must match when both are present")
            request_id = first
        else:
            request_id = _request_id(raw["id"] if has_id else raw["request_id"])

        action = raw.get("action")
        if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
            raise RequestError(
                f"action must be one of {sorted(ALLOWED_ACTIONS)!r}; got {action!r}"
            )

        target = raw.get("target")
        if target is not None and (not isinstance(target, str) or ID_PATTERN.fullmatch(target) is None):
            raise RequestError(
                "target must match [A-Za-z0-9_]{1,32} when provided; "
                f"got {target!r}"
            )

        if action in ("improve_relations", "declare_war"):
            if target != "ENG":
                raise RequestError(f"{action} is restricted to target ENG")
        elif target not in (None, "FRA"):
            raise RequestError(f"{action} is restricted to target FRA")

        return cls(request_id, action, target)

    @classmethod
    def from_json(cls, value: str) -> "ActionRequest":
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as error:
            raise RequestError(f"invalid request JSON: {error.msg}") from error
        return cls.from_mapping(raw)


def _ack(request_id: str, status: str) -> str:
    # request_id has already been checked by ActionRequest.  Keep this helper
    # separate so every generated receipt has exactly the same framing.
    return f'log = "EU4LLM|ACK|{request_id}|{status}"'


def _guard_lines(request: ActionRequest) -> list[str]:
    lines = [
        "                tag = FRA",
        "                ai = yes",
        "                exists = yes",
    ]
    # A snapshot is read-only and intentionally repeatable.  Mutating actions
    # get a request flag so replaying the same run file is rejected.
    if request.action != "snapshot":
        lines.append(
            f"                NOT = {{ has_country_flag = llm_req_{request.request_id} }}"
        )
    if request.action in ("improve_relations", "declare_war"):
        # This is evaluated from FRA country scope, so it verifies the named
        # country without ever interpolating an arbitrary target into script.
        lines.extend(
            [
                "                ENG = {",
                "                    exists = yes",
                "                }",
            ]
        )
    if request.action == "declare_war":
        # Script effects use a separate native war action from v7's peace
        # wrapper. Never clear the lock, even as a retry on failure.
        lines.extend([
            "                is_subject = no",
            "                has_country_flag = llm_diplomacy_locked",
            "                NOT = { war_with = ENG }",
            "                NOT = { truce_with = ENG }",
            "                NOT = { alliance_with = ENG }",
            "                has_casus_belli = { type = cb_core target = ENG }",
            "                177 = { owned_by = ENG is_core = FRA }",
        ])
    return lines


def _action_effect(request: ActionRequest) -> list[str]:
    if request.action == "snapshot":
        source = Path(__file__).resolve().parents[1] / "mod/llm_bridge/common/scripted_effects/llm_bridge.txt"
        effect = source.read_text(encoding="utf-8")
        body = effect[effect.index("{") + 1:effect.rfind("}")]
        return ["            " + line.strip() for line in body.splitlines() if line.strip()]
    if request.action == "lock_diplomacy":
        return [
            f"            set_country_flag = llm_req_{request.request_id}",
            "            set_country_flag = llm_diplomacy_locked",
        ]
    if request.action == "unlock_diplomacy":
        return [
            f"            set_country_flag = llm_req_{request.request_id}",
            "            clr_country_flag = llm_diplomacy_locked",
        ]
    if request.action == "improve_relations":
        return [
            f"            set_country_flag = llm_req_{request.request_id}",
            "            add_opinion = {",
            "                who = ENG",
            "                modifier = llm_bridge_goodwill",
            "            }",
        ]
    if request.action == "declare_war":
        return [
            f'            log = "EU4LLM_DIAG|{request.request_id}|locked_war_effect_entered"',
            "            declare_war_with_cb = { who = ENG casus_belli = cb_core war_goal_province = 177 }",
        ]
    # ActionRequest prevents reaching this branch.  Keeping an explicit
    # exception makes future additions fail closed if the allow-list changes.
    raise RequestError(f"unsupported action {request.action!r}")


def compile_request(request: ActionRequest | Mapping[str, Any] | str) -> str:
    """Compile one validated request into a deterministic EU4 run fragment.

    ``str`` input is treated as JSON for convenience.  A request is guarded
    by global ``exists = FRA`` and then executed in FRA scope.  Mutating
    actions set ``llm_req_<id>`` only in their applied branch, making replay of
    the same run file produce a rejected ACK rather than a duplicate effect.
    """

    if isinstance(request, ActionRequest):
        validated = request
    elif isinstance(request, str):
        validated = ActionRequest.from_json(request)
    elif isinstance(request, Mapping):
        validated = ActionRequest.from_mapping(request)
    else:
        raise RequestError("request must be an ActionRequest, mapping, or JSON string")

    guard = _guard_lines(validated)
    postconditions = {
        "lock_diplomacy": "has_country_flag = llm_diplomacy_locked",
        "unlock_diplomacy": "NOT = { has_country_flag = llm_diplomacy_locked }",
        "improve_relations": "has_opinion_modifier = { who = ENG modifier = llm_bridge_goodwill }",
        "declare_war": "war_with = ENG has_country_flag = llm_diplomacy_locked ai = yes",
    }
    receipt = [f"            {_ack(validated.request_id, 'applied')}"]
    if validated.action in postconditions:
        receipt = [
            "            if = {",
            f"                limit = {{ {postconditions[validated.action]} }}",
            *([f"                set_country_flag = llm_req_{validated.request_id}"]
              if validated.action == "declare_war" else []),
            f"                {_ack(validated.request_id, 'applied')}",
            "            }",
            "            else = {",
            f"                {_ack(validated.request_id, 'rejected')}",
            "            }",
        ]
    lines = [
        "# Generated by EU4LLM bridge; fixed allow-list only.",
        "if = {",
        "    limit = {",
        "        exists = FRA",
        "    }",
        "    FRA = {",
        "        if = {",
        "            limit = {",
        *guard,
        "            }",
        *_action_effect(validated),
        *receipt,
        "        }",
        "        else = {",
        f"            {_ack(validated.request_id, 'rejected')}",
        "        }",
        "    }",
        "}",
        "else = {",
        f"    {_ack(validated.request_id, 'rejected')}",
        "}",
    ]
    return "\n".join(lines) + "\n"


def _normalise_requests(
    requests: ActionRequest | Mapping[str, Any] | Sequence[Mapping[str, Any]] | str,
) -> list[ActionRequest]:
    if isinstance(requests, ActionRequest):
        return [requests]
    if isinstance(requests, str):
        try:
            decoded = json.loads(requests)
        except json.JSONDecodeError as error:
            raise RequestError(f"invalid request JSON: {error.msg}") from error
    else:
        decoded = requests

    if isinstance(decoded, Mapping):
        return [ActionRequest.from_mapping(decoded)]
    if isinstance(decoded, Sequence) and not isinstance(decoded, (str, bytes, bytearray)):
        result = [
            item if isinstance(item, ActionRequest) else ActionRequest.from_mapping(item)
            for item in decoded
        ]
        if not result:
            raise RequestError("request list must not be empty")
        return result
    raise RequestError("JSON input must be one request object or a non-empty list")


def compile_requests(
    requests: ActionRequest | Mapping[str, Any] | Sequence[Mapping[str, Any]] | str,
) -> str:
    """Compile one request or a JSON list of requests into one run file."""

    validated = _normalise_requests(requests)
    return "\n".join(compile_request(request).rstrip("\n") for request in validated) + "\n"


def compile_json_file(input_path: str | Path, output_path: str | Path) -> list[ActionRequest]:
    """Compile JSON requests and write a UTF-8 run file."""

    input_file = Path(input_path)
    output_file = Path(output_path)
    raw = input_file.read_text(encoding="utf-8")
    requests = _normalise_requests(raw)
    output_file.write_text(compile_requests(requests), encoding="utf-8", newline="\n")
    return requests

