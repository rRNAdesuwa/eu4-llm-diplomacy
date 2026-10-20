"""Private synthetic context-stamp checks. No memory reader or execution permission."""
from copy import deepcopy
import re

PTR_FIELDS=('module_base','game','database','countries','actor_country','target_country',
            'server','holder','context','transport','server_vtable','context_getter',
            'transport_vtable','transport_submit','transport_queue_getter')
INT_FIELDS={'pid':(1,2**32-1),'owner_thread':(1,2**32-1),'thread':(1,2**32-1),
            'date':(1,2**31-1),'frame_call':(1,2**64-1),'uptime_ms':(0,2**64-1),
            'ready55':(0,255),'ready80d':(0,255)}
TEXT_FIELDS={'creation':16,'session':32,'exe_sha256':64,'dll_sha256':64,'manifest_sha256':64}
HANDLES={'actor_handle':0x0100007a00415246,'player_handle':0x0100007a00415246,'target_handle':0x0100002e00474e45}
KEYS=set(PTR_FIELDS)|set(INT_FIELDS)|set(TEXT_FIELDS)|set(HANDLES)
GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
# Function pointers need not be 8-byte aligned (the observed queue getter is aligned,
# but alignment here is a per-field data contract, not a blanket native code rule).
CODE_FIELDS={'context_getter','transport_submit','transport_queue_getter'}


def require(test,why):
    if not test:raise ValueError(why)
def uint(value,lo,hi):return type(value) is int and lo<=value<=hi


def validate_stamp(value):
    require(type(value) is dict and set(value)==KEYS,'exact private stamp fields')
    for name in PTR_FIELDS:
        ptr=value[name]
        require(uint(ptr,0x10000,0x7fffffffffff),'pointer type/range '+name)
        if name not in CODE_FIELDS:require(ptr%8==0,'pointer alignment '+name)
    for name,(lo,hi) in INT_FIELDS.items():require(uint(value[name],lo,hi),'integer '+name)
    for name,length in TEXT_FIELDS.items():
        raw=value[name]
        require(type(raw) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',raw) is not None
                and int(raw,16)>0,'canonical text '+name)
    require(value['exe_sha256']==GAME_SHA,'exact executable')
    for name,expected in HANDLES.items():
        require(type(value[name]) is int and value[name]==expected,'full handle '+name)
    require(value['thread']==value['owner_thread'],'owner-thread assertion')
    base=value['module_base']
    for name,rva in [('server_vtable',0x1cb8460),('context_getter',0x811aa0),
                     ('transport_vtable',0x1d96178),('transport_submit',0x1580370),
                     ('transport_queue_getter',0x8b0e0)]:
        require(value[name]==base+rva,'fixed module identity '+name)
    return deepcopy(value)


def check_fresh(before,after,*,now_ms,expires_ms):
    """Compare supplied synthetic snapshots. Never authenticates who produced them."""
    left=validate_stamp(before);right=validate_stamp(after)
    require(uint(now_ms,0,2**64-1) and uint(expires_ms,1,2**64-1),'clock input')
    require(left['uptime_ms']<=right['uptime_ms']==now_ms<expires_ms,'fresh observation/TTL')
    for key in KEYS-{'uptime_ms'}:require(left[key]==right[key],'private stamp changed '+key)
    ready=right['ready55']!=0 or right['ready80d']!=0
    return dict(origin='pure_synthetic_context_stamp',same_recorded_context=True,
        readiness_nonzero=ready,restricted_readiness_path_candidate=ready,
        submit_permission=False,raw_graph_authenticated=False,actual_guard_verified=False,
        lifetime_verified=False,strict_sp_verified=False,world_epoch_verified=False,
        runtime_verified=False,production_ready=False)


def transfer_observation(*,entered,returned,accepted,slot_null,exception_code):
    require(type(entered) is bool and type(returned) is bool,'call boundary bools')
    require((accepted is None or type(accepted) is bool) and
            (slot_null is None or type(slot_null) is bool),'nullable return bools')
    require(uint(exception_code,0,2**32-1),'exception code')
    if not entered:
        require(not returned and accepted is None and slot_null is None and exception_code==0,'unentered outcome')
        outcome='not_entered';unknown=False
    else:
        acknowledged=returned and accepted is True and slot_null is True and exception_code==0
        outcome='transport_acknowledged' if acknowledged else 'dispatch_unknown';unknown=not acknowledged
    return dict(outcome=outcome,caller_ownership_relinquished=entered,
        freeze_required=unknown,read_or_destroy_transferred_command_allowed=False,
        retry_allowed=False,effect_verified=False,execution_permission=False,production_ready=False)
