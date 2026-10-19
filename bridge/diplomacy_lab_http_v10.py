"""Independent fixed v10 research adapter; no live operations at import time."""
from copy import deepcopy

from bridge import diplomacy_lab_http as transport
from work.native import lab_protocol_v10_1375 as lab

PREFIX = "/research/v10"
BASE = {**transport.BASE, "purpose": lab.PURPOSE, "protocol": lab.PROTOCOL}


class V10ResearchRuntime(transport.V9ResearchRuntime):
    # Internal class dependency, never selected by an HTTP field/path/module name.
    protocol = lab


class ResearchService(transport.ResearchService):
    protocol = lab
    prefix = PREFIX
    kind = "eu4_lab_v10_research_http"
    base = BASE

    def capabilities(self):
        value = super().capabilities()
        value["http_pair_contract"]["fixed_research_parameters"] = deepcopy(lab.FIXED_RESEARCH_PARAMETERS)
        value["v10_candidate"] = {"action_ids": sorted(lab.ACTIONS), "runtime_verified": False,
                                  "production_backend_registered": False,
                                  "fixed_research_parameters": deepcopy(lab.FIXED_RESEARCH_PARAMETERS)}
        value["semantics"]["v10_candidate"] = "24 implemented gated research entries; candidate membership is not a reviewed native effect"
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


def make_server(service, *, host="127.0.0.1", port=8767, token):
    transport.require(isinstance(service, ResearchService), "profile_mismatch", "A fixed v10 research service is required", 422)
    return transport.make_server(service, host=host, port=port, token=token)
