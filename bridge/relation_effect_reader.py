"""Bounded current indexed alliance/marriage/guarantee observation.

Only a caller-supplied, already identity-verified read port is used. No process
opening, game calls, writes, requests, callbacks or global membership claims.
"""
import json
from pathlib import Path
import re
import struct

from bridge.diplomacy_effect_observer import BudgetReader, LIMITS, roots, country, relation, ptr, full_handle
from bridge.tag_command_backend import ROOT, GAME_SHA, DEFAULT_MANIFEST, read, digest, decode, require, validate_identity, validate_command

SCHEMA = 'EU4DIPLOMACY-RELATION-PAIR/1'
SOURCE_MANIFEST = ROOT/'bridge/relation_effect_reader_manifest_1375.json'
INDEX_VT = 0x1C3A538
MAX_CAPACITY = 4096
PROFILES = {
    'offer_alliance': dict(index=0x78, object_vt=0x1C7A740, size=0x48, symmetric=True, reply_required=True,
        getter=0xA68D90, code='488b11488b411048c1e82098488b8a800000004c63828c00000049c1e0044c03c1493bc8740d3901740c4883c110493bc875f333c0c3488b4108c3'),
    'royal_marriage': dict(index=0x60, object_vt=0x1C80BE0, size=0x40, symmetric=True, reply_required=True,
        getter=0xA68BE0, code='488b11488b411048c1e82098488b4a684c63427449c1e0044c03c1493bc8740d3901740c4883c110493bc875f333c0c3488b4108c3'),
    'guarantee': dict(index=0x198, object_vt=0x1C817D8, size=0x48, symmetric=False, reply_required=False,
        getter=0xA6A050, code='488b11488b411048c1e82098488b8aa00100004c6382ac01000049c1e0044c03c1493bc8740d3901740c4883c110493bc875f333c0c3488b4108c3'),
}
ACTIONS = tuple(PROFILES)


def _index(r, base, root, offset, wanted, count):
    header = r.read(root+offset, 24)
    vt, array, capacity, used = struct.unpack('<QQii', header)
    require(vt == base+INDEX_VT, 'Relation typed index vtable mismatch')
    require(0 <= used <= LIMITS['index_entries'] and used <= capacity <= MAX_CAPACITY,
        'Relation signed index count/capacity bound')
    require((capacity == 0 and array == 0) or
        (capacity > 0 and 0x10000 <= array < array+capacity*16 <= 2**47 and array % 8 == 0),
        'Relation index allocation metadata mismatch')
    raw = r.read(ptr(array), used*16) if used else b''
    entries = list(struct.iter_unpack('<i4xQ', raw))
    require(all(0 < slot < min(count, 32768) and 0x10000 <= obj < 2**47 and obj % 8 == 0
        for slot, obj in entries), 'Relation index entry invalid')
    require(len({slot for slot, _ in entries}) == used, 'Duplicate relation index counterpart')
    matches = [obj for slot, obj in entries if slot == wanted]
    if matches:
        require(sum(obj == matches[0] for _, obj in entries) == 1,
            'Selected bilateral object aliased under another counterpart')
    require(r.read(root+offset, 24) == header and (not raw or r.read(array, len(raw)) == raw),
        'Relation index changed within sample')
    return dict(container=hex(root+offset), header_hex=header.hex(), array=hex(array),
        capacity_signed=capacity, count_signed=used, entries_hex=raw.hex(),
        records_sha256=digest(raw), object_pointer=hex(matches[0]) if matches else None,
        selected_member=bool(matches), allocation_metadata_guarded=True)


def _object(r, base, profile, address, actor, target, now):
    raw = r.read(ptr(address), profile['size'])
    require(struct.unpack_from('<QI', raw) == (base+profile['object_vt'], 357),
        'Relation object vtable/marker mismatch')
    first, second = struct.unpack_from('<QQ', raw, 0x10)
    forward = (int(actor['handle'], 16), int(target['handle'], 16))
    require((first, second) in (forward, forward[::-1]), 'Relation complete endpoints differ')
    start = struct.unpack_from('<i', raw, 0x20)[0]
    require(0 < start <= now, 'Relation start date unavailable/out of observed world')
    require(raw[0x28] == 0 and raw[0x29] == 0, 'Indexed relation removed or global insertion failed')
    require(r.read(address, profile['size']) == raw, 'Relation object changed within sample')
    return dict(address=hex(address), vtable_rva=hex(profile['object_vt']), marker=357,
        first_handle=hex(first), second_handle=hex(second), started_raw_date=start,
        removed_byte_28=raw[0x28], insertion_failed_byte_29=raw[0x29], raw_object_hex=raw.hex(),
        requested_direction_matches=profile['symmetric'] or (first, second) == forward)


