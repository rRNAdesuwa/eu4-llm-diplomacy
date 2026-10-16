"""Non-author finite cached-address search; never execute a subject or decoder."""
from pathlib import Path, PurePosixPath
import ctypes
import hashlib
import json
import re
import traceback

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/current-mod-field-cached-source-20261016-r1/'
OUT = ROOT / 'work/reports/current-mod-field-cached-source-independent-20261016-r1'
LIMIT = 8 * 1024 * 1024
MANUAL = 512 * 1024
SEAL = 512 * 1024
reads = []
cache = {}
pins = {}
peak = 0

class PMC(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in ('pw', 'w', 'pp', 'p', 'pn', 'n', 'pf', 'ppf', 'private')]

k = ctypes.WinDLL('kernel32', use_last_error=True)
k.GetCurrentProcess.restype = ctypes.c_void_p
ps = ctypes.WinDLL('psapi', use_last_error=True)

def memory():
    global peak
    x = PMC(); x.cb = ctypes.sizeof(x)
    assert ps.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()), ctypes.byref(x), x.cb)
    peak = max(peak, x.pw, x.ppf, x.private)
    assert peak < 1024**3 and peak <= 768 * 1024**2

def pin(b):
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

def get(rel, expected, phase='before'):
    q = PurePosixPath(rel)
    assert not q.is_absolute() and '..' not in q.parts and ':' not in rel and '\\' not in rel
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and p.suffix.lower() not in ('.exe', '.dll', '.pyd')
    memory()
    n = p.stat().st_size
    assert n <= 4 * 1024**2
    assert sum(x['bytes'] for x in reads) + n + MANUAL + SEAL <= LIMIT
    b = p.read_bytes()
    actual = pin(b)
    reads.append({'path': rel, 'phase': phase, **actual})
    assert actual == expected, rel
    return b

def ingest(rel, expected):
    if rel in cache:
        assert pins[rel] == expected
        return
    cache[rel] = get(rel, expected)
    pins[rel] = expected

def doc(rel):
    return json.loads(cache[rel])

def write(name, value):
    b = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    assert len(b) < 4 * 1024**2
    with (OUT / name).open('xb') as f:
        f.write(b)
    return pin(b)

