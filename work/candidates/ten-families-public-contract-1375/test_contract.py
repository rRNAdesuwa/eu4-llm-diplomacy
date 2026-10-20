import copy,json,pathlib,unittest
import catalog as c
import generate as g

def params(name):
    p={'actor':'FRA','target':'ENG'}
    p.update({'sell_province':{'province_id':183,'price_integer':100},'enforce_peace':{'opposing_country':'POR'},'threaten_war':{'province_id':183,'taker_country':'FRA'},'reduce_relations_favor':{'third_country':'POR'}}.get(name,{}));return p
def payload(name):return {'contract':c.CONTRACT,'action_id':name,'parameters':params(name),'request_id':'test-1'}
class ContractTests(unittest.TestCase):
    def test_all_ten_describe_validate_draft(self):
        self.assertEqual(len(c.actions()),10)
        for name in c.actions():
            d=c.describe(name);v=c.validate(name,params(name));r=c.request(payload(name))
            self.assertTrue(v['parameters_valid']);self.assertEqual(r['status'],'unsupported');self.assertEqual(r['request_id_status'],'not_reserved')
            for k in ('queued','submitted','production_ready','execution_verified','runtime_verified','effect_verified','live_identity_resolved'):self.assertIs(r[k],False)
            self.assertFalse(d['false_preview_is_cancel']);self.assertFalse(d['execution_verified'])
    def test_request_same_id_does_not_reserve_or_conflict(self):
        one=c.request(payload('sell_province'));p=payload('sell_province');p['parameters']['price_integer']=200
        two=c.request(p);self.assertEqual(one['request_id'],two['request_id']);self.assertNotEqual(one['parameters'],two['parameters']);self.assertEqual(two['request_id_status'],'not_reserved')
    def test_no_raw_or_control_fields_on_any_action(self):
        for name in c.actions():
            for key in ('pointer','rva','handle','state','value','envoy','expires','thread','cancel','amount','backend'):
                p=params(name);p[key]=1
                with self.subTest(name=name,key=key),self.assertRaises(ValueError):c.validate(name,p)
    def test_integer_endpoints_and_aliases(self):
        for name,field,lo,hi in [('sell_province','price_integer',0,2147483),('sell_province','province_id',1,2147483647),('threaten_war','province_id',1,2147483647)]:
            for value in (lo,hi):
                p=params(name);p[field]=value;self.assertTrue(c.validate(name,p)['parameters_valid'])
            for value in (True,False,float(lo),float(hi),str(lo),None,[],{},lo-1,hi+1):
                p=params(name);p[field]=value
                with self.subTest(name=name,field=field,value=value),self.assertRaises(ValueError):c.validate(name,p)
    def test_country_syntax_no_implicit_normalization(self):
        for value in ('fra','FRA ',' FR','ＦＲＡ','FR\n','0x123','---',123,True,None):
            for name in c.actions():
                p=params(name);p['actor']=value
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):c.validate(name,p)
        p=params('claim_throne');p['actor']='ZZZ';self.assertFalse(c.validate('claim_throne',p)['live_identity_resolved'])
    def test_roles_and_taker_restrictions(self):
        for name in c.actions():
            p=params(name);p['target']='FRA'
            with self.assertRaises(ValueError):c.validate(name,p)
        for name,key in [('enforce_peace','opposing_country'),('reduce_relations_favor','third_country')]:
            for tag in ('FRA','ENG'):
                p=params(name);p[key]=tag
                with self.assertRaises(ValueError):c.validate(name,p)
        p=params('threaten_war');p['taker_country']='POR'
        with self.assertRaises(ValueError):c.validate('threaten_war',p)
    def test_unclosed_trust_no_custom_or_guessed_defaults(self):
        r=c.request(payload('trade_favors_for_trust'));self.assertFalse(r['parameter_binding_closed']);self.assertIn('unclosed',r['reason'])
        for key in ('favors','favors_milli','favor_milli','trust','trust_int','trust_points'):
            p=params('trade_favors_for_trust');p[key]=10
            with self.assertRaises(ValueError):c.validate('trade_favors_for_trust',p)
        fields=c.describe('trade_favors_for_trust')['native_descriptor']['derived_fields'];self.assertEqual([x['width_bytes'] for x in fields],[4,4]);self.assertTrue(all(x['public_parameter'] is None and not x['live_value_observed'] for x in fields))
    def test_reduce_selector_still_unclosed(self):
        row=c.describe('reduce_relations_favor');self.assertFalse(row['normal_parameterized_caller_closed']);self.assertFalse(row['parameter_binding_closed'])
        self.assertEqual(c.request(payload('reduce_relations_favor'))['status'],'unsupported')
    def test_old_names_are_not_silently_migrated(self):
        for name,p in [('sell_province',{'actor':'FRA','target':'ENG','province_id':183,'price':10}),('enforce_peace',{'actor':'FRA','target':'ENG','war_id':'1','defender':'POR'}),('trade_favors_for_trust',{'actor':'FRA','target':'ENG','favors':10}),('threaten_war',{'actor':'FRA','target':'ENG','province_id':183})]:
            with self.assertRaises(ValueError):c.validate(name,p)
        old=json.loads((c.HERE/'legacy-parameters.json').read_text(encoding='utf-8'));self.assertIn('price',old['parameters']['sell_province']['properties']);self.assertIn('war_id',old['parameters']['enforce_peace']['properties']);self.assertIn('favors',old['parameters']['trade_favors_for_trust']['properties'])
    def test_strict_json_envelope_budget_and_duplicates(self):
        raw=json.dumps(payload('claim_throne')).encode();self.assertEqual(c.request_json(raw)['status'],'unsupported')
        bad=[b'{"contract":1,"contract":2}',raw+b'{}',b' '*4097,raw.decode(),b'{"x":NaN}']
        for value in bad:
            with self.assertRaises((ValueError,TypeError)):c.request_json(value)
        for key in ('send','queue','force','binding'):
            p=payload('claim_throne');p[key]=True
            with self.assertRaises(ValueError):c.request(p)
    def test_explicit_version_and_request_id(self):
        for value in ('Contract/1','Contract/2','',True,1):
            p=payload('claim_throne');p['contract']=value
            with self.assertRaises(ValueError):c.request(p)
        for value in ('','x'*97,'../../x','x\n','中文',False,1):
            p=payload('claim_throne');p['request_id']=value
            with self.assertRaises(ValueError):c.request(p)
    def test_descriptions_are_independent_and_no_authority(self):
        d=c.describe('sell_province');d['parameters']['properties']['price_integer']['maximum']=99999999;d['execution_verified']=True
        self.assertEqual(c.describe('sell_province')['parameters']['properties']['price_integer']['maximum'],2147483)
        self.assertFalse(c.describe('sell_province')['execution_verified'])
    def test_exact_evidence_and_determinism(self):
        self.assertEqual(g.canonical(g.build()),(c.HERE/'contract.json').read_bytes())
        self.assertEqual(sum(c.describe(n)['parameter_binding_closed'] for n in c.actions()),8)
        self.assertFalse(c.describe('threaten_war')['normal_full_preview_caller_closed'])
        for name in c.actions():
            evidence=c.describe(name)['evidence'];report=json.loads((g.ROOT/evidence['report_path']).read_text(encoding='utf-8'))
            for pointer in evidence['json_pointers']:
                obj=report
                for part in pointer.split('/')[1:]:obj=obj[int(part)] if isinstance(obj,list) else obj[part]
                self.assertIsNotNone(obj)
if __name__=='__main__':unittest.main(verbosity=2)
