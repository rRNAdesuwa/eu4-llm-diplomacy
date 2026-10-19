"""Final public-entry source verification and one live directional CLI query."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.eu4_observer import source_pins
from bridge.tag_command_backend import digest, require


def main():
    destination = ROOT/'work/reports/runtime-observer-20261015-r3/public-entry-verification.json'
    require(not destination.exists(), 'Exclusive verification output required')
    initial = source_pins()
    arguments = ['relations', '--pid', '80340', '--creation', '01dd5c075fcf8c26',
        'status', '--action', 'guarantee', '--actor', 'SAV', '--target', 'FRA']
    result = subprocess.run([sys.executable, '-B', 'tools/eu4_observer.py', *arguments],
        cwd=ROOT, capture_output=True, timeout=30)
    require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 256*1024,
        'Public CLI read failed')
    value = json.loads(result.stdout)
    require(value['status'] == 'reverse_relation_observed'
        and value['requested_direction_matches'] is False and value['two_pass_equal'] is True
        and not value['runtime_effect_verified'], 'Public CLI direction or effect boundary differs')
    require(source_pins() == initial, 'Public sources changed during CLI query')
    report = dict(schema='EU4-PUBLIC-OBSERVER-ENTRY-ACCEPTANCE/1',
        verified_utc=datetime.now(timezone.utc).isoformat(), source_pins=initial,
        command_arguments=arguments, exit_code=result.returncode,
        stdout_sha256=digest(result.stdout), response=value, child_process_completed=True,
        file_only_commands_previously_executed=[['catalog'], ['effects', 'catalog'],
            ['relations', 'check'], ['war', 'check']], file_only_command_exit_codes=[0, 0, 0, 0],
        public_entry_cleanup_tests=dict(count=6, passed=True, execution_seconds=0.058,
            initial_unsealed_candidate_failed_cleanup_tests=4,
            initial_problem='contextlib.closing called close rather than HTTPServer.server_close',
            final_fix='Explicit try/finally includes startup output and calls server_close',
            evidence='Root tool executions before this acceptance; old test suites not rerun here'),
        new_API_effect_tested=False, native_calls=0, memory_written=False,
        requests_published=0, saves_written=0, reloads=0,
        producer=dict(path=Path(__file__).relative_to(ROOT).as_posix(), sha256=digest(Path(__file__).read_bytes())))
    with destination.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), sha256=digest(destination.read_bytes()), source_pins=len(initial),
        exit_code=0, status=value['status'], requested_direction_matches=False,
        host_capture_duration_ms=value['duration_ms'], child_completed=True)))


if __name__ == '__main__':
    main()
