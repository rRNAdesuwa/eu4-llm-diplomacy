"""Full synthetic replay and selected-state counterexamples, never actual sessions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from synthetic import Fixture, r, lab, data, directional, insult


class PipelineTests(Fixture):
    def test_complete_four_phase_fixture_window_and_three_selected_effects(self):
        self.append_speed();self.append_pair("revoke_fleet_basing_rights",False)
        self.append_pair("revoke_fleet_basing_rights",True,legality=7);self.add_effect(8,"revoke_fleet_basing_rights")
        self.append_pair("insult",False);self.append_pair("insult",True,legality=9);self.add_effect(10,"insult");self.refresh()
        result=self.run_review()
        self.assertEqual(result["observed_effect_count"],3);self.assertEqual(len(result["requests"]),10)
        self.assertEqual(result["phase_case_counts"],r.COUNTS)
        self.assertTrue(result["effects"][0]["forced_test_acceptance_window"])
        self.assertFalse(result["effects"][1]["forced_test_acceptance_window"])
        for key in ("game_process_accessed","production_backend_registered","production_execution_verified","natural_ai_acceptance_verified",
                    "strict_live_single_player_verified","world_epoch_verified","request_id_causality_verified","save_reload_verified"):
            self.assertIs(result[key],False)

    def test_valid_unknown_offer_does_not_establish_rejection_or_override_use(self):
        self.add_effect(4,"offer_fleet_basing_rights",positive=False)
        result=self.run_review();self.assertEqual(result["observed_effect_count"],0)
        self.assertFalse(result["effects"][0]["native_rejection_verified"])
        self.assertFalse(result["acceptance_windows"][0]["asynchronous_override_use_verified"])

    def test_no_op_revoke_cannot_be_promoted(self):
        self.append_speed();self.append_pair("revoke_fleet_basing_rights",False)
        self.append_pair("revoke_fleet_basing_rights",True,legality=7);self.add_effect(8,"revoke_fleet_basing_rights");self.refresh()
        before=json.loads((self.root/"after8.json").read_bytes())
        self.write_artifact("before8","before8.json",before)
        with self.assertRaises(ValueError):self.run_review()

    def test_revoke_on_original_window_date_is_not_reviewed(self):
        self.append_pair("revoke_fleet_basing_rights",False);self.append_pair("revoke_fleet_basing_rights",True,legality=6)
        self.add_effect(7,"revoke_fleet_basing_rights");self.refresh()
        with self.assertRaisesRegex(ValueError,"later date"):self.run_review()

    def test_exact_begin_defaults_and_terminal_dates(self):
        saved=deepcopy(self.events)
        for event_name,key,value in (("test_acceptance_begin","native_invoked",True),("test_acceptance_begin","after_date",1),
                ("test_acceptance_complete","before_date",-123),("test_acceptance_complete","after_date",56456977)):
            self.events=deepcopy(saved)
            e=next(e["record"] for e in self.events if e.get("sequence")==3 and e.get("event")=="lab_native_record" and e["record"]["event"]==event_name)
            e[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.status()

    def test_native_terminal_no_begin_failure_never_becomes_success(self):
        self.events=[e for e in self.events if not(e.get("sequence")==3 and e.get("event")=="lab_native_record" and e["record"]["event"]=="test_acceptance_begin")]
        e=next(e["record"] for e in self.events if e.get("sequence")==3 and e.get("event")=="lab_native_record")
        e.update(reason=6,stage=1,no_native=True,before_date=0,after_date=0,before_raw_flag=None,after_raw_flag=None,freeze_session=True)
        for key in r.acceptance.SUCCESS_FIELDS:e[key]=False
        e["audit_complete"]=True
        with self.assertRaises(ValueError):self.status()

    def test_v15_empty_initial_strings_remain_rejected(self):
        for e in self.events:
            if e["event"]=="research_frame" and e["last_sequence"]==0:e.update(acceptance_action="",acceptance_target="")
        with self.assertRaisesRegex(ValueError,"action binding differs"):self.status()

    def test_no_native_already_off_does_not_reset_open_window(self):
        for e in self.events:
            if e.get("sequence")==5 and e.get("event")=="lab_native_record" and e["record"]["event"]=="test_acceptance_complete":
                e["record"].update(reason=11,no_native=True,before_raw_flag=0,after_raw_flag=0)
        with self.assertRaises(ValueError):self.status()

    def test_missing_durable_pending_or_off_rejected(self):
        saved=deepcopy(self.events)
        for marker in ("pending","off"):
            self.events=[e for e in deepcopy(saved) if not (e["event"]=="lab_acceptance_pending" if marker=="pending" else e.get("sequence")==5)]
            with self.subTest(marker=marker),self.assertRaises(ValueError):self.status()

    def test_pending_self_expiry_equal_rejects(self):
        pending=next(e for e in self.events if e["event"]=="lab_acceptance_pending")
        pending["uptime_ms"]=self.case_request(3)["expires"]
        with self.assertRaisesRegex(ValueError,"expired before durable pending"):self.status()

    def test_claim_own_expiry_equal_rejects(self):
        claim=next(e for e in self.events if e["event"]=="lab_request_claimed" and e["sequence"]==3)
        claim["claimed_uptime_ms"]=claim["expires"]
        with self.assertRaisesRegex(ValueError,"request itself expired"):self.status()

    def test_old_legal_completion_does_not_supply_wrong_target(self):
        row=next(e for e in self.events if e["event"]=="lab_acceptance_pending");row["bound_target"]="ENG"
        with self.assertRaises(ValueError):self.status()

    def test_closed_history_cannot_be_erased(self):
        self.events[-1].update(acceptance_action="none",acceptance_target="none",acceptance_origin_sequence=0,acceptance_submit_sequence=0,acceptance_off_sequence=0)
        with self.assertRaises(ValueError):self.status()

    def test_closing_health_must_preserve_window_date_and_flag(self):
        original=deepcopy(self.events[-1])
        for key,value in (("raw_date",original["raw_date"]+24),("acceptance_flag",1),("acceptance_flag",False),("frames",1)):
            self.events[-1]=dict(original,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):self.status()

    def test_duplicate_sequence_and_foreign_owner_are_rejected(self):
        original=deepcopy(self.events)
        for key,value in (("sequence",3),("pid",self.b.PID+1),("process_creation_filetime","01dd000000000003")):
            self.events=deepcopy(original);e=next(e for e in self.events if e["event"]=="lab_request_claimed" and e["sequence"]==4);e[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.status()

    def test_uncertain_submit_ownership_is_terminal_no_off_compensation(self):
        e=next(e["record"] for e in self.events if e.get("event")=="lab_native_record" and e.get("sequence")==4 and e["record"]["event"]=="pair_engine_complete")
        e["caller_container_consumed"]=False
        with self.assertRaisesRegex(ValueError,"known consumed return"):self.status()

    def test_thirteen_field_wire_is_exact(self):
        path=self.session/"00000000000000000003.claim";raw=path.read_bytes()
        for bad in (raw.replace(b"EU4LAB/3",b"EU4LAB/2"),raw.replace(b"bound_target=POR\n",b""),raw+b"ptr=0x123\n"):
            path.write_bytes(bad)
            with self.subTest(bad=bad[-35:]),self.assertRaises(ValueError):self.status()

    def test_exact_declared_window_no_numeric_aliases_or_extra_grants(self):
        original=deepcopy(self.case["acceptance_windows"])
        for value in (True,3.0,4):
            self.case["acceptance_windows"]=deepcopy(original);self.case["acceptance_windows"][0]["on_sequence"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.run_review()
        self.case["acceptance_windows"]=original*2
        with self.assertRaises(ValueError):self.run_review()

    def test_effect_is_mandatory_for_each_submit_and_not_native_return(self):
        self.case["effects"]=[]
        with self.assertRaisesRegex(ValueError,"missing explicit observed"):self.run_review()

    def test_readonly_before_after_wrong_role_and_second_pass_type_reject(self):
        doc=json.loads((self.root/"after4.json").read_bytes())
        doc["family_snapshot"]["observation"]["passes"][1]["relation"]["object"]["removed"]=False
        self.write_artifact("after4","after4.json",doc)
        with self.assertRaises(ValueError):self.run_review()

    def test_insult_modifier_without_trust_change_is_not_effect(self):
        self.append_pair("insult",False);self.append_pair("insult",True,legality=6);self.add_effect(7,"insult",positive=False);self.refresh()
        self.case["effects"][-1]["expected_observed_effect"]=True
        with self.assertRaises(ValueError):self.run_review()

    def test_fixed_insult_negative_one_cannot_be_externalized(self):
        self.append_pair("insult",False);self.append_pair("insult",True,legality=6);self.add_effect(7,"insult");self.refresh()
        e=next(e["record"] for e in self.events if e.get("event")=="lab_native_record" and e.get("sequence")==7)
        e["fixed_insult_index"]=0
        with self.assertRaises(ValueError):self.status()

    def test_future_closed_window_cannot_be_borrowed_by_armed_status(self):
        doc=json.loads((self.root/"status3.json").read_bytes());doc["report"]["acceptance_window"]=self.status()["acceptance_window"]
        self.write_artifact("status3","status3.json",doc)
        with self.assertRaisesRegex(ValueError,"borrows future"):self.run_review()

    def test_prior_exact_final_status_and_new_healthy_exit_tail_are_valid(self):
        old=json.loads((self.root/"final.json").read_bytes())
        f=deepcopy(self.events[-1]);f["frames"]+=1;f["uptime_ms"]+=1;self.events.append(f);self.refresh()
        self.write_artifact("final","final.json",old)
        self.assertEqual(self.run_review()["status"],"reviewed_stopped_session")

    def test_future_claim_timestamp_cannot_precede_following_health(self):
        e=next(e for e in self.events if e["event"]=="lab_request_claimed" and e["sequence"]==5)
        e["claimed_uptime_ms"]=self.events[-1]["uptime_ms"]+1
        self.capture("status5",self.status(5));self.refresh()
        with self.assertRaisesRegex(ValueError,"Following health precedes"):self.run_review()

    def test_speed_running_frame_mailbox_false_and_closed_history_retained(self):
        self.append_speed();self.refresh();self.assertEqual(self.run_review()["requests"][-1]["outcome"],"completed_and_paused")
        next(e for e in self.events if e["event"]=="research_frame" and e["lease_active"])["mailbox_ready"]=True
        self.capture("status6",self.status(6));self.refresh()
        with self.assertRaisesRegex(ValueError,"frame gates"):self.run_review()

    def test_stop_evidence_and_inventory_are_required(self):
        doc=json.loads((self.root/"exit.json").read_bytes());doc["process_stop_requested_by_observer"]=True
        self.write_artifact("exit","exit.json",doc)
        with self.assertRaises(ValueError):self.run_review()

    def test_unclaimed_request_file_cannot_hide_in_stopped_inventory(self):
        (self.session/"00000000000000000006.request").write_bytes(b"unclaimed")
        with self.assertRaises(ValueError):self.run_review()

    def test_fixture_begin_executed_defaults_and_date_alias_reject(self):
        saved=deepcopy(self.events)
        for key,value in (("native_invoked",True),("before_date",float(self.b.INITIAL_DATE)),("after_date",self.b.INITIAL_DATE)):
            self.events=deepcopy(saved)
            row=next(e["record"] for e in self.events if e.get("event")=="lab_native_record" and e.get("sequence")==1)
            row[key]=value
            # Final cached status need not be synthesized: strict fixture runs
            # before prefix receipt reconciliation and must reject these defaults.
            self.write_log();self.refresh()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"Fixture"):self.run_review()

    def test_preflight_unknown_acceptance_field_not_stripped(self):
        raw=self.prefix.decode();events=[json.loads(x) for x in raw.splitlines()]
        next(e for e in events if e["event"]=="research_frame")["acceptance_extra"]=False
        with self.assertRaisesRegex(ValueError,"exact frame fields"):self.pre.strict_preflight_stream(b"".join(data(e) for e in events),self.pre.EXPECTED_SESSION)

    def test_wrong_build_scope_finalized_false_and_unbounded_artifact_reject(self):
        original=deepcopy(self.case)
        for mutate in (lambda c:c.update(finalized=False),lambda c:c["scope"].update(pid=True),
            lambda c:c["scope"].update(prefix_bytes=8*1024*1024+1),lambda c:c["scope"].update(preflight_case="../x")):
            self.case=deepcopy(original);mutate(self.case)
            with self.assertRaises(ValueError):self.run_review()

    def test_create_new_output_and_exact_check_semantics(self):
        output=self.root/"review.json";review=self.run_review();r.write_new(output,review)
        with self.assertRaises(FileExistsError):r.write_new(output,review)
        self.assertTrue(r.same(review,json.loads(output.read_bytes())))
        wrong=deepcopy(review);wrong["observed_effect_count"]=True
        self.assertFalse(r.same(review,wrong))


if __name__=="__main__":unittest.main()