def _sample(r, base, action, actor_handle, target_handle):
    profile = PROFILES[action]
    root = roots(r, base)
    require(root['manual_pause'] == 1, 'Relation observation requires explicit manual pause')
    actor, target = country(r, base, root, actor_handle), country(r, base, root, target_handle)
    require(actor['handle'] != target['handle'], 'Relation endpoints identical')
    a, b = relation(r, actor, target, base), relation(r, target, actor, base)
    code = bytes.fromhex(profile['code'])
    require(r.read(base+profile['getter'], len(code)) == code, 'Loaded relation getter code differs')
    left = _index(r, base, a['root'], profile['index'], target['slot'], root['count'])
    right = _index(r, base, b['root'], profile['index'], actor['slot'], root['count'])
    require(left['object_pointer'] == right['object_pointer'], 'Relation bilateral indexes disagree')
    obj = None
    if left['object_pointer'] is None:
        status, reason = 'pair_absent_observed', 'Neither current typed native index contains the selected counterpart'
    else:
        obj = _object(r, base, profile, int(left['object_pointer'], 16), actor, target, root['date'])
        status = 'current_relation_observed' if obj['requested_direction_matches'] else 'reverse_relation_observed'
        reason = 'The same current typed object is in both native indexes; complete endpoints and lifecycle flags verified'
    # Re-resolve the current graph. Never follow a pointer retained by a prior
    # capture, and reject same-header in-place index/record mutation as well.
    require(relation(r, actor, target, base)['data'] == a['data']
        and relation(r, target, actor, base)['data'] == b['data'], 'Relation record changed within sample')
    for item, owner, other in ((left, a, target), (right, b, actor)):
        require(_index(r, base, owner['root'], profile['index'], other['slot'], root['count']) == item,
            'Relation index changed after object read')
    require(country(r, base, root, actor_handle) == actor and country(r, base, root, target_handle) == target,
        'Relation country identity changed')
    require(roots(r, base) == root, 'Relation roots/date/guards changed')
    return dict(status=status, reason=reason, module_base=hex(base), now_raw=root['date'], roots=root,
        pair=dict(actor_tag=actor['tag'], target_tag=target['tag'], actor_handle=actor['handle'], target_handle=target['handle']),
        actor=actor, target=target, indexes={'actor': left, 'target': right}, object=obj,
        records_sha256={'actor': digest(a['data']), 'target': digest(b['data'])},
        native_index_presence_observed=status == 'current_relation_observed',
        typed_index_allocation_guards_verified=True, object_lifecycle_flags_verified=obj is not None,
        global_membership_verified=False, global_membership_status='not_sampled',
        effective_movement_permission_verified=False, expiry_or_full_lifecycle_verified=False,
        reply_required_for_positive_action=profile['reply_required'])


def read_relation_pair(reader, base, action, actor_handle, target_handle, identity):
    """Two bounded passes through an already-held read-only port, never a lease."""
    result = dict(schema=SCHEMA, action=action, status='unknown', passes=[],
        current_relation_observed=False, global_membership_verified=False, native_calls=0,
        memory_written=False, requests_published=0, process_handle_opened=False,
        world_epoch_proven=False, atomic_snapshot_proven=False, AI_acceptance_verified=False)
    r = reader if isinstance(reader, BudgetReader) else BudgetReader(reader)
    try:
        require(action in ACTIONS, 'Unsupported relation action')
        result['identity'] = validate_identity(identity)
        ptr(base)
        for _ in range(2):result['passes'].append(_sample(r, base, action, actor_handle, target_handle))
        require(result['passes'][0] == result['passes'][1], 'Two complete relation pair passes differ')
        result.update(snapshot=result['passes'][0], status=result['passes'][0]['status'], two_pass_equal=True,
            current_relation_observed=result['passes'][0]['native_index_presence_observed'])
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, struct.error, UnicodeError) as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    result['read_budget'] = dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest, limits=LIMITS)
    return result


