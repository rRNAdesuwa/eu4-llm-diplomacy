"""Install a native peace-screen term; does not send a proposal or launch EU4."""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.compiler import compile_request
from local_config import user_data

source = ROOT / 'mod/llm_bridge'
user = user_data()
dest = user / 'mod/llm_bridge'
localization = source / 'localisation/llm_bridge_treaty_l_english.yml'
localization.parent.mkdir(parents=True, exist_ok=True)
localization.write_text('''l_english:
 llm_test_pay_10_desc:0 "The paying country transfers 10 ducats to the receiving country. Native peace-screen integration test."
 CB_ALLOWED_llm_test_pay_10:0 "Test payment of 10 ducats"
 PEACE_llm_test_pay_10:0 "LLM test: Payment of 10 ducats"
''', encoding='utf-8-sig')
for rel in ('common/peace_treaties/01_llm_bridge.txt', 'localisation/llm_bridge_treaty_l_english.yml'):
    output = dest / rel
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / rel, output)

probe = compile_request({'id': 'treaty_observe01', 'action': 'snapshot'})
for tag in ('FRA', 'ENG'):
    probe += f'''\n{tag} = {{
    export_to_variable = {{ which = llm_probe_treasury value = treasury }}
    log = "EU4LLM_TREATY|{tag}|treasury|[This.llm_probe_treasury.GetValue]"
    if = {{ limit = {{ has_country_flag = llm_test_payment_paid }} log = "EU4LLM_TREATY|{tag}|paid|1" }}
    else = {{ log = "EU4LLM_TREATY|{tag}|paid|0" }}
    if = {{ limit = {{ has_country_flag = llm_test_payment_received }} log = "EU4LLM_TREATY|{tag}|received|1" }}
    else = {{ log = "EU4LLM_TREATY|{tag}|received|0" }}
}}
'''
(user / 'llm_treaty_probe.txt').write_text(probe, encoding='utf-8')
print('Native treaty installed; restart required. Prepared run llm_treaty_probe.txt.')
