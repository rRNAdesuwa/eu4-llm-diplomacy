#include <cstdint>
#include <cstdio>
#include <cstring>

#include "alliance-authority-ledger.h"

using bridge::alliance_authority::AllianceAuthorityLedger;
using bridge::alliance_authority::AlliancePayload;
using bridge::alliance_authority::ActionFamily;
using bridge::alliance_authority::ClaimResult;
using bridge::alliance_authority::ClaimTicket;
using bridge::alliance_authority::CloneProof;
using bridge::alliance_authority::Context;
using bridge::alliance_authority::ErrorCode;
using bridge::alliance_authority::NativeHeader;
using bridge::alliance_authority::ObjectRef;
using bridge::alliance_authority::OperationResult;
using bridge::alliance_authority::Phase;
using bridge::alliance_authority::SeedResult;
using bridge::alliance_authority::SourceKind;
using bridge::alliance_authority::State;
using bridge::peace_payload::PeacePayloadRef;

static unsigned g_checks=0;
static unsigned g_failures=0;

static void check(bool condition,const char* name) {
    ++g_checks;
    if (!condition) {
        ++g_failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static bool is_code(const OperationResult& result,ErrorCode code) {
    return result.code==code;
}

static AlliancePayload payload_for(std::uint64_t salt,
    Phase phase=Phase::accept) {
    const std::uint64_t actor=0x1000u+salt;
    const std::uint64_t recipient=0x2000u+salt;
    const std::uint64_t variant=phase==Phase::dissolve?0u:1u;
    const std::uint64_t state=phase==Phase::accept?2u:
        (phase==Phase::reject?1u:0u);
    return AlliancePayload{
        actor,actor,recipient,
        0x2800u+salt,0x2c00u+salt,0x3000u+salt,
        state,variant,0x3c00u+salt};
}

static ObjectRef wrapper_for(std::uint64_t salt) {
    return ObjectRef{static_cast<std::uintptr_t>(0x100000u+salt*0x100u),
        1u+salt};
}

static ObjectRef action_for(std::uint64_t salt) {
    return ObjectRef{static_cast<std::uintptr_t>(0x200000u+salt*0x100u),
        11u+salt};
}

static ObjectRef with_generation(ObjectRef value,std::uint64_t generation) {
    value.generation=generation;
    return value;
}

static NativeHeader header_for(std::uint32_t sequence) {
    return NativeHeader{0x1234u,0x05u,sequence};
}

static CloneProof clone_for(ObjectRef source_wrapper,ObjectRef source_action,
    ObjectRef target_wrapper,ObjectRef target_action,
    const AlliancePayload& payload,std::uint32_t sequence) {
    return CloneProof{source_wrapper,source_action,target_wrapper,target_action,
        payload,bridge::alliance_authority::kTransferCloneHeader,
        NativeHeader{0xffffu,0u,sequence}};
}

static AlliancePayload declare_war_payload_for(std::uint64_t salt) {
    AlliancePayload payload=payload_for(salt,Phase::initiate);
    payload.family=ActionFamily::declare_war;
    payload.state34=0u;
    payload.variant38=1u;
    payload.war.flag40=1u;
    payload.war.flag41=2u;
    payload.war.flag42=3u;
    payload.war.owned_present=true;
    payload.war.owned.owned_field08=0x165u;
    payload.war.owned.owned_field10=0x100000000ULL+salt;
    payload.war.owned.owned_field18=0x180u+static_cast<std::uint32_t>(salt);
    payload.war.owned.owned_field1c=0x1c000000ULL+salt;
    payload.war.owned.owned_field28=0x28000000ULL+salt;
    payload.war.owned.owned_field30=0x30000000ULL+salt;
    payload.war.owned.owned_field38=0x38000000ULL+salt;
    payload.war.owned.owned_field40=0x40000000ULL+salt;
    payload.war.owned.owned_field48=0x48000000ULL+salt;
    payload.war.owned.owned_field50=0x50000000ULL+salt;
    payload.war.owned.owned_field58=0x58000000ULL+salt;
    payload.war.container50.count=2u;
    payload.war.container50.values[0]=0x500000000ULL+salt;
    payload.war.container50.values[1]=0x500000001ULL+salt;
    payload.war.container68.count=1u;
    payload.war.container68.values[0]=0x680000000ULL+salt;
    payload.war.container80.count=3u;
    payload.war.container80.values[0]=0x800000000ULL+salt;
    payload.war.container80.values[1]=0x800000001ULL+salt;
    payload.war.container80.values[2]=0x800000002ULL+salt;
    return payload;
}

static PeacePayloadRef peace_offer_for(std::uint64_t actor,
    std::uint64_t claimant,std::uint64_t payer,
    int amount=10000,std::uint32_t selected_index=0,
    std::uint64_t participant=0,bool demand=true) {
    PeacePayloadRef reference=PeacePayloadRef::allocate();
    auto* offer=reference.builder();
    if (!offer) return {};
    offer->payer=payer;
    offer->claimant=claimant;
    offer->direction=demand?1:0;
    offer->flag1b9=1;
    if (participant) {
        offer->participants[0].count=1;
        offer->participants[0].values[0]=participant;
    }
    offer->term_count=1;
    auto& gold=offer->terms[0];
    gold.type_id=0x2d2bu;
    gold.bucket=0;
    gold.gold_raw=amount;
    gold.selected=1;
    gold.selected_index=selected_index;
    gold.complete=true;
    offer->complete=true;
    if (!reference.seal()) return {};
    (void)actor;
    return reference;
}

static AlliancePayload peace_payload_for(std::uint64_t salt,
    int amount=10000,std::uint32_t selected_index=0,
    std::uint64_t participant=0,bool demand=true) {
    AlliancePayload payload=payload_for(salt,Phase::initiate);
    const std::uint64_t actor=payload.actor10;
    const std::uint64_t recipient=payload.recipient20;
    payload.family=ActionFamily::peace;
    payload.state34=0;
    payload.variant38=1;
    payload.proposal3c=0;
    payload.extra60=0;
    payload.parameter40=0;
    const std::uint64_t claimant=demand?actor:recipient;
    const std::uint64_t payer=demand?recipient:actor;
    payload.peace.offer=peace_offer_for(actor,claimant,payer,amount,
        selected_index,participant,demand);
    payload.peace.flag40=1;
    payload.peace.direction41=demand?1:0;
    payload.peace.preview208=0;
    return payload;
}

static void test_peace_handler_payload_matching() {
    AlliancePayload expected=peace_payload_for(730u);
    expected.envoy30=std::numeric_limits<std::uint32_t>::max();

    AlliancePayload exact=expected;
    check(bridge::alliance_authority::peace_handler_payload_matches(
        expected,exact,false),"peace_handler_exact_equal_allowed");

    AlliancePayload rebuilt=expected;
    rebuilt.envoy30=2u;
    check(bridge::alliance_authority::peace_handler_payload_matches(
        expected,rebuilt,true),"peace_handler_verified_envoy_rebuild");
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,rebuilt,false),"peace_handler_unverified_envoy_rejected");

    AlliancePayload invalid_envoy=expected;
    invalid_envoy.envoy30=256u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,invalid_envoy,true),"peace_handler_envoy_out_of_range_rejected");
    invalid_envoy.envoy30=0x100000000ULL;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,invalid_envoy,true),"peace_handler_envoy_uint32_overflow_rejected");
    AlliancePayload invalid_expected=expected;
    invalid_expected.envoy30=0x100000000ULL;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        invalid_expected,invalid_expected,false),
        "peace_handler_expected_envoy_uint32_overflow_rejected");

    AlliancePayload non_sentinel=expected;
    non_sentinel.envoy30=7u;
    AlliancePayload changed_non_sentinel=non_sentinel;
    changed_non_sentinel.envoy30=2u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        non_sentinel,changed_non_sentinel,true),
        "peace_handler_non_sentinel_replacement_rejected");
    AlliancePayload exact_regular=non_sentinel;
    check(bridge::alliance_authority::peace_handler_payload_matches(
        non_sentinel,exact_regular,false),
        "peace_handler_regular_exact_equal_allowed");

    AlliancePayload wrong_family=rebuilt;
    wrong_family.family=ActionFamily::alliance;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,wrong_family,true),"peace_handler_family_mismatch_rejected");
    AlliancePayload wrong_state=rebuilt;
    wrong_state.state34=1u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,wrong_state,true),"peace_handler_state_mismatch_rejected");

    AlliancePayload wrong_actor=rebuilt;
    wrong_actor.actor10^=1u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,wrong_actor,true),"peace_handler_actor_mismatch_rejected");
    AlliancePayload wrong_recipient=rebuilt;
    wrong_recipient.recipient20^=1u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,wrong_recipient,true),"peace_handler_recipient_mismatch_rejected");
    AlliancePayload wrong_date=rebuilt;
    wrong_date.date2c^=1u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,wrong_date,true),"peace_handler_date_mismatch_rejected");
    AlliancePayload wrong_direction=rebuilt;
    wrong_direction.peace.direction41=0u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,wrong_direction,true),"peace_handler_direction_mismatch_rejected");

    AlliancePayload wrong_terms=peace_payload_for(730u,10001);
    wrong_terms.envoy30=2u;
    check(!bridge::alliance_authority::peace_handler_payload_matches(
        expected,wrong_terms,true),"peace_handler_terms_mismatch_rejected");
}

static void expect_declare_war_payload_mismatch(
    const AlliancePayload& expected,const AlliancePayload& changed,
    std::uint64_t salt,const char* name) {
    const std::uint64_t epoch=0xd400u+salt;
    AllianceAuthorityLedger ledger(epoch);
    const Context context{epoch,1u};
    const ObjectRef wrapper=wrapper_for(700u+salt);
    const ObjectRef action=action_for(700u+salt);
    const SeedResult seeded=ledger.seed(context,"declare-war-mutation",
        expected,Phase::initiate,wrapper,action,100u);
    check(seeded.result.ok(),"declare_war_mutation_seed");
    check(is_code(ledger.serializer(context,seeded.receipt,Phase::initiate,
        wrapper,action,changed,header_for(static_cast<std::uint32_t>(salt))),
        ErrorCode::payload_mismatch),name);
}

