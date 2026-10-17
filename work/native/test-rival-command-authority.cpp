#include <cstdint>
#include <cstdio>

#include "rival-command-authority.h"

using bridge::rival_command_authority::ClaimResult;
using bridge::rival_command_authority::CloneProof;
using bridge::rival_command_authority::CommandKind;
using bridge::rival_command_authority::Context;
using bridge::rival_command_authority::DetachKind;
using bridge::rival_command_authority::ErrorCode;
using bridge::rival_command_authority::Family;
using bridge::rival_command_authority::NativeHeader;
using bridge::rival_command_authority::ObjectRef;
using bridge::rival_command_authority::RivalCommandAuthorityLedger;
using bridge::rival_command_authority::RivalPayload;
using bridge::rival_command_authority::State;

static unsigned g_checks=0;
static unsigned g_failures=0;

static void check(bool value,const char* name) {
    ++g_checks;
    if (!value) {
        ++g_failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static bool is_code(const bridge::rival_command_authority::OperationResult& result,
    ErrorCode code) {
    return result.code==code;
}

static ObjectRef ref(std::uint64_t address,std::uint64_t generation) {
    return ObjectRef{static_cast<std::uintptr_t>(address),generation};
}

static RivalPayload payload(std::uint64_t actor=0x100007a00415246ull,
    std::uint64_t target=0x100007500525542ull,
    CommandKind command=CommandKind::set_rival,std::int32_t date=42) {
    RivalPayload value{};
    value.family=Family::rival;
    value.command=command;
    value.actor=actor;
    value.target=target;
    value.old_rival=0;
    value.date_raw=date;
    return value;
}

static NativeHeader header(std::uint32_t sequence,std::uint8_t reserved=7,
    std::uint16_t origin=0x1234u) {
    return NativeHeader{3u,7,-4,0x4040u,12,origin,5u,reserved,sequence};
}

static CloneProof proof_for(ObjectRef loaded,ObjectRef target,
    const RivalPayload& value,const NativeHeader& source_header) {
    CloneProof proof{};
    proof.loaded=loaded;
    proof.target=target;
    proof.payload=value;
    proof.observed_clone_header=source_header;
    proof.target_header=source_header;
    return proof;
}

static void test_direct_success_chain() {
    RivalCommandAuthorityLedger ledger(0xabcdu);
    const Context context{0xabcdu,1000u,42};
    const RivalPayload value=payload();
    const ObjectRef source=ref(0x100000u,1u);
    const ObjectRef loaded=ref(0x200000u,2u);
    const ObjectRef target=ref(0x300000u,3u);
    const NativeHeader source_header=header(77u);

    const auto seeded=ledger.seed(context,"rival_full",value,source,5000u);
    check(seeded.result.ok(),"seed_direct_command");
    check(ledger.serialize_source(context,seeded.receipt,source,value,
        source_header).ok(),"serialize_source_direct");
    check(is_code(ledger.serialize_source(context,seeded.receipt,
        ref(source.address,source.generation+1u),value,source_header),
        ErrorCode::duplicate_header),"serialize_after_stage_is_rejected");

    const auto untrusted=ledger.load_native(context,seeded.receipt,loaded,
        source_header,value,false);
    check(is_code(untrusted.result,ErrorCode::untrusted_pipeline),
        "untrusted_load_rejected");
    const auto wrong_header=ledger.load_native(context,seeded.receipt,loaded,
        header(78u),value,true);
    check(is_code(wrong_header.result,ErrorCode::header_mismatch),
        "load_requires_exact_header");
    RivalPayload wrong_value=value;
    wrong_value.target^=1u;
    const auto wrong_payload=ledger.load_native(context,seeded.receipt,loaded,
        source_header,wrong_value,true);
    check(is_code(wrong_payload.result,ErrorCode::payload_mismatch),
        "load_requires_exact_payload");
    const ClaimResult claimed=ledger.load_native(context,seeded.receipt,loaded,
        source_header,value,true);
    check(claimed.result.ok(),"trusted_direct_load");
    check(is_code(ledger.load_native(context,seeded.receipt,ref(0x220000u,7u),
        source_header,value,true).result,ErrorCode::duplicate_claim),
        "claim_is_single_use");

    CloneProof bad_loaded=proof_for(ref(loaded.address,loaded.generation+1u),
        target,value,source_header);
    check(is_code(ledger.clone_native(context,claimed.ticket,bad_loaded),
        ErrorCode::generation_mismatch),"clone_loaded_generation_guard");
    const CloneProof proof=proof_for(loaded,target,value,source_header);
    check(ledger.clone_native(context,claimed.ticket,proof).ok(),
        "direct_clone_success");
    check(ledger.consume(context,claimed.ticket,target,value,source_header).ok(),
        "direct_consume_success");
    check(is_code(ledger.consume(context,claimed.ticket,target,value,source_header),
        ErrorCode::already_consumed),"consume_is_idempotency_guarded");
    const auto inspected=ledger.inspect(context,seeded.receipt);
    check(inspected.result.ok() && inspected.view.state==State::consumed,
        "consumed_state_visible");
    check(inspected.view.source==source && inspected.view.loaded==loaded
        && inspected.view.target==target,"record_keeps_direct_object_refs");
    check(!inspected.view.source_alive && !inspected.view.loaded_alive
        && !inspected.view.target_alive,"consumed_objects_are_not_live");
}

static void test_header_contract() {
    const Context context{0x1111u,10u,77};
    const RivalPayload value=payload(0x1001u,0x2002u,CommandKind::remove_rival,77);
    const ObjectRef source=ref(0x410000u,1u);
    const ObjectRef loaded=ref(0x420000u,1u);
    const ObjectRef target=ref(0x430000u,1u);
    const NativeHeader source_header=header(101u,9u);

    RivalCommandAuthorityLedger unassigned_ledger(0x1111u);
    const auto unassigned_seed=unassigned_ledger.seed(context,"unassigned",
        value,source,500u);
    NativeHeader unassigned=source_header;
    unassigned.origin48=0xffffu;
    unassigned.sequence4c=0u;
    check(is_code(unassigned_ledger.serialize_source(context,
        unassigned_seed.receipt,source,value,unassigned),
        ErrorCode::invalid_argument),"unassigned_header_rejected");
    NativeHeader assigned_ff=source_header;
    assigned_ff.origin48=0xffffu;
    assigned_ff.sequence4c=1u;
    RivalCommandAuthorityLedger assigned_ledger(0x1111u);
    const auto assigned_seed=assigned_ledger.seed(context,"assigned_ff",
        value,source,500u);
    check(assigned_ledger.serialize_source(context,assigned_seed.receipt,
        source,value,assigned_ff).ok(),"assigned_ff_sequence_is_valid");

    RivalCommandAuthorityLedger ledger(0x1111u);
    const auto seeded=ledger.seed(context,"header_exact",value,source,500u);
    check(ledger.serialize_source(context,seeded.receipt,source,value,
        source_header).ok(),"header_source_bound");
    NativeHeader reserved_mismatch=source_header;
    reserved_mismatch.reserved4b^=1u;
    check(is_code(ledger.load_native(context,seeded.receipt,loaded,
        reserved_mismatch,value,true).result,ErrorCode::header_mismatch),
        "reserved4b_load_mismatch");
    const auto claimed=ledger.load_native(context,seeded.receipt,loaded,
        source_header,value,true);
    check(claimed.result.ok(),"header_exact_claim");
    CloneProof clone_bad=proof_for(loaded,target,value,source_header);
    clone_bad.observed_clone_header.reserved4b^=1u;
    check(is_code(ledger.clone_native(context,claimed.ticket,clone_bad),
        ErrorCode::header_mismatch),"reserved4b_clone_mismatch");
    const CloneProof clone_good=proof_for(loaded,target,value,source_header);
    check(ledger.clone_native(context,claimed.ticket,clone_good).ok(),
        "clone_copies_complete_header");
    NativeHeader target_bad=source_header;
    target_bad.reserved4b^=2u;
    check(is_code(ledger.consume(context,claimed.ticket,target,value,target_bad),
        ErrorCode::header_mismatch),"reserved4b_consume_mismatch");
    const auto view=ledger.inspect(context,seeded.receipt);
    check(view.view.target_header==source_header
        && view.view.loaded_header==source_header,
        "clone_keeps_source_header_without_reset_marker");
    check(ledger.consume(context,claimed.ticket,target,value,source_header).ok(),
        "complete_header_consumes");

    RivalCommandAuthorityLedger collision(0x1111u);
    const auto first=collision.seed(context,"header_first",value,
        ref(0x440000u,1u),500u);
    const auto second=collision.seed(context,"header_second",value,
        ref(0x450000u,1u),500u);
    check(collision.serialize_source(context,first.receipt,ref(0x440000u,1u),
        value,source_header).ok(),"first_header_collision_setup");
    check(is_code(collision.serialize_source(context,second.receipt,
        ref(0x450000u,1u),value,source_header),ErrorCode::ambiguous_header),
        "full_header_collision_rejected");
    NativeHeader distinct=source_header;
    distinct.reserved4b^=4u;
    check(collision.serialize_source(context,second.receipt,
        ref(0x450000u,1u),value,distinct).ok(),
        "reserved4b_distinguishes_header");
}

static void test_destroy_and_detach_semantics() {
    const Context context{0x2222u,100u,8};
    const RivalPayload value=payload(0x9001u,0x9002u,CommandKind::set_rival,8);
    const NativeHeader native_header=header(201u);

    RivalCommandAuthorityLedger before_copy(0x2222u);
    const ObjectRef early_source=ref(0x610000u,1u);
    const auto early=before_copy.seed(context,"source_before_copy",value,
        early_source,200u);
    check(is_code(before_copy.detach_source(context,early.receipt,
        DetachKind::source,early_source),ErrorCode::source_destroyed),
        "source_destroy_before_serialize_invalidates");
    check(before_copy.inspect(context,early.receipt).view.state==State::invalidated,
        "source_destroyed_state_visible");

    RivalCommandAuthorityLedger copied(0x2222u);
    const ObjectRef source=ref(0x620000u,1u);
    const ObjectRef loaded=ref(0x630000u,1u);
    const ObjectRef target=ref(0x640000u,1u);
    const auto seeded=copied.seed(context,"destroy_after_copy",value,source,200u);
    check(copied.serialize_source(context,seeded.receipt,source,value,
        native_header).ok(),"copy_source_serialized");
    check(is_code(copied.detach_source(context,seeded.receipt,
        DetachKind::source,source),ErrorCode::source_detached),
        "source_destroy_after_copy_detaches_only");
    check(copied.load_native(context,seeded.receipt,loaded,native_header,
        value,true).result.ok(),"load_after_source_destroy");
    const auto claim=copied.load_native(context,seeded.receipt,loaded,
        native_header,value,true);
    check(is_code(claim.result,ErrorCode::duplicate_claim),
        "load_after_source_destroy_claimed_once");
    // Recover the ticket from the first successful load by repeating the
    // chain in a fresh ledger; the first ledger's result remains intentional.
    RivalCommandAuthorityLedger copied_again(0x2222u);
    const auto seeded_again=copied_again.seed(context,"destroy_after_clone",
        value,source,200u);
    check(copied_again.serialize_source(context,seeded_again.receipt,source,
        value,native_header).ok(),"copy_again_serialized");
    check(is_code(copied_again.detach_source(context,seeded_again.receipt,
        DetachKind::source,source),ErrorCode::source_detached),
        "source_detach_is_nonfatal_after_copy");
    const auto claim_again=copied_again.load_native(context,seeded_again.receipt,
        loaded,native_header,value,true);
    check(claim_again.result.ok(),"copy_again_loaded");
    check(copied_again.clone_native(context,claim_again.ticket,
        proof_for(loaded,target,value,native_header)).ok(),
        "copy_again_cloned");
    check(is_code(copied_again.detach_source(context,seeded_again.receipt,
        DetachKind::loaded,loaded),ErrorCode::loaded_detached),
        "loaded_destroy_after_clone_detaches_only");
    check(copied_again.consume(context,claim_again.ticket,target,value,
        native_header).ok(),"target_survives_source_and_loaded_destroy");

    RivalCommandAuthorityLedger loaded_before_clone(0x2222u);
    const auto early_load=loaded_before_clone.seed(context,"loaded_early",
        value,ref(0x650000u,1u),200u);
    check(loaded_before_clone.serialize_source(context,early_load.receipt,
        ref(0x650000u,1u),value,native_header).ok(),"loaded_early_serialized");
    const ObjectRef early_loaded=ref(0x660000u,1u);
    check(loaded_before_clone.load_native(context,early_load.receipt,
        early_loaded,native_header,value,true).result.ok(),"loaded_early_claim");
    check(is_code(loaded_before_clone.detach_source(context,early_load.receipt,
        DetachKind::loaded,early_loaded),ErrorCode::loaded_destroyed),
        "loaded_destroy_before_clone_invalidates");
    check(loaded_before_clone.inspect(context,early_load.receipt).view.state
        ==State::invalidated,"loaded_destroyed_state_visible");

    RivalCommandAuthorityLedger target_destroyed(0x2222u);
    const auto target_seed=target_destroyed.seed(context,"target_destroy",
        value,ref(0x670000u,1u),200u);
    check(target_destroyed.serialize_source(context,target_seed.receipt,
        ref(0x670000u,1u),value,native_header).ok(),"target_serialized");
    const auto target_claim=target_destroyed.load_native(context,target_seed.receipt,
        ref(0x680000u,1u),native_header,value,true);
    check(target_claim.result.ok(),"target_claimed");
    const ObjectRef target_object=ref(0x690000u,1u);
    check(target_destroyed.clone_native(context,target_claim.ticket,
        proof_for(ref(0x680000u,1u),target_object,value,native_header)).ok(),
        "target_clone_for_destroy");
    check(is_code(target_destroyed.destroy_target(context,target_claim.ticket,
        target_object),ErrorCode::target_destroyed),"target_destroy_invalidates");
    check(is_code(target_destroyed.consume(context,target_claim.ticket,
        target_object,value,native_header),ErrorCode::already_invalidated),
        "destroyed_target_cannot_consume");
}

static void test_generation_reuse() {
    const Context context{0x3333u,1u,10};
    const RivalPayload value=payload(0x7001u,0x7002u,CommandKind::set_rival,10);
    RivalCommandAuthorityLedger ledger(0x3333u);
    const ObjectRef source_v1=ref(0x700000u,1u);
    const auto first=ledger.seed(context,"generation_one",value,source_v1,100u);
    check(first.result.ok(),"generation_one_seed");
    check(is_code(ledger.seed(context,"generation_two_live",value,
        ref(source_v1.address,2u),100u).result,ErrorCode::generation_mismatch),
        "live_generation_reuse_rejected");
    check(is_code(ledger.seed(context,"same_object_live",value,source_v1,100u).result,
        ErrorCode::identity_in_use),"live_identity_reuse_rejected");
    check(is_code(ledger.detach_source(context,first.receipt,DetachKind::source,
        source_v1),ErrorCode::source_destroyed),"generation_one_released");
    const ObjectRef source_v2=ref(source_v1.address,2u);
    const auto second=ledger.seed(context,"generation_two_after_destroy",value,
        source_v2,100u);
    check(second.result.ok(),"released_address_accepts_new_generation");

    RivalCommandAuthorityLedger active_target(0x3333u);
    const auto seeded=active_target.seed(context,"target_generation",value,
        ref(0x710000u,1u),100u);
    check(active_target.serialize_source(context,seeded.receipt,
        ref(0x710000u,1u),value,header(301u)).ok(),"target_generation_serialized");
    const auto claim=active_target.load_native(context,seeded.receipt,
        ref(0x720000u,2u),header(301u),value,true);
    check(claim.result.ok(),"target_generation_loaded");
    const ObjectRef target_v1=ref(0x730000u,3u);
    check(active_target.clone_native(context,claim.ticket,
        proof_for(ref(0x720000u,2u),target_v1,value,header(301u))).ok(),
        "target_generation_cloned");
    check(is_code(active_target.seed(context,"target_generation_reuse",value,
        ref(target_v1.address,target_v1.generation+1u),100u).result,
        ErrorCode::generation_mismatch),"active_target_generation_reuse_rejected");

    // One address is deliberately observed as source generation 1, then as
    // loaded generation 2; target generation 3 is rejected while generation 2
    // remains live.  This is the direct-command three-generation guard.
    RivalCommandAuthorityLedger three(0x3333u);
    const ObjectRef reused_source=ref(0x740000u,1u);
    const auto three_seed=three.seed(context,"three_generation",value,
        reused_source,100u);
    check(three.serialize_source(context,three_seed.receipt,reused_source,value,
        header(302u)).ok(),"three_source_serialized");
    check(is_code(three.detach_source(context,three_seed.receipt,
        DetachKind::source,reused_source),ErrorCode::source_detached),
        "three_source_detached");
    const ObjectRef reused_loaded=ref(0x740000u,2u);
    const auto three_claim=three.load_native(context,three_seed.receipt,
        reused_loaded,header(302u),value,true);
    check(three_claim.result.ok(),"three_loaded_generation_two");
    check(is_code(three.clone_native(context,three_claim.ticket,
        proof_for(reused_loaded,ref(0x740000u,3u),value,header(302u))),
        ErrorCode::generation_mismatch),"three_target_generation_three_rejected");
}

static void test_context_deadline_and_claims() {
    const RivalPayload value=payload(0x8001u,0x8002u,CommandKind::remove_rival,12);
    const ObjectRef source=ref(0x800000u,1u);
    const Context context{0x4444u,100u,12};

    RivalCommandAuthorityLedger ledger(0x4444u);
    check(is_code(ledger.seed(Context{0x5555u,100u,12},"wrong_epoch",value,
        source,200u).result,ErrorCode::wrong_epoch),"seed_epoch_binding");
    RivalPayload wrong_date=value;
    wrong_date.date_raw=13;
    check(is_code(ledger.seed(context,"wrong_date",wrong_date,source,200u).result,
        ErrorCode::invalid_payload),"seed_date_binding");
    check(is_code(ledger.seed(context,"bad_deadline_zero",value,source,100u).result,
        ErrorCode::invalid_argument),"deadline_must_be_future");
    check(is_code(ledger.seed(context,"bad_deadline_long",value,source,60101u).result,
        ErrorCode::invalid_argument),"deadline_ttl_is_bounded");
    check(is_code(ledger.seed(context,"",value,source,200u).result,
        ErrorCode::request_id_invalid),"request_id_must_be_nonempty");
    const auto seeded=ledger.seed(context,"context_bound",value,source,200u);
    check(seeded.result.ok(),"context_seed");
    check(is_code(ledger.seed(context,"context_bound",value,ref(0x810000u,1u),200u).result,
        ErrorCode::duplicate_request),"request_id_replay_rejected");
    check(is_code(ledger.load_native(context,seeded.receipt,ref(0x820000u,1u),
        header(401u),value,true).result,ErrorCode::invalid_stage),
        "load_before_serialize_stage_guard");
    check(is_code(ledger.serialize_source(context,seeded.receipt,source,value,
        header(401u)),ErrorCode::ok),"context_serialized");
    const auto claim=ledger.load_native(context,seeded.receipt,ref(0x820000u,1u),
        header(401u),value,true);
    check(claim.result.ok(),"context_claim");
    check(is_code(ledger.consume(context,claim.ticket,ref(0x830000u,1u),value,
        header(401u)),ErrorCode::invalid_stage),"consume_before_clone_stage_guard");
    ClaimResult forged=claim;
    forged.ticket.claim_serial+=1u;
    check(is_code(ledger.clone_native(context,forged.ticket,
        proof_for(ref(0x820000u,1u),ref(0x830000u,1u),value,header(401u))),
        ErrorCode::claim_mismatch),"claim_ticket_binding");
    check(is_code(ledger.clone_native(Context{0x5555u,100u,12},claim.ticket,
        proof_for(ref(0x820000u,1u),ref(0x830000u,1u),value,header(401u))),
        ErrorCode::wrong_epoch),"clone_epoch_binding");

    RivalCommandAuthorityLedger dated(0x4444u);
    const auto dated_seed=dated.seed(context,"date_expiry",value,
        ref(0x840000u,1u),200u);
    check(is_code(dated.serialize_source(Context{0x4444u,100u,13},
        dated_seed.receipt,ref(0x840000u,1u),value,header(402u)),
        ErrorCode::date_mismatch),"date_change_invalidates_live_claim");
    check(dated.inspect(context,dated_seed.receipt).view.state==State::invalidated,
        "date_invalidated_state_visible");

    RivalCommandAuthorityLedger expired(0x4444u);
    const auto expired_seed=expired.seed(context,"tick_expiry",value,
        ref(0x850000u,1u),200u);
    const auto invalidated=expired.invalidate_expired(Context{0x4444u,201u,12});
    check(invalidated.result.ok() && invalidated.invalidated==1u,
        "deadline_expiry_invalidates_live_record");
    check(expired.inspect(context,expired_seed.receipt).view.state
        ==State::invalidated,"deadline_invalidated_state_visible");

    RivalCommandAuthorityLedger revoked(0x4444u);
    const auto revoked_seed=revoked.seed(context,"revoked",value,
        ref(0x860000u,1u),200u);
    check(is_code(revoked.revoke_request(context,revoked_seed.receipt),
        ErrorCode::request_revoked),"explicit_revoke");
    check(is_code(revoked.revoke_request(context,revoked_seed.receipt),
        ErrorCode::already_invalidated),"revoke_is_not_replayed");
    revoked.reset_session_epoch(0x9999u);
    check(is_code(revoked.inspect(Context{0x9999u,100u,12},revoked_seed.receipt).result,
        ErrorCode::claim_mismatch),"reset_drops_old_receipts");
}

int main() {
    static_assert(sizeof(NativeHeader)>=24u,"header retains reserved4b and alignment");
    test_direct_success_chain();
    test_header_contract();
    test_destroy_and_detach_semantics();
    test_generation_reuse();
    test_context_deadline_and_claims();
    std::printf("checks=%u failures=%u status=%s\n",g_checks,g_failures,
        g_failures==0?"passed":"failed");
    return g_failures==0?0:1;
}
