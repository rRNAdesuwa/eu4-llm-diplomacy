"""External white-peace negotiation; proposal and settlement are separate."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
from local_config import user_data

USER = user_data()

def write(name, body):
    (USER / name).write_text(body, encoding='utf-8')

for proposer, recipient, suffix in [('FRA', 'ENG', 'fra'), ('ENG', 'FRA', 'eng')]:
    flag = 'llm_peace_pending_' + suffix
    request = 'peace_' + suffix + '_01'
    offer = f'''# External proposal only: no native peace popup and no settlement.
FRA = {{
    if = {{
        limit = {{ ai = yes war_with = ENG }}
        set_country_flag = {flag}
        log = "EU4LLM_PEACE|OFFER|{request}|{proposer}|{recipient}|white_peace"
    }}
    else = {{ log = "EU4LLM|ACK|{request}_offer|rejected" }}
}}
'''
    accept = f'''# Use only after the external recipient accepts this white-peace offer.
FRA = {{
    if = {{
        limit = {{ ai = yes war_with = ENG has_country_flag = {flag} }}
        white_peace = ENG
        if = {{
            limit = {{ NOT = {{ war_with = ENG }} }}
            clr_country_flag = llm_peace_pending_fra
            clr_country_flag = llm_peace_pending_eng
            log = "EU4LLM|ACK|{request}_accept|applied"
        }}
        else = {{ log = "EU4LLM|ACK|{request}_accept|rejected" }}
    }}
    else = {{ log = "EU4LLM|ACK|{request}_accept|rejected" }}
}}
'''
    write(f'llm_peace_offer_{suffix}.txt', offer)
    write(f'llm_peace_accept_{suffix}.txt', accept)

runtime = ROOT / 'work/runtime'
runtime.mkdir(exist_ok=True)
(runtime / 'peace-offer.json').write_text(json.dumps({
    'id': 'peace_fra_01', 'proposer': 'FRA', 'recipient': 'ENG',
    'status': 'proposed', 'channel': 'external',
    'terms': {'type': 'white_peace', 'province_transfers': [], 'payments': 0},
    'message': '法国提议英法无条件停战，双方保留现有领土，不支付赔款。',
}, ensure_ascii=False, indent=2), encoding='utf-8')
print('Prepared external peace offer and guarded acceptance scripts for both directions.')
