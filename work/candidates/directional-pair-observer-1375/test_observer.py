"""Sparse synthetic memory and offline files only; no native process access."""
from copy import deepcopy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location("directional_candidate",Path(__file__).with_name("observer.py"))
candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
from bridge.tests.test_pair_extension_v10_probe import fixture, report, BASE, DATE, OBJ, TARGET
from bridge.tests.test_pair_extension_v10_probe import ROOT_A, ROOT_B, INDEX_A, INDEX_B, RECORDS_A, RECORDS_B

CREATION="01dd56169d5e2000"


def snapshot(action,active=False,after=False,target="POR",mutate=None):
    family=candidate.ACTIONS[action][0]
    memory=fixture(family,active=active,target=target)
    if mutate:mutate(memory)
    raw=report(memory,family,target=target,after=after)
    raw["source"]["process_creation_filetime"]=int(CREATION,16)
    raw["read_budget"]={"bytes_read":memory.bytes_read,"maximum_total":candidate.base.MAX_TOTAL_READ,
        "maximum_single":candidate.base.MAX_READ,"maximum_relation_entries":candidate.base.MAX_RELATION_ENTRIES,"passes":2}
    return candidate.wrap_snapshot(raw,action,123,CREATION)


class DirectionalCandidateTests(unittest.TestCase):
    def test_ten_protocol_directions_four_targets_have_exact_selected_transition(self):
        for action,(_,value) in candidate.ACTIONS.items():
            for target in candidate.legacy.TARGETS:
                with self.subTest(action=action,target=target):
                    before=snapshot(action,active=not value,target=target)
                    after=snapshot(action,active=value,after=True,target=target)
                    result=candidate.compare_reports(before,after)
                    self.assertTrue(result["observed_effect"],result)
                    self.assertEqual(result["binding"]["native_value"],value)
                    for key in ("runtime_verified","execution_verified","production_ready","request_causality_verified",
                                "ai_acceptance_verified","strict_single_player_verified","world_epoch_verified",
                                "whole_world_unchanged_verified","paused_verified","rejection_observed"):
                        self.assertFalse(result[key])

    def test_roles_come_from_family_indexes_not_proposal_order(self):
        for action,holder,grantor in (("cancel_military_access","FRA","POR"),
            ("revoke_military_access","POR","FRA"),("cancel_fleet_basing_rights","FRA","POR"),
            ("offer_fleet_basing_rights","POR","FRA"),("revoke_fleet_basing_rights","POR","FRA")):
            value=snapshot(action,active=True)
            _,state,_=candidate.validated_report(value)
            self.assertEqual(state["object"]["first_handle"],hex(candidate.legacy.HANDLES[holder]))
            self.assertEqual(state["object"]["second_handle"],hex(candidate.legacy.HANDLES[grantor]))
            self.assertEqual(value["binding"]["roles"]["rights_holder"],holder)
            self.assertEqual(value["binding"]["roles"]["rights_grantor"],grantor)

    def test_cross_family_retagging_and_swapped_role_metadata_are_rejected(self):
        before=snapshot("cancel_military_access",active=True)
        after=snapshot("revoke_military_access",after=True)
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])
        after=snapshot("cancel_military_access",after=True)
        after["binding"]["roles"]["rights_holder"]="POR"
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])
        with self.assertRaises(candidate.base.ProbeError):
            candidate.wrap_snapshot(before["family_snapshot"],"revoke_military_access",123,CREATION)

    def test_missing_or_reverse_access_never_counts_as_successful_cancellation(self):
        for action in ("cancel_military_access","revoke_military_access","cancel_fleet_basing_rights","revoke_fleet_basing_rights"):
            empty=snapshot(action)
            after=snapshot(action,after=True)
            self.assertFalse(candidate.compare_reports(empty,after)["observed_effect"])
            def reverse(memory):
                family=candidate.ACTIONS[action][0]
                pair=[candidate.legacy.HANDLES["FRA"],candidate.legacy.HANDLES["POR"]]
                if not family.startswith("offer"):pair.reverse()
                memory.write_fixture(OBJ+0x10,pair[0]);memory.write_fixture(OBJ+0x18,pair[1])
            invalid=snapshot(action,True,mutate=reverse)
            self.assertFalse(candidate.compare_reports(invalid,after)["observed_effect"])

    def test_enforce_peace_or_removed_object_is_not_ordinary_access(self):
        for offset,value,width in ((0x40,1,1),(0x40,2,1),(0x28,1,1)):
            before=snapshot("revoke_fleet_basing_rights",True,
                mutate=lambda memory:memory.write_fixture(OBJ+offset,value,width))
            self.assertFalse(candidate.compare_reports(before,snapshot("revoke_fleet_basing_rights",after=True))["observed_effect"])

    def test_other_direction_only_and_conditional_access_do_not_supply_selected_before(self):
        action="revoke_military_access"
        memory=fixture("milaccess",active=True,target="POR")
        # FRA holds a grant from POR; this is not a FRA grant to POR to revoke.
        raw=report(memory,"offermilaccess",target="POR")
        raw["source"]["process_creation_filetime"]=int(CREATION,16)
        raw["read_budget"]={"bytes_read":memory.bytes_read,"maximum_total":candidate.base.MAX_TOTAL_READ,
            "maximum_single":candidate.base.MAX_READ,"maximum_relation_entries":4096,"passes":2}
        before=candidate.wrap_snapshot(raw,action,123,CREATION)
        self.assertFalse(candidate.compare_reports(before,snapshot(action,after=True))["observed_effect"])
        def conditional(memory):
            memory.write_fixture(ROOT_A+0x50,INDEX_A);memory.write_fixture(ROOT_A+0x5C,1,4)
            memory.write_fixture(INDEX_A,struct.pack("<I4xQ",189,0x770000))
        before=snapshot("cancel_military_access",mutate=conditional)
        self.assertFalse(candidate.compare_reports(before,snapshot("cancel_military_access",after=True))["observed_effect"])

    def test_duplicate_single_sided_index_and_wrong_full_handle_are_unknown(self):
        mutations=[lambda m:m.write_fixture(ROOT_B+0xBC,0,4),
            lambda m:m.write_fixture(OBJ+0x18,candidate.legacy.HANDLES["FRA"]+0x100000000),
            lambda m:(m.write_fixture(ROOT_A+0xD4,2,4),m.write_fixture(INDEX_A+16,struct.pack("<I4xQ",189,OBJ)))]
        for mutate in mutations:
            before=snapshot("revoke_military_access",True,mutate=mutate)
            self.assertFalse(candidate.compare_reports(before,snapshot("revoke_military_access",after=True))["observed_effect"])

    def test_subsidy_fixed_amount_years_and_payer_are_mandatory_in_both_modes(self):
        for action in ("give_subsidies","cancel_subsidies"):
            value=candidate.ACTIONS[action][1]
            for offset,n in ((0x40,2000),(0x44,11),(0x40,-1)):
                active=snapshot(action,True,after=value,mutate=lambda m:m.write_fixture(OBJ+offset,struct.pack("<i",n)))
                empty=snapshot(action,after=not value)
                result=candidate.compare_reports(empty,active) if value else candidate.compare_reports(active,empty)
                self.assertFalse(result["observed_effect"])
            reverse=snapshot(action,True,after=value,mutate=lambda m:(m.write_fixture(OBJ+0x10,candidate.legacy.HANDLES["POR"]),m.write_fixture(OBJ+0x18,candidate.legacy.HANDLES["FRA"])))
            empty=snapshot(action,after=not value)
            result=candidate.compare_reports(empty,reverse) if value else candidate.compare_reports(reverse,empty)
            self.assertFalse(result["observed_effect"])

    def test_subsidy_expiry_or_later_day_cannot_masquerade_as_explicit_cancel(self):
        action="cancel_subsidies"
        expired=snapshot(action,True,mutate=lambda m:m.write_fixture(OBJ+0x20,DATE-10*0x2238,4))
        self.assertFalse(candidate.compare_reports(expired,snapshot(action,after=True))["observed_effect"])
        before=snapshot(action,True);after=snapshot(action,after=True)
        for row in after["family_snapshot"]["observation"]["passes"]:row["current_raw_date"]+=24
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])

    def test_embargo_mask_does_not_borrow_opposite_flag_or_dirty_bits(self):
        incoming=RECORDS_B+122*0x48+0x46
        outgoing=RECORDS_A+189*0x48+0x46
        before=snapshot("embargo")
        for mutate in (lambda m:m.write_fixture(incoming,2,1),lambda m:m.write_fixture(outgoing,1,1)):
            after=snapshot("embargo",after=True,mutate=mutate)
            self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])
        after=snapshot("embargo",True,True,mutate=lambda m:m.write_fixture(incoming,2,1))
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])
        after=snapshot("embargo",True,True,mutate=lambda m:m.write_fixture(outgoing,3,1))
        self.assertTrue(candidate.compare_reports(before,after)["observed_effect"])

    def test_alliance_is_symmetric_and_does_not_identify_initiator(self):
        before=snapshot("dissolve_alliance",True,mutate=lambda m:(m.write_fixture(OBJ+0x10,candidate.legacy.HANDLES["POR"]),m.write_fixture(OBJ+0x18,candidate.legacy.HANDLES["FRA"])))
        result=candidate.compare_reports(before,snapshot("dissolve_alliance",after=True))
        self.assertTrue(result["observed_effect"])
        self.assertFalse(result["binding"]["roles"]["initiating_country_verified"])

    def test_identity_epoch_appearance_or_incomplete_passes_cannot_be_rebound(self):
        before=snapshot("offer_fleet_basing_rights")
        original=snapshot("offer_fleet_basing_rights",True,True)
        mutations=[lambda r:r.update(expected_creation="01dd56169d5e2001"),
            lambda r:r["family_snapshot"]["source"].update(pid=124),
            lambda r:(r.update(expected_creation="01dd56169d5e2001"),
                r["family_snapshot"]["source"].update(process_creation_filetime=int("01dd56169d5e2001",16))),
            lambda r:r["family_snapshot"]["build"].update(sha256="0"*64),
            lambda r:r.update(contract_sha256="0"*64),
            lambda r:r["family_snapshot"]["observation"]["passes"].pop(),
            lambda r:r["family_snapshot"]["observation"]["passes"][1].update(game="0x777000"),
            lambda r:r["family_snapshot"]["read_budget"].update(bytes_read=True)]
        for mutate in mutations:
            after=deepcopy(original);mutate(after)
            self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])

    def test_sample_checks_creation_before_memory_and_closes_rejected_handle(self):
        reader=Mock(base=BASE)
        with patch.object(candidate,"verify_contract"),patch.object(candidate.base,"verified_executable",return_value=({},{})), \
             patch.object(candidate.base,"ProcessReader",return_value=reader) as opened, \
             patch.object(candidate.base,"process_identity",return_value={"process_creation_filetime":1,"process_exit_filetime":0}), \
             patch.object(candidate.legacy,"capture") as captured:
            with self.assertRaises(candidate.base.ProbeError):candidate.sample_process(123,CREATION,Path("unused.exe"),"POR","embargo")
        opened.assert_called_once();captured.assert_not_called();reader.close.assert_called_once()

    def test_each_pass_rejects_python_equal_native_scalar_type_changes(self):
        before=snapshot("offer_fleet_basing_rights")
        mutations={
            "raw_date_float":lambda row:row.update(current_raw_date=float(DATE)),
            "removed_bool":lambda row:row["relation"]["object"].update(removed=False),
            "enforce_peace_bool":lambda row:row["relation"]["object"].update(enforce_peace=False),
            "marker_float":lambda row:row["relation"]["object"].update(type_marker=357.0),
            "count_float":lambda row:row["relation"]["left"].update(count=1.0),
            "count_bool":lambda row:row["relation"]["right"].update(count=True),
            "slot_float":lambda row:row["relation"]["left"]["entries"][0].update(slot=189.0),
        }
        for changed in ((0,),(1,),(0,1)):
            for name,mutate in mutations.items():
                with self.subTest(passes=changed,field=name):
                    after=snapshot("offer_fleet_basing_rights",True,True)
                    rows=after["family_snapshot"]["observation"]["passes"]
                    original=deepcopy(rows)
                    for index in changed:mutate(rows[index])
                    self.assertEqual(original,rows) # Demonstrates Python's unsafe equality.
                    result=candidate.compare_reports(before,after)
                    self.assertFalse(result["observed_effect"],result)
                    self.assertEqual(result["status"],"unknown")
                    self.assertTrue(result["errors"])

    def test_stored_state_types_must_match_reconstruction_from_both_passes(self):
        for action,key,value in (("offer_fleet_basing_rights","removed",False),
                                ("offer_fleet_basing_rights","type_marker",357.0),
                                ("offer_fleet_basing_rights","enforce_peace",False),
                                ("give_subsidies","monthly_milli",1000.0),
                                ("give_subsidies","duration_years",10.0)):
            with self.subTest(action=action,field=key):
                before=snapshot(action);after=snapshot(action,True,True)
                observation=after["family_snapshot"]["observation"]
                # Persisted JSON has separate state/pass objects even if a live
                # in-memory capture shared the object reference.
                observation["state"]=deepcopy(observation["state"])
                original=deepcopy(observation["state"])
                observation["state"]["object"][key]=value
                self.assertEqual(original,observation["state"])
                self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])
        before=snapshot("embargo");after=snapshot("embargo",True,True)
        after["family_snapshot"]["observation"]["state"]["outgoing_embargo"]=1
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])

    def test_complete_pass_comparison_preserves_uninterpreted_field_types(self):
        before=snapshot("offer_fleet_basing_rights")
        for original,changed in ((0,False),(1,1.0),(False,0)):
            after=snapshot("offer_fleet_basing_rights",True,True)
            rows=after["family_snapshot"]["observation"]["passes"]
            rows[0]["supplementary_raw_field"]=original
            rows[1]["supplementary_raw_field"]=changed
            self.assertEqual(rows[0],rows[1])
            result=candidate.compare_reports(before,after)
            self.assertFalse(result["observed_effect"])
            self.assertIn("Two type-identical complete passes required",result["errors"])

    def test_atomic_claim_and_non_json_containers_are_not_accepted(self):
        before=snapshot("offer_fleet_basing_rights")
        after=snapshot("offer_fleet_basing_rights",True,True)
        after["family_snapshot"]["observation"]["atomic_snapshot"]=0
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])
        after=snapshot("offer_fleet_basing_rights",True,True)
        for row in after["family_snapshot"]["observation"]["passes"]:
            row["relation"]["left"]["entries"]=tuple(row["relation"]["left"]["entries"])
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])

    def test_unsupported_action_is_explicit_and_does_not_open_process(self):
        with patch.object(candidate.base,"ProcessReader") as opened,patch.object(candidate.base,"verified_executable") as exe:
            self.assertEqual(candidate.describe("insult")["status"],"unsupported")
            with self.assertRaises(candidate.base.ProbeError):candidate.sample_process(123,CREATION,Path("unused.exe"),"POR","send_gift")
        opened.assert_not_called();exe.assert_not_called()

    def test_static_roles_and_helper_dependencies_match_immutable_contract(self):
        contract=candidate.verify_contract()
        self.assertEqual(len(contract["action_bindings"]),10)
        self.assertEqual(len(contract["dependencies"]),9)
        self.assertEqual(len(contract["static_role_evidence"]),8)
        self.assertFalse(contract["runtime_verified"])
        self.assertEqual(contract["family_layouts"]["offer_fleet_access"]["actor_index_pointer"],"0xf8")
        self.assertEqual(contract["family_layouts"]["fleet_access"]["actor_index_pointer"],"0xe0")
        with patch.object(candidate,"CONTRACT_SHA256","0"*64):
            with self.assertRaises(candidate.base.ProbeError):candidate.verify_contract()

    def test_binding_boolean_and_fixed_integer_types_are_not_interchangeable(self):
        before=snapshot("offer_fleet_basing_rights");after=snapshot("offer_fleet_basing_rights",True,True)
        after["binding"]["native_value"]=1
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])
        before=snapshot("give_subsidies");after=snapshot("give_subsidies",True,True)
        after["binding"]["fixed_parameters"]["monthly_milli"]=1000.0
        self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])

    def test_modified_helper_and_read_budget_fail_before_process_access(self):
        contract=candidate.verify_contract()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            contract_path=root/"work/candidates/directional-pair-observer-1375/evidence-contract.json"
            contract_path.parent.mkdir(parents=True)
            contract_path.write_bytes(Path(__file__).with_name("evidence-contract.json").read_bytes())
            for name in contract["dependencies"]:
                destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes((ROOT/name).read_bytes())
            self.assertEqual(candidate.verify_contract(root)["profile"],candidate.PROFILE)
            helper=root/"work/probe_pair_extension_v10_1375.py"
            with helper.open("ab") as stream:stream.write(b"# changed\n")
            with patch.object(candidate.base,"ProcessReader") as process:
                with self.assertRaises(candidate.base.ProbeError):candidate.verify_contract(root)
                with patch.object(candidate,"MAX_DEPENDENCY",16):
                    with self.assertRaises(candidate.base.ProbeError):candidate.verify_contract()
            process.assert_not_called()

    def test_consistent_but_changed_world_or_non_fra_player_is_not_comparable(self):
        before=snapshot("embargo")
        for kind in ("world","player"):
            after=snapshot("embargo",True,True)
            for sample in after["family_snapshot"]["observation"]["passes"]:
                if kind=="world":sample["game"]="0x888000"
                else:sample["player"]=deepcopy(sample["pair"]["POR"])
            self.assertFalse(candidate.compare_reports(before,after)["observed_effect"])

    def test_cli_compare_is_bounded_create_new_and_has_no_external_scalar_or_direction(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);before=root/"before.json";after=root/"after.json";out=root/"result.json"
            before.write_text(json.dumps(snapshot("give_subsidies")),encoding="utf-8")
            after.write_text(json.dumps(snapshot("give_subsidies",True,True)),encoding="utf-8")
            argv=["compare","--before",str(before),"--after",str(after),"--output",str(out)]
            with patch.object(candidate.base,"ProcessReader") as process,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(candidate.main(argv),0)
                original=out.read_bytes();self.assertEqual(candidate.main(argv),2);self.assertEqual(out.read_bytes(),original)
                with self.assertRaises(SystemExit):candidate.main(argv+["--expected-monthly-milli","2500"])
                with self.assertRaises(SystemExit):candidate.main(argv+["--direction","positive"])
                self.assertEqual(candidate.main(argv[:-1]+[str(root/"unsafe.request")]),2)
                self.assertFalse((root/"unsafe.request").exists())
            process.assert_not_called()
            self.assertEqual(set(json.loads(original)["inputs"]),{"before_sha256","after_sha256"})


if __name__=="__main__":unittest.main()
