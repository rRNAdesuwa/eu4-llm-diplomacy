"""Build a version-specific overlay from local vanilla files, then install reversibly."""
import json
import re
import shutil
from pathlib import Path

from local_config import game_root, user_data

ROOT = Path(__file__).resolve().parents[1]
GAME = game_root()
USER = user_data()
SOURCE = ROOT / 'mod' / 'llm_bridge'
BACKUP = ROOT / 'work' / 'backup'
BACKUP.mkdir(parents=True, exist_ok=True)

# Preserve all existing action definitions, inserting a condition in two proven keys.
p = GAME / 'common/diplomatic_actions/00_diplomatic_actions.txt'
s = p.read_text(encoding='utf-8-sig')
condition = '''
    condition = {
        tooltip = LLM_BRIDGE_LOCKED
        potential = { has_country_flag = llm_diplomacy_locked }
        allow = { NOT = { has_country_flag = llm_diplomacy_locked } }
    }
'''
for action in ('declarewar', 'break_alliance'):
    s, count = re.subn(r'(?m)^' + action + r'\s*=\s*\{', lambda m: m[0] + condition, s, count=1)
    assert count == 1, action
out = SOURCE / 'common/diplomatic_actions/00_diplomatic_actions.txt'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(s, encoding='utf-8-sig')
# Avoid relying on duplicate on_action merge behavior.
s = (GAME / 'common/on_actions/00_on_actions.txt').read_text(encoding='utf-8-sig')
s, count = re.subn(r'(?m)^on_monthly_pulse\s*=\s*\{', lambda m: m[0] + '\n    events = { llm_bridge.1 }\n', s, count=1)
assert count == 1
out = SOURCE / 'common/on_actions/00_on_actions.txt'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(s, encoding='utf-8-sig')
out = SOURCE / 'localisation/llm_bridge_l_english.yml'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text('l_english:\n LLM_BRIDGE_LOCKED:0 "LLM bridge: autonomous diplomacy locked"\n llm_bridge_goodwill:0 "Diplomatic goodwill"\n', encoding='utf-8-sig')
dest = USER / 'mod/llm_bridge'
shutil.copytree(SOURCE, dest, dirs_exist_ok=True)
descriptor = f'name="LLM Diplomacy Bridge Prototype"\npath="{dest.as_posix()}"\nsupported_version="1.37.4"\n'
(USER / 'mod/llm_bridge.mod').write_text(descriptor, encoding='utf-8')
config = USER / 'dlc_load.json'
if not (BACKUP / 'dlc_load.json').exists(): shutil.copy2(config, BACKUP / 'dlc_load.json')
data = json.loads(config.read_text(encoding='utf-8-sig'))
if 'mod/llm_bridge.mod' not in data['enabled_mods']: data['enabled_mods'].append('mod/llm_bridge.mod')
config.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
(USER / 'llm_bootstrap.txt').write_text('FRA = { set_country_flag = llm_bridge_enabled set_country_flag = llm_diplomacy_locked llm_bridge_snapshot = yes }\n', encoding='ascii')
(USER / 'llm_stop.txt').write_text('FRA = { clr_country_flag = llm_bridge_enabled clr_country_flag = llm_diplomacy_locked remove_opinion = { who = ENG modifier = llm_bridge_goodwill } log = "EU4LLM|ACK|stop|applied" }\n', encoding='ascii')
print('Installed:', dest)
print('Run in a new non-Ironman game as ENG: run llm_bootstrap.txt')
