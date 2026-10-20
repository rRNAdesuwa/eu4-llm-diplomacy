#include "alliance-execution-wire.h"
#include "declarewar-selection.h"

#include <cstddef>
#include <cstdio>
#include <cstring>
#include <string>

using bridge::CountryTagList;
using bridge::kCountryTagBytes;
using bridge::kMaxCountryTags;
using bridge::alliance_execution_wire::ExecutionRequest;
using bridge::alliance_execution_wire::ParseError;
using bridge::alliance_execution_wire::kMaxWireBytes;
using bridge::alliance_execution_wire::parse_request;
using bridge::declarewar_selection::CsvError;
using bridge::declarewar_selection::parse_country_tag_csv;
using bridge::declarewar_selection::ParticipantError;
using bridge::declarewar_selection::validate_participant_selection;

static unsigned g_checks=0;
static unsigned g_failures=0;

static void check(bool condition,const char* name) {
    ++g_checks;
    if (!condition) {
        ++g_failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static std::string join_fields(const std::string* fields,std::size_t count) {
    std::string wire;
    for (std::size_t index=0;index<count;++index) {
        if (index) wire+='|';
        wire+=fields[index];
    }
    wire+='\n';
    return wire;
}

static std::string wire_for_v4(const char* call_allies="-",
    const char* promise_land_to="-",const char* co_belligerents="-",
    const char* action="declare_war",const char* cb="conquest",
    std::int32_t province=123,const char* beneficiary="---",
    const char* actor="FRA",const char* recipient="SAV") {
    const std::string fields[] = {
        "EU4DIP_EXEC4", "req_01", "1234-1abc", "1100000000", "42",
        action, actor, recipient, "initiate", cb, std::to_string(province),
        beneficiary, call_allies, promise_land_to, co_belligerents,
    };
    return join_fields(fields,sizeof(fields)/sizeof(fields[0]));
}

static std::string wire_for_v3() {
    const std::string fields[] = {
        "EU4DIP_EXEC3", "req_01", "1234-1abc", "1100000000", "42",
        "declare_war", "FRA", "SAV", "initiate", "conquest", "123", "---",
    };
    return join_fields(fields,sizeof(fields)/sizeof(fields[0]));
}

static std::string wire_for_v1() {
    const std::string fields[] = {
        "v1", "req_01", "1234-1abc", "1100000000", "42",
        "offer_alliance", "FRA", "SAV", "initiate",
    };
    return join_fields(fields,sizeof(fields)/sizeof(fields[0]));
}

static std::string wire_for_v2() {
    const std::string fields[] = {
        "v2", "req_01", "1234-1abc", "1100000000", "42",
        "send_insult", "FRA", "SAV", "initiate", "-1",
    };
    return join_fields(fields,sizeof(fields)/sizeof(fields[0]));
}

static void expect_csv_error(const char* csv,CsvError expected,const char* name) {
    CountryTagList output{};
    const auto result=parse_country_tag_csv(csv,output);
    check(result.error==expected,name);
}

static void expect_wire_error(const std::string& wire,ParseError expected,
    const char* name) {
    ExecutionRequest request{};
    const auto result=parse_request(wire.data(),wire.size(),request);
    check(result.error==expected,name);
}

static void test_csv_parser() {
    static_assert(sizeof(CountryTagList)==kMaxCountryTags*4u+sizeof(std::uint32_t),
        "country tag list must remain fixed capacity");
    static_assert(kCountryTagBytes==4,"country tags must retain a NUL");

    CountryTagList empty{};
    check(parse_country_tag_csv("-",empty).ok(),"csv_empty_marker_valid");
    check(empty.count==0,"csv_empty_marker_count");

    CountryTagList sorted{};
    check(parse_country_tag_csv("AAA,AAB,AAC",sorted).ok(),"csv_sorted_valid");
    check(sorted.count==3,"csv_sorted_count");
    check(std::strcmp(sorted.tags[1],"AAB")==0,"csv_tag_copied");
    expect_csv_error("AAA,AAA",CsvError::duplicate_tag,"csv_duplicate_rejected");
    expect_csv_error("AAB,AAA",CsvError::unsorted_tags,"csv_unsorted_rejected");
    expect_csv_error("AAA,aab",CsvError::invalid_tag,"csv_lowercase_rejected");
    expect_csv_error("AA",CsvError::invalid_tag,"csv_short_tag_rejected");
    expect_csv_error("AAA,",CsvError::empty_tag,"csv_trailing_empty_rejected");
    expect_csv_error("- ,AAA",CsvError::invalid_tag,"csv_marker_must_be_exact");
    expect_csv_error("",CsvError::empty_input,"csv_empty_string_rejected");

    const char* too_many="AAA,AAB,AAC,AAD,AAE,AAF,AAG,AAH,AAI,AAJ,AAK,AAL,AAM,AAN,AAO,AAP,AAQ";
    expect_csv_error(too_many,CsvError::too_many_tags,"csv_seventeenth_tag_rejected");
    CountryTagList bounded{};
    const std::string bounded_text="AAA,AAB";
    check(parse_country_tag_csv(bounded_text.data(),bounded_text.size(),bounded).ok(),
        "csv_explicit_length_valid");
    check(bounded.count==2,"csv_explicit_length_count");
    check(parse_country_tag_csv(bounded_text.data(),bounded_text.size()-1,bounded).error
        ==CsvError::invalid_tag,"csv_explicit_length_truncation_rejected");
}

static void test_participant_rules() {
    CountryTagList call{};
    CountryTagList promise{};
    CountryTagList co{};
    check(parse_country_tag_csv("AAA,AAB,AAC",call).ok(),"participants_call_setup");
    check(parse_country_tag_csv("AAA,AAC",promise).ok(),"participants_promise_setup");
    check(parse_country_tag_csv("ABA,ABB",co).ok(),"participants_co_setup");
    auto result=validate_participant_selection(call,promise,co,"FRA","SAV");
    check(result.ok(),"participants_valid");
    check(validate_participant_selection("FRA","SAV",call,promise,co).ok(),
        "participants_alternate_argument_order");

    CountryTagList outside{};
    parse_country_tag_csv("AAD",outside);
    result=validate_participant_selection(call,outside,co,"FRA","SAV");
    check(result.error==ParticipantError::promise_not_subset,
        "promise_must_be_subset_call_allies");

    CountryTagList overlap{};
    parse_country_tag_csv("AAB",overlap);
    result=validate_participant_selection(call,promise,overlap,"FRA","SAV");
    check(result.error==ParticipantError::participant_lists_overlap,
        "call_and_co_must_be_disjoint");

    CountryTagList actor{};
    parse_country_tag_csv("FRA",actor);
    result=validate_participant_selection(actor,promise,co,"FRA","SAV");
    check(result.error==ParticipantError::actor_in_participant_list,
        "actor_forbidden_in_lists");
    CountryTagList recipient{};
    parse_country_tag_csv("SAV",recipient);
    result=validate_participant_selection(call,promise,recipient,"FRA","SAV");
    check(result.error==ParticipantError::recipient_in_participant_list,
        "recipient_forbidden_in_lists");

    CountryTagList malformed{};
    malformed.count=2;
    std::memcpy(malformed.tags[0],"AAB",4);
    std::memcpy(malformed.tags[1],"AAA",4);
    result=validate_participant_selection(malformed,promise,co,"FRA","SAV");
    check(result.error==ParticipantError::invalid_call_allies,
        "manually_unsorted_list_rejected");
}

static void test_exec4_and_legacy() {
    static_assert(sizeof("EU4DIP_EXEC4")==13,"EXEC4 marker must remain exact");
    static_assert(offsetof(ExecutionRequest,call_allies)
        >offsetof(ExecutionRequest,war_goal_beneficiary),
        "EXEC4 fields must append after the EXEC3 prefix");
    static_assert(offsetof(ExecutionRequest,promise_land_to)
        ==offsetof(ExecutionRequest,call_allies)+sizeof(CountryTagList),
        "promise list must follow call list");
    static_assert(offsetof(ExecutionRequest,co_belligerents)
        ==offsetof(ExecutionRequest,promise_land_to)+sizeof(CountryTagList),
        "co-belligerent list must follow promise list");
    static_assert(offsetof(ExecutionRequest,call_allies)==308,
        "EXEC4 call-allies offset must preserve the legacy prefix");
    static_assert(sizeof(ExecutionRequest)==512,
        "EXEC4 request must end after the three fixed participant lists");

    ExecutionRequest request{};
    const std::string valid=wire_for_v4("AAA,AAB,AAC","AAA,AAC","ABA,ABB");
    check(valid.size()<=kMaxWireBytes,"exec4_wire_within_512_bytes");
    check(parse_request(valid.data(),valid.size(),request).ok(),"exec4_valid");
    check(request.call_allies.count==3,"exec4_call_allies_count");
    check(request.promise_land_to.count==2,"exec4_promise_count");
    check(request.co_belligerents.count==2,"exec4_co_count");
    check(std::strcmp(request.call_allies.tags[2],"AAC")==0,
        "exec4_call_tag_copied");

    // Exercise the actual fixed-capacity and wire-size limits together.  The
    // three lists are disjoint, the promise list is a subset of call-allies,
    // and every list contains the full sixteen canonical tags.
    const char* max_call=
        "AAA,AAB,AAC,AAD,AAE,AAF,AAG,AAH,AAI,AAJ,AAK,AAL,AAM,AAN,AAO,AAP";
    const char* max_co=
        "ABA,ABB,ABC,ABD,ABE,ABF,ABG,ABH,ABI,ABJ,ABK,ABL,ABM,ABN,ABO,ABP";
    const std::string max_cb(128,'a');
    const std::string max_fields[] = {
        "EU4DIP_EXEC4", std::string(64,'a'),
        "4294967295-ffffffffffffffff", "18446744073709551615", "2147483647",
        "declare_war", "FRA", "YYY", "initiate", max_cb, "2147483647", "ZZZ",
        max_call, max_call, max_co,
    };
    const std::string max_wire=join_fields(max_fields,
        sizeof(max_fields)/sizeof(max_fields[0]));
    check(max_wire.size()<=kMaxWireBytes,"exec4_max_wire_within_512_bytes");
    ExecutionRequest max_request{};
    const auto max_result=parse_request(max_wire.data(),max_wire.size(),max_request);
    check(max_result.ok(),
        "exec4_max_wire_valid");
    check(max_request.call_allies.count==kMaxCountryTags,
        "exec4_max_call_allies_count");
    check(max_request.promise_land_to.count==kMaxCountryTags,
        "exec4_max_promise_count");
    check(max_request.co_belligerents.count==kMaxCountryTags,
        "exec4_max_co_count");

    expect_wire_error(wire_for_v4("AAB,AAA","AAB","-"),
        ParseError::invalid_call_allies,"exec4_unsorted_call_rejected");
    expect_wire_error(wire_for_v4("AAA","AAB","-"),
        ParseError::invalid_participant_selection,"exec4_promise_subset_rejected");
    expect_wire_error(wire_for_v4("AAA","AAA","AAA"),
        ParseError::invalid_participant_selection,"exec4_overlap_rejected");
    expect_wire_error(wire_for_v4("FRA","-","-"),
        ParseError::invalid_participant_selection,"exec4_actor_rejected");
    expect_wire_error(wire_for_v4("-","-","SAV"),
        ParseError::invalid_participant_selection,"exec4_recipient_rejected");
    expect_wire_error(wire_for_v4("AAA","-","-","offer_alliance"),
        ParseError::invalid_action,"exec4_non_declare_action_rejected");

    const std::string v3=wire_for_v3();
    check(parse_request(v3.data(),v3.size(),request).ok(),"exec3_still_valid");
    check(request.call_allies.count==0 && request.promise_land_to.count==0
        && request.co_belligerents.count==0,"exec3_lists_default_empty");
    const std::string v1=wire_for_v1();
    check(parse_request(v1.data(),v1.size(),request).ok(),"exec1_still_valid");
    const std::string v2=wire_for_v2();
    check(parse_request(v2.data(),v2.size(),request).ok(),"exec2_still_valid");
    std::string v3_tail=v3;
    v3_tail.insert(v3_tail.size()-1,"|-|-|-" );
    expect_wire_error(v3_tail,ParseError::field_count,
        "exec3_cannot_carry_exec4_lists");
    std::string v4_missing=valid;
    v4_missing.resize(v4_missing.find_last_of('|')+1u);
    v4_missing.push_back('\n');
    expect_wire_error(v4_missing,ParseError::empty_field,
        "exec4_requires_all_three_lists");
}

int main() {
    test_csv_parser();
    test_participant_rules();
    test_exec4_and_legacy();
    std::printf("fixture=declarewar_selection checks=%u failures=%u\n",
        g_checks,g_failures);
    return g_failures==0?0:1;
}

