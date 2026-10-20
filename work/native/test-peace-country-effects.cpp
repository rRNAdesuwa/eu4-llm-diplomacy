#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <type_traits>
#include <windows.h>

#include "peace-effects.h"
#include "peace-execution-wire.h"
#include "peace-payload.h"
#include "alliance-authority-ledger.h"

using bridge::peace_effects::State;
using bridge::peace_execution_wire::PeaceExecutionRequest;
using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::ActionFamily;

uintptr_t base=0;
struct PeaceProvinceArrayBounds { uintptr_t begin=0,end=0; std::int32_t count=0; };
struct NativeShortString { char text[16]{}; std::uint64_t size=0,capacity=0; };

static bool global_reader_test=false;
static unsigned global_relation_count=0;
static bool global_duplicate_slot=false;
static constexpr std::uint64_t global_other1=0x10000000bull,global_other2=0x20000002cull;
template<class T> static bool read(uintptr_t address,T& output) noexcept {
    output=T{};
    if constexpr (std::is_arithmetic_v<T>) {
        if (global_reader_test) {
            std::uint64_t value=0;
            if (address==0x7000u+0x1510u) value=0xa000u;
            else if (address==0xa000u+0x48u || address==0xa000u+0x90u) value=0xb000u;
            else if (address==0xa000u+0x48u+0x10u) value=global_other1;
            else if (address==0xa000u+0x90u+0x10u) value=global_other2;
            else if (address==0xb000u+0x128u) value=0x9000u;
            else if (address==0xb000u+0x134u) value=global_relation_count;
            else if (address==0xc000u+0x18u || address==0xc100u+0x18u) value=22;
            else return false;
            output=static_cast<T>(value); return true;
        }
    }
    return false;
}
template<std::size_t N> static bool read(uintptr_t address,unsigned char (&output)[N]) noexcept {
    std::memset(output,0,N);
    if constexpr (N==16) {
        if (global_reader_test && (address==0x9000u || address==0x9010u)) {
            const int slot=address==0x9000u || global_duplicate_slot?1:2;
            const uintptr_t association=address==0x9000u?0xc000u:0xc100u;
            std::memcpy(output,&slot,4); std::memcpy(output+8,&association,8); return true;
        }
    }
    return false;
}
static bool peace_query_country_pointer(std::uint64_t country,uintptr_t& output) noexcept {
    if (global_reader_test && country==22) { output=0x7000u; return true; }
    output=0; return false;
}
static bool peace_province_tag_from_handle(std::uint64_t handle,char (&output)[4]) noexcept {
    const char* tag=handle==11?"ENG":handle==22?"FRA":handle==33?"TYR":handle==44?"AMG":nullptr;
    if (!tag) { output[0]=0; return false; }
    std::memcpy(output,tag,4); return true;
}
static bool peace_province_read_bounds(PeaceProvinceArrayBounds& output) noexcept {
    output={}; return false;
}
static bool peace_province_record_for_id(const PeaceProvinceArrayBounds&,std::int32_t,
    uintptr_t& output) noexcept { output=0; return false; }
static bool alliance_query_country(const char* tag,std::uint64_t& output) noexcept {
    if (tag && !std::strcmp(tag,"ENG")) { output=11; return true; }
    if (tag && !std::strcmp(tag,"FRA")) { output=22; return true; }
    if (tag && !std::strcmp(tag,"TYR")) { output=33; return true; }
    if (tag && !std::strcmp(tag,"AMG")) { output=44; return true; }
    output=0; return false;
}
static bool vassal_query_entry(uintptr_t record,std::uint64_t other,uintptr_t& output) noexcept {
    if (global_reader_test) {
        if (record!=0x7000u) { output=0; return false; }
        output=other==global_other1?0xc000u:other==global_other2?0xc100u:0;
        return output!=0;
    }
    output=0; return true;
}
static bool peace_reparations_state_read(std::uint64_t,std::uint64_t,std::int32_t,
    bridge::peace_effects::ReparationsState& output) noexcept { output={}; return false; }
static bool peace_trade_power_state_read(std::uint64_t,std::uint64_t,std::int32_t,
    bridge::peace_effects::TradePowerState& output) noexcept { output={}; return false; }
static bool peace_annul_treaty_state_read(std::uint64_t,std::uint64_t,std::int32_t,
    bridge::peace_effects::AnnulState& output) noexcept { output={}; return false; }
