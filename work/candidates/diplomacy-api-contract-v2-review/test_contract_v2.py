"""Public V2 integration; offline drafts only, real loopback HTTP, no game."""
from copy import deepcopy
import contextlib,http.client,io,json,sqlite3,subprocess,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from bridge.diplomacy_api import APIError,DEFAULT_CATALOG,DiplomacyAPI
from bridge import diplomacy_contract_v2 as v2
from bridge.diplomacy_service import make_server
from tools import diplomacy as cli
from tools import serve_diplomacy as serve

def sample(s,k=''):
    if 'const'in s:return deepcopy(s['const'])
    if 'enum'in s:return deepcopy(s['enum'][0])
    t=s['type']
    if t=='object':return {n:sample(s['properties'][n],n)for n in s.get('required',[])}
    if t=='array':return [sample(s['items'])for _ in range(s.get('minItems',0))]
    if t=='string':return ('FRA'if k=='actor'else'ENG')if s.get('pattern')=='^[A-Z0-9]{3}$'else'x'*max(1,s.get('minLength',1))
    if t in('integer','number'):return s.get('minimum',1)
    if t=='boolean':return True
    if t=='null':return None
    raise AssertionError(t)
def payload(action='steal_maps'):
    params={'actor':'FRA','target':'ENG','region_index':0}if action=='steal_maps'else {'actor':'FRA','target':'ENG','faction_identity':{'low':1,'high':2}}
    return dict(protocol=v2.PROTOCOL,request_id='draft-1',action=action,parameters=params)
def connection(server,method,path,value=None,raw=None,headers=None):
    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    body=raw if raw is not None else(json.dumps(value).encode()if value is not None else None)
    try:
        conn.request(method,path,body=body,headers={'Content-Type':'application/json',**(headers or {})})
        response=conn.getresponse();return response.status,json.loads(response.read())
    finally:conn.close()
class PublicContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=DiplomacyAPI.contract(version=2)
    def test_factory_and_all274_are_database_free(self):
        with patch.object(sqlite3,'connect',side_effect=AssertionError('database')),patch.object(subprocess,'Popen',side_effect=AssertionError('subprocess')),patch.object(DiplomacyAPI,'__init__',side_effect=AssertionError('v1 constructor')):
            c=DiplomacyAPI.contract(version=2);self.assertEqual(c.describe()['catalog_actions'],274)
            for row in c.describe()['actions']:
                p=dict(protocol=v2.PROTOCOL,request_id='same-id',action=row['action'],parameters=sample(c.describe(row['action'])['parameters']))
                result=c.request(p);self.assertEqual(result['status'],'unsupported');self.assertIs(result['draft_only'],True)
                self.assertEqual(result['parameters'],p['parameters']);self.assertFalse(result['request_written'])
    def test_factory_version_is_explicit_strict_integer(self):
        for value in (1,True,False,2.0,'2',None):
            with self.subTest(value=value),self.assertRaises(APIError):DiplomacyAPI.contract(value)
    def test_v1_old_two_parameters_v2_migrations_and_no_ledger_collision(self):
        with tempfile.TemporaryDirectory()as td:
            old=DiplomacyAPI(DEFAULT_CATALOG,Path(td)/'queue.db',build_probe=lambda:{'status':'not_inspected','sha256':None})
            try:
                changed=[]
                for name,entry in old.actions.items():
                    if entry['parameters']!=self.c.describe(name)['parameters']:changed.append(name)
                self.assertEqual(set(changed),{'steal_maps','support_rebels'})
                for action in changed:
                    legacy=dict(request_id='same-id',action=action,parameters=sample(old.actions[action]['parameters']))
                    self.assertEqual(old.validate(legacy),legacy)
                    with self.assertRaises(APIError):self.c.request(dict(protocol=v2.PROTOCOL,**legacy))
                    migrated=payload(action)
                    with self.assertRaises(APIError):old.validate({k:v for k,v in migrated.items()if k!='protocol'})
                legacy=dict(request_id='draft-1',action='steal_maps',parameters=sample(old.actions['steal_maps']['parameters']))
                old.submit(legacy)
                before=[tuple(r)for r in old.db.execute('SELECT * FROM requests')]
                self.c.request(payload());q=payload();q['parameters']['region_index']=2;self.c.request(q)
                self.assertEqual(before,[tuple(r)for r in old.db.execute('SELECT * FROM requests')])
            finally:old.close()
    def test_strict_v2_types_raw_parameters_and_protocol(self):
        for bad in (True,0.0,-1,2**31,'0',None):
            p=payload();p['parameters']['region_index']=bad
            with self.assertRaises(APIError):self.c.request(p)
        for key in('pointer','rva','backend','pid','envoy_id','state','value','script'):
            for at in('parameters','envelope'):
                p=payload();(p['parameters']if at=='parameters'else p)[key]=0
                with self.assertRaises(APIError):self.c.request(p)
        for version in ('EU4DIPLOMACY-CONTRACT/1',2,True,None):
            p=payload();p['protocol']=version
            with self.assertRaises(APIError):self.c.validate(p)
    def test_draft_normalization_detaches_mutable_parameters(self):
        p=payload('support_rebels');a=self.c.request(p);p['parameters']['faction_identity']['low']=3
        b=self.c.request(p);self.assertNotEqual(a['request_sha256'],b['request_sha256'])
        self.assertEqual(a['parameters']['faction_identity']['low'],1)
        for row in(a,b):self.assertEqual(row['idempotency_scope'],'not_reserved_contract_only');self.assertFalse(row['queued'])

class HttpContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(None,port=0);cls.thread=threading.Thread(target=cls.server.serve_forever,kwargs={'poll_interval':.02});cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join(3);assert not cls.thread.is_alive()
    def test_http_describe_validate_501_usable_draft_no_database(self):
        with patch.object(sqlite3,'connect',side_effect=AssertionError('database')),patch.object(DiplomacyAPI,'__init__',side_effect=AssertionError('v1 constructor')):
            self.assertEqual(connection(self.server,'GET','/v2/actions')[1]['catalog_actions'],274)
            self.assertEqual(connection(self.server,'GET','/v2/actions/steal_maps')[0],200)
            status,result=connection(self.server,'POST','/v2/validate',payload());self.assertEqual(status,200);self.assertIsNone(result['native_legality'])
            status,result=connection(self.server,'POST','/v2/requests',payload());self.assertEqual(status,501)
            self.assertEqual(result['parameters'],payload()['parameters']);self.assertTrue(result['draft_only']);self.assertEqual(result['status'],'unsupported')
            self.assertFalse(result['native_called']);self.assertFalse(result['request_written'])
    def test_no_v2_status_audit_submit_or_protocol_fallback(self):
        for path in('/v2/requests/draft-1','/v2/requests/draft-1/events','/v1/capabilities'):
            self.assertEqual(connection(self.server,'GET',path)[0],404)
        for path in('/v2/submit','/v2/preview','/v2/requests/draft-1/reconcile'):
            self.assertEqual(connection(self.server,'POST',path,{})[0],404)
        p=payload();del p['protocol'];self.assertEqual(connection(self.server,'POST','/v2/requests',p)[0],400)
    def test_http_wire_budget_duplicate_nonfinite_and_identity_types(self):
        for raw,status in [(b' '*16385,413),(b'{"action":"a","action":"b"}',400),(b'{"x":NaN}',400),(b'\xff',400)]:
            self.assertEqual(connection(self.server,'POST','/v2/requests',raw=raw)[0],status)
        p=payload('support_rebels');p['parameters']['faction_identity']['high']=True
        self.assertEqual(connection(self.server,'POST','/v2/requests',p)[0],422)
        self.assertEqual(connection(self.server,'GET','/v2/actions/none')[0],404)
    def test_v2_retains_origin_host_and_bearer_boundaries(self):
        self.assertEqual(connection(self.server,'GET','/v2/actions',headers={'Origin':'https://invalid.test'})[0],403)
        self.assertEqual(connection(self.server,'GET','/v2/actions',headers={'Host':'invalid.test'})[0],403)
        s=make_server(None,port=0,token='secret');t=threading.Thread(target=s.serve_forever,kwargs={'poll_interval':.02});t.start()
        try:
            self.assertEqual(connection(s,'GET','/v2/actions')[0],401)
            self.assertEqual(connection(s,'GET','/v2/actions',headers={'Authorization':'Bearer secret'})[0],200)
        finally:s.shutdown();s.server_close();t.join(3);self.assertFalse(t.is_alive())
    def test_mixed_server_v2_never_delegates_to_v1(self):
        old=Mock();old.describe.side_effect=AssertionError('legacy describe');old.submit.side_effect=AssertionError('legacy submit');old.preview.side_effect=AssertionError('legacy preview')
        s=make_server(old,port=0);t=threading.Thread(target=s.serve_forever,kwargs={'poll_interval':.02});t.start()
        try:
            self.assertEqual(connection(s,'POST','/v2/requests',payload())[0],501)
            self.assertEqual(connection(s,'POST','/v2/validate',payload())[0],200)
            self.assertEqual(connection(s,'GET','/v2/actions/steal_maps')[0],200)
            old.submit.assert_not_called();old.preview.assert_not_called();old.describe.assert_not_called()
        finally:s.shutdown();s.server_close();t.join(3);self.assertFalse(t.is_alive())

