"""Project only the pinned isolated executable's captures; print model results."""
import collections
import json
import prepare
import project

prepare.check()
groups = collections.defaultdict(list)
for row in project.decode(prepare.read(prepare.HERE/'compile-final/build/capture.jsonl')):
    groups[row['scenario']].append(row)
results = {name: project.project(rows) for name, rows in groups.items()}
assert len(results) == 16
assert {name for name, r in results.items() if r['valid_complete_mock']} == {'dispatched', 'preview_false', 'gate_false', 'mixed'}
print(json.dumps({'origin': 'isolated_mock_summary', 'scenarios': results,
                  'game_accessed': False, 'actual_host_supported': False, 'production_ready': False}, sort_keys=True, indent=2))
