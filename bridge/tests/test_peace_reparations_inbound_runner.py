import unittest
from pathlib import Path
from unittest.mock import patch

from work import run_peace_inbound_response as runner
from work import validate_peace_inbound_reload as reload_validator


DATE_RAW = 56545080
PAIR = ("FRA", "ENG")


def context(*, mixed: bool = False, payer: str = "FRA") -> dict[str, object]:
    terms: list[dict[str, object]] = [{
        "action_id": "war_reparations",
        "payer": payer,
        "claimant": "ENG",
    }]
    if mixed:
        terms.append({"action_id": "demand_ducats", "amount_raw": 0,
                      "scale": 1000})
    return {
        "war_id": "war_3fead0a5641ef4f5_00000001",
        "direction": "demand",
        "terms": terms,
        "original_actor": "ENG",
        "original_recipient": "FRA",
        "complete": True,
        "selected_terms_complete": True,
        "white_peace": False,
    }


def effects(*, accepted: bool) -> dict[str, object]:
    return {
        "complete": True,
        "date_unchanged": True,
        "currency_scale": 1000,
        "money": None,
        "provinces": [],
        "war_reparations": {
            "payer": "FRA",
            "claimant": "ENG",
            "active_before": False,
            "active_after": accepted,
            "verified": accepted,
            "start_date_raw": DATE_RAW if accepted else 0,
            "end_date_raw": DATE_RAW + 365 if accepted else 0,
        },
    }


def response(*, decision: str, accepted: bool,
             peace_context: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "phase": decision,
        "war_before": True,
        "war_after": not accepted,
        "pending_removed": True,
        "response_verified": True,
        "request_binding_verified": True,
        "native_outcome": "accepted" if accepted else "rejected",
        "terms_verified": accepted,
        "date_raw": DATE_RAW,
        "peace_context": peace_context or context(),
        "effects": effects(accepted=accepted),
    }


def final(*, decision: str, accepted: bool,
          peace_context: dict[str, object] | None = None) -> dict[str, object]:
    projected = response(decision=decision, accepted=accepted,
                         peace_context=peace_context)
    return {
        "status": "accepted" if accepted else "rejected",
        "game_outcome": "accepted" if accepted else "rejected",
        "result": projected,
    }


def native_probe(*, present: bool, active: bool,
                 start: int | None = None,
                 end: int | None = None) -> dict[str, object]:
    return {
        "status": "ok",
        "snapshot": {"runtime": {
            "countries": [],
            "provinces": [],
            "war_reparations": {
                "payer": "FRA", "claimant": "ENG", "complete": True,
                "present": present, "active": active,
                "start_date_raw": start, "end_date_raw": end,
            },
        }},
    }


def save_probe(*, exact: bool, status: str = "active") -> dict[str, object]:
    records: list[dict[str, object]] = []
    if exact:
        records.append({
            "complete": True,
            "payer": "FRA",
            "claimant": "ENG",
            "start_date": "1455.5.12",
            "end_date": "1465.5.12",
            "date_status": {
                "comparison_available": True,
                "status": status,
            },
        })
    return {
        "status": "ok",
        "parsed": {"countries": {}, "provinces": {}},
        "war_reparations": {"query": {
            "exact_pair_present": exact,
            "matching_records": records,
        }},
    }


