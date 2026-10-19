"""Independent file-only reconstruction of the retained live relation bytes."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import read, decode, require

LIVE = 'work/reports/relation-effect-observer-20261015/live-80340-current-relations.json'
LIVE_SHA = '4fcfddb5e8551a132a188a601aa74d9d45a4e663e7591d27c711d76594edbbe9'
LAYOUTS = {'offer_alliance': (0x78, 0x1C7A740, 0x48, True),
    'royal_marriage': (0x60, 0x1C80BE0, 0x40, True),
    'guarantee': (0x198, 0x1C817D8, 0x48, False)}
EXPECTED = [('offer_alliance','FRA','POR','current_relation_observed'),
    ('offer_alliance','POR','FRA','current_relation_observed'),
    ('royal_marriage','ORL','BRI','current_relation_observed'),
    ('guarantee','FRA','SAV','current_relation_observed'),
    ('guarantee','SAV','FRA','reverse_relation_observed'),
    ('offer_alliance','FRA','ENG','pair_absent_observed')]


def sha(raw):return hashlib.sha256(raw).hexdigest()


def handle(value, tag):
    raw = value.to_bytes(8,'little')
    slot = struct.unpack_from('<h',raw,4)[0]
    require(raw[:3] == tag.encode('ascii') and raw[3] == raw[6] == 0
        and raw[7] != 0 and 0 < slot < 1380,'Complete country handle differs')
    return slot


def audit():
    raw = read(ROOT/LIVE, 2*1024*1024)
    require(sha(raw) == LIVE_SHA,'Retained live receipt differs')
    d = decode(raw)
    require(d['schema'] == 'EU4-RELATION-CURRENT-LIVE-ACCEPTANCE/1'
        and len(d['captures']) == 6,'Live scope differs')
    inputs = {LIVE: dict(bytes=len(raw),sha256=sha(raw))}
    for name, pin in d['source_pins'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,'Input path bound')
        data = read(ROOT/name,16*1024*1024)
        actual = dict(bytes=len(data),sha256=sha(data))
        require(actual == pin,'Retained source differs: '+name);inputs[name]=actual
    name = d['producer']['path'];data=read(ROOT/name,65536)
    require(sha(data)==d['producer']['sha256'],'Live producer differs')
    inputs[name]=dict(bytes=len(data),sha256=sha(data))
    require(d['identity']['pid']==80340 and d['identity']['creation']=='01dd5c075fcf8c26', 'Identity differs')
    for k in ('native_calls','requests_published','saves_written','reloads'):require(type(d[k]) is int and d[k]==0,k)
    for k in ('memory_written','new_API_effect_tested','global_membership_verified',
              'exact_external_request_id_causality_verified'):require(d[k] is False,k)
    require(d['rpm_budget']==dict(calls=2325,bytes=52162,largest_read=11040),'Shared budget differs')
    cases=[]
    for row,expected in zip(d['captures'],EXPECTED):
        action,actor,target,status=expected;s=row['state'];p=s['snapshot']
        require((row['action'],row['actor'],row['target'],s['status'])==expected,'Selected case differs')
        require(s['identity']==d['identity'] and s['action']==action and s['two_pass_equal'] is True
            and s['passes']==[p,p] and p['status']==status,'Passes/identity differ')
        pair=p['pair'];base=int(p['module_base'],16);off,vt,size,symmetric=LAYOUTS[action]
        handles=(int(pair['actor_handle'],16),int(pair['target_handle'],16))
        slots=(handle(handles[0],actor),handle(handles[1],target))
        require(pair['actor_tag']==actor and pair['target_tag']==target,'Pair differs')
        r=p['roots'];require(r['count']==r['capacity']==1380 and r['date']==p['now_raw']==56461512
            and r['manual_pause']==1 and r['reset']==r['load_source']==r['recalculating']==r['selector']==0,
            'Retained world guards differ')
        derived=[]
        for key,wanted,owner,ownhandle,ownslot in (('actor',slots[1],p['actor'],handles[0],slots[0]),
                                                    ('target',slots[0],p['target'],handles[1],slots[1])):
            require(owner['handle']==hex(ownhandle) and owner['slot']==ownslot,'Selected country differs')
            item=p['indexes'][key];header=bytes.fromhex(item['header_hex'])
            require(len(header)==24,'Header length')
            ivt,array,cap,count=struct.unpack('<QQii',header)
            require(ivt==base+0x1C3A538 and 0<=count<=256 and count<=cap<=4096,'Index type/signed bounds')
            require((cap==0 and array==0) or (cap>0 and 0x10000<=array<array+cap*16<=2**47 and array%8==0),'Allocation metadata')
            entries=bytes.fromhex(item['entries_hex']);require(len(entries)==count*16 and sha(entries)==item['records_sha256'],'Entries digest')
            decoded=list(struct.iter_unpack('<i4xQ',entries))
            require(len({i for i,_ in decoded})==count and all(0<i<1380 and 0x10000<=o<2**47 and o%8==0 for i,o in decoded),'Entry bounds/duplicates')
            selected=[o for i,o in decoded if i==wanted]
            pointer=selected[0] if selected else None
            require(not selected or sum(o==pointer for _,o in decoded)==1,'Selected pointer alias')
            require(item['container']==hex(int(owner['address'],16)+0x14F8+off)
                and item['array']==hex(array) and item['capacity_signed']==cap and item['count_signed']==count
                and item['object_pointer']==(hex(pointer) if pointer else None)
                and item['selected_member'] is bool(selected),'Decoded index differs')
            derived.append(dict(side=key,container=item['container'],vtable_rva=hex(ivt-base),array=hex(array),
                capacity=cap,count=count,selected_slot=wanted,selected_pointer=item['object_pointer'],
                decoded_entries=[dict(slot=i,pointer=hex(o)) for i,o in decoded]))
        require(derived[0]['selected_pointer']==derived[1]['selected_pointer'],'Bilateral indexes differ')
        obj=p['object'];object_check=None
        if status=='pair_absent_observed':require(obj is None and derived[0]['selected_pointer'] is None and s['current_relation_observed'] is False,'False absence')
        else:
            b=bytes.fromhex(obj['raw_object_hex']);require(len(b)==size,'Object extent')
            ovt,marker=struct.unpack_from('<QI',b);ends=struct.unpack_from('<QQ',b,0x10);date=struct.unpack_from('<i',b,0x20)[0]
            require(ovt==base+vt and marker==357 and ends in (handles,handles[::-1]) and 0<date<=p['now_raw']
                and b[0x28:0x2A]==b'\0\0','Object type/endpoints/lifecycle/date')
            direction=symmetric or ends==handles
            require(obj['address']==derived[0]['selected_pointer'] and obj['vtable_rva']==hex(vt)
                and obj['marker']==marker and obj['first_handle']==hex(ends[0]) and obj['second_handle']==hex(ends[1])
                and obj['started_raw_date']==date and obj['removed_byte_28']==obj['insertion_failed_byte_29']==0
                and obj['requested_direction_matches'] is direction
                and s['current_relation_observed'] is direction
                and (status=='current_relation_observed')==direction,'Object projection/direction differs')
            object_check=dict(address=obj['address'],bytes=len(b),vtable_rva=hex(vt),marker=marker,
                first_handle=hex(ends[0]),second_handle=hex(ends[1]),started_raw_date=date,
                removed=0,insertion_failed=0,requested_direction_matches=direction,sha256=sha(b))
        require(s['global_membership_verified'] is False and p['global_membership_verified'] is False,'Global overclaim')
        cases.append(dict(action=action,actor=actor,target=target,status=status,two_pass_equal=True,
            complete_handle_slots=list(slots),physical_indexes=derived,object=object_check,duration_ms=row['duration_ms']))
    return dict(schema='EU4-RELATION-LIVE-FILE-AUDIT/1',passed=True,source_pins=inputs,cases=cases,
        reported_live_rpm_budget=d['rpm_budget'],audit_game_process_accessed=False,new_RPM_calls=0,
        native_calls=0,requests_published=0,new_API_effect_tested=False,global_membership_verified=False,
        limitations=['File-only verification of retained bytes, not a new runtime observation.',
            'Country headers, full TAG table and relation record raw bytes were checked by the pinned live producer/reader but were not retained as raw bytes in this receipt.',
            'Index capacity is allocation metadata, not an allocator ownership proof.',
            'Two equal passes do not prove atomicity, world epoch, lifetime lease, request causality or global registration.'])


if __name__=='__main__':
    value=audit();dest=Path(__file__).parent/'live-file-audit.json'
    if '--check' in sys.argv:require(decode(read(dest,2*1024*1024))==value,'Audit replay differs')
    else:
        with dest.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(passed=True,cases=len(value['cases']),pins=len(value['source_pins']),
        sha256=sha(dest.read_bytes()),game_process_accessed=False)))