static void test_declare_war_lifecycle_and_isolation() {
    const std::uint64_t epoch=0xd370u;
    AllianceAuthorityLedger ledger(epoch);
    const Context context{epoch,10u};
    const AlliancePayload war=declare_war_payload_for(600u);
    const ObjectRef outgoing_wrapper=wrapper_for(600u);
    const ObjectRef outgoing_action=action_for(600u);
    const ObjectRef incoming_wrapper=wrapper_for(601u);
    const ObjectRef incoming_action=action_for(601u);
    const ObjectRef target_wrapper=wrapper_for(602u);
    const ObjectRef target_action=action_for(602u);
    const NativeHeader source_header=header_for(600u);

    const SeedResult seeded=ledger.seed(context,"declare-war-lifecycle",war,
        Phase::initiate,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"declare_war_lifecycle_seed");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        outgoing_wrapper,outgoing_action,war,source_header).ok(),
        "declare_war_source_serialization");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::initiate,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"declare_war_source_detached");

    AlliancePayload wrong_family=payload_for(600u,Phase::initiate);
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,
        wrong_family,true).result,ErrorCode::payload_mismatch),
        "declare_war_inbound_alliance_mismatch");
    const ClaimResult claimed=ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,war,true);
    check(claimed.result.ok(),"declare_war_inbound_claim");

    const CloneProof valid_proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,target_action,war,source_header.seq);
    CloneProof wrong_transport=valid_proof;
    wrong_transport.payload=wrong_family;
    check(is_code(ledger.postclone(context,claimed.ticket,Phase::initiate,
        wrong_transport),ErrorCode::payload_mismatch),
        "declare_war_transport_alliance_mismatch");
    check(ledger.postclone(context,claimed.ticket,Phase::initiate,
        valid_proof).ok(),"declare_war_transport_clone");
    check(is_code(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,wrong_family,valid_proof.final_entry_header),
        ErrorCode::payload_mismatch),"declare_war_execution_alliance_mismatch");
    check(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,war,valid_proof.final_entry_header).ok(),
        "declare_war_execution_consume");
    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && inspected.view.payload.family==ActionFamily::declare_war
        && inspected.view.payload.war==war.war,
        "declare_war_payload_preserved_after_cycle");

    check(is_code(ledger.seed(context,"declare-war-accept-phase",war,
        Phase::accept,wrapper_for(610u),action_for(610u),100u).result,
        ErrorCode::invalid_payload),"declare_war_accept_phase_rejected");
    check(is_code(ledger.seed(context,"declare-war-reject-phase",war,
        Phase::reject,wrapper_for(611u),action_for(611u),100u).result,
        ErrorCode::invalid_payload),"declare_war_reject_phase_rejected");
    check(is_code(ledger.seed(context,"declare-war-dissolve-phase",war,
        Phase::dissolve,wrapper_for(612u),action_for(612u),100u).result,
        ErrorCode::invalid_payload),"declare_war_dissolve_phase_rejected");

    AlliancePayload bad_owned=war;
    bad_owned.war.owned.owned_field08=0x166u;
    check(is_code(ledger.seed(context,"declare-war-owned-sentinel",bad_owned,
        Phase::initiate,wrapper_for(613u),action_for(613u),100u).result,
        ErrorCode::invalid_payload),"declare_war_owned_sentinel_rejected");
    AlliancePayload bad_extra=war;
    bad_extra.extra60=1u;
    check(is_code(ledger.seed(context,"declare-war-extra60",bad_extra,
        Phase::initiate,wrapper_for(614u),action_for(614u),100u).result,
        ErrorCode::invalid_payload),"declare_war_extra60_rejected");
    AlliancePayload bad_parameter=war;
    bad_parameter.parameter40=1;
    check(is_code(ledger.seed(context,"declare-war-parameter40",bad_parameter,
        Phase::initiate,wrapper_for(615u),action_for(615u),100u).result,
        ErrorCode::invalid_payload),"declare_war_parameter40_rejected");
    AlliancePayload bad_state=war;
    bad_state.state34=1u;
    check(is_code(ledger.seed(context,"declare-war-state",bad_state,
        Phase::initiate,wrapper_for(616u),action_for(616u),100u).result,
        ErrorCode::invalid_payload),"declare_war_state_rejected");
    AlliancePayload bad_variant=war;
    bad_variant.variant38=0u;
    check(is_code(ledger.seed(context,"declare-war-variant",bad_variant,
        Phase::initiate,wrapper_for(617u),action_for(617u),100u).result,
        ErrorCode::invalid_payload),"declare_war_variant_rejected");
    AlliancePayload bad_vector=war;
    bad_vector.war.container50.count=129u;
    check(is_code(ledger.seed(context,"declare-war-vector-bound",bad_vector,
        Phase::initiate,wrapper_for(618u),action_for(618u),100u).result,
        ErrorCode::invalid_payload),"declare_war_vector_bound_rejected");
    AlliancePayload bad_family=war;
    bad_family.family=static_cast<ActionFamily>(0xffu);
    check(is_code(ledger.seed(context,"declare-war-unknown-family",bad_family,
        Phase::initiate,wrapper_for(619u),action_for(619u),100u).result,
        ErrorCode::invalid_payload),"declare_war_unknown_family_rejected");
    AlliancePayload non_war_with_extension=payload_for(620u,Phase::initiate);
    non_war_with_extension.war=war.war;
    check(is_code(ledger.seed(context,"alliance-war-extension",non_war_with_extension,
        Phase::initiate,wrapper_for(620u),action_for(620u),100u).result,
        ErrorCode::invalid_payload),"alliance_war_extension_rejected");

    AlliancePayload changed=war;
    changed.war.owned.owned_field10^=1u;
    expect_declare_war_payload_mismatch(war,changed,621u,
        "declare_war_owned_field10_mismatch");
    changed=war;
    changed.war.owned.owned_field18^=1u;
    expect_declare_war_payload_mismatch(war,changed,622u,
        "declare_war_owned_field18_mismatch");
    changed=war;
    changed.war.owned.owned_field1c^=1u;
    expect_declare_war_payload_mismatch(war,changed,629u,
        "declare_war_owned_field1c_mismatch");
    changed=war;
    changed.war.container50.values[0]^=1u;
    expect_declare_war_payload_mismatch(war,changed,623u,
        "declare_war_container50_mismatch");
    changed=war;
    changed.war.container68.count=2u;
    changed.war.container68.values[1]=0x680000001ULL;
    expect_declare_war_payload_mismatch(war,changed,624u,
        "declare_war_container68_mismatch");
    changed=war;
    changed.war.container80.values[1]^=1u;
    expect_declare_war_payload_mismatch(war,changed,625u,
        "declare_war_container80_mismatch");
    changed=war;
    changed.war.flag40^=1u;
    expect_declare_war_payload_mismatch(war,changed,626u,
        "declare_war_flag40_mismatch");
    changed=war;
    changed.war.flag41^=1u;
    expect_declare_war_payload_mismatch(war,changed,627u,
        "declare_war_flag41_mismatch");
    changed=war;
    changed.war.flag42^=1u;
    expect_declare_war_payload_mismatch(war,changed,628u,
        "declare_war_flag42_mismatch");
}

static void expect_peace_payload_mismatch(
    const AlliancePayload& expected,const AlliancePayload& changed,
    std::uint64_t salt,const char* name) {
    const std::uint64_t epoch=0xe400u+salt;
    AllianceAuthorityLedger ledger(epoch);
    const Context context{epoch,1u};
    const ObjectRef wrapper=wrapper_for(900u+salt);
    const ObjectRef action=action_for(900u+salt);
    const SeedResult seeded=ledger.seed(context,"peace-mutation",
        expected,Phase::initiate,wrapper,action,100u);
    check(seeded.result.ok(),"peace_mutation_seed");
    check(is_code(ledger.serializer(context,seeded.receipt,Phase::initiate,
        wrapper,action,changed,header_for(static_cast<std::uint32_t>(salt))),
        ErrorCode::payload_mismatch),name);
}

static void test_peace_lifecycle_and_isolation() {
    const std::uint64_t epoch=0xe300u;
    AllianceAuthorityLedger ledger(epoch);
    const Context context{epoch,10u};
    const AlliancePayload peace=peace_payload_for(700u);
    const AlliancePayload independent=peace_payload_for(700u);
    check(peace.family==ActionFamily::peace && peace.peace.valid(),
        "peace_payload_valid");
    check(peace.peace.offer.use_count()==1
        && independent.peace.offer.use_count()==1,
        "peace_independent_refs_start_at_one");
    check(peace.peace==independent.peace,
        "peace_independent_clone_logically_equal");

    const ObjectRef outgoing_wrapper=wrapper_for(700u);
    const ObjectRef outgoing_action=action_for(700u);
    const ObjectRef incoming_wrapper=wrapper_for(701u);
    const ObjectRef incoming_action=action_for(701u);
    const ObjectRef target_wrapper=wrapper_for(702u);
    const ObjectRef target_action=action_for(702u);
    const NativeHeader source_header=header_for(700u);

    const SeedResult seeded=ledger.seed(context,"peace-lifecycle",peace,
        Phase::initiate,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"peace_lifecycle_seed");
    check(peace.peace.offer.use_count()==2,
        "peace_seed_retains_offer_reference");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        outgoing_wrapper,outgoing_action,peace,source_header).ok(),
        "peace_source_serialization");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::initiate,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"peace_source_detached");

    const ClaimResult claimed=ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,
        independent,true);
    check(claimed.result.ok(),"peace_inbound_claim");
    const CloneProof proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,target_action,independent,source_header.seq);
    check(ledger.postclone(context,claimed.ticket,Phase::initiate,proof).ok(),
        "peace_clone_proof");
    check(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,independent,proof.final_entry_header).ok(),
        "peace_execution_consume");
    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && inspected.view.payload.family==ActionFamily::peace
        && inspected.view.payload.peace==peace.peace,
        "peace_payload_preserved_after_cycle");

    AlliancePayload changed=peace_payload_for(700u,10001);
    expect_peace_payload_mismatch(peace,changed,701u,
        "peace_term_value_mismatch");
    changed=peace_payload_for(700u,10000,1u);
    expect_peace_payload_mismatch(peace,changed,702u,
        "peace_selected_index_mismatch");
    changed=peace_payload_for(700u,10000,0u,0xabcdefu);
    expect_peace_payload_mismatch(peace,changed,703u,
        "peace_participant_mismatch");
    changed=peace;
    changed.peace.flag40=0;
    expect_peace_payload_mismatch(peace,changed,704u,
        "peace_flag40_mismatch");
    changed=peace;
    changed.peace.direction41=0;
    expect_peace_payload_mismatch(peace,changed,705u,
        "peace_direction41_mismatch");
    changed=peace;
    changed.peace.preview208=1;
    expect_peace_payload_mismatch(peace,changed,706u,
        "peace_preview208_mismatch");

    AllianceAuthorityLedger invalid_ledger(0xe700u);
    const Context invalid_context{0xe700u,1u};
    AlliancePayload wrong_family=peace;
    wrong_family.family=ActionFamily::alliance;
    check(is_code(invalid_ledger.seed(invalid_context,"peace-cross-family",
        wrong_family,Phase::initiate,wrapper_for(710u),action_for(710u),100u).result,
        ErrorCode::invalid_payload),"peace_cross_family_rejected");

    AlliancePayload unsealed=payload_for(711u,Phase::initiate);
    unsealed.family=ActionFamily::peace;
    unsealed.proposal3c=0;
    unsealed.peace.offer=PeacePayloadRef::allocate();
    unsealed.peace.flag40=1;
    unsealed.peace.direction41=1;
    check(is_code(invalid_ledger.seed(invalid_context,"peace-unsealed",
        unsealed,Phase::initiate,wrapper_for(711u),action_for(711u),100u).result,
        ErrorCode::invalid_payload),"peace_unsealed_rejected");

    AlliancePayload empty=peace;
    empty.peace={};
    check(is_code(invalid_ledger.seed(invalid_context,"peace-empty",
        empty,Phase::initiate,wrapper_for(712u),action_for(712u),100u).result,
        ErrorCode::invalid_payload),"peace_empty_rejected");

    AlliancePayload bad_payer=peace;
    bad_payer.peace.offer=peace_offer_for(bad_payer.actor10,
        bad_payer.actor10,bad_payer.recipient20+1u);
    check(is_code(invalid_ledger.seed(invalid_context,"peace-wrong-payer",
        bad_payer,Phase::initiate,wrapper_for(713u),action_for(713u),100u).result,
        ErrorCode::invalid_payload),"peace_wrong_payer_rejected");

    AlliancePayload response=peace;
    check(is_code(invalid_ledger.seed(invalid_context,"peace-accept",
        response,Phase::accept,wrapper_for(714u),action_for(714u),100u).result,
        ErrorCode::invalid_payload),"peace_accept_state0_rejected");
    AlliancePayload nonzero_initiate=peace;
    nonzero_initiate.proposal3c=199u;
    check(is_code(invalid_ledger.seed(invalid_context,"peace-initiate-token",
        nonzero_initiate,Phase::initiate,wrapper_for(715u),action_for(715u),
        100u).result,ErrorCode::invalid_payload),
        "peace_initiate_token_rejected");
    for (unsigned i=0;i<2;++i) {
        const Phase phase=i?Phase::reject:Phase::accept;
        const std::uint64_t salt=730u+i*3u;
        response=peace;
        response.state34=i?1u:2u;
        response.proposal3c=199u+i;
        const auto seed=invalid_ledger.seed(invalid_context,i?"peace-reject-valid":"peace-accept-valid",
            response,phase,wrapper_for(salt),action_for(salt),100u);
        check(seed.result.ok(),"peace_response_seed");
        const NativeHeader header=header_for(static_cast<std::uint32_t>(salt));
        check(invalid_ledger.serializer(invalid_context,seed.receipt,phase,
            wrapper_for(salt),action_for(salt),response,header).ok(),"peace_response_serialized");
        const auto claim=invalid_ledger.incoming_preclone(invalid_context,seed.receipt,phase,
            wrapper_for(salt+1u),action_for(salt+1u),header,response,true);
        check(claim.result.ok(),"peace_response_claimed");
        const auto proof=clone_for(wrapper_for(salt+1u),action_for(salt+1u),
            wrapper_for(salt+2u),action_for(salt+2u),response,header.seq);
        check(invalid_ledger.postclone(invalid_context,claim.ticket,phase,proof).ok(),
            "peace_response_postcloned");
        AlliancePayload wrong_token=response;
        ++wrong_token.proposal3c;
        check(is_code(invalid_ledger.consume_entry(invalid_context,claim.ticket,phase,
            proof.target_wrapper,proof.target_action,wrong_token,
            proof.final_entry_header),ErrorCode::payload_mismatch),
            "peace_response_token_mismatch");
        AlliancePayload altered=response;
        altered.peace=peace_payload_for(700u,20000).peace;
        check(is_code(invalid_ledger.consume_entry(invalid_context,claim.ticket,phase,
            proof.target_wrapper,proof.target_action,altered,proof.final_entry_header),
            ErrorCode::payload_mismatch),"peace_response_changed_offer_denied");
        check(invalid_ledger.consume_entry(invalid_context,claim.ticket,phase,
            proof.target_wrapper,proof.target_action,response,proof.final_entry_header).ok(),
            "peace_response_consumed");
    }

    {
        AllianceAuthorityLedger reset_ledger(0xe800u);
        const Context reset_context{0xe800u,1u};
        const AlliancePayload held=peace_payload_for(720u);
        check(held.peace.offer.use_count()==1,"peace_reset_ref_initial");
        const SeedResult reset_seed=reset_ledger.seed(reset_context,
            "peace-reset",held,Phase::initiate,wrapper_for(720u),
            action_for(720u),100u);
        check(reset_seed.result.ok() && held.peace.offer.use_count()==2,
            "peace_reset_seed_retains_ref");
        reset_ledger.reset_session_epoch(0xe801u);
        check(held.peace.offer.use_count()==1,
            "peace_reset_releases_offer_reference");
    }
}

