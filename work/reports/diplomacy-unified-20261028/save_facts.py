import re, json, sys
p = r'C:/Users/14108/Documents/Paradox Interactive/Europa Universalis IV/save games/wp_undivert_effect.eu4'
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
out = {'date': re.search(r'^date=([0-9.]+)', data, re.M).group(1)}
for tag in ('FRA','BRI','SAV','PRO','ENG'):
    b = country(tag)
    f = lambda n: (re.search(n + r'=([^\s}]+)', b) or [None,None])[1] if re.search(n + r'=([^\s}]+)', b) else None
    out[tag] = {'treasury': f('treasury'), 'prestige': f('prestige'), 'income': f('estimated_monthly_income'),
                'overlord': f('overlord'), 'gp_score': f('great_power_score'), 'num_loans': f('num_of_loans'),
                'monarch': re.search(r'monarch=\{([^}]*)\}', b).group(1)[:120] if re.search(r'monarch=\{([^}]*)\}', b) else None}
out['alliances'] = [(m.group(1), m.group(2)) for m in re.finditer(r'alliance=\{ first="([A-Z]{3})" second="([A-Z]{3})"', data)]
wars = []
for m in re.finditer(r'\nactive_war=\{', data):
    w = block(data, m.start())
    if 'FRA' in w: wars.append(w[:160].replace('\n',' '))
out['wars_with_FRA'] = wars
out['rm_count_FRA'] = len(re.findall(r'royal_marriage=\{[^}]*FRA', data)) + len(re.findall(r'royal_marriage=\{[^}]*"FRA"', data))
out['hre_emperor'] = (re.search(r'emperor="([A-Z]{3})"', data) or [None,None])[1] if re.search(r'emperor="([A-Z]{3})"', data) else None
print(json.dumps(out, ensure_ascii=False, indent=1))
open(r'work/reports/diplomacy-unified-20261028/live-state-facts.json','w',encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