[[maybe_unused]] static bool peace_base_term_source_tag(std::uint64_t,char (&output)[4]) noexcept {
    output[0]=0; return false;
}
static void line(const char*) noexcept {}
static BOOL country_effect_read_process_memory(HANDLE,LPCVOID,LPVOID,
    SIZE_T,SIZE_T* copied) noexcept {
    if (copied) *copied=0;
    return FALSE;
}

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#define ReadProcessMemory country_effect_read_process_memory
#include "peace-effect-state.inc"
#undef ReadProcessMemory
#pragma GCC diagnostic pop

static void check(bool value,const char* name,unsigned& checks,unsigned& failures) {
    ++checks; if (!value) { ++failures; std::printf("failed:%s\n",name); }
}

static bridge::peace_effects::CountryTermProvinceState row(std::int32_t id,
    std::uint64_t owner,std::uint64_t controller) {
    bridge::peace_effects::CountryTermProvinceState value{};
    value.province_id=id; value.owner=owner; value.controller=controller;
    value.complete=true; return value;
}

static bridge::peace_effects::CountryRelationEffectState relation(
    std::uint64_t country,std::uint64_t beneficiary,bool active,bool overlord,
    const char* type) {
    bridge::peace_effects::CountryRelationEffectState value{};
    value.requested=true; value.country=country; value.beneficiary=beneficiary;
    value.relation_active_before=false; value.relation_active_after=active;
    value.is_overlord_before=false; value.is_overlord_after=overlord;
    std::snprintf(value.subject_type_before,sizeof(value.subject_type_before),"%s",
        active?"":"vassal");
    std::snprintf(value.subject_type_after,sizeof(value.subject_type_after),"%s",type);
    value.complete=true; value.values_readable=true; return value;
}

static State all_terms_before() {
    State value{}; value.complete=true; value.date_raw=100; value.country_count=4;
    value.countries[0].country=11; value.countries[1].country=22;
    value.countries[2].country=33; value.countries[3].country=44;

    value.release_nation_requested=true;
    value.release_nation.requested=true; value.release_nation.country=33;
    value.release_nation.source=11; value.release_nation.count=1;
    value.release_nation.owned_count_before=0;
    value.release_nation.source_owned_count_before=3;
    value.release_nation.owned_count_after=0;
    value.release_nation.source_owned_count_after=3;
    value.release_nation.rows[0]=row(177,11,11);
    value.release_nation.complete=true; value.release_nation.values_readable=true;

    value.force_vassalization_requested=true;
    value.force_vassalization=relation(33,22,false,false,"vassal");
    value.form_personal_union_requested=true;
    value.form_personal_union=relation(33,22,false,false,"personal_union");

    value.grant_independence_requested=true;
    value.grant_independence.requested=true; value.grant_independence.country=22;
    value.grant_independence.overlord=11;
    value.grant_independence.relation_active_before=true;
    value.grant_independence.relation_active_after=true;
    value.grant_independence.is_overlord_before=true;
    value.grant_independence.is_overlord_after=true;
    std::snprintf(value.grant_independence.subject_type_before,
        sizeof(value.grant_independence.subject_type_before),"vassal");
    std::snprintf(value.grant_independence.subject_type_after,
        sizeof(value.grant_independence.subject_type_after),"vassal");
    value.grant_independence.complete=true; value.grant_independence.values_readable=true;
    std::snprintf(value.grant_independence.reason_code,
        sizeof(value.grant_independence.reason_code),
        "INDEPENDENCE_GLOBAL_OVERLORD_NOT_VERIFIED");

    value.full_annexation_requested=true;
    value.full_annexation.requested=true; value.full_annexation.country=33;
    value.full_annexation.source=22; value.full_annexation.count=1;
    value.full_annexation.owned_count_before=1;
    value.full_annexation.source_owned_count_before=2;
    value.full_annexation.owned_count_after=1;
    value.full_annexation.source_owned_count_after=2;
    value.full_annexation.rows[0]=row(178,33,33);
    value.full_annexation.complete=true; value.full_annexation.values_readable=true;
    return value;
}

