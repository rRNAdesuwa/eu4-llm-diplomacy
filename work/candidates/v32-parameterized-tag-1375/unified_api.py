"""Canonical TAG, subject and war requests on one existing V32 native session."""
from tag32_api import TagDiplomacyAPI, STATE_MAP
from tag32_backend import require, validate_command
import subject_codec
import war_transport
import peace_transport
import government_transport
import war_context_transport
import condottieri_transport
import sell_ships_transport
import rebel_transport
import confirm_tribute_transport
import governor_choice_transport
from subject_api import SubjectDiplomacyAPI, COMPOSITE_FIELDS


# EU4 1.37.5 ordinary creation and province save loading share AF04A0,
# which accepts only task token3378. Old spy task tokens are rejected on load.
# Their ordinary false Apply bodies retain positive effects; see
# docs/legacy-diplomacy-labels-1375.md. These are not pending bool switches.
_UNSUPPORTED_REASONS = {
    "cancel_agitate_for_liberty": "Unavailable legacy task label in EU4 1.37.5: task factory AF04A0 accepts only 0x3378; normal save loading of 0x3242 reports Invalid spy action type. Ordinary false mode still writes the agitation deadline; this is not a pending cancel switch.",
    "cancel_fabricate_claim": "Unavailable legacy task label in EU4 1.37.5: task factory AF04A0 accepts only 0x3378; normal save loading of 0x2AF1 reports Invalid spy action type. Ordinary false mode still adds a claim; this is not a pending cancel switch.",
    "cancel_justify_trade_conflict": "Unavailable legacy task label in EU4 1.37.5: task factory AF04A0 accepts only 0x3378; normal save loading of 0x2F5E reports Invalid spy action type. Ordinary false mode still grants or refreshes the CB; this is not a pending cancel switch.",
    "cancel_sow_discontent": "Unavailable legacy task label in EU4 1.37.5: task factory AF04A0 accepts only 0x3378; normal save loading of 0x2DDF reports Invalid spy action type. Ordinary false mode still applies the discontent modifier; this is not a pending cancel switch.",
    "break_vassalization": "Subject-to-overlord direction is rejected by the reviewed vassalaction legality branch; cancel_vassalization is the separate overlord action.",
    "gold": "Legacy build alias is unavailable. Use the explicit offer_peace request with peace.po_gold after selecting its participants and amount.",
    "whitepeace": "Legacy build alias is unavailable. Use the explicit offer_peace request with an empty term list after selecting its war participants.",
}


