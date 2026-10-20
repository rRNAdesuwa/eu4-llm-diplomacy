#pragma once

// Bounded, allocation-free authority hand-off ledger.
//
// This header deliberately contains no native calls, file I/O, address
// discovery, or policy decisions.  The caller supplies the trusted object
// identities, the pipeline proof bit, and the current session/tick context.
// Every identity contains a generation so an address reuse cannot silently
// match an older grant.

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include "declarewar-payload.h"
#include "peace-payload-ref.h"

namespace bridge::alliance_authority {

constexpr std::size_t kLedgerCapacity=64;
constexpr std::size_t kMaxRequestId=64;
constexpr std::uint16_t kInvalidSlot=0xffffu;
constexpr std::uint64_t kMaxDeadlineTtlMs=60000u;

enum class Phase : std::uint8_t {
    initiate=0,
    accept=1,
    reject=2,
    dissolve=3
};

// The native action layout is shared by alliance, royal-marriage,
// improve-relations, spy-network, guarantee, support-independence,
// military-access, insult, vassalization, favor-for-gold, favor-for-trust,
// favor-for-men, curry-favors, send-gift, and influence-nation actions.
// The family is part of the authority identity so a receipt issued for one
// action family cannot authorize another family.
enum class ActionFamily : std::uint8_t {
    alliance=0,
    royal_marriage=1,
    improve_relations=2,
    spy_network=3,
    guarantee=4,
    support_independence=5,
    military_access=6,
    insult=7,
    vassalization=8,
    declare_war=9,
    peace=10,
    // Native selector 0x3bce / public action trade_favors_for_gold.
    favor_gold=11,
    // Native selector 0x3acc / public actions curry_favors and
    // stop_curry_favors.  Start/stop is carried by variant38 and the ledger
    // phase, just like the existing one-sided task families.
    curry_favors=12,
    // Native selectors 0x3bd3 / 0x3bcf.  Both are one-shot negotiated
    // proposals with initiate/accept/reject phases.
    favor_trust=13,
    favor_men=14,
    // Native selector 0x2948 / public send_gift.  The signed +0x40 raw
    // amount is bound through AlliancePayload::parameter40.
    gift=15,
    // Native selector 0x346e / public influence_nation.  This is an empty
    // parameter, initiate-only action whose native config supplies cost.
    influence=16
};

enum class SourceKind : std::uint8_t {
    outgoing=0,
    incoming=1
};

enum class State : std::uint8_t {
    empty=0,
    seeded=1,
    serialized=2,
    claimed=3,
    postcloned=4,
    consumed=5,
    invalidated=6
};

enum class ErrorCode : std::uint8_t {
    ok=0,
    invalid_argument,
    invalid_phase,
    invalid_payload,
    request_id_invalid,
    wrong_epoch,
    deadline_expired,
    capacity_full,
    duplicate_request,
    duplicate_header,
    ambiguous_header,
    identity_in_use,
    identity_mismatch,
    generation_mismatch,
    payload_mismatch,
    phase_mismatch,
    header_mismatch,
    invalid_stage,
    untrusted_pipeline,
    duplicate_claim,
    claim_mismatch,
    already_consumed,
    already_invalidated,
    target_not_bound,
    source_destroyed,
    target_destroyed,
    outgoing_detached,
    incoming_detached,
    request_revoked
};

struct Context {
    std::uint64_t session_epoch=0;
    // Monotonic milliseconds (the production caller supplies
    // GetTickCount64-derived values).
    std::uint64_t current_tick=0;
};

// Values are kept as raw canonical words.  The ledger never dereferences or
// interprets them; equality is intentionally exact, including date2c.
struct AlliancePayload {
    std::uint64_t actor10=0;
    std::uint64_t mirror18=0;
    std::uint64_t recipient20=0;
    std::uint64_t date28=0;
    std::uint64_t date2c=0;
    std::uint64_t envoy30=0;
    std::uint64_t state34=0;
    std::uint64_t variant38=0;
    std::uint64_t proposal3c=0;
    // Appended fields preserve the nine-word aggregate initializer used by
    // the alliance path while binding the action family and insult variant
    // explicitly.
    ActionFamily family=ActionFamily::alliance;
    std::uint64_t extra60=0;
    // Native offset +0x40 is a signed int32.  It is meaningful for the
    // insult family, for trade_favors_for_trust (favor cost), and for gift
    // (raw ducat amount).  The trust increment is carried separately at +0x44.
    std::int32_t parameter40=0;
    std::int32_t favor_cost40=0;
    std::int32_t favor_amount44=0;
    // Declare War additionally owns a selected goal and three logical
    // vectors. Every proof stage compares their complete values.
    bridge::declarewar_payload::WarPayloadExtension war{};
    // Peace keeps its large offer on the observer heap. The ledger stores
    // only an immutable reference so fixed entries never contain 100 KB of
    // term data.
    bridge::peace_payload::PeaceActionPayload peace{};

