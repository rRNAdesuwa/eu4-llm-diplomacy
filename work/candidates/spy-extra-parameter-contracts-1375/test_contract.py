import dataclasses,unittest
from contract import Fields,PROFILES,NULL_HANDLE,validate,clone_fields,wrapper_fields,region_selection,faction_selection,technology_scope,preview_contract,Ownership
A=0x100007a00415246;T=0x100003500474e45
def fields(f='stealmap'):return Fields(f,A,A,T,600,900,parameter=2 if f=='stealmap' else 0x10000)
def records():return [{'pointer':0x10000,'identity':(7,9),'target_handle':T,'supporter_handle':NULL_HANDLE}]
def select(rs=None):return faction_selection(0x10000,(7,9),T,A,records() if rs is None else rs)

class Contract(unittest.TestCase):
    def test_three_exact_profiles(self):
        self.assertEqual([x[0] for x in PROFILES.values()],[0x33c8,0x2dde,0x3662])
        for name in PROFILES:self.assertIs(validate(fields(name)).value,True)
    def test_clone_primary_date_not_secondary(self):
        for name in PROFILES:
            f=fields(name);c=clone_fields(f);self.assertEqual((c.primary_date,c.secondary_date),(600,600));self.assertEqual(f.secondary_date,900);self.assertEqual(c.parameter,f.parameter)
    def test_wrapper_overwrites_clone_secondary(self):
        for name in PROFILES:
            f=fields(name);self.assertEqual(wrapper_fields(f,1000).secondary_date,1000);self.assertEqual(f.secondary_date,900)
    def test_no_false_cancel(self):
        for name in PROFILES:
            with self.assertRaises(ValueError):validate(dataclasses.replace(fields(name),value=False))
    def test_bool_float_identity_rejected(self):
        for key in ('actor','controller','target','primary_date','secondary_date','envoy','state','flag','identifier','parameter'):
            for val in (True,1.0):
                with self.subTest(key=key,val=val),self.assertRaises(ValueError):validate(dataclasses.replace(fields(),**{key:val}))
    def test_value_must_bool(self):
        for v in (1,1.0,'true'):
            with self.assertRaises(ValueError):validate(dataclasses.replace(fields(),value=v))
    def test_defaults_not_parameters(self):
        with self.assertRaises(ValueError):validate(dataclasses.replace(fields(),parameter=-1))
        for name in list(PROFILES)[1:]:
            with self.assertRaises(ValueError):validate(dataclasses.replace(fields(name),parameter=0))
    def test_distinct_pair_current_actor(self):
        for patch in ({'target':A},{'controller':T}):
            with self.assertRaises(ValueError):validate(dataclasses.replace(fields(),**patch))
    def test_region_boundary(self):
        self.assertFalse(region_selection(9,10)['authorized'])
        for i,n in ((-1,10),(10,10),(0,0),(0,4097),(True,10),(0,10.0)):
            with self.assertRaises(ValueError):region_selection(i,n)
    def test_region_legality_unknown(self):self.assertTrue(region_selection(0,1)['engine_legality_unknown'])
    def test_borrowed_selection(self):
        r=select();self.assertTrue(r['lifetime_unknown']);self.assertFalse(r['free_parameter']);self.assertFalse(r['native_call_authorized'])
    def test_missing_borrowed_pointer(self):
        r=records();r[0]['pointer']+=8
        with self.assertRaises(ValueError):select(r)
    def test_duplicate_pointer(self):
        with self.assertRaises(ValueError):select(records()*2)
    def test_faction_identity_two_dwords(self):
        for v in ((7,10),(7,True),(7,9.0),(7,1<<32),(7,)):
            r=records();r[0]['identity']=v
            with self.assertRaises(ValueError):select(r)
    def test_faction_target_generation(self):
        r=records();r[0]['target_handle']=T+(1<<56)
        with self.assertRaises(ValueError):select(r)
    def test_supported_or_noncanonical_null_rejected(self):
        for v in (A,0,NULL_HANDLE+1,False):
            r=records();r[0]['supporter_handle']=v
            with self.assertRaises(ValueError):select(r)
    def test_faction_bounded_list(self):
        for rs in ([],records()*257,tuple(records())):
            with self.assertRaises(ValueError):select(rs)
    def test_faction_exact_schema(self):
        for patch in ({'extra':1},{'pointer':1.0}):
            r=records();r[0].update(patch)
            with self.assertRaises(ValueError):select(r)
    def test_no_generic_steal_technology(self):
        for name in ('steal_technology','stealtech','study_technology'):
            r=technology_scope(name);self.assertTrue(r['unsupported']);self.assertFalse(r['authorized'])
    def test_modernization_not_technology(self):
        r=technology_scope('steal_modern_ideas');self.assertFalse(r['technology_level_change_proven']);self.assertTrue(r['loaded_definition_unknown'])
    def test_full_preview_separate_gate(self):
        r=preview_contract('stealmap',0x88,None,False);self.assertEqual(r['command_gate_slot'],0x40);self.assertFalse(r['native_call_authorized'])
    def test_preview_wrong_slot_mode(self):
        for slot,sink,mode in ((0x80,None,False),(0x40,None,False),(0x88,0,False),(0x88,None,0),(0x88,None,True)):
            with self.assertRaises(ValueError):preview_contract('stealmap',slot,sink,mode)
    def test_command_owns_clone_original_independent(self):
        o=Ownership();o.make_command();o.destroy_original();self.assertTrue(o.result()['clone_owned_by_command']);o.destroy_command();self.assertFalse(o.result()['clone_owned_by_command']);self.assertFalse(o.result()['borrowed_parameter_freed'])
    def test_original_may_outlive_command(self):
        o=Ownership();o.make_command();o.destroy_command();self.assertTrue(o.original);o.destroy_original();self.assertFalse(o.result()['submitted'])
    def test_double_cleanup_rejected(self):
        o=Ownership();o.make_command();o.destroy_command()
        with self.assertRaises(ValueError):o.destroy_command()
        o.destroy_original()
        with self.assertRaises(ValueError):o.destroy_original()
    def test_exception_terminal_no_cleanup_retry(self):
        o=Ownership();o.make_command();o.exception()
        for fn in (o.make_command,o.destroy_original,o.destroy_command):
            with self.assertRaises(ValueError):fn()
        self.assertTrue(o.result()['unknown']);self.assertFalse(o.result()['effect_verified'])
    def test_repeated_wrapper_not_in_model(self):
        o=Ownership();o.make_command()
        with self.assertRaises(ValueError):o.make_command()
    def test_dates_strict_and_bounded(self):
        for d in (True,1000.0,-1,1<<31):
            with self.assertRaises(ValueError):wrapper_fields(fields(),d)

if __name__=='__main__':unittest.main()
