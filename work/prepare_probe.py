"""Create a standalone run probe that does not require a loaded mod."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
from local_config import user_data

user = user_data()
effect = (root / 'mod/llm_bridge/common/scripted_effects/llm_bridge.txt').read_text(encoding='utf-8')
body = effect[effect.index('{') + 1:effect.rfind('}')]
# No enabling flags: this probe exports state only. Flag presence is not proof
# that the mod's diplomatic restrictions have actually been loaded.
(user / 'llm_probe.txt').write_text('FRA = {\n' + body + '\n}\n', encoding='utf-8')
print('Prepared run llm_probe.txt')
