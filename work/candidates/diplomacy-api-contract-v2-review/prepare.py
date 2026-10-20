"""Create/check a review-only patch from pinned formal sources. Never install it."""
from pathlib import Path
import argparse,ast,difflib,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
ORIGINAL=ROOT/'work/candidates/diplomacy-typed-binding-catalog-1375'
INPUTS=('bridge/diplomacy_api.py','bridge/diplomacy_service.py','bridge/diplomacy_catalog.json',
 'tools/diplomacy.py','tools/serve_diplomacy.py','docs/diplomacy-api.md',
 'bridge/tests/test_diplomacy_api.py','bridge/tests/test_diplomacy_reconciliation.py',
 'work/candidates/diplomacy-typed-binding-catalog-1375/catalog.py',
 'work/candidates/diplomacy-typed-binding-catalog-1375/bindings.json',
 'work/candidates/diplomacy-typed-binding-catalog-1375/input-pins.json',
 'work/candidates/diplomacy-typed-binding-catalog-1375/review.json',
 'work/review-results/typed-binding-catalog-action-catalog-20261008a/review.json')
def read(p,limit=2*1024*1024):
    with p.open('rb')as f:b=f.read(limit+1)
    if len(b)>limit:raise ValueError('bounded source exceeded')
    return b
def sha(b):return hashlib.sha256(b).hexdigest()
def desc(p):
    b=read(p);return {'bytes':len(b),'sha256':sha(b)}
