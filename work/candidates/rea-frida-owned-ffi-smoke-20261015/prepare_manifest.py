"""Create source-only pins once. Does not spawn, load a provider or call WinAPI."""
import hashlib

from evidence import require, strict_json
from protocol import HERE, ROOT, MANIFEST, LOCAL_NAMES, pin, read_bound, write_json_new, verify_sources

BASE = ROOT/'work/candidates/rea-frida-owned-smoke-20261015'
BASE_SHA = '076ef47c157d6f2bbe47211e071d947ee2b5f5f1770e67f03d66c3e54c869934'


def main():
    raw = read_bound(BASE/'source-manifest.json')
    require(hashlib.sha256(raw).hexdigest() == BASE_SHA, 'base_manifest_changed')
    base = strict_json(raw)
    reused = ['fixture.py','evidence.py','protocol.py','controller.py','launch_smoke.py']
    for name in reused:
        require(pin(BASE/name) == base['candidate_sources'][name], 'base_source_changed')
    # Explicitly selected already reviewed infrastructure pins; no full closure claim.
    old_dependencies = base['project_evidence_pins']
    wanted = [name for name in old_dependencies if '/prepared-r1-' not in name
              and '/offline-r2/' not in name and not name.endswith('OFFLINE_R2_CORRIGENDUM.md')]
    dependencies = {}
    for name in wanted:
        require(pin(ROOT/name) == old_dependencies[name], 'old_dependency_changed')
        dependencies[name] = old_dependencies[name]
    for path in [BASE/'source-manifest.json']+[BASE/name for name in reused]+[
        ROOT/'work/reports/rea-frida-owned-smoke-root-review-20261015/source-ready.json',
        ROOT/'work/reports/rea-frida-owned-smoke-independent-review-20261015/manifest.json']:
        dependencies[path.relative_to(ROOT).as_posix()] = pin(path)
    review = strict_json(read_bound(ROOT/'work/reports/rea-frida-owned-smoke-root-review-20261015/source-ready.json'))
    require(review['manifest_sha256'] == BASE_SHA, 'base_review_binding')
    manifest = dict(schema='REA-OWNED-FFI-SMOKE-SOURCE-MANIFEST/1', sealed=False,
        runtime_executed=False, status='source_only_pending_root_review_before_one_owned_run',
        candidate_sources={name:pin(HERE/name) for name in sorted(LOCAL_NAMES)},
        project_evidence_pins=dependencies, selected_external_pins=base['selected_external_pins'],
        complete_transitive_dependency_closure_claimed=False, Frida_version='17.23.2',
        target_selection='new Popen-created waiting child only; no external PID/command accepted',
        fixed_kernel32_exports=['lstrlenA','GetCurrentProcessId'],
        fixed_native_options=dict(abi='win64', scheduling='exclusive', exceptions='propagate', traps='none'),
        official_reference='https://frida.re/docs/javascript-api/#nativefunction',
        game_accessed=False, native_ready=False, native_ABI_ready=False, lease=False,
        old_sources_modified=False, old_suites_rerun=False)
    write_json_new(MANIFEST, manifest)
    result = verify_sources()
    print('source_only_manifest '+result['manifest_sha256']+' provider_executed=false')


if __name__ == '__main__':
    main()
