"""Append-only manual UI test journal; never calls the game or grants authority."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'work/runtime/spy5-ui-batch-38232.jsonl'
ORDER = ('corrupt_officials', 'sabotage_reputation', 'sow_discontent',
         'slander_merchants', 'sabotage_recruitment')
INITIAL = ROOT / 'work/runtime/spy-test-setup-ro-38232-after_fixture.json'
INITIAL_SHA = '21d40a44976fdc053c575740442bd99180b192ec87210c27e9989247270de81c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', choices=('start', 'intent', 'ui_confirmed', 'unknown'), required=True)
    parser.add_argument('--family', choices=ORDER)
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    if len(args.note) > 1024:
        raise ValueError('Note budget')
    if hashlib.sha256(INITIAL.read_bytes()).hexdigest() != INITIAL_SHA:
        raise ValueError('Initial census changed')
    initial = json.loads(INITIAL.read_text('utf-8'))
    if initial['status'] != 'captured' or initial['world'] != 0x1a0cb39c020:
        raise ValueError('Initial census identity')
    record = dict(event=args.event, family=args.family, note=args.note,
                  recorded_utc=datetime.now(timezone.utc).isoformat(),
                  pid=38232, creation='01dd56e0cbe2c7f7', world='0x1a0cb39c020',
                  initial_sha256=INITIAL_SHA, actor='FRA', target='ENG',
                  source='manual_game_ui_observation', native_request_receipt=False,
                  individual_effect_verified=False, production_ready=False)
    if args.event == 'start':
        if args.family is not None:
            raise ValueError('Start family')
        record['plan'] = ORDER
        with OUTPUT.open('xb') as stream:
            stream.write((json.dumps(record, sort_keys=True) + '\n').encode())
    else:
        if args.family is None or not OUTPUT.exists() or OUTPUT.stat().st_size > 32768:
            raise ValueError('Missing/bounded journal')
        rows = [json.loads(line) for line in OUTPUT.read_text('utf-8').splitlines()]
        if rows[0]['event'] != 'start' or any(x['event'] == 'unknown' for x in rows):
            raise ValueError('Terminal/missing start')
        intents = [x['family'] for x in rows if x['event'] == 'intent']
        done = [x['family'] for x in rows if x['event'] == 'ui_confirmed']
        if args.event == 'intent':
            if intents != done or len(done) >= len(ORDER) or args.family != ORDER[len(done)]:
                raise ValueError('No repeat; fixed next family only')
        elif intents != done + [args.family]:
            raise ValueError('Exact pending UI intent required')
        with OUTPUT.open('ab') as stream:
            stream.write((json.dumps(record, sort_keys=True) + '\n').encode())
    print(json.dumps(dict(event=args.event, family=args.family, bytes=OUTPUT.stat().st_size)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
