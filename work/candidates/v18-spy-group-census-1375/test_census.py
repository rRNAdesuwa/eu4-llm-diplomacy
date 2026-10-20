"""Small group-contract fakes only; no process or game sampling."""
import copy,io,struct,tempfile,types,unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
import census as c

PID=1234;CREATION='01dd000000000001'
class Reader:
    base=0x140000000
    def __init__(self):
        self.data={};self.bytes_read=0;self.closed=False
        self.game=0x40000000;self.server=0x50000000;self.manager=0x60000000
        for p,n in ((self.base+0x233fe78,self.game),(self.game+0x1e00,self.server),(self.server,self.base+0x1cb8460),
                    (self.server+0x418,self.manager),(self.manager+0x50,self.server),(self.manager,0),(self.manager+8,0),
                    (self.game+0x1e60,c.FRA),(self.game+0x74c8,0)):self.put(p,struct.pack('<Q',n))
        self.put(self.game+0x1dd0,struct.pack('<i',c.DATE));self.put(self.game+0x1e08,struct.pack('<i',0))
        self.put(self.manager+0x48,b'\1');self.put(self.server+0x19f1,b'\0');self.put(self.game+0x7485,b'\0')
    def put(self,p,raw):self.data.update({p+i:x for i,x in enumerate(raw)})
    def read(self,p,n):self.bytes_read+=n;return bytes(self.data[p+i] for i in range(n))
    def close(self):self.closed=True
class Spy:
    EXE_SHA='a'*64
    def held_identity(self,r,pid,creation):return dict(pid=pid,creation_filetime=f'{creation:016x}',exit_filetime=0,module_base=r.base)
    def selected(self,s):return {'unknown_objects_or_selected_semantics':True,'matching':[]}
    def inspect(self,s):
        assert s['family'] in c.FAMILIES
        assert type(s['identity']['date'])is int
        assert type(s['identity']['count'])is int
    def contract(self):return {'pe':{'timestamp':1,'image_size':2},'families':dict.fromkeys(c.FAMILIES)}
class Full:
    def __init__(self):self.calls=[];self.mutate=None
    def sha(self,path):return Spy.EXE_SHA
    def capture(self,r,base,*,family):
        self.calls.append(family)
        snapshot={'family':family,'target':'ENG','identity':{'base':base,'game':r.reader.game,'database':0x70000000,'array':0x71000000,'count':1000,
          'date':c.DATE,'player':c.FRA,'countries':{'FRA':{'handle':c.FRA,'address':0x72000000},'ENG':{'handle':c.ENG,'address':0x73000000}}}}
        source={'snapshot':snapshot,'two_pass_equal':True,'selected':Spy().selected(snapshot)}
        value={'family':family,'profile':'spy_dense_full_ro_1375_2','full_envelope_equal':True,'before':source,'after':copy.deepcopy(source),
            'dense':{'final_milli_candidate':None,'status':'unknown_lazy_or_thread_fallback'},
            **{k:False for k in ('native_calls','native_legality_verified','actual_cost_verified','individual_effect_verified','strict_single_player_verified','world_epoch_verified','paused_verified','production_ready')}}
        if self.mutate:self.mutate(self,r,value)
        return value

