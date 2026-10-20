"""One bounded, retained-file extraction. Never imports target/project code."""
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/current-mod-field-cached-source-20261016-r1'
SUBJECT = 'work/reports/peace-current-pending-observer-live-after-restart-independent-review-20261016-r2-review2/findings.json'
SUBJECT_PIN = {'bytes': 8290, 'sha256': 'e4473e6cee3abb2a740a97ca8a9159e01c458e8bb22ae01575ac3437fd5f235d'}
FILES = {
    'work/reports/native-action-fields-1375.json': (1144871, 'cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96'),
    'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/static.json': (298074, '25331327e18c4acf16f9cc9c82f3e19a6f6dfaea7f9fe42d4fa311e8d71fcdda'),
    'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/disassembly.txt': (104082, '736ad8e0cbfc9846efe83c790e7f9e4566058a9ec2c84c3a58e15fef5ab2e7fa'),
    'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/trace.py': (4961, '478d3b9a33a6be7a918d07de757c38108248ea8c8d6d11795069f1e5acb44b34'),
}
RVA = 0x233e064
CAP = 4 * 1024 * 1024
MANUAL_RESERVE = 131072  # Includes the previous metadata call's 8290-byte subject read.
SEAL_RESERVE = 650000
read_events = []
physical = 0
peak = 0


class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