def encode(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def change(text,old,new):
    if text.count(old)!=1:raise ValueError('exact source replacement count: '+old[:90])
    return text.replace(old,new)
def artifacts():
    expected=json.loads(read(HERE/'input-pins.json'))
    for p,d in expected.items():
        if desc(ROOT/p)!=d:raise ValueError('source mismatch '+p)
    output={}
    legacy={p:read(ROOT/p).decode('utf-8') for p in INPUTS if p.endswith('.py')or p.endswith('.md')}
    api=legacy['bridge/diplomacy_api.py']
    addition='''class DiplomacyAPI:
    @staticmethod
    def contract(version: int = 2):
        """Explicit Contract/2 draft API: no DB, build probe or execution adapter."""
        if type(version) is not int or version != 2:
            raise APIError("protocol_version", "contract() requires explicit integer version 2", 400)
        from .diplomacy_contract_v2 import ContractCatalog
        return ContractCatalog()

'''
    output['bridge/diplomacy_api.py']=change(api,'class DiplomacyAPI:\n',addition).encode()
    # Legacy methods and the validator remain AST-identical; V2 reuses these
    # definitions via the package import, avoiding an impossible self hash cycle.
    original_ast=ast.parse(api);new_ast=ast.parse(output['bridge/diplomacy_api.py'])
    for oldnode,newnode in zip(original_ast.body,new_ast.body):
        if isinstance(oldnode,ast.ClassDef)and oldnode.name=='DiplomacyAPI':
            assert ast.dump(oldnode)==ast.dump(ast.ClassDef(name=newnode.name,bases=newnode.bases,keywords=newnode.keywords,body=newnode.body[1:],decorator_list=newnode.decorator_list,type_params=[]))
        else:assert ast.dump(oldnode)==ast.dump(newnode)
    pins=json.loads(read(ORIGINAL/'input-pins.json'));del pins['bridge/diplomacy_api.py']
    for p in ('work/candidates/diplomacy-typed-binding-catalog-1375/catalog.py','work/candidates/diplomacy-typed-binding-catalog-1375/review.json','work/review-results/typed-binding-catalog-action-catalog-20261008a/review.json'):
        pins[p]=desc(ROOT/p)
    pinbytes=encode(pins)
    v2=read(ORIGINAL/'catalog.py').decode()
    v2=change(v2,'import types','from . import diplomacy_api as api\nfrom .diplomacy_api import APIError')
    v2=change(v2,'ROOT = HERE.parents[2]','ROOT = HERE.parent')
    v2=change(v2,'PIN_SHA = "a0d3e8f845d7e40b9fb0cbaadc8db533c1cf1435cd2cd4b27e4135f2ccde5000"',f'PIN_SHA = "{sha(pinbytes)}"')
    v2=change(v2,'class ContractError(ValueError):\n    def __init__(self, code, message):\n        self.code = code\n        super().__init__(message)',
'''class ContractError(APIError):
    def __init__(self, code, message):
        status = 404 if code == "unknown_action" else (413 if code == "request_budget" else
                 (500 if code in {"source_mismatch", "input_budget", "invalid_contract"} else
                  (422 if code in {"invalid_parameters", "unsupported_schema"} else 400)))
        super().__init__(code, message, status)''')
    v2=change(v2,'def __init__(self, root: Path = ROOT):','def __init__(self, root: Path | None = None):')
    v2=change(v2,'self.root = Path(root).resolve()','self.root = Path(ROOT if root is None else root).resolve()')
    v2=change(v2,'HERE / "input-pins.json"','HERE / "diplomacy_contract_v2_pins.json"')
    v2=change(v2,'HERE / "bindings.json"','HERE / "diplomacy_contract_v2_bindings.json"')
    v2=change(v2,'if name in {"bridge/diplomacy_api.py", "bridge/diplomacy_catalog.json"}:','if name == "bridge/diplomacy_catalog.json":')
    start=v2.index('        api_path = self.root / "bridge/diplomacy_api.py"')
    end=v2.index('        catalog = strict_json(',start)
    v2=v2[:start]+'        self._api = api  # Definitions only: never instantiate the durable V1 API.\n'+v2[end:]
    v2=change(v2,'"status": "unsupported", "reason": "No executable adapter; structural request draft only",',
        '"status": "unsupported", "reason": "No executable adapter; structural request draft only",\n                "draft_only": True, "parameters": deepcopy(payload["parameters"]),')
    output['bridge/diplomacy_contract_v2.py']=v2.encode()
    output['bridge/diplomacy_contract_v2_pins.json']=pinbytes
    output['bridge/diplomacy_contract_v2_bindings.json']=read(ORIGINAL/'bindings.json')
    service=legacy['bridge/diplomacy_service.py']
    service=change(service,'import time','import time\nimport threading')
    service=change(service,'def make_server(api: DiplomacyAPI,','def make_server(api: DiplomacyAPI | None,')
    service=change(service,'    class Handler(BaseHTTPRequestHandler):','''    contract_api = None
    contract_lock = threading.Lock()

    def contracts():
        nonlocal contract_api
        with contract_lock:
            if contract_api is None:
                contract_api = DiplomacyAPI.contract(version=2)
        return contract_api

    class Handler(BaseHTTPRequestHandler):''')
    service=change(service,'        def _body(self):','        def _body(self, limit=MAX_BODY):')
    service=change(service,'if length < 0 or length > MAX_BODY:','if length < 0 or length > limit:')
    service=change(service,'if MAX_BODY < length <= MAX_REJECT_DRAIN:','if limit < length <= MAX_REJECT_DRAIN:')
    service=change(service,'f"Body must be at most {MAX_BODY} bytes"','f"Body must be at most {limit} bytes"')
    service=change(service,'                path = unquote(parsed.path)','''                path = unquote(parsed.path)
                if method == "GET" and path == "/v2/actions":
                    return self._send(200, contracts().describe())
                if method == "GET" and path.startswith("/v2/actions/"):
                    return self._send(200, contracts().describe(path.removeprefix("/v2/actions/")))
                if method == "POST" and path == "/v2/validate":
                    return self._send(200, contracts().validate(self._body(limit=16 * 1024)))
                if method == "POST" and path == "/v2/requests":
                    return self._send(501, contracts().request(self._body(limit=16 * 1024)))
                if api is None and path.startswith("/v1/"):
                    raise APIError("version_disabled", "V1 durable service is not enabled", 404)''')
    output['bridge/diplomacy_service.py']=service.encode()
    cli=legacy['tools/diplomacy.py']
    cli=change(cli,'    parser.add_argument("--url",','    parser.add_argument("--api-version", type=int, choices=(1, 2), default=1)\n    parser.add_argument("--url",')
    cli=change(cli,'for verb in ("preview", "submit"):', 'for verb in ("preview", "submit", "validate", "request"):')
    cli=change(cli,'        body = None','''        if args.api_version == 2 and args.command not in ("describe", "validate", "request"):
            raise APIError("version_command", "V2 supports only describe, validate and request drafts", 400)
        if args.api_version == 1 and args.command in ("validate", "request"):
            raise APIError("version_command", "validate/request require --api-version 2; V1 retains preview/submit", 400)
        if args.api_version == 2 and (args.game_exe is not None or args.catalog != DEFAULT_CATALOG or args.queue_db != DEFAULT_DATABASE):
            raise APIError("version_option", "V2 has fixed evidence and no executable or queue database option", 400)
        body = None''')
    cli=change(cli,'        if args.command in ("preview", "submit"):', '''        if args.api_version == 2 and args.command in ("validate", "request"):
            if args.file == "-":
                source = getattr(sys.stdin, "buffer", sys.stdin).read(16 * 1024 + 1)
                if isinstance(source, str):
                    source = source.encode("utf-8")
            else:
                with Path(args.file).open("rb") as stream:
                    source = stream.read(16 * 1024 + 1)
            if len(source) > 16 * 1024:
                raise APIError("request_budget", "V2 request body exceeds 16 KiB", 413)
            body = decode_json(source.decode("utf-8"))
        elif args.command in ("preview", "submit"):''')
    cli=change(cli,'            route = {"capabilities":', '            route = ({"describe": "/v2/actions/" + quote(getattr(args, "action", ""), safe=""),\n                      "validate": "/v2/validate", "request": "/v2/requests"} if args.api_version == 2 else {"capabilities":')
    cli=change(cli,'+ "/events"}[args.command]','+ "/events"})[args.command]')
    cli=change(cli,'        else:\n            game_root = get_path(','''        elif args.api_version == 2:
            contract = DiplomacyAPI.contract(version=2)
            result = contract.describe(args.action) if args.command == "describe" else getattr(contract, args.command)(body)
            exit_code = 2 if result.get("status") == "unsupported" else 0
        else:
            game_root = get_path(''')
    output['tools/diplomacy.py']=cli.encode()
    serve=legacy['tools/serve_diplomacy.py']
    serve=change(serve,'    parser.add_argument("--host",','    parser.add_argument("--contract-only", action="store_true", help="V2 drafts only; no V1 database or executable inspection")\n    parser.add_argument("--host",')
    serve=change(serve,'    game_root = get_path("EU4_GAME_ROOT", required=False)\n    executable = args.game_exe or (game_root / "eu4.exe" if game_root else None)\n    api = DiplomacyAPI(args.catalog, args.queue_db, executable)', '''    if args.contract_only and (args.game_exe is not None or args.catalog != DEFAULT_CATALOG or args.queue_db != DEFAULT_DATABASE):
        parser.error("--contract-only has fixed evidence and no executable/queue options")
    api = None
    if not args.contract_only:
        game_root = get_path("EU4_GAME_ROOT", required=False)
        executable = args.game_exe or (game_root / "eu4.exe" if game_root else None)
        api = DiplomacyAPI(args.catalog, args.queue_db, executable)''')
    serve=serve.replace('        api.close()','        if api is not None:\n            api.close()')
    serve=change(serve,'    print(f"Diplomacy API: http://{args.host}:{server.server_port}/v1/capabilities", flush=True)', '''    route = "/v2/actions" if args.contract_only else "/v1/capabilities"
    print(f"Diplomacy API: http://{args.host}:{server.server_port}{route}", flush=True)''')
    serve=change(serve,'    print("Execution adapter: unavailable. Preview and audit are active; unsupported submits fail closed.", flush=True)', '''    print("V2: unsupported drafts only; no request ID reservation or native execution." if args.contract_only else
          "V1 durable audit active; V2 drafts have no reservation. Execution adapter unavailable.", flush=True)''')
    output['tools/serve_diplomacy.py']=serve.encode()
    output['docs/diplomacy-api.md']=(legacy['docs/diplomacy-api.md']+'\n\n'+read(HERE/'v2-documentation.md').decode()).encode()
    output['bridge/tests/test_diplomacy_contract_v2.py']=read(HERE/'test_contract_v2.py')
    return output,expected
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    out,pins=artifacts();diff=[]
    for path,b in out.items():
        dest=HERE/'files'/path
        if args.check:
            if read(dest)!=b:raise ValueError('candidate differs '+path)
        else:
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb')as f:f.write(b)
        if path.endswith('.py'):ast.parse(b)
        old=read(ROOT/path).decode()if(ROOT/path).is_file()else''
        diff.extend(difflib.unified_diff(old.splitlines(True),b.decode().splitlines(True),fromfile='a/'+path,tofile='b/'+path))
    index={'schema':1,'inputs':pins,'outputs':{p:{'bytes':len(b),'sha256':sha(b)}for p,b in out.items()},'production_ready':False,'materialized':False}
    for name,b in [('patch.diff',''.join(diff).encode()),('candidate-index.json',encode(index))]:
        if args.check:
            if read(HERE/name,4*1024*1024)!=b:raise ValueError('review artifact changed '+name)
        else:
            with(HERE/name).open('xb')as f:f.write(b)
    print(json.dumps({'check':args.check,'outputs':len(out),'index_sha256':sha(encode(index)),'formal_files_modified':False}))
if __name__=='__main__':main()
