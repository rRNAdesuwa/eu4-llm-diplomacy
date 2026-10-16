import http.client
import json
import threading
import unittest

from bridge.tag_command_service import make_server
from bridge.tests import test_tag_command_backend as fixtures


class TagCommandHTTPTests(unittest.TestCase):
    event = fixtures.TagCommandTests.event
    # Reuse the offline DLL/session fixture; no real process is ever opened.
    def setUp(self):
        fixtures.TagCommandTests.setUp(self)
        self.server = make_server(self.backend,self.identity,port=0,token="offline-test-token-123")
        self.thread = threading.Thread(target=self.server.serve_forever,kwargs={"poll_interval":0.01})
        self.thread.start()
        self.addCleanup(self.stop_server)
    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
    def call(self,method,path,body=None,authorized=True):
        connection = http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=2)
        try:
            headers = {"Content-Type":"application/json"}
            if authorized:
                headers["Authorization"] = "Bearer offline-test-token-123"
            connection.request(method,path,json.dumps(body) if body is not None else None,headers)
            response = connection.getresponse()
            return response.status,json.loads(response.read())
        finally:
            connection.close()
    def test_http_command_reaches_native_request_transport(self):
        status,value = self.call("POST","/native/v1/commands",self.command)
        self.assertEqual(status,202)
        self.assertEqual(value["published"][0]["actor"],"POR")
        self.assertIn(b"actor=POR\ntarget=BRI",(self.directory/"1.request").read_bytes())
        status,value = self.call("GET","/native/v1/commands/"+self.command["request_id"])
        self.assertEqual((status,value["state"]),(200,"published"))
    def test_http_duplicate_is_status_only(self):
        self.call("POST","/native/v1/commands",self.command)
        status,value = self.call("POST","/native/v1/commands",self.command)
        self.assertEqual(status,200)
        self.assertTrue(value["reused"])
        self.assertEqual(len(list(self.directory.glob("*.request"))),1)
    def test_http_missing_token_cannot_publish(self):
        status,_ = self.call("POST","/native/v1/commands",self.command,False)
        self.assertEqual(status,403)
        self.assertFalse(list(self.directory.glob("*.request")))
    def test_http_unknown_action_cannot_publish(self):
        status,_ = self.call("POST","/native/v1/commands",dict(self.command,action="unknown"))
        self.assertEqual(status,422)
        self.assertFalse(list(self.directory.glob("*.request")))
    def test_http_batch_preserves_distinct_actor_and_request_ids(self):
        second = dict(self.command,request_id="http-batch-2",actor="ENG",action="trade_favors_for_men")
        status,value = self.call("POST","/native/v1/batches",[self.command,second])
        self.assertEqual(status,202)
        self.assertEqual([r["request_id"] for r in value["published"]],
                         [self.command["request_id"],second["request_id"]])
        self.assertIn(b"actor=ENG\ntarget=BRI",(self.directory/"2.request").read_bytes())
    def test_http_capabilities_declare_pause_deadline_and_retry_contract(self):
        status,value = self.call("GET","/native/v1/capabilities")
        self.assertEqual(status,200)
        self.assertTrue(value["requires_explicit_manual_pause"])
        self.assertEqual(value["batch_expiry"]["maximum_ttl_ms"],60000)
        self.assertFalse(value["automatic_retry"])
    def test_http_parameterized_command_is_rejected_before_publication(self):
        status,_ = self.call("POST","/native/v1/commands",dict(self.command,parameters={"amount":100}))
        self.assertEqual(status,422)
        self.assertFalse(list(self.directory.glob("*.request")))