class PeaceReparationsInboundRunnerTests(unittest.TestCase):
    def test_inspection_binds_demand_roles_from_context(self) -> None:
        inspection = {
            "action_id": "peace_offer", "family": "peace",
            "actor": "ENG", "recipient": "FRA", "phase": "reject",
            "decision_country": "FRA", "decision_country_verified": True,
            "parameters": {"requested": {"proposal_id": "a" * 32}},
            "war_before": True,
            "native_inbound_inspection": {"response_rules_complete": True},
            "peace_payload_complete": True,
            "selected_terms_complete": True,
            "legality": {"status": "available"},
            "authorization": {"status": "available"},
            "peace_context": context(),
        }
        checks = runner._inspection_contract(inspection, "a" * 32, "reject")
        self.assertTrue(all(checks.values()))
        wrong = {**inspection, "peace_context": context(payer="ENG")}
        self.assertFalse(runner._inspection_contract(
            wrong, "a" * 32, "reject")["peace_reparations_roles"])

    def test_public_accept_and_reject_results_require_r_effect_shape(self) -> None:
        accepted = runner._public_effect_contract(
            final(decision="accept", accepted=True), "accept")
        rejected = runner._public_effect_contract(
            final(decision="reject", accepted=False), "reject")
        self.assertTrue(accepted["all"])
        self.assertTrue(rejected["all"])
        self.assertTrue(runner._public_response_contract(
            final(decision="reject", accepted=False), "reject", "a" * 32)
            ["effects_contract"])

    def test_source_context_is_taken_from_result_and_roles_are_checked(self) -> None:
        payload = {
            "status": "passed", "action_id": "peace_offer", "family": "peace",
            "actor": "ENG", "recipient": "FRA", "decision": "reject",
            "request_id": "r-inbound", "checks": {"one": True},
            "session": {"session_id": "source-session"},
            "after": {"control": {"date_raw": DATE_RAW}},
            "native_response": {
                "contract": True, "full_payload": True,
                "response_verified": True, "request_binding_verified": True,
                "handler_forwarded": True, "handler_consumed": True,
                "pending_removed": True,
                "response_event": {
                    "event": "native_peace_inbound_response_result",
                    "family": "peace", "action_id": "peace_offer",
                    "actor": "ENG", "recipient": "FRA", "phase": "reject",
                    "request_id": "r-inbound", "session_id": "source-session",
                    "war_before": True, "war_after": True,
                },
            },
            "result": final(decision="reject", accepted=False),
        }
        source = reload_validator._source_contract(payload)
        self.assertTrue(source["all"])
        self.assertEqual(PAIR, source["reparations_pair"])
        payload["result"]["result"]["peace_context"]["terms"][0]["payer"] = "ENG"
        self.assertFalse(reload_validator._source_contract(payload)["all"])

    def test_reload_rejected_r_reads_native_and_save_once(self) -> None:
        source = reload_validator._source_contract({
            "status": "passed", "action_id": "peace_offer", "family": "peace",
            "actor": "ENG", "recipient": "FRA", "decision": "reject",
            "request_id": "r-inbound", "checks": {"one": True},
            "session": {"session_id": "source-session"},
            "after": {"control": {"date_raw": DATE_RAW}},
            "native_response": {
                "contract": True, "full_payload": True,
                "response_verified": True, "request_binding_verified": True,
                "handler_forwarded": True, "handler_consumed": True,
                "pending_removed": True,
                "response_event": {
                    "event": "native_peace_inbound_response_result",
                    "family": "peace", "action_id": "peace_offer",
                    "actor": "ENG", "recipient": "FRA", "phase": "reject",
                    "request_id": "r-inbound", "session_id": "source-session",
                    "war_before": True, "war_after": True,
                },
            },
            "result": final(decision="reject", accepted=False),
        })
        with patch.object(reload_validator, "_run_effect_probe",
                          return_value=native_probe(present=False, active=False)) as native, \
                patch.object(reload_validator, "_stream_save_effect_state",
                             return_value=save_probe(exact=False)) as saved:
            result = reload_validator._peace_effect_reload_contract(
                source, {"request_id": "r-inbound"}, {}, object(), DATE_RAW,
                Path("inbound-r-evidence"))
        self.assertTrue(result["all"])
        self.assertEqual(1, native.call_count)
        self.assertEqual(1, saved.call_count)
        self.assertEqual(PAIR, native.call_args.kwargs["reparations_pair"])
        self.assertTrue(result["comparison"]["checks"][
            "native_war_reparations_present"])

    def test_reload_accepted_r_requires_present_active_relation(self) -> None:
        source_payload = {
            "status": "passed", "action_id": "peace_offer", "family": "peace",
            "actor": "ENG", "recipient": "FRA", "decision": "accept",
            "request_id": "r-inbound-accept", "checks": {"one": True},
            "session": {"session_id": "source-session"},
            "after": {"control": {"date_raw": DATE_RAW}},
            "native_response": {
                "contract": True, "full_payload": True,
                "response_verified": True, "request_binding_verified": True,
                "handler_forwarded": True, "handler_consumed": True,
                "pending_removed": True,
                "response_event": {
                    "event": "native_peace_inbound_response_result",
                    "family": "peace", "action_id": "peace_offer",
                    "actor": "ENG", "recipient": "FRA", "phase": "accept",
                    "request_id": "r-inbound-accept", "session_id": "source-session",
                    "war_before": True, "war_after": False,
                },
            },
            "result": final(decision="accept", accepted=True),
        }
        source = reload_validator._source_contract(source_payload)
        with patch.object(reload_validator, "_run_effect_probe",
                          return_value=native_probe(
                              present=True, active=True,
                              start=DATE_RAW, end=DATE_RAW + 365)), \
                patch.object(reload_validator, "_stream_save_effect_state",
                             return_value=save_probe(exact=True)):
            result = reload_validator._peace_effect_reload_contract(
                source, {"request_id": "r-inbound-accept"}, {}, object(), DATE_RAW,
                Path("inbound-r-accept-evidence"))
        self.assertTrue(result["all"])


