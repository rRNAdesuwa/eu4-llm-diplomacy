"""Compare bounded serialized extracts after the batch; never opens EU4."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import decode, encode, read, require


def canonical(node):
    if 'entries' in node:
        return {'key': node['key'], 'entries': [canonical(e) for e in node['entries']]}
    return {'key': node['key'], 'value': node['value']}


def records(nodes):
    return Counter(encode(canonical(n)) for n in nodes)


def difference(before, after):
    left, right = records(before), records(after)
    return dict(removed=[decode(n) for n in (left-right).elements()],
                added=[decode(n) for n in (right-left).elements()])


def compare(groups):
    countries, global_before, global_after, inputs = {}, {}, {}, []
    source_before = source_after = None
    metadata = None
    for before_raw, after_raw in groups:
        before, after = decode(before_raw), decode(after_raw)
        require(before['parsed_complete'] and after['parsed_complete']
                and before['actor'] == after['actor']
                and before['targets'] == after['targets']
                and before['selected_effect_fields'] == after['selected_effect_fields'],
                'Save extraction scope mismatch')
        a, b = before['source']['sha256'], after['source']['sha256']
        require(source_before in (None, a) and source_after in (None, b),
                'Mixed before/after saves')
        source_before, source_after = a, b
        metadata = {'before': before['metadata'], 'after': after['metadata']}
        inputs.append({'before': hashlib.sha256(before_raw).hexdigest(),
                       'after': hashlib.sha256(after_raw).hexdigest()})
        for tag, left in before['countries'].items():
            right = after['countries'][tag]
            require(left['status'] == right['status'] == 'found', 'Selected country missing')
            fields = difference(left['fields'], right['fields'])
            diplomats = difference(left['diplomats']['blocks'], right['diplomats']['blocks'])
            relations = {other: delta for other in left['relations']
                         if (delta := difference(left['relations'][other]['blocks'],
                                                 right['relations'][other]['blocks']))['removed'] or delta['added']}
            if tag in countries:
                require(countries[tag]['fields'] == fields and countries[tag]['diplomats'] == diplomats,
                        'Repeated selected country differs across groups')
                countries[tag]['relations'].update(relations)
            else:
                countries[tag] = dict(fields=fields, diplomats=diplomats, relations=relations)
        for report, target in ((before, global_before), (after, global_after)):
            for record in report['global_diplomacy']['records']:
                # Deduplicate the same source record captured by both selected groups.
                key = record['byte_offset']
                require(key not in target or target[key] == record, 'Global record changed across groups')
                target[key] = record
    require(groups, 'No save groups')
    return dict(schema='EU4TAG31-SERIALIZED-DIFF/1', file_only=True,
                before_save_sha256=source_before, after_save_sha256=source_after,
                extract_sha256=inputs, metadata=metadata, countries=countries,
                global_diplomacy=difference(global_before.values(), global_after.values()),
                gameplay_causality_proven=False, AI_acceptance_all_verified=False,
                limitation='Selected serialized state only; a dispatched request is not automatically an accepted action. Paired start/stop actions may leave the same final state.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before', type=Path, action='append', required=True)
    p.add_argument('--after', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(len(args.before) == len(args.after) <= 4, 'Mismatched save groups')
    report = compare([(read(a, 4*1024*1024), read(b, 4*1024*1024))
                      for a, b in zip(args.before, args.after)])
    with args.output.open('xb') as target:
        target.write(encode(report))
    print(json.dumps(dict(output=str(args.output), countries=len(report['countries']),
                          global_added=len(report['global_diplomacy']['added']),
                          global_removed=len(report['global_diplomacy']['removed']),
                          gameplay_causality_proven=False)))


if __name__ == '__main__':
    main()
