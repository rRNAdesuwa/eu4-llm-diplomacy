"""Offline institution/capital candidates; no eligibility or dispatch claim."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import inspect_diplomacy_save as parser
from work.discover_diplomacy import check_memory_budget

SOURCE_SHA = '09d3835dd0ac7a5e7e447fb05322b02aa7fbfcd84aaa20d67477b9022c912807'
EXTRA = {'institutions', 'capital', 'government', 'religion', 'num_of_cities',
         'owned_provinces', 'technology_group', 'technology'}


def main():
    out = ROOT/'work/reports/knowledge-nearby-candidates-20261015'
    out.mkdir(exist_ok=False)
    receipt = json.loads((ROOT/'work/reports/diplomacy-corrective-20261014-r3/runtime/batch-after-save-selected.json').read_bytes())
    parser_source = Path(parser.__file__).read_bytes()
    # Explicit key selection for this offline invocation only; the frozen
    # parser source, guards and parsing algorithm remain intact.
    parser.CONTROL = parser.CONTROL | EXTRA
    check_memory_budget()
    data = parser.inspect_save(Path(receipt['source']['path']), 'MOS',
        ('NOV', 'KAZ', 'QAS', 'UZB', 'TIM', 'MNG', 'RYA'), effect_fields=True)
    assert data['parsed_complete'] and data['source']['sha256'].lower() == SOURCE_SHA
    assert Path(parser.__file__).read_bytes() == parser_source
    data['additional_direct_country_keys_selected'] = sorted(EXTRA)
    data['parser_source_sha256'] = hashlib.sha256(parser_source).hexdigest()
    data['native_calls'] = 0
    data['game_process_accessed'] = False
    data['dispatch_eligibility_verified'] = False
    with (out/'selected-save.json').open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    summary = []
    for tag, country in data['countries'].items():
        selected = {x['key']: x for x in country.get('fields', []) if x['key'] in EXTRA}
        summary.append(dict(tag=tag, status=country['status'], fields=selected))
    result = dict(schema='EU4-KNOWLEDGE-NEARBY-OFFLINE-CANDIDATES/1',
        source_sha256=SOURCE_SHA, countries=summary,
        game_process_accessed=False, native_calls=0, requests_published=0,
        dispatch_eligibility_verified=False, peak_committed_bytes=check_memory_budget(),
        limitations=['Serialized institutions/capitals only; live range, war, current tasks and full legality unproved.'])
    with (out/'summary.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(out), countries=len(summary),
        peak_committed_bytes=result['peak_committed_bytes'], game_process_accessed=False)))


if __name__ == '__main__':
    main()
