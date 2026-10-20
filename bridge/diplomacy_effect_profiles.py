"""Pure selected-effect predicates over normalized snapshots and an audit receipt.

No file, process, native-call, request, reservation or save API is imported.
Identity/pair comparisons associate a recorded dispatch with selected changes;
they do not prove an atomic world epoch, exclusive causality or persistence.
"""
from dataclasses import dataclass
import re

SCHEMA = "EU4DIPLOMACY-EFFECT/1"
GAME_SHA256 = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
SENTINEL = 0x2D2D2D
_MISSING = object()
_COMMON_FIELDS = ("identity.pid", "identity.creation", "pair.actor_tag", "pair.target_tag",
                  "pair.actor_handle", "pair.target_handle")
_RECEIPT_FIELDS = ("command.action", "command.actor", "command.target", "identity.pid", "identity.creation",
                   "binding.actor_handle", "binding.target_handle", "state", "native_result.status",
                   "native_result.submitted", "native_result.slot_consumed", "native_result.ownership_closed",
                   "native_result.owned_live", "native_result.quarantined", "native_result.adapter_fault",
                   "native_result.submit_exception")
_LIMITATIONS = (
    "Only the selected matched state change is assessed; exclusive request causality and complete effects are not proven.",
    "No saved-state persistence, cold reload, native legality or AI acceptance is established.",
    "Same PID/creation and complete country handles do not prove an atomic world epoch across an in-process reload.",
    "Transport ownership closure does not prove all local destructors ran; known_cleanup_complete is preserved separately.",
    "An observed effect never authorizes repeating a historical dispatched, successful or unknown action.",
)
_PIN_ROWS = (
    ("annex", "work/reports/diplomacy-corrective-20261014-r3/annex-checks-static.json", 121942,
     "dab770be9fab8171a6b95bb16b54dec0a1a9edb56d4f69768a3e67e37c46f28b", "ordinary_capstone_file_analysis"),
    ("annex_helpers", "work/reports/diplomacy-corrective-20261014-r3/annex-helpers-static.json", 179259,
     "246f12d6bd910bb38836069bc6601be0cd6b0088c8fd1e7dcdd4e2147d73377a", "ordinary_capstone_file_analysis"),
    ("coalition", "work/reports/diplomacy-corrective-20261014-r3/coalition-false-static.json", 66381,
     "76929550fd9d462bfc4304cb498dcbb1bf0847dcff3113e0dbc564e840cf4a0c", "ordinary_capstone_file_analysis"),
    ("request_roles", "work/reports/rea-api-discovery-20261013/conditions/findings.json", 12730,
     "8f1dfa84d3b9b1000a62873ed8afdcd866393d90a573b3bcd88b0bfd4ec9f7f9", "ordinary_capstone_findings"),
    ("four_effects", "work/reports/unified-validation-20261013/corrective-effect-evidence.json", 15637,
     "3e58954c3bb88291b4bb17566aeefecb8834678e35624fc0fd0a57c0d85f061e", "recorded_selected_effect_observations"),
    ("favor_march_effects", "work/reports/diplomacy-corrective-20261014/runtime-file-audit.json", 20468,
     "592b588e2cdcad6f430c27fe61f622d6d8f9a3956597bec47a3abb03e25546d8", "recorded_selected_effect_observations"),
    ("annex_coalition_effects", "work/reports/diplomacy-corrective-20261014-r3/first-two-runtime-file-audit.json", 55798,
     "1c3f75db827a3fd1317011012fb68f5b47f6eb97ca91d0ffbdd1bb073849a97a", "recorded_selected_effect_observations"),
    ("favor_native", "work/reports/native-pair29-favor-effects-1375.json", 603966,
     "62abf72b2c30e71a7157e5f1fe08c3e5d49f091cf9ac31f1b436e8c6f79604a9", "bounded_native_file_analysis"),
)


@dataclass(frozen=True)
class _Profile:
    action: str
    kind: str
    fields: tuple
    sources: tuple
    stage: str = "selected_effect_observed"
    same_date: bool = False
    notes: tuple = ()


