#include "peace-execution-wire.h"

#include <cstddef>
#include <cstdio>
#include <cstring>
#include <string>

namespace wire=bridge::peace_execution_wire;

static_assert(offsetof(wire::PeaceExecutionRequest,term_mask)==243,
    "term_mask ABI offset changed");
static_assert(sizeof(((wire::PeaceExecutionRequest*)nullptr)->term_mask)==14,
    "term_mask ABI capacity changed");
static_assert(offsetof(wire::PeaceExecutionRequest,trade_power_source)==257,
    "trade_power_source ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,trade_power_beneficiary)==261,
    "trade_power_beneficiary ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_concede_defeat)==265,
    "selected_concede_defeat ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,concede_defeat)==266,
    "concede_defeat ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_annul_treaties)==267,
    "selected_annul_treaties ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,annul_treaties)==268,
    "annul_treaties ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,annul_country)==269,
    "annul_country ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,annul_partners)==273,
    "annul_partners ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,annul_partner_count)==337,
    "annul_partner_count ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_humiliate_rival)==338,
    "selected_humiliate_rival ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,humiliate_rival)==339,
    "humiliate_rival ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_show_strength)==340,
    "selected_show_strength ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,show_strength)==341,
    "show_strength ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_force_religion)==342,
    "selected_force_religion ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,force_religion)==343,
    "force_religion ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_return_core)==344,
    "selected_return_core ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,return_core)==345,
    "return_core ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,return_core_ids)==348,
    "return_core_ids ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,return_core_count)==412,
    "return_core_count ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,return_core_owner)==413,
    "return_core_owner ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_revoke_core)==417,
    "selected_revoke_core ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,revoke_core)==418,
    "revoke_core ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,revoke_core_ids)==420,
    "revoke_core_ids ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,revoke_core_count)==484,
    "revoke_core_count ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,revoke_core_owner)==485,
    "revoke_core_owner ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_release_subject)==489,
    "selected_release_subject ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,release_subject)==490,
    "release_subject ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,release_subject_countries)==491,
    "release_subject_countries ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,release_subject_count)==555,
    "release_subject_count ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,selected_transfer_subject)==556,
    "selected_transfer_subject ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,transfer_subject)==557,
    "transfer_subject ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,transfer_subject_countries)==558,
    "transfer_subject_countries ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,transfer_subject_count)==622,
    "transfer_subject_count ABI offset changed");
static_assert(offsetof(wire::PeaceExecutionRequest,country_term_mask)==624,
    "EXEC10 extension must follow the unchanged legacy ABI prefix");

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

struct Exec2MatrixCase {
    const char* mask;
    const char* action;
    const char* amount;
    const char* provinces;
    const char* beneficiary;
    bool selected_amount;
    bool selected_provinces;
};

static void expect_exec2_matrix_case(const char* direction,
    const Exec2MatrixCase& test_case,std::size_t case_number) {
    const char* war="war_0123456789abcdef_01234567";
    const std::string request_id="r48_matrix_"+std::to_string(case_number)
        +"_"+direction;
    const std::string text=std::string("EU4PEACE_EXEC2 48 ")+request_id+" "
        +test_case.action+" FRA ENG 1 7 "+war+" "+direction+" "
        +test_case.amount+" "+test_case.provinces+" "+test_case.beneficiary
        +" "+test_case.mask+"\n";
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.ok());
    if (!result.ok()) {
        std::fprintf(stderr,"EXEC2 matrix case failed: direction=%s mask=%s "
            "action=%s error=%s field=%zu\n",direction,test_case.mask,
            test_case.action,wire::parse_error_name(result.error),result.field);
        return;
    }
    CHECK(request.selected_reparations);
    CHECK(!request.selected_trade_power);
    CHECK(!request.selected_concede_defeat);
    CHECK(request.selected_amount==test_case.selected_amount);
    CHECK(request.selected_provinces==test_case.selected_provinces);
    CHECK(request.selected_beneficiary==test_case.selected_provinces);
    CHECK(request.amount_raw==(test_case.selected_amount?100:-1));
    CHECK(request.province_count==(test_case.selected_provinces?1:0));
    CHECK(std::strcmp(request.term_mask,test_case.mask)==0);
    CHECK(std::strcmp(request.direction,direction)==0);
    CHECK(request.demand_direction==(std::strcmp(direction,"demand")==0));
    CHECK(request.white_peace==false);
    CHECK(!request.concede_defeat);
    CHECK(request.demand_ducats==(std::strcmp(test_case.action,"demand_ducats")==0));
    CHECK(request.cede_province==(std::strcmp(test_case.action,"cede_province")==0));
    CHECK(request.war_reparations==(std::strcmp(test_case.action,"war_reparations")==0));
}

struct Exec3MatrixCase {
    const char* mask;
    const char* action;
    const char* amount;
    const char* provinces;
    const char* beneficiary;
    bool selected_amount;
    bool selected_provinces;
};

static void expect_exec3_matrix_case(const char* direction,
    const Exec3MatrixCase& test_case,std::size_t case_number) {
    const char* war="war_0123456789abcdef_01234567";
    const std::string request_id="r50_matrix_"+std::to_string(case_number)
        +"_"+direction;
    const std::string text=std::string("EU4PEACE_EXEC3 50 ")+request_id+" "
        +test_case.action+" FRA ENG 1 7 "+war+" "+direction+" "
        +test_case.amount+" "+test_case.provinces+" "+test_case.beneficiary
        +" "+test_case.mask+"\n";
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.ok());
    if (!result.ok()) {
        std::fprintf(stderr,"EXEC3 matrix case failed: direction=%s mask=%s "
            "action=%s error=%s field=%zu\n",direction,test_case.mask,
            test_case.action,wire::parse_error_name(result.error),result.field);
        return;
    }
    const bool mask_has_reparations=std::strchr(test_case.mask,'r')!=nullptr;
    CHECK(request.selected_trade_power);
    CHECK(!request.selected_concede_defeat);
    CHECK(request.selected_amount==test_case.selected_amount);
    CHECK(request.selected_provinces==test_case.selected_provinces);
    CHECK(request.selected_reparations==mask_has_reparations);
    CHECK(request.selected_beneficiary==test_case.selected_provinces);
    CHECK(request.amount_raw==(test_case.selected_amount?100:-1));
    CHECK(request.province_count==(test_case.selected_provinces?1:0));
    CHECK(std::strcmp(request.term_mask,test_case.mask)==0);
    CHECK(std::strcmp(request.direction,direction)==0);
    CHECK(request.demand_direction==(std::strcmp(direction,"demand")==0));
    CHECK(request.white_peace==false);
    CHECK(!request.concede_defeat);
    CHECK(request.demand_ducats==(std::strcmp(test_case.action,"demand_ducats")==0));
    CHECK(request.cede_province==(std::strcmp(test_case.action,"cede_province")==0));
    CHECK(request.war_reparations==(std::strcmp(test_case.action,"war_reparations")==0));
    CHECK(request.transfer_trade_power==
        (std::strcmp(test_case.action,"transfer_trade_power")==0));
    const char* expected_source=std::strcmp(direction,"demand")==0?"ENG":"FRA";
    const char* expected_beneficiary=std::strcmp(direction,"demand")==0?"FRA":"ENG";
    CHECK(std::strcmp(request.trade_power_source,expected_source)==0);
    CHECK(std::strcmp(request.trade_power_beneficiary,expected_beneficiary)==0);
}