def _capture(value, action):
    require(type(value) is dict and value['schema'] == SCHEMA and value['action'] == action
        and value['two_pass_equal'] is True and len(value['passes']) == 2
        and value['passes'][0] == value['passes'][1] == value['snapshot'], 'Relation capture is incomplete/inconsistent')
    s = value['snapshot'];require(s['status'] == value['status'] and s['typed_index_allocation_guards_verified'] is True,
        'Relation capture status/allocation evidence differs')
    base=int(s['module_base'],16);ptr(base);count=s['roots']['count']
    require(type(count) is int and count==1380, 'Relation capture country profile differs')
    actor_slot,_=full_handle(int(s['pair']['actor_handle'],16),count,tag=s['pair']['actor_tag'])
    target_slot,_=full_handle(int(s['pair']['target_handle'],16),count,tag=s['pair']['target_tag'])
    require(actor_slot!=target_slot and type(value['current_relation_observed']) is bool,
        'Relation capture pair/state encoding differs')
    obj = s['object'];left, right = s['indexes']['actor'], s['indexes']['target']
    for item,owner,wanted in ((left,s['actor'],target_slot),(right,s['target'],actor_slot)):
        header=bytes.fromhex(item['header_hex']);require(len(header)==24,'Relation capture index header length')
        vt,array,cap,used=struct.unpack('<QQii',header)
        raw=bytes.fromhex(item['entries_hex'])
        require(vt==base+INDEX_VT and 0<=used<=LIMITS['index_entries'] and used<=cap<=MAX_CAPACITY
            and ((cap==0 and array==0) or (cap>0 and 0x10000<=array<array+cap*16<=2**47 and array%8==0))
            and len(raw)==used*16 and digest(raw)==item['records_sha256']
            and item['capacity_signed']==cap and item['count_signed']==used and item['array']==hex(array)
            and item['container']==hex(int(owner['address'],16)+0x14F8+PROFILES[action]['index'])
            and item['allocation_metadata_guarded'] is True, 'Relation capture index allocation evidence differs')
        entries=list(struct.iter_unpack('<i4xQ',raw))
        require(all(0<slot<min(count,32768) and 0x10000<=pointer<2**47 and pointer%8==0 for slot,pointer in entries)
            and len({slot for slot,_ in entries})==used,'Relation capture index entries differ')
        matches=[pointer for slot,pointer in entries if slot==wanted]
        require(item['object_pointer']==(hex(matches[0]) if matches else None)
            and item['selected_member'] is bool(matches)
            and (not matches or sum(pointer==matches[0] for _,pointer in entries)==1),
            'Relation capture selected index differs')
    require(left['object_pointer'] == right['object_pointer'], 'Relation capture indexes disagree')
    if s['status'] == 'pair_absent_observed':
        require(obj is None and left['object_pointer'] is None and value['current_relation_observed'] is False,
            'Absent relation capture contains an object')
    elif s['status'] in ('current_relation_observed','reverse_relation_observed'):
        require(type(obj) is dict and obj['address'] == left['object_pointer'], 'Relation capture object differs from indexes')
        raw = bytes.fromhex(obj['raw_object_hex']);p=PROFILES[action]
        require(len(raw)==p['size'] and struct.unpack_from('<QI',raw)==(int(s['module_base'],16)+p['object_vt'],357)
            and raw[0x28:0x2a]==b'\0\0', 'Relation raw object/lifecycle evidence differs')
        endpoints=struct.unpack_from('<QQ',raw,0x10)
        forward=(int(s['pair']['actor_handle'],16),int(s['pair']['target_handle'],16))
        start=struct.unpack_from('<i',raw,0x20)[0]
        require(endpoints in (forward,forward[::-1]) and obj['first_handle']==hex(endpoints[0])
            and obj['second_handle']==hex(endpoints[1]) and 0<start<=s['now_raw']
            and obj['started_raw_date']==start and obj['removed_byte_28']==obj['insertion_failed_byte_29']==0,
            'Relation raw complete endpoints/date differ')
        expected=p['symmetric'] or endpoints==forward
        require((s['status']=='current_relation_observed') == expected == value['current_relation_observed'],
            'Relation direction/status differs')
    else:raise ValueError('Relation selected state unknown')
    return s