class CliContractTests(unittest.TestCase):
    def call(self,args,body=''):
        out=io.StringIO();err=io.StringIO()
        with patch('sys.stdin',io.StringIO(body)),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=cli.main(args)
        return code,json.loads(out.getvalue()or err.getvalue())
    def test_local_v2_never_reads_configuration_or_constructs_v1(self):
        with patch.object(cli,'get_path',side_effect=AssertionError('config')),patch.object(DiplomacyAPI,'__init__',side_effect=AssertionError('v1')),patch.object(sqlite3,'connect',side_effect=AssertionError('DB')):
            self.assertEqual(self.call(['--api-version','2','describe','steal_maps'])[0],0)
            self.assertEqual(self.call(['--api-version','2','validate','-'],json.dumps(payload()))[0],0)
            code,result=self.call(['--api-version','2','request','-'],json.dumps(payload()));self.assertEqual(code,2);self.assertEqual(result['status'],'unsupported')
    def test_explicit_cli_verb_version_and_options(self):
        for verb in('preview','submit'):
            self.assertEqual(self.call(['--api-version','2',verb,'missing-file.json'])[1]['error']['code'],'version_command')
        for verb in('status','audit','reconcile'):
            self.assertEqual(self.call(['--api-version','2',verb,'x'])[1]['error']['code'],'version_command')
        self.assertEqual(self.call(['validate','-'],'{}')[1]['error']['code'],'version_command')
        self.assertEqual(self.call(['--api-version','2','--queue-db','elsewhere.db','request','-'],'{}')[1]['error']['code'],'version_option')
    def test_cli_request_file_is_bounded_before_json_parse(self):
        with tempfile.TemporaryDirectory()as td:
            p=Path(td)/'input.json';p.write_bytes(b' '*16385)
            self.assertEqual(self.call(['--api-version','2','request',str(p)])[1]['error']['code'],'request_budget')
        self.assertEqual(self.call(['--api-version','2','request','-'],' '*16385)[1]['error']['code'],'request_budget')
    def test_http_cli_preserves_501_draft_and_exitcode(self):
        s=make_server(None,port=0);t=threading.Thread(target=s.serve_forever,kwargs={'poll_interval':.02});t.start()
        try:
            code,result=self.call(['--api-version','2','--url',f'http://127.0.0.1:{s.server_port}','request','-'],json.dumps(payload()))
            self.assertEqual(code,2);self.assertEqual(result['parameters'],payload()['parameters']);self.assertEqual(result['status'],'unsupported')
        finally:s.shutdown();s.server_close();t.join(3);self.assertFalse(t.is_alive())
    def test_contract_only_server_startup_does_not_instantiate_v1(self):
        fake=Mock(server_port=12345);fake.serve_forever.side_effect=KeyboardInterrupt
        with patch('sys.argv',['serve','--contract-only']),patch.object(serve,'get_path',side_effect=AssertionError('config')),patch.object(DiplomacyAPI,'__init__',side_effect=AssertionError('v1')),patch.object(serve,'make_server',return_value=fake)as made,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(serve.main(),0);self.assertIsNone(made.call_args.args[0]);fake.server_close.assert_called_once()

if __name__=='__main__':unittest.main()