    bool operator==(const AlliancePayload& other) const noexcept {
        return actor10==other.actor10 && mirror18==other.mirror18
            && recipient20==other.recipient20 && date28==other.date28
            && date2c==other.date2c && envoy30==other.envoy30
            && state34==other.state34 && variant38==other.variant38
            && proposal3c==other.proposal3c && family==other.family
            && extra60==other.extra60 && parameter40==other.parameter40
            && favor_cost40==other.favor_cost40
            && favor_amount44==other.favor_amount44
            && war==other.war && peace==other.peace;
    }
    bool operator!=(const AlliancePayload& other) const noexcept {
        return !(*this==other);
    }
};

// The Peace handler can rebuild the envoy field from its current diplomatic
// entry after the action has been consumed.  That rebuild is a narrowly
// scoped native observation: an original uint32(-1) sentinel may become the
// current envoy id (0..255).  Keep the general ledger equality exact and
// expose this normalization only to the proven 0x4ea900 handler path, where
// the caller has already established the consumed TLS target and the native
// envoy proof.
inline bool peace_handler_payload_matches(const AlliancePayload& expected,
    const AlliancePayload& current,bool native_envoy_verified) noexcept {
    if (expected.family!=ActionFamily::peace
        || current.family!=ActionFamily::peace
        || expected.state34!=0 || current.state34!=0)
        return false;

    // The native field is a uint32.  Reject values that cannot be produced by
    // that field instead of allowing an out-of-range test value to pass by
    // exact equality.
    constexpr std::uint64_t kMaxNativeEnvoy=
        static_cast<std::uint64_t>(std::numeric_limits<std::uint32_t>::max());
    if (expected.envoy30>kMaxNativeEnvoy || current.envoy30>kMaxNativeEnvoy)
        return false;

    if (expected.envoy30==kMaxNativeEnvoy && current.envoy30<256u
        && native_envoy_verified) {
        AlliancePayload normalized=current;
        normalized.envoy30=expected.envoy30;
        return expected==normalized;
    }
    return expected==current;
}

struct ObjectRef {
    std::uintptr_t address=0;
    std::uint64_t generation=0;

    constexpr bool valid() const noexcept {
        return address!=0 && generation!=0;
    }
    constexpr bool operator==(const ObjectRef& other) const noexcept {
        return address==other.address && generation==other.generation;
    }
    constexpr bool operator!=(const ObjectRef& other) const noexcept {
        return !(*this==other);
    }
};

// origin/flags/seq are kept at their native widths.  The all-FF/zero form is
// a transfer-only clone marker; it is never a wildcard for lookup.
struct NativeHeader {
    std::uint16_t origin=0;
    std::uint8_t flags=0;
    std::uint32_t seq=0;

    constexpr bool operator==(const NativeHeader& other) const noexcept {
        return origin==other.origin && flags==other.flags && seq==other.seq;
    }
    constexpr bool operator!=(const NativeHeader& other) const noexcept {
        return !(*this==other);
    }
};

constexpr NativeHeader kTransferCloneHeader{0xffffu,0u,0u};

struct SeedReceipt {
    std::uint64_t session_epoch=0;
    std::uint16_t slot=kInvalidSlot;
    std::uint64_t seed_serial=0;
};

struct ClaimTicket {
    std::uint64_t session_epoch=0;
    std::uint16_t slot=kInvalidSlot;
    std::uint64_t seed_serial=0;
    std::uint64_t claim_serial=0;
};

struct OperationResult {
    ErrorCode code=ErrorCode::invalid_argument;
    std::uint16_t slot=kInvalidSlot;
    std::uint64_t serial=0;

    constexpr bool ok() const noexcept { return code==ErrorCode::ok; }
};

struct SeedResult {
    OperationResult result{};
    SeedReceipt receipt{};
};

struct ClaimResult {
    OperationResult result{};
    ClaimTicket ticket{};
};

struct CloneProof {
    // source_* are the independently decoded incoming wrapper/action.  They
    // are deliberately separate from the outgoing expected identities.
    ObjectRef source_wrapper{};
    ObjectRef source_action{};
    ObjectRef target_wrapper{};
    ObjectRef target_action{};
    AlliancePayload payload{};
    NativeHeader observed_clone_header{};
    NativeHeader final_entry_header{};
};

struct RecordView {
    char request_id[kMaxRequestId+1]{};
    State state=State::empty;
    Phase phase=Phase::initiate;
    AlliancePayload payload{};
    ObjectRef expected_wrapper{};
    ObjectRef expected_action{};
    ObjectRef incoming_wrapper{};
    ObjectRef incoming_action{};
    ObjectRef target_wrapper{};
    ObjectRef target_action{};
    NativeHeader source_header{};
    NativeHeader final_entry_header{};
    std::uint64_t deadline_tick=0;
    std::uint64_t seed_serial=0;
    std::uint64_t claim_serial=0;
    bool outgoing_alive=false;
    bool incoming_alive=false;
    bool target_alive=false;
};

inline const char* error_name(ErrorCode code) noexcept {
    switch (code) {
    case ErrorCode::ok: return "ok";
    case ErrorCode::invalid_argument: return "invalid_argument";
    case ErrorCode::invalid_phase: return "invalid_phase";
    case ErrorCode::invalid_payload: return "invalid_payload";
    case ErrorCode::request_id_invalid: return "request_id_invalid";
    case ErrorCode::wrong_epoch: return "wrong_epoch";
    case ErrorCode::deadline_expired: return "deadline_expired";
    case ErrorCode::capacity_full: return "capacity_full";
    case ErrorCode::duplicate_request: return "duplicate_request";
    case ErrorCode::duplicate_header: return "duplicate_header";
    case ErrorCode::ambiguous_header: return "ambiguous_header";
    case ErrorCode::identity_in_use: return "identity_in_use";
    case ErrorCode::identity_mismatch: return "identity_mismatch";
    case ErrorCode::generation_mismatch: return "generation_mismatch";
    case ErrorCode::payload_mismatch: return "payload_mismatch";
    case ErrorCode::phase_mismatch: return "phase_mismatch";
    case ErrorCode::header_mismatch: return "header_mismatch";
    case ErrorCode::invalid_stage: return "invalid_stage";
    case ErrorCode::untrusted_pipeline: return "untrusted_pipeline";
    case ErrorCode::duplicate_claim: return "duplicate_claim";
    case ErrorCode::claim_mismatch: return "claim_mismatch";
    case ErrorCode::already_consumed: return "already_consumed";
    case ErrorCode::already_invalidated: return "already_invalidated";
    case ErrorCode::target_not_bound: return "target_not_bound";
    case ErrorCode::source_destroyed: return "source_destroyed";
    case ErrorCode::target_destroyed: return "target_destroyed";
    case ErrorCode::outgoing_detached: return "outgoing_detached";
    case ErrorCode::incoming_detached: return "incoming_detached";
    case ErrorCode::request_revoked: return "request_revoked";
    }
    return "unknown";
}

class AllianceAuthorityLedger {
public:
    explicit AllianceAuthorityLedger(std::uint64_t session_epoch) noexcept
        : session_epoch_(session_epoch) {}