def evaluate_relation_effect(action, before, after, receipt):
    """Assess only a selected absent-to-indexed relation with original receipt."""
    result = dict(schema='EU4DIPLOMACY-RELATION-EFFECT/1', action=action, status='unknown', selected_effect_verified=False,
        AI_acceptance_verified=False, exact_external_request_id_causality_verified=False, exclusive_causality_proven=False,
        world_epoch_proven=False, atomic_snapshot_proven=False, global_membership_verified=False,
        saved_state_verified=False, cold_reload_verified=False, automatic_command_retry=False,
        baseline_prepublication_guard_verified_by_this_pure_function=False)
    try:
        require(action in ACTIONS and before is not None and after is not None, 'Relation baseline/action unavailable')
        identity=validate_identity(before['identity'])
        require(identity==validate_identity(after['identity'])==validate_identity(receipt['identity']), 'Relation session identity differs')
        b,a=_capture(before,action),_capture(after,action)
        require(b['pair']==a['pair'] and b['actor']==a['actor'] and b['target']==a['target'], 'Relation exact pair differs')
        require(b['module_base']==a['module_base'] and all(b['roots'][k]==a['roots'][k]
            for k in ('game','database','array','server','pause')) and b['now_raw']<=a['now_raw'], 'Relation world/date differs')
        command=validate_command(receipt['command'],ACTIONS)
        require(command['action']==action and command['actor']==b['pair']['actor_tag']
            and command['target']==b['pair']['target_tag'] and receipt['state']=='dispatched', 'Relation dispatched command differs')
        require(re.fullmatch(r'[0-9a-f]{64}',receipt['audit_sha256']) is not None, 'Original relation audit digest unavailable')
        sequence=receipt['sequence'];require(type(sequence) is int and 0<sequence<=128, 'Original relation sequence unavailable')
        nr,binding=receipt['native_result'],receipt['binding']
        for row,event in ((nr,'request_result'),(binding,'pair_bound')):
            require(row['event']==event and type(row['sequence']) is int and row['sequence']==sequence and row['no_send'] is False
                and all(type(row[k]) is type(v) and row[k]==v for k,v in identity.items()),
                'Original relation native/binding identity differs')
        require(type(binding['actor_handle']) is int and type(binding['target_handle']) is int
            and binding['actor_handle']==int(b['pair']['actor_handle'],16)
            and binding['target_handle']==int(b['pair']['target_handle'],16), 'Original relation binding differs')
        require(type(nr['status']) is int and nr['status']==4 and nr['reason']=='normal_dispatch_slot_consumed'
            and all(nr[k] is True for k in ('submitted','submit_attempted','submit_returned','submit_value','slot_consumed','ownership_closed'))
            and all(type(nr[k]) is int and nr[k]==0 for k in ('owned_live','quarantined','adapter_fault','submit_exception'))
            and type(nr['transfer_outcome']) is int and nr['transfer_outcome']==1
            and type(nr['adapter_call_attempts']) is int and nr['adapter_call_attempts']==7
            and type(nr['owned_issued']) is int and nr['owned_issued']==3
            and type(nr['known_cleanup_complete']) is bool, 'Original relation dispatch/transport receipt incomplete')
        observed=b['status']=='pair_absent_observed' and a['status']=='current_relation_observed'
        result.update(status='observed' if observed else 'not_observed',selected_effect_verified=observed,
            completion_stage='selected_indexed_relation_observed' if observed else 'unverified',
            request_id=command['request_id'], native_known_cleanup_complete=nr['known_cleanup_complete'],
            changes={'pair_status':{'before':b['status'],'after':a['status']},
                'object_pointer':{'before':b['object']['address'] if b['object'] else None,
                                  'after':a['object']['address'] if a['object'] else None}})
    except (ValueError,KeyError,TypeError,struct.error,UnicodeError) as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc)}
    return result


def verify_manifest():
    raw=read(SOURCE_MANIFEST,65536);manifest=decode(raw)
    require(manifest['schema']=='EU4DIPLOMACY-RELATION-READER-MANIFEST/1' and manifest['game_sha256']==GAME_SHA
        and manifest['native_manifest_sha256']==digest(read(DEFAULT_MANIFEST,1024*1024)), 'Relation manifest/build differs')
    result={}
    for name,expected in manifest['source_pins'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Invalid relation source path')
        data=read(ROOT/name,16*1024*1024);actual={'bytes':len(data),'sha256':digest(data)}
        require(actual==expected,'Relation source/evidence changed: '+name);result[name]=actual
    require({'bridge/relation_effect_reader.py','bridge/diplomacy_effect_observer.py',
        'work/reports/relation-effect-observer-20261015/static.json'}<=set(result),'Relation evidence set incomplete')
    result[SOURCE_MANIFEST.relative_to(ROOT).as_posix()]={'bytes':len(raw),'sha256':digest(raw)}
    return result


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(description='Offline relation reader source checks; no game access')
    ap.add_argument('--check',action='store_true',required=True);ap.parse_args()
    print(json.dumps({'source_pins':len(verify_manifest()),'native_calls':0,'game_process_accessed':False}))
