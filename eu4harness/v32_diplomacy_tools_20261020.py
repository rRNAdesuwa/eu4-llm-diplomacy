"""Explicit tool registration for one retained V32 owner.

Import is inert. The default harness registry explicitly registers cached
capabilities through this module; the recovery service does not import it.
It constructs no backend, session, owner, scope, runtime or loader. Bound
submit/status registration still requires the explicit coordinator's owner.
"""
from __future__ import annotations

import threading


CAPABILITIES_TOOL = "diplomacy_capabilities_v32"
STATUS_TOOL = "diplomacy_status_v32"
SUBMIT_TOOL = "diplomacy_submit_v32"
PRODUCTION_SUBMIT_TOOL = "diplomacy_submit_production_v32"
PREPARE_TOOL = "diplomacy_prepare_effect_v32"
EFFECT_TOOL = "diplomacy_effect_v32"
OUTCOME_TOOL = "diplomacy_outcome_v32"
CANDIDATES_TOOL = "diplomacy_candidates_v32"
REPLIES_CURRENT_TOOL = "diplomacy_replies_current_v32"
NATIVE_OBSERVATION_TOOL = "diplomacy_native_observation_v32"
PEACE_PREVIEW_TOOL = "diplomacy_peace_preview_v32"
ACTION_CATALOG_TOOL = "diplomacy_actions_v32"
QUERY_TOOL = "diplomacy_query_v32"
PREVIEW_TOOL = "diplomacy_preview_v32"
RESPONSE_TOOL = "diplomacy_response_v32"
_IDENTITY_FIELDS = ("pid", "creation", "session", "dll_sha256", "manifest_sha256")
_RETAINED_FIELDS = ("_backend", "_runtime", "_policy", "_context", "_api")


def build_connects_no_send(backend):
    """Read the loaded build's explicit send=0 flag; no hash or native call."""
    from pathlib import Path
    import json
    manifest = Path(backend.build) / "build.json"
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return document.get("no_send") is True


def _effect_tool_result(result):
    """The observer retains raw evidence; the LLM needs outcomes and its path."""
    output = dict(result)
    capture = output.pop('capture', None)
    if isinstance(capture, dict):
        output['capture_summary'] = {key: capture[key] for key in (
            'schema', 'captured_utc', 'two_pass_equal', 'duration_ms', 'rpm_budget',
            'native_calls', 'memory_written', 'requests_published',
            'atomic_main_thread_snapshot', 'world_epoch_proven', 'limitations') if key in capture}
        output['capture_evidence'] = None if result.get('record_failure') else result.get('record')
    return output


def _identity_signature(value):
    if type(value) is not dict or set(value) != set(_IDENTITY_FIELDS):
        return None
    return tuple((key, type(value[key]), value[key]) for key in _IDENTITY_FIELDS)


