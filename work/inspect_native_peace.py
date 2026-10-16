"""Read-only executable string inventory; names are evidence, not callable APIs."""
from pathlib import Path
import re
import json

from local_config import game_root

game = game_root()
data = (game / 'eu4.exe').read_bytes()
patterns = re.compile(r'peace.?offer|offer.?peace|send.?peace|accept.?peace|script_docs|dump.*command|diplomatic.?action|requestpeace', re.I)
matches = []
for match in re.finditer(rb'[\x20-\x7e]{5,}', data):
    value = match.group().decode('ascii')
    if patterns.search(value) and len(value) < 500:
        matches.append({'offset': hex(match.start()), 'text': value})
output = Path(__file__).resolve().parent / 'runtime/native-peace-strings.json'
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(matches, indent=2), encoding='utf-8')
for item in matches[:120]:
    print(item['offset'], item['text'])
print(f'{len(matches)} matching strings; full inventory saved locally.')
