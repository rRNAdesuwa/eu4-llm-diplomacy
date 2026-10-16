"""Independent fixed v16 research adapter; no live operations at import time."""
from copy import deepcopy

from bridge import diplomacy_lab_http as transport
from work.native import lab_protocol_v16_1375 as lab

PREFIX = "/research/v16"
BASE = {**transport.BASE, "purpose": lab.PURPOSE, "protocol": lab.PROTOCOL}


class V16ResearchRuntime(transport.V9ResearchRuntime):
    # Internal class dependency, never selected by an HTTP field/path/module name.
    protocol = lab


class ResearchService(transport.ResearchService):
    protocol = lab
    prefix = PREFIX
    kind = "eu4_lab_v16_research_http"
    base = BASE

    def _summary(self, snapshot):
        value = super()._summary(snapshot)
        value["input_wait_pending"] = snapshot["evidence"].get("input_wait_pending", False)
        value["acceptance_window"] = deepcopy(snapshot["evidence"].get("acceptance_window", {}))
        value["phase_attempted"] = deepcopy(snapshot["evidence"].get("phase_attempted", {}))
        return value

    def capabilities(self):
        value = super().capabilities()
        value["http_pair_contract"]["fixed_research_parameters"] = deepcopy(lab.FIXED_RESEARCH_PARAMETERS)
        value["required_native_stages"] = deepcopy(lab.OWNED_PEACE_STAGE_CONTRACT)
        value["v16_candidate"] = {"action_ids": sorted(lab.ACTIONS), "runtime_verified": False,
                                  "production_backend_registered": False,
                                  "fixed_research_parameters": deepcopy(lab.FIXED_RESEARCH_PARAMETERS)}
        value["semantics"]["v16_candidate"] = "36 implemented gated research entries; candidate membership is not a reviewed native effect"
        value["acceptance_control"] = {"publication_surface": "explicit_versioned_CLI_only",
            "actions": ["accept_on", "accept_off"], "requires_exact_single_pair_binding": True,
            "http_accept_endpoint": False, "normal_ai_acceptance_verified": False}
        return value

    def _validate_request(self, request):
        lab = self.protocol
        transport.require(isinstance(request, dict) and set(request) == transport.REQUEST_FIELDS,
                "invalid_request", "Supply exactly the documented pair request fields", 422)
        transport.require(request["protocol"] == lab.PROTOCOL, "wrong_protocol", "Only this bound EU4LAB/3 research protocol is accepted", 422)
        transport.require(type(request["pid"]) is int and request["pid"] == self.pid and request["creation"] == self.creation,
                "wrong_session", "Request PID/creation differs from this bound service", 409)
        transport.require(lab.integer(request["sequence"], 1, lab.MAX_SEQUENCE)
                and lab.integer(request["ttl_ms"], 1, lab.MAX_TTL),
                "invalid_request", "Sequence and TTL must be integers in the advertised bounds", 422)
        transport.require(all(isinstance(request[key], str) for key in ("mode", "action", "actor", "target")),
                "invalid_request", "Mode, action and country tags must be strings", 422)
        try:
            lab.encode_request({key: request[key] for key in ("pid", "creation", "sequence", "mode", "action", "actor", "target")}
                               | {"operation": "pair", "speed": 0, "expires": 1, "bound_action": "none", "bound_target": "none", "bound_submit_sequence": 0})
            lab.require(request["mode"] != "submit" or request["actor"] == "FRA", "Only current player FRA may submit")
        except lab.LabError as error:
            raise transport.ResearchError("invalid_request", str(error), 422) from error
        return dict(request)

    def pair(self, body):
        status, value = super().pair(body)
        value["fixed_research_parameters"] = deepcopy(lab.FIXED_RESEARCH_PARAMETERS.get(body["action"], {}))
        return status, value

    def status(self, sequence=None):
        value = super().status(sequence)
        if sequence is not None:
            action = value.get("request", {}).get("action")
            value["fixed_research_parameters"] = deepcopy(lab.FIXED_RESEARCH_PARAMETERS.get(action, {}))
        return value


def make_server(service, *, host="127.0.0.1", port=8772, token):
    transport.require(isinstance(service, ResearchService), "profile_mismatch", "A fixed v16 research service is required", 422)
    return transport.make_server(service, host=host, port=port, token=token)