_DEPENDENCY_FIELDS = ("pair.dependency_present", "pair.dependency_type")
_ANNEX_FIELDS = ("pair.annex_index_count", "pair.annex_target_member", "pair.annex_object_pointer")
_PROFILES = (
    _Profile("annex_vassal", "annex_start", _ANNEX_FIELDS, ("annex", "annex_helpers", "annex_coalition_effects"),
             stage="in_progress", notes=("A new target annex index is a start signal, not completed annexation or complete task-object lifecycle proof.",)),
    _Profile("cancel_annexation", "annex_cancel", _ANNEX_FIELDS, ("annex", "annex_helpers"),
             notes=("Only disappearance of the previously observed exact target index/object is assessed.",)),
    _Profile("leave_coalition", "coalition", ("pair.coalition_actor_handle",), ("coalition", "annex_coalition_effects")),
    _Profile("ask_for_march", "ask_march", _DEPENDENCY_FIELDS+("pair.actor_overlord_handle",),
             ("request_roles", "four_effects"), notes=("Requester is the subject; native dispatch is not AI acceptance. The matched type change is independently required.",)),
    _Profile("designate_march", "designate", _DEPENDENCY_FIELDS+("pair.target_overlord_handle",), ("four_effects", "request_roles")),
    _Profile("revoke_march", "revoke", _DEPENDENCY_FIELDS+("pair.target_overlord_handle",), ("favor_march_effects",)),
    _Profile("release_soyurghal", "release_soyurghal", _DEPENDENCY_FIELDS+("pair.target_overlord_handle",), ("four_effects",)),
    _Profile("dissolve_protectorate", "dissolve_protectorate", _DEPENDENCY_FIELDS+("pair.target_overlord_handle",), ("four_effects",)),
    _Profile("trade_favors_for_trust", "trust", ("incoming.trust", "now_raw"), ("four_effects", "favor_native"), same_date=True),
    *tuple(_Profile(action, "resource", (f"actor.resources.{field}", f"target.resources.{field}", "now_raw"),
                    ("favor_march_effects", "favor_native"), same_date=True,
                    notes=("Conservation covers only the selected two-country field; any favor drop is an aggregate observation, not an individually attributed fee.",))
           for action, field in (("trade_favors_for_gold", "treasury_milli"), ("trade_favors_for_men", "manpower_milli"),
                                 ("trade_favors_for_sailors", "sailors_milli"))),
    _Profile("trade_favors_for_war_prep", "war_prep", ("target_war_prep.actor_handle", "target_war_prep.deadline", "now_raw"),
             ("favor_march_effects", "favor_native"), same_date=True),
    _Profile("knowledge_sharing", "knowledge", (), ("request_roles",), stage="diagnostic_only",
             notes=("Aggregate sharing counts are eligibility/diagnostic fields; the exact pair effect-object layout is unresolved and cannot prove an active sharing pair.",)),
    _Profile("ask_knowledge_sharing", "knowledge", (), ("request_roles",), stage="diagnostic_only",
             notes=("Provider=original target, recipient=original actor; exact pair effect-object layout remains unresolved.",)),
)
_BY_ACTION = {profile.action: profile for profile in _PROFILES}


def _pins(keys):
    return {path: {"bytes": size, "sha256": sha, "evidence_kind": kind}
            for key, path, size, sha, kind in _PIN_ROWS if key in keys}


def profile_catalog():
    """Return fresh metadata only; no source files or runtime APIs are read."""
    return [{"action": p.action, "required_fields": list(_COMMON_FIELDS+p.fields),
             "required_native_receipt_fields": list(_RECEIPT_FIELDS),
             "same_date_required": p.same_date, "runtime_snapshot_kind": "targeted_pair_rpm",
             "runtime_support": {"pure_data_predicate": True, "native_calls_required": False,
                                 "core_fields_sufficient_for_selected_effect": p.kind != "knowledge",
                                 "knowledge_pair_effect_layout_resolved": False if p.kind == "knowledge" else None},
             "completion_stage": p.stage, "source_pins": _pins(p.sources),
             "diagnostic_fields": ["incoming.favors"] if p.kind in ("resource", "trust", "war_prep") else [],
             "limitations": list(_LIMITATIONS+p.notes)} for p in _PROFILES]


def _parse(value, kind):
    if kind == "int":
        return value if type(value) is int else _MISSING
    if kind == "raw32":
        return value if type(value) is int and -(2**31) <= value < 2**31 else _MISSING
    if kind == "bool":
        return value if type(value) is bool else _MISSING
    if kind == "tag":
        return value if type(value) is str and re.fullmatch(r"[A-Z0-9]{3}", value) else _MISSING
    if kind == "creation":
        return value.lower() if type(value) is str and re.fullmatch(r"[0-9a-fA-F]{16}", value) else _MISSING
    if kind == "type":
        return value if value is None or (type(value) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value)) else _MISSING
    if kind in ("handle", "pointer"):
        if value is None and kind == "pointer":
            return None
        if type(value) is str and re.fullmatch(r"0x[0-9a-fA-F]{1,16}", value):
            value = int(value, 16)
        if type(value) is not int or not 0 <= value < 2**64:
            return _MISSING
        if kind == "pointer":
            if value == 0:
                return None
            return value if 0x10000 <= value < 2**47 else _MISSING
        return value
    if kind == "str":
        return value if type(value) is str else _MISSING
    raise ValueError("Unknown internal field kind")


