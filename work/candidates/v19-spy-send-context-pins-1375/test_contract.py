import unittest
from copy import deepcopy
import contract as c


def stamp():
    base=0x140000000
    return dict(module_base=base,game=0x100000,database=0x200000,countries=0x300000,
      actor_country=0x400000,target_country=0x500000,server=0x600000,holder=0x700000,
      context=0x800000,transport=0x900000,server_vtable=base+0x1cb8460,
      context_getter=base+0x811aa0,transport_vtable=base+0x1d96178,
      transport_submit=base+0x1580370,transport_queue_getter=base+0x8b0e0,
      pid=1234,owner_thread=5678,thread=5678,date=56456976,frame_call=50,uptime_ms=100,
      ready55=1,ready80d=0,creation='01dd000000000001',session='1'*32,
      exe_sha256=c.GAME_SHA,dll_sha256='2'*64,manifest_sha256='3'*64,
      actor_handle=c.HANDLES['actor_handle'],player_handle=c.HANDLES['player_handle'],
      target_handle=c.HANDLES['target_handle'])


class ContractTests(unittest.TestCase):
    def test_stable_typed_stamp_grants_no_authority(self):
        a=stamp();b={**a,'uptime_ms':101};r=c.check_fresh(a,b,now_ms=101,expires_ms=200)
        self.assertTrue(r['restricted_readiness_path_candidate'])
        for k in ('submit_permission','raw_graph_authenticated','actual_guard_verified','lifetime_verified',
                  'strict_sp_verified','world_epoch_verified','runtime_verified','production_ready'):
            self.assertIs(r[k],False)

    def test_every_numeric_alias_rejected(self):
        for key in set(c.PTR_FIELDS)|set(c.INT_FIELDS)|set(c.HANDLES):
            for bad in (True,float(stamp()[key])):
                s=stamp();s[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):c.validate_stamp(s)

    def test_every_missing_or_extra_field_rejected(self):
        for key in c.KEYS:
            s=stamp();del s[key]
            with self.assertRaises(ValueError,msg=key):c.validate_stamp(s)
        for key in ('context_vtable','strict_sp_verified','ready','rva','arbitrary_target'):
            s=stamp();s[key]=True
            with self.assertRaises(ValueError):c.validate_stamp(s)

    def test_all_pointer_bounds_and_alignment(self):
        for key in c.PTR_FIELDS:
            for bad in (0,0xffff,0x800000000000,-1):
                s=stamp();s[key]=bad
                with self.assertRaises(ValueError):c.validate_stamp(s)
            if key not in c.CODE_FIELDS:
                s=stamp();s[key]+=1
                with self.assertRaises(ValueError):c.validate_stamp(s)

    def test_every_fixed_slot_binding(self):
        for key in ('server_vtable','context_getter','transport_vtable','transport_submit','transport_queue_getter'):
            s=stamp();s[key]+=8
            with self.assertRaises(ValueError):c.validate_stamp(s)

    def test_false_is_not_raw_ready_byte(self):
        for key in ('ready55','ready80d'):
            for bad in (False,True,-1,256,0.0,None):
                s=stamp();s[key]=bad
                with self.assertRaises(ValueError):c.validate_stamp(s)

    def test_native_byte_nonzero_or_including_values_above_one(self):
        for a,b in ((0,0),(1,0),(0,1),(128,0),(0,255),(255,255)):
            s=stamp();s.update(ready55=a,ready80d=b)
            r=c.check_fresh(s,s,now_ms=100,expires_ms=200)
            self.assertEqual(r['readiness_nonzero'],a!=0 or b!=0)
            self.assertIs(r['submit_permission'],False)

    def test_all_private_cookies_rechecked_at_same_frame(self):
        for key in ('game','database','countries','actor_country','target_country','server','holder','context','transport','date','frame_call'):
            a=stamp();b=deepcopy(a);b[key]+=8
            with self.assertRaises(ValueError,msg=key):c.check_fresh(a,b,now_ms=100,expires_ms=200)

    def test_changed_ready_byte_even_nonzero_rejected(self):
        a=stamp();b={**a,'ready55':2}
        with self.assertRaises(ValueError):c.check_fresh(a,b,now_ms=100,expires_ms=200)

    def test_time_ttl_equality_and_rollback_rejected(self):
        for after,now,expiry in ((100,100,100),(99,99,200),(101,102,200),(100,True,200),(100,100,200.0)):
            a=stamp();b={**a,'uptime_ms':after}
            with self.assertRaises(ValueError):c.check_fresh(a,b,now_ms=now,expires_ms=expiry)

    def test_full_generation_and_player_binding(self):
        for key in c.HANDLES:
            for wrong in (stamp()[key]^(1<<48),122,'FRA'):
                s=stamp();s[key]=wrong
                with self.assertRaises(ValueError):c.validate_stamp(s)

    def test_session_build_and_thread_change(self):
        for key in ('creation','session','dll_sha256','manifest_sha256'):
            a=stamp();b={**a,key:'a'*len(a[key])}
            with self.assertRaises(ValueError):c.check_fresh(a,b,now_ms=100,expires_ms=200)
        a=stamp();a['thread']+=1
        with self.assertRaises(ValueError):c.validate_stamp(a)

    def test_canonical_strings_and_exact_exe(self):
        for key in c.TEXT_FIELDS:
            for bad in (0,'0'*c.TEXT_FIELDS[key],'a'*(c.TEXT_FIELDS[key]-1),'G'*c.TEXT_FIELDS[key]):
                s=stamp();s[key]=bad
                with self.assertRaises(ValueError):c.validate_stamp(s)
        s=stamp();s['exe_sha256']='a'*64
        with self.assertRaises(ValueError):c.validate_stamp(s)

    def test_stamp_copy_cannot_modify_original(self):
        a=stamp();b=c.validate_stamp(a);b['context']+=8
        self.assertNotEqual(a['context'],b['context'])

    def test_ack_is_not_applied_or_cleanup_permission(self):
        r=c.transfer_observation(entered=True,returned=True,accepted=True,slot_null=True,exception_code=0)
        self.assertEqual(r['outcome'],'transport_acknowledged')
        self.assertTrue(r['caller_ownership_relinquished']);self.assertFalse(r['freeze_required'])
        for k in ('effect_verified','execution_permission','read_or_destroy_transferred_command_allowed','retry_allowed'):
            self.assertIs(r[k],False)

    def test_every_nonack_transferred_result_is_frozen(self):
        for returned in (False,True):
            for accepted in (None,False,True):
                for slot in (None,False,True):
                    for exc in (0,0xc0000005):
                        r=c.transfer_observation(entered=True,returned=returned,accepted=accepted,slot_null=slot,exception_code=exc)
                        good=returned and accepted is True and slot is True and exc==0
                        self.assertEqual(r['freeze_required'],not good)
                        self.assertTrue(r['caller_ownership_relinquished'])
                        self.assertFalse(r['read_or_destroy_transferred_command_allowed'])

    def test_unentered_does_not_fabricate_return(self):
        r=c.transfer_observation(entered=False,returned=False,accepted=None,slot_null=None,exception_code=0)
        self.assertEqual(r['outcome'],'not_entered');self.assertFalse(r['caller_ownership_relinquished'])
        for key,value in [('returned',True),('accepted',False),('slot_null',True),('exception_code',1)]:
            args=dict(entered=False,returned=False,accepted=None,slot_null=None,exception_code=0);args[key]=value
            with self.assertRaises(ValueError):c.transfer_observation(**args)

    def test_receipt_aliases_rejected(self):
        for key in ('entered','returned','accepted','slot_null','exception_code'):
            for bad in (1.0,'true',[],{}):
                args=dict(entered=True,returned=True,accepted=True,slot_null=True,exception_code=0);args[key]=bad
                with self.assertRaises(ValueError):c.transfer_observation(**args)


if __name__=='__main__':unittest.main()
