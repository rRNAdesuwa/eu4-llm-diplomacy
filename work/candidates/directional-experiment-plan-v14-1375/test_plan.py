"""Offline fixed-scope validation. No process, native function or mailbox."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import socketserver
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("directional_v14_plan",HERE/"prepare.py")
plan=importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


class DirectionalPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=plan.make_plan()

    def test_exact_ten_directions_and_four_previously_reviewed_setups(self):
        plan.validate_plan(self.original)
        self.assertEqual(len(set(plan.TEN)),10)
        self.assertEqual(len(set(plan.SETUPS)),4)
        self.assertFalse(set(plan.TEN)&set(plan.SETUPS))
        self.assertTrue(set(plan.TEN+plan.SETUPS)<=plan.lab.ACTIONS)
        self.assertEqual(self.original["historical_effect_action_count"],20)
        self.assertEqual(len(plan.lab.ACTIONS)-20-10,6)

    def test_frozen_codec_round_trip_all_28_action_modes_no_private_fields(self):
        for action in plan.TEN+plan.SETUPS:
            for mode in ("legality_only","submit"):
                with self.subTest(action=action,mode=mode):
                    record,raw=plan.synthetic_wire(action,mode)
                    self.assertEqual(set(record),set(plan.lab.FIELDS))
                    self.assertTrue(raw.startswith(b"EU4LAB/2\n"))
                    self.assertTrue(raw.endswith(b"\n"))
                    self.assertNotIn(b"\r",raw)
                    self.assertEqual(plan.lab.decode_request(raw),record)
                    self.assertEqual((record["actor"],record["target"],record["speed"]),("FRA","POR",0))
                    self.assertNotIn(b"amount",raw)
                    self.assertNotIn(b"envoy",raw)

    def test_extra_amount_duration_rva_or_raw_envoy_are_rejected(self):
        record,_=plan.synthetic_wire("give_subsidies","submit")
        for key,value in (("monthly_milli",1000),("duration_years",10),("duration_months",120),
                          ("envoy_id",0),("rva","0x4e9930"),("console","event llmt.1")):
            with self.subTest(key=key):
                bad={**record,key:value}
                with self.assertRaises(plan.lab.LabError):plan.lab.encode_request(bad)

    def test_unknown_target_wrong_pair_nonplayer_submit_not_plannable(self):
        for target in ("SPA","FRA"):
            record,_=plan.synthetic_wire("embargo","submit");record["target"]=target
            with self.assertRaises(plan.lab.LabError):plan.lab.encode_request(record)
        with self.assertRaises(plan.lab.LabError):
            plan.lab.prepare_request({"pid":1,"process_creation_filetime":"0000000000000001"},
                {"last_sequence":0},sequence=1,ttl_ms=5000,now=1,operation="pair",mode="submit",
                action="embargo",actor="POR",target="FRA",speed=0)
        changed=deepcopy(self.original);changed["cases"][0]["requests"]["submit"]["target"]="NAV"
        with self.assertRaises(ValueError):plan.validate_plan(changed)

    def test_request_version_canonical_integer_and_fresh_sequence_ttl_are_enforced(self):
        _,raw=plan.synthetic_wire("revoke_embargo","legality_only")
        for bad in (raw.replace(b"EU4LAB/2",b"EU4LAB/1"),raw.replace(b"sequence=1",b"sequence=01"),
                    raw.replace(b"\n",b"\r\n"),raw+b"envoy_id=0\n"):
            with self.assertRaises(plan.lab.LabError):plan.lab.decode_request(bad)
        for sequence,ttl in ((1,5000),(3,5000),(2,0),(2,60001),(True,5000)):
            with self.subTest(sequence=sequence,ttl=ttl):
                with self.assertRaises(plan.lab.LabError):
                    plan.lab.prepare_request({"pid":1,"process_creation_filetime":"0000000000000001"},
                        {"last_sequence":1},sequence=sequence,ttl_ms=ttl,now=1,
                        **plan.request_template("embargo","submit"))

    def test_access_roles_cannot_be_swapped_or_inferred_from_actor_order(self):
        expected={"cancel_military_access":("FRA","POR"),"revoke_military_access":("POR","FRA"),
                  "cancel_fleet_basing_rights":("FRA","POR"),"revoke_fleet_basing_rights":("POR","FRA"),
                  "offer_fleet_basing_rights":("POR","FRA")}
        for case in self.original["cases"]:
            if case["action_id"] in expected:
                roles=case["binding"]["roles"]
                self.assertEqual((roles["rights_holder"],roles["rights_grantor"]),expected[case["action_id"]])
        changed=deepcopy(self.original)
        case=next(row for row in changed["cases"] if row["action_id"]=="revoke_military_access")
        case["binding"]["roles"].update(rights_holder="FRA",rights_grantor="POR")
        with self.assertRaises(ValueError):plan.validate_plan(changed)

    def test_subsidies_fixed_direction_amount_and_years_are_not_parameters(self):
        for action in ("give_subsidies","cancel_subsidies"):
            case=next(row for row in self.original["cases"] if row["action_id"]==action)
            self.assertEqual(case["binding"]["fixed_parameters"],{"monthly_milli":1000,"duration_years":10})
            self.assertEqual((case["binding"]["roles"]["payer"],case["binding"]["roles"]["payee"]),("FRA","POR"))
            for value in (1000.0,2000):
                changed=deepcopy(self.original)
                row=next(row for row in changed["cases"] if row["action_id"]==action)
                row["binding"]["fixed_parameters"]["monthly_milli"]=value
                with self.assertRaises(ValueError):plan.validate_plan(changed)

    def test_future_sequence_or_historical_permission_cannot_be_promoted(self):
        for modify in (lambda p:p.update(execution_order_is_future_sequence=True),
                       lambda p:p.update(automatic_target_fallback=True),
                       lambda p:p.update(production_ready=True),
                       lambda p:p["cases"][0].update(target_permission_verified=True),
                       lambda p:p["cases"][0].update(fresh_legality_required=False),
                       lambda p:p["cases"][0].update(future_sequence=3)):
            changed=deepcopy(self.original);modify(changed)
            with self.assertRaises(ValueError):plan.validate_plan(changed)

    def test_cancel_without_prestate_or_reversed_operation_order_rejected(self):
        for modify in (lambda p:p["groups"][0].update(cancel_requires_active_before=False),
                       lambda p:p["groups"][1]["order"].reverse(),
                       lambda p:p["groups"][5].update(same_raw_date_per_effect_comparison=False)):
            changed=deepcopy(self.original);modify(changed)
            with self.assertRaises(ValueError):plan.validate_plan(changed)

    def test_bounded_historical_matrix_does_not_prove_cancel_absence_or_new_permission(self):
        matrix=plan.historical_matrix()
        self.assertEqual(len(matrix),28)
        self.assertTrue(all(row["submitted"] is False for row in matrix))
        self.assertEqual(sum(row["allowed"] for row in matrix),14)
        self.assertIs(self.original["historical_matrix_is_fresh_legality"],False)
        self.assertIs(self.original["historical_legality_cutoff"]["not_a_current_permission"],True)

    def test_all_outputs_are_file_only_and_frozen_sources_are_verified(self):
        with patch.object(plan.lab,"LiveLabProcess",side_effect=AssertionError("No process access")) as process, \
             patch.object(plan.lab,"publish_research",side_effect=AssertionError("No publication")) as publish, \
             patch.object(socketserver,"TCPServer",side_effect=AssertionError("No server")) as server:
            result=plan.outputs()
        process.assert_not_called();publish.assert_not_called();server.assert_not_called()
        self.assertEqual(set(result),{"plan.json","input-pins.json","offline-wire-checks.json"})
        self.assertEqual(result["input-pins.json"]["frozen_native_sources_checked"],20)
        self.assertEqual(result["input-pins.json"]["manifest_sha256"],plan.MANIFEST_SHA)
        self.assertEqual(len(result["offline-wire-checks.json"]["checks"]),28)
        self.assertIs(result["offline-wire-checks.json"]["publishable"],False)


if __name__=="__main__":unittest.main()