class _Evaluation:
    def __init__(self, before, after, receipt):
        self.inputs = {"before": before, "after": after, "receipt": receipt}
        self.checks, self.missing, self.invalid, self.changes = [], [], [], {}
        self.cache = {}

    def value(self, scope, path, kind):
        key = (scope, path, kind)
        if key in self.cache:
            return self.cache[key]
        value = self.inputs[scope]
        for segment in path.split("."):
            if not isinstance(value, dict) or segment not in value:
                full = scope+"."+path
                if full not in self.missing:
                    self.missing.append(full)
                self.cache[key] = _MISSING
                return _MISSING
            value = value[segment]
        parsed = _parse(value, kind)
        if parsed is _MISSING:
            full = scope+"."+path
            if full not in self.invalid:
                self.invalid.append(full)
        self.cache[key] = parsed
        return parsed

    def check(self, name, values, predicate, *, role="effect", detail=None):
        state = "unknown" if any(v is _MISSING for v in values) else "pass" if predicate(*values) else "fail"
        row = {"name": name, "role": role, "state": state}
        if detail:
            row["detail"] = detail
        self.checks.append(row)
        return state

    def pair(self, path, kind):
        return tuple(self.value(scope, path, kind) for scope in ("before", "after"))

    def record(self, name, before, after):
        if before is not _MISSING and after is not _MISSING:
            if name.endswith(("_handle", "_pointer")):
                before = hex(before) if type(before) is int else before
                after = hex(after) if type(after) is int else after
            self.changes[name] = {"before": before, "after": after}


def _identity_and_dispatch(e, action):
    for path, kind in (("identity.pid", "int"), ("identity.creation", "creation"),
                       ("pair.actor_tag", "tag"), ("pair.target_tag", "tag"),
                       ("pair.actor_handle", "handle"), ("pair.target_handle", "handle")):
        a, b = e.pair(path, kind)
        e.check("stable_"+path, (a, b), lambda x, y: x == y and (x > 0 if path == "identity.pid" else True), role="baseline")
    actor = e.value("before", "pair.actor_handle", "handle")
    target = e.value("before", "pair.target_handle", "handle")
    atag = e.value("before", "pair.actor_tag", "tag")
    ttag = e.value("before", "pair.target_tag", "tag")
    def ordinary_matches(handle, tag):
        return (handle & 0xffffff) == int.from_bytes(tag.encode("ascii"), "little") and handle >> 56 != 0 and (handle >> 48) & 255 == 0 and (handle >> 32) & 65535 != 0
    e.check("complete_ordinary_actor_handle", (actor, atag), ordinary_matches, role="baseline")
    e.check("complete_ordinary_target_handle", (target, ttag), ordinary_matches, role="baseline")
    e.check("distinct_actor_target", (actor, target), lambda a, b: a != b, role="baseline")
    for path, kind, wanted in (("command.action", "str", action), ("command.actor", "tag", atag),
                               ("command.target", "tag", ttag), ("binding.actor_handle", "handle", actor),
                               ("binding.target_handle", "handle", target),
                               ("identity.pid", "int", e.value("before", "identity.pid", "int")),
                               ("identity.creation", "creation", e.value("before", "identity.creation", "creation"))):
        got = e.value("receipt", path, kind)
        e.check("receipt_matches_"+path, (got, wanted), lambda x, y: x == y, role="dispatch")
    for path, kind, wanted in (("state", "str", "dispatched"), ("native_result.status", "int", 4),
                               ("native_result.submitted", "bool", True), ("native_result.slot_consumed", "bool", True),
                               ("native_result.ownership_closed", "bool", True), ("native_result.owned_live", "int", 0),
                               ("native_result.quarantined", "int", 0), ("native_result.adapter_fault", "int", 0),
                               ("native_result.submit_exception", "int", 0)):
        got = e.value("receipt", path, kind)
        e.check("receipt_"+path, (got,), lambda x: x == wanted, role="dispatch")


