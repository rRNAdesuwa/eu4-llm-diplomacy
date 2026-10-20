"""Pure bounded reader for the audited R15 current context; no OS or calls.

Only supplied read(address,size) bytes are consumed. The values are current
diagnostics, never a borrowed-object lease, predicate result or sender permit.
"""
import struct

MIN, MAX = 0x10000, 0x7FFFFFFF0000
PLAN = (
    ('outer','base',0x242BF50,8,'pointer',None),
    ('game','base',0x233FE78,8,'pointer',None),
    ('outer_vtable','outer',0,8,'pointer',0x1C48BF8),
    ('outer_secondary_vtable','outer',0x10,8,'pointer',0x1C48C80),
    ('game_vtable','game',0,8,'pointer',0x1CB00C8),
    ('current','outer',0x40,8,'pointer',None),
    ('server','game',0x1E00,8,'pointer',None),
    ('server_vtable','server',0,8,'pointer',0x1CB8460),
    ('holder','server',0x330,8,'pointer',None),
    ('map_pointer','holder',0x360,8,'pointer',None),
    ('context','holder',0x370,8,'optional',None),
    ('context_vtable','context',0,8,'pointer',0x1D8C900),
    ('transport','context',0x58,8,'optional',None),
    ('transport_vtable','transport',0,8,'pointer',0x1D96178),
    ('transport_context_backlink','transport',0x70,8,'pointer',None),
    ('getter_endpoint','server_vtable',0x80,8,'pointer',0x811AA0),
    ('context_delete_endpoint','context_vtable',0,8,'pointer',0x14C88F0),
    ('transport_delete_endpoint','transport_vtable',0,8,'pointer',0x15800D0),
    ('transport_submit_endpoint','transport_vtable',0x30,8,'pointer',0x1580370),
    ('sender_flag55','context',0x55,1,'uint8',None),
    ('sender_flag80d','context',0x80D,1,'uint8',None),
    ('command_word_source68','context',0x68,4,'int32',None),
    ('command_dword_source8c','context',0x8C,4,'uint32',None),
    ('dispatch_flag7d4','context',0x7D4,1,'uint8',None),
    ('dispatch_flag841','context',0x841,1,'uint8',None),
)


def require(value, message):
    if not value:
        raise ValueError(message)


def span(address,size):
    require(type(address) is int and type(size) is int and 0 < size <= 8
            and MIN <= address < address+size <= MAX,'Invalid selected address/span')
    return address


def pointer(value):
    span(value,8)
    require(value % 8 == 0,'Unaligned selected pointer')
    return value


def h(value):
    return '0x'+format(value,'016x')


def sample(reader,base):
    result = dict(schema='EU4-CURRENT-CHILD-CONTEXT-PROJECTION/1',status='unknown',fields={},reads=[],
        requested_reads=0,requested_bytes=0,exact_bytes=0,
        limits=dict(reads=25,bytes=164,single_read=8),native_game_calls=0,game_fields_written=0,
        sender_authorized=False,native_ready=False,lifetime_lease=False,atomic_snapshot=False,
        native_entry_authenticated=False,diagnostics_are_predicate_results=False,
        endpoint_code_bytes_verified=False,owner_reference_or_lock_acquired=False)
    values = {}
    try:
        values['base'] = pointer(base)
        for name,receiver,offset,size,kind,expected in PLAN:
            address = span(values[receiver]+offset,size)
            require(result['requested_reads'] < 25 and result['requested_bytes']+size <= 164,'Selected read budget')
            result['requested_reads'] += 1
            result['requested_bytes'] += size
            raw = reader.read(address,size)
            require(type(raw) is bytes and len(raw) == size,'Exact selected bytes unavailable')
            result['exact_bytes'] += size
            value = struct.unpack('<i' if kind == 'int32' else '<I' if size == 4 else '<Q' if size == 8 else '<B',raw)[0]
            result['reads'].append(dict(field=name,receiver=receiver,address=h(address),size=size,
                raw_hex=raw.hex(),value=h(value) if size == 8 else value))
            result['fields'][name] = h(value) if size == 8 else value
            if kind == 'optional' and value == 0:
                result.update(status=name+'_absent',reason='Selected current slot is null')
                return result
            if kind in ('pointer','optional'):
                pointer(value)
            if expected is not None:
                require(value == base+expected,'Unsupported selected type/endpoint: '+name)
            values[name] = value
            if name == 'server':
                require(value == values['current'],'Current/server pointer values differ')
            if name == 'holder':
                require(value == values['outer'],'Holder is not this pass fresh outer')
            if name == 'transport_context_backlink':
                require(value == values['context'],'Transport backlink differs')
        require(result['requested_reads'] == 25 and result['requested_bytes'] == result['exact_bytes'] == 164,
                'Complete projection budget differs')
        result.update(status='typed_context_transport_observed',reason='Selected fresh chain and endpoints match')
    except (ValueError,TypeError,KeyError,OverflowError,OSError,struct.error) as exc:
        result.update(status='unknown',failure=dict(type=type(exc).__name__,message=str(exc)))
    return result
