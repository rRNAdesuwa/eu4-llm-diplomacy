"""Freeze one user-authorized integration plan; never publishes or opens EU4."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/runtime/tag31-integration-20261012'

# Paired cancellation follows its start; existing relationships are preferred.
# Every action occurs exactly once, including historical successes solely in
# the user's explicitly authorized final integration pass.
LANES = '''
improve_relations FRA POR
build_spy_network FRA UTR
curry_favors FRA NAV
counterespionage FRA ENG
support_heir FRA POL
annex_vassal POL MAZ
integrate_union DAN NOR
royal_marriage FRA POR
guarantee FRA SAV
offer_military_access FRA BRI
ask_military_access POR BRI
offer_fleet_basing_rights POR BRI
ask_fleet_basing_rights FRA POR
infiltrate_administration FRA ENG
embargo FRA ENG
steer_trade FRA BRI
offer_alliance FRA SAV
offer_vassalization FRA NAV
form_coalition FRA SAV
support_independence POR HOL
ask_support_independence SWE FRA
trade_favors_for_gold FRA NAV
trade_favors_for_men FRA NAV
trade_favors_for_sailors FRA NAV
trade_favors_for_trust FRA NAV
trade_favors_for_war_prep FRA NAV
trade_favors_for_heir FRA NAV
insult FRA ENG
warn FRA BUR
corrupt_officials FRA POR
sabotage_recruitment FRA NAV
sabotage_reputation FRA SCO
slander_merchants FRA BRI
sow_discontent FRA SAV
agitate_for_liberty FRA HOL
justify_trade_conflict FRA ENG
knowledge_sharing POR NAV
ask_knowledge_sharing BRI FRA
claim_throne SAV TRE
designate_march FRA ORL
ask_for_march MAZ POL
establish_tributary FRA UTR
ask_to_be_tributary SAV FRA
convert_tributary_to_vassal DAN DTT
invite_to_trade_league VEN UTR
request_to_join_trade_league BRI GEN
invite_to_federation HUR IRO
request_to_join_federation CHR HUR
join_coalition POR SAV
stop_improving_relations FRA POR
stop_building_spy_network FRA UTR
stop_currying_favors FRA NAV
stop_counterespionage FRA ENG
stop_supporting_heir FRA POL
cancel_annexation POL MAZ
cancel_integration DAN NOR
break_marriage LIT BLO
revoke_guarantee FRA SCO
revoke_military_access FRA BRI
cancel_military_access POR BRI
revoke_fleet_basing_rights POR BRI
cancel_fleet_basing_rights FRA POR
cancel_infiltration FRA ENG
revoke_embargo FRA ENG
cancel_steer_trade FRA BRI
cancel_subsidies FRA POR
cancel_trade_power_transfer SWE DAN
cancel_offered_independence_support FRA HOL
cancel_requested_independence_support SWE ENG
dissolve_alliance FRA SCO
cancel_vassalization POL MAZ
cancel_tributary DAN LAU
revoke_march FRA ORL
leave_coalition FRA SAV
kick_from_trade_league VEN UTR
leave_trade_league BRI GEN
kick_from_federation HUR IRO
leave_federation CHR HUR
abandon_union BUR BRB
fabricate_ottoman_invasion_cb FRA ENG
fabricate_spread_the_true_faith_cb FRA BUR
fabricate_tributary_cb FRA SAV
send_royal_ambassador FRA POR
heathen_royal_marriage POR NAV
sell_indulgence FRA BRI
mam_export_grain FRA POR
mam_sponsor_hajj FRA NAV
share_modern_ideas FRA SAV
request_access_to_modern_ideas BRI FRA
steal_modern_ideas FRA BUR
invite_to_zoroastrian_community FRA SAV
invite_into_cultural_sphere_of_influence FRA BRI
join_cultural_sphere_of_influence NAV POR
remove_them_from_cultural_sphere_of_influece FRA BRI
leave_the_cultural_sphere_of_influece NAV POR
create_pronoia FRA AMG
make_pronoia_inheritable FRA AMG
release_pronia FRA AMG
create_soyurghal FRA AUV
release_soyurghal FRA AUV
promote_appanage_heir FRA BOU
create_european_colony FRA FOI
promote_vassal_to_eyalet FRA ORL
call_eyalet_into_wars FRA ORL
reign_in_eyalet FRA ORL
grant_autonomy_to_core_eyalet FRA ORL
convert_to_core_personal_union DAN SWE
grant_war_rights DAN SWE
revoke_war_rights DAN SWE
offer_protectorate FRA UTR
call_trade_protectorate_into_wars FRA UTR
dissolve_protectorate FRA UTR
request_protectorate BRI POR
release_nahuatl_tributary DAN DTT
demand_sacrifices FRA SAV
promote_primary_culture FRA BOU
elevate_influenced_country_to_vassal FRA BRI
incorporate_vassal FRA BOU
select_rival FRA BUR
remove_rival FRA ENG
'''


def main():
    config = json.loads((ROOT/'bridge/tag_actions_1375_v31.json').read_text('utf-8'))
    commands = [dict(request_id=f'tag31-final-{i:03d}-{a}', action=a, actor=b, target=c)
                for i, (a,b,c) in enumerate((line.split() for line in LANES.splitlines() if line.strip()),1)]
    assert len(commands) == len(config['actions']) == 120
    assert len({c['action'] for c in commands}) == 120
    assert {c['action'] for c in commands} == set(config['actions'])
    assert all(c['actor'] != c['target'] for c in commands)
    data = (json.dumps(commands, indent=2)+'\n').encode('ascii')
    with OUT.with_suffix('.commands.json').open('xb') as stream:
        stream.write(data)
    report = {
        'purpose':'one_final_integration_pass', 'publishes':False,
        'user_authorization':'Complete TAG-only diplomacy first, then one final test; no repeated successful development tests.',
        'actions':120, 'unique_actions':120, 'human_player':'FRA',
        'commands_sha256':hashlib.sha256(data).hexdigest(),
        'baseline_save':'llm_diplomacy_1375_tag31_before.eu4',
        'baseline_save_sha256':'1f72be50b5d26534009137d240977ed4718e24a6b64eb73dc55a93c47252999a',
        'gameplay_effects_verified':False,
        'interpretation':'Native rejection is a tested unavailable command, not effect success. Dispatch alone is not AI acceptance.',
        'retry_policy':'Never resend dispatched or uncertain requests. A terminal host requires review before any unclaimed remaining commands.',
        'limitations':['Some native conditions remain hardcoded despite the testing Mod.',
                       'Absent starting relationships may make cancellation unavailable.',
                       'Accepted offers may require later days; no user-created fixtures are assumed.']}
    with OUT.with_suffix('.plan.json').open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
