"""Two-pass, bounded current prerequisites for four clean-rejection candidates."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import GAME_SHA, TagCommandBackend, WindowsRuntime
from work import inspect_tag31_corrective_pairs as prior
from work.discover_diplomacy import check_memory_budget
from work.probe_pair_effects_1375 import pointer


def envoy_exclusion(reader, country, diplomats):
    actor = int(country['address'], 16)
    container = pointer(reader.qword(actor + 0x1498))
    array = reader.qword(container + 0x28)
    count = reader.integer(container + 0x34)
    prior.require(0 <= count <= 1024, 'Signed envoy exclusion count outside sampling bound')
    raw = reader.read(pointer(array), count * 0x28) if count else b''
    ids = [struct.unpack_from('<I', raw, i * 0x28 + 0x10)[0] for i in range(count)]
    prior.require(reader.qword(actor + 0x1498) == container
                  and reader.qword(container + 0x28) == array
                  and reader.integer(container + 0x34) == count,
                  'Envoy exclusion header changed within sample')
    candidates = [dict(index=e['index'], envoy_id=e['envoy_id'],
                       matched=e['envoy_id'] in ids,
                       first_match_index=ids.index(e['envoy_id']) if e['envoy_id'] in ids else None)
                  for e in diplomats['entries'] if e['state'] == 0]
    n, r = len(candidates), sum(e['matched'] for e in candidates)
    return dict(container=hex(container), array=hex(array), count=count, ordered_ids=ids,
                records_sha256=hashlib.sha256(raw).hexdigest(), candidates=candidates,
                N=n, R=r, unmatched=n-r, R_less_than_N=r<n,
                duplicate_container_ids=len(ids)-len(set(ids)),
                duplicate_candidate_ids=n-len({e['envoy_id'] for e in candidates}),
                action_envoy_id_not_sampled=True, complete_legality_proven=False)


def sample(reader, base):
    value = prior.sample(reader, base)
    for tag, diplomats in value['diplomats'].items():
        diplomats['native_id_exclusion'] = envoy_exclusion(reader, value['countries'][tag], diplomats)
    value['country_war_raw_289b'] = {
        tag: reader.byte(int(country['address'],16)+0x289b)
        for tag,country in value['countries'].items()}
    prior.require(prior.roots(reader,base)==value['roots'], 'Roots changed after extended sample')
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,required=True)
    p.add_argument('--creation',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--allow-tag-host',action='store_true')
    args=p.parse_args()
    prior.require(not args.output.exists(),'Exclusive report exists; use no automatic retry')
    report=dict(schema='EU4TAG-CURRENT-PREREQUISITES/1',game_sha256=GAME_SHA,
                pid=args.pid,creation=args.creation,captured_utc=datetime.now(timezone.utc).isoformat(),
                native_calls=0,memory_written=False,requests_published=0,
                engine_predicates_called=False,status='incomplete',two_pass_equal=False,
                automatic_retry=False,complete_legality_proven=False,passes=[])
    reader=held=None
    try:
        backend=TagCommandBackend()
        runtime=WindowsRuntime()
        held=runtime.readonly.Held(dict(pid=args.pid,creation=args.creation,session='1'*32,
            manifest_sha256=backend.manifest_sha,dll_sha256=backend.manifest['dll']['sha256']))
        held.identity_check()
        canonical=held.injector._canonical
        modules=held.modules()
        matches=[b for b,path in modules if canonical(path)==canonical(held.injector.GAME)]
        prior.require(len(matches)==1,'Exact game module unavailable')
        research=[str(path) for _,path in modules if Path(path).name.lower().startswith(
            ('eu4_bridge_','eu4_pair_','eu4_spy_','eu4_tag_command_','tag_diplomacy'))]
        expected=backend.build/backend.manifest['DLL']
        prior.require((not research) or (args.allow_tag_host and len(research)==1
            and canonical(research[0])==canonical(expected)), 'Unexpected research module')
        base=pointer(matches[0]);reader=prior.Reader(held)
        disk=runtime.readonly.disk_identity(held.injector.GAME)
        prior.require(runtime.readonly.pe_header(reader.read(base,8192))==disk,'Loaded PE differs')
        report.update(module_base=hex(base),loaded_main_pe=disk,research_modules=research)
        for _ in range(2):
            report['passes'].append(sample(reader,base));held.identity_check()
        prior.require(report['passes'][0]==report['passes'][1], 'Two complete samples differ')
        report.update(status='sampled_equal',two_pass_equal=True)
    except Exception as exc:
        report.update(status='failed_no_retry',failure=dict(type=type(exc).__name__,message=str(exc)))
    finally:
        if reader:
            report['rpm_budget']=dict(calls=reader.calls,bytes=reader.bytes_read,
                largest_read=reader.largest_read,max_calls=prior.MAX_CALLS,max_bytes=prior.MAX_BYTES)
        if held:held.close()
    report['peak_committed_bytes']=check_memory_budget()
    names=['work/inspect_tag31_corrective_pairs.py','work/probe_pair_effects_1375.py',
           'work/probe_current_diplomacy_1375.py',
           'work/reports/rea-diplomacy-20261013/envoy-reservation-readonly-spec.md',
           'work/reports/rea-api-discovery-20261013/prior-four-findings.json']
    report['source_pins']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    report['limitations']=['Two equal passes are not an atomic owner-thread snapshot.',
        'Envoy exclusion and cooldown are partial public conditions, not full88 or acceptance.',
        'No factory, predicate, TLS initializer or effect function was called.']
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    summary={k:report[k] for k in ('status','two_pass_equal','rpm_budget','peak_committed_bytes') if k in report}
    if report['two_pass_equal']:
        value=report['passes'][0]
        summary.update(date=value['roots']['date'],war=value['country_war_raw_289b'],
            envoys={t:{k:d['native_id_exclusion'][k] for k in ('N','R','unmatched','R_less_than_N')}
                    for t,d in value['diplomats'].items()},
            pairs=[dict(action=r['action'],cooldown_allows=r['cooldown_only_allows'],
                type=r['dependency']['object']['type_name']['name'] if r['dependency']['object'] else None)
                for r in value['pairs']])
    else:summary['failure']=report['failure']
    print(json.dumps(summary));return 0 if report['two_pass_equal'] else 2

if __name__=='__main__':raise SystemExit(main())
