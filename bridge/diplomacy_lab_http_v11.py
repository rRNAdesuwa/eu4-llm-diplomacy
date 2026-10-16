"""Independent fixed v11 research adapter; no live operations at import time."""
from copy import deepcopy

from bridge import diplomacy_lab_http as transport
from work.native import lab_protocol_v11_1375 as lab

PREFIX = "/research/v11"
BASE = {**transport.BASE, "purpose": lab.PURPOSE, "protocol": lab.PROTOCOL}


class V11ResearchRuntime(transport.V9ResearchRuntime):
    # Internal class dependency, never selected by an HTTP field/path/module name.
    protocol = lab


class ResearchService(transport.ResearchService):
    protocol = lab
    prefix = PREFIX
    kind = "eu4_lab_v11_research_http"
    base = BASE

    def _summary(self, snapshot):
        value = super()._summary(snapshot)
        value["input_wait_pending"] = snapshot["evidence"].get("input_wait_pending", False)
        return value

    def capabilities(self):
        value = super().capabilities()
        value["http_pair_contract"]["fixed_research_parameters"] = deepcopy(lab.FIXED_RESEARCH_PARAMETERS)
        value["v11_candidate"] = {"action_ids": sorted(lab.ACTIONS), "runtime_verified": False,
                                  "production_backend_registered": False,
                                  "fixed_research_parameters": deepcopy(lab.FIXED_RESEARCH_PARAMETERS)}
        value["semantics"]["v11_candidate"] = "36 implemented gated research entries; candidate membership is not a reviewed native effect"
        return value

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


def make_server(service, *, host="127.0.0.1", port=8768, token):
    transport.require(isinstance(service, ResearchService), "profile_mismatch", "A fixed v11 research service is required", 422)
    return transport.make_server(service, host=host, port=port, token=token)
