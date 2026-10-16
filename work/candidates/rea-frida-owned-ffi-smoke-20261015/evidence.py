"""Strict pure-byte parser for one owned-fixture REA observation. No OS calls."""
import hashlib
import json
import re

EVIDENCE_KEYS = {'evidence_id', 'subject', 'provider', 'analysis_profile', 'predicate_type',
    'operation', 'parameters', 'raw_result', 'normalized_result', 'confidence', 'authority',
    'environment', 'limitations', 'relationship_coverage', 'locations', 'evidence_links'}
RESULT_KEYS = {'session_id', 'device_id', 'state', 'target', 'pid', 'mode', 'scripts',
    'messages', 'messages_truncated', 'source_kind', 'source_path', 'source_sha256', 'cleanup_error'}
LIMITATIONS = ['Artifact identity is unavailable for this observation.',
    'The target operating system and architecture were not reported by this observation.']
UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def strict_json(raw, maximum=65536, *, ascii_strings=True):
    require(type(ascii_strings) is bool, 'json_string_profile')
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'json_byte_bound')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite_json')
    try:
        # Explicit UTF-8, so UTF-16/BOM and invalid byte sequences cannot pass.
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('json_encoding_or_nesting') from exc
    todo, count = [(result, 0)], 0
    while todo:
        value, depth = todo.pop()
        count += 1
        require(count <= 4096 and depth <= 24, 'json_structure_bound')
        if type(value) is dict:
            todo.extend((item, depth+1) for pair in value.items() for item in pair)
        elif type(value) is list:
            todo.extend((item, depth+1) for item in value)
        else:
            require(value is None or type(value) in (str, int, bool), 'json_scalar_type')
            if type(value) is int:
                require(abs(value) <= (1 << 53)-1, 'json_safe_integer')
            if type(value) is str:
                if ascii_strings:
                    require(value.isascii(), 'fixed_profile_ascii_required')
                else:
                    # Source package strings may contain normal Unicode.
                    # Reject escaped unpaired surrogates as invalid UTF-8 text.
                    try:
                        value.encode('utf-8')
                    except UnicodeError as exc:
                        raise ValueError('source_string_not_utf8') from exc
    return result


def semantic_id(evidence):
    # This fixed profile requires subject/relationship_coverage null. REA's
    # semanticProjection omits the latter instead of hashing the raw object.
    projection = {key: value for key, value in evidence.items()
                  if key not in ('evidence_id', 'relationship_coverage')}
    return 'ev_'+hashlib.sha256(json.dumps(projection, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def extract(raw, *, pid, nonce, script_path, script_sha256, process_name='python.exe'):
    require(type(pid) is int and 0 < pid <= 0xffffffff, 'expected_pid')
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce), 'expected_nonce')
    require(type(script_path) is str and script_path.isascii() and script_path, 'expected_script_path')
    require(type(script_sha256) is str and re.fullmatch('[0-9a-f]{64}', script_sha256), 'expected_source_sha')
    require(process_name == 'python.exe', 'fixed_process_name')
    document = strict_json(raw)
    require(type(document) is dict and set(document) == {'ok', 'data', 'meta'}
            and document['ok'] is True, 'cli_success_envelope')
    meta = document['meta']
    require(type(meta) is dict and set(meta) == {'command', 'duration'}
            and meta['command'] == 'instrument-with-frida'
            and type(meta['duration']) is str
            and re.fullmatch('(0|[1-9][0-9]{0,15})ms', meta['duration']),
            'cli_meta')
    data = document['data']
    require(type(data) is dict and set(data) == {'evidence', 'cleanup_error'}
            and data['cleanup_error'] is None, 'outer_cleanup')
    evidence = data['evidence']
    require(type(evidence) is dict and set(evidence) == EVIDENCE_KEYS, 'evidence_keys')
    require(evidence['provider'] == {'id': 'frida', 'name': 'Frida', 'version': None}
            and evidence['operation'] == 'instrument_with_frida'
            and evidence['predicate_type'] == 'rea.frida.instrumentation-observation'
            and evidence['authority'] == 'external-service' and evidence['confidence'] == 'observed'
            and all(evidence[key] is None for key in
                    ('subject', 'analysis_profile', 'raw_result', 'environment', 'relationship_coverage'))
            and evidence['locations'] == [] and evidence['evidence_links'] == []
            and evidence['limitations'] == LIMITATIONS, 'evidence_profile')
    result = evidence['normalized_result']
    require(type(result) is dict and set(result) == RESULT_KEYS, 'normalized_keys')
    session = result['session_id']
    require(type(session) is str and re.fullmatch(UUID, session), 'session_uuid')
    parameters = evidence['parameters']
    require(type(parameters) is dict and set(parameters) == {'session_id', 'device_id', 'mode', 'pid'}
            and parameters == dict(session_id=session, device_id='local', mode='attach', pid=pid)
            and type(parameters['pid']) is int and type(result['pid']) is int
            and result['pid'] == pid and result['mode'] == 'attach' and result['device_id'] == 'local'
            and result['state'] == 'running'
            and result['target'] == process_name+' (pid '+str(pid)+')', 'session_target_binding')
    require(result['source_kind'] == 'file' and result['source_path'] == script_path
            and result['source_sha256'] == script_sha256 and result['cleanup_error'] is None
            and result['messages_truncated'] is False, 'source_cleanup_or_truncation')
    scripts, messages = result['scripts'], result['messages']
    require(type(scripts) is list and len(scripts) == 1 and type(scripts[0]) is dict
            and set(scripts[0]) == {'script_id', 'name'}, 'one_script')
    script_id = scripts[0]['script_id']
    require(type(script_id) is str and re.fullmatch(UUID, script_id)
            and scripts[0]['name'] == 'rea-'+script_id, 'script_identity')
    require(type(messages) is list and len(messages) == 1 and type(messages[0]) is dict
            and set(messages[0]) == {'script_id', 'type', 'payload'}
            and messages[0]['script_id'] == script_id and messages[0]['type'] == 'send', 'one_plain_send')
    expected = dict(schema='REA-OWNED-FFI-OBSERVATION/1', pid=pid, platform='windows',
                    arch='x64', pointer_size=8, nonce=nonce,
                    lstrlenA=3, GetCurrentProcessId=pid)
    payload = messages[0]['payload']
    require(type(payload) is dict and set(payload) == set(expected) and payload == expected
            and all(type(payload[key]) is int for key in
                    ('pid', 'pointer_size', 'lstrlenA', 'GetCurrentProcessId')),
            'payload_ffi_metadata_nonce')
    require(len(json.dumps(payload, separators=(',', ':')).encode('ascii')) <= 256, 'payload_bound')
    require(evidence['evidence_id'] == semantic_id(evidence), 'semantic_evidence_id')
    return dict(evidence_id=evidence['evidence_id'], session_id=session,
                script_id=script_id, payload=payload)
