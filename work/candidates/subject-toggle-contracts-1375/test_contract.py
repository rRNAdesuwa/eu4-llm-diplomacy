import copy,json,unittest
from pathlib import Path
import contract_model as m

def fact():
    return {'actor':m.FRA,'target':m.NAV,'overlord':m.FRA,'flag_word':0,
      'actor_presence':1,'actor_marker':0,'target_at_war':0,'rival_count':2,'type_allows':True}

class ContractTests(unittest.TestCase):
    def test_three_tokens_and_masks_match_static(self):
        c=json.loads((Path(__file__).parent/'contract.json').read_bytes())
        for name,(token,index) in m.FAMILIES.items():
            self.assertEqual(c['families'][name]['token'],token)
            self.assertEqual(c['families'][name]['flag_index'],index)
            self.assertEqual(c['families'][name]['mask'],1<<index)
    def test_enable_and_disable_use_inverse_cancel(self):
        for name,(_,index) in m.FAMILIES.items():
            f=fact();p=m.plan(name,True,f)
            self.assertFalse(p['cancel_snapshot']);self.assertEqual(p['reason'],'requires_native_full_gate')
            f['flag_word']=1<<index;p=m.plan(name,False,f)
            self.assertTrue(p['cancel_snapshot']);self.assertEqual(p['reason'],'requires_native_full_gate')
    def test_already_desired_never_authorizes(self):
        for name,(_,index) in m.FAMILIES.items():
            for on in [False,True]:
                f=fact();f['flag_word']=(1<<index) if on else 0
                p=m.plan(name,on,f);self.assertEqual(p['reason'],'already_desired')
                self.assertFalse(p['transition_needed']);self.assertFalse(p['native_call_authorized'])
    def test_stale_both_directions(self):
        for name,(_,index) in m.FAMILIES.items():
            f=fact();self.assertFalse(m.stale(name,False,f))
            f['flag_word']=1<<index;self.assertTrue(m.stale(name,False,f));self.assertFalse(m.stale(name,True,f))
            f['flag_word']=0;self.assertTrue(m.stale(name,True,f))
    def test_only_selected_bit_changes(self):
        for name,(_,index) in m.FAMILIES.items():
            for word in [0,0xffffffff,0xaaaaaaaa,0x55555555]:
                for cancel in [False,True]:
                    got=m.bit_write(name,cancel,word);self.assertEqual((word^got)&~(1<<index),0)
                    self.assertEqual(bool(got&(1<<index)),not cancel)
    def test_overlord_high_byte_is_part_of_identity(self):
        f=fact();f['flag_word']=0xffffffff;f['overlord']=0x00415246
        self.assertFalse(m.current('scutage',f));self.assertEqual(m.plan('scutage',True,f)['reason'],'not_full_direct_subject')
    def test_full_generation_not_slot_only(self):
        for field in ['actor','target','overlord']:
            f=fact();f[field]^=1<<48
            if field=='overlord':self.assertEqual(m.plan('scutage',True,f)['reason'],'not_full_direct_subject')
            else:
                with self.assertRaises(ValueError):m.plan('scutage',True,f)
    def test_wrong_pair_rejected(self):
        f=fact();f['actor'],f['target']=f['target'],f['actor']
        with self.assertRaises(ValueError):m.plan('scutage',True,f)
    def test_strict_types_all_integer_fields(self):
        for k,v in fact().items():
            if type(v) is int:
                for bad in [float(v),True,False,str(v)]:
                    f=fact();f[k]=bad
                    with self.assertRaises(ValueError):m.plan('scutage',True,f)
    def test_strict_bools(self):
        for bad in [0,1,0.0,1.0,None,'true']:
            with self.assertRaises(ValueError):m.plan('scutage',bad,fact())
            f=fact();f['type_allows']=bad
            with self.assertRaises(ValueError):m.plan('scutage',True,f)
            with self.assertRaises(ValueError):m.stale('scutage',bad,fact())
    def test_extra_missing_rejected(self):
        for k in fact():
            f=fact();del f[k]
            with self.assertRaises(ValueError):m.plan('scutage',True,f)
        f=fact();f['raw_singleton']=123
        with self.assertRaises(ValueError):m.plan('scutage',True,f)
    def test_family_whitelist(self):
        for bad in ['military_subject_focus','grant_province','embargo',0,None]:
            with self.assertRaises(ValueError):m.plan(bad,True,fact())
    def test_type_permissions_not_inferred_from_name(self):
        f=fact();f['type_allows']=False
        for family in m.FAMILIES:self.assertEqual(m.plan(family,True,f)['reason'],'type_reject')
    def test_actor_gate_mirror(self):
        f=fact();f['actor_presence']=0
        self.assertEqual(m.plan('scutage',True,f)['reason'],'actor_field_reject')
        f['actor_marker']=7;self.assertEqual(m.plan('scutage',True,f)['reason'],'requires_native_full_gate')
    def test_scutage_both_directions_at_war_reject(self):
        for old in [False,True]:
            f=fact();f['flag_word']=16 if old else 0;f['target_at_war']=1
            self.assertEqual(m.plan('scutage',not old,f)['reason'],'scutage_war_reject')
    def test_embargo_no_rivals_only_enabling(self):
        f=fact();f['rival_count']=0;self.assertEqual(m.plan('embargo_rivals',True,f)['reason'],'no_rivals')
        f['flag_word']=2;self.assertEqual(m.plan('embargo_rivals',False,f)['reason'],'requires_native_full_gate')
    def test_structural_pass_not_native_allowed(self):
        p=m.plan('divert_trade',True,fact())
        self.assertIsNone(p['native_allowed']);self.assertFalse(p['runtime_verified']);self.assertFalse(p['production_supported'])
    def test_clone_consumes_temp_and_keeps_source(self):
        x=m.Lifetime();x.clone_normal();self.assertEqual((x.original,x.clone,x.temporary_string),('owned','owned','destroyed'))
        with self.assertRaises(ValueError):x.clone_normal()
        x.destroy('original');x.destroy('clone')
        with self.assertRaises(ValueError):x.destroy('clone')
    def test_never_destroy_singleton(self):
        x=m.Lifetime()
        with self.assertRaises(ValueError):x.destroy('singleton')
    def test_handoff_terminal_no_dtor_no_retry(self):
        x=m.Lifetime();x.clone_normal();x.destroy('original');x.handoff_enter('clone')
        with self.assertRaises(ValueError):x.destroy('clone')
        with self.assertRaises(ValueError):x.handoff_enter('clone')
    def test_exception_any_stage_no_guessed_cleanup(self):
        for cloned in [False,True]:
            x=m.Lifetime()
            if cloned:x.clone_normal()
            x.exception()
            with self.assertRaises(ValueError):x.destroy('original')
            with self.assertRaises(ValueError):x.clone_normal()
    def test_hash_uses_four_little_endian_bytes(self):
        for token,_ in m.FAMILIES.values():
            v=0xcbf29ce484222325
            for i in range(4):v=((v^((token>>(8*i))&255))*1099511628211)%(1<<64)
            self.assertEqual(m.token_hash(token),v)
            self.assertNotEqual(m.token_hash(token),m.token_hash(int.from_bytes(token.to_bytes(4,'little'),'big')))
    def test_report_no_runtime_authority(self):
        j=json.loads((Path(__file__).parent/'report.json').read_bytes())
        self.assertEqual(len(j['actions']),3);self.assertLessEqual(j['limits']['new_decoded_bytes'],49152)
        for k in ['runtime_verified','execution_verified','production_supported']:self.assertIs(j[k],False)
        for f in j['functions'].values():
            if f['kind']=='new_bounded_cfg':self.assertLessEqual(f['decoded_bytes'],8192)
    def test_effects_not_generic_rollback(self):
        j=json.loads((Path(__file__).parent/'report.json').read_bytes())
        self.assertEqual(j['functions']['0xe6260']['instructions'][0]['instruction'],'mov eax, 4')
        self.assertEqual(j['functions']['0xe6280']['instructions'][0]['instruction'],'mov eax, 6')
        self.assertEqual(j['facts']['divert_disable_can_restore_half']['evidence'][-2]['instruction'],'mov dword ptr [rsi + 0x40], 0x1f4')
        self.assertIn('0x14ca33d',{r['rva'] for r in j['facts']['context_handoff']['evidence']})
if __name__=='__main__':unittest.main()
