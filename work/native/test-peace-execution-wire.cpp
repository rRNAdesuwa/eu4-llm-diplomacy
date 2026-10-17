#include "peace-execution-wire.h"

#include <cstdio>
#include <cstring>
#include <string>

namespace wire=bridge::peace_execution_wire;

static int failures=0;

#define CHECK(condition) do { \
    if (!(condition)) { \
        std::fprintf(stderr,"CHECK failed at %s:%d: %s\n",__FILE__,__LINE__,#condition); \
        ++failures; \
    } \
} while (false)

static wire::ParseResult parse(const char* text,wire::PeaceExecutionRequest& request) {
    return wire::parse_request(text,text?std::strlen(text):0,request);
}

static wire::ParseResult parse_bytes(const char* bytes,std::size_t length,
    wire::PeaceExecutionRequest& request) {
    return wire::parse_request(bytes,length,request);
}

static void expect_ok(const char* text,wire::PeaceExecutionRequest& request) {
    const wire::ParseResult result=parse(text,request);
    CHECK(result.ok());
    if (!result.ok())
        std::fprintf(stderr,"unexpected parse error: %s field=%zu\n",
            wire::parse_error_name(result.error),result.field);
}

static void expect_error(const std::string& text,wire::ParseError expected) {
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.error==expected);
    if (result.error!=expected)
        std::fprintf(stderr,"expected %s, got %s field=%zu\n",
            wire::parse_error_name(expected),wire::parse_error_name(result.error),result.field);
}

