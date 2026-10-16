"""Isolated TenFamiliesDraft/2 shape validation; no live binder or backend."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
CONTRACT = 'TenFamiliesDraft/2'
CONTRACT_SHA = 'd89cd608b27116dce88ecac718dc024ebe26ffe2c50c143462ca47ae8a3df2ac'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('Non-finite JSON number')


def _data():
    with (HERE / 'contract.json').open('rb') as stream:
        raw = stream.read(128 * 1024 + 1)
    require(len(raw) <= 128 * 1024 and hashlib.sha256(raw).hexdigest() == CONTRACT_SHA,
            'Fixed isolated contract changed')
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)


def actions():
    return sorted(_data()['actions'])


def describe(action_id):
    require(type(action_id) is str and 1 <= len(action_id) <= 64, 'Exact action ID')
    data = _data()
    require(action_id in data['actions'], 'Unknown action ID')
    return data['actions'][action_id]


def validate(action_id, parameters):
    row = describe(action_id)
    schema = row['parameters']
    require(type(parameters) is dict and len(parameters) <= 4, 'Exact bounded parameter object')
    require(all(type(key) is str for key in parameters), 'Exact string parameter keys')
    require(set(parameters) == set(schema['required']), 'Exact explicit parameters required')
    clean = {}
    for name, rules in schema['properties'].items():
        value = parameters[name]
        if rules['type'] == 'string':
            require(type(value) is str and len(value) == 3 and
                    re.fullmatch('[A-Z0-9]{3}', value) is not None,
                    'Exact three-character ASCII country TAG')
        else:
            require(type(value) is int and rules['minimum'] <= value <= rules['maximum'],
                    'Exact bounded integer')
        clean[name] = value
    require(clean['actor'] != clean['target'], 'Distinct actor/target required')
    if action_id == 'enforce_peace':
        require(clean['opposing_country'] not in (clean['actor'], clean['target']),
                'Restricted opposing-country identity')
    elif action_id == 'threaten_war':
        require(clean['taker_country'] == clean['actor'], 'Only explicit taker=actor has normal caller evidence')
    elif action_id == 'reduce_relations_favor':
        require(clean['third_country'] not in (clean['actor'], clean['target']), 'Distinct third-country syntax')
    return {'contract': CONTRACT, 'action_id': action_id, 'parameters': clean,
            'parameters_valid': True, 'parameter_binding_closed': True,
            'parameter_binding_scope': 'restricted_static_parameter_shape_and_source_only',
            'runtime_binding_verified': False, 'live_identity_resolved': False,
            'native_legality_verified': False, 'execution_supported': False,
            'production_ready': False}


def request(payload):
    require(type(payload) is dict and len(payload) == 4, 'Exact draft request object')
    require(all(type(key) is str for key in payload), 'Exact string request keys')
    require(set(payload) == {'contract', 'action_id', 'parameters', 'request_id'}, 'Exact draft request keys')
    require(type(payload['contract']) is str and payload['contract'] == CONTRACT,
            'Explicit isolated draft version required')
    ident = payload['request_id']
    require(type(ident) is str and 1 <= len(ident) <= 96 and
            re.fullmatch('[A-Za-z0-9_.:-]+', ident) is not None, 'Bounded ASCII request ID')
    result = validate(payload['action_id'], payload['parameters'])
    result.update(request_id=ident, status='unsupported', draft_only=True,
                  reason='Static parameter sources are described; no authenticated live binder or native adapter/backend exists.',
                  request_id_status='not_reserved', request_written=False,
                  queued=False, submitted=False, native_called=False,
                  execution_verified=False, runtime_verified=False,
                  effect_verified=False, request_causality_verified=False)
    return result


def request_json(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 4096, 'Bounded exact JSON bytes required')
    try:
        payload = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid bounded UTF-8 JSON') from exc
    return request(payload)