def register_v32_tools(registry, *, owner=None, observer=None):
    """Register source discovery, plus submit/status only for an actual owner.

    Use an existing exact ToolRegistry. An owner must have completed bind_once
    on this same coordinator thread; its explicit current-session producer is
    still external. With owner=None only the cached, source-only capabilities
    tool is installed. No unbound owner is silently ignored or auto-bound.

    Calls must use ToolRegistry.call. Its existing operator allow_writes gate
    protects the write tool before the handler runs. Direct invocation of a
    Tool.handler is an internal Python API, not a policy-aware dispatch path.
    Registration and every bound handler run on the original owner thread;
    this helper provides no hidden cross-thread queue or automatic retry.
    """
    # Lazy imports keep this new module inert and independent of a backend's
    # candidate imports. ToolRegistry's existing modules are not changed.
    from .tools import DANGER_READ, DANGER_WRITE, Tool, ToolDenied, ToolError, ToolRegistry

    if type(registry) is not ToolRegistry:
        raise ToolError("An actual ToolRegistry instance is required")

    retained = None
    signature = None
    bound_thread = None
    if owner is not None:
        from .v32_diplomacy_dispatch_20261019 import V32DiplomacyDispatch
        if type(owner) is not V32DiplomacyDispatch:
            raise ToolDenied("Only the exact retained V32DiplomacyDispatch owner is accepted")
        bound_thread = threading.get_ident()
        signature = _identity_signature(owner._identity)
        retained = tuple(getattr(owner, name) for name in _RETAINED_FIELDS)
        if (owner._owner != bound_thread or owner._invalidated or owner._audit is None
                or signature is None or any(value is None for value in retained)):
            raise ToolDenied("Bind the actual owner on this coordinator thread before registration")

    def same_observer():
        from pathlib import Path
        from bridge import diplomacy_effect_observer as effects
        actual = same_owner()
        if (Path(effects.__file__).resolve() != effects.ROOT / "bridge/diplomacy_effect_observer.py"
                or type(observer) is not effects.EffectObserver
                or observer.backend is not actual._backend or observer._status_owner is not actual
                or _identity_signature(observer.identity) != signature
                or observer.capture_factory is not effects.RuntimeCapture
                or observer.prepare.__func__ is not effects.EffectObserver.prepare
                or observer.observe.__func__ is not effects.EffectObserver.observe):
            raise ToolDenied("The actual same-owner effect observer is required")
        confirmed, _, _ = observer._current_status_owner()
        if confirmed is not actual:
            raise ToolDenied("Effect observation belongs to another owner")
        return observer

    names = ((CAPABILITIES_TOOL,) if owner is None else
             (CAPABILITIES_TOOL, STATUS_TOOL, SUBMIT_TOOL))
    if observer is not None:
        if owner is None:
            raise ToolDenied("An effect observer requires its retained owner")
        names += (PREPARE_TOOL, EFFECT_TOOL, OUTCOME_TOOL, CANDIDATES_TOOL, REPLIES_CURRENT_TOOL)
    if owner is not None:
        names += (PRODUCTION_SUBMIT_TOOL, NATIVE_OBSERVATION_TOOL, PEACE_PREVIEW_TOOL,
                  ACTION_CATALOG_TOOL, QUERY_TOOL, PREVIEW_TOOL, RESPONSE_TOOL)
    # ToolRegistry.register normally replaces a same-name tool. This extension
    # refuses the whole registration before writing anything if names collide.
    existing = set(registry.names())
    if existing.intersection(names):
        raise ToolError("V32 tool names already exist; never replace legacy or installed handlers")

    def exact_arguments(arguments, fields):
        if type(arguments) is not dict or set(arguments) != fields:
            raise ToolError("Exact V32 tool argument fields are required")

    def same_owner():
        # These are retained references from an already completed bind, not
        # caller-provided loaded/ready/verified booleans. The owner's methods
        # still enforce their actual V4/history/runtime/publication contracts.
        if (threading.get_ident() != bound_thread or owner._owner != bound_thread
                or _identity_signature(owner._identity) != signature
                or any(getattr(owner, name) is not value
                       for name, value in zip(_RETAINED_FIELDS, retained))):
            raise ToolDenied("The retained V32 owner/thread/session binding changed")
        return owner

    if observer is not None:
        same_observer()  # Pure provenance only; no capture, status or publication.

    def capabilities(arguments):
        from bridge.demo_war_peace import catalog as demo_catalog
        exact_arguments(arguments, set())
        if owner is None:
            value = {
                "source_routes": {"top_level": 214, "nested_peace": 54, "total": 268,
                                  "runtime_verified": False},
                "bound": False, "eligible_scope_ids": [], "historical_scope_ids": [],
                "runtime_ready": False, "live_readiness_checked": False,
                "gameplay_effects_verified": False, "automatic_retry": False,
                "test_only_required": True, "module_provides_session_producer": False,
                "requires_actual_current_session_producer": True,
                "blocked_reason": "No actual retained V32 dispatch owner was supplied",
                "recipient_response": "unknown", "effect": "unknown", "completion": "unknown",
            }
        else:
            value = same_owner().capabilities()  # Cached; no backend status/verify call.
        return dict(value, tool_schema="EU4HARNESSV32TOOLS/1", demo_scope=demo_catalog(),
                    registered_tools=list(getattr(owner, "_registered_v32_tools", names)),
                    submit_registered=owner is not None, status_registered=owner is not None,
                    production_submit_registered=owner is not None,
                    native_observation_registered=owner is not None,
                    production_interface_source_connected=owner is not None,
                    production_write_permission_checked=False, production_runtime_verified=False,
                    test_only_required_applies_to="development_submit",
                    operator_allow_writes_required=True,
                    executable_actions_implied_by_source_count=False,
                    legacy_catalog_and_preflight_unchanged=True)

    def submit(arguments):
        exact_arguments(arguments, {"request", "ttl_ms", "test_only"})
        if (arguments["test_only"] is not True or type(arguments["ttl_ms"]) is not int
                or not 1 <= arguments["ttl_ms"] <= 60000):
            raise ToolError("Explicit test_only=True and integer TTL1..60000 are required")
        # No normalizer, alias, TAG inference, legacy preflight, save-memory
        # note or fallback occurs between this call and the reviewed owner.
        # Scope/policy errors and Unknown DTOs propagate without reclassification.
        return same_owner().submit(arguments["request"], ttl_ms=arguments["ttl_ms"], test_only=True)

    def submit_production(arguments):
        exact_arguments(arguments, {"request", "ttl_ms"})
        if type(arguments["ttl_ms"]) is not int or not 1 <= arguments["ttl_ms"] <= 60000:
            raise ToolError("Production submit requires integer TTL1..60000")
        # The caller must use ToolRegistry.call(..., allow_writes=True).
        # This original owner enforces the distinct production policy itself.
        return same_owner().submit_production(arguments["request"], ttl_ms=arguments["ttl_ms"])

    def status(arguments):
        exact_arguments(arguments, {"request_id"})
        return same_owner().status(arguments["request_id"])

    def action_catalog(arguments):
        from bridge.diplomacy_operations import catalog
        if type(arguments) is not dict or set(arguments) - {"action", "category"}:
            raise ToolError("Expected optional action and category")
        if any(type(value) is not str for value in arguments.values()):
            raise ToolError("Action and category must be strings")
        return catalog(same_owner()._api, **arguments)

    def query_action(arguments):
        from bridge.diplomacy_operations import query
        exact_arguments(arguments, {"request"})
        return query(same_owner()._api, arguments["request"])

    def _require_native_no_send():
        # The source contract names actions with a send=0 form; the loaded build
        # must also advertise that channel. Publishing check_only through a
        # build without it becomes an unknown owner outcome.
        if not build_connects_no_send(same_owner()._backend):
            raise ToolError("Loaded native build does not connect send=0 preview; use parameter query and native checks during execution")
    def preview_action(arguments):
        from bridge.v32_native_preflight_20261025 import request as no_send
        exact_arguments(arguments, {"request", "ttl_ms"})
        inspected = query_action({"request": arguments["request"]})
        if not inspected["contract"]["native_preview"]:
            raise ToolError("This typed route supports parameter query and native checks during execution")
        _require_native_no_send()
        return submit({"request": no_send(inspected["request"]),
                       "ttl_ms": arguments["ttl_ms"], "test_only": True})

    def response_action(arguments):
        from bridge.diplomacy_operations import response
        exact_arguments(arguments, {"request_id"})
        return response(native_observation(arguments))

    def peace_preview(arguments):
        exact_arguments(arguments, {"request", "ttl_ms"})
        from bridge.v32_native_preflight_20261025 import request as no_send
        from bridge.demo_war_peace import validate_scope
        request = arguments["request"]
        if type(request) is not dict or request.get("action") != "offer_peace":
            raise ToolError("Preview requires an explicit offer_peace request")
        validate_scope(request)
        _require_native_no_send()
        return submit({"request": no_send(request), "ttl_ms": arguments["ttl_ms"], "test_only": True})

    def native_observation(arguments):
        exact_arguments(arguments, {"request_id"})
        actual = same_owner()
        result = actual.observe_native(arguments["request_id"])
        if result.get("status") != "native_observation":
            return result
        value = result["observation"]  # Already saved in full by the real owner.
        summary = {key: value[key] for key in (
            "found", "source_current_begin", "source_current_end", "source_ordinal_begin", "source_ordinal_end",
            "stopped", "revoked", "fault", "factory_unknown", "parser_unknown", "async_unknown",
            "acceptance", "effect_completion")}
        summary.update(schema="EU4NATIVELIFECYCLESUMMARY/5", native_schema=value["schema"], factories=[])
        if value["submit"] is not None:
            fields = {
                "parser": ("parsed_completion", "command4c", "normal_return", "unwound", "unknown", "fault"),
                "execute": ("entry_verified", "completion_verified", "command4c", "normal_return", "unwound", "unknown", "fault"),
                "pending": ("committed", "pending3c", "unknown", "fault"),
                "reply": ("matched_candidate", "reply_command4c", "d_state", "lookup_closed", "lookup_normal",
                          "unknown", "fault", "allocation_lifetime", "payload_provenance"),
                "generated_send": ("pre_verified", "call_observed", "normal_return_observed", "container_empty", "post_verified",
                                   "parent_closed", "parent_unwound", "unknown", "fault", "transport_enqueue", "reply_execution", "allocation_lifetime"),
                "decision": ("pre_verified", "clone_verified", "decision_observed", "decision_state", "generated_decision",
                             "reply_delivery", "full_payload", "unknown", "fault"),
                "effect": ("generated_lineage", "pre_verified", "apply_call_observed", "apply_normal_return_observed",
                           "normal_return", "unwound", "unknown", "fault", "request_association"),
            }
            for factory in value["submit"]["factories"]:
                if factory["reserved"]:
                    row = {key: factory[key] for key in ("slot_index", "generated_reply", "origin_parent_slot",
                        "origin_execute_activation", "origin_ni_generation", "origin_send_ordinal")}
                    row.update({phase: {key: factory[phase][key] for key in keys}
                                for phase, keys in fields.items()})
                    row["payload"] = {phase: {key: capture[key] for key in (
                        "attempted", "fields_complete", "fields_equal", "verified_match", "unknown", "fault")}
                        for phase, capture in factory["payload"].items()}
                    summary["factories"].append(row)
        # Keep raw slots and unused records out of LLM/HTTP output. The full
        # owner receipt and original authenticated bytes stay retained on E.
        return dict({key: item for key, item in result.items() if key != "observation"},
                    observation_summary=summary,
                    observation_evidence=str(actual._output / ("op-" + result["op_id"] + ".native-observation.json")))

    def prepare_effect(arguments):
        scope_field = "peace_preflight_request_id"
        scoped = type(arguments) is dict and scope_field in arguments
        exact_arguments(arguments, {"request", scope_field} if scoped else {"request"})
        current = same_observer()
        from .v32_diplomacy_dispatch_20261019 import _request
        request = _request(arguments["request"])
        actual = same_owner()
        if request["request_id"] in actual._attempts or request["request_id"] in actual._protected:
            raise ToolDenied("An attempted or protected ID cannot acquire a new before baseline")
        _, _, native = current._current_status_owner()
        command = native.validate_command(actual._api._command(request), actual._backend.actions)
        if scoped:
            identifier = arguments[scope_field]
            if command['action'] != 'offer_peace' or type(identifier) is not str or not identifier:
                raise ToolDenied("Peace scope requires the ID of an existing no-send peace check")
            return current.prepare(command, peace_preflight_request_id=identifier)
        return current.prepare(command)

    def effect(arguments):
        exact_arguments(arguments, {"request_id"})
        return _effect_tool_result(same_observer().observe(arguments["request_id"]))

    def outcome(arguments):
        exact_arguments(arguments, {"request_id"})
        from .v32_diplomacy_dispatch_20261019 import _request, _require, _json_copy, _MAX_RECEIPT
        from .v32_diplomacy_outcome_20261024 import collect_outcome
        actual, current = same_owner(), same_observer()
        actual._enter()
        try:
            identifier = arguments["request_id"]
            _require(type(identifier) is str and identifier in actual._attempts
                     and identifier not in actual._protected, "Original attempted request required")
            attempt = actual._attempts[identifier]
            _require(not attempt.get("denied"), "Denied request has no outcome observation")
            request = _request(attempt["request"])
            publication = attempt.get("publication")
            _require(type(publication) is dict and publication.get("status") == "queued",
                     "Original queued publication required")
            _, _, native = current._current_status_owner()
            command = native.validate_command(actual._api._command(request), actual._backend.actions)
            policy = "production" if attempt.get("test_only") is False else "development_test_only"
            op_id = actual._op("outcome")
            actual._intent(op_id, "outcome", request_id=identifier,
                           sequence=publication["sequence"], original_operation_id=publication["op_id"])
        finally:
            actual._busy = False
        # Existing methods own their source checks and retained raw records.
        # Their terminal caches, holds and in-flight slots are not edited here.
        result = collect_outcome(identity=dict(actual._identity), request=request, command=command,
            publication=publication, execution_policy=policy,
            native_read=lambda: native_observation(arguments),
            effect_read=lambda: same_observer().observe(identifier))
        result["op_id"] = op_id
        result["outcome_evidence"] = str(actual._output / ("op-" + op_id + ".outcome.json"))
        actual._save("op-" + op_id + ".outcome.json", result)
        return _json_copy(result, _MAX_RECEIPT)[0]

    def candidates(arguments):
        if type(arguments) is dict and arguments.get("kind") == "curia_controller":
            exact_arguments(arguments, {"kind", "actor"} if "actor" in arguments else {"kind"})
            if arguments.get("actor", "PAP") != "PAP":
                raise ToolError("curia_controller scope actor must be PAP; omit target")
        else:
            exact_arguments(arguments, {"kind", "actor", "target"})
        from bridge.diplomacy_candidate_reader_20261022 import read_candidates
        return read_candidates(same_observer(), arguments["kind"], arguments.get("actor"), arguments.get("target"))

    def replies_current(arguments):
        exact_arguments(arguments, {"actor", "target"})
        from bridge.diplomacy_reply_reader_20261022 import read_current_replies
        return read_current_replies(same_observer(), arguments["actor"], arguments["target"])

    definitions = [Tool(
        name=CAPABILITIES_TOOL,
        description=("Cached V32 source routes and exact supplied owner's scope boundary. "
                     "Source route counts are not runtime-ready action counts. No live query or permission is granted."),
        parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        danger=DANGER_READ,
        handler=capabilities,
    )]
    if owner is not None:
        definitions.extend((Tool(
            name=STATUS_TOOL,
            description=("Observe only a new request attempted by the same retained V32 owner. "
                         "Terminal/unchanged observations are cached; old request IDs are rejected. "
                         "No recipient reply, applied effect or completion is implied."),
            parameters={"type": "object", "properties": {"request_id": {
                "type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,96}$"}},
                "required": ["request_id"], "additionalProperties": False},
            danger=DANGER_READ,
            handler=status,
        ), Tool(
            name=SUBMIT_TOOL,
            description=("One reviewed V32 development publication, test_only=True, through the same owner. "
                         "Requires operator writes and an actual current V4 scope/history join. "
                         "Queued/dispatched is not applied; Unknown stays held with no retry."),
            parameters={"type": "object", "properties": {
                "request": {"type": "object", "properties": {
                    "request_id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,96}$"},
                    "action": {"type": "string", "description": "Exact frozen canonical action; no legacy alias"},
                    "parameters": {"type": "object", "description": "Exact canonical per-family fields; no coercion"}},
                    "required": ["request_id", "action", "parameters"], "additionalProperties": False},
                "ttl_ms": {"type": "integer", "minimum": 1, "maximum": 60000},
                "test_only": {"type": "boolean", "enum": [True]}},
                "required": ["request", "ttl_ms", "test_only"], "additionalProperties": False},
            danger=DANGER_WRITE,
            handler=submit,
        )))
    if observer is not None:
        definitions.extend((Tool(
            name=PREPARE_TOOL,
            description=("Read and retain a before baseline for a new canonical request; does not submit it. "
                         "For native-derived peace countries, pass peace_preflight_request_id from an existing "
                         "successful no-send check of the same terms to capture their actual countries."),
            parameters={"type": "object", "properties": {"request": {"type": "object",
                "properties": {"request_id": {"type": "string"}, "action": {"type": "string"},
                               "parameters": {"type": "object"}},
                "required": ["request_id", "action", "parameters"], "additionalProperties": False},
                "peace_preflight_request_id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,96}$"}},
                "required": ["request"], "additionalProperties": False},
            danger=DANGER_READ, handler=prepare_effect,
        ), Tool(
            name=EFFECT_TOOL,
            description=("Read independent effects for this owner's attempted request; never retries dispatch. "
                         "Returns outcomes and capture metadata; the full memory snapshot remains in the local evidence record."),
            parameters={"type": "object", "properties": {"request_id": {"type": "string",
                "pattern": "^[A-Za-z0-9_.:-]{1,96}$"}}, "required": ["request_id"],
                "additionalProperties": False},
            danger=DANGER_READ, handler=effect,
        ), Tool(
            name=OUTCOME_TOOL,
            description=("Read native lifecycle and selected state once each for the same original request. "
                         "outcome_partial retains whichever read succeeded; observation_complete only means both reads succeeded. "
                         "progress mirrors the bound selected_state.completion_state even when native evidence is unavailable; "
                         "in_progress and selected_effect_observed do not establish full completion. "
                         "generated_decisions are not proof of delivery or recipient acceptance. "
                         "Retains separate evidence; no implicit baseline, retry, acceptance or causation claim."),
            parameters={"type": "object", "properties": {"request_id": {"type": "string",
                "pattern": "^[A-Za-z0-9_.:-]{1,96}$"}}, "required": ["request_id"],
                "additionalProperties": False},
            danger=DANGER_READ, handler=outcome,
        ), Tool(
            name=CANDIDATES_TOOL,
            description=("Read unit/rebel/province IDs, positive navy candidates, current wars or the current Curia controller. "
                         "For curia_controller, omit actor or use PAP as the religion scope and omit target; bind "
                         "call_crusade/excommunicate/lift_excommunication actor from candidates[0].tag, not from the scope. "
                         "An empty curia_controller list means no current controller; candidates do not establish legality or permission to submit."),
            parameters={"type": "object", "properties": {
                "kind": {"type": "string", "enum": ["units", "fleets", "wars", "casus_belli", "provinces", "rebel_factions", "curia_controller"]},
                "actor": {"type": "string", "pattern": "^[A-Z0-9]{3}$",
                          "description": "Required for pair kinds; omitted or PAP for curia_controller scope only."},
                "target": {"type": "string", "pattern": "^[A-Z0-9]{3}$",
                           "description": "Required for pair kinds; not applicable and must be omitted for curia_controller."}},
                "required": ["kind"], "additionalProperties": False,
                "oneOf": [
                    {"properties": {"kind": {"enum": ["curia_controller"]}, "actor": {"enum": ["PAP"]}},
                     "not": {"required": ["target"]}},
                    {"properties": {"kind": {"enum": ["units", "fleets", "wars", "casus_belli", "provinces", "rebel_factions"]}},
                     "required": ["actor", "target"]}]},
            danger=DANGER_READ, handler=candidates,
        ), Tool(
            name=REPLIES_CURRENT_TOOL,
            description=("Read the recipient's current typed diplomatic inbox for an exact country pair. "
                         "Raw native IDs and states do not prove a harness request's acceptance or rejection."),
            parameters={"type": "object", "properties": {
                "actor": {"type": "string", "pattern": "^[A-Z0-9]{3}$"},
                "target": {"type": "string", "pattern": "^[A-Z0-9]{3}$"}},
                "required": ["actor", "target"], "additionalProperties": False},
            danger=DANGER_READ, handler=replies_current,
        )))
    if owner is not None:
        definitions.extend((Tool(
            name=ACTION_CATALOG_TOOL,
            description="List action parameters, current-world prerequisites, candidate selectors and effect contracts.",
            parameters={"type": "object", "properties": {
                "action": {"type": "string"}, "category": {"type": "string"}},
                "additionalProperties": False}, danger=DANGER_READ, handler=action_catalog,
        ), Tool(
            name=QUERY_TOOL,
            description="Validate a canonical action request and return its source contract without publishing it.",
            parameters={"type": "object", "properties": {"request": {"type": "object"}},
                "required": ["request"], "additionalProperties": False},
            danger=DANGER_READ, handler=query_action,
        ), Tool(
            name=PREVIEW_TOOL,
            description="Run a native no-send preview for an ordinary diplomatic action or peace proposal. Read status with its fresh request ID.",
            parameters={"type": "object", "properties": {"request": {"type": "object"},
                "ttl_ms": {"type": "integer", "minimum": 1, "maximum": 60000}},
                "required": ["request", "ttl_ms"], "additionalProperties": False},
            danger=DANGER_WRITE, handler=preview_action,
        ), Tool(
            name=RESPONSE_TOOL,
            description="Read generated decisions, pending delivery, reply execution and application for one original request.",
            parameters={"type": "object", "properties": {"request_id": {"type": "string",
                "pattern": "^[A-Za-z0-9_.:-]{1,96}$"}}, "required": ["request_id"],
                "additionalProperties": False}, danger=DANGER_READ, handler=response_action,
        )))
        definitions.append(Tool(
            name=PEACE_PREVIEW_TOOL,
            description=("Preview one exact peace proposal without sending it. Use a fresh request_id. "
                         "Then read diplomacy_status_v32 for native_ready, reason, warscore_known and warscore. "
                         "Never infer availability from a queued preview. Submission uses another ID and rechecks "
                         "native conditions, a 100-point ceiling, and land border / at most 3 sea zones for territory."),
            parameters={"type": "object", "properties": {
                "request": {"type": "object"},
                "ttl_ms": {"type": "integer", "minimum": 1, "maximum": 60000}},
                "required": ["request", "ttl_ms"], "additionalProperties": False},
            danger=DANGER_WRITE, handler=peace_preview,
        ))
        definitions.append(Tool(
            name=PRODUCTION_SUBMIT_TOOL,
            description=("Submit one explicit production request through the same original owner. "
                         "Requires operator writes and actual production admission; historical and Unknown holds remain. "
                         "No retry or gameplay-effect guarantee is provided."),
            parameters={"type": "object", "properties": {
                "request": {"type": "object", "properties": {
                    "request_id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,96}$"},
                    "action": {"type": "string"}, "parameters": {"type": "object"}},
                    "required": ["request_id", "action", "parameters"], "additionalProperties": False},
                "ttl_ms": {"type": "integer", "minimum": 1, "maximum": 60000}},
                "required": ["request", "ttl_ms"], "additionalProperties": False},
            danger=DANGER_WRITE, handler=submit_production,
        ))
        definitions.append(Tool(
            name=NATIVE_OBSERVATION_TOOL,
            description=("Read one native lifecycle snapshot for this owner's original queued request ID. "
                         "Retains parser, pending, reply-candidate and Apply call facts separately. "
                         "No automatic polling, dispatch retry or acceptance/effect-completion inference."),
            parameters={"type": "object", "properties": {"request_id": {
                "type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,96}$"}},
                "required": ["request_id"], "additionalProperties": False},
            danger=DANGER_READ, handler=native_observation,
        ))
    # Single-threaded coordinator setup only. If registration itself raises,
    # leave the existing partial state intact; no removal/automatic retry path.
    for tool in definitions:
        registry.register(tool)
    return names


