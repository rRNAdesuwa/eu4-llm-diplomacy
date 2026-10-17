#include <cstdint>
#include <cstdio>

#include "peace-payload.h"

using namespace bridge::peace_payload;

static unsigned g_checks=0;
static unsigned g_failures=0;

static void check(bool value,const char* name) {
    ++g_checks;
    if (!value) {
        ++g_failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static PeaceTermPayload complete_term(std::uint32_t type=0x2d2bu,
    std::uint32_t bucket=0u) {
    PeaceTermPayload value{};
    value.type_id=type;
    value.bucket=bucket;
    value.field10=0x1111222233334444ull;
    value.field18=0x5555666677778888ull;
    value.field22=0x9999aaaabbbbccccull;
    value.extra30=0x123456789abcdef0ull;
    value.gold_raw=42;
    value.selected=1u;
    value.selected_index=3u;
    value.complete=true;
    return value;
}

static PeaceOfferPayload complete_offer() {
    PeaceOfferPayload value{};
    value.payer=0x465241ull;
    value.claimant=0x454e47ull;
    value.direction=1u;
    value.flag1b9=1u;
    value.participants[0].count=2u;
    value.participants[0].values[0]=0x465241ull;
    value.participants[0].values[1]=0x454e47ull;
    value.terms[0]=complete_term();
    value.term_count=1u;
    value.complete=true;
    return value;
}

static void test_type_whitelist() {
    check(kPeaceTermTypeWhitelist.size()==40u,"whitelist_has_40_rows");
    const auto* gold=peace_find_term_type(0x1cd2190u);
    check(gold!=nullptr && gold->type_id==0x2d2bu
        && gold->bucket==0u
        && gold->serializer_rva==0x9b42b0u
        && gold->extra_kind==PeaceTermExtraKind::gold,
        "gold_descriptor");
    check(peace_find_term_type_id(0x2d2bu)==gold,
        "type_id_round_trip");
    const auto* type3=peace_find_term_type(0x1cd4ad8u);
    const auto* unsupported_colony=peace_find_term_type(0x1cd2568u);
    check(type3!=nullptr
        && type3->extra_kind==PeaceTermExtraKind::nested38flag40
        && peace_term_type_supported(*type3),
        "nested38_flag40_descriptor");
    const auto* definition_name=peace_find_term_type(0x1cd1f00u);
    check(definition_name!=nullptr
        && definition_name->extra_kind==PeaceTermExtraKind::definition_name30
        && peace_term_type_supported(*definition_name),
        "definition_name30_descriptor");
    check(unsupported_colony!=nullptr
        && unsupported_colony->extra_kind==PeaceTermExtraKind::region_name30
        && peace_term_type_supported(*unsupported_colony),
        "region_name30_descriptor");
    const auto* nested=peace_find_term_type(0x1cd3778u);
    check(nested!=nullptr && nested->extra_kind==PeaceTermExtraKind::nested38,
        "nested38_descriptor");
    check(peace_find_term_type(0xdeadbeefu)==nullptr,
        "unknown_vtable_rejected");

    struct AddedType {
        std::uintptr_t vtable;
        std::uint32_t type;
        std::uint32_t bucket;
        std::uintptr_t serializer;
        PeaceTermExtraKind extra_kind;
    };
    const AddedType added[]={
        {0x1cd4ad8u,0x2d25u,3u,0x9a37d0u,
            PeaceTermExtraKind::nested38flag40},
        {0x1cd4988u,0x2e00u,5u,0x99e630u,
            PeaceTermExtraKind::nested38},
        {0x1cd3628u,0x301bu,6u,0x99e480u,
            PeaceTermExtraKind::handle30},
        {0x1cd3100u,0x2d28u,15u,0x99e480u,
            PeaceTermExtraKind::handle30},
        {0x1cd41c8u,0x35c5u,30u,0x99e480u,
            PeaceTermExtraKind::handle30},
        {0x1cd17f8u,0x3c06u,31u,0x99e480u,
            PeaceTermExtraKind::handle30},
    };
    for (const auto& expected: added) {
        const auto* descriptor=peace_find_term_type(expected.vtable);
        check(descriptor!=nullptr
            && descriptor->type_id==expected.type
            && descriptor->bucket==expected.bucket
            && descriptor->serializer_rva==expected.serializer
            && descriptor->extra_kind==expected.extra_kind,
            "factory_audit_type_present");
    }
}

static void test_address_independent_equality() {
    PeaceOfferPayload first=complete_offer();
    PeaceOfferPayload second=first;
    second.participants[0].values[255]=0xdeadbeefull;
    second.terms[511].field10=0xfeedfaceull;
    check(first.valid() && second.valid(),"complete_payloads_valid");
    check(first==second,"unused_capacity_is_ignored");

    second.terms[0].field18^=1u;
    check(first!=second,"term_value_changes_equality");
    second=first;
    second.terms[0].selected_index=4u;
    check(first!=second,"selected_index_changes_equality");
    second=first;
    second.terms[0].flag40=1u;
    check(first!=second,"flag40_changes_equality");
    first.terms[0].definition_name_size=3u;
    first.terms[0].definition_name[0]='c';
    first.terms[0].definition_name[1]='b';
    first.terms[0].definition_name[2]='_';
    second=first;
    second.terms[0].definition_name[1]='x';
    check(first!=second,"definition_name_changes_equality");
}

static void test_incomplete_and_bounds() {
    PeaceOfferPayload incomplete=complete_offer();
    incomplete.complete=false;
    check(!incomplete.valid() && !(incomplete==incomplete),
        "incomplete_offer_never_equals");

    PeaceTermPayload incomplete_term=complete_term();
    incomplete_term.complete=false;
    check(!incomplete_term.valid() && !(incomplete_term==incomplete_term),
        "incomplete_term_never_equals");

    PeaceOfferPayload too_many_terms=complete_offer();
    too_many_terms.term_count=static_cast<std::uint32_t>(kMaxPeaceTerms+1u);
    check(!too_many_terms.valid(),"term_count_bound");

    PeaceOfferPayload too_many_participants=complete_offer();
    too_many_participants.participants[0].count=
        static_cast<std::uint32_t>(kMaxPeaceParticipants+1u);
    check(!too_many_participants.valid(),"participant_count_bound");

    PeaceTermPayload bad_selection=complete_term();
    bad_selection.selected_index=kInvalidSelectedIndex;
    check(!bad_selection.valid(),"selected_index_required");
    bad_selection=complete_term();
    bad_selection.selected=0u;
    bad_selection.selected_index=3u;
    check(!bad_selection.valid(),"unselected_index_rejected");

    PeaceTermPayload stale_nested=complete_term();
    stale_nested.nested_id=7u;
    stale_nested.nested_present=false;
    check(!stale_nested.valid(),"stale_nested_value_rejected");

    PeaceTermPayload oversized_name=complete_term();
    oversized_name.definition_name_size=
        static_cast<std::uint32_t>(kMaxPeaceDefinitionNameBytes+1u);
    check(!oversized_name.valid(),"definition_name_size_bound");
}

int main() {
    test_type_whitelist();
    test_address_independent_equality();
    test_incomplete_and_bounds();
    std::printf("checks=%u failures=%u\n",g_checks,g_failures);
    return g_failures?1:0;
}
