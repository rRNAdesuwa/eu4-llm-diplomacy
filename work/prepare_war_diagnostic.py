"""Write a read-only probe for each war-test precondition."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.compiler import ActionRequest

from local_config import user_data

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--request-id', default='war_v7_01')
args = parser.parse_args()
request = ActionRequest(args.request_id, 'declare_war', 'ENG')

checks = {
    'ai': 'ai = yes',
    'independent': 'is_subject = no',
    'locked': 'has_country_flag = llm_diplomacy_locked',
    'unused': f'NOT = {{ has_country_flag = llm_req_{request.request_id} }}',
    'at_peace_with_eng': 'NOT = { war_with = ENG }',
    'no_truce': 'NOT = { truce_with = ENG }',
    'no_alliance': 'NOT = { alliance_with = ENG }',
    'reconquest_cb': 'has_casus_belli = { type = cb_core target = ENG }',
    'goal_valid': '177 = { owned_by = ENG is_core = FRA }',
}
lines = ['log = "EU4LLM_DIAG|war|begin"']
for tag in ('FRA', 'ENG'):
    lines += [f'if = {{ limit = {{ exists = {tag} }} log = "EU4LLM_DIAG|exists_{tag}|1" }}',
              f'else = {{ log = "EU4LLM_DIAG|exists_{tag}|0" }}']
lines += ['FRA = {']
for key, condition in checks.items():
    lines += [f'if = {{ limit = {{ {condition} }} log = "EU4LLM_DIAG|{key}|1" }}',
              f'else = {{ log = "EU4LLM_DIAG|{key}|0" }}']
lines += ['}', 'log = "EU4LLM_DIAG|war|end"']
output = user_data() / 'llm_war_diag.txt'
output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(output)