def _dependency(e, p):
    present0, present1 = e.pair("pair.dependency_present", "bool")
    type0, type1 = e.pair("pair.dependency_type", "type")
    side = "actor" if p.kind == "ask_march" else "target"
    lord0, lord1 = e.pair(f"pair.{side}_overlord_handle", "handle")
    lord = e.value("before", "pair.target_handle" if side == "actor" else "pair.actor_handle", "handle")
    before_types = {"ask_march": ("vassal", "client_vassal"), "designate": ("vassal", "client_vassal"),
                    "revoke": ("march",), "release_soyurghal": ("soyurghal",),
                    "dissolve_protectorate": ("trade_protectorate",)}[p.kind]
    e.check("dependency_baseline", (present0, type0, lord0, lord),
            lambda present, typ, actual, expected: present is True and typ in before_types and actual == expected, role="baseline")
    releasing = p.kind in ("release_soyurghal", "dissolve_protectorate")
    if releasing:
        e.check("dependency_removed_and_overlord_cleared", (present1, type1, lord1),
                lambda present, typ, actual: present is False and typ is None and actual == SENTINEL)
    else:
        desired = "vassal" if p.kind == "revoke" else "march"
        e.check("dependency_type_changed_same_overlord", (present1, type1, lord1, lord),
                lambda present, typ, actual, expected: present is True and typ == desired and actual == expected)
    e.record("dependency_type", type0, type1)
    e.record(side+"_overlord_handle", lord0, lord1)


def _annex(e, p):
    member0, member1 = e.pair("pair.annex_target_member", "bool")
    count0, count1 = e.pair("pair.annex_index_count", "int")
    ptr0, ptr1 = e.pair("pair.annex_object_pointer", "pointer")
    start = p.kind == "annex_start"
    e.check("annex_baseline", (member0, count0, ptr0),
            lambda member, count, ptr: (member is False and 0 <= count <= 4096 and ptr is None) if start
            else (member is True and 1 <= count <= 4096 and ptr is not None), role="baseline")
    e.check("exact_target_annex_index_transition", (member1, count1, ptr1),
            lambda member, count, ptr: (member is True and 1 <= count <= 4096 and ptr is not None) if start
            else (member is False and 0 <= count <= 4096 and ptr is None),
            detail="Target membership/object is assessed; the total index count may include other targets.")
    e.record("annex_target_member", member0, member1)
    e.record("annex_index_count", count0, count1)
    e.record("annex_object_pointer", ptr0, ptr1)


def _instant(e, p):
    now0, now1 = e.pair("now_raw", "int")
    e.check("same_in_game_date_for_instant_effect", (now0, now1), lambda a, b: 0 < a < 2**31 and a == b, role="baseline")
    if p.kind == "resource":
        field = {"trade_favors_for_gold": "treasury_milli", "trade_favors_for_men": "manpower_milli",
                 "trade_favors_for_sailors": "sailors_milli"}[p.action]
        a0, a1 = e.pair("actor.resources."+field, "raw32")
        b0, b1 = e.pair("target.resources."+field, "raw32")
        e.check("positive_actor_transfer_and_two_country_conservation", (a0, a1, b0, b1),
                lambda x0, x1, y0, y1: x1 > x0 and y1-y0 == -(x1-x0) and x0+y0 == x1+y1)
        e.record("actor_"+field, a0, a1)
        e.record("target_"+field, b0, b1)
    elif p.kind == "trust":
        a, b = e.pair("incoming.trust", "int")
        e.check("target_trust_of_actor_increased", (a, b), lambda x, y: 0 <= x < y <= 100)
        e.record("target_trust_of_actor", a, b)
    elif p.kind == "war_prep":
        actor0, actor1 = e.pair("target_war_prep.actor_handle", "handle")
        date0, date1 = e.pair("target_war_prep.deadline", "raw32")
        expected = e.value("before", "pair.actor_handle", "handle")
        e.check("target_preparing_for_actor_with_new_future_deadline", (actor0, actor1, date0, date1, now1, expected),
                lambda old_actor, actor, old_date, date, now, wanted: actor == wanted and date > old_date and date > now)
        e.record("target_war_prep_actor_handle", actor0, actor1)
        e.record("target_war_prep_deadline", date0, date1)