class PeaceInboundReloadBindingTests(unittest.TestCase):
    @staticmethod
    def _sources(count: int = 61) -> list[dict[str, str]]:
        return [{"name": f"source-{index}.inc",
                 "sha256": f"{index + 1:064x}"}
                for index in range(count)]

    @classmethod
    def _binding(cls, count: int = 61, *, current_count: int | None = None,
                 current_sources: list[dict[str, str]] | None = None) -> tuple[dict[str, object], dict[str, object]]:
        source_sources = cls._sources(count)
        reload_sources = (current_sources if current_sources is not None
                          else cls._sources(current_count if current_count is not None else count))
        source = {
            "build_manifest": {"sources": source_sources},
            "build_binding": {"installation_matches_build_manifest": True},
            "session": {"dll_sha256": "a" * 64},
        }
        current = {
            "build_manifest": {"sources": reload_sources},
            "build_binding": {"installation_matches_build_manifest": True},
            "installation": {"declared_dll_sha256": "a" * 64},
        }
        return source, current

    def test_manifest_size_61_remains_compatible(self) -> None:
        source, current = self._binding(61)
        result = reload_validator._binding_contract(source, current)
        self.assertTrue(result["all"])
        self.assertEqual(61, result["source_source_count"])

    def test_manifest_size_65_is_valid_when_maps_match(self) -> None:
        source, current = self._binding(65)
        result = reload_validator._binding_contract(source, current)
        self.assertTrue(result["all"])
        self.assertEqual(65, result["reload_source_count"])

    def test_missing_duplicate_and_bad_hash_are_rejected(self) -> None:
        source, current = self._binding(65)
        missing = list(source["build_manifest"]["sources"])
        missing.pop()
        current["build_manifest"]["sources"] = missing
        missing_result = reload_validator._binding_contract(source, current)
        self.assertFalse(missing_result["all"])
        self.assertFalse(missing_result["checks"][
            "source_reload_source_hashes_equal"])

        duplicate = list(source["build_manifest"]["sources"])
        duplicate[-1] = dict(duplicate[0])
        self.assertIsNone(reload_validator._source_map(duplicate))

        bad_hash = list(source["build_manifest"]["sources"])
        bad_hash[0] = {**bad_hash[0], "sha256": "not-a-sha256"}
        self.assertIsNone(reload_validator._source_map(bad_hash))

if __name__ == "__main__":
    unittest.main()
