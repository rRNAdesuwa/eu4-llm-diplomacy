"""Root-owned bounded read-only acceptance; fixed commands, no action retries."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / 'work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py'
CLI_SHA = '5429932a8f4fb81180c566caa0905008d60880f51f7c5868dd7568b4040fe518'
MANIFEST = CLI.parent / 'source-manifest.json'
REVIEW = ROOT / 'work/reports/direct-truce-cache-cli-source-review-20261015-r1/independent-source-ready.json'
PRODUCTION_REVIEW = ROOT / 'work/reports/direct-truce-cache-cli-production-review-20261015-r1/independent-production-passed.json'
PRODUCTION_REVIEW_SHA = 'fa889e16ba1844cccaad8eca17b1905910e82560d3db374c262de9ac73200f50'
JOB = ROOT / 'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOB_SHA = '5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
OUT = ROOT / 'work/reports/direct-truce-cache-cli-root-queries-20261015-r1'
PAIRS = [('FRA', 'AUV'), ('AUV', 'FRA'), ('POR', 'BRI'), ('BRI', 'POR')]


def read(path, limit=2*1024*1024):
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    assert len(value) <= limit, str(path)
    return value


def pin(path):
    raw = read(path)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def load(path, expected_sha, name):
    raw = read(path)
    assert hashlib.sha256(raw).hexdigest() == expected_sha
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def save(name, value):
    with (OUT/name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-sha', required=True)
    parser.add_argument('--production-manifest-sha', required=True)
    args = parser.parse_args()
    assert not OUT.exists(), 'One-shot root acceptance already claimed'
    assert pin(REVIEW)['sha256'] == args.review_sha
    assert pin(MANIFEST)['sha256'] == args.production_manifest_sha
    assert pin(PRODUCTION_REVIEW)['sha256'] == PRODUCTION_REVIEW_SHA
    cli = load(CLI, CLI_SHA, '_root_current_truce_cli')
    sources = cli.Libraries()
    assert json.loads(read(MANIFEST))['runtime_capture_authorized'] is True
    job = load(JOB, JOB_SHA, '_root_current_truce_job')
    input_paths = [Path(__file__).resolve(), CLI, MANIFEST, REVIEW, PRODUCTION_REVIEW, JOB]
    inputs = {str(path.relative_to(ROOT)): pin(path) for path in input_paths}
    commands = [('check', ['check']), ('catalog', ['catalog'])]
    for actor, target in PAIRS:
        commands.append((actor + '-' + target, ['status', '--pid', '80340', '--creation',
            '01dd5c075fcf8c26', '--actor', actor, '--target', target]))
    OUT.mkdir()
    save('claim.json', dict(input_pins=inputs, fixed_commands=commands,
        purpose='current directional cache queries; historical releases are never resent',
        requests_published=0, native_game_calls=0, retries=0))
    results = []
    for name, arguments in commands:
        sources.guard()
        stdout, stderr = OUT/(name + '.stdout.json'), OUT/(name + '.stderr.txt')
        scope = job.run_cli_tree([sys.executable, '-B', str(CLI)] + arguments, ROOT,
            stdout, stderr, timeout_seconds=30, memory_limit=768*1024*1024)
        raw = read(stdout)
        parse_error = None
        try:
            value = json.loads(raw) if raw else None
        except (ValueError, UnicodeError) as exc:
            value = None
            parse_error = str(exc)
        sources.guard()
        okay = (scope.get('error') is None and scope.get('exit_code') == 0
            and scope.get('job_active_processes_final') == 0
            and scope.get('direct_child_collected') is True
            and 1 <= scope.get('job_total_processes', 0) <= 8
            and stderr.stat().st_size == 0 and type(value) is dict and cli.result_code(value) == 0)
        results.append(dict(name=name, arguments=arguments, passed=okay, job=scope,
            stdout=pin(stdout), stderr=pin(stderr), parse_error=parse_error, status=value.get('status') if value else None,
            direct_pair_cache_flag_set=value.get('direct_pair_cache_flag_set') if value else None,
            selected_effect_verified=value.get('selected_effect_verified') if value else None,
            duration_ms_including_guards=value.get('duration_ms_including_guards') if value else None))
        print(json.dumps(results[-1], ensure_ascii=True), flush=True)
        if not okay:
            break
    sources.guard()
    unchanged = all(pin(ROOT/name) == value for name, value in inputs.items())
    passed = unchanged and len(results) == len(commands) and all(row['passed'] for row in results)
    receipt = dict(schema='EU4-DIRECT-TRUCE-CACHE-CLI-ROOT-ACCEPTANCE/1',
        status='passed' if passed else 'incomplete', input_pins=inputs, sources_unchanged=unchanged,
        results=results, commands_attempted=len(results), commands_planned=len(commands),
        actual_status_commands=sum(row['arguments'][0] == 'status' for row in results),
        selected_effects_added=0, requests_published=0, native_game_calls=0, Frida_operations=0,
        game_fields_written=0, saves=0, reloads=0, retries=0, native_ready=False)
    save('receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'receipt': pin(OUT/'receipt.json')}, ensure_ascii=True))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
