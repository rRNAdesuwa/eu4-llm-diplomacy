#include "peace-effects.h"
#include <cstdio>

using namespace bridge::peace_effects;
static unsigned checks=0,failures=0;
static void check(bool value,const char* name) {
    ++checks;
    if (!value) { ++failures; std::printf("failed:%s\n",name); }
}

int main() {
    State before{};
    before.complete=true; before.date_raw=100; before.country_count=3;
    before.countries[0]={11,20000};
    before.countries[1]={22,50000};
    before.countries[2]={33,7000};
    before.province_count=1; before.provinces[0]={177,11,33};
    State after=before;
    after.countries[0].treasury_raw-=10000;
    after.countries[1].treasury_raw+=6000;
    after.countries[2].treasury_raw+=4000;
    auto money=assess_money(before,after,11,10000);
    check(money.verified && money.paid_raw==10000 && money.total_credit_raw==10000,"native_allied_distribution");
    check(!assess_money(before,before,11,10000).verified,"refusal_has_no_payment");
    check(!assess_money(before,after,22,10000).verified,"payer_is_bound");
    check(!assess_money(before,after,11,1000).verified,"amount_is_bound");
    check(!assess_money(before,after,11,0).verified,"zero_is_not_money");
    auto changed=after; changed.countries[2].treasury_raw=6000;
    check(!assess_money(before,changed,11,10000).verified,"unrelated_debit_rejected");
    changed=after; changed.countries[2].treasury_raw-=1;
    check(!assess_money(before,changed,11,10000).verified,"missing_credit_rejected");
    changed=after; changed.countries[2].country=44;
    check(!assess_money(before,changed,11,10000).verified,"recipient_identity_changed");
    changed=after; changed.date_raw+=24;
    check(!assess_money(before,changed,11,10000).verified,"economic_tick_not_attributed");
    changed=after; changed.complete=false;
    check(!assess_money(before,changed,11,10000).verified,"incomplete_capture_not_verified");
    auto duplicate=before; duplicate.countries[2].country=22;
    changed=after; changed.countries[2].country=22;
    check(!assess_money(duplicate,changed,11,10000).verified,"duplicate_country_not_double_counted");
    changed=after; changed.provinces[0]={177,22,22};
    check(province_transferred(before,changed,0,22),"owner_and_control_transferred");
    check(!province_transferred(before,changed,0,33),"beneficiary_is_bound");
    check(!province_transferred(before,changed,1,22),"province_index_is_bounded");
    changed.provinces[0].id=178;
    check(!province_transferred(before,changed,0,22),"province_identity_is_bound");
    changed=after; changed.provinces[0]={177,22,33};
    check(province_transferred(before,changed,0,22),"third_country_occupation_can_remain");
    changed.provinces[0].controller=0;
    check(!province_transferred(before,changed,0,22),"unreadable_controller_is_incomplete");
    changed=after; changed.provinces[0]={177,11,11};
    check(!province_transferred(before,changed,0,11),"existing_ownership_is_not_transfer");

    // A same-date outcome may contain both a money transfer and a province
    // cession.  Keep the two proofs independent: a partial outcome must not
    // be promoted to an overall verified result.
    State combined=after;
    combined.provinces[0]={177,22,22};
    auto combined_money=assess_money(before,combined,11,10000);
    const bool combined_province=province_transferred(before,combined,0,22);
    check(combined.date_raw==before.date_raw && combined_money.verified
        && combined_province,"same_date_money_and_province_verified");

    State missing_money=combined;
    for (unsigned i=0;i<before.country_count;++i)
        missing_money.countries[i]=before.countries[i];
    auto missing_money_assessment=assess_money(before,missing_money,11,10000);
    const bool missing_money_verified=missing_money_assessment.verified
        && province_transferred(before,missing_money,0,22);
    check(!missing_money_assessment.verified,"combined_missing_money_rejected");
    check(!missing_money_verified,"missing_money_not_overall_verified");

    State missing_province=combined;
    missing_province.provinces[0]=before.provinces[0];
    auto missing_province_money=assess_money(before,missing_province,11,10000);
    const bool missing_province_verified=missing_province_money.verified
        && province_transferred(before,missing_province,0,22);
    check(missing_province_money.verified,"combined_missing_province_money_kept");
    check(!province_transferred(before,missing_province,0,22),
        "combined_missing_province_rejected");
    check(!missing_province_verified,"missing_province_not_overall_verified");

    // Prestige is reported from the two country snapshots.  The assessor
    // accepts ordinary changes without imposing a fixed delta.
    State prestige_before=before;
    prestige_before.concede_defeat_requested=true;
    for (unsigned i=0;i<prestige_before.country_count;++i) {
        prestige_before.countries[i].prestige_readable=true;
        prestige_before.countries[i].prestige_raw=100+static_cast<std::int32_t>(i);
    }
    prestige_before.countries[0].prestige_raw=120;
    prestige_before.countries[1].prestige_raw=-40;
    prestige_before.countries[2].prestige_raw=7000;
    State prestige_after=prestige_before;
    prestige_after.countries[0].prestige_raw=85;
    prestige_after.countries[1].prestige_raw=-65;
    auto prestige=assess_prestige(prestige_before,prestige_after,11,22);
    check(prestige.readable && prestige.conceding_before==120
        && prestige.conceding_after==85 && prestige.beneficiary_before==-40
        && prestige.beneficiary_after==-65,"prestige_normal_pair");

    // Values at the engine bounds remain readable; no fixed delta is assumed.
    State prestige_clamp_before=prestige_before;
    prestige_clamp_before.countries[0].prestige_raw=99999;
    prestige_clamp_before.countries[1].prestige_raw=-99999;
    State prestige_clamp_after=prestige_clamp_before;
    prestige_clamp_after.countries[0].prestige_raw=100000;
    prestige_clamp_after.countries[1].prestige_raw=-100000;
    auto prestige_clamp=assess_prestige(prestige_clamp_before,
        prestige_clamp_after,11,22);
    check(prestige_clamp.readable && prestige_clamp.conceding_after==100000
        && prestige_clamp.beneficiary_after==-100000,"prestige_clamp_values");

    // Rejection-side penalties are ordinary readable observations as well.
    State prestige_refusal_before=prestige_before;
    prestige_refusal_before.countries[0].prestige_raw=25000;
    prestige_refusal_before.countries[1].prestige_raw=50000;
    State prestige_refusal_after=prestige_refusal_before;
    prestige_refusal_after.countries[0].prestige_raw=15000;
    prestige_refusal_after.countries[1].prestige_raw=45000;
    auto prestige_refusal=assess_prestige(prestige_refusal_before,
        prestige_refusal_after,11,22);
    check(prestige_refusal.readable && prestige_refusal.conceding_after==15000
        && prestige_refusal.beneficiary_after==45000
        && prestige_refusal.conceding_before-prestige_refusal.conceding_after==10000
        && prestige_refusal.beneficiary_before-prestige_refusal.beneficiary_after==5000,
        "prestige_refusal_penalties_readable");

    auto prestige_changed=prestige_after;
    prestige_changed.date_raw+=1;
    check(!assess_prestige(prestige_before,prestige_changed,11,22).readable,
        "prestige_date_changed_rejected");
    prestige_changed=prestige_after;
    prestige_changed.countries[2].country=44;
    check(!assess_prestige(prestige_before,prestige_changed,11,22).readable,
        "prestige_identity_changed_rejected");

    State prestige_duplicate_before=prestige_before;
    prestige_duplicate_before.countries[2]=prestige_duplicate_before.countries[1];
    State prestige_duplicate_after=prestige_after;
    prestige_duplicate_after.countries[2]=prestige_duplicate_after.countries[1];
    check(same_observation_context(prestige_duplicate_before,
        prestige_duplicate_after),"prestige_duplicate_context_same");
    check(!assess_prestige(prestige_duplicate_before,prestige_duplicate_after,
        11,22).readable,"prestige_duplicate_endpoint_rejected");

    State prestige_missing_before=prestige_before;
    prestige_missing_before.country_count=2;
    prestige_missing_before.countries[1]=prestige_before.countries[2];
    State prestige_missing_after=prestige_after;
    prestige_missing_after.country_count=2;
    prestige_missing_after.countries[1]=prestige_after.countries[2];
    check(!assess_prestige(prestige_missing_before,prestige_missing_after,
        11,22).readable,"prestige_missing_endpoint_rejected");

    prestige_changed=prestige_after;
    prestige_changed.countries[0].prestige_raw=100001;
    check(!assess_prestige(prestige_before,prestige_changed,11,22).readable,
        "prestige_upper_bound_rejected");
    prestige_changed=prestige_after;
    prestige_changed.countries[1].prestige_raw=-100001;
    check(!assess_prestige(prestige_before,prestige_changed,11,22).readable,
        "prestige_lower_bound_rejected");
    prestige_changed=prestige_after;
    prestige_changed.countries[0].prestige_readable=false;
    check(!assess_prestige(prestige_before,prestige_changed,11,22).readable,
        "prestige_unreadable_rejected");
    prestige_changed=prestige_after;
    prestige_changed.complete=false;
    check(!assess_prestige(prestige_before,prestige_changed,11,22).readable,
        "prestige_incomplete_rejected");
    prestige_changed=prestige_after;
    prestige_changed.concede_defeat_requested=false;
    auto prestige_without_c=assess_prestige(prestige_before,prestige_changed,
        11,22);
    check(!prestige_without_c.readable && prestige_without_c.conceding_before==0
        && prestige_without_c.beneficiary_after==0,
        "prestige_without_c_request_rejected");

    State reparations_before=before;
    reparations_before.reparations_requested=true;
    reparations_before.reparations={11,22,90,130,false,false,true};
    State reparations_after=reparations_before;
    reparations_after.reparations={11,22,100,130,true,true,true};
    check(same_observation_context(reparations_before,reparations_after),
        "reparations_endpoints_share_context");
    check(reparations_established(reparations_before,reparations_after,11,22),
        "new_reparations_relation_established");

    auto reparations_changed=reparations_after;
    reparations_changed.reparations.start_date_raw=1;
    reparations_changed.reparations.end_date_raw=200;
    reparations_changed.reparations.active=false;
    check(same_observation_context(reparations_before,reparations_changed),
        "reparations_dynamic_fields_not_context");

    reparations_changed=reparations_after;
    reparations_changed.reparations_requested=false;
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "missing_reparations_request_rejected");
    check(!reparations_established(reparations_before,reparations_after,22,11),
        "wrong_reparations_direction_rejected");
    reparations_changed=reparations_after;
    reparations_changed.reparations.claimant=33;
    check(!same_observation_context(reparations_before,reparations_changed),
        "requested_reparations_endpoint_changed_rejected");
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "wrong_reparations_endpoint_rejected");

    reparations_changed=reparations_after;
    reparations_changed.reparations.start_date_raw=101;
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "reparations_date_before_start_rejected");
    reparations_changed=reparations_after;
    reparations_changed.reparations.end_date_raw=100;
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "reparations_date_at_end_rejected");

    reparations_changed=reparations_after;
    reparations_changed.reparations.complete=false;
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "incomplete_after_reparations_rejected");
    reparations_changed=reparations_before;
    reparations_changed.reparations.complete=false;
    check(!reparations_established(reparations_changed,reparations_after,11,22),
        "incomplete_before_reparations_rejected");
    reparations_changed=reparations_after;
    reparations_changed.date_raw+=1;
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "reparations_non_same_day_rejected");
    reparations_changed=reparations_after;
    reparations_changed.reparations.active=false;
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "reparations_after_inactive_rejected");
    reparations_changed=reparations_before;
    reparations_changed.reparations.active=true;
    check(!reparations_established(reparations_changed,reparations_after,11,22),
        "reparations_before_active_rejected");
    reparations_changed=reparations_after;
    reparations_changed.reparations.present=false;
    check(!reparations_established(reparations_before,reparations_changed,11,22),
        "reparations_missing_after_relation_rejected");
    check(!reparations_established(reparations_before,reparations_after,0,22),
        "zero_reparations_payer_rejected");
    check(!reparations_established(reparations_before,reparations_after,11,0),
        "zero_reparations_claimant_rejected");
    check(!reparations_established(reparations_before,reparations_after,11,11),
        "same_reparations_endpoints_rejected");

    State trade_new_before=before;
    check(TradePowerState{}.amount_scale==1000,
        "trade_power_default_amount_scale");
    trade_new_before.trade_power_requested=true;
    trade_new_before.trade_power={11,22,90,-1,0,1000,false,false,true};
    State trade_new_after=trade_new_before;
    trade_new_after.trade_power={11,22,100,-1,250,1000,true,true,true};
    check(same_observation_context(trade_new_before,trade_new_after),
        "trade_power_endpoints_share_context");
    check(trade_power_established(trade_new_before,trade_new_after,11,22),
        "new_trade_power_relation_established");

    State trade_voluntary_before=before;
    trade_voluntary_before.trade_power_requested=true;
    trade_voluntary_before.trade_power={11,22,90,-1,250,1000,true,false,true};
    State trade_voluntary_after=trade_voluntary_before;
    trade_voluntary_after.trade_power.peace_treaty=true;
    check(trade_power_established(trade_voluntary_before,trade_voluntary_after,11,22),
        "voluntary_trade_power_relation_established");

    State trade_unchanged_before=before;
    trade_unchanged_before.trade_power_requested=true;
    trade_unchanged_before.trade_power={11,22,90,-1,250,1000,true,true,true};
    State trade_unchanged_after=trade_unchanged_before;
    check(same_observation_context(trade_unchanged_before,trade_unchanged_after),
        "unchanged_trade_power_context");
    check(!trade_power_established(trade_unchanged_before,trade_unchanged_after,11,22),
        "unchanged_trade_power_rejected");

    check(!trade_power_established(trade_new_before,trade_new_after,22,11),
        "wrong_trade_power_direction_rejected");
    check(!trade_power_established(trade_new_before,trade_new_after,0,22),
        "zero_trade_power_source_rejected");
    check(!trade_power_established(trade_new_before,trade_new_after,11,0),
        "zero_trade_power_beneficiary_rejected");

    auto trade_changed=trade_new_after;
    trade_changed.trade_power_requested=false;
    check(!same_observation_context(trade_new_before,trade_changed),
        "missing_trade_power_request_context_rejected");
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "missing_trade_power_request_rejected");
    trade_changed=trade_new_after;
    trade_changed.trade_power.source=33;
    check(!same_observation_context(trade_new_before,trade_changed),
        "changed_trade_power_source_context_rejected");
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "changed_trade_power_source_rejected");

    trade_changed=trade_new_after;
    trade_changed.trade_power.present=false;
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "missing_trade_power_after_relation_rejected");
    trade_changed=trade_new_after;
    trade_changed.trade_power.peace_treaty=false;
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "missing_trade_power_peace_treaty_rejected");
    trade_changed=trade_new_after;
    trade_changed.trade_power.amount_raw=0;
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "zero_trade_power_amount_rejected");
    trade_changed=trade_new_after;
    trade_changed.trade_power.amount_scale=0;
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "zero_trade_power_scale_rejected");

    trade_changed=trade_new_after;
    trade_changed.complete=false;
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "incomplete_after_trade_power_capture_rejected");
    trade_changed=trade_new_after;
    trade_changed.trade_power.complete=false;
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "incomplete_after_trade_power_relation_rejected");
    trade_changed=trade_new_before;
    trade_changed.trade_power.complete=false;
    check(!trade_power_established(trade_changed,trade_new_after,11,22),
        "incomplete_before_trade_power_relation_rejected");
    trade_changed=trade_new_after;
    trade_changed.trade_power.start_date_raw=101;
    check(!trade_power_established(trade_new_before,trade_changed,11,22),
        "trade_power_date_before_start_rejected");

    // Annul rows retain the requested direction and the native relation's
    // actual dates.  A new row proves settlement even when the engine keeps
    // its open-ended end-date sentinel.
    constexpr std::int32_t kAnnulSentinel=0x29c77f8;
    State annul_before=before;
    annul_before.annul_treaties_requested=true;
    annul_before.annul_count=2;
    annul_before.annul_treaties[0]={11,22,90,kAnnulSentinel,false,true,true};
    annul_before.annul_treaties[1]={11,33,90,kAnnulSentinel,false,true,true};
    State annul_after=annul_before;
    annul_after.annul_treaties[0]={11,22,100,kAnnulSentinel,true,false,true};
    annul_after.annul_treaties[1]={11,33,100,kAnnulSentinel,true,false,true};
    check(annul_context_pairs_valid(annul_before)
        && annul_context_pairs_valid(annul_after),"annul_unique_pair_context");
    check(same_observation_context(annul_before,annul_after),
        "annul_pairs_share_context");
    check(annul_treaties_established(annul_before,annul_after),
        "annul_new_relations_established");
    check(annul_state_values_readable(annul_after.annul_treaties[0]),
        "annul_after_values_readable");

    // A pre-existing voluntary relation can still be replaced by the
    // requested treaty; only an observed date change is needed.
    State annul_date_before=annul_before;
    annul_date_before.annul_treaties[0].present=true;
    annul_date_before.annul_treaties[0].alliance_present=true;
    annul_date_before.annul_treaties[0].start_date_raw=90;
    annul_date_before.annul_treaties[0].end_date_raw=100;
    State annul_date_after=annul_date_before;
    annul_date_after.annul_treaties[0].start_date_raw=100;
    annul_date_after.annul_treaties[0].end_date_raw=kAnnulSentinel;
    annul_date_after.annul_treaties[0].alliance_present=false;
    check(annul_treaty_established(annul_date_before.annul_treaties[0],
        annul_date_after.annul_treaties[0],annul_date_after.date_raw),
        "annul_existing_relation_date_changed");
    check(annul_date_after.annul_treaties[0].end_date_raw==kAnnulSentinel,
        "annul_end_sentinel_is_preserved");

    State annul_changed=annul_after;
    annul_changed.annul_treaties[0].present=false;
    check(!annul_treaties_established(annul_before,annul_changed),
        "annul_missing_after_relation_rejected");
    annul_changed=annul_after;
    annul_changed.annul_treaties[0].alliance_present=true;
    check(!annul_treaties_established(annul_before,annul_changed),
        "annul_alliance_after_rejected");
    annul_changed=annul_after;
    annul_changed.annul_treaties[0].start_date_raw=101;
    check(!annul_treaties_established(annul_before,annul_changed),
        "annul_date_before_start_rejected");
    annul_changed=annul_after;
    annul_changed.annul_treaties[0].complete=false;
    check(!annul_treaties_established(annul_before,annul_changed),
        "annul_incomplete_after_rejected");
    annul_changed=annul_after;
    annul_changed.annul_treaties[0].country=22;
    check(!same_observation_context(annul_before,annul_changed),
        "annul_country_direction_changed_rejected");
    check(!annul_treaty_established(annul_before.annul_treaties[0],
        AnnulState{22,11,100,kAnnulSentinel,true,false,true},100),
        "annul_reverse_record_direction_rejected");

    State annul_duplicate=annul_before;
    annul_duplicate.annul_treaties[1]=annul_duplicate.annul_treaties[0];
    check(!annul_context_pairs_valid(annul_duplicate),
        "annul_duplicate_pair_rejected");
    check(!same_observation_context(annul_before,annul_duplicate),
        "annul_duplicate_context_rejected");
    State annul_missing=annul_after;
    annul_missing.annul_count=1;
    check(!same_observation_context(annul_before,annul_missing),
        "annul_missing_pair_rejected");
    State annul_zero=annul_before;
    annul_zero.annul_treaties[1].partner=0;
    check(!annul_context_pairs_valid(annul_zero),"annul_zero_partner_rejected");
    State annul_changed_context=annul_after;
    annul_changed_context.date_raw+=1;
    check(!annul_treaties_established(annul_before,annul_changed_context),
        "annul_date_context_changed_rejected");
    State annul_no_request=annul_after;
    annul_no_request.annul_treaties_requested=false;
    annul_no_request.annul_count=0;
    check(!annul_treaties_established(annul_before,annul_no_request),
        "annul_without_request_rejected");

    // H/S/F use the native term's payer as the affected country and claimant
    // as the beneficiary.  These fixtures model the exact country context
    // while allowing the engine to clamp prestige or power values freely.
    State special_before=before;
    special_before.humiliate_rival_requested=true;
    special_before.humiliate_rival_country=22;
    special_before.humiliate_rival_beneficiary=11;
    special_before.humiliate_rival.country=22;
    special_before.humiliate_rival.beneficiary=11;
    special_before.humiliate_rival.humiliated_index=-1;
    std::snprintf(special_before.humiliate_rival.country_tag,
        sizeof(special_before.humiliate_rival.country_tag),"FRA");
    std::snprintf(special_before.humiliate_rival.beneficiary_tag,
        sizeof(special_before.humiliate_rival.beneficiary_tag),"ENG");
    special_before.humiliate_rival.country_prestige_raw=850;
    special_before.humiliate_rival.beneficiary_prestige_raw=-125;
    special_before.humiliate_rival.values_readable=true;
    special_before.humiliate_rival.complete=true;
    State special_after=special_before;
    special_after.humiliate_rival.humiliated_index=0;
    special_after.humiliate_rival.humiliated=true;
    special_after.humiliate_rival.country_prestige_raw=777;
    special_after.humiliate_rival.beneficiary_prestige_raw=-250;
    check(same_observation_context(special_before,special_after),
        "humiliate_same_context");
    check(humiliate_rival_established(special_before,special_after,22,11),
        "humiliate_rival_established");
    auto special_changed=special_after;
    special_changed.humiliate_rival.humiliated=false;
    special_changed.humiliate_rival.humiliated_index=-1;
    check(!humiliate_rival_established(special_before,special_changed,22,11),
        "humiliate_missing_after_consequence_rejected");
    special_changed=special_after;
    special_changed.humiliate_rival_beneficiary=33;
    check(!same_observation_context(special_before,special_changed),
        "humiliate_beneficiary_changed_rejected");
    check(!humiliate_rival_established(special_before,special_changed,22,11),
        "humiliate_wrong_beneficiary_rejected");
    special_changed=special_after;
    special_changed.humiliate_rival.country_prestige_raw=100001;
    check(!humiliate_rival_established(special_before,special_changed,22,11),
        "humiliate_prestige_out_of_range_rejected");
    special_changed=special_after;
    special_changed.humiliate_rival.values_readable=false;
    check(!humiliate_rival_established(special_before,special_changed,22,11),
        "humiliate_unreadable_values_rejected");
    special_changed=special_after;
    special_changed.date_raw+=1;
    check(!humiliate_rival_established(special_before,special_changed,22,11),
        "humiliate_date_changed_rejected");
    special_changed=special_after;
    special_changed.humiliate_rival_requested=false;
    check(!humiliate_rival_established(special_before,special_changed,22,11),
        "humiliate_missing_request_rejected");

    State show_before=before;
    show_before.show_strength_requested=true;
    show_before.show_strength_country=22;
    show_before.show_strength_beneficiary=11;
    show_before.show_strength.country=22;
    show_before.show_strength.beneficiary=11;
    show_before.show_strength.humiliated_index=-1;
    std::snprintf(show_before.show_strength.country_tag,
        sizeof(show_before.show_strength.country_tag),"FRA");
    std::snprintf(show_before.show_strength.beneficiary_tag,
        sizeof(show_before.show_strength.beneficiary_tag),"ENG");
    show_before.show_strength.country_prestige_raw=99999;
    show_before.show_strength.beneficiary_prestige_raw=-99999;
    show_before.show_strength.powers[0]=451;
    show_before.show_strength.powers[1]=269;
    show_before.show_strength.powers[2]=381;
    show_before.show_strength.powers_requested=73;
    show_before.show_strength.values_readable=true;
    show_before.show_strength.complete=true;
    State show_after=show_before;
    show_after.show_strength.humiliated_index=2;
    show_after.show_strength.humiliated=true;
    show_after.show_strength.country_prestige_raw=100000;
    show_after.show_strength.beneficiary_prestige_raw=-100000;
    show_after.show_strength.powers[0]=400;
    show_after.show_strength.powers[1]=300;
    show_after.show_strength.powers[2]=500;
    show_after.show_strength.powers_requested=73;
    check(show_strength_established(show_before,show_after,22,11),
        "show_strength_established_with_clamp");
    auto show_changed=show_after;
    show_changed.show_strength.humiliated=false;
    show_changed.show_strength.humiliated_index=-1;
    check(!show_strength_established(show_before,show_changed,22,11),
        "show_strength_missing_after_consequence_rejected");
    show_changed=show_after;
    show_changed.show_strength.powers[0]=1000000;
    check(show_strength_established(show_before,show_changed,22,11),
        "show_strength_power_delta_is_not_fixed");
    show_changed=show_after;
    show_changed.show_strength.beneficiary=33;
    check(!show_strength_established(show_before,show_changed,22,11),
        "show_strength_wrong_direction_rejected");
    show_changed=show_after;
    show_changed.show_strength.values_readable=false;
    check(!show_strength_established(show_before,show_changed,22,11),
        "show_strength_unreadable_values_rejected");
    show_changed=show_after;
    show_changed.show_strength.powers_requested=-1;
    check(!show_strength_established(show_before,show_changed,22,11),
        "show_strength_negative_request_rejected");
    show_changed=show_after;
    show_changed.show_strength.country_prestige_raw=-100001;
    check(!show_strength_established(show_before,show_changed,22,11),
        "show_strength_prestige_out_of_range_rejected");
    show_changed=show_after;
    show_changed.complete=false;
    check(!show_strength_established(show_before,show_changed,22,11),
        "show_strength_incomplete_after_rejected");
    show_changed=show_after;
    show_changed.show_strength_requested=false;
    check(!show_strength_established(show_before,show_changed,22,11),
        "show_strength_missing_request_rejected");

    State religion_before=before;
    religion_before.force_religion_requested=true;
    religion_before.force_religion_country=22;
    religion_before.force_religion_beneficiary=11;
    religion_before.force_religion.country=22;
    religion_before.force_religion.beneficiary=11;
    std::snprintf(religion_before.force_religion.religion,
        sizeof(religion_before.force_religion.religion),"catholic");
    std::snprintf(religion_before.force_religion.beneficiary_religion,
        sizeof(religion_before.force_religion.beneficiary_religion),"anglican");
    std::snprintf(religion_before.force_religion.capital_religion,
        sizeof(religion_before.force_religion.capital_religion),"catholic");
    religion_before.force_religion.values_readable=true;
    religion_before.force_religion.complete=true;
    State religion_after=religion_before;
    std::snprintf(religion_after.force_religion.religion,
        sizeof(religion_after.force_religion.religion),"anglican");
    std::snprintf(religion_after.force_religion.capital_religion,
        sizeof(religion_after.force_religion.capital_religion),"anglican");
    check(force_religion_established(religion_before,religion_after,22,11),
        "force_religion_established");
    auto religion_changed=religion_after;
    std::snprintf(religion_changed.force_religion.capital_religion,
        sizeof(religion_changed.force_religion.capital_religion),"catholic");
    check(!force_religion_established(religion_before,religion_changed,22,11),
        "force_religion_capital_mismatch_rejected");
    religion_changed=religion_after;
    std::snprintf(religion_changed.force_religion.religion,
        sizeof(religion_changed.force_religion.religion),"orthodox");
    check(!force_religion_established(religion_before,religion_changed,22,11),
        "force_religion_country_mismatch_rejected");
    religion_changed=religion_after;
    religion_changed.force_religion.values_readable=false;
    check(!force_religion_established(religion_before,religion_changed,22,11),
        "force_religion_unreadable_values_rejected");
    religion_changed=religion_after;
    religion_changed.force_religion_beneficiary=33;
    check(!force_religion_established(religion_before,religion_changed,22,11),
        "force_religion_wrong_direction_rejected");
    religion_changed=religion_after;
    religion_changed.date_raw+=1;
    check(!force_religion_established(religion_before,religion_changed,22,11),
        "force_religion_date_changed_rejected");
    religion_changed=religion_after;
    religion_changed.force_religion_requested=false;
    check(!force_religion_established(religion_before,religion_changed,22,11),
        "force_religion_missing_request_rejected");

    // A mixed observation keeps the three requested special terms tied to
    // the same date and endpoint pair while their concrete consequences are
    // assessed independently.
    State mixed_before=before;
    mixed_before.humiliate_rival_requested=true;
    mixed_before.humiliate_rival_country=22; mixed_before.humiliate_rival_beneficiary=11;
    mixed_before.humiliate_rival=special_before.humiliate_rival;
    mixed_before.show_strength_requested=true;
    mixed_before.show_strength_country=22; mixed_before.show_strength_beneficiary=11;
    mixed_before.show_strength=show_before.show_strength;
    mixed_before.force_religion_requested=true;
    mixed_before.force_religion_country=22; mixed_before.force_religion_beneficiary=11;
    mixed_before.force_religion=religion_before.force_religion;
    State mixed_after=mixed_before;
    mixed_after.humiliate_rival=special_after.humiliate_rival;
    mixed_after.show_strength=show_after.show_strength;
    mixed_after.force_religion=religion_after.force_religion;
    check(same_observation_context(mixed_before,mixed_after),
        "mixed_special_terms_share_context");
    check(humiliate_rival_established(mixed_before,mixed_after,22,11)
        && show_strength_established(mixed_before,mixed_after,22,11)
        && force_religion_established(mixed_before,mixed_after,22,11),
        "mixed_special_terms_established_independently");
    mixed_after.show_strength_country=33;
    check(!same_observation_context(mixed_before,mixed_after),
        "mixed_special_direction_change_rejected");

    // Core effects report the province owner/controller and the requested
    // core-vector membership independently.  Return Core does not prescribe
    // whether the old core remains; Revoke Core does require the requested
    // core to disappear after settlement.
    State return_before=before;
    return_before.return_core_requested=true;
    return_before.return_core={true,1,{{177,44,11,33,true,true}},true};
    State return_after=return_before;
    return_after.return_core.rows[0].owner=44;
    return_after.return_core.rows[0].core_owner_present=false;
    check(same_observation_context(return_before,return_after),
        "return_core_context_preserves_target");
    check(core_effect_established(return_before,return_after,true),
        "return_core_owner_transition_verified");
    auto return_unchanged=return_after;
    return_unchanged.return_core.rows[0]=return_before.return_core.rows[0];
    check(!core_effect_established(return_before,return_unchanged,true),
        "return_core_requires_before_after_change");
    auto return_wrong_target=return_after;
    return_wrong_target.return_core.rows[0].target_core_owner=22;
    check(!same_observation_context(return_before,return_wrong_target),
        "return_core_target_change_rejected");

    State revoke_before=before;
    revoke_before.revoke_core_requested=true;
    revoke_before.revoke_core={true,1,{{177,22,11,33,true,true}},true};
    State revoke_after=revoke_before;
    revoke_after.revoke_core.rows[0].core_owner_present=false;
    check(same_observation_context(revoke_before,revoke_after),
        "revoke_core_context_preserves_target");
    check(core_effect_established(revoke_before,revoke_after,false),
        "revoke_core_membership_removed_verified");
    auto revoke_missing=revoke_after;
    revoke_missing.revoke_core.rows[0].core_owner_present=true;
    check(!core_effect_established(revoke_before,revoke_missing,false),
        "revoke_core_membership_retained_rejected");
    auto revoke_unreadable=revoke_after;
    revoke_unreadable.revoke_core.rows[0].complete=false;
    check(!core_effect_established(revoke_before,revoke_unreadable,false),
        "revoke_core_unreadable_after_rejected");

    std::printf("{\"passed\":%s,\"checks\":%u,\"failures\":%u,\"native_calls\":false}\n",
        failures?"false":"true",checks,failures);
    return failures?1:0;
}