def bind_cold_product_api_tools_once(product):
    """Bind only the existing cold product's original owner; construction is inert."""
    from pathlib import Path
    import sys
    from .cold_source_identity_20261022 import cold_current
    from .tools import ToolRegistry
    from bridge.diplomacy_effect_observer import EffectObserver
    main = sys.modules.get("__main__")
    root = Path("E:/work/Programming/eullm")
    entry = Path(main.__file__).resolve() if main is not None and getattr(main, "__file__", None) else None
    cold_entry = (entry == root / "work/product_cold_letters_20261022.py"
                  and type(product) is getattr(main, "ColdLettersProduct", None))
    resumed_entry = (entry == root / "work/product_preserved_handover_letters_20261021.py"
                     and type(product) is getattr(main, "PreservedLettersProduct", None)
                     and (product.args.cold_launch or product.args.resume_unconnected))
    if (not (cold_entry or resumed_entry)
            or not any(item is product for item in main._RETAINED)
            or product.thread != threading.get_ident()
            or getattr(product, "_api_tools_attempted", False)
            or getattr(product, "effect_observer", None) is not None
            or getattr(product, "api_tools", None) is not None):
        raise RuntimeError("Only the original unbound cold product may bind API tools once")
    c = cold_current(product.source)
    if (product.ticket is not product.source._ticket or product.source._verified_backend is not product.backend
            or product.runtime is not product.backend.runtime or product.runtime._cold_current() is not c
            or product.handoff.connection is not c or product.handoff.owner is not product.owner
            or product.reader is not product.owner._resident_reader):
        raise RuntimeError("Actual cold source/backend/runtime/handoff/owner graph changed")
    product._api_tools_attempted = True
    product._api_tools_bound = False
    product.effect_observer = EffectObserver(dict(product.owner._identity),
        backend=product.backend, status_owner=product.owner)
    from bridge.diplomacy_reply_reader_20261022 import install_native_family_index_once
    with (root / "work/reports/native-diplomacy-1.37.5.json").open("rb") as inventory:
        install_native_family_index_once(inventory.read(2 * 1024 * 1024 + 1))
    product.api_tools = ToolRegistry()
    names = register_v32_tools(product.api_tools, owner=product.owner, observer=product.effect_observer)
    product.owner._registered_v32_tools = names
    product._api_tools_binding = (product.owner, product.backend, product.runtime,
                                 product.effect_observer, product.api_tools)
    product._api_tools_bound = True
    return {"api_tools_bound": True, "registered_tools": list(names), "automatic_retry": False,
            "requests_submitted": 0, "effect_captures": 0}


