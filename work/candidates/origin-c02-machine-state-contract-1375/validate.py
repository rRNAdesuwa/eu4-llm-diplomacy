"""CreateNew offline validation record; no compile, process access, or native test."""
import datetime
import json
import subprocess
import sys
from pathlib import Path
from prepare import HERE, ROOT, SOURCE_FILES, digest, load


def inventory():
    paths = [ROOT / name for name in load(HERE / 'pins.json')['files']]
    paths += [HERE / name for name in SOURCE_FILES + ('contract.json',)]
    return {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in paths}


def main():
    # All destinations are exclusively created before running child commands.
    with (HERE / 'validation.json').open('x', encoding='utf-8', newline='\n') as output:
        streams = []
        try:
            for name in ('check.stdout', 'tests.stdout'):
                streams.append((HERE / name).open('xb'))
            before = inventory()
            commands = [[sys.executable, '-B', str(HERE / 'prepare.py'), '--check'],
                        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_model.py', '-v']]
            results = []
            for index, command in enumerate(commands):
                start = datetime.datetime.now(datetime.timezone.utc).isoformat()
                run = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     timeout=60, check=False)
                streams[index].write(run.stdout)
                streams[index].flush()
                results.append({'argv': command, 'cwd': str(ROOT), 'started_utc': start,
                                'exit_code': run.returncode, 'stdout_path': ('check.stdout', 'tests.stdout')[index],
                                'stdout_sha256': __import__('hashlib').sha256(run.stdout).hexdigest(),
                                'stdout_bytes': len(run.stdout), 'child_collected': True})
            after = inventory()
            result = {'schema': 'origin_c02_validation_v1', 'commands': results,
                      'inputs_before': before, 'inputs_after': after, 'inputs_unchanged': before == after,
                      'offline_validation_passed': before == after and all(x['exit_code'] == 0 for x in results),
                      'all_child_shells_collected': True, 'native_compiled': False, 'native_executed': False,
                      'game_process_accessed': False, 'hook_installed': False,
                      'previous_ad_hoc_commands': [
                          {'purpose': 'read evidence and docs', 'uncollected_sessions': 0},
                          {'purpose': 'separate requested exact-byte check for v16 pin issue',
                           'exe_sha256': '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
                           'read_rva': '0xe5021e', 'read_bytes': 7, 'output_hex': '483bd87710488d',
                           'exit_code': 1, 'reason': 'after printed read result, attempted nonexistent PE.close; process exited',
                           'part_of_C02_evidence': False, 'child_collected': True}]}
            output.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            output.flush()
            print(json.dumps({'passed': result['offline_validation_passed'], 'commands': len(results),
                              'inputs': len(before), 'path': str(HERE / 'validation.json')}))
            return 0 if result['offline_validation_passed'] else 1
        finally:
            for stream in streams:
                stream.close()


if __name__ == '__main__':
    raise SystemExit(main())
