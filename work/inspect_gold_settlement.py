"""Read-only save evidence for the authorized, one-time gold peace test."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re

from inspect_peace_save import (
    read_member, find_country_container, find_country_body, top_level_entries,
    scalar, parse_meta, find_eng_fra_active_wars, relation_summary, extract_block,
)

TAGS = ('FRA', 'ENG', 'POR', 'AMG', 'AUV', 'BOU', 'FOI', 'ORL')

def snapshot(path):
    text = read_member(path, 'gamestate')
    container = find_country_container(text)
    countries = {}
    for tag in TAGS:
        body = find_country_body(container, tag)
        entries = top_level_entries(body)
        countries[tag] = {'treasury': scalar(entries, 'treasury'),
                          'human': scalar(entries, 'human')}
        if tag in ('FRA', 'ENG'):
            countries[tag]['relation'] = relation_summary(body, 'ENG' if tag == 'FRA' else 'FRA')
    owners = {}
    for match in re.finditer(r'(?m)^[ \t]*(-\d+)=\{', text):
        owner = scalar(top_level_entries(extract_block(text, match.end()-1)), 'owner')
        if owner is not None:
            owners[match.group(1)] = owner
    return {'path': str(path.resolve()), 'meta': parse_meta(read_member(path, 'meta')),
            'countries': countries, 'eng_fra_active_wars': find_eng_fra_active_wars(text),
            'province_owners': owners}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = snapshot(args.before)
    report = {'before': before, 'settlement_verified': False}
    if args.after:
        after = snapshot(args.after)
        report['after'] = after
        report['treasury_deltas'] = {
            tag: str(Decimal(after['countries'][tag]['treasury']) - Decimal(before['countries'][tag]['treasury']))
            for tag in TAGS
        }
        report['same_date'] = before['meta'].get('date') == after['meta'].get('date')
        report['province_owner_changes'] = [
            {'province': key, 'before': before['province_owners'].get(key),
             'after': after['province_owners'].get(key)}
            for key in before['province_owners'].keys() | after['province_owners'].keys()
            if before['province_owners'].get(key) != after['province_owners'].get(key)
        ]
        report['limitations'] = ['Treasury deltas require native clause/response evidence; elapsed dates and other transfers can confound attribution.']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'before_meta': before['meta'],
                      'comparison': bool(args.after), 'settlement_verified': False}, ensure_ascii=False))

if __name__ == '__main__':
    main()