struct Exec4MatrixCase {
    const char* mask;
    const char* action;
    const char* amount;
    const char* provinces;
    const char* beneficiary;
    const char* source;
    bool selected_amount;
    bool selected_provinces;
};

static void expect_exec4_matrix_case(const char* direction,
    const Exec4MatrixCase& test_case,std::size_t case_number) {
    const char* war="war_0123456789abcdef_01234567";
    const std::string request_id="r51_matrix_"+std::to_string(case_number)
        +"_"+direction;
    const std::string text=std::string("EU4PEACE_EXEC4 51 ")+request_id+" "
        +test_case.action+" FRA ENG 1 7 "+war+" "+direction+" "
        +test_case.amount+" "+test_case.provinces+" "+test_case.beneficiary
        +" "+test_case.mask+" "+test_case.source+"\n";
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.ok());
    if (!result.ok()) {
        std::fprintf(stderr,"EXEC4 matrix case failed: direction=%s mask=%s "
            "action=%s source=%s error=%s field=%zu\n",direction,
            test_case.mask,test_case.action,test_case.source,
            wire::parse_error_name(result.error),result.field);
        return;
    }
    const bool mask_has_reparations=std::strchr(test_case.mask,'r')!=nullptr;
    CHECK(request.selected_trade_power);
    CHECK(!request.selected_concede_defeat);
    CHECK(request.selected_amount==test_case.selected_amount);
    CHECK(request.selected_provinces==test_case.selected_provinces);
    CHECK(request.selected_reparations==mask_has_reparations);
    CHECK(request.selected_beneficiary==test_case.selected_provinces);
    CHECK(request.amount_raw==(test_case.selected_amount?100:-1));
    CHECK(request.province_count==(test_case.selected_provinces?1:0));
    CHECK(std::strcmp(request.term_mask,test_case.mask)==0);
    CHECK(std::strcmp(request.direction,direction)==0);
    CHECK(request.demand_direction==(std::strcmp(direction,"demand")==0));
    CHECK(std::strcmp(request.trade_power_source,test_case.source)==0);
    const char* expected_beneficiary=std::strcmp(direction,"demand")==0?"FRA":"ENG";
    CHECK(std::strcmp(request.trade_power_beneficiary,expected_beneficiary)==0);
    CHECK(request.white_peace==false);
    CHECK(!request.concede_defeat);
    CHECK(request.demand_ducats==
        (std::strcmp(test_case.action,"demand_ducats")==0));
    CHECK(request.cede_province==
        (std::strcmp(test_case.action,"cede_province")==0));
    CHECK(request.war_reparations==
        (std::strcmp(test_case.action,"war_reparations")==0));
    CHECK(request.transfer_trade_power==
        (std::strcmp(test_case.action,"transfer_trade_power")==0));
}

struct Exec5MatrixCase {
    const char* mask;
    const char* action;
    const char* amount;
    const char* provinces;
    const char* beneficiary;
    const char* source;
    bool selected_amount;
    bool selected_provinces;
    bool selected_trade_power;
};

static void expect_exec5_matrix_case(const char* direction,
    const Exec5MatrixCase& test_case,std::size_t case_number) {
    const char* war="war_0123456789abcdef_01234567";
    const std::string request_id="r52_matrix_"+std::to_string(case_number)
        +"_"+direction;
    const std::string text=std::string("EU4PEACE_EXEC5 52 ")+request_id+" "
        +test_case.action+" FRA ENG 1 7 "+war+" "+direction+" "
        +test_case.amount+" "+test_case.provinces+" "+test_case.beneficiary
        +" "+test_case.mask+" "+test_case.source+"\n";
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.ok());
    if (!result.ok()) {
        std::fprintf(stderr,"EXEC5 matrix case failed: direction=%s mask=%s "
            "action=%s source=%s error=%s field=%zu\n",direction,
            test_case.mask,test_case.action,test_case.source,
            wire::parse_error_name(result.error),result.field);
        return;
    }
    const bool mask_has_reparations=std::strchr(test_case.mask,'r')!=nullptr;
    CHECK(request.selected_concede_defeat);
    CHECK(request.selected_trade_power==test_case.selected_trade_power);
    CHECK(request.selected_amount==test_case.selected_amount);
    CHECK(request.selected_provinces==test_case.selected_provinces);
    CHECK(request.selected_reparations==mask_has_reparations);
    CHECK(request.selected_beneficiary==test_case.selected_provinces);
    CHECK(request.amount_raw==(test_case.selected_amount?100:-1));
    CHECK(request.province_count==(test_case.selected_provinces?1:0));
    CHECK(std::strcmp(request.term_mask,test_case.mask)==0);
    CHECK(std::strcmp(request.action_id,test_case.action)==0);
    CHECK(std::strcmp(request.direction,direction)==0);
    CHECK(request.demand_direction==(std::strcmp(direction,"demand")==0));
    CHECK(request.white_peace==false);
    CHECK(request.concede_defeat==
        (std::strcmp(test_case.action,"concede_defeat")==0));
    CHECK(request.demand_ducats==
        (std::strcmp(test_case.action,"demand_ducats")==0));
    CHECK(request.cede_province==
        (std::strcmp(test_case.action,"cede_province")==0));
    CHECK(request.war_reparations==
        (std::strcmp(test_case.action,"war_reparations")==0));
    CHECK(request.transfer_trade_power==
        (std::strcmp(test_case.action,"transfer_trade_power")==0));
    if (test_case.selected_trade_power) {
        CHECK(std::strcmp(request.trade_power_source,test_case.source)==0);
        const char* expected_beneficiary=
            std::strcmp(direction,"demand")==0?"FRA":"ENG";
        CHECK(std::strcmp(request.trade_power_beneficiary,
            expected_beneficiary)==0);
    } else {
        CHECK(std::strcmp(test_case.source,"-")==0);
        CHECK(request.trade_power_source[0]=='\0');
        CHECK(request.trade_power_beneficiary[0]=='\0');
    }
}

struct Exec6MatrixCase {
    const char* mask;
    const char* action;
};