    AllianceAuthorityLedger(const AllianceAuthorityLedger&)=delete;
    AllianceAuthorityLedger& operator=(const AllianceAuthorityLedger&)=delete;

    std::uint64_t session_epoch() const noexcept { return session_epoch_; }

    // A ledger is created once in the DLL image and re-bound only during
    // BridgeStart, before any native hook can publish a receipt.  Resetting
    // also clears every old identity and serial so a process/session change
    // cannot reuse a prior grant.
    void reset_session_epoch(std::uint64_t session_epoch) noexcept {
        session_epoch_=session_epoch;
        entries_={};
        next_seed_serial_=0;
        next_claim_serial_=0;
    }

    SeedResult seed(const Context& context,const char* request_id,
        const AlliancePayload& payload,Phase phase,ObjectRef expected_wrapper,
        ObjectRef expected_action,std::uint64_t deadline_tick) noexcept {
        SeedResult output{};
        OperationResult context_result=check_context(context);
        if (!context_result.ok()) {
            output.result=context_result;
            return output;
        }
        if (!valid_request_id(request_id)) {
            output.result=make_result(ErrorCode::request_id_invalid);
            return output;
        }
        if (!valid_phase(phase)) {
            output.result=make_result(ErrorCode::invalid_phase);
            return output;
        }
        if (!valid_payload(payload,phase)) {
            output.result=make_result(ErrorCode::invalid_payload);
            return output;
        }
        if (!expected_wrapper.valid() || !expected_action.valid()) {
            output.result=make_result(ErrorCode::invalid_argument);
            return output;
        }
        if (!valid_deadline(context.current_tick,deadline_tick)) {
            output.result=make_result(ErrorCode::invalid_argument);
            return output;
        }
        if (find_request(request_id)!=kInvalidSlot) {
            output.result=make_result(ErrorCode::duplicate_request);
            return output;
        }
        if (generation_conflict(expected_wrapper,expected_action)) {
            output.result=make_result(ErrorCode::generation_mismatch);
            return output;
        }
        if (identity_in_use(expected_wrapper,expected_action)) {
            output.result=make_result(ErrorCode::identity_in_use);
            return output;
        }

        const std::uint16_t slot=find_empty_slot();
        if (slot==kInvalidSlot) {
            output.result=make_result(ErrorCode::capacity_full);
            return output;
        }
        Entry& entry=entries_[slot];
        entry=Entry{};
        copy_request_id(entry.request_id,request_id);
        entry.state=State::seeded;
        entry.phase=phase;
        entry.payload=payload;
        entry.expected_wrapper=expected_wrapper;
        entry.expected_action=expected_action;
        entry.deadline_tick=deadline_tick;
        entry.outgoing_alive=true;
        entry.seed_serial=next_serial(next_seed_serial_);
        output.receipt=SeedReceipt{session_epoch_,slot,entry.seed_serial};
        output.result=make_result(ErrorCode::ok,slot,entry.seed_serial);
        return output;
    }

    OperationResult serializer(const Context& context,
        const SeedReceipt& receipt,Phase phase,ObjectRef wrapper,
        ObjectRef action,const AlliancePayload& payload,
        NativeHeader header) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_seed(context,receipt,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state!=State::seeded) {
            if (entry->state==State::serialized
                && entry->source_header==header)
                return make_result(ErrorCode::duplicate_header,result.slot,
                    entry->seed_serial);
            return stage_result(*entry);
        }
        if (!phase_matches(*entry,phase))
            return make_result(ErrorCode::phase_mismatch,result.slot,
                entry->seed_serial);
        if (wrapper!=entry->expected_wrapper
            || action!=entry->expected_action)
            return identity_result(*entry,wrapper,action);
        if (payload!=entry->payload)
            return make_result(ErrorCode::payload_mismatch,result.slot,
                entry->seed_serial);
        if (header==kTransferCloneHeader)
            return make_result(ErrorCode::invalid_argument,result.slot,
                entry->seed_serial);
        const std::uint16_t same=find_header(header);
        if (same!=kInvalidSlot) {
            if (same==result.slot)
                return make_result(ErrorCode::duplicate_header,result.slot,
                    entry->seed_serial);
            return make_result(ErrorCode::ambiguous_header,result.slot,
                entry->seed_serial);
        }
        entry->source_header=header;
        entry->source_header_bound=true;
        entry->state=State::serialized;
        return make_result(ErrorCode::ok,result.slot,entry->seed_serial);
    }

