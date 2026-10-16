"""Merge the two fragments of one integration pass. Reads evidence files only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import decode, encode, read, require


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def combine(original_raw, remaining_raw, review_raw, first_raw, last_raw):
    original, remaining, review, first, last = map(
        decode, (original_raw, remaining_raw, review_raw, first_raw, last_raw))
    require(review['schema'] == 'EU4TAG-CONTINUATION-REVIEW/1'
            and review['file_only'] and review['only_unclaimed_commands']
            and review['idempotency_keys_preserved'] and not review['publishes'],
            'Not a reviewed unclaimed continuation')
    require(sha(original_raw) == review['original_commands_file_sha256']
            and sha(remaining_raw) == review['remaining_commands_sha256']
            and sha(first_raw) == review['captured_evidence_file_sha256'],
            'Continuation input changed')
    require(first['identity'] == review['original_identity']
            and first['audit_sha256'] == review['original_audit_sha256']
            and first['terminal'] and first['file_only'] and last['file_only']
            and first['identity'] != last['identity']
            and not last.get('partial_audit_tail', False), 'Invalid audit fragments')
    require(len(original) == review['original_count'] == first['planned']
            and len(remaining) == review['remaining_count'] == last['planned'],
            'Command count changed')
    planned = {c['request_id']: c for c in original}
    selected = {c['request_id']: c for c in remaining}
    excluded = {x['command']['request_id']: x for x in review['excluded']}
    require(len(planned) == len(original) and len(selected) == len(remaining)
            and len(excluded) == review['excluded_count']
            and not selected.keys() & excluded.keys()
            and selected.keys() | excluded.keys() == planned.keys(),
            'Duplicate or missing integration request')
    old = {r['command']['request_id']: r for r in first['results']}
    new = {r['command']['request_id']: r for r in last['results']}
    require(len(old) == len(first['results']) and old.keys() == planned.keys()
            and len(new) == len(last['results']) and new.keys() == selected.keys(),
            'Fragment request set changed')
    outcomes = []
    for command in original:
        key = command['request_id']
        require(old[key]['command'] == command, 'Original command changed')
        if key in selected:
            require(selected[key] == command and new[key]['command'] == command
                    and old[key]['state'] == 'not_dispatched'
                    and old[key]['binding'] is None and old[key]['native_result'] is None,
                    'Continuation entered an already attempted request')
            outcome = new[key]
        else:
            require(excluded[key]['command'] == command
                    and excluded[key]['state'] == old[key]['state']
                    and excluded[key]['may_resend'] is False,
                    'Excluded request changed')
            outcome = old[key]
        require(outcome['state'] not in ('published', 'claimed', 'publication_unknown'),
                'Integration fragment is still running or publication is uncertain')
        outcomes.append(outcome)
    return dict(schema='EU4TAG31-INTEGRATION-COMBINED/1', file_only=True,
                planned=len(original), results=outcomes,
                states=dict(Counter(r['state'] for r in outcomes)),
                fragments=[dict(identity=r['identity'], audit_sha256=r['audit_sha256'],
                                native_call_begins=r['native_call_begins'], terminal=r['terminal'])
                           for r in (first, last)],
                native_call_begins=first['native_call_begins'] + last['native_call_begins'],
                native_exceptions=first['native_exceptions'] + last['native_exceptions'],
                nonplayer_dispatched=[r['command'] for r in outcomes
                    if r['state'] == 'dispatched' and not r['binding']['actor_is_human_player']],
                input_sha256=dict(original=sha(original_raw), remaining=sha(remaining_raw),
                                  review=sha(review_raw), first=sha(first_raw), last=sha(last_raw)),
                gameplay_effects_verified=False, AI_acceptance_verified=False,
                automatic_retry=False, completed_without_unattempted_requests=all(
                    r['native_result'] is not None for r in outcomes))


def extend(parent_raw, segment):
    """Append a reviewed fragment without counting the shared fragment twice."""
    parent = decode(parent_raw)
    require(parent['schema'] == segment['schema'] == 'EU4TAG31-INTEGRATION-COMBINED/1'
            and parent['file_only'] and segment['file_only']
            and parent['fragments'][-1] == segment['fragments'][0]
            and parent['input_sha256']['last'] == segment['input_sha256']['first'],
            'Continuation chain is not contiguous')
    previous = {r['command']['request_id']: r for r in parent['results']}
    updates = {r['command']['request_id']: r for r in segment['results']}
    require(len(previous) == len(parent['results']) == parent['planned']
            and len(updates) == len(segment['results']) == segment['planned']
            and updates.keys() <= previous.keys(), 'Continuation chain request set changed')
    for key, result in updates.items():
        old = previous[key]
        require(old['command'] == result['command'], 'Continuation chain command changed')
        require(old == result or (old['state'] == 'not_dispatched'
                and old['binding'] is None and old['native_result'] is None),
                'Continuation changed an already attempted result')
    outcomes = [updates.get(r['command']['request_id'], r) for r in parent['results']]
    newest = segment['fragments'][-1]
    exceptions = {encode(r): r for r in parent['native_exceptions'] + segment['native_exceptions']}
    parent.update(results=outcomes, states=dict(Counter(r['state'] for r in outcomes)),
                  fragments=parent['fragments'] + [newest],
                  native_call_begins=parent['native_call_begins'] + newest['native_call_begins'],
                  native_exceptions=list(exceptions.values()),
                  nonplayer_dispatched=[r['command'] for r in outcomes
                      if r['state'] == 'dispatched' and not r['binding']['actor_is_human_player']],
                  input_sha256=dict(parent=sha(parent_raw), **segment['input_sha256']),
                  completed_without_unattempted_requests=all(r['native_result'] is not None for r in outcomes))
    return parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('original', 'remaining', 'review', 'first', 'last', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--parent', type=Path, help='Previously merged pass to extend')
    args = p.parse_args()
    report = combine(*(read(getattr(args, k), 2 * 1024 * 1024)
                       for k in ('original', 'remaining', 'review', 'first', 'last')))
    if args.parent:
        report = extend(read(args.parent, 2 * 1024 * 1024), report)
    with args.output.open('xb') as target:
        target.write(encode(report))
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ('results', 'nonplayer_dispatched')}
                     | {'nonplayer_dispatched_count': len(report['nonplayer_dispatched'])}))


if __name__ == '__main__':
    main()