static void test_peace_offer_direction_lifecycle() {
    const std::uint64_t epoch=0xe900u;
    AllianceAuthorityLedger ledger(epoch);
    const Context context{epoch,10u};
    const AlliancePayload offer=peace_payload_for(740u,10000,0,0,false);
    const AlliancePayload independent=offer;
    check(offer.family==ActionFamily::peace && offer.peace.valid()
        && offer.peace.direction41==0
        && offer.peace.offer.get()->claimant==offer.recipient20
        && offer.peace.offer.get()->payer==offer.actor10,
        "peace_offer_roles_follow_direction");
    check(offer.peace.offer.get()->direction==0
        && independent.peace==offer.peace,
        "peace_offer_payload_direction_captured");

    const ObjectRef outgoing_wrapper=wrapper_for(740u);
    const ObjectRef outgoing_action=action_for(740u);
    const ObjectRef incoming_wrapper=wrapper_for(741u);
    const ObjectRef incoming_action=action_for(741u);
    const ObjectRef target_wrapper=wrapper_for(742u);
    const ObjectRef target_action=action_for(742u);
    const NativeHeader source_header=header_for(740u);
    const SeedResult seeded=ledger.seed(context,"peace-offer-lifecycle",offer,
        Phase::initiate,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"peace_offer_seed");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        outgoing_wrapper,outgoing_action,offer,source_header).ok(),
        "peace_offer_source_serialization");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::initiate,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"peace_offer_source_detached");
    const ClaimResult claimed=ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,
        independent,true);
    check(claimed.result.ok(),"peace_offer_inbound_claim");
    const CloneProof proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,target_action,independent,source_header.seq);
    check(ledger.postclone(context,claimed.ticket,Phase::initiate,proof).ok(),
        "peace_offer_clone_proof");
    check(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,independent,proof.final_entry_header).ok(),
        "peace_offer_execution_consume");
    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && inspected.view.payload.peace==offer.peace,
        "peace_offer_payload_preserved_after_cycle");

    for (unsigned i=0;i<2;++i) {
        const Phase phase=i?Phase::reject:Phase::accept;
        AlliancePayload response=offer;
        response.state34=i?1u:2u;
        response.proposal3c=240u+i;
        const std::uint64_t salt=750u+i*3u;
        const ObjectRef response_wrapper=wrapper_for(salt);
        const ObjectRef response_action=action_for(salt);
        const NativeHeader response_header=header_for(
            static_cast<std::uint32_t>(salt));
        const auto response_seed=ledger.seed(context,
            i?"peace-offer-reject":"peace-offer-accept",response,phase,
            response_wrapper,response_action,100u);
        check(response_seed.result.ok(),i?"peace_offer_reject_seed"
            :"peace_offer_accept_seed");
        check(ledger.serializer(context,response_seed.receipt,phase,
            response_wrapper,response_action,response,response_header).ok(),
            i?"peace_offer_reject_serialized":"peace_offer_accept_serialized");
        const auto response_claim=ledger.incoming_preclone(context,
            response_seed.receipt,phase,wrapper_for(salt+1u),
            action_for(salt+1u),response_header,response,true);
        check(response_claim.result.ok(),i?"peace_offer_reject_claim"
            :"peace_offer_accept_claim");
        const auto response_proof=clone_for(wrapper_for(salt+1u),
            action_for(salt+1u),wrapper_for(salt+2u),action_for(salt+2u),
            response,response_header.seq);
        check(ledger.postclone(context,response_claim.ticket,phase,
            response_proof).ok(),i?"peace_offer_reject_clone"
            :"peace_offer_accept_clone");
        check(ledger.consume_entry(context,response_claim.ticket,phase,
            response_proof.target_wrapper,response_proof.target_action,
            response,response_proof.final_entry_header).ok(),
            i?"peace_offer_reject_consume":"peace_offer_accept_consume");
    }

    AlliancePayload wrong_roles=offer;
    wrong_roles.peace.offer=peace_offer_for(wrong_roles.actor10,
        wrong_roles.actor10,wrong_roles.recipient20,10000,0,0,false);
    check(is_code(ledger.seed(context,"peace-offer-wrong-roles",wrong_roles,
        Phase::initiate,wrapper_for(760u),action_for(760u),100u).result,
        ErrorCode::invalid_payload),"peace_offer_reverse_roles_rejected");
    AlliancePayload wrong_direction=offer;
    wrong_direction.peace.direction41=1;
    check(is_code(ledger.seed(context,"peace-offer-wrong-direction",
        wrong_direction,Phase::initiate,wrapper_for(761u),action_for(761u),
        100u).result,ErrorCode::invalid_payload),
        "peace_offer_direction_mismatch_rejected");
    AlliancePayload wrong_terms=offer;
    wrong_terms.peace.offer=peace_offer_for(wrong_terms.actor10,
        wrong_terms.recipient20,wrong_terms.actor10,20000,0,0,false);
    expect_peace_payload_mismatch(offer,wrong_terms,762u,
        "peace_offer_term_mutation_rejected");
}

static void test_normal_and_exact_matching() {
    AllianceAuthorityLedger ledger(0x1111u);
    const Context context{0x1111u,10u};
    const AlliancePayload payload=payload_for(1u);
    const ObjectRef outgoing_wrapper=wrapper_for(1u);
    const ObjectRef outgoing_action=action_for(1u);
    const ObjectRef incoming_wrapper=wrapper_for(2u);
    const ObjectRef incoming_action=action_for(2u);
    const ObjectRef target_wrapper=wrapper_for(3u);
    const ObjectRef target_action=action_for(3u);
    const NativeHeader header=header_for(77u);

    const SeedResult seeded=ledger.seed(context,"authority-normal",payload,
        Phase::accept,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"normal_seed");
    check(seeded.receipt.slot!=bridge::alliance_authority::kInvalidSlot,
        "normal_seed_receipt");
    check(ledger.serializer(context,seeded.receipt,Phase::accept,
        outgoing_wrapper,outgoing_action,payload,header).ok(),
        "normal_serializer");
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::accept,with_generation(outgoing_wrapper,
            outgoing_wrapper.generation+1u),incoming_action,header,payload,true)
        .result,ErrorCode::generation_mismatch),
        "incoming_cannot_reuse_live_outgoing_generation");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::accept,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"outgoing_detaches_after_serialize");
    const auto serialized=ledger.inspect(context,seeded.receipt);
    check(serialized.result.ok() && serialized.view.state==State::serialized
        && !serialized.view.outgoing_alive,"serialized_keeps_record");

    ClaimResult untrusted=ledger.incoming_preclone(context,seeded.receipt,
        Phase::accept,incoming_wrapper,incoming_action,header,payload,false);
    check(is_code(untrusted.result,ErrorCode::untrusted_pipeline),
        "untrusted_pipeline_rejected");
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::accept,outgoing_wrapper,incoming_action,header,payload,true)
        .result,ErrorCode::identity_mismatch),
        "incoming_must_be_independent");
    const NativeHeader wrong_header{header.origin,header.flags,
        header.seq+1u};
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::accept,incoming_wrapper,incoming_action,wrong_header,payload,true)
        .result,ErrorCode::header_mismatch),"preclone_header_exact");
    const ClaimResult claimed=ledger.incoming_preclone(context,seeded.receipt,
        Phase::accept,incoming_wrapper,incoming_action,header,payload,true);
    check(claimed.result.ok(),"trusted_preclone_claim");
    const ClaimTicket ticket=claimed.ticket;
    CloneProof wrong_source=clone_for(
        with_generation(incoming_wrapper,incoming_wrapper.generation+1u),
        incoming_action,target_wrapper,target_action,payload,header.seq);
    check(is_code(ledger.postclone(context,ticket,Phase::accept,wrong_source),
        ErrorCode::generation_mismatch),"incoming_generation_required");
    const CloneProof proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,
        target_action,payload,header.seq);
    CloneProof wrong_clone_header=proof;
    wrong_clone_header.observed_clone_header=header;
    check(is_code(ledger.postclone(context,ticket,Phase::accept,
        wrong_clone_header),ErrorCode::header_mismatch),
        "postclone_transfer_header_exact");
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::accept,incoming_wrapper,incoming_action,header,payload,true)
        .result,ErrorCode::duplicate_claim),"claim_ticket_once");
    check(ledger.postclone(context,ticket,Phase::accept,proof).ok(),
        "normal_postclone");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::accept,SourceKind::incoming,incoming_wrapper,incoming_action),
        ErrorCode::incoming_detached),"incoming_detaches_after_postclone");

    const NativeHeader same_sequence_wrong_header{0x1235u,0x05u,header.seq};
    check(is_code(ledger.consume_entry(context,ticket,Phase::accept,
        target_wrapper,target_action,payload,same_sequence_wrong_header),
        ErrorCode::header_mismatch),"full_header_required");
    AlliancePayload changed_date=payload;
    ++changed_date.date2c;
    check(is_code(ledger.consume_entry(context,ticket,Phase::accept,
        target_wrapper,target_action,changed_date,
        proof.final_entry_header),ErrorCode::payload_mismatch),
        "date2c_exact_match");
    const ObjectRef reused_target{target_action.address,
        target_action.generation+1u};
    check(is_code(ledger.consume_entry(context,ticket,Phase::accept,
        target_wrapper,reused_target,payload,proof.final_entry_header),
        ErrorCode::generation_mismatch),"old_ticket_generation_rejected");
    check(ledger.consume_entry(context,ticket,Phase::accept,target_wrapper,
        target_action,payload,proof.final_entry_header).ok(),"normal_consume");
    check(is_code(ledger.consume_entry(context,ticket,Phase::accept,
        target_wrapper,target_action,payload,proof.final_entry_header),
        ErrorCode::already_consumed),"duplicate_entry_rejected");

    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && !inspected.view.target_alive && !inspected.view.incoming_alive,
        "consumed_state_recorded");
}

