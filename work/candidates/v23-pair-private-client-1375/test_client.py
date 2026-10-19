"""Analysis-owned synthetic logs; no process handles, injection or game access."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('private_client',HERE/'client.py');client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
FIXTURE=Path(sys.argv.pop(1));ID=client.identity(77,'01dd123456789012','1'*32,{'dll':{'sha256':'a'*64}})
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='synthetic-log-',dir=HERE);self.old=client.BUILD;client.BUILD=Path(self.temp.name)
  self.path=client.session_path(ID);self.path.mkdir();self.rows=[]
 def tearDown(self):client.BUILD=self.old;self.temp.cleanup()
 def row(self,event,sequence=0,**extra):
  r=dict(schema='EU4PAIRNOSEND/1',event=event,**ID,owner_thread=99,thread=99,ordinal=len(self.rows)+1,uptime_ms=100+len(self.rows),sequence=sequence,no_send=True,production_ready=False)
  r.update(extra);self.rows.append(r);return r
 def start(self):
  self.row('bootstrap_verified',native_environment_initialized=True,game_sha256=client.GAME_SHA,strict_SP_verified=False,world_epoch_verified=False)
  self.row('hook_attempt',detail=dict(event='hook_install_attempt',attempt=1,result=0,send_supported=False))
  self.row('hook_installed',request_limit=64,automatic_action=False,hot_unload_supported=False)
 def action(self,seq,status=4):
  action=client.ACTIONS[seq-1];expires=10000
  wire=client.request(ID,seq,expires,action)
  for suffix in ['request','claim']:(self.path/f'{seq}.{suffix}').write_bytes(wire)
  intent=dict(identity=ID,actions=client.ACTIONS,expires=expires,no_send=True,request_sha256=[client.sha(client.request(ID,i+1,expires,a)) for i,a in enumerate(client.ACTIONS)])
  (self.path/'positive-six.publisher-intent.json').write_bytes(client.encoded(intent))
  self.row('request_claimed',seq,action=action,actor='FRA',target='ENG',expires=expires)
  calls={0:[0],1:[],2:[0,1,2,5],3:[0,1,2,3,4,5,6],4:[0,1,2,3,4,5,6]}[status]
  for call in calls:
   self.row('native_call_begin',seq,call=call,family=seq-1)
   self.row('native_call_return',seq,call=call,normal=True,boolean=(status!=2 or call!=2) and (status!=3 or call!=4),returned_same_slot=True,exception=0)
  reason={0:'normal_factory_null',1:'final_factory_guard',2:'full88_normal_false',3:'command_gate_normal_false',4:'synthetic_lifecycle_no_send'}[status]
  self.row('request_result',seq,status=status,reason=reason,adapter_call_attempts=len(calls),owned_issued=3 if status in (3,4) else 1 if status==2 else 0,
   owned_live=0,quarantined=0,adapter_fault=0,known_cleanup_complete=True,submitted=False)
 def inspect(self):
  (self.path/'events.jsonl').write_bytes(b''.join(client.encoded(r).replace(b'\n',b'')+b'\n' for r in self.rows))
  return client.inspect(ID)
 def test_cpp_wire_matches_python(self):
  lines=FIXTURE.read_text().splitlines();expected=[client.boot(ID)]+[client.request(ID,i+1,123456,a) for i,a in enumerate(client.ACTIONS)]
  self.assertEqual([bytes.fromhex(x) for x in lines],expected)
 def test_request_and_identity_bounds(self):
  for seq,expiry,action in [(True,1,'guarantee'),(0,1,'guarantee'),(65,1,'guarantee'),(1,True,'guarantee'),(1,0,'guarantee'),(1,2**64,'guarantee'),(1,1,'unknown'),(1,1,[]),(1,1,'stop_currying_favors')]:
   with self.subTest(seq=seq,expiry=expiry,action=action),self.assertRaises(ValueError):client.request(ID,seq,expiry,action)
  for pid,creation,session in [(True,ID['creation'],ID['session']),(0,ID['creation'],ID['session']),(77,1,ID['session']),(77,'0'*16,ID['session']),(77,ID['creation'],'0'*32)]:
   with self.subTest(pid=pid,creation=creation,session=session),self.assertRaises(ValueError):client.identity(pid,creation,session,{'dll':{'sha256':'a'*64}})
 def test_json_rejects_duplicates_and_nonfinite(self):
  for b in [b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}']:
   with self.subTest(b=b),self.assertRaises(ValueError):client.value(b)
 def test_initial_ready_is_not_complete(self):
  self.start();s=self.inspect();self.assertFalse(s['complete']);self.assertFalse(s['terminal']);self.assertEqual(s['results'],[])
 def test_complete_six_all_cleanup_paths(self):
  self.start()
  for i in range(6):self.action(i+1,[0,1,2,3,4,4][i])
  s=self.inspect();self.assertTrue(s['complete']);self.assertEqual(len(s['results']),6)
 def test_partial_request_is_not_success(self):
  self.start();self.action(1);self.rows.pop();s=self.inspect();self.assertFalse(s['complete']);self.assertEqual(s['pending_sequence'],1)
 def test_audit_identity_types_order_and_clock(self):
  self.start();self.action(1);base=copy.deepcopy(self.rows)
  for key,val in [('pid',True),('ordinal',True),('owner_thread',True),('uptime_ms',False),('sequence',True),('production_ready',True),('extra',1)]:
   with self.subTest(key=key):
    self.rows=copy.deepcopy(base);self.rows[3][key]=val
    with self.assertRaises(ValueError):self.inspect()
  self.rows=copy.deepcopy(base);self.rows[4]['uptime_ms']=1
  with self.assertRaises(ValueError):self.inspect()
 def test_missing_hook_and_duplicate_request(self):
  self.start();self.action(1);base=copy.deepcopy(self.rows);self.rows[2]['event']='bootstrap_verified'
  with self.assertRaises(ValueError):self.inspect()
  self.rows=base;self.rows[4]=dict(self.rows[3],ordinal=5,uptime_ms=104)
  with self.assertRaises(ValueError):self.inspect()
 def test_return_pair_and_owner(self):
  self.start();self.action(1);base=copy.deepcopy(self.rows)
  for index,key,val in [(5,'call',1),(4,'family',1),(4,'thread',100),(5,'normal',1)]:
   with self.subTest(index=index,key=key):
    self.rows=copy.deepcopy(base);self.rows[index][key]=val
    with self.assertRaises(ValueError):self.inspect()
 def test_request_and_claim_and_intent_tampering(self):
  self.start();self.action(1)
  for suffix in ['claim','request']:
   p=self.path/f'1.{suffix}';old=p.read_bytes();p.write_bytes(old.replace(b'target=ENG',b'target=POR'))
   with self.subTest(suffix=suffix),self.assertRaises(ValueError):self.inspect()
   p.write_bytes(old)
  p=self.path/'positive-six.publisher-intent.json';d=json.loads(p.read_bytes());d['request_sha256'][0]='0'*64;p.write_bytes(client.encoded(d))
  with self.assertRaises(ValueError):self.inspect()
 def test_cleanup_counts_and_normal_returns(self):
  self.start();self.action(1);base=copy.deepcopy(self.rows)
  for key,val in [('owned_live',1),('quarantined',1),('adapter_fault',1),('owned_issued',2),('adapter_call_attempts',6),('submitted',True)]:
   with self.subTest(key=key):
    self.rows=copy.deepcopy(base);self.rows[-1][key]=val
    with self.assertRaises(ValueError):self.inspect()
  self.rows=copy.deepcopy(base);self.rows[-2]['normal']=False
  with self.assertRaises(ValueError):self.inspect()
 def test_missing_destructor_cannot_claim_cleanup(self):
  self.start();self.action(1);self.rows[-3]['call']=5;self.rows[-2]['call']=5
  with self.assertRaises(ValueError):self.inspect()
 def test_frozen_stops_all_following_actions(self):
  self.start();self.action(1);self.rows[-1].update(status=5,known_cleanup_complete=False,owned_live=3,quarantined=3,adapter_fault=14)
  self.row('terminal',1,unknown_no_retry=True);s=self.inspect();self.assertTrue(s['terminal']);self.assertFalse(s['complete'])
  self.action(2)
  with self.assertRaises(ValueError):self.inspect()
 def test_lease_rejection_and_truncated_record(self):
  self.start();self.action(1);self.rows=self.rows[:4];self.row('lease_rejected',1,native_call_attempts=0,unknown_no_retry=True);self.row('terminal',1,unknown_no_retry=True)
  self.assertTrue(self.inspect()['terminal'])
  p=self.path/'events.jsonl';p.write_bytes(p.read_bytes()[:-1])
  with self.assertRaises(ValueError):client.inspect(ID)
 def test_file_links_and_path_escape(self):
  p=self.path/'ordinary';p.write_bytes(b'one');self.assertEqual(client.raw(p,3),b'one')
  with self.assertRaises(ValueError):client.raw(p,2)
  with self.assertRaises(ValueError):client.raw(Path('C:/outside-untrusted'),3)
if __name__=='__main__':unittest.main()