def _diagnostics(e, p):
    diagnostics = []
    if p.kind in ("resource", "trust", "war_prep"):
        # Optional observation: no missing diagnostic field blocks an otherwise
        # complete primary predicate, and no per-request fee is inferred.
        values = []
        for scope in ("before", "after"):
            value = e.inputs[scope]
            raw = value.get("incoming", {}).get("favors", _MISSING) if isinstance(value, dict) and isinstance(value.get("incoming", {}), dict) else _MISSING
            values.append(_parse(raw, "raw32"))
        diagnostics.append({"name": "incoming_favors", "state": "unknown" if _MISSING in values else "observed",
                            "before": None if values[0] is _MISSING else values[0],
                            "after": None if values[1] is _MISSING else values[1],
                            "per_request_cost_attribution_proven": False})
    if p.kind == "knowledge":
        e.checks.append({"name": "knowledge_pair_effect_object_layout", "role": "effect", "state": "unknown",
                         "detail": "Aggregate sharing counts cannot prove a matching provider/recipient active object; the effect layout is unresolved."})
        provider = "target" if p.action == "ask_knowledge_sharing" else "actor"
        recipient = "actor" if p.action == "ask_knowledge_sharing" else "target"
        diagnostics.append({"name": "knowledge_roles", "provider_side": provider, "recipient_side": recipient,
                            "aggregate_count_changes_are_not_pair_effect_proof": True})
    return diagnostics


def evaluate_profile(action, before, after, native_result):
    """Evaluate selected changes using a full backend receipt, without any I/O.

    Snapshots use identity{pid,creation}, pair{actor/target_tag,actor/target_handle}
    plus catalog fields. Handles are normalized hexadecimal strings; integer
    handles in the existing backend binding are also accepted losslessly.
    Explicit null type/pointer values differ from missing fields. An incomplete
    baseline, mismatched receipt or changed instant-effect date returns unknown.
    """
    p = _BY_ACTION.get(action) if type(action) is str else None
    result = {"schema": SCHEMA, "action": action if type(action) is str else None, "game_sha256": GAME_SHA256,
              "supported": p is not None, "status": "unsupported", "selected_effect_verified": False,
              "native_dispatch_verified": False, "AI_acceptance_verified": False,
              "baseline_comparable": False, "world_epoch_proven": False, "exclusive_causality_proven": False,
              "saved_state_verified": False, "cold_reload_verified": False, "annexation_finished": False,
              "completion_stage": "unsupported", "checks": [], "changes": {}, "diagnostics": [],
              "missing_fields": [], "invalid_fields": [], "source_pins": {}, "limitations": list(_LIMITATIONS)}
    if p is None:
        return result
    e = _Evaluation(before, after, native_result)
    _identity_and_dispatch(e, action)
    if p.kind.startswith("annex_"):
        _annex(e, p)
    elif p.kind in ("ask_march", "designate", "revoke", "release_soyurghal", "dissolve_protectorate"):
        _dependency(e, p)
    elif p.kind == "coalition":
        a, b = e.pair("pair.coalition_actor_handle", "handle")
        target = e.value("before", "pair.target_handle", "handle")
        e.check("coalition_baseline_targets_requested_country", (a, target), lambda x, y: x == y, role="baseline")
        e.check("coalition_target_cleared_to_native_sentinel", (b,), lambda x: x == SENTINEL)
        e.record("coalition_actor_handle", a, b)
    elif p.kind in ("resource", "trust", "war_prep"):
        _instant(e, p)
    diagnostics = _diagnostics(e, p)
    baseline = all(c["state"] == "pass" for c in e.checks if c["role"] == "baseline")
    dispatch = all(c["state"] == "pass" for c in e.checks if c["role"] == "dispatch")
    unknown = bool(e.missing or e.invalid) or any(c["state"] == "unknown" for c in e.checks)
    effect_passed = all(c["state"] == "pass" for c in e.checks if c["role"] == "effect")
    status = "unknown" if unknown or not baseline or not dispatch else "observed" if effect_passed else "not_observed"
    raw_native = native_result.get("native_result", {}) if isinstance(native_result, dict) else {}
    cleanup = raw_native.get("known_cleanup_complete") if isinstance(raw_native, dict) else None
    result.update(status=status, selected_effect_verified=status == "observed", native_dispatch_verified=dispatch,
                  baseline_comparable=baseline, completion_stage=p.stage if status == "observed" else "diagnostic_only" if p.kind == "knowledge" else "unverified",
                  profile_completion_stage=p.stage, checks=e.checks, changes=e.changes,
                  diagnostics=diagnostics, missing_fields=sorted(e.missing), invalid_fields=sorted(e.invalid),
                  native_known_cleanup_complete=cleanup if type(cleanup) is bool else None,
                  source_pins=_pins(p.sources), limitations=list(_LIMITATIONS+p.notes))
    return result