static void expect_exec6_matrix_case(const char* direction,
    const Exec6MatrixCase& test_case,std::size_t case_number) {
    const char* war="war_0123456789abcdef_01234567";
    const bool mask_has_money=std::strchr(test_case.mask,'m')!=nullptr;
    const bool mask_has_province=std::strchr(test_case.mask,'p')!=nullptr;
    const bool mask_has_reparations=std::strchr(test_case.mask,'r')!=nullptr;
    const bool mask_has_trade_power=std::strchr(test_case.mask,'t')!=nullptr;
    const bool mask_has_concede=std::strchr(test_case.mask,'c')!=nullptr;
    const std::string request_id="r53_matrix_"+std::to_string(case_number)
        +"_"+test_case.mask+"_"+direction;
    const std::string text=std::string("EU4PEACE_EXEC6 53 ")+request_id+" "
        +test_case.action+" FRA ENG 1 7 "+war+" "+direction+" "
        +(mask_has_money?"100":"-1")+" "
        +(mask_has_province?"177":"-")+" "
        +(mask_has_province?"SAV":"-")+" "+test_case.mask+" "
        +(mask_has_trade_power?"GER":"-")+" SAV ENG,GER\n";
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.ok());
    if (!result.ok()) {
        std::fprintf(stderr,"EXEC6 matrix case failed: direction=%s mask=%s "
            "action=%s error=%s field=%zu\n",direction,test_case.mask,
            test_case.action,wire::parse_error_name(result.error),result.field);
        return;
    }
    CHECK(request.selected_annul_treaties);
    CHECK(request.annul_treaties==
        (std::strcmp(test_case.action,"annul_treaties")==0));
    CHECK(request.selected_amount==mask_has_money);
    CHECK(request.selected_provinces==mask_has_province);
    CHECK(request.selected_reparations==mask_has_reparations);
    CHECK(request.selected_trade_power==mask_has_trade_power);
    CHECK(request.selected_concede_defeat==mask_has_concede);
    CHECK(request.amount_raw==(mask_has_money?100:-1));
    CHECK(request.province_count==(mask_has_province?1:0));
    CHECK(request.selected_beneficiary==mask_has_province);
    CHECK(std::strcmp(request.term_mask,test_case.mask)==0);
    CHECK(std::strcmp(request.action_id,test_case.action)==0);
    CHECK(std::strcmp(request.direction,direction)==0);
    CHECK(request.demand_direction==(std::strcmp(direction,"demand")==0));
    CHECK(request.white_peace==false);
    CHECK(request.demand_ducats==
        (std::strcmp(test_case.action,"demand_ducats")==0));
    CHECK(request.cede_province==
        (std::strcmp(test_case.action,"cede_province")==0));
    CHECK(request.war_reparations==
        (std::strcmp(test_case.action,"war_reparations")==0));
    CHECK(request.transfer_trade_power==
        (std::strcmp(test_case.action,"transfer_trade_power")==0));
    CHECK(request.concede_defeat==
        (std::strcmp(test_case.action,"concede_defeat")==0));
    CHECK(std::strcmp(request.annul_country,"SAV")==0);
    CHECK(request.annul_partner_count==2);
    CHECK(std::strcmp(request.annul_partners[0],"ENG")==0);
    CHECK(std::strcmp(request.annul_partners[1],"GER")==0);
    if (mask_has_trade_power) {
        CHECK(std::strcmp(request.trade_power_source,"GER")==0);
        const char* expected_beneficiary=
            std::strcmp(direction,"demand")==0?"FRA":"ENG";
        CHECK(std::strcmp(request.trade_power_beneficiary,
            expected_beneficiary)==0);
    } else {
        CHECK(request.trade_power_source[0]=='\0');
        CHECK(request.trade_power_beneficiary[0]=='\0');
    }
}

struct Exec7MatrixCase {
    const char* mask;
    const char* action;
};

static void expect_exec7_matrix_case(const char* direction,
    const Exec7MatrixCase& test_case,std::size_t case_number) {
    const char* war="war_0123456789abcdef_01234567";
    const bool mask_has_money=std::strchr(test_case.mask,'m')!=nullptr;
    const bool mask_has_province=std::strchr(test_case.mask,'p')!=nullptr;
    const bool mask_has_reparations=std::strchr(test_case.mask,'r')!=nullptr;
    const bool mask_has_trade_power=std::strchr(test_case.mask,'t')!=nullptr;
    const bool mask_has_concede=std::strchr(test_case.mask,'c')!=nullptr;
    const bool mask_has_annul=std::strchr(test_case.mask,'a')!=nullptr;
    const bool mask_has_humiliate=std::strchr(test_case.mask,'h')!=nullptr;
    const bool mask_has_strength=std::strchr(test_case.mask,'s')!=nullptr;
    const bool mask_has_religion=std::strchr(test_case.mask,'f')!=nullptr;
    const std::string request_id="r54_matrix_"+std::to_string(case_number)
        +"_"+test_case.mask+"_"+direction;
    const std::string text=std::string("EU4PEACE_EXEC7 54 ")+request_id+" "
        +test_case.action+" FRA ENG 1 7 "+war+" "+direction+" "
        +(mask_has_money?"100":"-1")+" "
        +(mask_has_province?"177":"-")+" "
        +(mask_has_province?"SAV":"-")+" "+test_case.mask+" "
        +(mask_has_trade_power?"GER":"-")
        +(mask_has_annul?" SAV ENG,GER\n":" - -\n");
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.ok());
    if (!result.ok()) {
        std::fprintf(stderr,"EXEC7 matrix case failed: direction=%s mask=%s "
            "action=%s error=%s field=%zu\n",direction,test_case.mask,
            test_case.action,wire::parse_error_name(result.error),result.field);
        return;
    }
    CHECK(request.selected_amount==mask_has_money);
    CHECK(request.selected_provinces==mask_has_province);
    CHECK(request.selected_reparations==mask_has_reparations);
    CHECK(request.selected_trade_power==mask_has_trade_power);
    CHECK(request.selected_concede_defeat==mask_has_concede);
    CHECK(request.selected_annul_treaties==mask_has_annul);
    CHECK(request.selected_humiliate_rival==mask_has_humiliate);
    CHECK(request.selected_show_strength==mask_has_strength);
    CHECK(request.selected_force_religion==mask_has_religion);
    CHECK(request.amount_raw==(mask_has_money?100:-1));
    CHECK(request.province_count==(mask_has_province?1:0));
    CHECK(request.selected_beneficiary==mask_has_province);
    CHECK(std::strcmp(request.term_mask,test_case.mask)==0);
    CHECK(std::strcmp(request.action_id,test_case.action)==0);
    CHECK(std::strcmp(request.direction,direction)==0);
    CHECK(request.demand_direction==(std::strcmp(direction,"demand")==0));
    CHECK(request.white_peace==false);
    CHECK(request.demand_ducats==
        (std::strcmp(test_case.action,"demand_ducats")==0));
    CHECK(request.cede_province==
        (std::strcmp(test_case.action,"cede_province")==0));
    CHECK(request.war_reparations==
        (std::strcmp(test_case.action,"war_reparations")==0));
    CHECK(request.transfer_trade_power==
        (std::strcmp(test_case.action,"transfer_trade_power")==0));
    CHECK(request.concede_defeat==
        (std::strcmp(test_case.action,"concede_defeat")==0));
    CHECK(request.annul_treaties==
        (std::strcmp(test_case.action,"annul_treaties")==0));
    CHECK(request.humiliate_rival==
        (std::strcmp(test_case.action,"humiliate_rival")==0));
    CHECK(request.show_strength==
        (std::strcmp(test_case.action,"show_strength")==0));
    CHECK(request.force_religion==
        (std::strcmp(test_case.action,"force_religion")==0));
    if (mask_has_annul) {
        CHECK(std::strcmp(request.annul_country,"SAV")==0);
        CHECK(request.annul_partner_count==2);
        CHECK(std::strcmp(request.annul_partners[0],"ENG")==0);
        CHECK(std::strcmp(request.annul_partners[1],"GER")==0);
    } else {
        CHECK(request.annul_country[0]=='\0');
        CHECK(request.annul_partner_count==0);
    }
    if (mask_has_trade_power) {
        CHECK(std::strcmp(request.trade_power_source,"GER")==0);
        const char* expected_beneficiary=
            std::strcmp(direction,"demand")==0?"FRA":"ENG";
        CHECK(std::strcmp(request.trade_power_beneficiary,
            expected_beneficiary)==0);
    } else {
        CHECK(request.trade_power_source[0]=='\0');
        CHECK(request.trade_power_beneficiary[0]=='\0');
    }
}

