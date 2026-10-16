"""Pure whole-payload replay for source-only owned body ABI probe.

Independent copy of entry parser 56639f22 (exact origin pin in manifest).
No fake old zero-call envelope is built; no original parser is imported.
No address is dereferenced.

Profile source: entry_observer.js SHA256
4b2107d0a912280c271be66e5436482f1e89bfb348b326dfd25daf2d3308820e;
CONTRACT.md SHA256
f55ecb7edc2ab9bf25bc260b143c44f80711baa25627b64f4911530ecd5e59d0.

Matching supplied metadata/bytes is not process authentication. Prefix bytes
read before/after the hook are not retained in the payload; cleanup flags are
producer statements only. Held identity, REA evidence and independent code
restoration must be verified by the host. No process, Frida or native API here.
"""
import json
import re

GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
PREFIX = '4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f'
ENTRY_RVA = 0x10A6EC0
SOURCE = 'Frida_Interceptor_onEnter_before_original_prologue'
MIN_ADDRESS, MAX_ADDRESS = 0x10000, 0x7FFFFFFF0000
RETURNS = ((0,0x10A6D61),(0x40,0x81582E),(0x370,0x14C2818),
           (0x3F0,0x14C2E18),(0x440,0x8781B9))
CONFIG_KEYS = {'schema','pid','creation','game_sha256','base','expected_prefix_hex','observer_nonce','max_attempts'}
FALSE_FLAGS = {'pure_RPM','native_ready','native_entry_authenticated','creation_authenticated_in_script',
               'image_sha_verified_in_script','lifetime_lease','atomic_snapshot'}
ZERO_FIELDS = {'field_game_data_writes','native_game_objects_constructed'}
PAYLOAD_KEYS = {'schema','status','reason','observer_nonce','configured_pid','configured_creation',
    'configured_game_sha256','module_base','entry_rva','attempts','observation','temporary_code_hook',
    'budgets','counters','cleanup','probe','requires_host_authentication',
    'native_game_calls_attempted','native_game_calls_returned'} | FALSE_FLAGS | ZERO_FIELDS
CATEGORIES = {'prefix_before','prefilter','stack','world','prefix_cleanup',
    'code_before','code_after','owned_before','owned_after'}
WORLD_FIELDS = {'outer','game','outer_vtable','outer_secondary_vtable','current_app','pending_app',
    'previous_app','transition_byte','retain_previous_byte','game_vtable','game_server','current_vtable',
    'current_update','server_holder','map_object','pending_vtable','previous_vtable'}
CLEANUP_KEYS = {'listener_detach_attempted','listener_detach_returned','interceptor_flush_returned',
                'original_prefix32_matches','host_cleanup_still_required'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mapping(value, keys, label):
    require(type(value) is dict and set(value) == keys, label+' fields differ')
    return value


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high, label+' integer/range differs')
    return value


def text(value, pattern, label):
    require(type(value) is str and re.fullmatch(pattern,value) is not None, label+' encoding differs')
    return value


def wire_bound(value, maximum):
    """Bound JSON-shaped input before projection; no unbounded serialization.

    Counts compact JSON size one bounded scalar at a time. The payload wrapper
    sent by the script is accounted for by the caller. Rejects arbitrary Python
    objects, deep containers, nonfinite numbers and huge scalar encodings.
    """
    nodes = 0
    def count(item, depth):
        nonlocal nodes
        nodes += 1
        require(depth <= 10 and nodes <= 1024, 'JSON nesting/node bound')
        kind = type(item)
        if kind is dict:
            require(len(item) <= 64 and all(type(k) is str for k in item), 'JSON object shape bound')
            size = 2
            for index,(key,child) in enumerate(item.items()):
                size += count(key,depth+1)+1+count(child,depth+1)+(1 if index else 0)
                require(size <= maximum, 'JSON message size bound')
        elif kind is list:
            require(len(item) <= 64, 'JSON array bound')
            size = 2
            for index,child in enumerate(item):
                size += count(child,depth+1)+(1 if index else 0)
                require(size <= maximum, 'JSON message size bound')
        else:
            require(item is None or kind in (str,int,bool), 'Unsupported JSON scalar type')
            if kind is str:
                require(len(item) <= maximum and item.isascii(), 'JSON string bound/ASCII differs')
            if kind is int:
                require(item.bit_length() <= 64, 'JSON integer size bound')
            size = len(json.dumps(item,ensure_ascii=True,separators=(',',':')))
        require(size <= maximum, 'JSON message size bound')
        return size
    return count(value,0)


