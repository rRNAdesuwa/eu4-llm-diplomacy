"""EU4LAB/2 isolation and canonical input tests; never opens a game process."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from work.native import lab_protocol_1375 as v6
from work.native import lab_protocol_v9_1375 as v9
from tools import request_diplomacy_lab_v9 as cli
from work.native import lab_protocol_v8_1375 as frozen_v8
from work.native import inject_lab_v9_1375 as loader
from bridge.tests import test_diplomacy_lab as old_fixtures


class LabV9Tests(unittest.TestCase):
    def setUp(self):
        self.record=dict(pid=1234,creation="01da123456789abc",sequence=1,expires=6400,operation="pair",
                         mode="legality_only",action="royal_marriage",actor="FRA",target="NAV",speed=0)

    def session_fixture(self):
        fixture=old_fixtures.LabTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.metadata["purpose"]=v9.PURPOSE
        for event in fixture.events:
            if event["event"]=="research_frame":
                event["fixture_profile_sha256"]=v9.FIXTURE_PROFILE_SHA256
        for name in ("session.json","install.claim"):
            (fixture.session/name).write_text(json.dumps(fixture.metadata),encoding="utf-8")
        fixture.write()
        return fixture

    def fixture_events(self, fixture):
        request=dict(fixture.record,operation="fixture",mode="submit",action="fixture_on",actor="FRA",target="FRA")
        (fixture.session/"00000000000000000001.claim").write_bytes(v9.encode_request(request))
        (fixture.session/"00000000000000000001.fixture-profile").write_bytes(v9.fixture_proof_wire(fixture.metadata,1))
        fixture.events.append(fixture.bound("lab_request_claimed",**{k:v for k,v in request.items() if k not in ("pid","creation","sequence")},durable_claim=True,retry_allowed=False))
        flags=("native_invoked","callback_returned","callback_success","arguments_unchanged","result_destroyed","world_identity_unchanged","callback_flag_restored")
        core=dict(thread_id=fixture.thread,fixture_event="llmt.1",target="FRA",fixture_profile_sha256=v9.FIXTURE_PROFILE_SHA256,
                  reason=0,before_date=56456976,after_date=56456976,exception_code=0,freeze_session=False,
                  retry_allowed=False,fixture_effect_verified=False,diplomacy_submitted=False,**{key:True for key in flags})
        begin=dict(core,event="test_fixture_begin",after_date=0,**{key:False for key in flags})
        fixture.events.append(fixture.bound("lab_native_record",lease_pause=False,record=begin))
        fixture.events.append(fixture.bound("lab_native_record",lease_pause=False,record=dict(core,event="test_fixture_complete")))
        fixture.events.append(fixture.bound("lab_request_complete",operation="fixture",action="fixture_on",reason=0,
            session_frozen=False,fixture_effect_verified=False,applied_verified=False,retry_allowed=False,**{key:True for key in flags}))
        fixture.write()

    def installation_fixture(self, directory):
        root,user=Path(directory)/"repo",Path(directory)/"user"
        for name in v9.FIXTURE_SOURCES:
            source=v9.fixture_source_path(root,name)
            installed=user/name
            source.parent.mkdir(parents=True,exist_ok=True)
            installed.parent.mkdir(parents=True,exist_ok=True)
            raw=b'name="fixture-only"\n' if name.endswith("descriptor.mod") else (name+"\n").encode("ascii")
            source.write_bytes(raw);installed.write_bytes(raw)
        profile={"profile_id":v9.FIXTURE_PROFILE_ID,"source_sha256":{name:v9.file_hash(v9.fixture_source_path(root,name)) for name in v9.FIXTURE_SOURCES}}
        digest=hashlib.sha256(v9.canonical(profile).encode("ascii")).hexdigest()
        (user/"dlc_load.json").write_text(json.dumps({"enabled_mods":["mod/llm_diplomacy_test.mod"]}),encoding="utf-8")
        (user/"mod/llm_diplomacy_test.mod").write_text('name="fixture-only"\n\npath="mod/llm_diplomacy_test"\n',encoding="utf-8")
        return root,user,profile,digest

    def test_new_protocol_and_paths_do_not_alias_v6(self):
        self.assertEqual(v9.PROTOCOL,"EU4LAB/2")
        self.assertEqual(v6.PROTOCOL,"EU4LAB/1")
        self.assertNotEqual(v9.OUTPUT,v6.OUTPUT)
        self.assertNotEqual(v9.DLL_NAME,v6.DLL_NAME)
        self.assertNotEqual(v9.PURPOSE,v6.PURPOSE)
        self.assertEqual(len(v9.SOURCES),14)
        self.assertEqual(set(v9.SOURCES)&set(v6.SOURCES),set())
        for name in v9.SOURCES:
            self.assertTrue(name.startswith("work/native/v9/") or name.startswith("work/native/test-fixture-v9-"))

    def test_v8_wire_version_is_shared_but_build_session_and_fixture_identity_are_distinct(self):
        self.assertEqual(v9.PROTOCOL,frozen_v8.PROTOCOL)
        self.assertNotEqual(v9.PURPOSE,frozen_v8.PURPOSE)
        self.assertNotEqual(v9.OUTPUT,frozen_v8.OUTPUT)
        self.assertNotEqual(v9.DLL_NAME,frozen_v8.DLL_NAME)
        self.assertNotEqual(v9.FIXTURE_PROFILE_ID,frozen_v8.FIXTURE_PROFILE_ID)
        self.assertNotEqual(v9.FIXTURE_PROFILE_SHA256,frozen_v8.FIXTURE_PROFILE_SHA256)
        self.assertFalse(set(v9.SOURCES)&set(frozen_v8.SOURCES))
        fixture=self.session_fixture()
        fixture.metadata["purpose"]=frozen_v8.PURPOSE
        (fixture.session/"session.json").write_text(json.dumps(fixture.metadata),encoding="utf-8")
        with self.assertRaises(ValueError):
            v9.read_session_metadata(fixture.session,fixture.pid,fixture.creation)

    def test_candidate_profile_does_not_read_or_modify_frozen_source_mod(self):
        with tempfile.TemporaryDirectory() as directory:
            root,user,profile,digest=self.installation_fixture(directory)
            decoy=root/v9.FIXTURE_SOURCES[0]
            decoy.parent.mkdir(parents=True,exist_ok=True)
            decoy.write_bytes(b"older frozen source bytes")
            with patch.object(v9,"FIXTURE_PROFILE_SHA256",digest):
                self.assertEqual(v9.fixture_profile(root),profile)
                self.assertEqual(decoy.read_bytes(),b"older frozen source bytes")
                with self.assertRaises(ValueError):
                    v9.fixture_source_path(root,"../escape")
                (user/v9.FIXTURE_SOURCES[1]).write_bytes(b"old installed definition")
                with self.assertRaises(ValueError):
                    v9.verify_installed_fixture({"fixture_profile":profile},1234,
                        f'{116444736000000000+2000000000*10000000:016x}',root=root,user_root=user)

    def test_loader_requires_explicit_reviewed_test_save_before_any_process_open(self):
        with patch.object(v9,"LiveLabProcess") as live,patch.object(v9,"verify_build") as build, \
             contextlib.redirect_stderr(io.StringIO()):
            for options in ([],["--test-save","not-reviewed.eu4"],["--test-save","llm_diplomacy_1375_v7_marriage_vassal_20261008a.eu4"]):
                with self.assertRaises(SystemExit) as error:
                    loader.main(["--pid","1234","--ack-test-save","--plan-only",*options])
                self.assertEqual(error.exception.code,2)
            live.assert_not_called();build.assert_not_called()
        self.assertEqual(v9.TEST_SAVES, {
            "llm_diplomacy_1375_baseline.eu4":"276F88AFECDBC1F1A24ED6314845351B1BA5640715B7ED1FD14513B3376664FB",
            "llm_diplomacy_1375_after_improve.eu4":"7BFABE371E68AE502B806F9B80375FC8A4DAC638AD116D2506966FEF69633C5F"})

    def test_positive_vassal_save_is_rejected_before_disk_or_process_access(self):
        positive="llm_diplomacy_1375_v7_marriage_vassal_20261008a.eu4"
        self.assertIn(positive,frozen_v8.TEST_SAVES)
        with patch.object(v9,"file_hash") as file_hash,patch.object(v9,"LiveLabProcess") as live:
            with self.assertRaises(ValueError):
                v9.verify_test_save(positive,save_root=Path("synthetic-not-opened"))
            file_hash.assert_not_called();live.assert_not_called()

    def test_nav_foi_allowed_only_in_new_protocol(self):
        for target in ("NAV","FOI"):
            record=dict(self.record,target=target)
            self.assertEqual(v9.decode_request(v9.encode_request(record)),record)
            with self.assertRaises(ValueError):
                v6.encode_request(record)
        raw=v9.encode_request(dict(self.record,target="ENG"))
        with self.assertRaises(ValueError):
            v6.decode_request(raw)
        with self.assertRaises(ValueError):
            v9.decode_request(raw.replace(b"EU4LAB/2",b"EU4LAB/1"))

    def test_fixture_has_two_fixed_actions_and_no_script_or_target_escape(self):
        fixture=dict(self.record,operation="fixture",mode="submit",actor="FRA",target="FRA",action="fixture_on")
        for action in v9.FIXTURE_ACTIONS:
            row=dict(fixture,action=action)
            self.assertEqual(v9.decode_request(v9.encode_request(row)),row)
        for fields in (dict(action="event llmt.1"),dict(action="llmt.1"),dict(action="fixture_on\nscript=x"),
                       dict(target="NAV"),dict(actor="ENG"),dict(mode="legality_only"),dict(speed=1),dict(script="llmt.1")):
            with self.subTest(fields=fields),self.assertRaises(ValueError):
                v9.encode_request(dict(fixture,**fields))

    def test_submit_actor_remains_fra_even_with_extended_tags(self):
        evidence={"last_sequence":0,"latest_frame":{"running_speed_enabled":True}}
        metadata={"pid":1234,"process_creation_filetime":self.record["creation"]}
        for actor in ("NAV","FOI","ENG","POR"):
            with self.assertRaises(ValueError):
                v9.prepare_request(metadata,evidence,sequence=1,operation="pair",mode="submit",action="guarantee",
                                   actor=actor,target="FRA",speed=0,ttl_ms=5000,now=1400)

    def test_incomplete_fixture_contract_cannot_publish_or_record_build(self):
        with patch.object(v9,"FIXTURE_EVENT_CONTRACT_READY",False),patch.object(v9,"FIXTURE_SOURCES",()):
            with self.assertRaises(ValueError):
                v9.prepare_request({"pid":1234,"process_creation_filetime":self.record["creation"]},
                    {"last_sequence":0,"latest_frame":{}},sequence=1,operation="fixture",mode="submit",action="fixture_on",
                    actor="FRA",target="FRA",speed=0,ttl_ms=5000,now=1400)
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                (root/v9.DLL_NAME).write_bytes(b"fake DLL, never loaded")
                with self.assertRaises(ValueError):
                    v9.record_build(root,root)
                self.assertFalse((root/"build.json").exists())

    def test_cli_v9_stops_before_process_access_without_final_manifest(self):
        with patch.object(v9,"verify_build",side_effect=ValueError("incomplete v9 fixture contract")), \
             patch.object(v9,"LiveLabProcess") as live,patch.object(v9,"publish_research") as publish, \
             contextlib.redirect_stderr(io.StringIO()):
            result=cli.main(["--pid","1234","--creation",self.record["creation"],"fixture","fixture_on","--sequence","1","--publish"])
            self.assertEqual(result,2)
            live.assert_not_called();publish.assert_not_called()

    def test_fixture_completed_callback_is_not_effect_verification(self):
        fixture=self.session_fixture()
        self.fixture_events(fixture)
        result=v9.read_evidence(fixture.session,fixture.metadata)
        self.assertFalse(result["pending"])
        self.assertTrue(result["requests"][1]["complete"]["callback_returned"])
        self.assertFalse(result["requests"][1]["complete"]["fixture_effect_verified"])

    def test_wrong_profile_action_cleanup_or_outer_ack_rejected(self):
        fixture=self.session_fixture();self.fixture_events(fixture)
        original=deepcopy(fixture.events)
        for mutation in (lambda:fixture.events[-2]["record"].update(fixture_profile_sha256="0"*64),
                         lambda:fixture.events[-2]["record"].update(fixture_event="llmt.2"),
                         lambda:fixture.events[-2]["record"].update(result_destroyed=False),
                         lambda:fixture.events[-2]["record"].update(callback_flag_restored=False),
                         lambda:fixture.events[-1].update(callback_success=False),
                         lambda:fixture.events[-1].update(fixture_effect_verified=True),
                         lambda:fixture.events[-2]["record"].update(exception_code=False)):
            fixture.events=deepcopy(original);mutation();fixture.write()
            with self.assertRaises(ValueError):
                v9.read_evidence(fixture.session,fixture.metadata)

    def test_fixture_permanent_proof_is_required_and_process_bound(self):
        fixture=self.session_fixture();self.fixture_events(fixture)
        proof=fixture.session/"00000000000000000001.fixture-profile"
        proof.write_bytes(v9.fixture_proof_wire(dict(fixture.metadata,pid=9),1))
        with self.assertRaises(ValueError):
            v9.read_evidence(fixture.session,fixture.metadata)
        proof.unlink()
        with self.assertRaises(OSError):
            v9.read_evidence(fixture.session,fixture.metadata)

    def test_publication_proof_precedes_request_and_failed_proof_never_publishes(self):
        fixture=self.session_fixture()
        evidence=v9.read_evidence(fixture.session,fixture.metadata)
        proof=dict(pid=fixture.pid,creation=fixture.creation,profile_sha256=v9.FIXTURE_PROFILE_SHA256,
                   fixture_definition_files_verified=True,installed_before_process_creation=True,engine_registration_verified=False)
        with patch.object(v9,"_private_root"):
            result=v9.publish_research(fixture.session,fixture.metadata,"a"*64,evidence,fixture.live,sequence=1,
                operation="fixture",mode="submit",action="fixture_on",actor="FRA",target="FRA",clock=lambda:1400,
                fixture_check=lambda:proof)
        self.assertEqual(result["status"],"published")
        sidecar=fixture.session/"00000000000000000001.fixture-profile"
        self.assertEqual(sidecar.read_bytes(),v9.fixture_proof_wire(fixture.metadata,1))
        (fixture.session/"00000000000000000001.request").unlink()
        with patch.object(v9,"_private_root"),self.assertRaises(OSError):
            v9.publish_research(fixture.session,fixture.metadata,"a"*64,evidence,fixture.live,sequence=1,
                operation="fixture",mode="submit",action="fixture_on",actor="FRA",target="FRA",clock=lambda:1400,
                fixture_check=lambda:proof)

    def test_installed_profile_hash_enabled_descriptor_and_precreation_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root,user,profile,digest=self.installation_fixture(directory)
            creation=f'{116444736000000000+2000000000*10000000:016x}'
            with patch.object(v9,"FIXTURE_PROFILE_SHA256",digest):
                result=v9.verify_installed_fixture({"fixture_profile":profile},1234,creation,root=root,user_root=user)
                self.assertTrue(result["fixture_definition_files_verified"])
                self.assertFalse(result["engine_registration_verified"])
                config=user/"dlc_load.json"
                os.utime(config,ns=(2100000000*10**9,2100000000*10**9))
                with self.assertRaises(ValueError):
                    v9.verify_installed_fixture({"fixture_profile":profile},1234,creation,root=root,user_root=user)
                os.utime(config,ns=(1900000000*10**9,1900000000*10**9))
                config.write_text('{"enabled_mods":[]}',encoding="utf-8")
                with self.assertRaises(ValueError):
                    v9.verify_installed_fixture({"fixture_profile":profile},1234,creation,root=root,user_root=user)

    def test_v9_manifest_binds_all_native_and_fixed_fixture_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root,user,profile,digest=self.installation_fixture(directory)
            output=root/"output";output.mkdir()
            (output/v9.DLL_NAME).write_bytes(b"synthetic-not-executable")
            for name in v9.SOURCES:
                source=root/name;source.parent.mkdir(parents=True,exist_ok=True)
                source.write_text("synthetic",encoding="utf-8")
            (root/"work/native/v9/research-lab-1375.cpp").write_text("static constexpr bool running_speed_enabled = true;",encoding="utf-8")
            with patch.object(v9,"FIXTURE_PROFILE_SHA256",digest):
                manifest=v9.record_build(root,output)
                self.assertEqual(manifest["fixture_profile"],profile)
                self.assertEqual(v9.verify_build(root,output)[0],manifest)
                v9.fixture_source_path(root,v9.FIXTURE_SOURCES[-1]).write_text("modified",encoding="utf-8")
                with self.assertRaises(ValueError):
                    v9.verify_build(root,output)


if __name__=="__main__":
    unittest.main()
