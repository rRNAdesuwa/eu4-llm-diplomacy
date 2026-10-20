#include "peace-execution-wire.h"
#include <array>
#include <string>
#include <cstdio>

using namespace bridge::peace_execution_wire;
using Fields=std::array<std::string,32>;

static Fields fields(const char* action,const char* mask) {
    Fields value;
    value.fill("-");
    value[0]="EU4PEACE_EXEC10"; value[1]="1"; value[2]="r61_country_wire";
    value[3]=action; value[4]="FRA"; value[5]="ENG"; value[6]="56549064";
    value[7]="999999999999"; value[8]="war_0123456789abcdef_01234567";
    value[9]="demand"; value[10]="-1"; value[13]=mask;
    return value;
}

static ParseResult parse(const Fields& fields,PeaceExecutionRequest& output) {
    std::string wire;
    for (const auto& field:fields) { if (!wire.empty()) wire+=' '; wire+=field; }
    wire+='\n';
    return parse_request(wire.data(),wire.size(),output);
}

int main() {
    unsigned checks=0,failures=0;
    const auto check=[&](bool value,const char* label) {
        ++checks;
        if (!value) { ++failures; std::printf("failed:%s\n",label); }
    };
    PeaceExecutionRequest output;
    auto value=fields("force_vassalization","z"); value[25]="UTR"; value[29]="FRA";
    check(parse(value,output).ok() && output.selected_force_vassalization
        && std::string(output.vassal_country)=="UTR","force_target_and_beneficiary");
    value[29]="UTR";
    check(parse(value,output).error==ParseError::invalid_combination,"self_vassal_rejected");
    value=fields("release_nation","n"); value[23]="FLY"; value[24]="ENG";
    check(parse(value,output).ok() && output.selected_release_nation
        && std::string(output.release_nation_source)=="ENG","release_target_and_host");
    value[24]="-";
    check(!parse(value,output).ok(),"release_missing_host_rejected");
    value=fields("form_personal_union","u"); value[26]="LEI"; value[30]="FRA";
    check(parse(value,output).ok() && output.selected_form_personal_union,"union_bound");
    value=fields("grant_independence","i"); value[27]="ENG";
    check(parse(value,output).ok() && output.selected_grant_independence,"grant_native_payer_bound");
    value[27]="FRA";
    check(!parse(value,output).ok(),"grant_wrong_payer_rejected");
    value[9]="offer";
    check(parse(value,output).ok(),"grant_offer_reverses_payer");
    value=fields("full_annexation","e"); value[28]="UTR"; value[31]="FRA";
    check(parse(value,output).ok() && output.selected_full_annexation
        && output.province_count==0,"annex_country_is_not_wire_expanded_province_list");
    value[23]="FLY";
    check(!parse(value,output).ok(),"unselected_country_payload_rejected");
    value=fields("release_nation","nz"); value[23]="FLY"; value[24]="ENG";
    value[25]="UTR"; value[29]="FRA";
    check(parse(value,output).ok() && output.selected_release_nation
        && output.selected_force_vassalization,"two_country_families_bound");
    auto mixed=fields("release_nation","mn");
    mixed[10]="1000"; mixed[23]="PIC"; mixed[24]="ENG";
    check(parse(mixed,output).ok() && output.selected_release_nation
        && output.amount_raw==1000,"country_money_amount_bound");
    value[13]="zn";
    check(parse(value,output).error==ParseError::invalid_term_mask,"noncanonical_mask_rejected");
    value[13]="n";
    check(!parse(value,output).ok(),"mask_does_not_hide_second_country");
    value=fields("release_nation","z"); value[25]="UTR"; value[29]="FRA";
    check(!parse(value,output).ok(),"primary_action_must_be_selected");
    value=fields("full_annexation","e"); value[28]="UTR"; value[31]="FRA";
    value[0]="EU4PEACE_EXEC9";
    check(!parse(value,output).ok(),"legacy_version_cannot_carry_country_fields");
    std::printf("{\"passed\":%s,\"checks\":%u,\"failures\":%u}\n",
        failures?"false":"true",checks,failures);
    return failures?1:0;
}
