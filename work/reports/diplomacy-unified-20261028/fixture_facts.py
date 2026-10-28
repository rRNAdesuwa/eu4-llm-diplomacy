import re, json
p = r'work/fixtures/111.eu4'
data = open(p, 'r', encoding='latin1').read()
def block(text, start):
    i = text.find('{', start); d = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == '{': d += 1
        elif c == '}':
            d -= 1
            if d == 0: return text[i:j+1]
    return ''
def country(tag):
    i = data.find('\n\t' + tag + '={\n')
    return block(data, i) if i >= 0 else ''
out = {'date': re.search(r'^date=([0-9.]+)', data, re.M).group(1),
       'player': (re.search(r'^player="([A-Z]{3})"', data, re.M) or [None,None])[1]}
for tag in ('FRA','BRI','ENG','PRO','SAV','BUR','CAS'):
    b = country(tag)
    if not b: continue
    f = lambda n: (re.search(n + r'=([^\s}]+)', b) or [None,None])[1] if re.search(n + r'=([^\s}]+)', b) else None
    out[tag] = {'treasury': f('treasury'), 'income': f('estimated_monthly_income'), 'overlord': f('overlord'),
                'prestige': f('prestige'), 'gp_score': f('great_power_score')}
subj = []
for tag in ('BRI','ENG','PRO','SAV','BUR','CAS','LOR','AMG','AUV','BOU','FOI','ORL'):
    b = country(tag)
    m = re.search(r'overlord="([A-Z]{3})"', b) if b else None
    if m: subj.append((tag, m.group(1)))
out['subjects'] = subj
wars = []
for m in re.finditer(r'\nactive_war=\{', data):
    w = block(data, m.start())
    wars.append(re.findall(r'(?:add_attacker|add_defender)="([A-Z]{3})"', w))
out['wars'] = wars
out['alliances'] = [(m.group(1), m.group(2)) for m in re.finditer(r'alliance=\{ first="([A-Z]{3})" second="([A-Z]{3})"', data)][:20]
print(json.dumps(out, ensure_ascii=False, indent=1))
open(r'work/reports/diplomacy-unified-20261028/fixture-111-facts.json','w',encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
