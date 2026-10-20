"""In-memory HTTP dispatch and temporary mailbox; no listener/process/native calls."""
from copy import deepcopy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from test_candidate import HERE, lab
import test_integration as integration
from bridge.tests.test_diplomacy_lab_http import fake_history

http=integration.load("candidate_v16_http",HERE/"files/bridge/diplomacy_lab_http_v16.py")


class Runtime:
    protocol=lab
    def __init__(self,snapshot):
        self.snapshot=snapshot;self.pid=snapshot["metadata"]["pid"]
        self.creation=snapshot["metadata"]["process_creation_filetime"]
        self.calls=0;self.inspections=0
    def inspect(self):
        self.inspections+=1;return deepcopy(self.snapshot)
    def publish(self,snapshot,request):
        self.calls+=1
        return lab.publish_research(snapshot["session"],snapshot["metadata"],snapshot["manifest_sha256"],
            snapshot["evidence"],snapshot["live"],sequence=request["sequence"],operation="pair",
            mode=request["mode"],action=request["action"],actor=request["actor"],target=request["target"],
            ttl_ms=request["ttl_ms"],clock=lambda:snapshot["now"])


class HTTP(unittest.TestCase):
    def setUp(self):
        self.data=integration.Integration();self.data.setUp();self.addCleanup(self.data.doCleanups)
        self.enterContext(patch.object(http.transport,"make_server",side_effect=AssertionError("No listener")))
        self.snapshot={"session":self.data.f.session,"metadata":self.data.f.metadata,
            "manifest_sha256":"a"*64,"dll_sha256":"B"*64,
            "fixture_disk_evidence":{"fixture_definition_files_verified":True},
            "evidence":self.data.read(),"live":self.data.f.live,"now":self.data.t}
        self.runtime=Runtime(self.snapshot)
        self.service=http.ResearchService(self.runtime,capability_reader=fake_history)
        self.body={"protocol":lab.PROTOCOL,"pid":self.runtime.pid,"creation":self.runtime.creation,
            "sequence":1,"mode":"legality_only","action":"offer_fleet_basing_rights","actor":"FRA","target":"POR","ttl_ms":5000}

    def post(self,**updates):
        return self.service.dispatch("POST",http.PREFIX+"/pair",self.body|updates)

    def test_discovery_explicit_candidate_controls_not_http_or_production(self):
        status,value=self.service.dispatch("GET",http.PREFIX+"/capabilities")
        self.assertEqual(status,200)
        self.assertEqual(set(value["http_pair_contract"]["actions"]),set(lab.ACTIONS))
        self.assertEqual(len(value["http_pair_contract"]["actions"]),36)
        self.assertEqual(value["protocol"],"EU4LAB/3")
        self.assertFalse(value["v16_candidate"]["runtime_verified"])
        self.assertFalse(value["acceptance_control"]["http_accept_endpoint"])
        self.assertFalse(value["production"]);self.assertIsNone(value["live_readiness"])
        self.assertEqual(self.runtime.inspections,0)

    def test_ordinary_pair_serializes_unbound_v3_and_duplicate_is_read_only(self):
        status,value=self.post();self.assertEqual(status,202,value)
        raw=(self.data.f.session/"00000000000000000001.request").read_bytes()
        request=lab.decode_request(raw)
        self.assertEqual((request["bound_action"],request["bound_target"],request["bound_submit_sequence"]),("none","none",0))
        self.assertTrue(raw.startswith(b"EU4LAB/3\n"))
        status,replay=self.post();self.assertEqual(status,200,replay)
        self.assertTrue(replay["replayed"]);self.assertFalse(replay["request_written"])
        self.assertEqual(self.runtime.calls,1)

    def test_control_path_extra_binding_or_old_protocol_is_rejected_before_access(self):
        for changes in ({"protocol":"EU4LAB/2"},{"action":"accept_on"},{"bound_action":"offer_fleet_basing_rights"},
                        {"bound_submit_sequence":3},{"bound_target":"POR"},{"operation":"accept"}):
            with self.subTest(changes=changes):
                status,_=self.post(**changes);self.assertEqual(status,422)
        for path in ("accept","speed","fixture","console"):
            status,_=self.service.dispatch("POST",http.PREFIX+"/"+path,{})
            self.assertEqual(status,404)
        self.assertEqual(self.runtime.inspections,0);self.assertEqual(self.runtime.calls,0)

    def test_active_window_wrong_pair_never_publishes(self):
        self.data.pair(1);self.data.health(1,"closed",0,0);self.data.control(2,True);self.data.health(2,"armed",1)
        self.runtime.snapshot["evidence"]=self.data.read()
        self.runtime.snapshot["live"]["acceptance_flag"]=1
        self.runtime.snapshot["now"]=self.data.t+200
        for changes in ({"mode":"legality_only"},{"mode":"submit","target":"NAV"},
                        {"mode":"submit","action":"offer_alliance"}):
            status,value=self.post(sequence=3,**changes)
            self.assertEqual(status,409,value)
        self.assertEqual(self.runtime.calls,0)
        self.assertFalse((self.data.f.session/"00000000000000000003.request").exists())

    def test_exact_bound_pair_can_publish_once_but_controls_remain_cli_only(self):
        self.data.pair(1);self.data.health(1,"closed",0,0);self.data.control(2,True);self.data.health(2,"armed",1)
        self.runtime.snapshot["evidence"]=self.data.read()
        self.runtime.snapshot["live"]["acceptance_flag"]=1
        self.runtime.snapshot["now"]=self.data.t+200
        status,value=self.post(sequence=3,mode="submit")
        self.assertEqual(status,202,value)
        status,value=self.post(sequence=3,mode="submit")
        self.assertEqual(status,200,value);self.assertEqual(self.runtime.calls,1)
        self.assertFalse(value["applied_verified"])

    def test_busy_and_post_off_health_wait_remain_guarded(self):
        self.service._lock.acquire()
        try:
            status,value=self.post();self.assertEqual(status,409);self.assertEqual(value["error"]["code"],"service_busy")
        finally:self.service._lock.release()
        self.runtime.snapshot["evidence"]["acceptance_window"]["state"]="awaiting_health"
        status,value=self.post();self.assertEqual(status,409,value);self.assertEqual(self.runtime.calls,0)


if __name__=="__main__":unittest.main()