static void test_wrong_context_phase_and_headers() {
    AllianceAuthorityLedger ledger(0x2222u);
    const Context context{0x2222u,5u};
    const AlliancePayload payload=payload_for(2u,Phase::initiate);
    const ObjectRef source_wrapper=wrapper_for(2u);
    const ObjectRef source_action=action_for(2u);
    const NativeHeader header=header_for(88u);

    AlliancePayload bad_mirror=payload;
    bad_mirror.mirror18^=1u;
    check(is_code(ledger.seed(context,"authority-bad-mirror",bad_mirror,
        Phase::initiate,wrapper_for(20u),action_for(20u),50u).result,
        ErrorCode::invalid_payload),"mirror_must_equal_actor");
    AlliancePayload bad_recipient=payload;
    bad_recipient.recipient20=bad_recipient.actor10;
    check(is_code(ledger.seed(context,"authority-bad-recipient",
        bad_recipient,Phase::initiate,wrapper_for(21u),action_for(21u),50u)
        .result,ErrorCode::invalid_payload),"actor_recipient_must_differ");
    AlliancePayload bad_variant=payload;
    bad_variant.variant38=0u;
    check(is_code(ledger.seed(context,"authority-bad-variant",bad_variant,
        Phase::initiate,wrapper_for(22u),action_for(22u),50u).result,
        ErrorCode::invalid_payload),"offer_variant_required");
    check(is_code(ledger.seed(context,"authority-bad-phase",payload,
        static_cast<Phase>(99u),wrapper_for(23u),action_for(23u),50u).result,
        ErrorCode::invalid_phase),"unknown_phase_rejected");
    check(is_code(ledger.seed(context,"authority-deadline-equal",payload,
        Phase::initiate,wrapper_for(24u),action_for(24u),5u).result,
        ErrorCode::invalid_argument),"deadline_must_be_future");
    check(is_code(ledger.seed(context,"authority-deadline-long",payload,
        Phase::initiate,wrapper_for(25u),action_for(25u),60006u).result,
        ErrorCode::invalid_argument),"deadline_ttl_bounded");

    const SeedResult seeded=ledger.seed(context,"authority-context",payload,
        Phase::initiate,source_wrapper,source_action,50u);
    check(seeded.result.ok(),"context_seed");
    const Context wrong_epoch{0x9999u,5u};
    check(is_code(ledger.serializer(wrong_epoch,seeded.receipt,Phase::initiate,
        source_wrapper,source_action,payload,header),ErrorCode::wrong_epoch),
        "wrong_epoch_rejected");
    check(is_code(ledger.serializer(context,seeded.receipt,Phase::accept,
        source_wrapper,source_action,payload,header),ErrorCode::phase_mismatch),
        "serializer_phase_immutable");
    check(is_code(ledger.serializer(context,seeded.receipt,Phase::initiate,
        wrapper_for(202u),source_action,payload,header),
        ErrorCode::identity_mismatch),"serializer_identity_exact");
    AlliancePayload changed=payload;
    ++changed.actor10;
    check(is_code(ledger.serializer(context,seeded.receipt,Phase::initiate,
        source_wrapper,source_action,changed,header),
        ErrorCode::payload_mismatch),"serializer_payload_immutable");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        source_wrapper,source_action,payload,header).ok(),
        "context_serializer");
    check(is_code(ledger.serializer(context,seeded.receipt,Phase::initiate,
        source_wrapper,source_action,payload,header),
        ErrorCode::duplicate_header),"duplicate_header_same_record");

    const SeedResult second=ledger.seed(context,"authority-header-other",
        payload_for(3u,Phase::initiate),Phase::initiate,wrapper_for(3u),
        action_for(3u),50u);
    check(second.result.ok(),"header_second_seed");
    check(is_code(ledger.serializer(context,second.receipt,Phase::initiate,
        wrapper_for(3u),action_for(3u),payload_for(3u,Phase::initiate),header),
        ErrorCode::ambiguous_header),"duplicate_header_other_record");

    char too_long[66]{};
    for (unsigned i=0;i<65;++i) too_long[i]='a';
    const SeedResult invalid_id=ledger.seed(context,too_long,
        payload_for(4u,Phase::initiate),
        Phase::initiate,wrapper_for(4u),action_for(4u),50u);
    check(is_code(invalid_id.result,ErrorCode::request_id_invalid),
        "request_id_bound");
    const SeedResult null_identity=ledger.seed(context,"authority-null",
        payload_for(5u,Phase::initiate),Phase::initiate,ObjectRef{},
        action_for(5u),50u);
    check(is_code(null_identity.result,ErrorCode::invalid_argument),
        "null_identity_rejected");
}

