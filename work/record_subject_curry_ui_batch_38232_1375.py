"""Append-only manual UI journal; no process access or native authorization."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'work/runtime/subject-curry-ui-batch-38232.jsonl'
INITIAL = ROOT / 'work/runtime/subject-and-curry-ui-batch-ro-38232-before_ui.json'
INITIAL_SHA = 'd31f3c1335569659fd42ba59ddb3a70c2d364e8315f003e7d75488822b2b01fb'
PLAN = (('set_rival', 'BUR', True), ('military_focus', 'NAV', 5),
        ('embargo_rivals', 'NAV', True), ('scutage', 'NAV', True),
        ('divert_trade', 'NAV', True), ('curry_favors', 'POR', True))
ORDER = tuple(row[0] for row in PLAN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', choices=('start', 'intent', 'ui_confirmed', 'unavailable', 'unknown'), required=True)
    parser.add_argument('--action', choices=ORDER)
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    if len(args.note) > 1024 or INITIAL.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Input budget')
    data = INITIAL.read_bytes()
    if hashlib.sha256(data).hexdigest() != INITIAL_SHA:
        raise ValueError('Initial census changed')
    initial = json.loads(data)
    if (initial['status'], initial['pid'], initial['creation'], initial['world'], initial['raw_date']) != (
            'captured', 38232, '01dd56e0cbe2c7f7', 0x1a0cb39c020, 56456976):
        raise ValueError('Initial identity')
    record = dict(event=args.event, action=args.action, note=args.note,
                  recorded_utc=datetime.now(timezone.utc).isoformat(),
                  pid=38232, creation='01dd56e0cbe2c7f7', world='0x1a0cb39c020',
                  initial_sha256=INITIAL_SHA, actor='FRA',
                  source='manual_game_ui_observation', native_request_receipt=False,
                  individual_effect_verified=False, production_ready=False)
    if args.event == 'start':
        if args.action is not None:
            raise ValueError('Start action')
        record['plan'] = PLAN
        mode = 'xb'
    else:
        if args.action is None or not OUTPUT.exists() or OUTPUT.stat().st_size > 32768:
            raise ValueError('Missing/bounded journal')
        rows = [json.loads(line) for line in OUTPUT.read_text('utf-8').splitlines()]
        if rows[0]['event'] != 'start' or any(row['event'] == 'unknown' for row in rows):
            raise ValueError('Terminal/missing start')
        intents = [row['action'] for row in rows if row['event'] == 'intent']
        done = [row['action'] for row in rows if row['event'] in ('ui_confirmed', 'unavailable')]
        if args.event == 'intent':
            if intents != done or len(done) >= len(ORDER) or args.action != ORDER[len(done)]:
                raise ValueError('Fixed next action; no repeat')
        elif intents != done + [args.action]:
            raise ValueError('Exact pending intent required')
        _, record['target'], record['requested_value'] = PLAN[ORDER.index(args.action)]
        mode = 'ab'
    with OUTPUT.open(mode) as stream:
        stream.write((json.dumps(record, sort_keys=True) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(dict(event=args.event, action=args.action, bytes=OUTPUT.stat().st_size)))


if __name__ == '__main__':
    main()