static State all_terms_after(const State& before) {
    State value=before;
    value.release_nation.owned_count_after=1;
    value.release_nation.source_owned_count_after=2;
    value.release_nation.rows[0]=row(177,33,33);

    value.force_vassalization.relation_active_after=true;
    value.force_vassalization.is_overlord_after=true;
    std::snprintf(value.force_vassalization.subject_type_after,
        sizeof(value.force_vassalization.subject_type_after),"vassal");
    value.form_personal_union.relation_active_after=true;
    value.form_personal_union.is_overlord_after=true;
    std::snprintf(value.form_personal_union.subject_type_after,
        sizeof(value.form_personal_union.subject_type_after),"personal_union");

    value.full_annexation.owned_count_after=0;
    value.full_annexation.source_owned_count_after=3;
    value.full_annexation.rows[0]=row(178,22,22);
    return value;
}

static bool contains(const char* text,const char* value) {
    return text && value && std::strstr(text,value)!=nullptr;
}

static State grant_accepted_before() {
    State value{}; value.complete=true; value.date_raw=100; value.country_count=2;
    value.countries[0].country=11; value.countries[1].country=22;
    value.grant_independence_requested=true;
    auto& grant=value.grant_independence;
    grant.requested=true; grant.country=22; grant.overlord=11;
    grant.relation_active_before=true; grant.relation_active_after=true;
    grant.is_overlord_before=true; grant.is_overlord_after=true;
    grant.overlord_count_before=1; grant.overlord_count_after=1;
    grant.overlord_scan_complete_before=true;
    grant.overlord_scan_complete_after=true;
    grant.no_other_overlords_before=false;
    grant.no_other_overlords_after=false;
    std::snprintf(grant.subject_type_before,sizeof(grant.subject_type_before),"vassal");
    std::snprintf(grant.subject_type_after,sizeof(grant.subject_type_after),"vassal");
    grant.complete=true; grant.values_readable=true;
    return value;
}