    ClaimResult incoming_preclone(const Context& context,
        const SeedReceipt& receipt,Phase phase,ObjectRef incoming_wrapper,
        ObjectRef incoming_action,NativeHeader header,
        const AlliancePayload& payload,bool trusted_pipeline_proof) noexcept {
        ClaimResult output{};
        Entry* entry=nullptr;
        OperationResult result=acquire_seed(context,receipt,entry);
        if (!result.ok()) {
            output.result=result;
            return output;
        }
        result=check_live(context,*entry);
        if (!result.ok()) {
            output.result=result;
            return output;
        }
        if (entry->state==State::claimed || entry->state==State::postcloned)
            result=make_result(ErrorCode::duplicate_claim,result.slot,
                entry->claim_serial);
        else if (entry->state!=State::serialized)
            result=stage_result(*entry);
        else if (!phase_matches(*entry,phase))
            result=make_result(ErrorCode::phase_mismatch,result.slot,
                entry->seed_serial);
        else if (!trusted_pipeline_proof)
            result=make_result(ErrorCode::untrusted_pipeline,result.slot,
                entry->seed_serial);
        else if (!incoming_wrapper.valid() || !incoming_action.valid())
            result=make_result(ErrorCode::invalid_argument,result.slot,
                entry->seed_serial);
        else if (entry->outgoing_alive && ((incoming_wrapper.address==entry->expected_wrapper.address
                && incoming_wrapper.generation
                    !=entry->expected_wrapper.generation)
            || (incoming_action.address==entry->expected_action.address
                && incoming_action.generation
                    !=entry->expected_action.generation)))
            result=make_result(ErrorCode::generation_mismatch,result.slot,
                entry->seed_serial);
        else if (incoming_wrapper==entry->expected_wrapper
            || incoming_action==entry->expected_action)
            result=make_result(ErrorCode::identity_mismatch,result.slot,
                entry->seed_serial);
        else if (generation_conflict(incoming_wrapper,incoming_action,
                result.slot))
            result=make_result(ErrorCode::generation_mismatch,result.slot,
                entry->seed_serial);
        else if (identity_in_use(incoming_wrapper,incoming_action,
                result.slot))
            result=make_result(ErrorCode::identity_in_use,result.slot,
                entry->seed_serial);
        else if (header!=entry->source_header)
            result=make_result(ErrorCode::header_mismatch,result.slot,
                entry->seed_serial);
        else if (payload!=entry->payload)
            result=make_result(ErrorCode::payload_mismatch,result.slot,
                entry->seed_serial);
        else {
            entry->incoming_wrapper=incoming_wrapper;
            entry->incoming_action=incoming_action;
            entry->incoming_alive=true;
            entry->claim_serial=next_serial(next_claim_serial_);
            entry->state=State::claimed;
            output.ticket=ClaimTicket{session_epoch_,result.slot,
                entry->seed_serial,entry->claim_serial};
            result=make_result(ErrorCode::ok,result.slot,entry->claim_serial);
        }
        output.result=result;
        return output;
    }

