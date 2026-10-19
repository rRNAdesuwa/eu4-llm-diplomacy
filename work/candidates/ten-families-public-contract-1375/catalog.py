"""Ten-family isolated description/validation/draft; no executable backend."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
CONTRACT='TenFamiliesDraft/1'
CONTRACT_SHA='74679ba5b708d028da3ca8b2f9b25a34994c127ba2d2c561d5e2c20e289b842d'
def require(ok,reason):
    if not ok:raise ValueError(reason)
def _unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,'Duplicate JSON key');result[k]=v
    return result
def _nonfinite(value):raise ValueError('Non-finite JSON number')
def _data():
    with (HERE/'contract.json').open('rb') as f:raw=f.read(131073)
    require(len(raw)<=131072 and hashlib.sha256(raw).hexdigest()==CONTRACT_SHA,'Fixed contract changed')
    return json.loads(raw,object_pairs_hook=_unique,parse_constant=_nonfinite)
def describe(action_id):
    require(type(action_id)is str and 1<=len(action_id)<=64,'Exact action ID')
    data=_data();require(action_id in data['actions'],'Unknown action ID')
    return data['actions'][action_id]
def actions():return sorted(_data()['actions'])
def validate(action_id,parameters):
    row=describe(action_id);schema=row['parameters']
    require(type(parameters)is dict and len(parameters)<=4 and set(parameters)==set(schema['required']),'Exact parameters required')
    clean={}
    for name,rules in schema['properties'].items():
        value=parameters[name]
        if rules['type']=='string':
            require(type(value)is str and len(value)==3 and re.fullmatch('[A-Z0-9]{3}',value)is not None,'Exact three-character ASCII TAG')
        else:
            require(type(value)is int and rules['minimum']<=value<=rules['maximum'],'Exact bounded integer')
        clean[name]=value
    require(clean['actor']!=clean['target'],'Distinct actor/target required')
    if action_id=='enforce_peace':require(clean['opposing_country'] not in (clean['actor'],clean['target']),'Restricted opposing-country identity')
    if action_id=='threaten_war':require(clean['taker_country']==clean['actor'],'Only taker=actor has normal caller evidence')
    if action_id=='reduce_relations_favor':require(clean['third_country'] not in (clean['actor'],clean['target']),'Distinct third-country syntax')
    return {'contract':CONTRACT,'action_id':action_id,'parameters':clean,'parameters_valid':True,
            'parameter_binding_status':row['parameter_binding_status'],'parameter_binding_closed':row['parameter_binding_closed'],
            'live_identity_resolved':False,'native_legality_verified':False,'execution_supported':False,'production_ready':False}
def request(payload):
    require(type(payload)is dict and len(payload)==4 and set(payload)=={'contract','action_id','parameters','request_id'},'Exact draft request keys')
    require(type(payload['contract'])is str and payload['contract']==CONTRACT,'Explicit isolated draft contract required')
    ident=payload['request_id'];require(type(ident)is str and 1<=len(ident)<=96 and re.fullmatch('[A-Za-z0-9_.:-]+',ident)is not None,'Bounded ASCII request ID')
    result=validate(payload['action_id'],payload['parameters'])
    result.update(request_id=ident,status='unsupported',draft_only=True,request_id_status='not_reserved',
                  reason='No native adapter/backend; parameter shape does not grant execution.',
                  queued=False,submitted=False,execution_verified=False,runtime_verified=False,
                  effect_verified=False,request_causality_verified=False)
    if not result['parameter_binding_closed']:
        result['reason']='Parameter binding is unclosed: '+result['parameter_binding_status']+'; no native adapter/backend.'
    return result
def request_json(raw):
    require(type(raw)is bytes and 0<len(raw)<=4096,'Bounded JSON bytes required')
    return request(json.loads(raw,object_pairs_hook=_unique,parse_constant=_nonfinite))
