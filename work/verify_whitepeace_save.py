"""Read-only final checks for the AI-recipient white peace experiment."""
import json
import re
from pathlib import Path
from inspect_peace_save import read_member, extract_block, top_level_entries, scalar

root = Path(__file__).parent
output = root / 'runtime/native-ai-whitepeace-saved-validation.json'
report = json.loads(output.read_text(encoding='utf-8'))
if 'after_reject' in report:
    report['after'] = report.pop('after_reject')

def owners(path):
    text = read_member(Path(path), 'gamestate')
    result = {}
    for match in re.finditer(r'(?m)^[ \t]*(-\d+)=\{', text):
        body = extract_block(text, match.end() - 1)
        owner = scalar(top_level_entries(body), 'owner')
        if owner is not None:
            result[match.group(1)] = owner
    return result

before = owners(report['initial']['path'])
after = owners(report['after']['path'])
changes = [{'province': key, 'before': before.get(key), 'after': after.get(key)}
           for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)]
relations = report['after']['eng_fra_relations']
report['settlement_checks'] = {
    'player': report['after']['meta']['player'],
    'eng_fra_active_wars_before': len(report['initial']['eng_fra_active_wars']),
    'eng_fra_active_wars_after': len(report['after']['eng_fra_active_wars']),
    'mutual_truce': all(relations[key].get('truce_field') == 'yes'
                        for key in ('ENG_to_FRA', 'FRA_to_ENG')),
    'owned_provinces_before': len(before),
    'owned_provinces_after': len(after),
    'province_owner_changes': changes,
    'reload_verified': False,
}
report['limitations'] = [
    'Meta player=POR; ENG/FRA lack human=yes. Historic was_player does not imply current human control.',
    'The generic semantic diff retains historical field labels; settlement_checks is the current verification summary.',
    'Save inspection confirms serialized outcome, not successful reload or general reliability.',
]
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report['settlement_checks'], ensure_ascii=False))