int main() {
    const char* war="war_0123456789abcdef_01234567";
    wire::PeaceExecutionRequest request{};

    const char* white=
        "EU4PEACE_EXEC1 123456789 r42_white_001 white_peace FRA ENG 14450101 223456789 "
        "war_0123456789abcdef_01234567 demand -1 - -\n";
    expect_ok(white,request);
    CHECK(request.white_peace);
    CHECK(!request.demand_ducats && !request.cede_province);
    CHECK(request.creation_epoch==123456789ull);
    CHECK(request.expiry_epoch_ms==223456789ull);
    CHECK(request.amount_raw==-1 && !request.selected_amount);
    CHECK(request.province_count==0 && !request.selected_provinces);
    CHECK(!request.selected_beneficiary);
    CHECK(std::strcmp(request.war_id,war)==0);

    const char* money=
        "EU4PEACE_EXEC1 123 r42_money demand_ducats FRA S4V 56465000 999 "
        "war_0123456789abcdef_01234567 demand 10000 177,12,3,4 FRA\n";
    expect_ok(money,request);
    CHECK(request.demand_ducats && request.selected_amount);
    CHECK(!request.white_peace && !request.cede_province);
    CHECK(request.amount_raw==10000);
    CHECK(request.province_count==4 && request.selected_provinces);
    CHECK(request.province_ids[0]==177 && request.province_ids[1]==12
        && request.province_ids[2]==3 && request.province_ids[3]==4);
    CHECK(request.selected_beneficiary && std::strcmp(request.beneficiary,"FRA")==0);

    const char* money_offer=
        "EU4PEACE_EXEC1 124 r42_money_offer demand_ducats FRA ENG 56465000 999 "
        "war_0123456789abcdef_01234567 offer 20000 177,12,3,4 SAV\n";
    expect_ok(money_offer,request);
    CHECK(!request.demand_direction && std::strcmp(request.direction,"offer")==0);
    CHECK(request.demand_ducats && request.selected_amount
        && request.amount_raw==20000);
    CHECK(request.province_count==4 && request.selected_provinces
        && request.province_ids[0]==177 && request.province_ids[1]==12
        && request.province_ids[2]==3 && request.province_ids[3]==4);
    CHECK(request.selected_beneficiary && std::strcmp(request.beneficiary,"SAV")==0);

    const char* money_only=
        "EU4PEACE_EXEC1 1 r42_money_only demand_ducats FRA ENG 0 2 "
        "war_0123456789abcdef_01234567 demand 100 - -\n";
    expect_ok(money_only,request);
    CHECK(request.amount_raw==100 && request.selected_amount);
    CHECK(request.province_count==0 && !request.selected_provinces);
    CHECK(!request.selected_beneficiary);

    const char* cede=
        "EU4PEACE_EXEC1 5 r42_cede cede_province FRA SAV 1 7 "
        "war_0123456789abcdef_01234567 demand 300 177,12,3,4 FRA\n";
    expect_ok(cede,request);
    CHECK(request.cede_province && !request.white_peace && !request.demand_ducats);
    CHECK(request.amount_raw==300 && request.selected_amount);
    CHECK(request.province_count==4);
    CHECK(request.province_ids[0]==177 && request.province_ids[1]==12
        && request.province_ids[2]==3 && request.province_ids[3]==4);
    CHECK(request.selected_beneficiary);

    const char* offer= 
        "EU4PEACE_EXEC1 6 r42_offer cede_province FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 offer 400 177,12,3,4 FRA\n";
    expect_ok(offer,request);
    CHECK(!request.demand_direction);
    CHECK(std::strcmp(request.direction,"offer")==0);
    CHECK(request.cede_province && request.selected_amount
        && request.amount_raw==400 && request.province_count==4
        && request.province_ids[0]==177 && request.province_ids[1]==12
        && request.province_ids[2]==3 && request.province_ids[3]==4);

    std::string sixteen=
        "EU4PEACE_EXEC1 5 r42_cede_16 cede_province FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 demand -1 ";
    for (int index=1;index<=16;++index) {
        if (index>1) sixteen.push_back(',');
        sixteen += std::to_string(index);
    }
    sixteen += " FRA\n";
    const wire::ParseResult sixteen_result=parse_bytes(
        sixteen.data(),sixteen.size(),request);
    CHECK(sixteen_result.ok());
    CHECK(request.province_count==16 && request.province_ids[0]==1
        && request.province_ids[15]==16);

    const char* cede_with_money=
        "EU4PEACE_EXEC1 5 r42_cede_money cede_province FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 demand 200 1 SAV\n";
    expect_ok(cede_with_money,request);
    CHECK(request.amount_raw==200 && request.selected_amount);
    CHECK(request.province_count==1 && request.province_ids[0]==1);
    CHECK(std::strcmp(request.beneficiary,"SAV")==0);

    const char* reparations_r= 
        "EU4PEACE_EXEC2 7 r48_reparations_r war_reparations FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 demand -1 - - r\n";
    expect_ok(reparations_r,request);
    CHECK(request.war_reparations && !request.white_peace
        && !request.demand_ducats && !request.cede_province);
    CHECK(request.selected_reparations && !request.selected_amount
        && !request.selected_provinces);
    CHECK(std::strcmp(request.term_mask,"r")==0);

    const char* reparations_offer=
        "EU4PEACE_EXEC2 8 r48_reparations_offer war_reparations FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 offer -1 - - r\n";
    expect_ok(reparations_offer,request);
    CHECK(!request.demand_direction && request.selected_reparations
        && std::strcmp(request.term_mask,"r")==0);

    const char* money_mr=
        "EU4PEACE_EXEC2 9 r48_money_mr demand_ducats FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 demand 100 - - mr\n";
    expect_ok(money_mr,request);
    CHECK(request.demand_ducats && request.selected_amount
        && request.amount_raw==100 && request.selected_reparations
        && !request.selected_provinces
        && std::strcmp(request.term_mask,"mr")==0);

    const char* province_pr=
        "EU4PEACE_EXEC2 10 r48_province_pr cede_province FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 demand -1 177 FRA pr\n";
    expect_ok(province_pr,request);
    CHECK(request.cede_province && !request.selected_amount
        && request.selected_provinces && request.province_count==1
        && request.selected_beneficiary && request.selected_reparations
        && std::strcmp(request.term_mask,"pr")==0);

    const char* combined_mpr=
        "EU4PEACE_EXEC2 11 r48_combined_mpr cede_province FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 offer 200 177,12 SAV mpr\n";
    expect_ok(combined_mpr,request);
    CHECK(!request.demand_direction && request.selected_amount
        && request.amount_raw==200 && request.selected_provinces
        && request.province_count==2 && request.selected_beneficiary
        && request.selected_reparations
        && std::strcmp(request.term_mask,"mpr")==0);

    const char* money_with_province=
        "EU4PEACE_EXEC2 12 r48_money_with_province demand_ducats FRA ENG 1 7 "
        "war_0123456789abcdef_01234567 demand 300 177 FRA mpr\n";
    expect_ok(money_with_province,request);
    CHECK(request.demand_ducats && request.selected_amount
        && request.selected_provinces && request.selected_reparations
        && std::strcmp(request.term_mask,"mpr")==0);

    const std::string valid_white(white);
    expect_error(std::string("EU4PEACE_EXEC0")+valid_white.substr(14),
        wire::ParseError::invalid_prefix);
    expect_error(valid_white.substr(0,valid_white.size()-1),
        wire::ParseError::missing_final_lf);
    expect_error(valid_white.substr(0,valid_white.size()-1)+"\r\n",
        wire::ParseError::crlf_rejected);
    std::string hidden_nul=valid_white;
    hidden_nul.insert(hidden_nul.size()-1,1,'\0');
    expect_error(hidden_nul,wire::ParseError::embedded_nul);
    std::string embedded_lf=valid_white;
    embedded_lf.insert(20,1,'\n');
    expect_error(embedded_lf,wire::ParseError::embedded_newline);
    expect_error(valid_white+"tail\n",wire::ParseError::embedded_newline);
    expect_error(std::string(513,'x')+"\n",wire::ParseError::wire_too_long);

    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 -\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC1  r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::empty_field);
    expect_error("EU4PEACE_EXEC1 18446744073709551616 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_creation_epoch);
    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA ENG 1 18446744073709551616 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_expiry_epoch_ms);

    expect_error("EU4PEACE_EXEC1 1 r unknown FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA FRA 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_recipient);
    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA eng 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_recipient);
    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA ENG 1 2 war_0123456789ABCDEF_01234567 demand -1 - -\n",
        wire::ParseError::invalid_war_id);
    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 counter -1 - -\n",
        wire::ParseError::invalid_direction);

    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand 101 - -\n",
        wire::ParseError::invalid_amount);
    expect_error("EU4PEACE_EXEC1 1 r demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC1 1 r demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 177,12,3,4 FRA\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand 0 - -\n",
        wire::ParseError::invalid_amount);
    expect_error("EU4PEACE_EXEC1 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC1 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC1 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 177,177 FRA\n",
        wire::ParseError::invalid_province_ids);
    expect_error("EU4PEACE_EXEC1 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 0 FRA\n",
        wire::ParseError::invalid_province_ids);
    expect_error("EU4PEACE_EXEC1 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 177 ---\n",
        wire::ParseError::invalid_beneficiary);
    expect_error("EU4PEACE_EXEC1 1 r demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand 10000 177 -\n",
        wire::ParseError::invalid_beneficiary);
    expect_error("EU4PEACE_EXEC1 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC1 1 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - r\n",
        wire::ParseError::field_count);

    expect_error("EU4PEACE_EXEC2 1 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - r\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC2 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - mr\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC2 1 r demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - mr\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC2 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - pr\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC2 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - - mr\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC2 1 r demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - - m\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC2 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 177 FRA p\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC2 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - rm\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC2 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - mprr\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC2 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - x\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC2 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC2 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - mpr\n",
        wire::ParseError::invalid_combination);

    std::string too_many="EU4PEACE_EXEC1 1 r cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 ";
    for (int index=1;index<=17;++index) {
        if (index>1) too_many.push_back(',');
        too_many += std::to_string(index);
    }
    too_many += " FRA\n";
    expect_error(too_many,wire::ParseError::invalid_province_ids);

    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::invalid_combination),
        "invalid_combination")==0);
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::invalid_term_mask),
        "invalid_term_mask")==0);
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::ok),"ok")==0);

    if (failures) {
        std::fprintf(stderr,"%d checks failed\n",failures);
        return 1;
    }
    std::puts("peace execution wire tests passed");
    return 0;
}