def memory_guard():
    global peak
    p = PMC()
    p.cb = ctypes.sizeof(p)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    fn = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    fn.restype = wintypes.BOOL
    if not fn(k.GetCurrentProcess(), ctypes.byref(p), p.cb):
        raise RuntimeError('self memory measurement unavailable')
    peak = max(peak, p.PeakWorkingSetSize)
    if p.WorkingSetSize > 768 * 1024 * 1024 or p.PeakWorkingSetSize > 1024 * 1024 * 1024:
        raise RuntimeError('self memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase, expected=None):
    global physical
    memory_guard()
    fp = ROOT / path
    n = fp.stat().st_size
    if n > CAP or physical + n + MANUAL_RESERVE + SEAL_RESERVE > CAP:
        raise RuntimeError('retained file read budget')
    with fp.open('rb') as stream:
        raw = stream.read(n + 1)
    physical += len(raw)
    actual = pin(raw)
    read_events.append({'path': path, 'phase': phase, **actual})
    if len(raw) != n or (expected is not None and actual != expected):
        raise RuntimeError('source pin differs: ' + path)
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    if len(raw) > 200000:
        raise RuntimeError('local report bound')
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return {'path': str((OUT / name).relative_to(ROOT)).replace('\\', '/'), **pin(raw)}


def ptr(path, key):
    return path + '/' + str(key).replace('~', '~0').replace('/', '~1')


def walk(value, path=''):
    # Iterative stack avoids making recursion depth a hidden read/CPU budget.
    todo = [(path, value)]
    visited = 0
    while todo:
        p, v = todo.pop()
        visited += 1
        if visited > 180000:
            raise RuntimeError('retained JSON node budget')
        yield p, v
        if isinstance(v, dict):
            todo.extend((ptr(p, k), x) for k, x in reversed(list(v.items())))
        elif isinstance(v, list):
            todo.extend((ptr(p, k), x) for k, x in reversed(list(enumerate(v))))


def clipped(value, limit=5000):
    raw = json.dumps(value, ensure_ascii=True, separators=(',', ':'))
    return {'json': value} if len(raw) <= limit else {'bounded_json_prefix': raw[:limit], 'complete': False, 'serialized_chars': len(raw)}


def as_number(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r'(?:0[xX][0-9a-fA-F]+|[0-9]+)', value):
        return int(value, 16 if value.lower().startswith('0x') else 10)
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Exclusive claim precedes all source-body extraction.
    write('claim.json', {'schema': 'EU4-CACHED-FIELD-EXTRACTION-CLAIM/1',
          'scope': 'four_fixed_retained_sources_only', 'sources': FILES,
          'rva': hex(RVA), 'single_extraction': True, 'source_budget': CAP,
          'manual_reserve': MANUAL_RESERVE, 'seal_reserve': SEAL_RESERVE,
          'game_access': False, 'native_calls': 0, 'decoder_calls': 0})
    own_path = str(Path(__file__).relative_to(ROOT)).replace('\\', '/')
    own = read(own_path, 'reviewer_source_before')
    subject = read(SUBJECT, 'subject_before', SUBJECT_PIN)
    s = json.loads(subject)
    authorized = s['next_source_scope_proposal']['fixed_sources']
    # The field shape is deliberately reported before matching, not guessed.
    normalized = {}
    if isinstance(authorized, dict):
        for path, data in authorized.items():
            normalized[path] = {'bytes': data['bytes'], 'sha256': data['sha256']}
    elif isinstance(authorized, list):
        for data in authorized:
            normalized[data['path']] = {'bytes': data['bytes'], 'sha256': data['sha256']}
    else:
        raise RuntimeError('fixed source schema unknown')
    if normalized != {p: {'bytes': n, 'sha256': h} for p, (n, h) in FILES.items()}:
        raise RuntimeError('fixed source scope differs')
    source_raw = {}
    for path, (n, h) in FILES.items():
        source_raw[path] = read(path, 'fixed_source_before', {'bytes': n, 'sha256': h})
    # Only after ALL four exact raw pins pass may any of their contents be parsed.
    docs = {p: json.loads(raw.decode('utf-8-sig')) for p, raw in source_raw.items() if p.endswith('.json')}
    explicit_bases = []
    for p, doc in docs.items():
        for jp, value in walk(doc):
            if isinstance(value, dict):
                for k, v in value.items():
                    if re.fullmatch(r'(?:preferred_)?image_?base|preferred_base|module_base|pe_image_base', k, re.I):
                        number = as_number(v)
                        if number is not None:
                            explicit_bases.append({'source': p, 'pointer': ptr(jp, k), 'key': k, 'value': v, 'number': number})
    base_values = sorted(set(x['number'] for x in explicit_bases))
    # No default preferred base is introduced. Each VA token carries its own metadata source.
    numeric_targets = {RVA} | {base + RVA for base in base_values}
    target_hex = {format(x, 'x') for x in numeric_targets}
    tokens = set(target_hex) | {str(x) for x in numeric_targets}
    def match(value):
        if type(value) is int:
            return value in numeric_targets
        if not isinstance(value, str):
            return False
        low = value.lower()
        return any(re.search(r'(?<![0-9a-f])(?:0x)?' + re.escape(tok) + r'(?![0-9a-f])', low) for tok in tokens)
    json_matches = []
    for p, doc in docs.items():
        parents = {'': doc}
        for jp, value in walk(doc):
            if isinstance(value, (dict, list)):
                parents[jp] = value
            if not isinstance(value, (dict, list)) and match(value):
                parent = jp.rsplit('/', 1)[0]
                # Capture immediate object and nearest enclosing row, bounded by size.
                contexts = []
                ancestor = parent
                for _ in range(3):
                    if ancestor in parents:
                        contexts.append({'pointer': ancestor, **clipped(parents[ancestor])})
                    if not ancestor:
                        break
                    ancestor = ancestor.rsplit('/', 1)[0]
                json_matches.append({'source': p, 'pointer': jp, 'value': value, 'contexts': contexts})
                if len(json_matches) > 48:
                    raise RuntimeError('too many selected field matches')
    text_matches = []
    for p, raw in source_raw.items():
        lines = raw.decode('utf-8-sig').splitlines()
        for idx, line in enumerate(lines):
            # Include exact lowercase RVA substring: a preferred-VA lexical hit is
            # retained as such unless metadata authorizes normalization above.
            lexical = '233e064' in line.lower()
            if lexical or match(line):
                lo, hi = max(0, idx - 4), min(len(lines), idx + 5)
                text_matches.append({'source': p, 'line': idx + 1, 'kind': 'lexical_rva_or_explicit_metadata_address',
                                     'lines': [{'line': i + 1, 'text': lines[i]} for i in range(lo, hi)]})
                if len(text_matches) > 64:
                    raise RuntimeError('too many bounded line matches')
    # AST is source-only: no import/compile/execute of trace.py.
    trace = next(p for p in FILES if p.endswith('/trace.py'))
    tree = ast.parse(source_raw[trace].decode('utf-8-sig'))
    trace_imports = [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    schema = {p: {'kind': type(d).__name__, 'top_level_keys': list(d) if isinstance(d, dict) else None} for p, d in docs.items()}
    evidence = {'schema': 'EU4-CACHED-FIELD-EXTRACTION/1', 'rva': hex(RVA), 'rva_decimal': RVA,
                'fixed_source_schema': type(authorized).__name__, 'source_schema': schema,
                'explicit_base_metadata': explicit_bases, 'authorized_normalized_numeric_targets': sorted(numeric_targets),
                'json_matches': json_matches, 'bounded_text_matches': text_matches,
                'trace_imports_source_only': trace_imports,
                'limits': {'json_match_cap': 48, 'text_match_cap': 64, 'context_ancestors': 3,
                           'context_serialized_chars_each': 5000, 'line_context_radius': 4},
                'absence_scope': 'Only four retained exact source bodies, not EXE or whole repository.',
                'native_game_calls': 0, 'process_reads': 0, 'decoder_calls': 0,
                'source_trace_execution': False, 'authority_granted': False}
    # Pre/post verification is over the same fixed four paths, no dynamic expansion.
    for path, (n, h) in FILES.items():
        read(path, 'fixed_source_after', {'bytes': n, 'sha256': h})
    read(SUBJECT, 'subject_after', SUBJECT_PIN)
    read(own_path, 'reviewer_source_after', pin(own))
    memory_guard()
    outputs = [write('extraction.json', evidence)]
    outputs.append(write('source-manifest.json', {'schema': 'EU4-CACHED-FIELD-SOURCE/1',
        'sealed': True, 'fixed_sources': normalized,
        'subject': {'path': SUBJECT, **SUBJECT_PIN}, 'reviewer_source': {'path': own_path, **pin(own)},
        'raw_pin_before_parse': True, 'fixed_sources_before_after_reads': 8,
        'single_extraction': True, 'no_recursive_closure': True, 'authority_granted': False}))
    outputs.append(write('read-account.json', {'schema': 'EU4-CACHED-FIELD-READ-ACCOUNT/1',
        'source_read_events': read_events, 'charged_read_bytes': physical,
        'fixed_source_each_pass': sum(n for n, _ in FILES.values()),
        'fixed_source_two_pass': 2 * sum(n for n, _ in FILES.values()),
        'manual_reserve': MANUAL_RESERVE,
        'manual_scope': 'Initial 8290-byte subject metadata read and bounded reviewer small-file views; not whole-OS IO.',
        'seal_reserve': SEAL_RESERVE, 'upper_including_manual_and_seal': physical + MANUAL_RESERVE + SEAL_RESERVE,
        'budget': CAP, 'self_peak_working_set': peak, 'target_process_access': False,
        'all_tool_shells_collected_on_return': True}))
    write('extraction-manifest.json', {'schema': 'EU4-CACHED-FIELD-EXTRACTION-MANIFEST/1',
          'sealed': True, 'source_prepost_verified': True, 'outputs': outputs,
          'physical_read_bytes': physical, 'all_authority': False})
    print(json.dumps({'ok': True, 'rva_decimal': RVA, 'bases': explicit_bases,
          'json_match_count': len(json_matches), 'text_match_count': len(text_matches),
          'read_bytes': physical, 'upper_with_reserves': physical + MANUAL_RESERVE + SEAL_RESERVE,
          'peak': peak, 'outputs': outputs}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        failure = {'schema': 'EU4-CACHED-FIELD-EXTRACTION-FAILURE/1', 'error': str(exc),
                   'traceback': traceback.format_exc(), 'read_events': read_events,
                   'charged_read_bytes': physical, 'peak': peak, 'no_automatic_retry': True}
        with (OUT / 'failure.json').open('xb') as f:
            f.write((json.dumps(failure, ensure_ascii=True, indent=2) + '\n').encode('ascii'))
        print(json.dumps({'ok': False, 'error': str(exc), 'charged_read_bytes': physical}))
        sys.exit(1)
