"""Preserve the reviewer-only schema error and create a separate R2 reviewer."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = root / 'work/review_r61_branch_seed_20261016.py'
raw = old.read_bytes()
assert len(raw) < 16384
text = raw.decode()
old_field = "budget['old_prefix_targeted_code_read_bytes']"
new_field = "budget['old38_and183_targeted_PE_code_or_decode_bytes']"
old_dir = "war-peace-api-20261016-r61-entry-root-review'"
new_dir = "war-peace-api-20261016-r61-entry-root-review-r2'"
assert text.count(old_field) == text.count(old_dir) == 1
replacement = text.replace(old_field, new_field).replace(old_dir, new_dir).encode()
target = root / 'work/review_r61_branch_seed_20261016_r2.py'
with target.open('xb') as stream:
    stream.write(replacement)
receipt = {
    'schema': 'EU4-R61-ROOT-REVIEW-R1-ERROR/1', 'sealed': True,
    'failure': "KeyError: old_prefix_targeted_code_read_bytes at reviewer line77",
    'error_scope': 'Reviewer assumed R59 budget key; R61 uses old38_and183_targeted_PE_code_or_decode_bytes.',
    'old_reviewer': {'path': str(old), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()},
    'r2_reviewer': {'path': str(target), 'bytes': len(replacement), 'sha256': hashlib.sha256(replacement).hexdigest()},
    'r1_fixed_source_before_reads': 8, 'r1_fixed_source_bytes': 174945,
    'r1_postguard_or_findings_published': False, 'management_budget_read_bytes_after_failure': 1558,
    'changes': ['Reviewer budget key only; separate output directory to preserve R1 claim.'],
    'unchanged': ['R61 author sources', 'R59 capture', 'Original R1 reviewer script and claim'],
    'PE_decoder_game_native_requests_or_producer_rerun': 0,
}
output = root / 'work/reports/war-peace-api-20261016-r61-entry-root-review/failure.json'
with output.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(receipt, stream, ensure_ascii=True, indent=2)
    stream.write('\n')
assert old.read_bytes() == raw
print(json.dumps({'repaired_reviewer_only': True, 'r2': receipt['r2_reviewer']}))
