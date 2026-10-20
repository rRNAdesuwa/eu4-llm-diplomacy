import copy,unittest
from model import Batch,FAMILIES,GAME,OLD_DLL,PROTOCOL,PURPOSE,encode_request,decode_request

def binding():
    return dict(pid=1234,thread=5678,date=56456976,world=0x100000,database=0x200000,countries=0x300000,
      server=0x400000,holder=0x500000,context=0x600000,transport=0x700000,creation='01dd000000000001',
      session='1'*32,dll_sha256='2'*64,manifest_sha256='3'*64,
      actor_handle='0100007a00415246',target_handle='0100002e00474e45',player_handle='0100007a00415246')
def request(s,expires=60000):
    return dict(protocol=PROTOCOL,purpose=PURPOSE,game_sha256=GAME,sequence=4,expires=expires,
      operation='submit_fixed_spy5',actor='FRA',target='ENG',profile='spy5_true_state0_envoy_minus1_v19',
      **{k:s[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256')})
def ready(expires=60000):
    s=binding();m=Batch(s)
    for n in range(1,4):m.phase(n,s,n,n,core_passed=True,later_clean_health=True)
    m.claim(encode_request(request(s,expires)),s,4,4,exclusive_durable=True,initial_sha256='4'*64)
    return m,s
def prefix(m,s,through='gate'):
    f=m.frame+1;t=m.now+1
    events=[('item_claim',dict(family=FAMILIES[len(m.rows)],durable=True)),('factory',dict(verified=True)),
      ('initialize',dict(verified=True)),('preview',dict(allowed=True)),('wrapper',dict(verified=True)),('gate',dict(allowed=True))]
    for k,d in events:
        m.event(k,s,f,t,**d)
        if k==through:break
    return f,t
def dispatched(m,s):
    f,t=prefix(m,s)
    for k,d in [('destroy_original',dict(returned=True)),('dispatch_intent',dict(durable=True)),
      ('submit_enter',dict(guard_passed=True)),('submit_result',dict(returned=True,accepted=True,consumed=True))]:m.event(k,s,f,t,**d)
    m.event('health',s,f+1,t+1,healthy=True)

class ModelTests(unittest.TestCase):
    def test_complete_five_is_only_model_dispatch_and_final(self):
        m,s=ready()
        for _ in FAMILIES:dispatched(m,s)
        m.observe_final(s,m.frame+1,m.now+1,'5'*64);r=m.summary()
        self.assertTrue(r['all_five_dispatched']);self.assertEqual(len(r['rows']),5)
        for k in ('native_calls_performed','native_runtime_verified','effect_verified','production_ready','strict_sp_verified','actual_journal_validated'):self.assertIs(r[k],False)
    def test_every_preview_rejection_cleans_original_and_continues(self):
        m,s=ready()
        for _ in FAMILIES:
            f,t=prefix(m,s,'initialize');m.event('preview',s,f,t,allowed=False)
            m.event('destroy_original',s,f,t,returned=True);m.event('health',s,f+1,t+1,healthy=True)
        self.assertEqual(m.state,'complete');self.assertFalse(m.summary()['all_five_dispatched'])
    def test_gate_reject_destroys_command_with_clone_then_original(self):
        m,s=ready();f,t=prefix(m,s,'wrapper');m.event('gate',s,f,t,allowed=False)
        m.event('destroy_command',s,f,t,returned=True);self.assertEqual(m.owned,{'original'})
        m.event('destroy_original',s,f,t,returned=True);m.event('health',s,f+1,t+1,healthy=True)
        self.assertEqual(m.rows[0]['outcome'],'command_gate_rejected')
    def test_reject_cannot_forge_submit(self):
        m,s=ready();f,t=prefix(m,s,'initialize');m.event('preview',s,f,t,allowed=False)
        with self.assertRaises(ValueError):m.event('submit_enter',s,f,t,guard_passed=True)
    def test_false_or_unreturned_or_unconsumed_transfer_freezes_no_cleanup(self):
        for returned,accepted,consumed in [(True,False,True),(True,True,False),(False,None,None),(True,None,True)]:
            m,s=ready();f,t=prefix(m,s)
            for k,d in [('destroy_original',dict(returned=True)),('dispatch_intent',dict(durable=True)),('submit_enter',dict(guard_passed=True))]:m.event(k,s,f,t,**d)
            with self.assertRaises(ValueError):m.event('submit_result',s,f,t,returned=returned,accepted=accepted,consumed=consumed)
            self.assertTrue(m.entered);self.assertEqual(m.owned,set())
            with self.assertRaises(ValueError):m.event('destroy_command',s,f,t,returned=True)
    def test_no_read_or_destructor_for_transferred_object(self):
        m,s=ready();dispatched(m,s)
        with self.assertRaises(ValueError):m.event('destroy_command',s,m.frame,m.now,returned=True)
    def test_unknown_factory_and_wrapper_stop_without_guessed_cleanup(self):
        for upto,kind in [('item_claim','factory'),('preview','wrapper')]:
            m,s=ready();f,t=prefix(m,s,upto)
            with self.assertRaises(ValueError):m.event(kind,s,f,t,verified=False)
            self.assertTrue(m.frozen)
    def test_claims_and_dispatch_audit_must_be_durable(self):
        m,s=ready()
        with self.assertRaises(ValueError):m.event('item_claim',s,5,5,family=FAMILIES[0],durable=False)
        m,s=ready();f,t=prefix(m,s);m.event('destroy_original',s,f,t,returned=True)
        with self.assertRaises(ValueError):m.event('dispatch_intent',s,f,t,durable=False)
    def test_later_owner_frame_and_final_health_mandatory(self):
        m,s=ready()
        with self.assertRaises(ValueError):m.event('item_claim',s,4,5,family=FAMILIES[0],durable=True)
        m,s=ready();f,t=prefix(m,s,'initialize');m.event('preview',s,f,t,allowed=False);m.event('destroy_original',s,f,t,returned=True)
        with self.assertRaises(ValueError):m.event('health',s,f,t,healthy=True)
    def test_no_middle_census(self):
        m,s=ready();dispatched(m,s)
        with self.assertRaises(ValueError):m.observe_final(s,m.frame+1,m.now+1,'5'*64)
    def test_same_date_roots_generation_and_thread_exact(self):
        for k in ('date','thread','pid','world','context','transport','player_handle','target_handle','creation'):
            m,s=ready();bad=copy.deepcopy(s);bad[k]=bad[k]+8 if type(bad[k]) is int else '0'*len(bad[k])
            with self.assertRaises(ValueError,msg=k):m.event('item_claim',bad,5,5,family=FAMILIES[0],durable=True)
    def test_typed_int_aliases_rejected(self):
        for k in ('pid','thread','date','world'):
            for value in [True,float(binding()[k])]:
                s=binding();s[k]=value
                with self.assertRaises(ValueError):Batch(s)
        for key in ('pid','sequence','expires'):
            r=request(binding());r[key]=float(r[key])
            with self.assertRaises(ValueError):encode_request(r)
    def test_bool_aliases_not_accepted_at_native_boundaries(self):
        for bad in (1,0,1.0,None,'true'):
            m,s=ready();f,t=prefix(m,s,'initialize')
            with self.assertRaises(ValueError):m.event('preview',s,f,t,allowed=bad)
    def test_cleanup_may_cross_ttl_but_next_native_work_cannot(self):
        m,s=ready(expires=10);f,t=prefix(m,s,'initialize');m.event('preview',s,f,t,allowed=False)
        m.event('destroy_original',s,f,11,returned=True);m.event('health',s,f+1,12,healthy=True)
        with self.assertRaises(ValueError):m.event('item_claim',s,f+2,13,family=FAMILIES[1],durable=True)
    def test_final_guard_ttl_equality_is_rejected(self):
        m,s=ready(expires=10);f,t=prefix(m,s);m.event('destroy_original',s,f,t,returned=True);m.event('dispatch_intent',s,f,t,durable=True)
        with self.assertRaises(ValueError):m.event('submit_enter',s,f,10,guard_passed=True)
        self.assertFalse(m.entered)
    def test_expiry_bounds_claim_and_new_version(self):
        for expiry in (4,60005):
            s=binding();m=Batch(s)
            for n in range(1,4):m.phase(n,s,n,n,core_passed=True,later_clean_health=True)
            with self.assertRaises(ValueError):m.claim(encode_request(request(s,expiry)),s,4,4,exclusive_durable=True,initial_sha256='4'*64)
        r=request(binding());r['dll_sha256']=OLD_DLL
        with self.assertRaises(ValueError):encode_request(r)
    def test_one_batch_and_exact_family_order(self):
        m,s=ready()
        with self.assertRaises(ValueError):m.claim(encode_request(request(s)),s,5,5,exclusive_durable=True,initial_sha256='4'*64)
        m,s=ready()
        with self.assertRaises(ValueError):m.event('item_claim',s,5,5,family=FAMILIES[1],durable=True)
    def test_request_rejects_addresses_modes_control_old_protocol_and_duplicates(self):
        for key in ('rva','pointer','envoy','mode','accept_all','script','target_handle'):
            r=request(binding());r[key]=1
            with self.assertRaises(ValueError):encode_request(r)
        r=request(binding());raw=encode_request(r)
        self.assertEqual(decode_request(raw),r)
        for bad in [raw.replace(PROTOCOL.encode(),b'EU4SPYLAB/1'),raw.replace(b'"pid":1234',b'"pid":1234,"pid":1234'),raw+b' ',raw.replace(b'1234',b'1234.0')]:
            with self.assertRaises(ValueError):decode_request(bad)
    def test_phase_failure_and_skips_do_not_rearm(self):
        for number,passed in [(2,True),(1,False),(True,True)]:
            s=binding();m=Batch(s)
            with self.assertRaises(ValueError):m.phase(number,s,1,1,core_passed=passed,later_clean_health=True)
            self.assertTrue(m.frozen)
    def test_all_fault_positions_are_terminal(self):
        for upto in ('item_claim','factory','initialize','preview','wrapper','gate'):
            m,s=ready();f,t=prefix(m,s,upto)
            with self.assertRaises(ValueError):m.event('fault',s,f,t,reason='simulated audit failure or SEH')
            self.assertTrue(m.frozen);self.assertFalse(m.summary()['retry_allowed'])

if __name__=='__main__':unittest.main()
