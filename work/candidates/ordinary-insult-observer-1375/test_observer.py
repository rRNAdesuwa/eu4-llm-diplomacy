"""Sparse-memory and imported-evidence tests; never open a process."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ordinary_insult_candidate',HERE/'observer.py')
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)

class Sparse:
    def __init__(self):self.mem={};self.reads=[];self.base=0x140000000;self.closed=False
    def put(self,p,data):
        for i,v in enumerate(data):self.mem[p+i]=v
    def pack(self,p,fmt,*values):self.put(p,struct.pack(fmt,*values))
    def read(self,p,n):
        self.reads.append((p,n))
        try:return bytes(self.mem[p+i] for i in range(n))
        except KeyError as exc:raise o.legacy.MissingMemory('Synthetic unmapped read') from exc
    def close(self):self.closed=True

class Fixture:
    def __init__(self,target='POR',active=False,trust=50):
        self.target=target;self.r=Sparse();self.base=self.r.base;self.db=0x200000;self.game=0x210000
        self.array=0x230000;self.actor=0x300000;self.recipient=0x310000;self.registry=0x400000
        self.definition=0x410000;self.records=0x500000;self.manager=0x520000;self.outer=0x530000;self.inner=0x540000;self.obj=0x550000
        self.slot=(o.HANDLES['FRA']>>32)&0xffff;self.record=self.records+self.slot*0x48;self.container=self.outer+self.slot*24
        r=self.r;p=r.pack
        for row in o.load_contract()['instruction_pins']:r.put(self.base+int(row['rva'],16),bytes.fromhex(row['bytes']))
        p(self.base+0x233d8d0,'<Q',self.db);p(self.base+0x233fe78,'<Q',self.game);p(self.base+0x233ff08,'<Q',self.registry)
        p(self.db+0x118,'<Q',self.array);p(self.db+0x124,'<i',200);p(self.game+0x1dd0,'<i',56456976)
        p(self.game+0x1e60,'<Q',o.HANDLES['FRA']);p(self.game+0x7485,'<B',0);p(self.game+0x74c8,'<Q',0)
        for tag,where in (('FRA',self.actor),(target,self.recipient)):
            p(self.array+((o.HANDLES[tag]>>32)&0xffff)*8,'<Q',where);p(where+0x20,'<Q',o.HANDLES[tag])
        p(self.registry+0x2f8,'<Q',self.definition);self.name(self.registry+0x300,'insulted');self.name(self.definition+0x10,'insulted')
        p(self.definition+0x50,'<ii',-50,120);p(self.definition+0x5c,'<ii',-100,0)
        p(self.recipient+0x1510,'<Q',self.records);r.put(self.record,bytes(32));p(self.record,'<QQQ',self.manager,o.HANDLES[target],o.HANDLES['FRA']);p(self.record+0x1e,'<B',trust)
        p(self.manager+0x10,'<QQ',self.recipient,self.records);p(self.manager+0x308,'<Qii',self.outer,200,200)
        p(self.container,'<QQii',self.base+0x1c38348,self.inner,8,int(active))
        if active:self.modifier()
    def name(self,location,text):
        raw=bytearray(32);raw[:len(text)]=text.encode();struct.pack_into('<QQ',raw,16,len(text),15);self.r.put(location,raw)
    def modifier(self):
        self.r.pack(self.inner,'<Q',self.obj);raw=bytearray(0x28)
        struct.pack_into('<QI',raw,0,self.base+0x1ccf4f8,0x165);struct.pack_into('<Qiii',raw,0x10,self.definition,56544576,1,-50000)
        self.r.put(self.obj,raw)
    def report(self):
        captured=o.capture(self.r,self.base,self.target)
        contract=o.load_contract();ident={'pid':1234,'creation_filetime':123456789012345678,'exit_filetime':0,'module_base':hex(self.base)}
        return o.wrap(captured,{'kind':'held_process_readonly','before':ident,'after':dict(ident),'expected_creation':f'{ident["creation_filetime"]:016x}',
            'exe_sha256':contract['exe_sha256'],'module_signature':dict(contract['pe_signature']),
            'rights':['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'],'loaded_full_image_hash_verified':False})

class InsultTests(unittest.TestCase):
    def positive(self,target='POR',trust=50):
        a=Fixture(target,False,trust).report();b=Fixture(target,True,max(0,trust-5)).report();return a,b
    def test_all_fixed_targets_new_modifier_and_trust(self):
        for tag in ('ENG','POR','NAV','FOI'):
            with self.subTest(tag=tag):
                a,b=self.positive(tag);r=o.compare_reports(a,b);self.assertTrue(r['observed_effect'],r);self.assertFalse(r['request_causality_verified'])
    def test_clamped_trust_decrease(self):
        a,b=self.positive(trust=3);self.assertTrue(o.compare_reports(a,b)['observed_effect'])
    def test_zero_trust_and_modifier_alone_not_enough(self):
        a,b=self.positive(trust=0);self.assertFalse(o.compare_reports(a,b)['observed_effect'])
    def test_existing_modifier_refresh_not_supported(self):
        a=Fixture(active=True).report();b=Fixture(active=True,trust=45).report();self.assertFalse(o.compare_reports(a,b)['observed_effect'])
    def test_mismatched_trust_rejected(self):
        a=Fixture().report();b=Fixture(active=True,trust=46).report();self.assertFalse(o.compare_reports(a,b)['observed_effect'])
    def test_unknown_object_never_followed_or_absence(self):
        f=Fixture(active=True);f.r.pack(f.obj,'<QI',f.base+0x123458,0x165)
        for k in range(f.obj+0x10,f.obj+0x28):del f.r.mem[k]
        report=f.report();self.assertEqual(report['observation']['state']['status'],'unsupported_unknown_modifier_class')
        self.assertFalse(any(p==f.obj+0x10 for p,n in f.r.reads))
    def test_wrong_marker_short_circuits(self):
        f=Fixture(active=True);f.r.pack(f.obj+8,'<I',0x166)
        self.assertEqual(f.report()['observation']['state']['status'],'unsupported_unknown_modifier_class')
    def test_unmaterialized_outer_slot_unknown_without_getter(self):
        f=Fixture();f.r.pack(f.manager+0x314,'<i',10)
        report=f.report();self.assertEqual(report['observation']['state']['status'],'unsupported_unmaterialized_container')
        self.assertFalse(any(p==f.container for p,n in f.r.reads))
    def test_unknown_definition_name_fails(self):
        f=Fixture();f.name(f.definition+0x10,'other')
        with self.assertRaises(o.legacy.ProbeError):f.report()
    def test_heap_definition_name_and_string_bounds(self):
        f=Fixture();location=f.definition+0x10;storage=0x580000
        f.r.put(location,bytes(32));f.r.pack(location,'<Q',storage);f.r.pack(location+16,'<QQ',8,31);f.r.put(storage,b'insulted\0')
        self.assertEqual(f.report()['observation']['state']['status'],'absent')
        for length,capacity in ((0,15),(129,255),(16,15),(8,4097)):
            f.r.pack(location+16,'<QQ',length,capacity)
            with self.subTest(length=length,capacity=capacity),self.assertRaises(o.legacy.ProbeError):f.report()
    def test_nonterminated_string_rejected(self):
        f=Fixture();f.r.put(f.definition+0x18,b'x')
        with self.assertRaises(o.legacy.ProbeError):f.report()
    def test_runtime_definition_values_are_not_assumed_from_script(self):
        for offset,value in ((0x50,-100),(0x54,121),(0x60,1),(0x5c,-49)):
            f=Fixture();f.r.pack(f.definition+offset,'<i',value)
            with self.subTest(offset=offset),self.assertRaises(o.legacy.ProbeError):f.report()
    def test_uninitialized_cache_fails_without_mutator(self):
        f=Fixture();f.r.pack(f.registry+0x2f8,'<Q',0)
        with self.assertRaises(o.legacy.ProbeError):f.report()
    def test_capacity_count_and_database_bounds(self):
        for location,value in (('outercount',201),('outercap',4097),('innercount',257),('innercap',-1),('dbcount',100)):
            f=Fixture();p={'outercount':f.manager+0x314,'outercap':f.manager+0x310,'innercount':f.container+0x14,'innercap':f.container+0x10,'dbcount':f.db+0x124}[location]
            f.r.pack(p,'<i',value)
            with self.subTest(location=location),self.assertRaises(o.legacy.ProbeError):f.report()
    def test_duplicate_object_and_selected_definition_rejected(self):
        f=Fixture(active=True);f.r.pack(f.container+0x14,'<i',2);f.r.pack(f.inner+8,'<Q',f.obj)
        with self.assertRaises(o.legacy.ProbeError):f.report()
        f.r.pack(f.inner+8,'<Q',f.obj+0x100);f.r.put(f.obj+0x100,f.r.read(f.obj,0x28))
        with self.assertRaises(o.legacy.ProbeError):f.report()
    def test_direction_and_manager_identity(self):
        for mode in ('reverse','owner','manager_owner','manager_records'):
            f=Fixture()
            if mode=='reverse':f.r.pack(f.record+0x10,'<Q',o.HANDLES['POR'])
            if mode=='owner':f.r.pack(f.record+8,'<Q',o.HANDLES['FRA'])
            if mode=='manager_owner':f.r.pack(f.manager+0x10,'<Q',f.actor)
            if mode=='manager_records':f.r.pack(f.manager+0x18,'<Q',f.records+8)
            with self.subTest(mode=mode),self.assertRaises(o.legacy.ProbeError):f.report()
    def test_reset_load_and_full_handle_guard(self):
        for mode in ('reset','load','country'):
            f=Fixture()
            if mode=='reset':f.r.pack(f.game+0x7485,'<B',1)
            if mode=='load':f.r.pack(f.game+0x74c8,'<Q',0x200000)
            if mode=='country':f.r.pack(f.recipient+0x20,'<Q',o.HANDLES['POR']^0x100000000000000)
            with self.subTest(mode=mode),self.assertRaises(o.legacy.ProbeError):f.report()
    def test_loaded_code_pin_change(self):
        f=Fixture();p=f.base+int(o.load_contract()['instruction_pins'][0]['rva'],16);f.r.put(p,b'\x90')
        with self.assertRaises(o.legacy.ProbeError):f.report()
    def test_short_read_and_budget_fail_closed(self):
        class Short:
            def read(self,p,n):return b'x'*(n-1)
        with self.assertRaises(o.legacy.ProbeError):o.Budget(Short()).read(0x10000,8)
        r=o.Budget(Sparse());r.bytes=o.MAX_TOTAL
        with self.assertRaises(o.legacy.ProbeError):r.read(0x10000,1)
        r.bytes=0;r.calls=o.MAX_READS
        with self.assertRaises(o.legacy.ProbeError):r.read(0x10000,1)
    def test_two_pass_change_rejected(self):
        f=Fixture();original=f.r.read;seen=0
        def changed(p,n):
            nonlocal seen
            if p==f.record:seen+=1
            data=original(p,n)
            if p==f.record and seen==2:data=data[:30]+b'\x2d'+data[31:]
            return data
        f.r.read=changed
        with self.assertRaises(o.legacy.ProbeError):f.report()
    def test_each_pass_strict_types_and_state(self):
        source=Fixture(active=True).report()
        changes=[('identity','raw_date',56456976.0),('identity','world_reset_active',False),
                 ('relation','trust',50.0),('relation','outer_count',200.0)]
        for sections in ((0,),(1,),(0,1)):
            for group,key,value in changes:
                r=copy.deepcopy(source)
                for i in sections:r['observation']['passes'][i]['snapshot'][group][key]=value
                with self.subTest(sections=sections,key=key),self.assertRaises(o.legacy.ProbeError):o.validated_report(r)
        for key,value in [('flag24',False),('value_milli',-50000.0),('multiplier',True)]:
            r=copy.deepcopy(source)
            for p in r['observation']['passes']:p['snapshot']['relation']['selected']['objects'][0]['fields'][key]=value
            with self.subTest(key=key),self.assertRaises(o.legacy.ProbeError):o.validated_report(r)
    def test_stored_state_numeric_alias_rejected(self):
        r=Fixture().report();r['observation']['state']['trust']=50.0
        with self.assertRaises(o.legacy.ProbeError):o.validated_report(r)
    def test_held_identity_strict_creation_and_exit(self):
        for field,value in [('pid',True),('creation_filetime',123456789012345680.0),('exit_filetime',False)]:
            r=Fixture().report()
            for when in ('before','after'):r['source'][when][field]=value
            with self.subTest(field=field),self.assertRaises(o.legacy.ProbeError):o.validated_report(r)
    def test_expiry_flags_and_value_do_not_fake_effect(self):
        for offset,fmt,value in [(0x18,'<i',56456976),(0x20,'<i',-100000),(0x24,'<B',1),(0x26,'<B',1),(0x1c,'<i',2)]:
            a=Fixture().report();f=Fixture(active=True,trust=45);f.r.pack(f.obj+offset,fmt,value);b=f.report()
            with self.subTest(offset=offset):self.assertFalse(o.compare_reports(a,b)['observed_effect'])
    def test_world_date_and_process_changes_block_compare(self):
        for mode in ('date','world','creation'):
            a,b=self.positive()
            if mode=='creation':
                for when in ('before','after'):b['source'][when]['creation_filetime']+=1
                b['source']['expected_creation']=f'{b["source"]["before"]["creation_filetime"]:016x}'
            else:
                for p in b['observation']['passes']:
                    if mode=='date':p['snapshot']['identity']['raw_date']+=24
                    else:p['snapshot']['identity']['world']='0x999000'
            with self.subTest(mode=mode):self.assertFalse(o.compare_reports(a,b)['observed_effect'])
    def test_missing_extra_and_duplicate_json(self):
        r=Fixture().report();del r['observation']['passes'][1]['snapshot']['relation']['trust']
        with self.assertRaises(o.legacy.ProbeError):o.validated_report(r)
        r=Fixture().report();r['observation']['passes'][1]['snapshot']['extra']=False
        with self.assertRaises(o.legacy.ProbeError):o.validated_report(r)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';p.write_text('{"x":1,"x":2}')
            with self.assertRaises(o.legacy.ProbeError):o.read_report(p)
    def test_file_report_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'too-large.json'
            with p.open('wb') as f:f.write(b' '*(o.MAX_REPORT+1))
            with self.assertRaises(o.legacy.ProbeError):o.read_report(p)
            # Simulate a stat-before-read race without creating a huge input.
            with patch.object(Path,'stat',return_value=type('S',(),{'st_size':2})()):
                with self.assertRaises(o.legacy.ProbeError):o.read_report(p)
    def test_future_process_wrapper_uses_held_before_after_and_closes_mock(self):
        f=Fixture();c=o.load_contract();creation=123456789012345678
        ident={'pid':1234,'creation_filetime':creation,'exit_filetime':0,'module_base':hex(f.base)}
        with patch.object(o,'digest',return_value=c['exe_sha256']),patch.object(o.legacy,'verified_executable',return_value=({},c['pe_signature'])),patch.object(o.legacy,'ProcessReader',return_value=f.r) as opened,patch.object(o,'held_identity',return_value=ident) as held,patch.object(o.legacy,'pe_signature',return_value=c['pe_signature']):
            # Pin verification itself remains real; only full EXE hashing/mock wrapper is patched.
            with patch.object(o,'load_contract',return_value=c):
                report=o.sample_process(1234,f'{creation:016x}',o.ROOT.parent/'eu4.exe','POR')
            self.assertTrue(report['read_only']);self.assertEqual(held.call_count,2);self.assertTrue(f.r.closed);opened.assert_called_once()
    def test_future_process_wrapper_closes_on_identity_failure(self):
        f=Fixture();c=o.load_contract()
        with patch.object(o,'load_contract',return_value=c),patch.object(o,'digest',return_value=c['exe_sha256']),patch.object(o.legacy,'verified_executable',return_value=({},c['pe_signature'])),patch.object(o.legacy,'ProcessReader',return_value=f.r),patch.object(o,'held_identity',side_effect=o.legacy.ProbeError('creation changed')):
            with self.assertRaises(o.legacy.ProbeError):o.sample_process(1234,'0000000000000001',o.ROOT.parent/'eu4.exe','POR')
        self.assertTrue(f.r.closed)
    def test_invalid_request_rejected_before_process(self):
        for pid,creation,target in [(True,'0000000000000001','POR'),(1,'1','POR'),(1,'0000000000000001','FRA')]:
            with patch.object(o.legacy,'ProcessReader',side_effect=AssertionError('must not open')):
                with self.assertRaises(o.legacy.ProbeError):o.sample_process(pid,creation,o.ROOT.parent/'eu4.exe',target)

if __name__=='__main__':unittest.main()