class Census(unittest.TestCase):
    def collect(self,full=None,reader=None,spy=None):return c._collect(reader or Reader(),full or Full(),spy or Spy(),PID,CREATION,'initial')
    def test_complete_five_fixed_order_original_unknown_preserved(self):
        full=Full();result=self.collect(full)
        self.assertEqual(full.calls,list(c.FAMILIES));self.assertEqual(len(result['family_reports']),5)
        self.assertIs(result['group_atomic'],False);self.assertEqual(result['raw_date'],c.DATE)
        for report in result['family_reports'].values():self.assertIsNone(report['dense']['final_milli_candidate']);self.assertIs(report['paused_verified'],False)
        for k in ('individual_effect_verified','request_causality_verified','production_ready','whole_world_unchanged_verified'):self.assertIs(result[k],False)
    def test_group_identity_and_typed_aliases_reject(self):
        for field,value in (('game',0x40010000),('date',c.DATE+1),('player',c.ENG),('count',1000.0),('base',0x140000000+8)):
            full=Full()
            def mutate(f,r,x):
                if len(f.calls)==2:
                    for part in ('before','after'):x[part]['snapshot']['identity'][field]=value
            full.mutate=mutate
            with self.subTest(field=field),self.assertRaises((ValueError,AssertionError)):self.collect(full)
            self.assertEqual(len(full.calls),2)
        for value in (True,float(c.ENG),0):
            full=Full()
            def mutate(f,r,x):
                for part in ('before','after'):x[part]['snapshot']['identity']['countries']['ENG']['handle']=value
            full.mutate=mutate
            with self.assertRaises(ValueError):self.collect(full)
    def test_pause_and_after_pause_change_reject(self):
        for where,raw in (('pause',b'\0'),('classifier',b'\1'),('date',struct.pack('<i',c.DATE+24)),('reset',b'\1')):
            reader=Reader();p={'pause':reader.manager+0x48,'classifier':reader.server+0x19f1,'date':reader.game+0x1dd0,'reset':reader.game+0x7485}[where]
            reader.put(p,raw)
            with self.subTest(where=where),self.assertRaises(ValueError):self.collect(reader=reader)
        full=Full();full.mutate=lambda f,r,x:r.reader.put(r.reader.manager+0x48,b'\0')
        with self.assertRaises(ValueError):self.collect(full)
    def test_held_identity_changes_reject(self):
        spy=Spy();original=spy.held_identity;calls=0
        def held(r,p,t):
            nonlocal calls
            calls+=1;x=original(r,p,t)
            if calls==2:x['creation_filetime']='01dd000000000002'
            return x
        spy.held_identity=held
        with self.assertRaises(ValueError):self.collect(spy=spy)
    def test_whole_group_budget_and_short_read(self):
        with patch.object(c,'MAX_BYTES',20),self.assertRaises(ValueError):self.collect()
        with patch.object(c,'MAX_CALLS',2),self.assertRaises(ValueError):self.collect()
        r=c.GroupReader(Reader())
        for args in ((True,8),(0x40000000,True),(0x40000000,65537)):
            with self.assertRaises(ValueError):r.read(*args)
        with patch.object(r.reader,'read',return_value=b''),self.assertRaises(ValueError):r.read(0x40000000,8)
    def test_sample_closes_exact_fake_handle_success_and_failure(self):
        import sys
        sys.path.insert(0,str(c.ROOT));from work import probe_diplomacy_current as legacy
        for fail in (False,True):
            r=Reader();full=Full()
            if fail:full.mutate=lambda f,b,x:b.reader.put(b.reader.manager+0x48,b'\0')
            with patch.object(c,'check',return_value={}),patch.object(c,'dependencies',return_value=(full,Spy())),\
                 patch.object(legacy,'verified_executable',return_value=({},dict(timestamp=1,size=2))),patch.object(legacy,'ProcessReader',return_value=r) as opened,\
                 patch.object(legacy,'pe_signature',return_value={}),patch.object(legacy,'verify_module_signature',return_value=None):
                if fail:
                    with self.assertRaises(ValueError):c.sample(PID,CREATION,'final')
                else:self.assertEqual(c.sample(PID,CREATION,'final')['source_kind'],'held_process_readonly_sequential_group')
                opened.assert_called_once_with(PID,(c.ROOT.parent/'eu4.exe').resolve(),dict(timestamp=1,size=2))
            self.assertTrue(r.closed)
    def test_arguments_output_create_new_and_no_replacement(self):
        for args in ((True,CREATION,'initial'),(PID,CREATION.upper(),'initial'),(PID,CREATION,'middle')):
            with self.assertRaises(ValueError):c.arguments(*args)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'census.json';result=self.collect();c.write_new(p,result);original=p.read_bytes()
            with self.assertRaises(FileExistsError):c.write_new(p,{'changed':True})
            self.assertEqual(p.read_bytes(),original)
            with patch.object(c,'sample',side_effect=AssertionError('no sample')):
                with self.assertRaises(ValueError):c.main(['--pid',str(PID),'--creation',CREATION,'--phase','initial','--output',str(p)])
            with patch.object(c,'MAX_OUTPUT',10),self.assertRaises(ValueError):c.write_new(Path(td)/'too-big.json',result)
    def test_original_claims_and_selected_report_mutations_fail(self):
        for mutate in (lambda x:x.update(production_ready=True),lambda x:x['after'].update(two_pass_equal=1),lambda x:x['before']['selected'].update(matching=[1])):
            full=Full();full.mutate=lambda f,r,x:mutate(x)
            with self.assertRaises(ValueError):self.collect(full)

if __name__=='__main__':unittest.main(verbosity=2)