static void test_action_family_binding() {
    AllianceAuthorityLedger ledger(0x9999u);
    const Context context{0x9999u,10u};
    const ObjectRef wrapper=wrapper_for(300u);
    const ObjectRef action=action_for(300u);

    // Appending family fields leaves the legacy nine-word aggregate intact.
    const AlliancePayload legacy=payload_for(300u,Phase::initiate);
    check(legacy.family==ActionFamily::alliance && legacy.extra60==0,
        "legacy_payload_defaults_to_alliance");

    AlliancePayload royal=legacy;
    royal.family=ActionFamily::royal_marriage;
    check(royal!=legacy,"family_part_of_payload_identity");
    const auto seeded=ledger.seed(context,"royal-family",royal,
        Phase::initiate,wrapper,action,100u);
    check(seeded.result.ok(),"royal_family_seed");
    check(is_code(ledger.serializer(context,seeded.receipt,Phase::initiate,
        wrapper,action,legacy,header_for(302u)),
        ErrorCode::payload_mismatch),"cross_family_authority_rejected");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        wrapper,action,royal,header_for(301u)).ok(),
        "royal_family_serializer");

    AlliancePayload improve=legacy;
    improve.family=ActionFamily::improve_relations;
    check(improve!=legacy && improve!=royal,
        "improve_family_part_of_payload_identity");
    const auto improve_seed=ledger.seed(context,"improve-family",improve,
        Phase::initiate,wrapper_for(305u),action_for(305u),100u);
    check(improve_seed.result.ok(),"improve_family_seed");
    check(is_code(ledger.serializer(context,improve_seed.receipt,
        Phase::initiate,wrapper_for(305u),action_for(305u),legacy,
        header_for(306u)),ErrorCode::payload_mismatch),
        "improve_cannot_use_alliance_authority");
    check(is_code(ledger.serializer(context,improve_seed.receipt,
        Phase::initiate,wrapper_for(305u),action_for(305u),royal,
        header_for(307u)),ErrorCode::payload_mismatch),
        "improve_cannot_use_royal_authority");
    check(ledger.serializer(context,improve_seed.receipt,Phase::initiate,
        wrapper_for(305u),action_for(305u),improve,header_for(305u)).ok(),
        "improve_family_serializer");

    // Stop-improving reuses the existing dissolve shape: variant/state are
    // both zero while the family remains bound to improve-relations.
    const AlliancePayload improve_stop=payload_for(308u,Phase::dissolve);
    AlliancePayload improve_stop_family=improve_stop;
    improve_stop_family.family=ActionFamily::improve_relations;
    const auto improve_stop_seed=ledger.seed(context,"improve-stop",
        improve_stop_family,Phase::dissolve,wrapper_for(308u),
        action_for(308u),100u);
    check(improve_stop_seed.result.ok(),"improve_stop_dissolve_shape");
    const auto improve_stop_view=ledger.inspect(context,
        improve_stop_seed.receipt);
    check(improve_stop_view.result.ok()
        && improve_stop_view.view.phase==Phase::dissolve
        && improve_stop_view.view.payload.family==ActionFamily::improve_relations,
        "improve_stop_family_preserved");

    AlliancePayload spy=legacy;
    spy.family=ActionFamily::spy_network;
    check(spy!=legacy && spy!=royal && spy!=improve,
        "spy_family_part_of_payload_identity");
    const auto spy_seed=ledger.seed(context,"spy-family",spy,
        Phase::initiate,wrapper_for(310u),action_for(310u),100u);
    check(spy_seed.result.ok(),"spy_family_seed");
    check(is_code(ledger.serializer(context,spy_seed.receipt,
        Phase::initiate,wrapper_for(310u),action_for(310u),legacy,
        header_for(311u)),ErrorCode::payload_mismatch),
        "spy_cannot_use_alliance_authority");
    check(is_code(ledger.serializer(context,spy_seed.receipt,
        Phase::initiate,wrapper_for(310u),action_for(310u),royal,
        header_for(312u)),ErrorCode::payload_mismatch),
        "spy_cannot_use_royal_authority");
    check(is_code(ledger.serializer(context,spy_seed.receipt,
        Phase::initiate,wrapper_for(310u),action_for(310u),improve,
        header_for(313u)),ErrorCode::payload_mismatch),
        "spy_cannot_use_improve_authority");
    check(ledger.serializer(context,spy_seed.receipt,Phase::initiate,
        wrapper_for(310u),action_for(310u),spy,header_for(310u)).ok(),
        "spy_family_serializer");

    const AlliancePayload spy_stop=payload_for(314u,Phase::dissolve);
    AlliancePayload spy_stop_family=spy_stop;
    spy_stop_family.family=ActionFamily::spy_network;
    const auto spy_stop_seed=ledger.seed(context,"spy-stop",
        spy_stop_family,Phase::dissolve,wrapper_for(314u),
        action_for(314u),100u);
    check(spy_stop_seed.result.ok(),"spy_stop_dissolve_shape");
    const auto spy_stop_view=ledger.inspect(context,spy_stop_seed.receipt);
    check(spy_stop_view.result.ok()
        && spy_stop_view.view.phase==Phase::dissolve
        && spy_stop_view.view.payload.family==ActionFamily::spy_network,
        "spy_stop_family_preserved");

    AlliancePayload guarantee=legacy;
    guarantee.family=ActionFamily::guarantee;
    check(guarantee!=legacy && guarantee!=royal && guarantee!=improve
        && guarantee!=spy,"guarantee_family_part_of_payload_identity");
    const auto guarantee_seed=ledger.seed(context,"guarantee-family",
        guarantee,Phase::initiate,wrapper_for(330u),action_for(330u),100u);
    check(guarantee_seed.result.ok(),"guarantee_family_seed");
    check(is_code(ledger.serializer(context,guarantee_seed.receipt,
        Phase::initiate,wrapper_for(330u),action_for(330u),legacy,
        header_for(331u)),ErrorCode::payload_mismatch),
        "guarantee_cannot_use_alliance_authority");
    check(is_code(ledger.serializer(context,guarantee_seed.receipt,
        Phase::initiate,wrapper_for(330u),action_for(330u),royal,
        header_for(332u)),ErrorCode::payload_mismatch),
        "guarantee_cannot_use_royal_authority");
    check(is_code(ledger.serializer(context,guarantee_seed.receipt,
        Phase::initiate,wrapper_for(330u),action_for(330u),improve,
        header_for(333u)),ErrorCode::payload_mismatch),
        "guarantee_cannot_use_improve_authority");
    check(is_code(ledger.serializer(context,guarantee_seed.receipt,
        Phase::initiate,wrapper_for(330u),action_for(330u),spy,
        header_for(334u)),ErrorCode::payload_mismatch),
        "guarantee_cannot_use_spy_authority");
    check(ledger.serializer(context,guarantee_seed.receipt,Phase::initiate,
        wrapper_for(330u),action_for(330u),guarantee,header_for(330u)).ok(),
        "guarantee_family_serializer");

    AlliancePayload guarantee_stop=payload_for(335u,Phase::dissolve);
    guarantee_stop.family=ActionFamily::guarantee;
    const auto guarantee_stop_seed=ledger.seed(context,"guarantee-stop",
        guarantee_stop,Phase::dissolve,wrapper_for(335u),action_for(335u),
        100u);
    check(guarantee_stop_seed.result.ok(),"guarantee_stop_dissolve_shape");
    const auto guarantee_stop_view=ledger.inspect(context,
        guarantee_stop_seed.receipt);
    check(guarantee_stop_view.result.ok()
        && guarantee_stop_view.view.phase==Phase::dissolve
        && guarantee_stop_view.view.payload.family==ActionFamily::guarantee,
        "guarantee_stop_family_preserved");

    AlliancePayload guarantee_accept=guarantee;
    guarantee_accept.state34=2u;
    check(is_code(ledger.seed(context,"guarantee-accept-state",
        guarantee_accept,Phase::accept,wrapper_for(336u),action_for(336u),
        100u).result,ErrorCode::invalid_payload),
        "guarantee_accept_state_rejected");
    AlliancePayload guarantee_reject=guarantee;
    guarantee_reject.state34=1u;
    check(is_code(ledger.seed(context,"guarantee-reject-state",
        guarantee_reject,Phase::reject,wrapper_for(337u),action_for(337u),
        100u).result,ErrorCode::invalid_payload),
        "guarantee_reject_state_rejected");
    AlliancePayload guarantee_bad_mode=guarantee;
    guarantee_bad_mode.variant38=2u;
    check(is_code(ledger.seed(context,"guarantee-bad-mode",
        guarantee_bad_mode,Phase::initiate,wrapper_for(338u),action_for(338u),
        100u).result,ErrorCode::invalid_payload),
        "guarantee_mode_rejected");
    AlliancePayload guarantee_bad_state=guarantee;
    guarantee_bad_state.state34=1u;
    check(is_code(ledger.seed(context,"guarantee-bad-state",
        guarantee_bad_state,Phase::initiate,wrapper_for(339u),action_for(339u),
        100u).result,ErrorCode::invalid_payload),
        "guarantee_state_rejected");

    AlliancePayload spy_accept=spy;
    spy_accept.state34=2u;
    check(is_code(ledger.seed(context,"spy-accept-state",spy_accept,
        Phase::accept,wrapper_for(315u),action_for(315u),100u).result,
        ErrorCode::invalid_payload),"spy_accept_state_rejected");
    AlliancePayload spy_reject=spy;
    spy_reject.state34=1u;
    check(is_code(ledger.seed(context,"spy-reject-state",spy_reject,
        Phase::reject,wrapper_for(316u),action_for(316u),100u).result,
        ErrorCode::invalid_payload),"spy_reject_state_rejected");
    AlliancePayload spy_bad_mode=spy;
    spy_bad_mode.variant38=2u;
    check(is_code(ledger.seed(context,"spy-bad-mode",spy_bad_mode,
        Phase::initiate,wrapper_for(317u),action_for(317u),100u).result,
        ErrorCode::invalid_payload),"spy_mode_rejected");
    AlliancePayload spy_bad_state=spy;
    spy_bad_state.state34=1u;
    check(is_code(ledger.seed(context,"spy-bad-state",spy_bad_state,
        Phase::initiate,wrapper_for(318u),action_for(318u),100u).result,
        ErrorCode::invalid_payload),"spy_state_rejected");

    AlliancePayload unknown=legacy;
    unknown.family=static_cast<ActionFamily>(99u);
    check(is_code(ledger.seed(context,"unknown-family",unknown,
        Phase::initiate,wrapper_for(302u),action_for(302u),100u).result,
        ErrorCode::invalid_payload),"unknown_family_rejected");

    AlliancePayload alliance_extra=legacy;
    alliance_extra.extra60=1u;
    check(is_code(ledger.seed(context,"alliance-extra",alliance_extra,
        Phase::initiate,wrapper_for(303u),action_for(303u),100u).result,
        ErrorCode::invalid_payload),"alliance_extra60_rejected");

    AlliancePayload royal_extra=royal;
    royal_extra.extra60=1u;
    check(is_code(ledger.seed(context,"royal-extra",royal_extra,
        Phase::initiate,wrapper_for(304u),action_for(304u),100u).result,
        ErrorCode::invalid_payload),"royal_extra60_rejected");

    AlliancePayload improve_extra=improve;
    improve_extra.extra60=1u;
    check(is_code(ledger.seed(context,"improve-extra",improve_extra,
        Phase::initiate,wrapper_for(309u),action_for(309u),100u).result,
        ErrorCode::invalid_payload),"improve_extra60_rejected");

    AlliancePayload spy_extra=spy;
    spy_extra.extra60=1u;
    check(is_code(ledger.seed(context,"spy-extra",spy_extra,
        Phase::initiate,wrapper_for(319u),action_for(319u),100u).result,
        ErrorCode::invalid_payload),"spy_extra60_rejected");

    AlliancePayload guarantee_extra=guarantee;
    guarantee_extra.extra60=1u;
    check(is_code(ledger.seed(context,"guarantee-extra",guarantee_extra,
        Phase::initiate,wrapper_for(340u),action_for(340u),100u).result,
        ErrorCode::invalid_payload),"guarantee_extra60_rejected");

    AlliancePayload support=legacy;
    support.family=ActionFamily::support_independence;
    check(support!=legacy && support!=royal && support!=improve
        && support!=spy && support!=guarantee,
        "support_independence_family_part_of_payload_identity");
    const auto support_seed=ledger.seed(context,"support-family",support,
        Phase::initiate,wrapper_for(360u),action_for(360u),100u);
    check(support_seed.result.ok(),"support_independence_family_seed");
    check(is_code(ledger.serializer(context,support_seed.receipt,
        Phase::initiate,wrapper_for(360u),action_for(360u),legacy,
        header_for(361u)),ErrorCode::payload_mismatch),
        "support_cannot_use_alliance_authority");
    check(is_code(ledger.serializer(context,support_seed.receipt,
        Phase::initiate,wrapper_for(360u),action_for(360u),guarantee,
        header_for(362u)),ErrorCode::payload_mismatch),
        "support_cannot_use_guarantee_authority");
    check(ledger.serializer(context,support_seed.receipt,Phase::initiate,
        wrapper_for(360u),action_for(360u),support,header_for(360u)).ok(),
        "support_independence_family_serializer");

    AlliancePayload support_accept=payload_for(363u,Phase::accept);
    support_accept.family=ActionFamily::support_independence;
    const auto support_accept_seed=ledger.seed(context,"support-accept",
        support_accept,Phase::accept,wrapper_for(363u),action_for(363u),100u);
    check(support_accept_seed.result.ok(),"support_accept_state2_valid");
    AlliancePayload support_reject=payload_for(364u,Phase::reject);
    support_reject.family=ActionFamily::support_independence;
    const auto support_reject_seed=ledger.seed(context,"support-reject",
        support_reject,Phase::reject,wrapper_for(364u),action_for(364u),100u);
    check(support_reject_seed.result.ok(),"support_reject_state1_valid");
    AlliancePayload support_dissolve=payload_for(365u,Phase::dissolve);
    support_dissolve.family=ActionFamily::support_independence;
    const auto support_dissolve_seed=ledger.seed(context,"support-dissolve",
        support_dissolve,Phase::dissolve,wrapper_for(365u),action_for(365u),
        100u);
    check(support_dissolve_seed.result.ok(),"support_dissolve_state0_valid");
    const auto support_dissolve_view=ledger.inspect(context,
        support_dissolve_seed.receipt);
    check(support_dissolve_view.result.ok()
        && support_dissolve_view.view.phase==Phase::dissolve
        && support_dissolve_view.view.payload.family
            ==ActionFamily::support_independence,
        "support_dissolve_family_preserved");

    AlliancePayload support_bad_accept=support_accept;
    support_bad_accept.state34=1u;
    check(is_code(ledger.seed(context,"support-accept-state1",
        support_bad_accept,Phase::accept,wrapper_for(366u),action_for(366u),
        100u).result,ErrorCode::invalid_payload),
        "support_accept_requires_state2");
    AlliancePayload support_bad_reject=support_reject;
    support_bad_reject.state34=2u;
    check(is_code(ledger.seed(context,"support-reject-state2",
        support_bad_reject,Phase::reject,wrapper_for(367u),action_for(367u),
        100u).result,ErrorCode::invalid_payload),
        "support_reject_requires_state1");
    AlliancePayload support_bad_mode=support;
    support_bad_mode.variant38=0u;
    check(is_code(ledger.seed(context,"support-initiate-mode0",
        support_bad_mode,Phase::initiate,wrapper_for(368u),action_for(368u),
        100u).result,ErrorCode::invalid_payload),
        "support_initiate_requires_mode1");
    AlliancePayload support_bad_dissolve=support_dissolve;
    support_bad_dissolve.variant38=1u;
    check(is_code(ledger.seed(context,"support-dissolve-mode1",
        support_bad_dissolve,Phase::dissolve,wrapper_for(369u),
        action_for(369u),100u).result,ErrorCode::invalid_payload),
        "support_dissolve_requires_mode0");
    AlliancePayload support_extra=support;
    support_extra.extra60=1u;
    check(is_code(ledger.seed(context,"support-extra",support_extra,
        Phase::initiate,wrapper_for(370u),action_for(370u),100u).result,
        ErrorCode::invalid_payload),"support_extra60_rejected");

    AlliancePayload vassalization=legacy;
    vassalization.family=ActionFamily::vassalization;
    check(vassalization!=legacy && vassalization!=royal
        && vassalization!=guarantee && vassalization!=support,
        "vassalization_family_part_of_payload_identity");
    const auto vassalization_seed=ledger.seed(context,
        "vassalization-family",vassalization,Phase::initiate,
        wrapper_for(380u),action_for(380u),100u);
    check(vassalization_seed.result.ok(),"vassalization_family_seed");
    check(is_code(ledger.serializer(context,vassalization_seed.receipt,
        Phase::initiate,wrapper_for(380u),action_for(380u),legacy,
        header_for(381u)),ErrorCode::payload_mismatch),
        "vassalization_cannot_use_alliance_authority");
    check(is_code(ledger.serializer(context,vassalization_seed.receipt,
        Phase::initiate,wrapper_for(380u),action_for(380u),royal,
        header_for(382u)),ErrorCode::payload_mismatch),
        "vassalization_cannot_use_royal_authority");
    check(is_code(ledger.serializer(context,vassalization_seed.receipt,
        Phase::initiate,wrapper_for(380u),action_for(380u),guarantee,
        header_for(383u)),ErrorCode::payload_mismatch),
        "vassalization_cannot_use_guarantee_authority");
    check(ledger.serializer(context,vassalization_seed.receipt,
        Phase::initiate,wrapper_for(380u),action_for(380u),vassalization,
        header_for(380u)).ok(),"vassalization_family_serializer");

    AlliancePayload vassalization_accept=payload_for(384u,Phase::accept);
    vassalization_accept.family=ActionFamily::vassalization;
    check(ledger.seed(context,"vassalization-accept",
        vassalization_accept,Phase::accept,wrapper_for(384u),
        action_for(384u),100u).result.ok(),
        "vassalization_accept_state2_valid");
    AlliancePayload vassalization_reject=payload_for(385u,Phase::reject);
    vassalization_reject.family=ActionFamily::vassalization;
    check(ledger.seed(context,"vassalization-reject",
        vassalization_reject,Phase::reject,wrapper_for(385u),
        action_for(385u),100u).result.ok(),
        "vassalization_reject_state1_valid");
    AlliancePayload vassalization_dissolve=payload_for(386u,Phase::dissolve);
    vassalization_dissolve.family=ActionFamily::vassalization;
    const auto vassalization_dissolve_seed=ledger.seed(context,
        "vassalization-dissolve",vassalization_dissolve,Phase::dissolve,
        wrapper_for(386u),action_for(386u),100u);
    check(vassalization_dissolve_seed.result.ok(),
        "vassalization_dissolve_state0_valid");
    const auto vassalization_dissolve_view=ledger.inspect(context,
        vassalization_dissolve_seed.receipt);
    check(vassalization_dissolve_view.result.ok()
        && vassalization_dissolve_view.view.phase==Phase::dissolve
        && vassalization_dissolve_view.view.payload.family
            ==ActionFamily::vassalization,
        "vassalization_dissolve_family_preserved");

    AlliancePayload vassalization_bad_accept=vassalization_accept;
    vassalization_bad_accept.state34=1u;
    check(is_code(ledger.seed(context,"vassalization-accept-state1",
        vassalization_bad_accept,Phase::accept,wrapper_for(387u),
        action_for(387u),100u).result,ErrorCode::invalid_payload),
        "vassalization_accept_requires_state2");
    AlliancePayload vassalization_bad_reject=vassalization_reject;
    vassalization_bad_reject.state34=2u;
    check(is_code(ledger.seed(context,"vassalization-reject-state2",
        vassalization_bad_reject,Phase::reject,wrapper_for(388u),
        action_for(388u),100u).result,ErrorCode::invalid_payload),
        "vassalization_reject_requires_state1");
    AlliancePayload vassalization_bad_dissolve=vassalization_dissolve;
    vassalization_bad_dissolve.variant38=1u;
    check(is_code(ledger.seed(context,"vassalization-dissolve-mode1",
        vassalization_bad_dissolve,Phase::dissolve,wrapper_for(389u),
        action_for(389u),100u).result,ErrorCode::invalid_payload),
        "vassalization_dissolve_requires_mode0");
    AlliancePayload vassalization_extra=vassalization;
    vassalization_extra.extra60=1u;
    check(is_code(ledger.seed(context,"vassalization-extra",
        vassalization_extra,Phase::initiate,wrapper_for(390u),
        action_for(390u),100u).result,ErrorCode::invalid_payload),
        "vassalization_extra60_rejected");
}