    OperationResult postclone(const Context& context,
        const ClaimTicket& ticket,Phase phase,const CloneProof& proof) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_claim(context,ticket,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state!=State::claimed) return stage_result(*entry);
        if (!phase_matches(*entry,phase))
            return make_result(ErrorCode::phase_mismatch,result.slot,
                entry->claim_serial);
        if ((proof.source_wrapper.address==entry->incoming_wrapper.address
                && proof.source_wrapper.generation
                    !=entry->incoming_wrapper.generation)
            || (proof.source_action.address==entry->incoming_action.address
                && proof.source_action.generation
                    !=entry->incoming_action.generation))
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (proof.source_wrapper!=entry->incoming_wrapper
            || proof.source_action!=entry->incoming_action)
            return make_result(ErrorCode::identity_mismatch,result.slot,
                entry->claim_serial);
        if (!proof.target_wrapper.valid() || !proof.target_action.valid()
            || proof.target_wrapper==entry->expected_wrapper
            || proof.target_action==entry->expected_action
            || proof.target_wrapper==entry->incoming_wrapper
            || proof.target_action==entry->incoming_action)
            return make_result(ErrorCode::invalid_argument,result.slot,
                entry->claim_serial);
        if ((entry->outgoing_alive && ((proof.target_wrapper.address==entry->expected_wrapper.address
                && proof.target_wrapper.generation
                    !=entry->expected_wrapper.generation)
            || (proof.target_action.address==entry->expected_action.address
                && proof.target_action.generation
                    !=entry->expected_action.generation)))
            || (proof.target_wrapper.address==entry->incoming_wrapper.address
                && proof.target_wrapper.generation
                    !=entry->incoming_wrapper.generation)
            || (proof.target_action.address==entry->incoming_action.address
                && proof.target_action.generation
                    !=entry->incoming_action.generation))
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (proof.payload!=entry->payload)
            return make_result(ErrorCode::payload_mismatch,result.slot,
                entry->claim_serial);
        if (proof.observed_clone_header!=kTransferCloneHeader)
            return make_result(ErrorCode::header_mismatch,result.slot,
                entry->claim_serial);
        const NativeHeader expected_final{0xffffu,0u,entry->source_header.seq};
        if (proof.final_entry_header!=expected_final)
            return make_result(ErrorCode::header_mismatch,result.slot,
                entry->claim_serial);
        if (generation_conflict(proof.target_wrapper,proof.target_action,
                result.slot))
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (identity_in_use(proof.target_wrapper,proof.target_action,
                result.slot))
            return make_result(ErrorCode::identity_in_use,result.slot,
                entry->claim_serial);
        entry->target_wrapper=proof.target_wrapper;
        entry->target_action=proof.target_action;
        entry->final_entry_header=proof.final_entry_header;
        entry->target_alive=true;
        entry->state=State::postcloned;
        return make_result(ErrorCode::ok,result.slot,entry->claim_serial);
    }

    OperationResult consume_entry(const Context& context,
        const ClaimTicket& ticket,Phase phase,ObjectRef target_wrapper,
        ObjectRef target_action,const AlliancePayload& payload,
        NativeHeader entry_header) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_claim(context,ticket,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state==State::consumed)
            return make_result(ErrorCode::already_consumed,result.slot,
                entry->claim_serial);
        if (entry->state==State::invalidated)
            return make_result(ErrorCode::already_invalidated,result.slot,
                entry->claim_serial);
        if (entry->state!=State::postcloned) return stage_result(*entry);
        if (!phase_matches(*entry,phase))
            return make_result(ErrorCode::phase_mismatch,result.slot,
                entry->claim_serial);
        if ((target_wrapper.address==entry->target_wrapper.address
                && target_wrapper.generation
                    !=entry->target_wrapper.generation)
            || (target_action.address==entry->target_action.address
                && target_action.generation
                    !=entry->target_action.generation))
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (target_wrapper!=entry->target_wrapper
            || target_action!=entry->target_action)
            return identity_result(*entry,target_wrapper,target_action);
        if (payload!=entry->payload)
            return make_result(ErrorCode::payload_mismatch,result.slot,
                entry->claim_serial);
        if (entry_header!=entry->final_entry_header)
            return make_result(ErrorCode::header_mismatch,result.slot,
                entry->claim_serial);
        entry->state=State::consumed;
        entry->outgoing_alive=false;
        entry->incoming_alive=false;
        entry->target_alive=false;
        return make_result(ErrorCode::ok,result.slot,entry->claim_serial);
    }

    // The caller must identify which native source was destroyed.  An
    // outgoing destructor before serialization revokes the request; after
    // serialization it only detaches the outgoing object.  An incoming
    // destructor before postclone revokes, while after postclone it detaches
    // the incoming object and leaves the already-proven target grant alive.
    OperationResult source_destroyed(const Context& context,
        const SeedReceipt& receipt,Phase phase,SourceKind kind,
        ObjectRef wrapper,ObjectRef action) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_seed(context,receipt,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state==State::consumed)
            return make_result(ErrorCode::already_consumed,result.slot,
                entry->seed_serial);
        if (entry->state==State::invalidated)
            return make_result(ErrorCode::already_invalidated,result.slot,
                entry->seed_serial);
        if (!phase_matches(*entry,phase))
            return make_result(ErrorCode::phase_mismatch,result.slot,
                entry->seed_serial);
        if (kind==SourceKind::outgoing) {
            if (wrapper.address==entry->expected_wrapper.address
                && wrapper.generation!=entry->expected_wrapper.generation)
                return make_result(ErrorCode::generation_mismatch,result.slot,
                    entry->seed_serial);
            if (action.address==entry->expected_action.address
                && action.generation!=entry->expected_action.generation)
                return make_result(ErrorCode::generation_mismatch,result.slot,
                    entry->seed_serial);
            if (wrapper!=entry->expected_wrapper
                || action!=entry->expected_action)
                return identity_result(*entry,wrapper,action);
            if (!entry->outgoing_alive)
                return make_result(ErrorCode::outgoing_detached,result.slot,
                    entry->seed_serial);
            entry->outgoing_alive=false;
            if (entry->state==State::seeded) {
                entry->state=State::invalidated;
                return make_result(ErrorCode::source_destroyed,result.slot,
                    entry->seed_serial);
            }
            return make_result(ErrorCode::outgoing_detached,result.slot,
                entry->seed_serial);
        }

        if (kind!=SourceKind::incoming)
            return make_result(ErrorCode::invalid_argument,result.slot,
                entry->seed_serial);
        if (entry->state==State::seeded || entry->state==State::serialized)
            return make_result(ErrorCode::target_not_bound,result.slot,
                entry->seed_serial);
        if (wrapper.address==entry->incoming_wrapper.address
            && wrapper.generation!=entry->incoming_wrapper.generation)
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->seed_serial);
        if (action.address==entry->incoming_action.address
            && action.generation!=entry->incoming_action.generation)
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->seed_serial);
        if (wrapper!=entry->incoming_wrapper
            || action!=entry->incoming_action)
            return make_result(ErrorCode::identity_mismatch,result.slot,
                entry->claim_serial);
        if (!entry->incoming_alive)
            return make_result(ErrorCode::incoming_detached,result.slot,
                entry->claim_serial);
        entry->incoming_alive=false;
        if (entry->state==State::claimed) {
            entry->state=State::invalidated;
            return make_result(ErrorCode::source_destroyed,result.slot,
                entry->claim_serial);
        }
        return make_result(ErrorCode::incoming_detached,result.slot,
            entry->claim_serial);
    }

    OperationResult revoke_request(const Context& context,
        const SeedReceipt& receipt,Phase phase) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_seed(context,receipt,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state==State::consumed)
            return make_result(ErrorCode::already_consumed,result.slot,
                entry->claim_serial);
        if (entry->state==State::invalidated)
            return make_result(ErrorCode::already_invalidated,result.slot,
                entry->claim_serial);
        if (!phase_matches(*entry,phase))
            return make_result(ErrorCode::phase_mismatch,result.slot,
                entry->claim_serial?entry->claim_serial:entry->seed_serial);
        entry->state=State::invalidated;
        entry->outgoing_alive=false;
        entry->incoming_alive=false;
        entry->target_alive=false;
        return make_result(ErrorCode::request_revoked,result.slot,
            entry->claim_serial?entry->claim_serial:entry->seed_serial);
    }

    OperationResult target_destroyed(const Context& context,
        const ClaimTicket& ticket,Phase phase,ObjectRef wrapper,
        ObjectRef action) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_claim(context,ticket,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state==State::consumed)
            return make_result(ErrorCode::already_consumed,result.slot,
                entry->claim_serial);
        if (entry->state==State::invalidated)
            return make_result(ErrorCode::already_invalidated,result.slot,
                entry->claim_serial);
        if (entry->state!=State::postcloned)
            return make_result(ErrorCode::target_not_bound,result.slot,
                entry->claim_serial);
        if (wrapper.address==entry->target_wrapper.address
            && wrapper.generation!=entry->target_wrapper.generation)
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (action.address==entry->target_action.address
            && action.generation!=entry->target_action.generation)
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (wrapper!=entry->target_wrapper || action!=entry->target_action)
            return identity_result(*entry,wrapper,action);
        if (!phase_matches(*entry,phase))
            return make_result(ErrorCode::phase_mismatch,result.slot,
                entry->claim_serial);
        entry->state=State::invalidated;
        entry->outgoing_alive=false;
        entry->incoming_alive=false;
        entry->target_alive=false;
        return make_result(ErrorCode::target_destroyed,result.slot,
            entry->claim_serial);
    }

    // Marks every live record past its deadline invalidated.  It is safe to
    // call before a native frame is inspected; no record is evicted.
    OperationResult invalidate_expired(const Context& context) noexcept {
        OperationResult result=check_context(context);
        if (!result.ok()) return result;
        for (Entry& entry: entries_) {
            if (entry.state!=State::empty && entry.state!=State::consumed
                && entry.state!=State::invalidated
                && context.current_tick>entry.deadline_tick) {
                entry.state=State::invalidated;
                entry.outgoing_alive=false;
                entry.incoming_alive=false;
                entry.target_alive=false;
            }
        }
        return make_result(ErrorCode::ok);
    }

    struct InspectResult {
        OperationResult result{};
        RecordView view{};
    };

    InspectResult inspect(const Context& context,
        const SeedReceipt& receipt) noexcept {
        InspectResult output{};
        Entry* entry=nullptr;
        OperationResult result=acquire_seed(context,receipt,entry);
        if (!result.ok()) {
            output.result=result;
            return output;
        }
        result=check_live(context,*entry);
        if (!result.ok()) {
            output.result=result;
            return output;
        }
        fill_view(*entry,output.view);
        output.result=make_result(ErrorCode::ok,result.slot,entry->seed_serial);
        return output;
    }

