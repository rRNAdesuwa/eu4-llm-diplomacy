"""Extend discovery with an explicitly pending reader; never authorize execution."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = 'docs/runtime-capability-map-1375.json'
OUTPUT = ROOT / 'docs/runtime-capability-map-1375-v2.json'
HERE = 'work/candidates/support-heir-current-observer-1375-v1/'
REVIEWS = {
 'work/reports/support-heir-current-observer-source-review-20261015-r1/independent-source-ready.json': '6ca2a47412189b621ecc765791557f0e4ea861d26317b2831fb5d2b7f6842a21',
 'work/reports/support-heir-current-observer-production-review-20261015-r1/production-passed.json': '5a5aeb0288436311715aadbad783475d0c965a822dd4248747f382a6d3b32ab2',
 'work/reports/support-heir-current-observer-unknown-path-review-20261015-r1/findings.json': 'c945c55a2aae4d6c066134977d3c02a070cfb94a632ca63f9d715554ce3a6d02',
}


def read(name):
 with (ROOT / name).open('rb') as stream: raw = stream.read(256 * 1024 + 1)
 assert 0 < len(raw) <= 256 * 1024
 return raw


def pin(name):
 raw = read(name)
 return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
 assert not OUTPUT.exists(), 'Preserve existing discovery versions'
 assert pin(OLD)['sha256'] == '3c67f43031917ea859ef95a0b8f6289ef7075d89aafa5bcbe647cedbecd0c42a'
 base = json.loads(read(OLD)); before = {OLD: pin(OLD)}
 assert len(base['tools']) == 5 and base['authoritative_for_permissions'] is False
 for item in base['tools']:
  for kind in ('entry', 'manifest'):
   assert pin(item[kind]) == item[kind + '_pin']
   before[item[kind]] = item[kind + '_pin']
 for name, sha in REVIEWS.items():
  assert pin(name)['sha256'] == sha
  before[name] = pin(name)
 entry = HERE + 'support_heir_current_observer.py'; manifest = HERE + 'source-manifest.json'
 assert pin(manifest)['sha256'] == 'f8442eefa3dbacb5a952a5d8387cf0bcea83adfcb059034984af5bd40478c069'
 owner = json.loads(read(manifest))
 assert owner['sealed'] is True and owner['runtime_capture_authorized'] is True and owner['native_ready'] is False
 assert pin(entry) == owner['source_pins'][entry] and len(owner['source_pins']) == 22
 before[entry] = pin(entry); before[manifest] = pin(manifest)
 assert (ROOT / (HERE + 'STATUS.md')).is_file()
 row = dict(id='support_heir_current_task_pending_active_world', entry=entry, manifest=manifest,
  guide=HERE + 'STATUS.md', entry_pin=pin(entry), manifest_pin=pin(manifest), manifest_direct_pin_count=22,
  scope='selected current task presence/absence or unknown; genuine loaded-world sample still pending',
  maturity='source_and_production_reviewed_failure_paths_verified_active_world_pending',
  request_effect_profile_count=0, real_world_task_decoder_verified=False,
  real_capture_scope='old process exited; new process world root NULL; two unknown results, no selected task sample',
  independent_reviews={name: before[name] for name in REVIEWS},
  permission_authority='exact owner manifest and runtime source gate, never this discovery map',
  game_functions_invoked_by_observer=False, publishes_diplomacy_requests=False,
  final_heir_result_verified=False, original_request_effect_verified=False)
 result = dict(base)
 result.update(schema='EU4-READONLY-TOOL-DISCOVERY/2', previous_discovery=dict(path=OLD, **before[OLD]),
  accepted_entry_count=5, pending_active_world_reader_count=1, tools=base['tools'] + [row],
  discovery_build_scope='exact previous artifact, owner entry/manifest pins and three selected reviews; no deep closure rehash',
  build_operations=dict(process_accesses=0, PE_opens=0, native_game_calls=0, CLI_or_tests_run=0, requests_published=0))
 assert result['tools'][:5] == base['tools']
 assert all(pin(name) == expected for name, expected in before.items())
 with OUTPUT.open('x', encoding='utf-8', newline='\n') as stream:
  stream.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
 print(json.dumps(dict(status='built', accepted_entries=5, pending_active_world=1,
  output=pin('docs/runtime-capability-map-1375-v2.json'))))


if __name__ == '__main__': main()