int main() {
    unsigned checks=0,failures=0;
    const State before=all_terms_before();
    const State after=all_terms_after(before);
    State partial_before=before,partial_after=after;
    partial_before.release_nation.count=partial_after.release_nation.count=2;
    partial_before.release_nation.rows[1]=row(178,11,11);
    partial_after.release_nation.rows[1]=row(178,11,11);
    check(bridge::peace_effects::release_nation_established(partial_before,partial_after),
        "release_allows_untransferred_ineligible_core",checks,failures);
    partial_after.release_nation.rows[0]=row(177,11,11);
    check(!bridge::peace_effects::release_nation_established(partial_before,partial_after),
        "release_requires_real_province_transfer",checks,failures);
    char json[32768]{}; std::size_t used=0;
    bool complete=true,readable=true,verified=true;
    check(execution_peace_effects_country_terms_json_append(json,sizeof(json),used,
        before,after,true,true,complete,readable,verified),
        "production_country_terms_serializer",checks,failures);
    json[used]=0;
    check(complete && readable && !verified,"grant_global_proof_blocks_aggregate",
        checks,failures);
    check(contains(json,"\"release_nation\"")
        && contains(json,"\"source\":\"ENG\"")
        && contains(json,"\"owner_after\":\"TYR\"")
        && contains(json,"\"verified\":true"),
        "release_rows_are_projected",checks,failures);
    check(contains(json,"\"force_vassalization\"")
        && contains(json,"\"relation_active_after\":true"),
        "force_relation_is_projected",checks,failures);
    check(contains(json,"\"form_personal_union\"")
        && contains(json,"\"subject_type_after\":\"personal_union\""),
        "personal_union_type_is_projected",checks,failures);
    check(contains(json,"\"grant_independence\"")
        && contains(json,"INDEPENDENCE_GLOBAL_OVERLORD_NOT_VERIFIED")
        && contains(json,"\"verified\":false"),
        "grant_global_proof_is_explicit",checks,failures);
    check(contains(json,"\"full_annexation\"")
        && contains(json,"\"beneficiary\":\"FRA\"")
        && contains(json,"\"owned_count_after\":0"),
        "full_annexation_uses_beneficiary",checks,failures);

    State rejected=before; bool reject_complete=true,reject_readable=true,reject_verified=true;
    char rejected_json[8192]{}; std::size_t rejected_used=0;
    check(execution_peace_effects_country_terms_json_append(rejected_json,
        sizeof(rejected_json),rejected_used,before,rejected,false,true,
        reject_complete,reject_readable,reject_verified),
        "production_rejected_serializer",checks,failures);
    rejected_json[rejected_used]=0;
    check(reject_complete && reject_readable && !reject_verified
        && contains(rejected_json,"\"unchanged\":true"),
        "rejected_terms_remain_unchanged",checks,failures);

    const State grant_before=grant_accepted_before();
    State grant_after=grant_before;
    auto& accepted=grant_after.grant_independence;
    accepted.relation_active_after=false; accepted.is_overlord_after=false;
    accepted.overlord_count_after=0; accepted.no_other_overlords_after=true;
    accepted.subject_type_after[0]=0;
    check(bridge::peace_effects::grant_independence_established(grant_before,grant_after),
        "verified_independence_state_can_establish",checks,failures);

    State wartime_independent_before=grant_before;
    auto& wartime_before_effect=wartime_independent_before.grant_independence;
    wartime_before_effect.relation_active_before=false;
    wartime_before_effect.is_overlord_before=false;
    wartime_before_effect.overlord_count_before=0;
    wartime_before_effect.no_other_overlords_before=true;
    wartime_before_effect.subject_type_before[0]=0;
    State wartime_independent_after=wartime_independent_before;
    auto& wartime_after_effect=wartime_independent_after.grant_independence;
    wartime_after_effect.relation_active_after=false;
    wartime_after_effect.is_overlord_after=false;
    wartime_after_effect.overlord_count_after=0;
    wartime_after_effect.no_other_overlords_after=true;
    wartime_after_effect.subject_type_after[0]=0;
    check(bridge::peace_effects::grant_independence_established(
            wartime_independent_before,wartime_independent_after),
        "grant_accepts_already_independent_war_snapshot",checks,failures);

    State lingering_overlord_after=grant_after;
    auto& lingering_effect=lingering_overlord_after.grant_independence;
    lingering_effect.relation_active_after=true;
    lingering_effect.is_overlord_after=true;
    lingering_effect.overlord_count_after=1;
    lingering_effect.overlord_scan_complete_after=true;
    lingering_effect.no_other_overlords_after=false;
    std::snprintf(lingering_effect.subject_type_after,
        sizeof(lingering_effect.subject_type_after),"vassal");
    check(!bridge::peace_effects::grant_independence_established(
            grant_before,lingering_overlord_after),
        "grant_rejects_remaining_overlord",checks,failures);

    State incomplete_scan_after=wartime_independent_after;
    auto& incomplete_scan_effect=incomplete_scan_after.grant_independence;
    incomplete_scan_effect.overlord_scan_complete_after=false;
    incomplete_scan_effect.no_other_overlords_after=false;
    check(!bridge::peace_effects::grant_independence_established(
            wartime_independent_before,incomplete_scan_after),
        "grant_rejects_incomplete_after_scan",checks,failures);

    char grant_json[8192]{}; std::size_t grant_used=0;
    bool grant_complete=true,grant_readable=true,grant_verified=true;
    check(execution_peace_effects_country_terms_json_append(grant_json,sizeof(grant_json),
        grant_used,grant_before,grant_after,true,true,grant_complete,grant_readable,
        grant_verified) && grant_verified && contains(grant_json,"\"verified\":true")
        && contains(grant_json,"\"reason_code\":null"),
        "accepted_grant_global_proof_is_projected",checks,failures);
    global_reader_test=true;
    std::uint32_t global_count=99; bool scan_complete=false,no_overlords=false;
    check(peace_effect_read_global_overlords(22,global_other1,global_count,scan_complete,no_overlords)
        && global_count==0 && scan_complete && no_overlords,
        "reader_resolves_handle_before_empty_vector",checks,failures);
    global_relation_count=1;
    check(peace_effect_read_global_overlords(22,global_other1,global_count,scan_complete,no_overlords)
        && global_count==1 && scan_complete && !no_overlords,
        "reader_detects_remaining_overlord",checks,failures);
    global_relation_count=2;
    check(peace_effect_read_global_overlords(22,global_other1,global_count,scan_complete,no_overlords)
        && global_count==2 && scan_complete && !no_overlords,
        "reader_counts_other_overlord",checks,failures);
    global_duplicate_slot=true;
    check(!peace_effect_read_global_overlords(22,global_other1,global_count,scan_complete,no_overlords)
        && !scan_complete && !no_overlords,"reader_rejects_duplicate_slot",checks,failures);
    std::printf("{\"passed\":%s,\"checks\":%u,\"failures\":%u,\"production_calls\":true}\n",
        failures?"false":"true",checks,failures);
    return failures?1:0;
}
