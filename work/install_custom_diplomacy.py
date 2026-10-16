"""Install only the custom-action prototype; no launch configuration changes."""
from pathlib import Path
import shutil

from local_config import user_data

root = Path(__file__).resolve().parents[1]
source = root / 'mod/llm_bridge'
dest = user_data() / 'mod/llm_bridge'
localization = source / 'localisation/llm_bridge_actions_l_english.yml'
localization.parent.mkdir(parents=True, exist_ok=True)
localization.write_text('''l_english:
 llm_submit_white_peace:0 "LLM: Propose White Peace"
 llm_submit_white_peace_title:0 "LLM: Propose White Peace"
 llm_submit_white_peace_desc:0 "Submit a white-peace proposal to France's external LLM. The war continues until acceptance."
 llm_submit_white_peace_tooltip:0 "Submit a white-peace proposal for external review."
 llm_submit_white_peace_alert_tooltip:0 "External white-peace proposal"
 llm_accept_white_peace:0 "LLM: Accept White Peace"
 llm_accept_white_peace_title:0 "LLM: Accept White Peace"
 llm_accept_white_peace_desc:0 "Accept France's pending external white-peace proposal and end the war."
 llm_accept_white_peace_tooltip:0 "Accept the pending white peace."
 llm_accept_white_peace_alert_tooltip:0 "Accept external white peace"
''', encoding='utf-8-sig')
for rel in ('common/new_diplomatic_actions/01_llm_bridge.txt', 'localisation/llm_bridge_actions_l_english.yml'):
    output = dest / rel
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / rel, output)
print('Installed custom diplomatic actions. Requires game restart; not yet runtime-tested.')