def call_cold_product_api_tool(product, value):
    """Explicit main-thread commands only; ToolRegistry retains its write gate."""
    from .tools import ToolRegistry
    if (not product.connected or product.thread != threading.get_ident()
            or not getattr(product, "_api_tools_bound", False)
            or type(product.api_tools) is not ToolRegistry
            or any(a is not b for a, b in zip(product._api_tools_binding,
                (product.owner, product.backend, product.runtime, product.effect_observer, product.api_tools)))
            or type(value) is not dict):
        raise RuntimeError("Actual connected original API owner required")
    operation = value.get("operation")
    if operation == "prepare" and set(value) == {"operation", "request"}:
        return product.api_tools.call(PREPARE_TOOL, {"request": value["request"]}, allow_writes=False)
    if operation == "effect" and set(value) == {"operation", "request_id"}:
        return product.api_tools.call(EFFECT_TOOL, {"request_id": value["request_id"]}, allow_writes=False)
    if (operation == "api-tool" and set(value) == {"operation", "name", "arguments", "allow_writes"}
            and type(value["name"]) is str and type(value["arguments"]) is dict
            and type(value["allow_writes"]) is bool):
        return product.api_tools.call(value["name"], value["arguments"], allow_writes=value["allow_writes"])
    raise RuntimeError("Exact explicit API tool command required")
