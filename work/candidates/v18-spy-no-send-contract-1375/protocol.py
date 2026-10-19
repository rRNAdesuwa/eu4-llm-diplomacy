"""Pure proposed v18 no-send wire grammar; no file publisher or native reader.

This is not EU4LAB/3, not deployed, and not proof that a supplied session exists.
Native claim consumption, stage ownership replay and identity guards remain
separate future implementation work. Encoding never authorizes a native call.
"""
import re

PROTOCOL = 'EU4SPYLAB/1'
PURPOSE = 'restricted_spy_no_send_lab_1375_v18'
PROFILE = 'spy5_true_state0_v1'
GAME_SHA256 = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
STAGES = ('lifecycle', 'family_preview', 'owned_command')
FAMILIES = ('corrupt_officials', 'sabotage_reputation', 'sow_discontent',
            'slander_merchants', 'sabotage_recruitment')
MAX_WIRE = 1024
MAX_TTL_MS = 60000
MAX_UPTIME = 2**64-1
FIELDS = ('purpose', 'game_sha256', 'pid', 'creation', 'session', 'dll_sha256',
          'manifest_sha256', 'sequence', 'expires', 'stage', 'profile',
          'actor', 'target', 'value', 'state', 'envoy')


def require(ok, reason):
    if not ok:raise ValueError(reason)


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def hex_id(value, length):
    return (type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is not None
            and int(value,16)>0)


def encode(record):
    """Canonical bytes only. The caller must not treat this as an execution API."""
    require(type(record) is dict and set(record)==set(FIELDS),'Exact fixed wire fields required')
    require(all(type(record[k]) is str for k in ('purpose','game_sha256','profile','actor','target')),
            'Exact string fields required')
    require(record['purpose']==PURPOSE and record['game_sha256']==GAME_SHA256
            and record['profile']==PROFILE,'Wrong version/build/profile')
    require(integer(record['pid'],1,2**32-1) and hex_id(record['creation'],16)
            and hex_id(record['session'],32) and hex_id(record['dll_sha256'],64)
            and hex_id(record['manifest_sha256'],64),'Invalid process/session/build identity')
    require(type(record['stage']) is str and record['stage'] in STAGES
            and integer(record['sequence'],1,3) and record['sequence']==STAGES.index(record['stage'])+1,
            'Only three ordered explicit stages')
    require(integer(record['expires'],1,MAX_UPTIME),'Expiry type/range')
    require(record['actor']=='FRA' and record['target']=='ENG' and record['value'] is True
            and integer(record['state'],0,0) and integer(record['envoy'],-1,-1),
            'Only fixed FRA to ENG true/state0/envoy-1')
    values=dict(record,value=1)
    raw=(PROTOCOL+'\n'+''.join(key+'='+str(values[key])+'\n' for key in FIELDS)).encode('ascii')
    require(len(raw)<=MAX_WIRE,'Wire byte budget');return raw


def decode(raw):
    require(type(raw) is bytes and 0<len(raw)<=MAX_WIRE and raw.endswith(b'\n'),
            'Complete bounded bytes required')
    require(all(c==10 or 32<=c<=126 for c in raw),'Only LF printable ASCII')
    lines=raw.decode('ascii').splitlines()
    require(len(lines)==len(FIELDS)+1 and lines[0]==PROTOCOL,'Exact protocol and line count')
    record={}
    for key,line in zip(FIELDS,lines[1:]):
        require(line.startswith(key+'='),'Exact field ordering required')
        record[key]=line[len(key)+1:]
    for key in ('pid','sequence','expires','state'):
        require(re.fullmatch('0|[1-9][0-9]{0,19}',record[key]) is not None,'Canonical decimal integer')
        record[key]=int(record[key])
    require(record['value']=='1' and record['envoy']=='-1','Fixed value/envoy')
    record['value']=True;record['envoy']=-1
    require(encode(record)==raw,'Canonical rendering differs');return record


def validate_claim_wire(raw, session, now_ms, expected_stage):
    """Pure pre-consumption check, not a durable claim or identity attestation.

    The future native consumer must rerun the TTL/identity/phase guards on its
    owner thread immediately before every call. No retry state is created here.
    """
    require(type(session) is dict and set(session)==set(('pid','creation','session','dll_sha256','manifest_sha256')),
            'Exact proposed session binding')
    require(type(expected_stage) is str and expected_stage in STAGES,'Expected phase required')
    record=decode(raw)
    require(all(type(record[k]) is type(v) and record[k]==v for k,v in session.items()),'Foreign session')
    require(record['stage']==expected_stage and integer(now_ms,0,MAX_UPTIME)
            and now_ms<record['expires'] and record['expires']-now_ms<=MAX_TTL_MS,
            'Wrong/expired/oversized phase window')
    return record


def descriptor():
    return {'protocol':PROTOCOL,'purpose':PURPOSE,'profile':PROFILE,'stages':list(STAGES),
            'families':list(FAMILIES),'actor':'FRA','target':'ENG','value':True,'state':0,'envoy':-1,
            'deployed':False,'native_host_implemented':False,'native_log_replay_implemented':False,
            'publisher_implemented':False,'native_call_authorized':False,'send_supported':False,
            'runtime_verified':False,'production_ready':False}