def main():
    ingest(BASE+'manifest.json', {'bytes':4715,'sha256':'9004f4db1e24f286c2c7f65856c13f60091529ca5b77a9bcbd2705045e5d620c'})
    m = doc(BASE+'manifest.json')
    assert m['sealed'] and m['passed'] and m['source_prepost_verified']
    for rel, expected in m['inputs'].items():
        ingest(rel, expected)
    for value in m['outputs']:
        ingest(value['path'], {k:value[k] for k in ('bytes','sha256')})
    ingest(BASE+'verification.json', {'bytes':5301,'sha256':'f3c66956b88ca83a1e7d7ca7633010a573c85bb99ed9d25f4d3614e86a7f9036'})
    source = doc(BASE+'source-manifest.json')
    assert source['sealed'] and source['single_extraction'] and source['no_recursive_closure']
    sources = source['fixed_sources']
    assert len(sources) == 4 and sum(x['bytes'] for x in sources.values()) == 1551988
    assert sources == m['fixed_source_pins_witnessed_by_extractor']
    for value in [source['reviewer_source'], source['subject']]:
        ingest(value['path'], {k:value[k] for k in ('bytes','sha256')})
    for rel, expected in sources.items():
        ingest(rel, expected)
    f = doc(BASE+'findings.json')
    e = doc(BASE+'extraction.json')
    assert f['sealed'] and f['passed'] and f['blocking_findings'] == []
    assert all(v is False for v in f['authority'].values())
    assert e['json_matches'] == [] and e['bounded_text_matches'] == []
    assert e['source_trace_execution'] is False and e['authority_granted'] is False
    rva = 0x233e064
    static_rel = 'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/static.json'
    preferred = int(doc(static_rel)['image_base'], 16)
    assert preferred == 0x140000000
    target = preferred + rva
    assert target == 0x14233e064
    assert e['authorized_normalized_numeric_targets'] == [rva, target]
    assert e['explicit_base_metadata'] == [{'source':static_rel,'pointer':'/image_base','key':'image_base','value':'0x140000000','number':preferred}]
    # A deliberately finite independent text search also includes JSON keys.
    # This cannot find RIP displacements, aliases or unnamed native consumers.
    patterns = {
        'RVA_hex': re.compile(r'(?<![0-9a-z_])(?:0x)?0*233e064(?![0-9a-z_])', re.I),
        'preferred_VA_hex': re.compile(r'(?<![0-9a-z_])(?:0x)?0*14233e064(?![0-9a-z_])', re.I),
        'RVA_decimal': re.compile(r'(?<![0-9])0*36954212(?![0-9])'),
        'preferred_VA_decimal': re.compile(r'(?<![0-9])0*5405663332(?![0-9])'),
    }
    replay = []
    for rel in sources:
        text = cache[rel].decode('utf-8')
        counts = {name: sum(1 for _ in pattern.finditer(text)) for name, pattern in patterns.items()}
        assert not any(counts.values()), (rel, counts)
        replay.append({'path':rel,'pin':pins[rel],'finite_text_pattern_counts':counts,'JSON_keys_included':rel.endswith('.json')})
    for rel, expected in pins.items():
        assert get(rel, expected, 'after') == cache[rel]
    self_bytes = Path(__file__).read_bytes()
    assert len(self_bytes) <= 65536
    reads.append({'path':Path(__file__).relative_to(ROOT).as_posix(),'phase':'own_source','bytes':len(self_bytes),'sha256':hashlib.sha256(self_bytes).hexdigest()})
    memory()
    total = sum(x['bytes'] for x in reads) + MANUAL + SEAL
    assert total < LIMIT
    rp = write('finite-search-replay.json', {'passed':True,'rva':hex(rva),'preferred_base':hex(preferred),'preferred_VA':hex(target),'sources':replay,'new_native_bytes':0})
    finding = {
        'schema':'ROOT-CACHED-FIELD-INDEPENDENT-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
        'subject_manifest':{'path':BASE+'manifest.json',**pins[BASE+'manifest.json']},
        'subject_findings':{'path':BASE+'findings.json',**pins[BASE+'findings.json']},
        'subject_extraction':{'path':BASE+'extraction.json',**pins[BASE+'extraction.json']},
        'source_count':4,'flat_pin_count':len(pins),'source_before_after_equal':True,
        'reviewer_role':'Root non-author finite retained-file search. War authored this extraction. Prior root runtime capture is directly pinned provenance, not semantic evidence for this field.',
        'conclusion':'No explicit RVA or metadata-supported preferred-VA encodings occur in these four fixed source texts; native field meaning remains unknown.',
        'checks':{'all_selected_flat_pins_exact':True,'preferred_base_from_static_image_base':True,'normalized_numeric_targets_correct':True,'independent_finite_text_search_including_JSON_keys_zero':True,'original_launch_failure_and_continuation_pins_preserved':True,'source_before_after_equal':True},
        'evidence_limits':['Zero finite text matches is not absence of native references, RIP-relative displacements, aliases or indirect use in the PE.','No raw native writer/consumer or enum meaning was established; the label Mod does not identify installed mods or multiplayer.','Claimed first-extraction/launcher chronology, collection and historical memory are producer witnesses.','This review does not approve a new policy, runtime query, general Mod compatibility, original effect or reader adoption.','Before/after file equality does not establish atomicity or exclude ABA.'],
        'author_upper_witness':m['whole_stage_upper'],
        'review_resources':{'completed_explicit_bytes':sum(x['bytes'] for x in reads),'manual_allowance':MANUAL,'seal_reserve':SEAL,'upper_bytes':total,'limit_bytes':LIMIT,'peak_bytes':peak,'hard_Job_claimed':False,'ordinary_file_limit':4194304},
        'authority':{'native_ready':False,'callable':False,'field_meaning_verified':False,'runtime_status_authorized':False,'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False},
        'operations':{'author_programs':0,'old_trace_execution':0,'PE_or_decoder':0,'game_queries':0,'native_calls':0,'child_shells':0},
    }
    fp = write('findings.json', finding)
    mp = write('manifest.json', {'schema':'ROOT-CACHED-FIELD-REVIEW-MANIFEST/1','sealed':True,'passed':True,'source_pins':pins,'local_pins':{'finite-search-replay.json':rp,'findings.json':fp,'reviewer_source':pin(self_bytes)},'read_journal':reads,'scope':'26 selected flat files only, no recursive or new native scope'})
    print(json.dumps({'passed':True,'findings':fp,'manifest':mp,'flat_files':len(pins),'source_upper':total},ensure_ascii=True))

if __name__ == '__main__':
    OUT.mkdir(exist_ok=False)
    try:
        main()
    except BaseException as exc:
        write('failure.json', {'error':str(exc),'type':type(exc).__name__,'traceback':traceback.format_exc(),'reads':reads})
        raise