static void test_spy_network_lifecycle_and_isolation() {
    AllianceAuthorityLedger ledger(0xaaaaU);
    const Context context{0xaaaaU,20u};
    AlliancePayload spy=payload_for(320u,Phase::initiate);
    spy.family=ActionFamily::spy_network;
    const ObjectRef outgoing_wrapper=wrapper_for(320u);
    const ObjectRef outgoing_action=action_for(320u);
    const ObjectRef incoming_wrapper=wrapper_for(321u);
    const ObjectRef incoming_action=action_for(321u);
    const ObjectRef target_wrapper=wrapper_for(322u);
    const ObjectRef target_action=action_for(322u);
    const NativeHeader source_header=header_for(320u);

    const SeedResult seeded=ledger.seed(context,"spy-lifecycle",spy,
        Phase::initiate,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"spy_lifecycle_seed");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        outgoing_wrapper,outgoing_action,spy,source_header).ok(),
        "spy_source_serialization");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::initiate,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"spy_source_detached");

    AlliancePayload improve=spy;
    improve.family=ActionFamily::improve_relations;
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,
        improve,true).result,ErrorCode::payload_mismatch),
        "spy_inbound_family_mismatch");
    const ClaimResult claimed=ledger.incoming_preclone(context,
        seeded.receipt,Phase::initiate,incoming_wrapper,incoming_action,
        source_header,spy,true);
    check(claimed.result.ok(),"spy_inbound_claim");

    const CloneProof valid_proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,target_action,spy,source_header.seq);
    CloneProof wrong_family_proof=valid_proof;
    wrong_family_proof.payload=improve;
    check(is_code(ledger.postclone(context,claimed.ticket,Phase::initiate,
        wrong_family_proof),ErrorCode::payload_mismatch),
        "spy_transport_family_mismatch");
    check(ledger.postclone(context,claimed.ticket,Phase::initiate,
        valid_proof).ok(),"spy_transport_clone");

    check(is_code(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,improve,valid_proof.final_entry_header),
        ErrorCode::payload_mismatch),"spy_execution_family_mismatch");
    check(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,spy,valid_proof.final_entry_header).ok(),
        "spy_execution_consume");
    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && inspected.view.payload.family==ActionFamily::spy_network
        && inspected.view.payload.extra60==0,
        "spy_lifecycle_family_preserved");
}

static void test_guarantee_lifecycle_and_isolation() {
    AllianceAuthorityLedger ledger(0xbbbbU);
    const Context context{0xbbbbU,30u};
    AlliancePayload guarantee=payload_for(350u,Phase::initiate);
    guarantee.family=ActionFamily::guarantee;
    const ObjectRef outgoing_wrapper=wrapper_for(350u);
    const ObjectRef outgoing_action=action_for(350u);
    const ObjectRef incoming_wrapper=wrapper_for(351u);
    const ObjectRef incoming_action=action_for(351u);
    const ObjectRef target_wrapper=wrapper_for(352u);
    const ObjectRef target_action=action_for(352u);
    const NativeHeader source_header=header_for(350u);

    const SeedResult seeded=ledger.seed(context,"guarantee-lifecycle",
        guarantee,Phase::initiate,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"guarantee_lifecycle_seed");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        outgoing_wrapper,outgoing_action,guarantee,source_header).ok(),
        "guarantee_source_serialization");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::initiate,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"guarantee_source_detached");

    AlliancePayload spy=guarantee;
    spy.family=ActionFamily::spy_network;
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,
        spy,true).result,ErrorCode::payload_mismatch),
        "guarantee_inbound_spy_mismatch");
    const ClaimResult claimed=ledger.incoming_preclone(context,
        seeded.receipt,Phase::initiate,incoming_wrapper,incoming_action,
        source_header,guarantee,true);
    check(claimed.result.ok(),"guarantee_inbound_claim");

    const CloneProof valid_proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,target_action,guarantee,source_header.seq);
    CloneProof wrong_family_proof=valid_proof;
    wrong_family_proof.payload=spy;
    check(is_code(ledger.postclone(context,claimed.ticket,Phase::initiate,
        wrong_family_proof),ErrorCode::payload_mismatch),
        "guarantee_transport_spy_mismatch");
    check(ledger.postclone(context,claimed.ticket,Phase::initiate,
        valid_proof).ok(),"guarantee_transport_clone");
    check(is_code(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,spy,valid_proof.final_entry_header),
        ErrorCode::payload_mismatch),"guarantee_execution_spy_mismatch");
    check(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,guarantee,
        valid_proof.final_entry_header).ok(),"guarantee_execution_consume");

    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && inspected.view.payload.family==ActionFamily::guarantee
        && inspected.view.payload.extra60==0,
        "guarantee_lifecycle_family_preserved");
}

static void test_support_independence_lifecycle_and_isolation() {
    AllianceAuthorityLedger ledger(0xccccU);
    const Context context{0xccccU,40u};
    AlliancePayload support=payload_for(380u,Phase::initiate);
    support.family=ActionFamily::support_independence;
    const ObjectRef outgoing_wrapper=wrapper_for(380u);
    const ObjectRef outgoing_action=action_for(380u);
    const ObjectRef incoming_wrapper=wrapper_for(381u);
    const ObjectRef incoming_action=action_for(381u);
    const ObjectRef target_wrapper=wrapper_for(382u);
    const ObjectRef target_action=action_for(382u);
    const NativeHeader source_header=header_for(380u);

    const SeedResult seeded=ledger.seed(context,"support-lifecycle",support,
        Phase::initiate,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"support_lifecycle_seed");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        outgoing_wrapper,outgoing_action,support,source_header).ok(),
        "support_source_serialization");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::initiate,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"support_source_detached");

    AlliancePayload wrong_family=support;
    wrong_family.family=ActionFamily::royal_marriage;
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,
        wrong_family,true).result,ErrorCode::payload_mismatch),
        "support_inbound_royal_mismatch");
    const ClaimResult claimed=ledger.incoming_preclone(context,
        seeded.receipt,Phase::initiate,incoming_wrapper,incoming_action,
        source_header,support,true);
    check(claimed.result.ok(),"support_inbound_claim");

    const CloneProof valid_proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,target_action,support,source_header.seq);
    CloneProof wrong_transport=valid_proof;
    wrong_transport.payload.family=ActionFamily::guarantee;
    check(is_code(ledger.postclone(context,claimed.ticket,Phase::initiate,
        wrong_transport),ErrorCode::payload_mismatch),
        "support_transport_guarantee_mismatch");
    check(ledger.postclone(context,claimed.ticket,Phase::initiate,
        valid_proof).ok(),"support_transport_clone");
    check(is_code(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,wrong_family,valid_proof.final_entry_header),
        ErrorCode::payload_mismatch),"support_execution_royal_mismatch");
    check(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,support,valid_proof.final_entry_header).ok(),
        "support_execution_consume");

    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && inspected.view.payload.family==ActionFamily::support_independence
        && inspected.view.payload.extra60==0,
        "support_lifecycle_family_preserved");
}

static void test_military_access_lifecycle_and_isolation() {
    AllianceAuthorityLedger ledger(0xddddU);
    const Context context{0xddddU,50u};
    AlliancePayload military=payload_for(410u,Phase::initiate);
    military.family=ActionFamily::military_access;
    const ObjectRef outgoing_wrapper=wrapper_for(410u);
    const ObjectRef outgoing_action=action_for(410u);
    const ObjectRef incoming_wrapper=wrapper_for(411u);
    const ObjectRef incoming_action=action_for(411u);
    const ObjectRef target_wrapper=wrapper_for(412u);
    const ObjectRef target_action=action_for(412u);
    const NativeHeader source_header=header_for(410u);

    const SeedResult seeded=ledger.seed(context,"military-lifecycle",
        military,Phase::initiate,outgoing_wrapper,outgoing_action,100u);
    check(seeded.result.ok(),"military_lifecycle_seed");
    check(ledger.serializer(context,seeded.receipt,Phase::initiate,
        outgoing_wrapper,outgoing_action,military,source_header).ok(),
        "military_source_serialization");
    check(is_code(ledger.source_destroyed(context,seeded.receipt,
        Phase::initiate,SourceKind::outgoing,outgoing_wrapper,outgoing_action),
        ErrorCode::outgoing_detached),"military_source_detached");

    AlliancePayload wrong_family=military;
    wrong_family.family=ActionFamily::support_independence;
    check(is_code(ledger.incoming_preclone(context,seeded.receipt,
        Phase::initiate,incoming_wrapper,incoming_action,source_header,
        wrong_family,true).result,ErrorCode::payload_mismatch),
        "military_inbound_support_mismatch");
    const ClaimResult claimed=ledger.incoming_preclone(context,
        seeded.receipt,Phase::initiate,incoming_wrapper,incoming_action,
        source_header,military,true);
    check(claimed.result.ok(),"military_inbound_claim");

    const CloneProof valid_proof=clone_for(incoming_wrapper,incoming_action,
        target_wrapper,target_action,military,source_header.seq);
    CloneProof wrong_transport=valid_proof;
    wrong_transport.payload.family=ActionFamily::guarantee;
    check(is_code(ledger.postclone(context,claimed.ticket,Phase::initiate,
        wrong_transport),ErrorCode::payload_mismatch),
        "military_transport_guarantee_mismatch");
    check(ledger.postclone(context,claimed.ticket,Phase::initiate,
        valid_proof).ok(),"military_transport_clone");
    check(is_code(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,wrong_family,valid_proof.final_entry_header),
        ErrorCode::payload_mismatch),"military_execution_support_mismatch");
    check(ledger.consume_entry(context,claimed.ticket,Phase::initiate,
        target_wrapper,target_action,military,valid_proof.final_entry_header).ok(),
        "military_execution_consume");

    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed
        && inspected.view.payload.family==ActionFamily::military_access
        && inspected.view.payload.extra60==0,
        "military_lifecycle_family_preserved");

    AlliancePayload accept=payload_for(413u,Phase::accept);
    accept.family=ActionFamily::military_access;
    check(ledger.seed(context,"military-accept",accept,Phase::accept,
        wrapper_for(413u),action_for(413u),100u).result.ok(),
        "military_accept_state2_variant1");
    AlliancePayload reject=payload_for(414u,Phase::reject);
    reject.family=ActionFamily::military_access;
    check(ledger.seed(context,"military-reject",reject,Phase::reject,
        wrapper_for(414u),action_for(414u),100u).result.ok(),
        "military_reject_state1_variant1");
    AlliancePayload dissolve=payload_for(415u,Phase::dissolve);
    dissolve.family=ActionFamily::military_access;
    check(ledger.seed(context,"military-dissolve",dissolve,Phase::dissolve,
        wrapper_for(415u),action_for(415u),100u).result.ok(),
        "military_dissolve_state0_variant0");

    AlliancePayload bad=military;
    bad.variant38=0;
    check(is_code(ledger.seed(context,"military-bad-initiate",bad,
        Phase::initiate,wrapper_for(416u),action_for(416u),100u).result,
        ErrorCode::invalid_payload),"military_initiate_requires_variant1");
    bad=accept;
    bad.state34=1;
    check(is_code(ledger.seed(context,"military-bad-accept",bad,
        Phase::accept,wrapper_for(417u),action_for(417u),100u).result,
        ErrorCode::invalid_payload),"military_accept_requires_state2");
    bad=reject;
    bad.state34=2;
    check(is_code(ledger.seed(context,"military-bad-reject",bad,
        Phase::reject,wrapper_for(418u),action_for(418u),100u).result,
        ErrorCode::invalid_payload),"military_reject_requires_state1");
    bad=dissolve;
    bad.variant38=1;
    check(is_code(ledger.seed(context,"military-bad-dissolve",bad,
        Phase::dissolve,wrapper_for(419u),action_for(419u),100u).result,
        ErrorCode::invalid_payload),"military_dissolve_requires_variant0");
    bad=military;
    bad.extra60=1u;
    check(is_code(ledger.seed(context,"military-extra60",bad,
        Phase::initiate,wrapper_for(420u),action_for(420u),100u).result,
        ErrorCode::invalid_payload),"military_extra60_rejected");
    bad=military;
    bad.family=static_cast<ActionFamily>(99u);
    const auto unknown_family_result=ledger.seed(context,
        "military-unknown-family",bad,Phase::initiate,wrapper_for(421u),
        action_for(421u),100u).result;
    check(unknown_family_result.code==ErrorCode::invalid_payload,
        "military_unknown_family_rejected");
}

