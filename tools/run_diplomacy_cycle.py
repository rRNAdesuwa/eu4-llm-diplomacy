"""Run the fixed v9 war -> test fixture -> whitepeace sequence in one PID.

The game must render foreground frames. Advance time manually when envoys or
cooldowns require it. Existing acknowledged stages are resumed, never repeated.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'work'))
from local_config import get_value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--test-winwars', action='store_true', required=True,
                        help='Explicitly enable the artificial war-score experiment.')
    parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    python = get_value('EU4_PYTHON')
    native = ROOT / 'work/native'
    deadline = time.monotonic() + args.timeout
    sent = set()
    last_message = None
    while time.monotonic() < deadline:
        events = [json.loads(line) for line in (native / 'probe.jsonl').read_text(
            encoding='utf-8').splitlines() if line.strip()]
        installs = [i for i, e in enumerate(events)
                    if e.get('event') == 'automated_diplomacy_installed']
        if not installs or events[installs[-1]].get('pid') != args.pid:
            raise SystemExit('Latest v9 installation must match the requested PID.')
        events = events[installs[-1]:]
        names = {e.get('event') for e in events}
        failures = [e for e in events if e.get('event', '').endswith(
            ('_failed', '_rejected', '_not_submitted', '_not_confirmed'))]
        if failures:
            raise SystemExit(json.dumps({'stopped': failures[-1]}))
        accepted = any(e.get('event') == 'llm_authorized_peace_execute_entry'
                       and e.get('state_raw') == 2 and e.get('authorization', 0)
                       for e in events)
        if accepted:
            report = ROOT / 'work/runtime/automatic-cycle-settlement.json'
            subprocess.run([python, '-B', str(ROOT / 'work/probe_war_pair.py'),
                            '--pid', str(args.pid), '--output', str(report)],
                           check=True, capture_output=True, text=True, timeout=45)
            state = json.loads(report.read_text(encoding='utf-8'))
            if not state['both_pair_at_peace'] or state['player_slot'] != 189:
                raise SystemExit('Native acceptance observed but settlement/player verification failed.')
            print(json.dumps({'pid': args.pid, 'cycle_native_accepted': True,
                              'both_pair_at_peace': True, 'player_restored': True,
                              'report': str(report)}), flush=True)
            return
        if 'automatic_war_runtime_confirmed' not in names:
            action, filename = 'declare_war', 'declare-war.request'
        elif 'authorization_selftest_passed' not in names:
            action, filename = None, None
        elif 'test_winwars_fixture_applied' not in names:
            action, filename = 'test_winwars', 'test-winwars.request'
        elif 'whitepeace_submitted' not in names:
            action, filename = 'whitepeace', 'whitepeace.request'
        else:
            action, filename = None, None
        if action and action not in sent and not (native / filename).exists():
            result = subprocess.run([python, '-B', str(ROOT / 'tools/request_diplomacy.py'),
                                     action, '--pid', str(args.pid)], capture_output=True,
                                    text=True, timeout=45)
            message = (result.stdout + result.stderr).strip()
            if result.returncode:
                # Only these temporary engine gates are retried; no request was queued.
                waiting = ('no confirmed available diplomat', 'date guard has not cleared',
                           'relation cooldown has not cleared')
                if not any(reason in message for reason in waiting):
                    raise SystemExit(message)
            else:
                sent.add(action)
            if message != last_message:
                print(message, flush=True)
                last_message = message
        time.sleep(3)
    raise SystemExit('Timed out; no restart or retry of an acknowledged stage was performed.')


if __name__ == '__main__':
    main()
