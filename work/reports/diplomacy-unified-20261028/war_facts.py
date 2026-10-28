import re, json
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
wars = []
for m in re.finditer(r'\nactive_war=\{', data):
    w = block(data, m.start())
    wars.append(w)
print('active war count', len(wars))
for w in wars:
    tags = re.findall(r'(?:add_attacker|add_defender)="([A-Z]{3})"', w)
    print('war tags', tags)
    print('name/date head', w[:120].encode('ascii','replace').decode())
    # leaders? find attacker/defender blocks
    for key in ('attacker','defender','war_goal','start_date'):
        i = w.find(key + '=')
        print(key, w[i:i+200].encode('ascii','replace').decode() if i>=0 else None)
open(r'work/reports/diplomacy-unified-20261028/live-active-wars.json','w',encoding='utf-8').write(json.dumps(wars, ensure_ascii=False, indent=1))