struct Exec8MatrixCase {
    const char* mask;
    const char* action;
};

static void expect_exec8_matrix_case(const char* direction,
    const Exec8MatrixCase& test_case,std::size_t case_number) {
    const char* war="war_0123456789abcdef_01234567";
    const bool money=std::strchr(test_case.mask,'m')!=nullptr;
    const bool province=std::strchr(test_case.mask,'p')!=nullptr;
    const bool reparations=std::strchr(test_case.mask,'r')!=nullptr;
    const bool trade_power=std::strchr(test_case.mask,'t')!=nullptr;
    const bool concede=std::strchr(test_case.mask,'c')!=nullptr;
    const bool annul=std::strchr(test_case.mask,'a')!=nullptr;
    const bool humiliate=std::strchr(test_case.mask,'h')!=nullptr;
    const bool strength=std::strchr(test_case.mask,'s')!=nullptr;
    const bool religion=std::strchr(test_case.mask,'f')!=nullptr;
    const bool return_core=std::strchr(test_case.mask,'b')!=nullptr;
    const bool revoke_core=std::strchr(test_case.mask,'v')!=nullptr;
    const std::string request_id="r58_matrix_"+std::to_string(case_number)
        +"_"+test_case.mask+"_"+direction;
    const std::string text=std::string("EU4PEACE_EXEC8 58 ")+request_id+" "
        +test_case.action+" FRA ENG 1 7 "+war+" "+direction+" "
        +(money?"100":"-1")+" "+(province?"177,174":"-")+" "
        +(province?"SAV":"-")+" "+test_case.mask+" "
        +(trade_power?"GER":"-")+" "
        +(annul?"SAV ENG,GER":"- -")+" "
        +(return_core?"173,177 AMG":"- -")+" "
        +(revoke_core?"175 ENG":"- -")+"\n";
    wire::PeaceExecutionRequest request{};
    const wire::ParseResult result=parse_bytes(text.data(),text.size(),request);
    CHECK(result.ok());
    if (!result.ok()) {
        std::fprintf(stderr,"EXEC8 matrix case failed: direction=%s mask=%s "
            "action=%s error=%s field=%zu\n",direction,test_case.mask,
            test_case.action,wire::parse_error_name(result.error),result.field);
        return;
    }
    CHECK(request.selected_amount==money);
    CHECK(request.selected_provinces==province);
    CHECK(request.selected_reparations==reparations);
    CHECK(request.selected_trade_power==trade_power);
    CHECK(request.selected_concede_defeat==concede);
    CHECK(request.selected_annul_treaties==annul);
    CHECK(request.selected_humiliate_rival==humiliate);
    CHECK(request.selected_show_strength==strength);
    CHECK(request.selected_force_religion==religion);
    CHECK(request.selected_return_core==return_core);
    CHECK(request.selected_revoke_core==revoke_core);
    CHECK(request.return_core==
        (std::strcmp(test_case.action,"return_core")==0));
    CHECK(request.revoke_core==
        (std::strcmp(test_case.action,"revoke_core")==0));
    CHECK(std::strcmp(request.term_mask,test_case.mask)==0);
    CHECK(request.return_core_count==(return_core?2:0));
    CHECK(request.revoke_core_count==(revoke_core?1:0));
    if (return_core) {
        CHECK(request.return_core_ids[0]==173 && request.return_core_ids[1]==177);
        CHECK(std::strcmp(request.return_core_owner,"AMG")==0);
    } else CHECK(request.return_core_owner[0]=='\0');
    if (revoke_core) {
        CHECK(request.revoke_core_ids[0]==175);
        CHECK(std::strcmp(request.revoke_core_owner,"ENG")==0);
    } else CHECK(request.revoke_core_owner[0]=='\0');
    if (trade_power) {
        CHECK(std::strcmp(request.trade_power_source,"GER")==0);
    } else CHECK(request.trade_power_source[0]=='\0');
    if (annul) {
        CHECK(std::strcmp(request.annul_country,"SAV")==0);
        CHECK(request.annul_partner_count==2);
    } else CHECK(request.annul_country[0]=='\0');
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
    CHECK(!request.selected_reparations && !request.selected_trade_power
        && !request.selected_concede_defeat && !request.concede_defeat);
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

    // Every valid EXEC2 mask has a reparations term and may choose any one
    // of the terms present as its primary action.  Exercise all eight
    // mask/primary combinations in both wire directions.
    const Exec2MatrixCase exec2_matrix[] = {
        {"r",   "war_reparations", "-1", "-",     "-",   false, false},
        {"mr",  "demand_ducats",   "100", "-",     "-",   true,  false},
        {"mr",  "war_reparations", "100", "-",     "-",   true,  false},
        {"pr",  "cede_province",   "-1", "177",   "SAV", false, true },
        {"pr",  "war_reparations", "-1", "177",   "SAV", false, true },
        {"mpr", "cede_province",   "100", "177",   "SAV", true,  true },
        {"mpr", "demand_ducats",   "100", "177",   "SAV", true,  true },
        {"mpr", "war_reparations", "100", "177",   "SAV", true,  true },
    };
    for (const char* direction : {"demand","offer"}) {
        for (std::size_t index=0;index<sizeof(exec2_matrix)/sizeof(exec2_matrix[0]);++index)
            expect_exec2_matrix_case(direction,exec2_matrix[index],index
                +(std::strcmp(direction,"offer")==0?8u:0u));
    }

    // EXEC3 has the same fourteen fields as EXEC2 and adds a mandatory t
    // term.  Every canonical mask and every primary action is exercised in
    // both wire directions; m/p payload flags still have to match the mask.
    const Exec3MatrixCase exec3_matrix[] = {
        {"t",    "transfer_trade_power", "-1", "-",   "-",   false, false},
        {"mt",   "demand_ducats",        "100", "-",   "-",   true,  false},
        {"pt",   "cede_province",        "-1",  "177", "SAV", false, true },
        {"rt",   "war_reparations",     "-1",  "-",   "-",   false, false},
        {"mpt",  "transfer_trade_power", "100", "177", "SAV", true,  true },
        {"mrt",  "demand_ducats",        "100", "-",   "-",   true,  false},
        {"prt",  "cede_province",        "-1",  "177", "SAV", false, true },
        {"mprt", "war_reparations",     "100", "177", "SAV", true,  true },
    };
    for (const char* direction : {"demand","offer"}) {
        for (std::size_t index=0;index<sizeof(exec3_matrix)/sizeof(exec3_matrix[0]);++index)
            expect_exec3_matrix_case(direction,exec3_matrix[index],index
                +(std::strcmp(direction,"offer")==0?8u:0u));
    }

    // EXEC4 keeps EXEC3's fourteen fields and appends an explicit source tag.
    // T remains mandatory, m/p/r payload and primary-action rules are shared,
    // and a third-country source is accepted when it differs from the derived
    // trade-power beneficiary.
    const Exec4MatrixCase exec4_matrix[] = {
        {"t",    "transfer_trade_power", "-1", "-",   "-",   "ENG", false, false},
        {"mt",   "demand_ducats",        "100", "-",   "-",   "SAV", true,  false},
        {"pt",   "cede_province",        "-1",  "177", "SAV", "ENG", false, true },
        {"rt",   "war_reparations",     "-1",  "-",   "-",   "SAV", false, false},
        {"mpt",  "transfer_trade_power", "100", "177", "SAV", "ENG", true,  true },
        {"mrt",  "demand_ducats",        "100", "-",   "-",   "SAV", true,  false},
        {"prt",  "cede_province",        "-1",  "177", "SAV", "ENG", false, true },
        {"mprt", "war_reparations",     "100", "177", "SAV", "ENG", true,  true },
    };
    for (const char* direction : {"demand","offer"}) {
        for (std::size_t index=0;index<sizeof(exec4_matrix)/sizeof(exec4_matrix[0]);++index) {
            Exec4MatrixCase test_case=exec4_matrix[index];
            // Exercise both the direction-derived source and a third-country
            // source while keeping source distinct from the beneficiary.
            if (std::strcmp(direction,"offer")==0) {
                test_case.source=(index%2==0)?"FRA":"SAV";
            }
            expect_exec4_matrix_case(direction,test_case,index
                +(std::strcmp(direction,"offer")==0?8u:0u));
        }
    }

    // EXEC5 keeps EXEC4's fifteen fields, adds the C-bearing canonical mask
    // family, and accepts every one of the sixteen combinations containing c.
    // With no t, the fifteenth field is the required '-' placeholder and the
    // trade-power source/beneficiary output remains empty.
    const Exec5MatrixCase exec5_matrix[] = {
        {"c",     "concede_defeat",    "-1", "-",     "-",   "-",   false, false, false},
        {"mc",    "demand_ducats",     "100", "-",     "-",   "-",   true,  false, false},
        {"pc",    "cede_province",     "-1", "177",   "SAV", "-",   false, true,  false},
        {"rc",    "war_reparations",   "-1", "-",     "-",   "-",   false, false, false},
        {"tc",    "transfer_trade_power","-1","-",   "-",   "SAV", false, false, true },
        {"mpc",   "concede_defeat",    "100", "177",   "SAV", "-",   true,  true,  false},
        {"mrc",   "demand_ducats",     "100", "-",     "-",   "-",   true,  false, false},
        {"mtc",   "transfer_trade_power","100","-",   "-",   "SAV", true,  false, true },
        {"prc",   "cede_province",     "-1", "177",   "SAV", "-",   false, true,  false},
        {"ptc",   "concede_defeat",    "-1", "177",   "SAV", "SAV", false, true,  true },
        {"rtc",   "war_reparations",   "-1", "-",     "-",   "SAV", false, false, true },
        {"mprc",  "demand_ducats",     "100", "177",   "SAV", "-",   true,  true,  false},
        {"mptc",  "transfer_trade_power","100","177", "SAV", "SAV", true,  true,  true },
        {"mrtc",  "concede_defeat",    "100", "-",     "-",   "SAV", true,  false, true },
        {"prtc",  "cede_province",     "-1", "177",   "SAV", "SAV", false, true,  true },
        {"mprtc", "concede_defeat",    "100", "177",   "SAV", "SAV", true,  true,  true },
    };
    for (const char* direction : {"demand","offer"}) {
        for (std::size_t index=0;index<sizeof(exec5_matrix)/sizeof(exec5_matrix[0]);++index)
            expect_exec5_matrix_case(direction,exec5_matrix[index],index
                +(std::strcmp(direction,"offer")==0?16u:0u));
    }

    // EXEC6 preserves EXEC5's fifteen fields and appends country plus a
    // strictly sorted, unique partner CSV.  The canonical m,p,r,t,c,a order
    // accepts all 32 masks containing a; the first six cases also exercise
    // every old primary action alongside the new Annul term.
    const Exec6MatrixCase exec6_matrix[] = {
        {"a",      "annul_treaties"},
        {"ma",     "demand_ducats"},
        {"pa",     "cede_province"},
        {"ra",     "war_reparations"},
        {"ta",     "transfer_trade_power"},
        {"ca",     "concede_defeat"},
        {"mpa",    "annul_treaties"},
        {"mra",    "annul_treaties"},
        {"mta",    "annul_treaties"},
        {"mca",    "annul_treaties"},
        {"pra",    "annul_treaties"},
        {"pta",    "annul_treaties"},
        {"pca",    "annul_treaties"},
        {"rta",    "annul_treaties"},
        {"rca",    "annul_treaties"},
        {"tca",    "annul_treaties"},
        {"mpra",   "annul_treaties"},
        {"mpta",   "annul_treaties"},
        {"mpca",   "annul_treaties"},
        {"mrta",   "annul_treaties"},
        {"mrca",   "annul_treaties"},
        {"mtca",   "annul_treaties"},
        {"prta",   "annul_treaties"},
        {"prca",   "annul_treaties"},
        {"ptca",   "annul_treaties"},
        {"rtca",   "annul_treaties"},
        {"mprta",  "annul_treaties"},
        {"mprca",  "annul_treaties"},
        {"mptca",  "annul_treaties"},
        {"mrtca",  "annul_treaties"},
        {"prtca",  "annul_treaties"},
        {"mprtca", "annul_treaties"},
    };
    for (const char* direction : {"demand","offer"}) {
        for (std::size_t index=0;index<sizeof(exec6_matrix)/sizeof(exec6_matrix[0]);++index)
            expect_exec6_matrix_case(direction,exec6_matrix[index],index
                +(std::strcmp(direction,"offer")==0?32u:0u));
    }

    // EXEC7 keeps EXEC6's seventeen fields and permits the three native
    // base terms in canonical m,p,r,t,c,a,h,s,f order.  Every H/S/F subset
    // is accepted, as are representative combinations with the older terms;
    // each direction is exercised and the primary action may be any selected
    // term because native mutual-exclusion belongs to the candidate rules.
    const Exec7MatrixCase exec7_matrix[] = {
        {"h",        "humiliate_rival"},
        {"s",        "show_strength"},
        {"f",        "force_religion"},
        {"hs",       "humiliate_rival"},
        {"hf",       "force_religion"},
        {"sf",       "force_religion"},
        {"hsf",      "show_strength"},
        {"mh",       "demand_ducats"},
        {"ps",       "cede_province"},
        {"rf",       "war_reparations"},
        {"th",       "transfer_trade_power"},
        {"cs",       "concede_defeat"},
        {"af",       "annul_treaties"},
        {"mprtcahsf", "force_religion"},
    };
    for (const char* direction : {"demand","offer"}) {
        for (std::size_t index=0;index<sizeof(exec7_matrix)/sizeof(exec7_matrix[0]);++index)
            expect_exec7_matrix_case(direction,exec7_matrix[index],index
                +(std::strcmp(direction,"offer")==0?14u:0u));
    }

    // EXEC8 keeps EXEC7's seventeen fields and appends return/revoke core
    // ids and owners.  b/v are canonical after h/s/f; either core term is
    // enough for the version, and all older terms remain composable.
    const Exec8MatrixCase exec8_matrix[] = {
        {"b",             "return_core"},
        {"v",             "revoke_core"},
        {"bv",            "return_core"},
        {"mbv",           "demand_ducats"},
        {"thv",           "revoke_core"},
        {"pab",           "return_core"},
        {"mprtcahsfbv",   "revoke_core"},
    };
    for (const char* direction : {"demand","offer"}) {
        for (std::size_t index=0;index<sizeof(exec8_matrix)/sizeof(exec8_matrix[0]);++index)
            expect_exec8_matrix_case(direction,exec8_matrix[index],index
                +(std::strcmp(direction,"offer")==0?7u:0u));
    }

    // EXEC8 version isolation and core field contracts.
    expect_error("EU4PEACE_EXEC7 1 r58_old_b humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b - - -\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC6 1 r58_old_v revoke_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV ENG,GER\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC8 1 r58_no_core_term demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - - m - - - - - - -\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC8 1 r58_wrong_order revoke_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - vb - - - - - 175 ENG\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC8 1 r58_duplicate revoke_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - bvv - - - 173 AMG 175 ENG\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC8 1 r58_bad_return_ids return_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b - - - 0,173 AMG - -\n",
        wire::ParseError::invalid_return_core_ids);
    expect_error("EU4PEACE_EXEC8 1 r58_duplicate_return_ids return_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b - - - 173,173 AMG - -\n",
        wire::ParseError::invalid_return_core_ids);
    expect_error("EU4PEACE_EXEC8 1 r58_bad_return_owner return_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b - - - 173 amg - -\n",
        wire::ParseError::invalid_return_core_owner);
    expect_error("EU4PEACE_EXEC8 1 r58_missing_return_owner return_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b - - - 173 - - -\n",
        wire::ParseError::invalid_return_core_owner);
    expect_error("EU4PEACE_EXEC8 1 r58_unselected_return revoke_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - v - - - 173 AMG 175 ENG\n",
        wire::ParseError::invalid_return_core_ids);
    expect_error("EU4PEACE_EXEC8 1 r58_bad_revoke_ids revoke_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - v - - - - - 175,175 ENG\n",
        wire::ParseError::invalid_revoke_core_ids);
    expect_error("EU4PEACE_EXEC8 1 r58_bad_revoke_owner revoke_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - v - - - - - 175 eng\n",
        wire::ParseError::invalid_revoke_core_owner);
    expect_error("EU4PEACE_EXEC8 1 r58_unselected_action return_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - v - - - - - 175 ENG\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC8 1 r58_unselected_revoke revoke_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b - - - 173 AMG - -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC8 1 r58_core_source_placeholder return_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b GER - - 173 AMG - -\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC8 1 r58_missing_tail return_core FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - b - -\n",
        wire::ParseError::field_count);

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
    expect_error(std::string(1025,'x')+"\n",wire::ParseError::wire_too_long);

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

    // Version isolation: EXEC1 has no R/T, EXEC2 has mandatory R and no T,
    // and EXEC3 rejects white peace and every mask without mandatory T.
    expect_error("EU4PEACE_EXEC1 1 r transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC2 1 r transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC2 1 r war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - rt\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC3 1 r white_peace FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC3 1 r transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - mpr\n",
        wire::ParseError::invalid_term_mask);

    // EXEC3 masks are canonical m,p,r,t order with no duplicates and must
    // include t.  Wrong order, duplicate, and missing-term examples stay on
    // the mask error path before payload/action consistency is checked.
    for (const char* mask : {"tm","ptm","rmt","mtt","mprtt","mpr"}) {
        const std::string text=std::string("EU4PEACE_EXEC3 1 r50_mask_")
            +mask+" transfer_trade_power FRA ENG 1 2 "
            "war_0123456789abcdef_01234567 demand -1 - - "+mask+"\n";
        expect_error(text,wire::ParseError::invalid_term_mask);
    }

    // The primary action must be represented by the selected mask term, and
    // m/p still cannot be claimed without their corresponding payload.
    expect_error("EU4PEACE_EXEC3 1 r50_unselected_money demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC3 1 r50_unselected_province cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC3 1 r50_unselected_reparations war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC3 1 r50_money_mask demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - - t\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC3 1 r50_province_mask cede_province FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 177 SAV t\n",
        wire::ParseError::invalid_combination);

    // EXEC4 is isolated from EXEC3: its fifteenth source field is required,
    // canonical, and distinct from the direction-derived beneficiary.
    expect_error("EU4PEACE_EXEC3 1 r51_extra_source transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t ENG\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC4 1 r51_missing_source transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC4 1 r51_bad_source transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t eng\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC4 1 r51_same_beneficiary transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t FRA\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC4 1 r51_same_beneficiary_offer transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 offer -1 - - t ENG\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC4 1 r51_missing_t demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - - m ENG\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC4 1 r51_unselected_money demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t ENG\n",
        wire::ParseError::invalid_combination);

    // EXEC5 is the only C-bearing version.  It keeps fifteen fields, accepts
    // all canonical masks containing c, and requires '-' in the source field
    // whenever t is absent.
    expect_error("EU4PEACE_EXEC1 1 r52_c_action concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC2 1 r52_c_action concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - r\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC3 1 r52_c_action concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC4 1 r52_c_action concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - t SAV\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC2 1 r52_c_mask war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - rc\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC3 1 r52_c_mask transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - tc\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC4 1 r52_c_mask transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - tc SAV\n",
        wire::ParseError::invalid_term_mask);

    expect_error("EU4PEACE_EXEC5 1 r52_missing_source concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - c\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC5 1 r52_extra_source concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - c - extra\n",
        wire::ParseError::field_count);
    for (const char* mask : {"cm","ct","mct","mcc","mprt","mprttc","x"}) {
        const std::string text=std::string("EU4PEACE_EXEC5 1 r52_mask_")
            +mask+" concede_defeat FRA ENG 1 2 "
            "war_0123456789abcdef_01234567 demand -1 - - "+mask+" -\n";
        expect_error(text,wire::ParseError::invalid_term_mask);
    }
    expect_error("EU4PEACE_EXEC5 1 r52_no_t_source concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - c ENG\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC5 1 r52_t_dash transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - tc -\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC5 1 r52_t_bad_source transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - tc eng\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC5 1 r52_t_same_beneficiary transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - tc FRA\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC5 1 r52_t_same_beneficiary_offer transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 offer -1 - - tc ENG\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC5 1 r52_c_unselected demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - c -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC5 1 r52_c_money_mismatch concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - mc -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC5 1 r52_c_province_mismatch concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - pc -\n",
        wire::ParseError::invalid_combination);

    // EXEC6 keeps the preceding fifteen fields byte-for-byte and appends the
    // required annul country plus partner CSV.  Old versions reject both the
    // action and the new mask alphabet.
    expect_error("EU4PEACE_EXEC5 1 r53_old_action annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a -\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC5 1 r53_old_mask concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ca -\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC6 1 r53_missing_annul_fields annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a -\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC6 1 r53_missing_partner_csv annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC6 1 r53_bad_country annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - sav ENG,GER\n",
        wire::ParseError::invalid_annul_country);
    expect_error("EU4PEACE_EXEC6 1 r53_short_country annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SA ENG,GER\n",
        wire::ParseError::invalid_annul_country);
    expect_error("EU4PEACE_EXEC6 1 r53_dash_partners annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV -\n",
        wire::ParseError::invalid_annul_partners);
    expect_error("EU4PEACE_EXEC6 1 r53_country_partner annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV SAV,GER\n",
        wire::ParseError::invalid_annul_partners);
    expect_error("EU4PEACE_EXEC6 1 r53_duplicate_partner annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV ENG,ENG\n",
        wire::ParseError::invalid_annul_partners);
    expect_error("EU4PEACE_EXEC6 1 r53_unsorted_partner annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV GER,ENG\n",
        wire::ParseError::invalid_annul_partners);
    expect_error("EU4PEACE_EXEC6 1 r53_bad_partner_tag annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV ENG,geR\n",
        wire::ParseError::invalid_annul_partners);
    expect_error("EU4PEACE_EXEC6 1 r53_mask_without_a concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - mprtc - SAV ENG,GER\n",
        wire::ParseError::invalid_term_mask);
    for (const char* mask : {"am","pma","mpratc","aa","mprtcx"}) {
        const std::string text=std::string("EU4PEACE_EXEC6 1 r53_bad_mask_")
            +mask+" annul_treaties FRA ENG 1 2 "
            "war_0123456789abcdef_01234567 demand -1 - - "+mask
            +" - SAV ENG,GER\n";
        expect_error(text,wire::ParseError::invalid_term_mask);
    }
    expect_error("EU4PEACE_EXEC6 1 r53_missing_t_source transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ta - SAV ENG,GER\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC6 1 r53_no_t_source annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a GER SAV ENG,GER\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC6 1 r53_bad_t_source transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ta eng SAV ENG,GER\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC6 1 r53_unselected_old_action demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV ENG,GER\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC6 1 r53_mask_payload_mismatch annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ma - SAV ENG,GER\n",
        wire::ParseError::invalid_combination);

    // EXEC7 is the only version that accepts H/S/F.  The preceding versions
    // reject both their action names and the new mask alphabet, while EXEC7
    // keeps canonical ordering, duplicate rejection, a/t field presence,
    // and primary-action selection strict.
    expect_error("EU4PEACE_EXEC1 1 r54_old_h_action humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - -\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC2 1 r54_old_h_mask war_reparations FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - rh\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC3 1 r54_old_s_mask transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ts\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC4 1 r54_old_f_mask transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - tf GER\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC5 1 r54_old_h_mask concede_defeat FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ch -\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC6 1 r54_old_s_mask annul_treaties FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - as - SAV ENG,GER\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC6 1 r54_old_f_action show_strength FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - a - SAV ENG,GER\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC7 1 r54_missing_tail humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - h -\n",
        wire::ParseError::field_count);
    expect_error("EU4PEACE_EXEC7 1 r54_missing_partners humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - h - SAV\n",
        wire::ParseError::field_count);
    for (const char* mask : {"sh","fh","hhs","mprtcahfs","mprtcahfsh",
                             "mprtcahsfh","mprtcahsfx","mprtca"}) {
        const std::string text=std::string("EU4PEACE_EXEC7 1 r54_bad_mask_")
            +mask+" humiliate_rival FRA ENG 1 2 "
            "war_0123456789abcdef_01234567 demand -1 - - "+mask
            +" - SAV ENG,GER\n";
        expect_error(text,wire::ParseError::invalid_term_mask);
    }
    expect_error("EU4PEACE_EXEC7 1 r54_no_t_source transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - th - SAV ENG,GER\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC7 1 r54_no_t_dash humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - h GER SAV ENG,GER\n",
        wire::ParseError::invalid_trade_power_source);
    expect_error("EU4PEACE_EXEC7 1 r54_t_same_beneficiary transfer_trade_power FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - th FRA SAV ENG,GER\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC7 1 r54_h_unselected show_strength FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - h - - -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC7 1 r54_s_unselected humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - s - - -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC7 1 r54_f_unselected force_religion FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - hs - - -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC7 1 r54_absent_a_country humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - h - SAV -\n",
        wire::ParseError::invalid_annul_country);
    expect_error("EU4PEACE_EXEC7 1 r54_absent_a_partners humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - h - - ENG,GER\n",
        wire::ParseError::invalid_annul_partners);
    expect_error("EU4PEACE_EXEC7 1 r54_selected_a_country humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ah - - -\n",
        wire::ParseError::invalid_annul_country);
    expect_error("EU4PEACE_EXEC7 1 r54_selected_a_partners humiliate_rival FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ah - SAV -\n",
        wire::ParseError::invalid_annul_partners);

    // EXEC9 appends the two subject CSVs after the unchanged EXEC8 core
    // fields.  Each selected family requires 1..16 tags; an unselected
    // family is represented by '-'.
    wire::PeaceExecutionRequest release_subject_output{};
    expect_ok("EU4PEACE_EXEC9 1 r60_release release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - l - - - - - - - TYR -\n",
        release_subject_output);
    CHECK(release_subject_output.selected_release_subject);
    CHECK(release_subject_output.release_subject_count==1);
    CHECK(std::strcmp(release_subject_output.release_subject_countries[0],"TYR")==0);
    CHECK(release_subject_output.transfer_subject_count==0);
    wire::PeaceExecutionRequest transfer_subject_output{};
    expect_ok("EU4PEACE_EXEC9 1 r60_transfer transfer_subject FRA ENG 1 2 war_0123456789abcdef_01234567 offer -1 - - x - - - - - - - - LEI\n",
        transfer_subject_output);
    CHECK(transfer_subject_output.selected_transfer_subject);
    CHECK(transfer_subject_output.transfer_subject_count==1);
    CHECK(std::strcmp(transfer_subject_output.transfer_subject_countries[0],"LEI")==0);
    wire::PeaceExecutionRequest combined_subject_output{};
    expect_ok("EU4PEACE_EXEC9 1 r60_combined release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - rlx - - - - - - - TYR,SAV LEI\n",
        combined_subject_output);
    CHECK(combined_subject_output.selected_reparations);
    CHECK(combined_subject_output.release_subject_count==2);
    CHECK(combined_subject_output.transfer_subject_count==1);
    CHECK(std::strcmp(combined_subject_output.release_subject_countries[1],"SAV")==0);
    std::string subject_csv;
    for (unsigned i=0;i<16;++i) {
        if (i) subject_csv.push_back(',');
        subject_csv.push_back('A');
        subject_csv.push_back('0');
        subject_csv.push_back(static_cast<char>(i<10?'0'+i:'A'+(i-10)));
    }
    const std::string max_subject_request=
        std::string("EU4PEACE_EXEC9 1 r60_max_subject release_subject FRA ENG 1 2 ")
        +"war_0123456789abcdef_01234567 demand -1 - - l - - - - - - - "
        +subject_csv+" -\n";
    wire::PeaceExecutionRequest max_subject_output{};
    expect_ok(max_subject_request.c_str(),max_subject_output);
    CHECK(max_subject_output.release_subject_count==16);
    CHECK(std::strcmp(max_subject_output.release_subject_countries[15],"A0F")==0);
    const std::string overflow_subject_request=max_subject_request.substr(
        0,max_subject_request.size()-3)+",A0G -\n";
    expect_error(overflow_subject_request,wire::ParseError::invalid_release_subject_countries);
    expect_error("EU4PEACE_EXEC8 1 r60_old_subject release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - l - - - - - - -\n",
        wire::ParseError::invalid_action);
    expect_error("EU4PEACE_EXEC9 1 r60_missing_subject demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - - m - - - - - - - - -\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC9 1 r60_wrong_subject_order release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - xl - - - - - - - TYR LEI\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC9 1 r60_duplicate_subject_bit release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - ll - - - - - - - TYR -\n",
        wire::ParseError::invalid_term_mask);
    expect_error("EU4PEACE_EXEC9 1 r60_missing_release_csv release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - l - - - - - - - - -\n",
        wire::ParseError::invalid_release_subject_countries);
    expect_error("EU4PEACE_EXEC9 1 r60_duplicate_release_csv release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - l - - - - - - - TYR,TYR -\n",
        wire::ParseError::invalid_release_subject_countries);
    expect_error("EU4PEACE_EXEC9 1 r60_overlap_subject_csv release_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - lx - - - - - - - TYR TYR\n",
        wire::ParseError::invalid_subject_overlap);
    expect_error("EU4PEACE_EXEC9 1 r60_unselected_subject_action demand_ducats FRA ENG 1 2 war_0123456789abcdef_01234567 demand 100 - - l - - - - - - - TYR -\n",
        wire::ParseError::invalid_combination);
    expect_error("EU4PEACE_EXEC9 1 r60_non_dash_unselected transfer_subject FRA ENG 1 2 war_0123456789abcdef_01234567 demand -1 - - x - - - - - - - TYR LEI\n",
        wire::ParseError::invalid_release_subject_countries);

    const char* max_partner_values[] = {
        "001","002","003","004","005","006","007","008",
        "009","00A","00B","00C","00D","00E","00F","00G",
    };
    std::string max_partners;
    for (std::size_t index=0;index<sizeof(max_partner_values)/sizeof(max_partner_values[0]);++index) {
        if (index) max_partners.push_back(',');
        max_partners+=max_partner_values[index];
    }
    const std::string max_partner_request=
        std::string("EU4PEACE_EXEC6 1 r53_max_partners annul_treaties FRA ENG 1 2 ")
        +"war_0123456789abcdef_01234567 demand -1 - - a - SAV "+max_partners+"\n";
    wire::PeaceExecutionRequest max_partner_output{};
    expect_ok(max_partner_request.c_str(),max_partner_output);
    CHECK(max_partner_output.annul_partner_count==16);
    CHECK(std::strcmp(max_partner_output.annul_partners[0],"001")==0);
    CHECK(std::strcmp(max_partner_output.annul_partners[15],"00G")==0);
    const std::string overflow_partner_request=max_partner_request.substr(
        0,max_partner_request.size()-1)+",00H\n";
    expect_error(overflow_partner_request,wire::ParseError::invalid_annul_partners);

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
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::invalid_annul_country),
        "invalid_annul_country")==0);
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::invalid_annul_partners),
        "invalid_annul_partners")==0);
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::invalid_release_subject_countries),
        "invalid_release_subject_countries")==0);
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::invalid_transfer_subject_countries),
        "invalid_transfer_subject_countries")==0);
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::invalid_subject_overlap),
        "invalid_subject_overlap")==0);
    CHECK(std::strcmp(wire::parse_error_name(wire::ParseError::ok),"ok")==0);

    if (failures) {
        std::fprintf(stderr,"%d checks failed\n",failures);
        return 1;
    }
    std::puts("peace execution wire tests passed");
    return 0;
}