class UnifiedDiplomacyAPI(TagDiplomacyAPI):
    def validate(self, request):
        from bridge.demo_war_peace import validate_scope
        validate_scope(request)
        require(type(request) is dict and type(request.get("action")) is str, "Missing canonical action")
        require(request["action"] not in _UNSUPPORTED_REASONS,
                _UNSUPPORTED_REASONS.get(request["action"], "Unsupported action"))
        if request["action"] in subject_codec.ACTIONS:
            return subject_codec.normalize_request(request)
        if request["action"] == "declare_war":
            return war_transport.codec.normalize_request(request)
        if request["action"] == "offer_peace":
            return peace_transport.normalize_request(request)
        if request["action"] in government_transport.ACTIONS:
            return government_transport.normalize_request(request)
        if request["action"] in war_context_transport.ACTIONS:
            return war_context_transport.normalize_request(request)
        if request["action"] in condottieri_transport.ACTIONS:
            return condottieri_transport.normalize_request(request)
        if request["action"] in sell_ships_transport.ACTIONS:
            return sell_ships_transport.normalize_request(request)
        if request["action"] in rebel_transport.ACTIONS:
            return rebel_transport.normalize_request(request)
        if request["action"] in confirm_tribute_transport.ACTIONS:
            return confirm_tribute_transport.normalize_request(request)
        if request["action"] in governor_choice_transport.ACTIONS:
            return governor_choice_transport.normalize_request(request)
        return super().validate(request)

    def _command(self, request):
        action = request["action"]
        if action in subject_codec.ACTIONS:
            return subject_codec.to_flat_command(request)
        if action == "declare_war":
            return war_transport.to_flat_command(request)
        if action == "offer_peace":
            return peace_transport.to_flat_command(request)
        if action in government_transport.ACTIONS:
            return government_transport.to_flat_command(request)
        if action in war_context_transport.ACTIONS:
            return war_context_transport.to_flat_command(request)
        if action in condottieri_transport.ACTIONS:
            return condottieri_transport.to_flat_command(request)
        if action in sell_ships_transport.ACTIONS:
            return sell_ships_transport.to_flat_command(request)
        if action in rebel_transport.ACTIONS:
            return rebel_transport.to_flat_command(request)
        if action in confirm_tribute_transport.ACTIONS:
            return confirm_tribute_transport.to_flat_command(request)
        if action in governor_choice_transport.ACTIONS:
            return governor_choice_transport.to_flat_command(request)
        return super()._command(request)

    def _canonical(self, command):
        action = command["action"]
        if action in subject_codec.ACTIONS:
            return subject_codec.from_flat_command(command)
        if action == "declare_war":
            return war_transport.from_flat_command(command)
        if action == "offer_peace":
            return peace_transport.from_flat_command(command)
        if action in government_transport.ACTIONS:
            return government_transport.from_flat_command(command)
        if action in war_context_transport.ACTIONS:
            return war_context_transport.from_flat_command(command)
        if action in condottieri_transport.ACTIONS:
            return condottieri_transport.from_flat_command(command)
        if action in sell_ships_transport.ACTIONS:
            return sell_ships_transport.from_flat_command(command)
        if action in rebel_transport.ACTIONS:
            return rebel_transport.from_flat_command(command)
        if action in confirm_tribute_transport.ACTIONS:
            return confirm_tribute_transport.from_flat_command(command)
        if action in governor_choice_transport.ACTIONS:
            return governor_choice_transport.from_flat_command(command)
        return super()._canonical(command)

    def _observation(self, native):
        require(type(native) is dict and native.get("identity") == self.identity, "Native session differs")
        command = validate_command(native["command"], self.actions)
        states = dict(STATE_MAP, already_desired="already_desired", partial_dispatched="partial_dispatched")
        state = native.get("state")
        require(state in states, "Unknown native receipt state; never resubmit")
        result = native.get("native_result")
        return {"request_id": command["request_id"], "request": self._canonical(command),
                "status": states[state], "native_state": state, "identity": dict(self.identity),
                "sequence": native.get("sequence"),
                "reason": result.get("reason") if type(result) is dict else None,
                "ownership_closed": result.get("ownership_closed") if type(result) is dict else None,
                **({key: result[key] for key in COMPOSITE_FIELDS if key in result} if type(result) is dict else {}),
                "automatic_retry": False, "gameplay_effects_verified": False,
                "native_observation": native}

    def list_actions(self, *, category=None, include_excluded=True):
        require(category is None or category in (*self.categories, "subject", "war", "government"), "Unknown action category")
        typed_actions = (set(subject_codec.ACTIONS) | {"declare_war", "offer_peace"}
                         | set(government_transport.ACTIONS) | set(war_context_transport.ACTIONS)
                         | set(condottieri_transport.ACTIONS) | set(sell_ships_transport.ACTIONS)
                         | set(rebel_transport.ACTIONS) | set(confirm_tribute_transport.ACTIONS) | set(governor_choice_transport.ACTIONS))
        rows = [row for row in super().list_actions(include_excluded=include_excluded)
                if row["action"] not in typed_actions]
        additions = [{"action": action,
                      "category": "influence" if action == subject_codec.CREATE_VASSAL_ACTION else "subject", "support": "bound",
                      "route": "typed_subject", "runtime_verified": False,
                      "native_source_integrated": True} for action in subject_codec.ACTIONS]
        additions.append({"action": "declare_war", "category": "war", "support": "bound",
                          "route": "typed_war", "runtime_verified": False,
                          "native_source_integrated": True,
                          "call_allies_true_supported": war_transport.codec.capabilities()["call_allies_true_supported"]})
        additions.append({"action": "offer_peace", "category": "war", "support": "bound",
                          "route": "typed_peace", "runtime_verified": False,
                          "native_source_integrated": True, "nested_term_labels": 54})
        additions += [{"action": action, "category": "government", "support": "bound",
                       "route": "typed_government", "runtime_verified": False,
                       "native_source_integrated": True} for action in government_transport.ACTIONS]
        additions += [{"action": action, "category": "war", "support": "bound",
                       "route": "typed_war_context", "runtime_verified": False,
                       "native_source_integrated": True} for action in war_context_transport.ACTIONS]
        additions += [{"action": action, "category": "economy", "support": "bound",
                       "route": "typed_condottieri", "runtime_verified": False,
                       "native_source_integrated": True} for action in condottieri_transport.ACTIONS]
        additions += [{"action": action, "category": "economy", "support": "bound",
                       "route": "typed_sell_ships", "runtime_verified": False,
                       "native_source_integrated": True} for action in sell_ships_transport.ACTIONS]
        additions += [{"action": action, "category": "covert", "support": "bound",
                       "route": "typed_rebels", "runtime_verified": False,
                       "native_source_integrated": True} for action in rebel_transport.ACTIONS]
        additions += [{"action": action, "category": "influence", "support": "bound",
                       "route": "typed_confirm_tribute", "runtime_verified": False,
                       "native_source_integrated": True} for action in confirm_tribute_transport.ACTIONS]
        additions += [dict(action=action,category='subject',support='bound',route='typed_governor_choice',
                           runtime_verified=False,native_source_integrated=True,
                           publication_connected=governor_choice_transport.PUBLICATION_CONNECTED)
                      for action in governor_choice_transport.ACTIONS]
        for row in rows:
            if row["action"] in _UNSUPPORTED_REASONS:
                row["reason"] = _UNSUPPORTED_REASONS[row["action"]]
        return [row for row in rows + additions if category is None or row["category"] == category]

    def capabilities(self):
        result = super().capabilities()
        result.update(actions=list(self.actions) + list(subject_codec.ACTIONS) + ["declare_war", "offer_peace"]
                             + list(government_transport.ACTIONS) + list(war_context_transport.ACTIONS) + list(condottieri_transport.ACTIONS)
                             + list(sell_ships_transport.ACTIONS) + list(rebel_transport.ACTIONS)
                             + list(confirm_tribute_transport.ACTIONS) + list(governor_choice_transport.ACTIONS),
                      action_count=len(self.actions) + len(subject_codec.ACTIONS) + 2 + len(government_transport.ACTIONS)
                                   + len(war_context_transport.ACTIONS) + len(condottieri_transport.ACTIONS)
                                   + len(sell_ships_transport.ACTIONS) + len(rebel_transport.ACTIONS) + len(confirm_tribute_transport.ACTIONS) + len(governor_choice_transport.ACTIONS),
                      categories=list(dict.fromkeys([*self.categories, "subject", "war", "government"])),
                      typed_subject_actions=list(subject_codec.ACTIONS),
                      typed_subject=SubjectDiplomacyAPI().capabilities(),
                      typed_war=war_transport.codec.capabilities(),
                      typed_peace=peace_transport.planner().capabilities(),
                      typed_government=government_transport.capabilities(),
                      typed_war_context=war_context_transport.capabilities(),
                      typed_condottieri=condottieri_transport.capabilities(),
                      typed_sell_ships=sell_ships_transport.capabilities(),
                      typed_rebels=rebel_transport.capabilities(),
                      typed_confirm_tribute=confirm_tribute_transport.capabilities(),
                      typed_governor_choice=governor_choice_transport.capabilities(),
                      shared_request_queue=True, mixed_batches=True,
                      native_build_verified=self.backend is not None, runtime_verified=False)
        supported = set(result["actions"])
        result["excluded"] = [dict(row, reason=_UNSUPPORTED_REASONS.get(row["action"], row["reason"]))
                              for row in result["excluded"] if row["action"] not in supported]
        result["unsupported_actions"] = dict(_UNSUPPORTED_REASONS)
        result["actions"] = list(dict.fromkeys(result["actions"]))
        result["action_count"] = len(result["actions"])
        return result

    def submit_batch(self, requests, *, ttl_ms=None, test_only=False):
        validated = self.validate_batch(requests)
        require(governor_choice_transport.PUBLICATION_CONNECTED is True or
                not any(q['action'] in governor_choice_transport.ACTIONS for q in validated),
                'Governor native Claim route is not connected; no publication performed')
        require(not test_only or all(request["action"] in self.actions for request in validated),
                "Typed gameplay validation is deferred to final concentrated testing")
        return super().submit_batch(validated, ttl_ms=ttl_ms, test_only=test_only)
