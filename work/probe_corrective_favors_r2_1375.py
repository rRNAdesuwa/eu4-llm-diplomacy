"""Bounded two-pass RPM for the next favor/march tests, without game calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import GAME_SHA, TagCommandBackend, WindowsRuntime
from work import inspect_tag31_corrective_pairs as prior
from work.probe_current_diplomacy_1375 import sample as common_sample
from work.discover_diplomacy import check_memory_budget
from work.probe_pair_effects_1375 import pointer

PAIRS = tuple((f'trade_favors_for_{kind}', 'FRA', 'SCO')
              for kind in ('gold', 'men', 'sailors', 'war_prep', 'heir')) + (
                  ('revoke_march', 'FRA', 'ORL'),)
FIELDS = {'treasury_milli': 0xbb0, 'manpower_milli': 0xdb8,
          'sailors_milli': 0xdc0, 'war_prep_date': 0x2728,
          'country_raw_e00': 0xe00}

def sample(reader, base):
    # Configure only this interpreter's imported helper. No source is edited.
    old_pairs = prior.PAIRS
    try:
        prior.PAIRS = PAIRS
        value = common_sample(reader, base)
    finally:
        prior.PAIRS = old_pairs
    resources = {}
    for tag in ('FRA', 'SCO'):
        address = int(value['countries'][tag]['address'], 16)
        resource = {name: reader.integer(address + offset) for name, offset in FIELDS.items()}
        resource['war_prep_actor'] = hex(reader.qword(address + 0x272c))
        heir = reader.qword(address + 0x1298)
        resource['heir_pointer'] = hex(heir)
        resource['heir_vtable_rva'] = hex(reader.qword(pointer(heir))-base) if heir else None
        resources[tag] = resource
    value['selected_resources'] = resources
    prior.require(prior.roots(reader, base) == value['roots'], 'Roots changed after resource sample')
    return value

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--creation', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-tag-host', action='store_true')
    args = parser.parse_args()
    prior.require(not args.output.exists(), 'Exclusive report exists')
    report = dict(schema='EU4TAG-FAVOR-MARCH-RPM/1', game_sha256=GAME_SHA,
        pid=args.pid, creation=args.creation, captured_utc=datetime.now(timezone.utc).isoformat(),
        native_calls=0, memory_written=False, requests_published=0,
        engine_predicates_called=False, status='incomplete', two_pass_equal=False,
        automatic_retry=False, complete_legality_proven=False, passes=[])
    reader = held = None
    try:
        backend = TagCommandBackend()
        runtime = WindowsRuntime()
        held = runtime.readonly.Held(dict(pid=args.pid, creation=args.creation, session='1'*32,
            manifest_sha256=backend.manifest_sha, dll_sha256=backend.manifest['dll']['sha256']))
        held.identity_check()
        canonical = held.injector._canonical
        modules = held.modules()
        matches = [base for base, path in modules if canonical(path) == canonical(held.injector.GAME)]
        prior.require(len(matches) == 1, 'Exact game module unavailable')
        research = [str(path) for _, path in modules if Path(path).name.lower().startswith(
            ('eu4_bridge_', 'eu4_pair_', 'eu4_spy_', 'eu4_tag_command_', 'tag_diplomacy'))]
        expected = backend.build / backend.manifest['DLL']
        prior.require(not research or (args.allow_tag_host and len(research) == 1
            and canonical(research[0]) == canonical(expected)), 'Unexpected research module')
        base = pointer(matches[0])
        reader = prior.Reader(held)
        disk = runtime.readonly.disk_identity(held.injector.GAME)
        prior.require(runtime.readonly.pe_header(reader.read(base, 8192)) == disk, 'Loaded PE differs')
        report.update(module_base=hex(base), loaded_main_pe=disk, research_modules=research)
        for _ in range(2):
            report['passes'].append(sample(reader, base))
            held.identity_check()
        prior.require(report['passes'][0] == report['passes'][1], 'Two samples differ')
        report.update(status='sampled_equal', two_pass_equal=True)
    except Exception as exc:
        report.update(status='failed_no_retry', failure=dict(type=type(exc).__name__, message=str(exc)))
    finally:
        if reader:
            report['rpm_budget'] = dict(calls=reader.calls, bytes=reader.bytes_read,
                largest_read=reader.largest_read, max_calls=prior.MAX_CALLS, max_bytes=prior.MAX_BYTES)
        if held:
            held.close()
    names = ['work/probe_corrective_favors_r2_1375.py', 'work/inspect_tag31_corrective_pairs.py',
        'work/probe_current_diplomacy_1375.py', 'work/probe_pair_effects_1375.py',
        'work/observe_pair29_favors_1375.py', 'work/reports/native-pair29-favor-effects-1375.json']
    report['source_pins'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    report['peak_committed_bytes'] = check_memory_budget()
    report['limitations'] = ['Two equal passes are not atomic.', 'A null heir pointer closes only that local branch; full legality is not claimed.',
        'Resource field layout reuses prior pinned native effect/observation evidence.',
        'No native getter, predicate, constructor, TLS initializer or effect was called.']
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    brief = {k: report[k] for k in ('status', 'two_pass_equal', 'rpm_budget', 'peak_committed_bytes')}
    if report['two_pass_equal']:
        value = report['passes'][0]
        brief.update(date=value['roots']['date'], resources=value['selected_resources'],
            war=value['country_war_raw_289b'], pairs=[dict(action=p['action'],
                cooldown_allows=p['cooldown_only_allows'], favors=p['target_to_actor']['favors_raw_milli'],
                dependency=p['dependency']['object']) for p in value['pairs']],
            envoys={tag: {k: d['native_id_exclusion'][k] for k in ('N', 'R', 'R_less_than_N')}
                    for tag, d in value['diplomats'].items()})
    else:
        brief['failure'] = report['failure']
    print(json.dumps(brief))
    return 0 if report['two_pass_equal'] else 2

if __name__ == '__main__':
    raise SystemExit(main())
