"""Offline research index. No process access, native calls, dispatch, or servers."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GAME_SHA256 = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
DATA_MANIFEST_SHA256 = '9f68d95f963fedd64372d30eba94b25643289bd03aa14a3a926d4cbe0a0c0c6f'
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
USER_MIN = 0x10000
USER_END = 0x00007fffffff0000
FALSE_FLAGS = ('callable', 'native_ready', 'sender_authorized',
               'gameplay_effect_verified', 'process_authenticated')


class LookupFailure(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise LookupFailure(reason)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def _json(raw):
    def invalid_constant(_):
        raise LookupFailure('nonfinite_json_number')
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LookupFailure('invalid_json') from error


def _bounded_read(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    require(len(raw) <= MAX_FILE, 'file_limit_exceeded')
    return raw


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _check_pin(raw, pin):
    require(type(pin) is dict and set(pin) == {'bytes', 'sha256'}, 'malformed_pin')
    require(type(pin['bytes']) is int and 0 <= pin['bytes'] <= MAX_FILE, 'malformed_pin_bytes')
    require(type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'malformed_pin_sha')
    require(len(raw) == pin['bytes'] and _hash(raw) == pin['sha256'], 'source_pin_mismatch')


def _source_path(root, relative):
    require(type(relative) is str and '\\' not in relative, 'invalid_evidence_path')
    parts = PurePosixPath(relative).parts
    require(relative == '/'.join(parts) and parts[:2] == ('work', 'reports')
            and all(part not in ('', '.', '..') for part in parts)
            and ':' not in relative and relative.endswith('.json'), 'invalid_evidence_path')
    target = (root / relative).resolve(strict=True)
    require(target.is_relative_to(root.resolve()), 'evidence_path_escape')
    return target


def _pointer(document, pointer):
    require(type(pointer) is str and pointer.startswith('/'), 'invalid_json_pointer')
    value = document
    for part in pointer.split('/')[1:]:
        require(re.search(r'~(?![01])', part) is None, 'invalid_json_pointer_escape')
        part = part.replace('~1', '/').replace('~0', '~')
        if type(value) is list:
            require(re.fullmatch('0|[1-9][0-9]*', part), 'invalid_json_pointer_index')
            value = value[int(part)]
        else:
            require(type(value) is dict, 'json_pointer_not_container')
            value = value[part]
    return value


def parse_rva(value):
    require(type(value) is str and re.fullmatch(r'0x[0-9a-fA-F]{1,8}', value), 'invalid_uint32_rva')
    return int(value, 16)


def conditional_va(base, rva):
    require(type(base) is str and re.fullmatch(r'0x[0-9a-fA-F]{1,16}', base), 'invalid_base')
    number = int(base, 16)
    offset = parse_rva(rva)
    require(USER_MIN <= number < USER_END and number % 0x1000 == 0, 'unsafe_or_unaligned_base')
    va = number + offset
    require(number <= va < USER_END and va < 1 << 64, 'unsafe_conditional_address')
    return {'base': f'0x{number:016x}', 'rva': f'0x{offset:x}', 'va': f'0x{va:016x}',
            'meaning': 'conditional_arithmetic_from_user_supplied_base',
            'module_identity_verified': False, 'process_authenticated': False,
            'module_size_or_mapping_verified': False, 'callable': False}


def _validate_index(index, manifest, documents):
    require(type(index) is dict and index.get('schema') == 'EU4-WAR-PEACE-OFFLINE-INDEX/1', 'index_schema')
    require(index.get('version') == '1.37.5' and index.get('game_sha256') == GAME_SHA256, 'index_target')
    require(index.get('scope') == 'research_endpoint_lookup_only' and index.get('not_a_callable_API') is True, 'index_scope')
    families = index.get('family_aliases')
    require(type(families) is dict and set(families) == {'declare_war', 'peace'}, 'index_families')
    names = {}
    for family, aliases in families.items():
        require(type(aliases) is list and family in aliases, 'family_aliases')
        for alias in aliases:
            require(type(alias) is str and alias and alias == alias.strip(), 'family_alias')
            key = alias.casefold()
            require(key not in names or names[key] == family, 'ambiguous_family_alias')
            names[key] = family
    rows = index.get('entries')
    require(type(rows) is list and 1 <= len(rows) <= 128, 'index_count')
    ids = []
    used_sources = set()
    for row in rows:
        require(type(row) is dict, 'index_row')
        identifier = row.get('id')
        require(type(identifier) is str and re.fullmatch(r'(declare_war|peace|shared)\.[a-z_]+', identifier), 'index_id')
        ids.append(identifier)
        for flag in FALSE_FLAGS:
            require(row.get(flag) is False, 'authority_must_remain_false')
        parse_rva(row.get('rva'))
        require(row.get('kind') in ('function', 'callsite', 'basic_block'), 'index_kind')
        require(row.get('stage') in ('static', 'real_rawbody_postcondition'), 'index_stage')
        if row['stage'] == 'real_rawbody_postcondition':
            require(identifier == 'declare_war.body_destructor' and row['rva'] == '0x500560'
                    and row.get('signature', {}).get('status') == 'raw_probe_only', 'runtime_scope_escalation')
        for key in ('title', 'summary', 'stage_scope'):
            require(type(row.get(key)) is str and row[key], 'missing_description')
        require(type(row.get('unresolved')) is list and row['unresolved']
                and all(type(v) is str and v for v in row['unresolved']), 'missing_unknowns')
        require(type(row.get('actions')) is list and row['actions']
                and set(row['actions']) <= set(families), 'index_actions')
        signature = row.get('signature')
        require(type(signature) is dict and signature.get('complete_prototype') == 'unknown'
                and signature.get('status') in ('partial_static', 'raw_probe_only', 'unknown')
                and type(signature.get('parameters')) is list
                and all(type(v) is str for v in signature['parameters'])
                and type(signature.get('returns')) is str, 'index_signature')
        ownership = row.get('ownership')
        require(type(ownership) is dict and set(ownership) == {'owned', 'borrowed'}, 'index_ownership')
        for values in ownership.values():
            require(type(values) is list and values and all(type(v) is str and v for v in values), 'ownership_scope')
        sites = row.get('call_sites')
        require(type(sites) is list, 'index_callsites')
        for site in sites:
            require(type(site) is dict and type(site.get('relationship')) is str, 'index_callsite')
            parse_rva(site.get('rva'))
        aliases = row.get('aliases')
        require(type(aliases) is list, 'index_aliases')
        for alias in [identifier] + aliases:
            require(type(alias) is str and alias and alias == alias.strip(), 'index_alias')
            key = alias.casefold()
            require(key not in names or names[key] == identifier, 'ambiguous_endpoint_alias')
            names[key] = identifier
        refs = row.get('evidence')
        require(type(refs) is list and refs, 'missing_evidence')
        for ref in refs:
            require(type(ref) is dict and set(ref) == {'path', 'json_pointer', 'bytes', 'sha256'}, 'evidence_ref')
            path = ref['path']
            require(path in manifest['sources'], 'evidence_not_pinned')
            require({k: ref[k] for k in ('bytes', 'sha256')} == manifest['sources'][path], 'evidence_pin_disagrees')
            _pointer(documents[path], ref['json_pointer'])
            used_sources.add(path)
    require(ids == sorted(ids) and len(ids) == len(set(ids)), 'index_id_order')
    require(used_sources == set(manifest['sources']), 'unused_or_missing_source')


class SourceGraph:
    """Internal fixture seam; the public CLI always supplies the fixed graph."""
    def __init__(self, root=ROOT, directory=HERE, expected_manifest=DATA_MANIFEST_SHA256):
        self.root = Path(root)
        self.directory = Path(directory)
        self.expected_manifest = expected_manifest

    def verify(self, parse=False):
        raw = _bounded_read(self.directory / 'data-manifest.json')
        require(_hash(raw) == self.expected_manifest, 'data_manifest_pin_mismatch')
        manifest = _json(raw)
        require(type(manifest) is dict and manifest.get('schema') == 'EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1', 'manifest_schema')
        require(manifest.get('version') == '1.37.5' and manifest.get('game_sha256') == GAME_SHA256
                and manifest.get('scope') == 'offline_selected_evidence_only', 'manifest_target')
        sources = manifest.get('sources')
        require(type(sources) is dict and 1 <= len(sources) <= 64, 'manifest_sources')
        index_raw = _bounded_read(self.directory / 'index.json')
        _check_pin(index_raw, manifest['index'])
        total = len(raw) + len(index_raw)
        documents = {}
        for path, pin in sorted(sources.items()):
            content = _bounded_read(_source_path(self.root, path))
            total += len(content)
            require(total <= MAX_TOTAL, 'source_graph_limit_exceeded')
            _check_pin(content, pin)
            if parse:
                documents[path] = _json(content)
        if parse:
            index = _json(index_raw)
            _validate_index(index, manifest, documents)
            return index, {'manifest_sha256': self.expected_manifest,
                           'index_sha256': manifest['index']['sha256'],
                           'selected_source_count': len(sources), 'selected_bytes_per_pass': total}
        return None


def _family(index, value):
    if value is None:
        return None
    require(type(value) is str, 'invalid_family')
    for family, aliases in index['family_aliases'].items():
        if value.strip().casefold() in [alias.casefold() for alias in aliases]:
            return family
    raise LookupFailure('unknown_family')


def _brief(row):
    keys = ('id', 'actions', 'title', 'rva', 'kind', 'stage', 'stage_scope', 'summary', 'evidence') + FALSE_FLAGS
    return {key: copy.deepcopy(row[key]) for key in keys}


def _envelope(operation, status='ok'):
    return {'schema': 'EU4-WAR-PEACE-LOOKUP-RESULT/1', 'operation': operation,
            'status': status, 'version': '1.37.5', 'game_sha256': GAME_SHA256,
            'identity_scope': 'retained_evidence_target_only_not_current_process_authentication',
            'accounting_scope': 'this_offline_query_only',
            'requests_published': 0, 'native_calls': 0,
            **{key: False for key in FALSE_FLAGS}}


def query(graph, operation, selector=None, family=None, base=None, limit=20):
    """Return only after both source-pin passes. Errors contain no catalog rows/VA."""
    try:
        require(operation in ('catalog', 'search', 'lookup', 'check'), 'unknown_operation')
        index, provenance = graph.verify(parse=True)
        selected_family = _family(index, family)
        rows = [row for row in index['entries'] if selected_family is None or selected_family in row['actions']]
        result = _envelope(operation)
        result['provenance'] = provenance
        if operation == 'check':
            require(selector is None and base is None and family is None, 'unexpected_check_argument')
            result.update(entry_count=len(rows), stage_counts={stage: sum(row['stage'] == stage for row in rows)
                          for stage in ('static', 'real_rawbody_postcondition')})
        elif operation == 'catalog':
            require(selector is None and base is None, 'unexpected_catalog_argument')
            result.update(count=len(rows), entries=[_brief(row) for row in rows])
        else:
            require(type(selector) is str and 0 < len(selector.strip()) <= 256, 'invalid_selector')
            key = selector.strip().casefold()
            if operation == 'search':
                require(base is None and type(limit) is int and 1 <= limit <= 100, 'invalid_search_options')
                ranked = []
                for row in rows:
                    labels = [row['id'], *row['aliases'], row['rva'], row['title']]
                    labels = [label.casefold() for label in labels]
                    haystack = ' '.join(labels + [row['summary'], *row['signature']['parameters']]).casefold()
                    if key in haystack:
                        score = 0 if key in labels else 1 if any(label.startswith(key) for label in labels) else 2
                        ranked.append((score, row['id'], row))
                ranked.sort(key=lambda item: (item[0], item[1]))
                result.update(total_matches=len(ranked), entries=[_brief(row) for _, _, row in ranked[:limit]])
                result['count'] = len(result['entries'])
            else:
                if key.startswith('0x'):
                    rva = parse_rva(key)
                    matches = [row for row in rows if parse_rva(row['rva']) == rva]
                else:
                    family_match = next((f for f, aliases in index['family_aliases'].items()
                                         if key in [alias.casefold() for alias in aliases]), None)
                    matches = [row for row in rows if (family_match in row['actions'] if family_match else
                               key in [label.casefold() for label in [row['id'], *row['aliases']]])]
                require(matches, 'unknown_endpoint')
                entries = copy.deepcopy(matches)
                if base is not None:
                    for row in entries:
                        row['conditional_address'] = conditional_va(base, row['rva'])
                result.update(count=len(entries), entries=entries)
        graph.verify(parse=False)
        result['provenance']['source_guard_before_and_after'] = True
        return result, 0
    except (LookupFailure, OSError, KeyError, IndexError, TypeError, OverflowError, ValueError):
        error = sys.exception()
        result = _envelope(operation if type(operation) is str else 'unknown', 'unknown')
        result.update(reason=str(error) if isinstance(error, LookupFailure) else 'invalid_or_unavailable_evidence',
                      entries=[], count=0)
        return result, 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LookupFailure('invalid_cli_arguments: ' + message)


def main(argv=None):
    parser = _Parser(description='EU4 1.37.5 offline research index; no callable API or process access. '
                                 'Exit 0 = successful local query/check, never native readiness; 2 = unknown/refused.')
    commands = parser.add_subparsers(dest='operation', required=True)
    catalog = commands.add_parser('catalog', help='list retained evidence endpoints')
    catalog.add_argument('--family')
    search = commands.add_parser('search', help='deterministic substring search')
    search.add_argument('selector')
    search.add_argument('--family')
    search.add_argument('--limit', type=int, default=20)
    lookup = commands.add_parser('lookup', help='exact id, alias, family, or indexed hexadecimal RVA')
    lookup.add_argument('selector')
    lookup.add_argument('--family')
    lookup.add_argument('--base', help='user supplied page-aligned base; conditional arithmetic only')
    commands.add_parser('check', help='verify fixed data manifest, selected sources, and index semantics')
    try:
        args = vars(parser.parse_args(argv))
        result, code = query(SourceGraph(), **args)
    except LookupFailure as error:
        result = _envelope('unknown', 'unknown')
        result.update(reason=str(error), entries=[], count=0)
        code = 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
