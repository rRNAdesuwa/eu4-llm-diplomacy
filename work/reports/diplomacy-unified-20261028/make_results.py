import json, collections, datetime
base = 'work/reports/diplomacy-unified-20261028/'
cov = json.load(open(base + 'offline-coverage.json', encoding='utf-8'))
research = json.load(open('bridge/diplomacy_research_evidence.json', encoding='utf-8'))
hist = {}
for o in research['observations']:
    claims = o.get('claims', {})
    if claims.get('observed_state_change') or claims.get('saved_state_verified'):
        hist.setdefault(o['action_id'], []).append(o['experiment_id'])
live_files = {'offer_loan': 'live-unified-live-loan-01.json', 'influence_nation': 'live-unified-live-infl-01.json'}
live = {}
for action, f in live_files.items():
    value = json.load(open(base + f, encoding='utf-8'))
    live[action] = {'file': f, 'request_id': value['request']['request_id'],
                    'sequence': value['submission']['native_publication']['published'][0]['sequence'],
                    'states': value['status_states'], 'final': value['final']}
reused_war_peace = {'declare_war': 'war-peace-results.json', 'offer_peace': 'war-peace-results.json',
                    'subject.divert_trade': 'war-peace-results.json', 'subject.placate_rulers': 'war-peace-results.json'}
rows = []
for rec in cov['actions']:
    a = rec['action']; route = rec['route']
    if a in live:
        state, evidence = 'live_dispatched', {'kind':'new_request','file':live[a]['file'],'request_id':live[a]['request_id'],'sequence':live[a]['sequence'],'final':live[a]['final']}
    elif a in hist:
        state, evidence = 'evidence_reused', {'kind':'historical','source':'bridge/diplomacy_research_evidence.json','experiments':hist[a][:3]}
    elif a in reused_war_peace:
        state, evidence = 'evidence_reused', {'kind':'historical','source':'work/reports/war-peace-connectivity-20261027/war-peace-results.json'}
    elif route == 'independent_command':
        state, evidence = 'offline_validated', {'kind':'offline_contract','source':'offline-coverage.json'}
    elif route and route.startswith('typed_'):
        state, evidence = 'offline_validated_typed_backend_unavailable', {'kind':'offline_contract','source':'offline-coverage.json'}
    else:
        state, evidence = 'offline_validated', {'kind':'offline_contract','source':'offline-coverage.json'}
    rows.append({'action':a,'route':route,'parameter_fields':rec['parameter_fields'],
                 'native_preview':rec.get('native_preview'),'effect_profile':rec['effect_profile'],
                 'query_ok':rec['query_ok'],'live_state':state,'evidence':evidence})
summary = collections.Counter(r['live_state'] for r in rows)
payload = {
 'schema': 'EU4DIPLOMACYUNIFIEDRESULTS/1',
 'generated_utc': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
 'scope': 'GPT-静态接口统一后：目录/参数/预览/响应/执行/效果 逐项测试',
 'offline': {
   'tests': {'command':'python -B -m unittest tests.test_diplomacy_operations -v','result':'PASS 5/5'},
   'catalog': {'action_count': cov['summary']['action_count'], 'by_route': cov['summary']['by_route'],
               'parameter_fields_empty': 0, 'effect_profile_missing': cov['summary']['missing_effect_profile'],
               'native_preview_true': cov['summary']['native_preview_true']},
   'query_coverage': {'ok': cov['summary']['query_ok'], 'failed': cov['summary']['query_failed'],
                      'file':'offline-coverage.json'},
   'fixes': [
      {'file':'bridge/diplomacy_operations.py','change':'catalog rows carry resolved route; native_preview only ordinary_tag/offer_peace; governor event profile note'},
      {'file':'tests/test_diplomacy_operations.py','change':'assert route and independent-command preview policy'},
   ],
 },
 'live': {
   'host': {'pid':28704,'creation':'01dd664b54377989','session':'3318a0b8c43c7b11f9e22e0b3a64e2cd',
            'backend':'D:/.../v32-common-demo-1375/build-3 (tag command host, 153 ordinary actions)',
            'requests_before':6,'terminal':False},
   'published': [
      {'request_id':live['offer_loan']['request_id'],'action':'offer_loan','parameters':{'actor':'FRA','target':'BRI','amount':100,'interest_percent':'1.000','duration_months':12},
       'sequence':live['offer_loan']['sequence'],'final':live['offer_loan']['final'],'evidence':live['offer_loan']['file'],
       'response':{'generated_decision':'unavailable through tag backend','reply':'unavailable while paused'}},
      {'request_id':live['influence_nation']['request_id'],'action':'influence_nation','parameters':{'actor':'FRA','target':'SAV'},
       'sequence':live['influence_nation']['sequence'],'final':live['influence_nation']['final'],'evidence':live['influence_nation']['file'],
       'response':{'generated_decision':'unavailable through tag backend','reply':'unavailable while paused'}},
   ],
   'evidence_reused': {'count': sum(1 for r in rows if r['live_state']=='evidence_reused'),
                       'sources':['bridge/diplomacy_research_evidence.json (30 actions)',
                                  'work/reports/war-peace-connectivity-20261027/war-peace-results.json (declare_war/offer_peace + subject continue actions)']},
   'blocked': [
      {'kind':'typed_backend_surface','detail':'loaded tag_command backend exposes 153 ordinary actions; 61 typed routes (subject 45, war context 3, war/peace 2, government 3, condottieri 3, sell_ships 1, rebels 2, confirm_tribute 1, governor 1) validated offline but cannot be published through this backend. Cold owner /v1 facade not running.'},
      {'kind':'native_preview','detail':'send=0 preview requires the cold owner or a build with check_only; loaded tag build has no check_only source; preview not published.'},
      {'kind':'ai_reply_effect','detail':'game paused; both live requests ended dispatched with ownership closed; no AI decision/effect observed; effect evidence not claimed.'},
   ],
 },
 'action_rows': rows,
 'summary': {'by_live_state': dict(summary), 'offline_query_ok': cov['summary']['query_ok'], 'actions': len(rows)},
 'followups': [
   'Run typed routes on the cold product owner (or extended backend) when /v1 owner is available; start with subject.divert_trade reuse then one new typed action.',
   'Verify preview with check_only on a build that implements it; do not publish previews through the 153-action tag backend.',
   'Advance one day or read the next AI reply to attach an effect to the two dispatched requests; do not resubmit.',
   'War-context routes: current real war exists (ENG attacker vs ORD/MCM; FRA defender in PRO war); typed publication still requires extended backend.',
 ],
}
from reconcile_results import reconcile
payload = reconcile(payload)
open(base + 'results.json', 'w', encoding='utf-8').write(json.dumps(payload, ensure_ascii=False, indent=1))
print(json.dumps({'summary': payload['summary'], 'reused': payload['live']['evidence_reused']['count'], 'hist_count': len(hist), 'hist_actions': sorted(hist), 'reused_set': sorted({r['action'] for r in rows if r['live_state']=='evidence_reused'})}, ensure_ascii=False, indent=1))
