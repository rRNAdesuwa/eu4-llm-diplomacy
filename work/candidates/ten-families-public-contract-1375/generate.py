"""Derive ten non-executable public parameter descriptions from sealed facts."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
FAVOR='work/candidates/favor-exchanges-contract-1375/report.json'
WAR='work/candidates/war-dynasty-province-contracts-1375/report.json'
def canonical(x):return (json.dumps(x,sort_keys=True,indent=2,ensure_ascii=True)+'\n').encode()
def read(path,limit=4*1024*1024):
    with path.open('rb') as f:b=f.read(limit+1)
    if len(b)>limit:raise ValueError('bounded input')
    return b
def verify_inputs():
    pins=json.loads(read(HERE/'input-pins.json',65536));total=0
    for name,pin in pins.items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT):raise ValueError('input escape')
        b=read(p);total+=len(b)
        if total>12*1024*1024 or pin!={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}:raise ValueError('sealed input changed')
    return pins
def build():
    pins=verify_inputs();favor=json.loads(read(ROOT/FAVOR));war=json.loads(read(ROOT/WAR))
    assert favor['game_sha256'].lower()==war['game_sha256'].lower()==GAME
    tag={'type':'string','pattern':'^[A-Z0-9]{3}$'}
    integer={'type':'integer','minimum':1,'maximum':2147483647}
    extras={'sell_province':{'province_id':integer,'price_integer':{'type':'integer','minimum':0,'maximum':2147483}},
            'enforce_peace':{'opposing_country':tag},'threaten_war':{'province_id':integer,'taker_country':tag},
            'reduce_relations_favor':{'third_country':tag}}
    evidence={'claim_throne':['claim_normal','claim_effect','clone_and_ownership'],
        'sell_province':['sell_normal','sell_effect','clone_and_ownership'],
        'enforce_peace':['enforce_normal','enforce_effect','clone_and_ownership'],
        'threaten_war':['threaten_normal','threaten_effect','normal_sender_boundary'],
        'reduce_relations_favor':['normal_ai_owner','reduce_third_gap','effect_reduce'],
        'trade_favors_for_gold':['normal_ai_owner','gold_no_external_amount'],
        'trade_favors_for_men':['normal_ai_owner','men_no_external_amount'],
        'trade_favors_for_sailors':['normal_ai_owner','sailors_no_external_amount'],
        'trade_favors_for_trust':['factory_trust_parameters','serialization_trust','effect_trust'],
        'trade_favors_for_war_prep':['normal_ai_owner','effect_war_prep']}
    fields={'sell_province':[{'offset':'0x40','width_bytes':4,'representation':'signed integer currency','public_parameter':'price_integer','accepted_effect_scaling':1000}, {'offset':'0x44','width_bytes':4,'representation':'signed province ID','public_parameter':'province_id'}],
        'enforce_peace':[{'offset':'0x40','width_bytes':8,'representation':'full opposing-country handle','public_parameter':'opposing_country','live_resolution_implemented':False}],
        'threaten_war':[{'offset':'0x40','width_bytes':4,'representation':'signed province ID','public_parameter':'province_id'},{'offset':'0x44','width_bytes':8,'representation':'unaligned full taker-country handle','public_parameter':'taker_country','restricted_to':'actor','live_resolution_implemented':False}],
        'reduce_relations_favor':[{'offset':'0x40','width_bytes':8,'representation':'full third-country handle','public_parameter':'third_country','normal_selection_closed':False,'live_resolution_implemented':False}],
        'trade_favors_for_trust':[{'offset':'0x40','width_bytes':4,'representation':'signed favors_milli','source':'global 0x233db7c multiplied by 1000','public_parameter':None,'live_value_observed':False},{'offset':'0x44','width_bytes':4,'representation':'signed trust_int','source':'global 0x233db80','public_parameter':None,'live_value_observed':False}]}
    notes={'claim_throne':'Unilateral claim branch; no promise of subsequent succession-war outcome.',
        'sell_province':'price_integer is whole currency; the model ceiling avoids observed signed32 multiply-by-1000 overflow, not the full game acceptance range.',
        'enforce_peace':'opposing_country is a TAG draft for a country handle, never war_id. Decline may enter a join-war branch.',
        'threaten_war':'Only normal taker=actor is closed. Normal caller uses local +0x80 then direct bfe50; normal full +0x88 caller is not closed. Decline may declare war.',
        'reduce_relations_favor':'Known QWORD layout does not close normal third-country selection. Normal AI leaves the invalid handle and score returns zero; selector remains unsupported.',
        'trade_favors_for_trust':'Pair-only intent draft omits both native fields. Existing public favors parameter migration and custom favors/trust amounts are unclosed; no default 10/5 is assumed.',
        'trade_favors_for_gold':'Native computes gold; no arbitrary external amount field.',
        'trade_favors_for_men':'Native computes manpower; no arbitrary external amount field.',
        'trade_favors_for_sailors':'Native computes sailors; no arbitrary external amount field.',
        'trade_favors_for_war_prep':'Pair only; accepted preparation is not a guarantee that war will occur.'}
    rows={}
    for report,path,is_war in ((favor,FAVOR,False),(war,WAR,True)):
        for index,item in enumerate(report['families']):
            name=item['public_id'] if is_war else item['name'];props={'actor':tag,'target':tag,**extras.get(name,{})}
            refs=['/families/'+str(index)]+['/facts/'+key for key in evidence[name]]
            assert all(key in report['facts'] for key in evidence[name])
            gap={'trade_favors_for_trust':'unclosed_legacy_migration_and_native_dynamic_defaults','reduce_relations_favor':'unclosed_normal_third_country_selector'}.get(name)
            rows[name]={'action_id':name,'native_name':item.get('native_name',name),'parameters':{'type':'object','properties':props,'required':list(props),'additionalProperties':False},
                'constraints':['actor != target']+(['opposing_country differs from actor and target'] if name=='enforce_peace' else ['taker_country == actor'] if name=='threaten_war' else ['third_country differs from actor and target'] if name=='reduce_relations_favor' else []),
                'parameter_binding_status':gap or 'restricted_static_shape_only','parameter_binding_closed':gap is None,
                'native_descriptor':{'token':item['token'],'vtable_rva':item['vtable'],'object_size':item['size'],'derived_fields':fields.get(name,[])},
                'evidence':{'report_path':path,'report_sha256':pins[path]['sha256'],'json_pointers':refs,'static_evidence_verified':True},
                'normal_parameterized_caller_closed':item.get('normal_parameterized_caller_closed',True),
                'normal_full_preview_caller_closed':item.get('normal_full88_call_closed',True),
                'native_legality_verified':False,'live_identity_resolved':False,'execution_verified':False,'runtime_verified':False,'production_ready':False,
                'state_or_value_user_override':False,'false_preview_is_cancel':False,'binding_note':notes[name]}
    assert len(rows)==10
    return {'contract':'TenFamiliesDraft/1','scope':'isolated proposal only; not formal Contract/2 or a new API service','game_sha256':GAME,'actions':rows,
            'raw_addresses_or_control_fields_accepted':False,'backend_registered':False,'production_ready':False,'idempotence_reserved':False,
            'common_limits':['TAG and province IDs are syntax only; live existence/generation/world/war identity are unresolved.','No native construction, getter, preview, queue, send, memory or process call is provided.','No custom cancel, state, value, expiry, thread, raw pointer or RVA input is accepted.','Full preview false and command-gate false are observations, not cancellation or side-effect-free proofs.']}
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();raw=canonical(build());out=HERE/'contract.json'
    if a.check:
        if read(out,131072)!=raw:raise ValueError('derived JSON differs')
    else:
        with out.open('xb') as f:f.write(raw)
    print(json.dumps({'checked':a.check,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'families':10,'production_ready':False}))
if __name__=='__main__':main()
