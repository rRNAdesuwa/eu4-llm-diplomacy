"""Pure mocked evidence-binding tests. No process, UI, engine or runtime-record writes."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from work import verify_v8_reload_1375 as review


class V8ReloadReviewTests(unittest.TestCase):
    def setUp(self):
        self.manifest={"dll_sha256":"A"*64}
        self.manifest_sha="b"*64
        self.hashes={name:"C"*64 for name in review.FILES.values()}
        self.hashes[review.FILES["summary"]]=review.SUMMARY_SHA
        self.hashes[review.FILES["vassal_before"]]=review.VASSAL_BEFORE_SHA
        player=dict(tag="FRA",handle="0x0100007a00415246",address="0x12340000",slot=122)
        pair={"FRA":deepcopy(player),"NAV":dict(tag="NAV",handle="0x010000bc0056414e",address="0x12350000",slot=188)}
        self.reports={
            "summary":dict(schema_version=1,purpose="v8_experiment_evidence_review",read_only=True,pid=39216,
                creation=review.OLD_CREATION,game_sha256=review.lab.LOCAL_SHA256,dll_sha256=self.manifest["dll_sha256"],
                manifest_sha256=self.manifest_sha,fixture_profile_sha256=review.lab.FIXTURE_PROFILE_SHA256,
                save_sha256=review.SAVE_SHA,phase_checks_passed=True,
                actions={"break_marriage":dict(native_dispatch_completed=True,observed_relation_removed=True,
                         saved_result_consistent=True,saved_reload_state_consistent=False)},
                input_sha256={review.FILES[k]:self.hashes[review.FILES[k]] for k in ("save","copy","marriage_before")}),
            "save":dict(parsed_complete=True,read_only=True,evidence_scope="serialized_state_only",
                source=dict(path="saved",sha256=review.SAVE_SHA,size_bytes=review.SAVE_SIZE,gamestate_bytes=review.SAVE_SIZE,
                            format="plain_text",gamestate_sha256=review.SAVE_SHA),actor="FRA",targets=["NAV"],
                captured_at_utc="2026-10-07T18:06:30+00:00",
                metadata={key:{"value":value} for key,value in (("date","1444.11.17"),("player","FRA"),("multi_player","no"))},
                global_diplomacy={"container_found":True,"records":[{"key":"dependency","entries":[
                    {"key":key,"value":value} for key,value in (("first","FRA"),("second","NAV"),
                    ("subject_type","vassal"),("start_date","1444.11.13"))]}]}),
            "copy":dict(sha256=review.SAVE_SHA,size=review.SAVE_SIZE,byte_identical=True,overwrite=False,
                         source="original",preserved="saved"),
            "restart":dict(expected_pid=54232,new_pid=20276,forced_test_process_exit=False,plan_only=False,
                save_sha256=review.SAVE_SHA,loaded_save_verified=False,purpose="disposable_1375_test_restart",
                executable_sha256=review.lab.LOCAL_SHA256,startup_option="-continue=<verified test filename>",
                save=review.SAVE_NAME,launched_at_utc="2026-10-07T18:47:25.793035+00:00"),
            "installed":dict(installed=True,enabled=True,fixture_profile="v8",fixture_profile_sha256=review.lab.FIXTURE_PROFILE_SHA256),
            "binding":dict(pid=20276,creation=review.NEW_CREATION,bridge_loaded=False,read_only=True,
                live=dict(pid=20276,creation=review.NEW_CREATION,world_cookie="0x22220000",player_handle=player["handle"],raw_date=56457120),
                fixture_disk_evidence=dict(pid=20276,creation=review.NEW_CREATION,profile_sha256=review.lab.FIXTURE_PROFILE_SHA256,
                    installed_before_process_creation=True,fixture_definition_files_verified=True,
                    engine_registration_verified=False,files_checked=7,enabled_mod_configuration_sha256="D"*64)),
        }
        for kind,action in (("marriage","royal_marriage"),("vassal","vassalaction")):
            for reloaded in (False,True):
                key=kind+("_reloaded" if reloaded else "_before")
                source=dict(pid=20276 if reloaded else 39216,process_creation_filetime=int(review.NEW_CREATION if reloaded else review.OLD_CREATION,16),module_base="0x140000000")
                sample=dict(module_base="0x140000000",database="0x11110000",game="0x22220000",country_array="0x33330000",
                            player=deepcopy(player),pair=deepcopy(pair),current_raw_date=56457120 if reloaded else (56457024 if kind=="vassal" else 56457072))
                # All addresses are deliberately reusable across the new process.
                state=dict(state="absent",object=None)
                if kind=="vassal":state=dict(state="active",object=dict(actor_handle=player["handle"],target_handle=pair["NAV"]["handle"],
                    started_raw_date=56457024,removed=0,type_name={"name":"vassal"}))
                stamp=datetime(2026,10,7,19 if reloaded else 18,0,0,tzinfo=timezone.utc)
                self.reports[key]=dict(action=action,target="NAV",source=source,_sample=sample,_state=state,_times=[stamp,stamp])
        self.patch=patch.object(review.observer,"validated_report",side_effect=lambda r:(r["_sample"],r["_state"],r["_times"]))
        self.patch.start();self.addCleanup(self.patch.stop)

    def validate(self):return review.validate_reports(self.reports,self.hashes,self.manifest,self.manifest_sha)

    def test_new_pid_creation_can_reuse_all_addresses_without_claiming_world_generation(self):
        result=self.validate()
        self.assertTrue(result["saved_reload_state_consistent"])
        self.assertTrue(result["separate_process_identity_verified"])
        self.assertFalse(result["world_generation_verified"])
        self.assertFalse(result["exact_loaded_file_path_verified"])
        self.assertFalse(result["request_id_causality_verified"])
        self.assertFalse(self.reports["summary"]["actions"]["break_marriage"]["saved_reload_state_consistent"])

    def test_immutable_summary_and_earlier_input_hashes_must_match(self):
        for key in ("summary","save","copy","marriage_before","vassal_before"):
            before=deepcopy(self.hashes);self.hashes[review.FILES[key]]="E"*64
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate()
            self.hashes=before

    def test_summary_wrong_build_or_upgraded_in_place_is_rejected(self):
        original=deepcopy(self.reports)
        for mutator in (lambda r:r["summary"].update(creation=review.NEW_CREATION),
                        lambda r:r["summary"].update(dll_sha256="E"*64),
                        lambda r:r["summary"]["actions"]["break_marriage"].update(saved_reload_state_consistent=True)):
            self.reports=deepcopy(original);mutator(self.reports)
            with self.assertRaises(ValueError):self.validate()

    def test_saved_dependency_dates_direction_and_uniqueness_are_bound(self):
        original=deepcopy(self.reports)
        for mutate in (lambda e:e[0].update(value="NAV"),lambda e:e[3].update(value="1444.11.15"),
                       lambda e:e.append(dict(e[0]))):
            self.reports=deepcopy(original);mutate(self.reports["save"]["global_diplomacy"]["records"][0]["entries"])
            with self.assertRaises(ValueError):self.validate()
        self.reports=deepcopy(original)
        self.reports["save"]["global_diplomacy"]["records"].append(deepcopy(self.reports["save"]["global_diplomacy"]["records"][0]))
        with self.assertRaises(ValueError):self.validate()

    def test_remaining_serialized_marriage_and_missing_container_are_rejected(self):
        entry=deepcopy(self.reports["save"]["global_diplomacy"]["records"][0]);entry["key"]="royal_marriage"
        self.reports["save"]["global_diplomacy"]["records"].append(entry)
        with self.assertRaises(ValueError):self.validate()
        self.reports["save"]["global_diplomacy"]["records"].pop()
        self.reports["save"]["global_diplomacy"]["container_found"]=False
        with self.assertRaises(ValueError):self.validate()

    def test_two_reloaded_reports_cannot_mix_world_roots_or_player(self):
        original=deepcopy(self.reports)
        for field in ("game","database","country_array","module_base"):
            self.reports=deepcopy(original);self.reports["vassal_reloaded"]["_sample"][field]="0x44440000"
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate()
        self.reports=deepcopy(original);self.reports["vassal_reloaded"]["_sample"]["player"]["handle"]="0x010000bc0056414e"
        with self.assertRaises(ValueError):self.validate()

    def test_creation_binding_and_fixed_fixture_attestation_are_required(self):
        original=deepcopy(self.reports)
        for field,value in (("creation",review.OLD_CREATION),("pid",39216),("files_checked",5),
                            ("fixture_definition_files_verified",False),("installed_before_process_creation",False),
                            ("engine_registration_verified",True)):
            self.reports=deepcopy(original);self.reports["binding"]["fixture_disk_evidence"][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate()

    def test_capture_before_restart_or_old_creation_does_not_pass(self):
        self.reports["vassal_reloaded"]["_times"]=[datetime(2026,10,7,18,1,tzinfo=timezone.utc)]*2
        with self.assertRaises(ValueError):self.validate()

    def test_copy_hash_size_and_no_overwrite_claim_are_checked(self):
        for field,bad in (("sha256","0"*64),("size",0),("byte_identical",False),("overwrite",True)):
            old=self.reports["copy"][field];self.reports["copy"][field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate()
            self.reports["copy"][field]=old

    def test_file_verification_uses_preserved_field_and_fixed_names_only(self):
        with tempfile.TemporaryDirectory() as directory:
            user=Path(directory);root=user/"save games";root.mkdir()
            original=root/"法兰西1444_11_17.eu4";preserved=root/review.SAVE_NAME
            original.write_bytes(b"test");preserved.write_bytes(b"test")
            self.reports["save"]["source"]["path"]=str(preserved)
            self.reports["copy"].update(source=str(original),preserved=str(preserved))
            self.reports["restart"]["save"]=str(preserved)
            with patch.object(review,"user_data",return_value=user),patch.object(review,"SAVE_SIZE",4), \
                 patch.object(review.lab,"file_hash",return_value=review.SAVE_SHA) as hash_file:
                review.verify_save_files(self.reports)
                self.assertEqual(hash_file.call_count,2)
                hash_file.reset_mock();self.reports["copy"]["source"]=str(user/"not-reviewed.eu4")
                with self.assertRaises(ValueError):review.verify_save_files(self.reports)
                hash_file.assert_not_called()

    def test_review_never_returns_success_when_disk_bytes_fail(self):
        with patch.object(review,"read_reports",return_value=(self.reports,self.hashes)), \
             patch.object(review.lab,"verify_build",return_value=(self.manifest,self.manifest_sha)), \
             patch.object(review,"verify_save_files",side_effect=ValueError("changed save bytes")):
            with self.assertRaises(ValueError):review.review()


if __name__=="__main__":unittest.main()