def u64(value, label):
    text(value,r'0x[0-9a-f]{16}',label)
    return int(value,16)


def span(address, size, label):
    require(type(address) is int and type(size) is int and 1 <= size <= 0x40000000
            and MIN_ADDRESS <= address < address+size <= MAX_ADDRESS, label+' address span differs')
    return address


def pointer(value, label, optional=False):
    address = u64(value,label)
    if optional and address == 0:
        return 0
    span(address,8,label)
    require(address % 8 == 0,label+' alignment differs')
    return address


def h(value):
    return '0x'+format(value,'016x')


def raw_value(raw, size, label):
    text(raw,r'[0-9a-f]{'+str(size*2)+'}',label)
    value = int.from_bytes(bytes.fromhex(raw),'little')
    return value if size == 1 else h(value)


def same(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(same(left[key],right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(same(a,b) for a,b in zip(left,right))
    return left == right


def checked_config(config):
    wire_bound(config,2048)
    mapping(config,CONFIG_KEYS,'Config')
    require(config['schema'] == 'EU4-FRIDA-BODY-PROBE-CONFIG/1' and config['game_sha256'] == GAME_SHA
            and config['expected_prefix_hex'] == PREFIX, 'Fixed config profile differs')
    integer(config['pid'],1,0xFFFFFFFF,'Config PID')
    integer(config['max_attempts'],16,16,'Config attempts')
    text(config['creation'],r'[0-9a-f]{16}','Config creation')
    text(config['observer_nonce'],r'[0-9a-f]{32}','Config nonce')
    # validateConfig accepts non-padded/case-insensitive hex, then normalizes it.
    text(config['base'],r'0[xX][0-9a-fA-F]{1,16}','Config base')
    base = int(config['base'],16)
    span(base,0x2433E90,'Config module')
    require(base == 0x7FF7034B0000 and config['pid'] == 80340
            and config['creation'] == '01dd5c075fcf8c26','Fixed process identity differs')
    return base


def checked_counters(payload):
    budget = mapping(payload['budgets'],{'scope','max_reads','max_bytes','max_message_envelope_bytes',
                                        'stack_window_read'},'Budget')
    require(budget['scope'] == 'all explicit readByteArray requests in this script'
            and budget['stack_window_read'] is False, 'Budget scope/window differs')
    for name,expected in (('max_reads',192),('max_bytes',16384),('max_message_envelope_bytes',32768)):
        integer(budget[name],expected,expected,'Budget '+name)
    counters = mapping(payload['counters'],{'reads','requested_bytes','exact_bytes','categories'},'Counter')
    integer(counters['reads'],0,192,'Total reads')
    integer(counters['requested_bytes'],0,16384,'Requested bytes')
    integer(counters['exact_bytes'],0,counters['requested_bytes'],'Exact bytes')
    categories = mapping(counters['categories'],CATEGORIES,'Counter category')
    for name,row in categories.items():
        mapping(row,{'reads','bytes'},name+' counter')
        integer(row['reads'],0,192,name+' reads')
        integer(row['bytes'],0,16384,name+' bytes')
    require(sum(row['reads'] for row in categories.values()) == counters['reads']
            and sum(row['bytes'] for row in categories.values()) == counters['requested_bytes'],
            'Category sums differ from total')
    return counters


def checked_pass(project, base, q, rcx, r8):
    mapping(project,{'slots','fields','reads'},'Projection')
    slots = project['slots']
    require(type(slots) is list and len(slots) == 6,'Exactly six owned slots required')
    fields = mapping(project['fields'],WORLD_FIELDS,'World')
    outer = pointer(fields['outer'],'outer')
    game = pointer(fields['game'],'game')
    current = pointer(fields['current_app'],'current')
    pending = pointer(fields['pending_app'],'pending',optional=True)
    previous = pointer(fields['previous_app'],'previous',optional=True)
    server = pointer(fields['game_server'],'server')
    holder = pointer(fields['server_holder'],'server holder')
    require(current == server == r8,'Current/server/original R8 differs')
    for name,expected in (('outer_vtable',base+0x1C48BF8),('outer_secondary_vtable',base+0x1C48C80),
        ('game_vtable',base+0x1CB00C8),('current_vtable',base+0x1CB8460),
        ('current_update',base+0x8137C0),('map_object',rcx)):
        require(u64(fields[name],name) == expected,name+' typed projection differs')
    for name in ('transition_byte','retain_previous_byte'):
        integer(fields[name],0,255,name)
    for index,(offset,expected) in enumerate(tuple((offset,base+rva) for offset,rva in RETURNS)+((0x4A8,outer),)):
        row = mapping(slots[index],{'offset','address','raw8_hex','value'},'Owned slot')
        integer(row['offset'],offset,offset,'Slot offset')
        require(u64(row['address'],'Slot source') == span(q+offset,8,'Slot source'), 'Slot actual Q+offset differs')
        value = raw_value(row['raw8_hex'],8,'Slot raw8')
        require(row['value'] == value == h(expected),'Slot raw/value/expected return or holder differs')
    layout = [
        ('outer',base+0x242BF50,8),('game',base+0x233FE78,8),
        ('outer_vtable',outer,8),('outer_secondary_vtable',outer+0x10,8),
        ('current_app',outer+0x40,8),('pending_app',outer+0x70,8),('previous_app',outer+0x78,8),
        ('transition_byte',outer+0x48,1),('retain_previous_byte',outer+0x80,1),
        ('game_vtable',game,8),('game_server',game+0x1E00,8),('current_vtable',current,8),
        ('current_update',base+0x1CB8460+0x20,8),('server_holder',server+0x330,8),
        ('map_object',holder+0x360,8)]
    for name,address in (('pending_vtable',pending),('previous_vtable',previous)):
        if address:
            # This is only a raw uint64 diagnostic; it need not be a pointer.
            u64(fields[name],name)
            layout.append((name,address,8))
        else:
            require(fields[name] is None,name+' must be null without an optional object')
    reads = project['reads']
    require(type(reads) is list and len(reads) == len(layout),'World read count differs')
    for row,(name,address,size) in zip(reads,layout):
        mapping(row,{'field','address','size','raw_hex'},'World read')
        require(row['field'] == name,'World read field/order differs')
        integer(row['size'],size,size,'World read size')
        require(u64(row['address'],'World read source') == span(address,size,'World field'),
                'World actual field address differs: '+name)
        decoded = raw_value(row['raw_hex'],size,'World raw '+name)
        require(same(fields[name],decoded),'World raw/field differs: '+name)
    return int(bool(pending))+int(bool(previous))


CODE = (('0x500560', 5244256, 109, '40534883ec20488bd9488d0520087801488901488b4948488b01ff507884c0741e488b4b484885c9740a488b01ba01000000ff10488b0595fae30148894348488d8b80000000e815e5b8ff488d4b68e80ce5b8ff488d4b50e803e5b8ff488d05b4df73014889034883c4205bc3'), ('0x8eac0', 584384, 91, '40534883ec20488bd9488b094885c9743e488b5310482bd14883e2f84881fa0010000072184c8b41f84883c227492bc8488d41f84883f81f771b498bc8e8eea96a0133c048890348894308488943104883c4205bc3e852319b01cc'), ('0x8f450', 586832, 3, '32c0c3'))

PROFILE = 'owned-zero-A98-G60-body500560-v1'
OPTIONS = dict(abi='win64',scheduling='exclusive',exceptions='propagate',traps='none')
PROBE_KEYS = {'profile','spent','allocations','before','after','call','owned_writes'}


def checked_probe_counters(payload):
    probe = mapping(payload['probe'],PROBE_KEYS,'Probe')
    require(probe['profile'] == PROFILE and type(probe['spent']) is bool,'Probe profile/spent differs')
    call = mapping(probe['call'],{'entry_rva','signature','options','attempted','returned'},'Call')
    require(call['entry_rva'] == '0x500560' and call['signature'] == 'void(pointer)'
            and same(call['options'],OPTIONS),'Call target/signature/options differs')
    integer(call['attempted'],0,1,'Call attempted')
    integer(call['returned'],0,call['attempted'],'Call returned')
    require(not call['attempted'] or probe['spent'] is True,'Call before permanent spent flag')
    for source,target in (('native_game_calls_attempted','attempted'),('native_game_calls_returned','returned')):
        integer(payload[source],call[target],call[target],source)
    writes = mapping(probe['owned_writes'],{'attempts','returned','requested_bytes','completed_bytes'},'Owned writes')
    integer(writes['attempts'],0,4,'Owned write attempts')
    integer(writes['returned'],0,writes['attempts'],'Owned write returned')
    integer(writes['requested_bytes'],0,264,'Owned write requested bytes')
    integer(writes['completed_bytes'],0,writes['requested_bytes'],'Owned write completed bytes')
    return probe


def checked_probe(probe, base):
    require(probe['spent'] is True and probe['call']['attempted'] == probe['call']['returned'] == 1,
            'Successful probe was not attempted and returned once')
    require(probe['owned_writes'] == dict(attempts=4,returned=4,requested_bytes=264,completed_bytes=264),
            'Owned write success accounting differs')
    allocations = mapping(probe['allocations'],{'A','G'},'Allocations')
    addresses = {}
    for name,size in (('A',152),('G',96)):
        row = mapping(allocations[name],{'address','size'},'Owned allocation '+name)
        integer(row['size'],size,size,'Owned size '+name)
        address = u64(row['address'],'Owned address '+name)
        span(address,size,'Owned '+name)
        require(address % 16 == 0,'Owned buffer alignment differs')
        addresses[name] = address
    a,g = addresses['A'],addresses['G']
    require(a+152 <= g or g+96 <= a,'Owned buffers overlap')
    before_a = bytearray(152)
    before_a[0x48:0x50] = g.to_bytes(8,'little')
    expected_g = (base+0x1D207F8).to_bytes(8,'little')+bytes(88)
    after_a = bytearray(before_a)
    after_a[:8] = (base+0x1C3E578).to_bytes(8,'little')
    for phase,expected_a in (('before',before_a),('after',after_a)):
        snapshot = mapping(probe[phase],{'code','slot','owned'},'Probe '+phase)
        code = snapshot['code']
        require(type(code) is list and len(code) == 3,'Full code scopes differ')
        for row,(rva,offset,size,raw) in zip(code,CODE):
            mapping(row,{'rva','address','size','raw_hex'},'Code row')
            require(row['rva'] == rva,'Code RVA/order differs')
            integer(row['size'],size,size,'Code size')
            require(u64(row['address'],'Code source') == base+offset,'Code actual source differs')
            require(row['raw_hex'] == raw,'Code full bytes differ')
        slot = mapping(snapshot['slot'],{'rva','address','raw8_hex','value'},'Goal slot')
        require(slot['rva'] == '0x1d20870' and u64(slot['address'],'Slot source') == base+0x1D20870,
                'Goal slot source differs')
        require(raw_value(slot['raw8_hex'],8,'Goal slot raw') == slot['value'] == h(base+0x8F450),
                'Goal relocated slot differs')
        owned = mapping(snapshot['owned'],{'A_hex','G_hex'},'Owned raw')
        require(owned['A_hex'] == expected_a.hex() and owned['G_hex'] == expected_g.hex(),
                'Owned full '+phase+' bytes differ')
    return addresses


def evaluate(payload, config):
    """Replay the new whole script schema; never dereference/invoke/claim authority."""
    result = dict(schema='EU4-FRIDA-BODY-PROBE-EVALUATION/1',status='unknown',
        raw_abi_postcondition_match=False,requires_host_authentication=True,requires_rea_evidence=True,
        requires_independent_code_restore_verification=True,host_identity_authenticated=False,
        creation_authenticated=False,image_sha_verified=False,code_restore_verified=False,
        native_ready=False,native_entry_authenticated=False,lifetime_lease=False,atomic_snapshot=False,
        AI_acceptance_verified=False,gameplay_effects_verified=False,pure_RPM=False,
        native_Cpp_object_verified=False,constructor_equivalence=False,full_native_lifecycle=False,
        parser_dereferences_addresses=False,reason='evidence_not_validated',observational_flags={})
    try:
        base = checked_config(config)
        require(wire_bound(payload,32768)+len('{"type":"send","payload":}') <= 32768,'Send envelope size bound')
        mapping(payload,PAYLOAD_KEYS,'Payload')
        require(payload['schema'] == 'EU4-FRIDA-BODY-PROBE-OBSERVATION/1'
                and payload['status'] in ('raw_abi_postcondition_match','unknown'),'Payload schema/status differs')
        text(payload['reason'],r'[\x20-\x7e]{1,256}','Producer reason')
        result['producer_reason'] = payload['reason']
        for name in FALSE_FLAGS:
            require(payload[name] is False,'Producer authority flag is not false: '+name)
        for name in ZERO_FIELDS:
            integer(payload[name],0,0,'Producer '+name)
        require(payload['requires_host_authentication'] is True,'Producer must require host authentication')
        require(type(payload['temporary_code_hook']) is bool,'Hook flag must be boolean')
        integer(payload['entry_rva'],ENTRY_RVA,ENTRY_RVA,'Entry RVA')
        integer(payload['attempts'],0,16,'Attempts')
        require(payload['configured_game_sha256'] == GAME_SHA,'Configured image SHA differs')
        counters = checked_counters(payload)
        probe = checked_probe_counters(payload)
        result.update(native_game_calls_attempted=probe['call']['attempted'],
                      native_game_calls_returned=probe['call']['returned'])
        cleanup = payload['cleanup']
        require(type(cleanup) is dict and set(cleanup) <= CLEANUP_KEYS
                and cleanup.get('host_cleanup_still_required') is True
                and all(type(value) is bool for value in cleanup.values()),'Cleanup report differs')
        if payload['status'] == 'unknown':
            result['reason'] = 'producer_unknown'
            return result
        require(payload['reason'] == 'owned_body_postcondition_observed','Success reason differs')
        require(payload['observer_nonce'] == config['observer_nonce']
                and payload['configured_creation'] == config['creation'],'Observer nonce/creation binding differs')
        integer(payload['configured_pid'],config['pid'],config['pid'],'Configured PID')
        require(u64(payload['module_base'],'Observed module base') == base,'Module base binding differs')
        require(payload['temporary_code_hook'] is True and set(cleanup) == CLEANUP_KEYS
                and all(value is True for value in cleanup.values()),'Successful cleanup statements unavailable')
        attempts = integer(payload['attempts'],1,16,'Successful attempts')
        observation = mapping(payload['observation'],{'source','Q','original_rcx','original_r8','thread_id',
            'interceptor_depth','first','second','two_pass_equal'},'Observation')
        require(observation['source'] == SOURCE,'Observation is not original onEnter context')
        q = u64(observation['Q'],'Original Q')
        span(q,0x4B0,'Original Q')
        require(q % 16 == 8,'Original Q entry alignment differs')
        rcx = pointer(observation['original_rcx'],'Original RCX')
        r8 = pointer(observation['original_r8'],'Original R8')
        integer(observation['thread_id'],1,0xFFFFFFFF,'Thread ID')
        integer(observation['interceptor_depth'],0,0,'Interceptor depth')
        require(observation['two_pass_equal'] is True
                and same(observation['first'],observation['second']),'Two owned projections differ')
        optional = checked_pass(observation['first'],base,q,rcx,r8)
        require(checked_pass(observation['second'],base,q,rcx,r8) == optional,'Optional count differs')
        addresses = checked_probe(probe,base)
        categories = counters['categories']
        expected = {'prefix_before':(1,32),'prefix_cleanup':(1,32),'stack':(7,56),
                    'world':(2*(15+optional),2*(106+8*optional)),
                    'code_before':(4,211),'code_after':(4,211),'owned_before':(2,248),'owned_after':(2,248)}
        for name,(reads,nbytes) in expected.items():
            require(categories[name] == {'reads':reads,'bytes':nbytes},'Successful category count differs: '+name)
        prefilter = categories['prefilter']
        require(attempts+4 <= prefilter['reads'] <= 5*attempts
                and prefilter['bytes'] == 8*prefilter['reads'],'Prefilter attempts/read count differs')
        require(counters['reads'] > 0 and counters['requested_bytes'] > 0
                and counters['exact_bytes'] == counters['requested_bytes'],'Successful exact/requested bytes differ')
        flags = dict(entry_projection_matches=True,owned_preimage_matches=True,owned_postimage_matches=True,
            before_after_code_slot_matches=True,native_call_attempted=True,native_call_returned=True,
            script_cleanup_report_consistent=True,all_explicit_reads_accounted_for=True,
            all_owned_writes_accounted_for=True)
        result.update(status='raw_abi_postcondition_match',raw_abi_postcondition_match=True,
            reason='owned_record_replay_matches',observational_flags=flags,
            observer_nonce=config['observer_nonce'],configured_pid=config['pid'],configured_creation=config['creation'],
            configured_game_sha256=GAME_SHA,module_base=h(base),entry_rva=ENTRY_RVA,Q=h(q),
            thread_id=observation['thread_id'],original_rcx=h(rcx),original_r8=h(r8),attempts=attempts,
            optional_nonnull_count=optional,owned_allocations={name:h(value) for name,value in addresses.items()},
            explicit_reads=counters['reads'],explicit_requested_bytes=counters['requested_bytes'],
            explicit_exact_bytes=counters['exact_bytes'],script_owned_write_requests=4,
            script_owned_write_requested_bytes=264,script_owned_write_completed_bytes=264,
            temporary_code_hook_declared=True)
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:
        result.update(reason='invalid_or_incomplete_evidence',failure=dict(type=type(exc).__name__,message=str(exc)))
    return result
