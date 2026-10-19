import unittest,struct,json
from dataclasses import replace
from pathlib import Path
from contract import *
FRA=0x100007a00415246;POR=0x100005200524f50;ENG=0x100003000474e45;DATE=56456976
class ContractTests(unittest.TestCase):
    def make(self,name='trade_favors_for_men'):
        return factory(name,**({'trust_cost_units':10,'trust_amount':5} if name=='trade_favors_for_trust' else {}))
    def test_six_explicit_sizes(self):
        self.assertEqual(list(SIZES.values()),[72,64,64,64,72,64])
    def test_factory_secondary_is_not_current(self):
        a=initialize_like_normal_ai(self.make(),FRA,POR,DATE);self.assertEqual(a.secondary_date,FACTORY_DATE);self.assertNotEqual(a.secondary_date,DATE)
    def test_all_normal_initializations(self):
        for name in SIZES:
            a=initialize_like_normal_ai(self.make(name),FRA,POR,DATE)
            self.assertEqual((a.actor,a.current_actor,a.target,a.envoy,a.state,a.value,a.flag),(FRA,FRA,POR,-1,0,True,0))
    def test_clone_dates_come_from_primary(self):
        a=replace(initialize_like_normal_ai(self.make(),FRA,POR,DATE),secondary_date=7,flag=1)
        b=clone(a);self.assertEqual((b.primary_date,b.secondary_date,b.flag),(DATE,DATE,0));self.assertEqual((a.secondary_date,a.flag),(7,1))
    def test_wrapper_uses_current_date(self):
        a=initialize_like_normal_ai(self.make(),FRA,POR,DATE);b=wrapped_clone(a,DATE+24)
        self.assertEqual((b.primary_date,b.secondary_date),(DATE,DATE+24))
    def test_clone_trust_extension(self):
        a=self.make('trade_favors_for_trust');self.assertEqual(extension_bytes(clone(a)),struct.pack('<ii',10000,5))
    def test_reduce_extension_is_qword(self):
        a=replace(self.make('reduce_relations_favor'),third=ENG);self.assertEqual(extension_bytes(a),struct.pack('<Q',ENG))
    def test_reduce_normal_ai_keeps_invalid_third(self):
        a=initialize_like_normal_ai(self.make('reduce_relations_favor'),FRA,POR,DATE);self.assertEqual(a.third,INVALID);self.assertFalse(parameterized_caller_status(a)['normal_parameterized_caller_closed'])
    def test_valid_third_shape_does_not_close_caller(self):
        a=replace(self.make('reduce_relations_favor'),third=ENG);self.assertFalse(parameterized_caller_status(a)['construct_authorized'])
    def test_no_arbitrary_amount_for_resource_families(self):
        for name in ('trade_favors_for_gold','trade_favors_for_men','trade_favors_for_sailors','trade_favors_for_war_prep'):
            with self.assertRaises(ValueError):extension_bytes(replace(self.make(name),favor_milli=1000))
    def test_wrong_extra_field_types(self):
        for x in (True,1.0,'1',None,-1,2147484):
            with self.assertRaises(ValueError):factory('trade_favors_for_trust',trust_cost_units=x,trust_amount=5)
    def test_trust_integer_not_scaled(self):
        with self.assertRaises(ValueError):factory('trade_favors_for_trust',trust_cost_units=10,trust_amount=5000)
    def test_trust_config_required(self):
        with self.assertRaises(ValueError):factory('trade_favors_for_trust')
    def test_no_foreign_config(self):
        with self.assertRaises(ValueError):factory('trade_favors_for_men',trust_cost_units=10,trust_amount=5)
    def test_bad_family(self):
        for x in ('trade_favors_for_cancel','cancel_trade_favors_for_men',0,True,None):
            with self.assertRaises(ValueError):factory(x)
    def test_not_tag_only(self):
        for x in (0,0x415246,INVALID,FRA&0x00ffffffffffffff,True,float(FRA)):
            with self.assertRaises(ValueError):country(x)
    def test_slot_bound(self):
        with self.assertRaises(ValueError):country((FRA&~(0xffff<<32))|(4096<<32))
    def test_distinct_generation_same_slot_rejected(self):
        with self.assertRaises(ValueError):initialize_like_normal_ai(self.make(),FRA,FRA+(1<<56),DATE)
    def test_date_exact_type(self):
        for x in (True,float(DATE),-1,2**31):
            with self.assertRaises(ValueError):initialize_like_normal_ai(self.make(),FRA,POR,x)
    def test_modified_factory_cannot_reinitialize(self):
        for field,value in (('state',2),('value',False),('envoy',0),('identifier',1)):
            with self.assertRaises(ValueError):initialize_like_normal_ai(replace(self.make(),**{field:value}),FRA,POR,DATE)
    def test_raw_fields_cannot_use_equal_float_or_bool(self):
        for field,value in (('state',False),('value',1),('envoy',-1.0),('identifier',False),('flag',False),('primary_date',float(FACTORY_DATE))):
            with self.assertRaises(ValueError):initialize_like_normal_ai(replace(self.make(),**{field:value}),FRA,POR,DATE)
    def test_resource_no_extension(self):
        self.assertEqual(extension_bytes(self.make()),b'')
    def test_layouts_not_interchangeable(self):
        with self.assertRaises(ValueError):extension_bytes(replace(self.make('trade_favors_for_trust'),third=ENG))
        with self.assertRaises(ValueError):extension_bytes(replace(self.make('reduce_relations_favor'),trust_points=5))
    def test_selected_effect_direction_and_cap(self):
        x=selected_trust_effect_candidate(98,9000,10000,5);self.assertEqual((x['record_direction'],x['trust'],x['favors_milli']),('recipient_to_actor',100,0));self.assertFalse(x['effect_verified'])
    def test_response_does_not_mean_applied(self):
        self.assertEqual(classify(0),'pending');self.assertIn('side_effects',classify(1));self.assertEqual(classify(2),'accepted_branch_only')
    def test_response_type(self):
        for x in (True,2.0,-1,3):
            with self.assertRaises(ValueError):classify(x)
    def test_preview_gate_false_normal_no_send(self):
        for a in (False,True):
            for b in (False,True):self.assertFalse(phase_result(a,b)['submit_authorized'])
    def test_gate_type_not_integer(self):
        for x in (0,1,0.0,None):
            with self.assertRaises(ValueError):phase_result(x,True)
    def test_no_alias_command_clone(self):
        for pair in ((1,2),(2,1),(2,2)):
            with self.assertRaises(ValueError):Ownership(1).wrap(*pair)
    def test_independent_original_and_command(self):
        x=Ownership(1);x.wrap(2,3);x.destroy_original();self.assertEqual((x.command,x.clone),(2,3));x.destroy_command();self.assertIsNone(x.clone)
    def test_double_destruction_rejected(self):
        x=Ownership(1);x.wrap(2,3);x.destroy_command()
        with self.assertRaises(ValueError):x.destroy_command()
    def test_exception_never_retry_cleanup(self):
        x=Ownership(1);x.wrap(2,3);x.exception()
        for f in (x.destroy_original,x.destroy_command,lambda:x.wrap(4,5)):
            with self.assertRaises(ValueError):f()
    def test_report_disclaims_runtime(self):
        d=json.loads((Path(__file__).parent/'report.json').read_bytes())
        for k in ('runtime_verified','execution_verified','effect_verified','production_ready','process_accessed'):self.assertIs(d[k],False)
        self.assertLessEqual(d['limits']['new_decoded_bytes_including_failures_and_repeated_prefixes'],49152)
if __name__=='__main__':unittest.main()