static void test_insult_lifecycle_and_isolation() {
    AllianceAuthorityLedger ledger(0xe1e1u);
    const Context context{0xe1e1u,70u};
    const AlliancePayload legacy=payload_for(500u,Phase::initiate);

    AlliancePayload ordinary=legacy;
    ordinary.family=ActionFamily::insult;
    ordinary.parameter40=-1;
    check(ordinary!=legacy,"insult_family_and_parameter_are_identity");
    AlliancePayload scornful=ordinary;
    scornful.parameter40=0;
    check(scornful!=ordinary,"insult_parameter_is_strictly_compared");
    scornful.parameter40=2147483647;
    const SeedResult scornful_seed=ledger.seed(context,"insult-scornful",
        scornful,Phase::initiate,wrapper_for(501u),action_for(501u),100u);
    check(scornful_seed.result.ok(),"scornful_insult_int32_max_valid");

    ordinary.parameter40=-1;
    const SeedResult ordinary_seed=ledger.seed(context,"insult-ordinary",
        ordinary,Phase::initiate,wrapper_for(500u),action_for(500u),100u);
    check(ordinary_seed.result.ok(),"ordinary_insult_seed");
    check(is_code(ledger.serializer(context,ordinary_seed.receipt,
        Phase::initiate,wrapper_for(500u),action_for(500u),legacy,
        header_for(501u)),ErrorCode::payload_mismatch),
        "insult_cannot_use_alliance_authority");
    check(ledger.serializer(context,ordinary_seed.receipt,Phase::initiate,
        wrapper_for(500u),action_for(500u),ordinary,header_for(500u)).ok(),
        "ordinary_insult_serializer");

    AlliancePayload non_insult_parameter=legacy;
    non_insult_parameter.parameter40=1;
    check(is_code(ledger.seed(context,"alliance-insult-parameter",
        non_insult_parameter,Phase::initiate,wrapper_for(502u),
        action_for(502u),100u).result,ErrorCode::invalid_payload),
        "non_insult_parameter_rejected");

    AlliancePayload bad_parameter=ordinary;
    bad_parameter.parameter40=-2;
    check(is_code(ledger.seed(context,"insult-parameter-negative",
        bad_parameter,Phase::initiate,wrapper_for(503u),action_for(503u),
        100u).result,ErrorCode::invalid_payload),
        "insult_parameter_below_minus_one_rejected");

    bad_parameter=ordinary;
    bad_parameter.parameter40=static_cast<std::int32_t>(-2147483647-1);
    check(is_code(ledger.seed(context,"insult-parameter-int32-min",
        bad_parameter,Phase::initiate,wrapper_for(504u),action_for(504u),
        100u).result,ErrorCode::invalid_payload),
        "insult_parameter_int32_min_rejected");

    AlliancePayload bad_extra=ordinary;
    bad_extra.extra60=1u;
    check(is_code(ledger.seed(context,"insult-extra60",
        bad_extra,Phase::initiate,wrapper_for(505u),action_for(505u),100u)
        .result,ErrorCode::invalid_payload),"insult_extra60_rejected");

    AlliancePayload bad_state=ordinary;
    bad_state.state34=1u;
    check(is_code(ledger.seed(context,"insult-state",
        bad_state,Phase::initiate,wrapper_for(506u),action_for(506u),100u)
        .result,ErrorCode::invalid_payload),"insult_state34_rejected");
    AlliancePayload bad_variant=ordinary;
    bad_variant.variant38=0u;
    check(is_code(ledger.seed(context,"insult-variant",
        bad_variant,Phase::initiate,wrapper_for(507u),action_for(507u),100u)
        .result,ErrorCode::invalid_payload),"insult_variant38_rejected");

    check(is_code(ledger.seed(context,"insult-accept",
        ordinary,Phase::accept,wrapper_for(508u),action_for(508u),100u)
        .result,ErrorCode::invalid_payload),"insult_accept_phase_rejected");
    check(is_code(ledger.seed(context,"insult-reject",
        ordinary,Phase::reject,wrapper_for(509u),action_for(509u),100u)
        .result,ErrorCode::invalid_payload),"insult_reject_phase_rejected");
    check(is_code(ledger.seed(context,"insult-dissolve",
        ordinary,Phase::dissolve,wrapper_for(510u),action_for(510u),100u)
        .result,ErrorCode::invalid_payload),"insult_dissolve_phase_rejected");

    const auto inspected=ledger.inspect(context,scornful_seed.receipt);
    check(inspected.result.ok()
        && inspected.view.payload.family==ActionFamily::insult
        && inspected.view.payload.parameter40==2147483647,
        "scornful_parameter_preserved");
}

static void test_destruction_and_deadline() {
    AllianceAuthorityLedger source_ledger(0x3333u);
    const Context context{0x3333u,1u};
    const AlliancePayload payload=payload_for(6u,Phase::reject);
    const ObjectRef source_wrapper=wrapper_for(6u);
    const ObjectRef source_action=action_for(6u);
    const NativeHeader header=header_for(99u);
    const SeedResult seeded=source_ledger.seed(context,"authority-source",payload,
        Phase::reject,source_wrapper,source_action,20u);
    check(seeded.result.ok(),"source_seed");
    check(is_code(source_ledger.source_destroyed(context,seeded.receipt,
        Phase::reject,SourceKind::outgoing,source_wrapper,source_action),
        ErrorCode::source_destroyed),"source_destroy_before_serialize");
    check(is_code(source_ledger.serializer(context,seeded.receipt,Phase::reject,
        source_wrapper,source_action,payload,header),
        ErrorCode::already_invalidated),"source_revoke_blocks_serialize");

    AllianceAuthorityLedger incoming_ledger(0x3444u);
    const Context incoming_context{0x3444u,1u};
    const AlliancePayload incoming_payload=payload_for(61u,Phase::reject);
    const ObjectRef outgoing=wrapper_for(61u);
    const ObjectRef outgoing_action=action_for(61u);
    const ObjectRef incoming=wrapper_for(62u);
    const ObjectRef incoming_action=action_for(62u);
    const SeedResult incoming_seed=incoming_ledger.seed(incoming_context,
        "authority-incoming",incoming_payload,Phase::reject,outgoing,
        outgoing_action,20u);
    check(incoming_seed.result.ok(),"incoming_seed");
    check(incoming_ledger.serializer(incoming_context,incoming_seed.receipt,
        Phase::reject,outgoing,outgoing_action,incoming_payload,header_for(100u))
        .ok(),"incoming_serializer");
    const ClaimResult incoming_claim=incoming_ledger.incoming_preclone(
        incoming_context,incoming_seed.receipt,Phase::reject,incoming,
        incoming_action,header_for(100u),incoming_payload,true);
    check(incoming_claim.result.ok(),"incoming_claim");
    check(is_code(incoming_ledger.source_destroyed(incoming_context,
        incoming_seed.receipt,Phase::reject,SourceKind::incoming,
        with_generation(incoming,incoming.generation+1u),incoming_action),
        ErrorCode::generation_mismatch),"incoming_wrong_generation");
    check(is_code(incoming_ledger.source_destroyed(incoming_context,
        incoming_seed.receipt,Phase::reject,SourceKind::incoming,incoming,
        incoming_action),ErrorCode::source_destroyed),
        "incoming_destroy_before_postclone");
    check(is_code(incoming_ledger.postclone(incoming_context,
        incoming_claim.ticket,Phase::reject,clone_for(incoming,incoming_action,
            wrapper_for(63u),action_for(63u),incoming_payload,100u)),
        ErrorCode::already_invalidated),"incoming_revoke_blocks_postclone");

    AllianceAuthorityLedger target_ledger(0x4444u);
    const Context target_context{0x4444u,2u};
    const AlliancePayload target_payload=payload_for(7u,Phase::dissolve);
    const ObjectRef target_source_wrapper=wrapper_for(70u);
    const ObjectRef target_source_action=action_for(70u);
    const ObjectRef target_incoming_wrapper=wrapper_for(71u);
    const ObjectRef target_incoming_action=action_for(71u);
    const ObjectRef target_wrapper=wrapper_for(107u);
    const ObjectRef target_action=action_for(107u);
    const NativeHeader target_header=header_for(100u);
    const SeedResult target_seed=target_ledger.seed(target_context,
        "authority-target",target_payload,Phase::dissolve,
        target_source_wrapper,target_source_action,20u);
    check(target_seed.result.ok(),"target_seed");
    check(target_ledger.serializer(target_context,target_seed.receipt,
        Phase::dissolve,target_source_wrapper,target_source_action,
        target_payload,target_header).ok(),"target_serializer");
    const ClaimResult target_claim=target_ledger.incoming_preclone(
        target_context,target_seed.receipt,Phase::dissolve,
        target_incoming_wrapper,target_incoming_action,target_header,
        target_payload,true);
    check(target_claim.result.ok(),"target_claim");
    const CloneProof target_proof=clone_for(target_incoming_wrapper,
        target_incoming_action,target_wrapper,target_action,target_payload,
        target_header.seq);
    check(target_ledger.postclone(target_context,target_claim.ticket,
        Phase::dissolve,target_proof).ok(),"target_postclone");
    const ObjectRef reused_target{target_action.address,
        target_action.generation+1u};
    check(is_code(target_ledger.target_destroyed(target_context,
        target_claim.ticket,Phase::dissolve,target_wrapper,reused_target),
        ErrorCode::generation_mismatch),"target_generation_destroy_rejected");
    check(is_code(target_ledger.target_destroyed(target_context,
        target_claim.ticket,Phase::dissolve,target_wrapper,target_action),
        ErrorCode::target_destroyed),"target_destroy_revokes");
    check(is_code(target_ledger.consume_entry(target_context,target_claim.ticket,
        Phase::dissolve,target_wrapper,target_action,target_payload,
        target_proof.final_entry_header),ErrorCode::already_invalidated),
        "target_revoke_blocks_consume");

    AllianceAuthorityLedger revoke_ledger(0x4555u);
    const Context revoke_context{0x4555u,2u};
    const AlliancePayload revoke_payload=payload_for(73u);
    const ObjectRef revoke_outgoing=wrapper_for(73u);
    const ObjectRef revoke_outgoing_action=action_for(73u);
    const SeedResult revoke_seed=revoke_ledger.seed(revoke_context,
        "authority-explicit-revoke",revoke_payload,Phase::accept,
        revoke_outgoing,revoke_outgoing_action,20u);
    check(revoke_seed.result.ok(),"explicit_revoke_seed");
    check(revoke_ledger.serializer(revoke_context,revoke_seed.receipt,
        Phase::accept,revoke_outgoing,revoke_outgoing_action,revoke_payload,
        header_for(102u)).ok(),"explicit_revoke_serializer");
    check(is_code(revoke_ledger.revoke_request(revoke_context,
        revoke_seed.receipt,Phase::accept),ErrorCode::request_revoked),
        "explicit_revoke_terminal");
    check(is_code(revoke_ledger.revoke_request(revoke_context,
        revoke_seed.receipt,Phase::accept),ErrorCode::already_invalidated),
        "explicit_revoke_once");

    AllianceAuthorityLedger deadline_ledger(0x5555u);
    const Context deadline_context{0x5555u,4u};
    const SeedResult deadline_seed=deadline_ledger.seed(deadline_context,
        "authority-deadline",payload_for(8u,Phase::initiate),Phase::initiate,
        wrapper_for(8u),
        action_for(8u),5u);
    check(deadline_seed.result.ok(),"deadline_seed");
    const Context after_deadline{0x5555u,6u};
    check(is_code(deadline_ledger.serializer(after_deadline,
        deadline_seed.receipt,Phase::initiate,wrapper_for(8u),action_for(8u),
        payload_for(8u,Phase::initiate),header_for(101u)),
        ErrorCode::deadline_expired),
        "deadline_invalidates");
    const auto expired_view=deadline_ledger.inspect(after_deadline,
        deadline_seed.receipt);
    check(expired_view.result.ok()
        && expired_view.view.state==State::invalidated,
        "expired_state_recorded");
}

