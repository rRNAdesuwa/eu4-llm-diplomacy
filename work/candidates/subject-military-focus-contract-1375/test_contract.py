import copy, unittest
import contract_model as m

def snapshot():
    actor=(1<<56)|(122<<32)|0x415246
    target=(1<<56)|(100<<32)|0x56414e
    return dict(pid=100,creation_filetime=123456,date=56456976,game=0x200000,database=0x300000,array=0x400000,count=200,
      player_handle=actor,actor_handle=actor,target_handle=target,actor_subjects=[target],target_overlord=actor,
      dependency=0x500000,definition=0x600000,definition_vtable=0x140000000+0x1ce7488,
      uses_military_focus=1,can_set_mil_focus=1,country_status=1,country_kind=0,focus=0,paused=True,
      selected_country_identity_verified=True,dependency_identity_verified=True,prototype_vtable_verified=True,
      snapshot_identity_verified=True,entitlement='unsupported_tls_identity')

class Contract(unittest.TestCase):
    def test_enum_mapping(self):
        for name,value in m.ENUM.items():self.assertEqual(m.request(dict(actor='FRA',target='NAV',focus=name)),value)
        self.assertEqual(m.ENUM['aggressive'],1);self.assertEqual(m.ENUM['supportive'],2)
    def test_zero_is_real_mode_not_cancel(self):
        self.assertEqual(m.request(dict(actor='FRA',target='NAV',focus='no_focus')),0)
        for v in [False,0,True,1.0,None,'false','cancel',[],{}]:
            with self.subTest(v=v),self.assertRaises(ValueError):m.request(dict(actor='FRA',target='NAV',focus=v))
    def test_request_scope(self):
        for x in [dict(actor='NAV',target='FRA',focus='siege'),dict(actor='FRA',target='POR',focus='siege'),dict(actor='FRA',target='NAV',focus='siege',address=1)]:
            with self.assertRaises(ValueError):m.request(x)
    def test_constructor_defined_ranges(self):
        for poison in (0,0xa5,0xff):
            b=m.ctor(poison);self.assertEqual(m.default_mask(b),0);self.assertEqual(m.get(b,0x50,8),0x2d2d2d)
    def test_each_defined_default_counterexample(self):
        for offset in (0,8,0x10,0x18,0x28,0x30,0x38,0x3c,0x40,0x44,0x48,0x50,0x58):
            b=m.ctor();b[offset]^=1;self.assertNotEqual(m.default_mask(b),0)
    def test_padding_not_contract(self):
        b=m.ctor()
        for o in [0xc,0xf,0x11,0x17,0x20,0x27,0x42,0x43,0x5c,0x5f]:b[o]^=0xff
        self.assertEqual(m.default_mask(b),0)
    def test_extent(self):
        for b in [b'',bytes(95),bytes(97),[0]*96]:
            with self.assertRaises(ValueError):m.default_mask(b)
    def test_clone_all_six_nonzero_handle(self):
        for mode in range(6):
            src=m.ctor();m.put(src,0x50,8,snapshot()['target_handle']);m.put(src,0x58,4,mode)
            before=bytes(src);arg=bytearray(24)+(15).to_bytes(8,'little');out=m.clone(src,arg)
            self.assertIsNot(src,out);self.assertEqual(bytes(src),before)
            for o,n in m.COPY:self.assertEqual(src[o:o+n],out[o:o+n])
            self.assertEqual(arg,bytearray(24)+(15).to_bytes(8,'little'))
    def test_clone_metadata_reset(self):
        src=m.ctor();m.put(src,0x38,4,88);m.put(src,0x3c,4,99);m.put(src,0x4c,4,777)
        out=m.clone(src,bytearray(24)+(15).to_bytes(8,'little'))
        self.assertEqual(m.get(out,0x38,4),88);self.assertEqual(m.get(out,0x4c,4),777);self.assertEqual(m.get(out,0x3c,4),0)
    def test_clone_requires_real_argument_model(self):
        for arg in [None,bytearray(32),bytes(24)+(15).to_bytes(8,'little'),bytearray(31)]:
            with self.assertRaises(ValueError):m.clone(m.ctor(),arg)
    def test_gate_enum_bound(self):
        for mode in range(6):self.assertTrue(m.native_gate_model(1,0,mode))
        for mode in (6,0xffffffff):self.assertFalse(m.native_gate_model(1,0,mode))
        for mode in (-1,True,1.0):
            with self.assertRaises(ValueError):m.native_gate_model(1,0,mode)
    def test_gate_does_not_prove_subject(self):
        self.assertTrue(m.native_gate_model(1,0,1));self.assertTrue(m.native_gate_model(0,7,1))
        self.assertFalse(m.native_gate_model(0,0,1))
    def test_ro_is_not_call_permission(self):
        r=m.ro_preconditions(snapshot(),snapshot());self.assertTrue(r['structural_ro_preconditions'])
        self.assertFalse(r['native_call_authorized']);self.assertFalse(r['effect_verified'])
    def test_identity_numbers_reject_bool_float(self):
        base=snapshot()
        for key,v in base.items():
            if type(v) is not int:continue
            for bad in [float(v),True]:
                a=copy.deepcopy(base);a[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_false_evidence(self):
        for k,v in snapshot().items():
            if type(v) is bool:
                for bad in [False,1,1.0,None]:
                    a=snapshot();a[k]=bad
                    with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_missing_extra_keys(self):
        a=snapshot();del a['definition']
        with self.assertRaises(ValueError):m.ro_preconditions(a,a)
        a=snapshot();a['injected_authorized']=True
        with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_wrong_overlord(self):
        a=snapshot();a['target_overlord']=a['target_handle']
        with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_subject_missing_duplicate_unbounded(self):
        for values in [[],[snapshot()['target_handle']]*2,[snapshot()['target_handle']]*257]:
            a=snapshot();a['actor_subjects']=values
            with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_stale_generation_bare_tag_or_slot(self):
        for key,bad in [('target_handle',0x56414e),('count',100),('actor_handle',snapshot()['actor_handle']^(1<<56))]:
            a=snapshot();a[key]=bad
            with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_separate_definition_flags(self):
        for key in ('uses_military_focus','can_set_mil_focus'):
            a=snapshot();a[key]=0
            with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_wrong_definition_vtable(self):
        a=snapshot();a['definition_vtable']+=8
        with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_two_samples_change(self):
        a=snapshot();b=snapshot();b['focus']=1
        with self.assertRaises(ValueError):m.ro_preconditions(a,b)
    def test_tls_unknown_cannot_promote(self):
        a=snapshot();a['entitlement']='available'
        with self.assertRaises(ValueError):m.ro_preconditions(a,a)
    def test_lifetime_independent(self):
        a,b=m.Ownership(),m.Ownership();a.destroy();b.destroy()
        self.assertEqual(a.destroy_count,1);self.assertEqual(b.destroy_count,1)
        with self.assertRaises(ValueError):a.destroy()
    def test_no_cleanup_after_entry_or_exception(self):
        x=m.Ownership();x.before_dispatch()
        with self.assertRaises(ValueError):x.destroy()
        with self.assertRaises(ValueError):x.before_dispatch()
    def test_false_return_does_not_restore_ownership(self):
        for ok,consumed in [(False,False),(False,True),(True,False),(True,True)]:
            x=m.Ownership();x.before_dispatch();x.returned(ok,consumed)
            with self.assertRaises(ValueError):x.destroy()
            with self.assertRaises(ValueError):x.before_dispatch()

if __name__=='__main__':unittest.main()
