"""Inspect three explicitly named retained JSON directories; never opens the PE."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/gold-helper-retained-body-inventory-20261016-r1'
SOURCES = {
    'work/reports/native-diplomacy-1.37.5.json': 'c64df6e043c9e7a498a25082e0e768902764e4a271ab3579f0eaddb2f1391633',
    'work/reports/native-action-fields-1375.json': 'cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96',
    'work/reports/native-diplomacy-modes-1375.json': '1c0fa12b630a134036c32caf826750ce82608c44fab80108e6cfd2b738d06676',
}
TARGETS = ('0x3383b0', '0x339c10')
LIMIT_FILE = 8 * 1024 * 1024
LIMIT_TOTAL = 24 * 1024 * 1024

def dump(path, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    dump(OUT / 'claim.json', {'scope': 'three retained JSON explicit function directories only',
                            'targets': TARGETS, 'new_PE_decoder_game_tests_requests': 0})
    events = []
    total = 0
    findings = []
    for rel, expected in SOURCES.items():
        path = ROOT / rel
        size = path.stat().st_size
        assert size <= LIMIT_FILE and total + size * 2 <= LIMIT_TOTAL
        raw = path.read_bytes()
        total += len(raw)
        digest = hashlib.sha256(raw).hexdigest()
        events.append({'path': rel, 'phase': 'before', 'bytes': len(raw), 'sha256': digest})
        assert digest == expected
        data = json.loads(raw)
        dirs = {key: data[key] for key in ('functions', 'ranges', 'selected_functions', 'extras') if key in data}
        record = {'path': rel, 'top_level_keys': list(data), 'directories': []}
        for key, directory in dirs.items():
            item = {'key': key, 'type': type(directory).__name__, 'entries': len(directory), 'targets': {}}
            if isinstance(directory, dict):
                for target in TARGETS:
                    matched = [k for k in directory if str(k).lower() == target]
                    item['targets'][target] = {'matching_keys': matched,
                                              'selected_bodies': {k: directory[k] for k in matched}}
            elif isinstance(directory, list):
                for target in TARGETS:
                    matches = []
                    for ordinal, value in enumerate(directory):
                        if not isinstance(value, dict):
                            continue
                        for field in ('rva', 'start', 'entry', 'entry_rva', 'function_rva', 'begin_rva'):
                            if str(value.get(field, '')).lower() == target:
                                matches.append({'ordinal': ordinal, 'field': field, 'record': value})
                    item['targets'][target] = {'matching_records': matches}
            else:
                item['unknown_directory_type'] = True
            record['directories'].append(item)
        findings.append(record)
        after = path.read_bytes()
        total += len(after)
        digest_after = hashlib.sha256(after).hexdigest()
        events.append({'path': rel, 'phase': 'after', 'bytes': len(after), 'sha256': digest_after})
        assert digest_after == expected
    result = {'schema': 'EU4-RETAINED-GOLD-HELPER-BODY-INVENTORY/1', 'sealed': True,
              'passed': True, 'sources': events, 'findings': findings,
              'physical_source_bytes': total, 'file_limit': LIMIT_FILE, 'total_limit': LIMIT_TOTAL,
              'limits': ['Only explicit top-level named directories and exact entry fields/keys inspected.',
                         'No matching key does not prove no body elsewhere or native absence.',
                         'No existing producer, test, CLI, PE, decoder or game executed.'],
              'authority': {'callable': False, 'native_ready': False, 'effect_verified': False, 'retry': False}}
    pin = dump(OUT / 'findings.json', result)
    pin['path'] = 'findings.json'
    script = Path(__file__).read_bytes()
    dump(OUT / 'manifest.json', {'sealed': True, 'findings': pin,
                               'script': {'path': str(Path(__file__)), 'bytes': len(script),
                                          'sha256': hashlib.sha256(script).hexdigest()},
                               'source_pins': events})
    print(json.dumps({'passed': True, 'source_bytes': total, 'findings': pin,
                      'directories': [{ 'path': f['path'], 'dirs': [d['key'] for d in f['directories']] }
                                      for f in findings]}, ensure_ascii=True))

if __name__ == '__main__':
    main()
