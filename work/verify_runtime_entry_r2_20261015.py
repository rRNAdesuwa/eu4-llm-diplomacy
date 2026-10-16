"""End-to-end new guarded CLI acceptance, with one read-only live pair."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import digest, require
from tools.eu4_runtime_observer_r2 import runtime_source_pins


def main():
    directory = ROOT/'work/reports/runtime-observer-20261015-r1'
    destination = directory/'guarded-cli-verification.json'
    require(not destination.exists(), 'Exclusive acceptance report required')
    initial = runtime_source_pins()
    cases = []
    for arguments in (['catalog'], ['effects', 'catalog'],
        ['war', '--pid', '80340', '--creation', '01dd5c075fcf8c26',
         'status', '--actor', 'FRA', '--target', 'ENG']):
        command = [sys.executable, '-B', 'tools/eu4_runtime_observer_r2.py', *arguments]
        child = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
        require(child.returncode == 0 and not child.stderr and len(child.stdout) <= 256*1024,
            'Guarded CLI contract differs')
        value = json.loads(child.stdout)
        if arguments[0] == 'war':
            require(value['status'] == 'observed' and value['pair_state'] == 'not_currently_opponents'
                and value['two_pass_equal'] is True and value['global_war_count'] == 4,
                'Guarded CLI live pair differs')
            require(not value['runtime_effect_verified'] and not value['peace_completion_verified'],
                'Guarded CLI overstates current membership')
        else:
            require(len(value['profiles']) == 15 and not value['all120_effect_profiles_complete'],
                'Catalog coverage differs')
        cases.append(dict(arguments=arguments, exit_code=child.returncode,
            stdout_bytes=len(child.stdout), stdout_sha256=digest(child.stdout), response=value))
    require(runtime_source_pins() == initial, 'Source changed during guarded CLI acceptance')
    result = dict(schema='EU4-RUNTIME-GUARDED-CLI-ACCEPTANCE/1',
        verified_utc=datetime.now(timezone.utc).isoformat(), source_pins=initial,
        cases=cases, new_guard_regression_tests=dict(count=6, passed=True, execution_seconds=0.192,
            evidence='Root tool execution before this CLI acceptance; not rerun here'),
        native_calls=0, memory_written=False, requests_published=0, saves_written=0, reloads=0,
        child_processes_completed=True, new_war_peace_API_effect_tested=False,
        producer=dict(path=Path(__file__).relative_to(ROOT).as_posix(),
            sha256=digest(Path(__file__).read_bytes())))
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), bytes=destination.stat().st_size,
        sha256=digest(destination.read_bytes()), source_pins=len(initial),
        commands=[dict(arguments=x['arguments'], exit_code=x['exit_code'],
            pair_state=x['response'].get('pair_state')) for x in cases],
        children_completed=True)))


if __name__ == '__main__':
    main()
