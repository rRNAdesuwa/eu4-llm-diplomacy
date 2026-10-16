"""Offline, pinned typed bindings. There is deliberately no execution adapter.

Use ContractCatalog.describe/validate/request. Construction verifies small fixed
source artifacts; neither construction nor request opens SQLite or a process.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from . import diplomacy_api as api
from .diplomacy_api import APIError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROTOCOL = "EU4DIPLOMACY-CONTRACT/2"
PIN_SHA = "48572e9f6f1a82f8c4e9346a47ac387af66eff3e6350c0a6e3892586ca8b1818"
BINDING_SHA = "c948b1183ac56af06ec5d0837f9d6dfaa9340649be253d9812c5431b183ec80c"
MAX_SOURCE = 2 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_INPUTS = 64
MAX_REQUEST = 16 * 1024
MAPPING_FIELDS = ("native_mapping", "native_subject_mapping", "native_special_mapping", "native_peace_mapping")


class ContractError(APIError):
    def __init__(self, code, message):
        status = 404 if code == "unknown_action" else (413 if code == "request_budget" else
                 (500 if code in {"source_mismatch", "input_budget", "invalid_contract"} else
                  (422 if code in {"invalid_parameters", "unsupported_schema"} else 400)))
        super().__init__(code, message, status)


def require(condition, message, code="invalid_contract"):
    if not condition:
        raise ContractError(code, message)


def read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, f"File exceeds {limit} byte budget: {path.name}", "input_budget")
    return data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "Duplicate JSON key", "invalid_json")
            out[key] = value
        return out
    def invalid(value):
        raise ContractError("invalid_json", "Non-finite JSON constant")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("invalid_json", "Invalid UTF-8 JSON") from exc


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def request_tree(value):
    """Bound in-memory callers too, before encoding or recursive schema work."""
    count = 0
    def walk(item, depth):
        nonlocal count
        count += 1
        require(depth <= 8 and count <= 128, "Request nesting/node budget exceeded", "request_budget")
        kind = type(item)
        require(kind in (dict, list, str, int, float, bool, type(None)), "Non-JSON Python value", "invalid_parameters")
        if kind is dict:
            require(len(item) <= 32, "Object key budget exceeded", "request_budget")
            for key, child in item.items():
                require(type(key) is str and len(key) <= 128, "Invalid JSON object key", "invalid_parameters")
                walk(child, depth + 1)
        elif kind is list:
            require(len(item) <= 64, "Array budget exceeded", "request_budget")
            for child in item:
                walk(child, depth + 1)
        elif kind is str:
            require(len(item) <= 4096, "String budget exceeded", "request_budget")
        elif kind is int:
            require(item.bit_length() <= 256, "Integer budget exceeded", "request_budget")
    walk(value, 0)
    try:
        data = canonical(value)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("invalid_parameters", "Non-finite or invalid text value") from exc
    require(len(data) <= MAX_REQUEST, "Encoded request budget exceeded", "request_budget")
    return data


class ContractCatalog:
    def __init__(self, root: Path | None = None):
        # root is a repository location, never a native process or caller-supplied
        # evidence directory. Every accepted artifact has a compiled-in pin.
        self.root = Path(ROOT if root is None else root).resolve()
        pin_bytes = read_bounded(HERE / "diplomacy_contract_v2_pins.json", 64 * 1024)
        binding_bytes = read_bounded(HERE / "diplomacy_contract_v2_bindings.json", 128 * 1024)
        require(digest(pin_bytes) == PIN_SHA and digest(binding_bytes) == BINDING_SHA,
                "Candidate pin/binding artifact changed", "source_mismatch")
        self._pins = strict_json(pin_bytes)
        self._bindings = strict_json(binding_bytes)
        require(type(self._pins) is dict and 1 <= len(self._pins) <= MAX_INPUTS, "Input inventory budget")
        retained = {}
        total = 0
        for name, pin in self._pins.items():
            require(type(name) is str and not Path(name).is_absolute() and ".." not in Path(name).parts,
                    "Non-relative source path")
            path = (self.root / name).resolve()
            require(path.is_relative_to(self.root), "Source escaped repository")
            require(type(pin) is dict and set(pin) == {"bytes", "sha256"} and
                    type(pin["bytes"]) is int and 0 <= pin["bytes"] <= MAX_SOURCE, "Invalid source descriptor")
            data = read_bounded(path, pin["bytes"])
            total += len(data)
            require(total <= MAX_TOTAL, "Aggregate source budget", "input_budget")
            require(len(data) == pin["bytes"] and digest(data) == pin["sha256"],
                    f"Pinned source changed: {name}", "source_mismatch")
            # Only these verified bytes are used; reports are not kept in memory.
            if name == "bridge/diplomacy_catalog.json":
                retained[name] = data
        self.verified_source_bytes = total
        self._api = api  # Definitions only: never instantiate the durable V1 API.
        catalog = strict_json(retained["bridge/diplomacy_catalog.json"])
        require(catalog.get("schema_version") == 1 and len(catalog["actions"]) == 274, "Unexpected base catalog")
        self._catalog_build = catalog["game_build"]
        self._actions = {a["action_id"]: a for a in catalog["actions"]}
        require(len(self._actions) == 274 and set(self._bindings["actions"]) <= set(self._actions), "Action inventory differs")

    def _entry(self, action):
        require(type(action) is str and action in self._actions, "Unknown action", "unknown_action")
        return self._actions[action]

    def _schema(self, action):
        schema = deepcopy(self._entry(action)["parameters"])
        if action == "steal_maps":
            del schema["properties"]["region_id"]
            schema["properties"]["region_index"] = {"type": "integer", "minimum": 0, "maximum": 2147483647,
                "description": "Serialized native region index; live membership/type/lifetime remain unresolved."}
            schema["required"] = ["actor", "target", "region_index"]
        elif action == "support_rebels":
            del schema["properties"]["rebel_faction_id"]
            u32 = {"type": "integer", "minimum": 0, "maximum": 4294967295}
            schema["properties"]["faction_identity"] = {"type": "object",
                "properties": {"low": deepcopy(u32), "high": deepcopy(u32)},
                "required": ["low", "high"], "additionalProperties": False,
                "description": "Serialized DWORDs at faction +10 and +14, not pointer/lifetime authority."}
            schema["required"] = ["actor", "target", "faction_identity"]
        return schema

    def describe(self, action=None):
        if action is None:
            return {"protocol": PROTOCOL, "catalog_actions": len(self._actions),
                    "static_mapped": sum(any(k in a for k in MAPPING_FIELDS) for a in self._actions.values()),
                    "typed_binding_extensions": len(self._bindings["actions"]),
                    "schema_migrations": ["steal_maps", "support_rebels"],
                    "actions": [{"action": k, "typed_extension": k in self._bindings["actions"],
                                 "production_supported": False} for k in sorted(self._actions)],
                    "production_supported": False, "native_ready": False, "live_readiness": None,
                    "production_executable_actions": 0, "evidence_read_only": True,
                    "static_catalog_build": deepcopy(self._catalog_build), "live_build_inspected": False,
                    "limits": {"request_bytes": MAX_REQUEST, "source_count": MAX_INPUTS,
                               "source_bytes": MAX_SOURCE, "total_source_bytes": MAX_TOTAL}}
        entry = self._entry(action)
        ext = self._bindings["actions"].get(action)
        sources = (ext or {}).get("evidence", [])
        common = deepcopy(self._bindings["common_blockers"])
        return {"protocol": PROTOCOL, "action": action, "name_zh": entry["name_zh"],
                "static_catalog_build": deepcopy(self._catalog_build), "live_build_inspected": False,
                "surface": entry["surface"], "parameters": self._schema(action),
                "legacy_parameters": deepcopy(entry["parameters"]),
                "legacy_parameter_status": entry["parameter_status"],
                "parameter_validation": "structural_only", "native_binding_complete": False,
                "static_mapping_kinds": [k for k in MAPPING_FIELDS if k in entry],
                "binding": deepcopy(ext),
                "source_evidence": [{"path": p, **self._pins[p]} for p in sources],
                "catalog_evidence": deepcopy(self._pins["bridge/diplomacy_catalog.json"]),
                "readiness": {"source_mock_only": bool(ext and ext.get("source_mock_profile")),
                              "live_readiness": None, "native_ready": False,
                              "production_supported": False, "runtime_binding_verified": False,
                              "legality": None, "ai_acceptance": None, "effect": None,
                              "blockers": common + (deepcopy(ext["unresolved"]) if ext else
                                  ["No additional typed live binding in this isolated extension"])}}

    def decode(self, payload: bytes):
        require(type(payload) is bytes, "Wire input must be bytes", "invalid_json")
        require(len(payload) <= MAX_REQUEST, "Wire request budget exceeded", "request_budget")
        try:
            text = payload.decode("utf-8")
        except UnicodeError as exc:
            raise ContractError("invalid_json", "Wire request must be UTF-8") from exc
        result = strict_json(text)
        self.validate(result)
        return result

    def validate(self, payload):
        encoded = request_tree(payload)
        # All subsequent validation uses the canonical snapshot. A mutable
        # caller dictionary cannot change a binding after its digest is fixed.
        payload = strict_json(encoded)
        require(type(payload) is dict and set(payload) == {"protocol", "request_id", "action", "parameters"},
                "Request requires exactly protocol/request_id/action/parameters", "invalid_request")
        require(payload["protocol"] == PROTOCOL, "Explicit candidate protocol version required", "protocol_version")
        require(type(payload["request_id"]) is str and self._api.REQUEST_ID.fullmatch(payload["request_id"]) is not None,
                "Invalid request_id", "invalid_request")
        self._entry(payload["action"])
        try:
            self._api.validate_value(payload["parameters"], self._schema(payload["action"]))
        except self._api.APIError as exc:
            raise ContractError(exc.code, str(exc)) from exc
        return {"schema_valid": True, "protocol": PROTOCOL, "request_sha256": digest(encoded),
                "canonical_request": encoded.decode("ascii"), "native_binding_resolved": False,
                "native_legality": None, "production_supported": False}

    def _symbolic(self, action, parameters):
        ext = self._bindings["actions"].get(action)
        if ext is None:
            return None
        result = {"kind": ext["binding_kind"], "native_token": ext["native_token"],
                  "fixed_fields": deepcopy(ext["fixed_fields"]), "resolved": False}
        if ext["binding_kind"] == "unsupported_false_mode":
            result["fixed_fields"] = None
        elif action == "subject.set_military_focus":
            result["focus_enum"] = ext["enum_binding"][parameters["focus"]]
        elif ext["binding_kind"] == "desired_state_subject_command":
            result.update(desired_enabled=parameters["enabled"], current_enabled=None, cancel=None,
                          decision="requires_authenticated_current_state", flag_mask=ext["flag_mask"])
        elif action == "steal_maps":
            result["region_index"] = parameters["region_index"]
        elif action == "support_rebels":
            result.update(faction_identity=deepcopy(parameters["faction_identity"]), faction_resolved=False)
        return result

    def request(self, payload):
        validated = self.validate(payload)
        payload = strict_json(validated["canonical_request"])
        action = payload["action"]
        return {"protocol": PROTOCOL, "request_id": payload["request_id"], "action": action,
                "request_sha256": validated["request_sha256"], "canonical_request": validated["canonical_request"],
                "status": "unsupported", "reason": "No executable adapter; structural request draft only",
                "draft_only": True, "parameters": deepcopy(payload["parameters"]),
                "request_written": False, "native_called": False, "queued": False,
                "idempotency_scope": "not_reserved_contract_only", "production_supported": False,
                "symbolic_binding": self._symbolic(action, payload["parameters"]),
                "blockers": self.describe(action)["readiness"]["blockers"]}
