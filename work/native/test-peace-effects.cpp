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

    std::printf("{\"passed\":%s,\"checks\":%u,\"failures\":%u,\"native_calls\":false}\n",
        failures?"false":"true",checks,failures);
    return failures?1:0;
}