private:
    struct Entry {
        char request_id[kMaxRequestId+1]{};
        State state=State::empty;
        Phase phase=Phase::initiate;
        AlliancePayload payload{};
        ObjectRef expected_wrapper{};
        ObjectRef expected_action{};
        ObjectRef incoming_wrapper{};
        ObjectRef incoming_action{};
        ObjectRef target_wrapper{};
        ObjectRef target_action{};
        NativeHeader source_header{};
        NativeHeader final_entry_header{};
        bool source_header_bound=false;
        // Monotonic millisecond deadline, validated against current_tick and
        // kMaxDeadlineTtlMs at seed time.
        std::uint64_t deadline_tick=0;
        std::uint64_t seed_serial=0;
        std::uint64_t claim_serial=0;
        bool outgoing_alive=false;
        bool incoming_alive=false;
        bool target_alive=false;
    };

    std::array<Entry,kLedgerCapacity> entries_{};
    std::uint64_t session_epoch_=0;
    std::uint64_t next_seed_serial_=0;
    std::uint64_t next_claim_serial_=0;

    static constexpr bool valid_phase(Phase phase) noexcept {
        return phase==Phase::initiate || phase==Phase::accept
            || phase==Phase::reject || phase==Phase::dissolve;
    }

    static bool valid_payload(const AlliancePayload& payload,
        Phase phase) noexcept {
        if (payload.family!=ActionFamily::declare_war
            && payload.war!=bridge::declarewar_payload::WarPayloadExtension{}) return false;
        if (payload.family!=ActionFamily::peace && !payload.peace.empty()) return false;
        switch (payload.family) {
        case ActionFamily::alliance:
        case ActionFamily::royal_marriage:
        case ActionFamily::improve_relations:
        case ActionFamily::spy_network:
        case ActionFamily::guarantee:
        case ActionFamily::support_independence:
        case ActionFamily::military_access:
        case ActionFamily::vassalization:
            // The current native UI constructor initializes +0x60 to zero;
            // a nonzero value is not yet a supported authority variant.
            if (payload.extra60!=0 || payload.parameter40!=0) return false;
            break;
        case ActionFamily::insult:
            // Insults are initiate-only.  Native +0x40 is signed: -1 is the
            // ordinary form, while every nonnegative int32 selects a
            // scornful form.  Values below -1 are malformed.
            if (payload.extra60!=0 || payload.parameter40 < -1
                || phase!=Phase::initiate || payload.state34!=0
                || payload.variant38!=1) return false;
            break;
        case ActionFamily::declare_war:
            if (payload.extra60!=0 || payload.parameter40!=0
                || phase!=Phase::initiate || payload.state34!=0
                || payload.variant38!=1 || !payload.war.valid()
                || (payload.war.owned_present && payload.war.owned.owned_field08!=0x165))
                return false;
            break;
        case ActionFamily::peace: {
            // States 0/1/2 retain the same complete embedded offer. NPC
            // responses still require an independently observed transport
            // record tied to the initiating binding before a seed is made.
            if (phase==Phase::dissolve || payload.variant38!=1
                || payload.extra60!=0 || payload.parameter40!=0
                || !payload.peace.valid() || payload.peace.flag40!=1)
                return false;
            // Native initiation has no response token.  Accept/reject keep
            // the raw native proposal token, bounded to the uint32 field used
            // by the response path; zero remains a valid legacy token.
            if (phase==Phase::initiate && payload.proposal3c!=0) return false;
            if ((phase==Phase::accept || phase==Phase::reject)
                && payload.proposal3c>std::numeric_limits<std::uint32_t>::max())
                return false;
            const auto* offer=payload.peace.offer.get();
            const bool demand=payload.peace.direction41!=0;
            const auto claimant=demand?payload.actor10:payload.recipient20;
            const auto payer=demand?payload.recipient20:payload.actor10;
            if (!offer || offer->claimant!=claimant || offer->payer!=payer)
                return false;
            break;
        }
        case ActionFamily::favor_gold:
            // Favors-for-gold is a response-capable negotiated action.  Its
            // native phase field is 0=request, 2=accepted, 1=rejected; there
            // is no dissolve/cancel transition for this one-shot action.
            if (payload.extra60!=0 || payload.parameter40!=0
                || phase==Phase::dissolve || payload.variant38!=1)
                return false;
            break;
        case ActionFamily::favor_trust:
            // Trust carries the native factory payload at +0x40/+0x44.  The
            // bridge binds those words exactly so a response cannot change
            // either cost or increment in transit.
            if (payload.extra60!=0 || payload.parameter40!=0
                || payload.favor_cost40<0 || payload.favor_amount44<0
                || phase==Phase::dissolve || payload.variant38!=1)
                return false;
            break;
        case ActionFamily::favor_men:
            // Men amount is computed by the native helper; there is no
            // action-local amount slot to accept from the wire.
            if (payload.extra60!=0 || payload.parameter40!=0
                || payload.favor_cost40!=0 || payload.favor_amount44!=0
                || phase==Phase::dissolve || payload.variant38!=1)
                return false;
            break;
        case ActionFamily::gift:
            // Gift is an immediate actor->recipient effect.  The public
            // ducat value is checked again at the execution wire; the native
            // action carries only the signed raw amount at +0x40 here.
            if (payload.extra60!=0 || payload.favor_cost40!=0
                || payload.favor_amount44!=0 || phase!=Phase::initiate
                || payload.state34!=0 || payload.variant38!=1
                || payload.parameter40<25000
                || payload.parameter40>2147475000
                || payload.parameter40%25000!=0)
                return false;
            break;
        case ActionFamily::influence:
            // Influence is immediate and has no bridge-supplied amount or
            // proposal state; cost/configuration stay native-owned.
            if (payload.extra60!=0 || payload.parameter40!=0
                || payload.favor_cost40!=0 || payload.favor_amount44!=0
                || phase!=Phase::initiate || payload.state34!=0
                || payload.variant38!=1)
                return false;
            break;
        case ActionFamily::curry_favors:
            // Curry is a continuous one-sided task.  Its native effect uses
            // state34==0 for both start and stop; the stop transition is
            // represented by the dissolve phase and variant38==0.
            if (payload.extra60!=0 || payload.parameter40!=0
                || payload.state34!=0) return false;
            break;
        default:
            return false;
        }
        if (payload.actor10==0 || payload.recipient20==0
            || payload.mirror18!=payload.actor10
            || payload.actor10==payload.recipient20) return false;
        // Spy-network and Guarantee actions are one-sided tasks.  They share
        // the initiate and dissolve wire shapes, but never use
        // alliance/response states.  Support-independence is a response-capable
        // family: initiate/accept/reject use variant 1 with states 0/2/1,
        // while its internal revoke transition uses dissolve (variant/state 0).
        if (payload.family==ActionFamily::spy_network
            || payload.family==ActionFamily::guarantee
            || payload.family==ActionFamily::curry_favors) {
            if (phase==Phase::dissolve)
                return payload.variant38==0 && payload.state34==0;
            return phase==Phase::initiate
                && payload.variant38==1 && payload.state34==0;
        }
        if (payload.family==ActionFamily::gift
            || payload.family==ActionFamily::influence)
            return phase==Phase::initiate
                && payload.variant38==1 && payload.state34==0;
        if (phase==Phase::dissolve)
            return payload.variant38==0 && payload.state34==0;
        if (payload.variant38!=1) return false;
        if (phase==Phase::initiate) return payload.state34==0;
        if (phase==Phase::accept) return payload.state34==2;
        if (phase==Phase::reject) return payload.state34==1;
        return false;
    }

    static bool valid_deadline(std::uint64_t current_tick,
        std::uint64_t deadline_tick) noexcept {
        if (deadline_tick<=current_tick) return false;
        return deadline_tick-current_tick<=kMaxDeadlineTtlMs;
    }

    static bool valid_request_id(const char* request_id) noexcept {
        if (!request_id) return false;
        for (std::size_t i=0;i<=kMaxRequestId;++i) {
            const unsigned char value=static_cast<unsigned char>(request_id[i]);
            if (value==0) return i!=0;
            if (i==kMaxRequestId || value<0x20u || value>0x7eu)
                return false;
        }
        return false;
    }

    static void copy_request_id(char (&destination)[kMaxRequestId+1],
        const char* source) noexcept {
        std::size_t i=0;
        for (;i<kMaxRequestId && source[i]!=0;++i)
            destination[i]=source[i];
        destination[i]=0;
    }

    static bool request_equal(const char* left,const char* right) noexcept {
        return std::strncmp(left,right,kMaxRequestId+1)==0;
    }

    static std::uint64_t next_serial(std::uint64_t& serial) noexcept {
        ++serial;
        if (serial==0) ++serial;
        return serial;
    }

    static OperationResult make_result(ErrorCode code,
        std::uint16_t slot=kInvalidSlot,std::uint64_t serial=0) noexcept {
        return OperationResult{code,slot,serial};
    }

    OperationResult check_context(const Context& context) const noexcept {
        if (context.session_epoch!=session_epoch_)
            return make_result(ErrorCode::wrong_epoch);
        return make_result(ErrorCode::ok);
    }

    OperationResult stage_result(const Entry& entry) const noexcept {
        const std::uint16_t slot=slot_of(entry);
        if (entry.state==State::consumed)
            return make_result(ErrorCode::already_consumed,
                slot,entry.claim_serial);
        if (entry.state==State::invalidated)
            return make_result(ErrorCode::already_invalidated,
                slot,entry.claim_serial);
        return make_result(ErrorCode::invalid_stage,slot,
            entry.claim_serial?entry.claim_serial:entry.seed_serial);
    }

    OperationResult identity_result(const Entry& entry,
        ObjectRef supplied_wrapper,ObjectRef supplied_action) noexcept {
        const std::uint16_t slot=slot_of(entry);
        if ((supplied_wrapper.address==entry.expected_wrapper.address
                && supplied_wrapper.generation
                    !=entry.expected_wrapper.generation)
            || (supplied_action.address==entry.expected_action.address
                && supplied_action.generation
                    !=entry.expected_action.generation))
            return make_result(ErrorCode::generation_mismatch,slot,
                entry.claim_serial?entry.claim_serial:entry.seed_serial);
        return make_result(ErrorCode::identity_mismatch,slot,
            entry.claim_serial?entry.claim_serial:entry.seed_serial);
    }

    std::uint16_t slot_of(const Entry& entry) const noexcept {
        return static_cast<std::uint16_t>(&entry-entries_.data());
    }

    OperationResult check_live(const Context& context,Entry& entry) noexcept {
        if (entry.state!=State::consumed && entry.state!=State::invalidated
            && context.current_tick>entry.deadline_tick) {
            entry.state=State::invalidated;
            entry.outgoing_alive=false;
            entry.incoming_alive=false;
            entry.target_alive=false;
            return make_result(ErrorCode::deadline_expired,
                static_cast<std::uint16_t>(&entry-entries_.data()),
                entry.claim_serial?entry.claim_serial:entry.seed_serial);
        }
        return make_result(ErrorCode::ok,
            static_cast<std::uint16_t>(&entry-entries_.data()),
            entry.claim_serial?entry.claim_serial:entry.seed_serial);
    }

    static bool phase_matches(const Entry& entry,Phase phase) noexcept {
        return entry.phase==phase;
    }

    std::uint16_t find_empty_slot() const noexcept {
        for (std::uint16_t i=0;i<kLedgerCapacity;++i)
            if (entries_[i].state==State::empty) return i;
        return kInvalidSlot;
    }

    std::uint16_t find_request(const char* request_id) const noexcept {
        for (std::uint16_t i=0;i<kLedgerCapacity;++i)
            if (entries_[i].state!=State::empty
                && request_equal(entries_[i].request_id,request_id)) return i;
        return kInvalidSlot;
    }

    std::uint16_t find_header(NativeHeader header) const noexcept {
        for (std::uint16_t i=0;i<kLedgerCapacity;++i)
            if (entries_[i].state!=State::empty
                && entries_[i].state!=State::seeded
                && entries_[i].source_header_bound
                && entries_[i].source_header==header) return i;
        return kInvalidSlot;
    }

    bool identity_in_use(ObjectRef wrapper,ObjectRef action,
        std::uint16_t except=kInvalidSlot) const noexcept {
        for (std::uint16_t i=0;i<kLedgerCapacity;++i) {
            if (i==except || !is_live_state(entries_[i].state)) continue;
            const Entry& entry=entries_[i];
            if (entry.expected_wrapper==wrapper
                || entry.expected_action==action
                || entry.incoming_wrapper==wrapper
                || entry.incoming_action==action
                || entry.target_wrapper==wrapper
                || entry.target_action==action) return true;
        }
        return false;
    }

    bool generation_conflict(ObjectRef wrapper,ObjectRef action,
        std::uint16_t except=kInvalidSlot) const noexcept {
        for (std::uint16_t i=0;i<kLedgerCapacity;++i) {
            if (i==except || !is_live_state(entries_[i].state)) continue;
            const Entry& entry=entries_[i];
            if ((wrapper.address!=0
                    && entry.expected_wrapper.address==wrapper.address
                    && entry.expected_wrapper.generation
                        !=wrapper.generation)
                || (action.address!=0
                    && entry.expected_action.address==action.address
                    && entry.expected_action.generation
                        !=action.generation)
                || (wrapper.address!=0
                    && entry.incoming_wrapper.address==wrapper.address
                    && entry.incoming_wrapper.generation
                        !=wrapper.generation)
                || (action.address!=0
                    && entry.incoming_action.address==action.address
                    && entry.incoming_action.generation
                        !=action.generation)
                || (wrapper.address!=0
                    && entry.target_wrapper.address==wrapper.address
                    && entry.target_wrapper.generation
                        !=wrapper.generation)
                || (action.address!=0
                    && entry.target_action.address==action.address
                    && entry.target_action.generation
                        !=action.generation)) return true;
        }
        return false;
    }

    static bool is_live_state(State state) noexcept {
        return state==State::seeded || state==State::serialized
            || state==State::claimed || state==State::postcloned;
    }

    OperationResult acquire_seed(const Context& context,
        const SeedReceipt& receipt,Entry*& entry) noexcept {
        OperationResult result=check_context(context);
        if (!result.ok()) return result;
        if (receipt.session_epoch!=session_epoch_
            || receipt.slot>=kLedgerCapacity)
            return make_result(ErrorCode::claim_mismatch);
        Entry& candidate=entries_[receipt.slot];
        if (candidate.state==State::empty
            || candidate.seed_serial!=receipt.seed_serial)
            return make_result(ErrorCode::claim_mismatch,receipt.slot,
                receipt.seed_serial);
        entry=&candidate;
        return make_result(ErrorCode::ok,receipt.slot,receipt.seed_serial);
    }

    OperationResult acquire_claim(const Context& context,
        const ClaimTicket& ticket,Entry*& entry) noexcept {
        OperationResult result=check_context(context);
        if (!result.ok()) return result;
        if (ticket.session_epoch!=session_epoch_
            || ticket.slot>=kLedgerCapacity)
            return make_result(ErrorCode::claim_mismatch);
        Entry& candidate=entries_[ticket.slot];
        if (candidate.state==State::empty
            || candidate.seed_serial!=ticket.seed_serial
            || candidate.claim_serial!=ticket.claim_serial)
            return make_result(ErrorCode::claim_mismatch,ticket.slot,
                ticket.claim_serial);
        entry=&candidate;
        return make_result(ErrorCode::ok,ticket.slot,ticket.claim_serial);
    }

    static void fill_view(const Entry& entry,RecordView& view) noexcept {
        std::memcpy(view.request_id,entry.request_id,kMaxRequestId+1);
        view.state=entry.state;
        view.phase=entry.phase;
        view.payload=entry.payload;
        view.expected_wrapper=entry.expected_wrapper;
        view.expected_action=entry.expected_action;
        view.incoming_wrapper=entry.incoming_wrapper;
        view.incoming_action=entry.incoming_action;
        view.target_wrapper=entry.target_wrapper;
        view.target_action=entry.target_action;
        view.source_header=entry.source_header;
        view.final_entry_header=entry.final_entry_header;
        view.deadline_tick=entry.deadline_tick;
        view.seed_serial=entry.seed_serial;
        view.claim_serial=entry.claim_serial;
        view.outgoing_alive=entry.outgoing_alive;
        view.incoming_alive=entry.incoming_alive;
        view.target_alive=entry.target_alive;
    }
};

} // namespace bridge::alliance_authority