static void test_fresh_intent_reuse() {
    AllianceAuthorityLedger ledger(0x7777u);
    const Context context{0x7777u,10u};
    const AlliancePayload old_payload=payload_for(90u);
    const ObjectRef old_outgoing=wrapper_for(90u);
    const ObjectRef old_outgoing_action=action_for(90u);
    const ObjectRef old_incoming=wrapper_for(91u);
    const ObjectRef old_incoming_action=action_for(91u);
    const ObjectRef old_target=wrapper_for(92u);
    const ObjectRef old_target_action=action_for(92u);
    const NativeHeader old_header=header_for(200u);
    const SeedResult old_seed=ledger.seed(context,"authority-old-consumed",
        old_payload,Phase::accept,old_outgoing,old_outgoing_action,100u);
    check(old_seed.result.ok(),"reuse_old_seed");
    check(ledger.serializer(context,old_seed.receipt,Phase::accept,
        old_outgoing,old_outgoing_action,old_payload,old_header).ok(),
        "reuse_old_serializer");
    const ClaimResult old_claim=ledger.incoming_preclone(context,
        old_seed.receipt,Phase::accept,old_incoming,old_incoming_action,
        old_header,old_payload,true);
    check(old_claim.result.ok(),"reuse_old_claim");
    const CloneProof old_proof=clone_for(old_incoming,old_incoming_action,
        old_target,old_target_action,old_payload,old_header.seq);
    check(ledger.postclone(context,old_claim.ticket,Phase::accept,old_proof)
        .ok(),"reuse_old_postclone");
    check(is_code(ledger.consume_entry(context,old_claim.ticket,Phase::accept,
        old_target,with_generation(old_target_action,
            old_target_action.generation+1u),old_payload,
        old_proof.final_entry_header),ErrorCode::generation_mismatch),
        "reuse_old_generation_guard");
    check(ledger.consume_entry(context,old_claim.ticket,Phase::accept,
        old_target,old_target_action,old_payload,old_proof.final_entry_header)
        .ok(),"reuse_old_consumed");

    const ObjectRef destroyed_source=wrapper_for(93u);
    const ObjectRef destroyed_action=action_for(93u);
    const SeedResult invalidated=ledger.seed(context,"authority-old-destroyed",
        payload_for(93u),Phase::accept,destroyed_source,destroyed_action,100u);
    check(invalidated.result.ok(),"reuse_destroyed_seed");
    check(is_code(ledger.source_destroyed(context,invalidated.receipt,
        Phase::accept,SourceKind::outgoing,destroyed_source,destroyed_action),
        ErrorCode::source_destroyed),"reuse_destroyed_source");

    const ObjectRef fresh_outgoing=with_generation(destroyed_source,
        destroyed_source.generation+1000u);
    const ObjectRef fresh_outgoing_action=with_generation(destroyed_action,
        destroyed_action.generation+1000u);
    const ObjectRef fresh_incoming=with_generation(old_incoming,
        old_incoming.generation+1000u);
    const ObjectRef fresh_incoming_action=with_generation(old_incoming_action,
        old_incoming_action.generation+1000u);
    const ObjectRef fresh_target=with_generation(old_target,
        old_target.generation+1000u);
    const ObjectRef fresh_target_action=with_generation(old_target_action,
        old_target_action.generation+1000u);
    const AlliancePayload fresh_payload=payload_for(94u);
    const NativeHeader fresh_header=header_for(201u);
    const SeedResult fresh_seed=ledger.seed(context,"authority-fresh-intent",
        fresh_payload,Phase::accept,fresh_outgoing,fresh_outgoing_action,100u);
    check(fresh_seed.result.ok(),"fresh_terminal_address_reuse_seed");
    check(is_code(ledger.serializer(context,fresh_seed.receipt,Phase::accept,
        fresh_outgoing,fresh_outgoing_action,fresh_payload,old_header),
        ErrorCode::ambiguous_header),"header_tombstone_not_reused");
    check(ledger.serializer(context,fresh_seed.receipt,Phase::accept,
        fresh_outgoing,fresh_outgoing_action,fresh_payload,fresh_header).ok(),
        "fresh_terminal_address_reuse_serializer");
    const ClaimResult fresh_claim=ledger.incoming_preclone(context,
        fresh_seed.receipt,Phase::accept,fresh_incoming,fresh_incoming_action,
        fresh_header,fresh_payload,true);
    check(fresh_claim.result.ok(),"fresh_terminal_address_reuse_claim");
    const CloneProof fresh_proof=clone_for(fresh_incoming,fresh_incoming_action,
        fresh_target,fresh_target_action,fresh_payload,fresh_header.seq);
    check(ledger.postclone(context,fresh_claim.ticket,Phase::accept,fresh_proof)
        .ok(),"fresh_terminal_address_reuse_postclone");
    check(ledger.consume_entry(context,fresh_claim.ticket,Phase::accept,
        fresh_target,fresh_target_action,fresh_payload,
        fresh_proof.final_entry_header).ok(),
        "fresh_terminal_address_reuse_consume");
}

static void test_same_intent_detached_address_reuse() {
    for (unsigned reuse_incoming=0;reuse_incoming<2;++reuse_incoming) {
        AllianceAuthorityLedger ledger(0x8888u);
        const Context context{0x8888u,10u};
        const AlliancePayload payload=payload_for(200u,Phase::initiate);
        const ObjectRef outgoing=wrapper_for(200u),out_action=action_for(200u);
        const ObjectRef incoming=reuse_incoming?with_generation(outgoing,1000u):wrapper_for(201u);
        const ObjectRef in_action=reuse_incoming?with_generation(out_action,1001u):action_for(201u);
        const ObjectRef target=reuse_incoming?wrapper_for(202u):with_generation(outgoing,2000u);
        const ObjectRef target_action=reuse_incoming?action_for(202u):with_generation(out_action,2001u);
        const NativeHeader header=header_for(300u+reuse_incoming);
        const auto seed=ledger.seed(context,"reuse-within-intent",payload,
            Phase::initiate,outgoing,out_action,100u);
        check(seed.result.ok(),"reuse_within_seed");
        check(ledger.serializer(context,seed.receipt,Phase::initiate,
            outgoing,out_action,payload,header).ok(),"reuse_within_serialize");
        check(is_code(ledger.source_destroyed(context,seed.receipt,Phase::initiate,
            SourceKind::outgoing,outgoing,out_action),ErrorCode::outgoing_detached),
            "reuse_within_detach_outgoing");
        const auto claim=ledger.incoming_preclone(context,seed.receipt,
            Phase::initiate,incoming,in_action,header,payload,true);
        check(claim.result.ok(),"reuse_within_trusted_incoming");
        const auto proof=clone_for(incoming,in_action,target,target_action,payload,header.seq);
        check(ledger.postclone(context,claim.ticket,Phase::initiate,proof).ok(),
            "reuse_within_postclone");
        check(is_code(ledger.source_destroyed(context,seed.receipt,Phase::initiate,
            SourceKind::incoming,with_generation(incoming,incoming.generation+1),
            in_action),ErrorCode::generation_mismatch),"reuse_within_wrong_source_generation");
        check(is_code(ledger.source_destroyed(context,seed.receipt,Phase::initiate,
            SourceKind::incoming,incoming,in_action),ErrorCode::incoming_detached),
            "reuse_within_detach_incoming");
        check(is_code(ledger.consume_entry(context,claim.ticket,Phase::initiate,
            with_generation(target,target.generation+1),target_action,payload,
            proof.final_entry_header),ErrorCode::generation_mismatch),
            "reuse_within_wrong_target_generation");
        check(ledger.consume_entry(context,claim.ticket,Phase::initiate,
            target,target_action,payload,proof.final_entry_header).ok(),
            "reuse_within_one_valid_consume");
    }
}

static void test_capacity_and_session_binding() {
    AllianceAuthorityLedger ledger(0x6666u);
    const Context context{0x6666u,0u};
    SeedResult first{};
    for (unsigned i=0;i<64;++i) {
        char id[32]{};
        std::snprintf(id,sizeof(id),"authority-cap-%02u",i);
        const SeedResult seeded=ledger.seed(context,id,
            payload_for(100u+i,Phase::initiate),
            Phase::initiate,wrapper_for(1000u+i),action_for(1000u+i),100u);
        if (i==0) first=seeded;
        check(seeded.result.ok(),"capacity_live_seed");
    }
    const SeedResult full=ledger.seed(context,"authority-cap-overflow",
        payload_for(999u,Phase::initiate),Phase::initiate,wrapper_for(999u),
        action_for(999u),
        100u);
    check(is_code(full.result,ErrorCode::capacity_full),"capacity_bound");
    const auto first_view=ledger.inspect(context,first.receipt);
    check(first_view.result.ok() && first_view.view.state==State::seeded,
        "capacity_does_not_evict_live");
    check(is_code(ledger.revoke_request(context,first.receipt,Phase::initiate),
        ErrorCode::request_revoked),"terminal_does_not_free_slot");
    const SeedResult still_full=ledger.seed(context,"authority-cap-after-term",
        payload_for(5001u,Phase::initiate),Phase::initiate,wrapper_for(5001u),
        action_for(5001u),100u);
    check(is_code(still_full.result,ErrorCode::capacity_full),
        "terminal_tombstone_preserves_capacity");

    const Context wrong_epoch{0x7777u,0u};
    check(is_code(ledger.invalidate_expired(wrong_epoch),ErrorCode::wrong_epoch),
        "capacity_epoch_isolated");
    check(is_code(ledger.inspect(wrong_epoch,first.receipt).result,
        ErrorCode::wrong_epoch),"epoch_bound_at_construction");
}

int main() {
    test_normal_and_exact_matching();
    test_wrong_context_phase_and_headers();
    test_action_family_binding();
    test_declare_war_lifecycle_and_isolation();
    test_peace_lifecycle_and_isolation();
    test_peace_offer_direction_lifecycle();
    test_peace_handler_payload_matching();
    test_spy_network_lifecycle_and_isolation();
    test_guarantee_lifecycle_and_isolation();
    test_support_independence_lifecycle_and_isolation();
    test_military_access_lifecycle_and_isolation();
    test_insult_lifecycle_and_isolation();
    test_destruction_and_deadline();
    test_fresh_intent_reuse();
    test_same_intent_detached_address_reuse();
    test_capacity_and_session_binding();
    const bool passed=g_failures==0;
    std::printf(
        "{\"passed\":%s,\"checks\":%u,\"failures\":%u,"
        "\"capacity\":%u,\"heap_or_io_in_ledger\":false,"
        "\"native_calls\":false}\n",
        passed?"true":"false",g_checks,g_failures,
        static_cast<unsigned>(bridge::alliance_authority::kLedgerCapacity));
    return passed?0:1;
}

