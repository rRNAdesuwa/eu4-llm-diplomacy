#pragma once

// Allocation-free authority ledger for the direct Rival country-command
// family.  Rival is a command object, rather than an Alliance-style wrapper
// containing an action object.  The ledger therefore binds exactly one native
// ObjectRef at each hand-off stage: source, loaded, and target.
//
// This header does not call native code, inspect addresses, or decide whether
// a country-command is legal.  The caller supplies the already checked
// objects, payload, header, and pipeline proof.  The ledger only binds those
// claims to one session, date, generation, and bounded deadline.

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace bridge::rival_command_authority {

constexpr std::size_t kLedgerCapacity=64;
constexpr std::size_t kMaxRequestId=64;
constexpr std::uint16_t kInvalidSlot=0xffffu;
constexpr std::uint64_t kMaxDeadlineTtlMs=60000u;

enum class Family : std::uint8_t {
    rival=0
};

enum class CommandKind : std::uint8_t {
    set_rival=0,
    remove_rival=1
};

// Rival has one direct command object.  old_rival remains a zero-only field
// so a future replace command cannot be silently accepted by Set or Remove.
struct RivalPayload {
    Family family=Family::rival;
    CommandKind command=CommandKind::set_rival;
    std::uint64_t actor=0;
    std::uint64_t target=0;
    std::uint64_t old_rival=0;
    std::int32_t date_raw=0;

    constexpr bool operator==(const RivalPayload& other) const noexcept {
        return family==other.family && command==other.command
            && actor==other.actor && target==other.target
            && old_rival==other.old_rival && date_raw==other.date_raw;
    }
    constexpr bool operator!=(const RivalPayload& other) const noexcept {
        return !(*this==other);
    }
};

enum class Phase : std::uint8_t {
    initiate=0
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

enum class DetachKind : std::uint8_t {
    source=0,
    loaded=1
};

enum class ErrorCode : std::uint8_t {
    ok=0,
    invalid_argument,
    invalid_family,
    invalid_phase,
    invalid_payload,
    request_id_invalid,
    wrong_epoch,
    date_mismatch,
    deadline_expired,
    capacity_full,
    duplicate_request,
    duplicate_header,
    ambiguous_header,
    identity_in_use,
    identity_mismatch,
    generation_mismatch,
    payload_mismatch,
    header_mismatch,
    invalid_stage,
    untrusted_pipeline,
    duplicate_claim,
    claim_mismatch,
    already_consumed,
    already_invalidated,
    target_not_bound,
    source_destroyed,
    loaded_destroyed,
    target_destroyed,
    source_detached,
    loaded_detached,
    request_revoked
};

struct Context {
    std::uint64_t session_epoch=0;
    std::uint64_t current_tick=0;
    std::int32_t current_date=0;
};

// Exact direct-command header.  reserved4b is a real native byte and is
// included in equality, collision detection, and every hand-off check.
// The field names retain the observed offsets used by the integration layer.
struct NativeHeader {
    std::uint8_t raw10=0;
    std::int32_t raw38=0;
    std::int32_t raw3c=0;
    std::uint16_t raw40=0;
    std::int32_t raw44=0;
    std::uint16_t origin48=0;
    std::uint8_t flags4a=0;
    std::uint8_t reserved4b=0;
    std::uint32_t sequence4c=0;

    constexpr bool operator==(const NativeHeader& other) const noexcept {
        return raw10==other.raw10 && raw38==other.raw38
            && raw3c==other.raw3c && raw40==other.raw40
            && raw44==other.raw44 && origin48==other.origin48
            && flags4a==other.flags4a && reserved4b==other.reserved4b
            && sequence4c==other.sequence4c;
    }
    constexpr bool operator!=(const NativeHeader& other) const noexcept {
        return !(*this==other);
    }
};

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

struct InvalidationResult {
    OperationResult result{};
    std::uint16_t invalidated=0;
};

// A direct Rival clone copies the complete native header.  No transfer marker
// or Alliance wrapper/action pair is part of this proof.
struct CloneProof {
    ObjectRef loaded{};
    ObjectRef target{};
    RivalPayload payload{};
    NativeHeader observed_clone_header{};
    NativeHeader target_header{};
};

struct RecordView {
    char request_id[kMaxRequestId+1]{};
    State state=State::empty;
    Family family=Family::rival;
    CommandKind command=CommandKind::set_rival;
    Phase phase=Phase::initiate;
    RivalPayload payload{};
    ObjectRef source{};
    ObjectRef loaded{};
    ObjectRef target{};
    NativeHeader source_header{};
    NativeHeader loaded_header{};
    NativeHeader target_header{};
    std::int32_t date_raw=0;
    std::uint64_t deadline_tick=0;
    std::uint64_t seed_serial=0;
    std::uint64_t claim_serial=0;
    bool source_header_bound=false;
    bool source_alive=false;
    bool loaded_alive=false;
    bool target_alive=false;
};

inline const char* error_name(ErrorCode code) noexcept {
    switch (code) {
    case ErrorCode::ok: return "ok";
    case ErrorCode::invalid_argument: return "invalid_argument";
    case ErrorCode::invalid_family: return "invalid_family";
    case ErrorCode::invalid_phase: return "invalid_phase";
    case ErrorCode::invalid_payload: return "invalid_payload";
    case ErrorCode::request_id_invalid: return "request_id_invalid";
    case ErrorCode::wrong_epoch: return "wrong_epoch";
    case ErrorCode::date_mismatch: return "date_mismatch";
    case ErrorCode::deadline_expired: return "deadline_expired";
    case ErrorCode::capacity_full: return "capacity_full";
    case ErrorCode::duplicate_request: return "duplicate_request";
    case ErrorCode::duplicate_header: return "duplicate_header";
    case ErrorCode::ambiguous_header: return "ambiguous_header";
    case ErrorCode::identity_in_use: return "identity_in_use";
    case ErrorCode::identity_mismatch: return "identity_mismatch";
    case ErrorCode::generation_mismatch: return "generation_mismatch";
    case ErrorCode::payload_mismatch: return "payload_mismatch";
    case ErrorCode::header_mismatch: return "header_mismatch";
    case ErrorCode::invalid_stage: return "invalid_stage";
    case ErrorCode::untrusted_pipeline: return "untrusted_pipeline";
    case ErrorCode::duplicate_claim: return "duplicate_claim";
    case ErrorCode::claim_mismatch: return "claim_mismatch";
    case ErrorCode::already_consumed: return "already_consumed";
    case ErrorCode::already_invalidated: return "already_invalidated";
    case ErrorCode::target_not_bound: return "target_not_bound";
    case ErrorCode::source_destroyed: return "source_destroyed";
    case ErrorCode::loaded_destroyed: return "loaded_destroyed";
    case ErrorCode::target_destroyed: return "target_destroyed";
    case ErrorCode::source_detached: return "source_detached";
    case ErrorCode::loaded_detached: return "loaded_detached";
    case ErrorCode::request_revoked: return "request_revoked";
    }
    return "unknown";
}

class RivalCommandAuthorityLedger {
public:
    explicit RivalCommandAuthorityLedger(std::uint64_t session_epoch) noexcept
        : session_epoch_(session_epoch) {}

    RivalCommandAuthorityLedger(const RivalCommandAuthorityLedger&)=delete;
    RivalCommandAuthorityLedger& operator=(const RivalCommandAuthorityLedger&)=delete;

    std::uint64_t session_epoch() const noexcept { return session_epoch_; }

    void reset_session_epoch(std::uint64_t session_epoch) noexcept {
        session_epoch_=session_epoch;
        entries_={};
        next_seed_serial_=0;
        next_claim_serial_=0;
    }

    // Rival's phase is always initiate; there is no inbound action object.
    SeedResult seed(const Context& context,const char* request_id,
        const RivalPayload& payload,ObjectRef source,
        std::uint64_t deadline_tick) noexcept {
        SeedResult output{};
        OperationResult result=check_context(context);
        if (!result.ok()) {
            output.result=result;
            return output;
        }
        if (!valid_request_id(request_id)) {
            output.result=make_result(ErrorCode::request_id_invalid);
            return output;
        }
        if (!valid_phase(Phase::initiate)) {
            output.result=make_result(ErrorCode::invalid_phase);
            return output;
        }
        if (payload.family!=Family::rival) {
            output.result=make_result(ErrorCode::invalid_family);
            return output;
        }
        if (!valid_payload(payload) || payload.date_raw!=context.current_date) {
            output.result=make_result(ErrorCode::invalid_payload);
            return output;
        }
        if (!source.valid() || !valid_deadline(context.current_tick,deadline_tick)) {
            output.result=make_result(ErrorCode::invalid_argument);
            return output;
        }
        if (find_request(request_id)!=kInvalidSlot) {
            output.result=make_result(ErrorCode::duplicate_request);
            return output;
        }
        if (generation_conflict(source) || identity_in_use(source)) {
            output.result=make_result(generation_conflict(source)
                ? ErrorCode::generation_mismatch : ErrorCode::identity_in_use);
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
        entry.payload=payload;
        entry.source=source;
        entry.deadline_tick=deadline_tick;
        entry.source_alive=true;
        entry.seed_serial=next_serial(next_seed_serial_);
        output.receipt=SeedReceipt{session_epoch_,slot,entry.seed_serial};
        output.result=make_result(ErrorCode::ok,slot,entry.seed_serial);
        return output;
    }

    OperationResult serialize_source(const Context& context,
        const SeedReceipt& receipt,ObjectRef source,const RivalPayload& payload,
        NativeHeader header) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_seed(context,receipt,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state!=State::seeded) {
            if (entry->state==State::serialized && entry->source_header==header)
                return make_result(ErrorCode::duplicate_header,result.slot,
                    entry->seed_serial);
            return stage_result(*entry);
        }
        if (source!=entry->source) return source_identity_result(*entry,source);
        if (payload!=entry->payload)
            return make_result(ErrorCode::payload_mismatch,result.slot,
                entry->seed_serial);
        // Only the unmistakably unassigned origin/sequence pair is rejected.
        // origin=ffff with a real sequence remains a valid native header.
        if (header.origin48==0xffffu && header.sequence4c==0u)
            return make_result(ErrorCode::invalid_argument,result.slot,
                entry->seed_serial);
        const std::uint16_t same=find_header(header);
        if (same!=kInvalidSlot) {
            return make_result(same==result.slot
                ? ErrorCode::duplicate_header : ErrorCode::ambiguous_header,
                result.slot,entry->seed_serial);
        }
        entry->source_header=header;
        entry->source_header_bound=true;
        entry->loaded_header=header;
        entry->state=State::serialized;
        return make_result(ErrorCode::ok,result.slot,entry->seed_serial);
    }

    // Bind one independently loaded direct command object.  The caller
    // supplies the trusted pipeline result; the ledger never dereferences it.
    ClaimResult load_native(const Context& context,const SeedReceipt& receipt,
        ObjectRef loaded,NativeHeader header,const RivalPayload& payload,
        bool trusted_pipeline) noexcept {
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
        if (entry->state==State::claimed || entry->state==State::postcloned) {
            result=make_result(ErrorCode::duplicate_claim,result.slot,
                entry->claim_serial);
        } else if (entry->state!=State::serialized) {
            result=stage_result(*entry);
        } else if (!trusted_pipeline) {
            result=make_result(ErrorCode::untrusted_pipeline,result.slot,
                entry->seed_serial);
        } else if (!loaded.valid()) {
            result=make_result(ErrorCode::invalid_argument,result.slot,
                entry->seed_serial);
        } else if (entry->source_alive && loaded==entry->source) {
            result=make_result(ErrorCode::identity_mismatch,result.slot,
                entry->seed_serial);
        } else if (entry->source_alive
            && loaded.address==entry->source.address
            && loaded.generation!=entry->source.generation) {
            result=make_result(ErrorCode::generation_mismatch,result.slot,
                entry->seed_serial);
        } else if (generation_conflict(loaded,result.slot)) {
            result=make_result(ErrorCode::generation_mismatch,result.slot,
                entry->seed_serial);
        } else if (identity_in_use(loaded,result.slot)) {
            result=make_result(ErrorCode::identity_in_use,result.slot,
                entry->seed_serial);
        } else if (header!=entry->source_header) {
            result=make_result(ErrorCode::header_mismatch,result.slot,
                entry->seed_serial);
        } else if (payload!=entry->payload) {
            result=make_result(ErrorCode::payload_mismatch,result.slot,
                entry->seed_serial);
        } else {
            entry->loaded=loaded;
            entry->loaded_header=header;
            entry->loaded_alive=true;
            entry->claim_serial=next_serial(next_claim_serial_);
            entry->state=State::claimed;
            output.ticket=ClaimTicket{session_epoch_,result.slot,
                entry->seed_serial,entry->claim_serial};
            result=make_result(ErrorCode::ok,result.slot,entry->claim_serial);
        }
        output.result=result;
        return output;
    }

    OperationResult clone_native(const Context& context,
        const ClaimTicket& ticket,const CloneProof& proof) noexcept {
        Entry* entry=nullptr;
        OperationResult result=acquire_claim(context,ticket,entry);
        if (!result.ok()) return result;
        result=check_live(context,*entry);
        if (!result.ok()) return result;
        if (entry->state!=State::claimed) return stage_result(*entry);
        if (proof.loaded!=entry->loaded)
            return loaded_identity_result(*entry,proof.loaded);
        if (!proof.target.valid())
            return make_result(ErrorCode::invalid_argument,result.slot,
                entry->claim_serial);
        if ((entry->source_alive && proof.target==entry->source)
            || (entry->loaded_alive && proof.target==entry->loaded))
            return make_result(ErrorCode::invalid_argument,result.slot,
                entry->claim_serial);
        if ((entry->source_alive && proof.target.address==entry->source.address
                && proof.target.generation!=entry->source.generation)
            || (entry->loaded_alive && proof.target.address==entry->loaded.address
                && proof.target.generation!=entry->loaded.generation))
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (generation_conflict(proof.target,result.slot))
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (identity_in_use(proof.target,result.slot))
            return make_result(ErrorCode::identity_in_use,result.slot,
                entry->claim_serial);
        if (proof.payload!=entry->payload)
            return make_result(ErrorCode::payload_mismatch,result.slot,
                entry->claim_serial);
        if (proof.observed_clone_header!=entry->source_header
            || proof.target_header!=entry->source_header)
            return make_result(ErrorCode::header_mismatch,result.slot,
                entry->claim_serial);
        entry->target=proof.target;
        entry->target_header=proof.target_header;
        entry->target_alive=true;
        entry->state=State::postcloned;
        return make_result(ErrorCode::ok,result.slot,entry->claim_serial);
    }

    OperationResult consume(const Context& context,const ClaimTicket& ticket,
        ObjectRef target,const RivalPayload& payload,
        NativeHeader target_header) noexcept {
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
        if (target.address==entry->target.address
                && target.generation!=entry->target.generation)
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (target!=entry->target)
            return target_identity_result(*entry,target);
        if (payload!=entry->payload)
            return make_result(ErrorCode::payload_mismatch,result.slot,
                entry->claim_serial);
        if (target_header!=entry->target_header)
            return make_result(ErrorCode::header_mismatch,result.slot,
                entry->claim_serial);
        entry->state=State::consumed;
        entry->source_alive=false;
        entry->loaded_alive=false;
        entry->target_alive=false;
        return make_result(ErrorCode::ok,result.slot,entry->claim_serial);
    }

    // The method name is retained for the integration layer.  kind identifies
    // the one direct object that was destroyed; no wrapper/action pair exists.
    OperationResult detach_source(const Context& context,
        const SeedReceipt& receipt,DetachKind kind,ObjectRef object) noexcept {
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
                entry->claim_serial?entry->claim_serial:entry->seed_serial);
        if (kind==DetachKind::source) {
            if (object.address==entry->source.address
                    && object.generation!=entry->source.generation)
                return make_result(ErrorCode::generation_mismatch,result.slot,
                    entry->seed_serial);
            if (object!=entry->source)
                return source_identity_result(*entry,object);
            if (!entry->source_alive)
                return make_result(ErrorCode::source_detached,result.slot,
                    entry->seed_serial);
            entry->source_alive=false;
            if (entry->state==State::seeded) {
                invalidate_entry(*entry);
                return make_result(ErrorCode::source_destroyed,result.slot,
                    entry->seed_serial);
            }
            return make_result(ErrorCode::source_detached,result.slot,
                entry->seed_serial);
        }
        if (kind!=DetachKind::loaded)
            return make_result(ErrorCode::invalid_argument,result.slot,
                entry->seed_serial);
        if (entry->state==State::seeded || entry->state==State::serialized)
            return make_result(ErrorCode::target_not_bound,result.slot,
                entry->seed_serial);
        if (object.address==entry->loaded.address
                && object.generation!=entry->loaded.generation)
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (object!=entry->loaded)
            return loaded_identity_result(*entry,object);
        if (!entry->loaded_alive)
            return make_result(ErrorCode::loaded_detached,result.slot,
                entry->claim_serial);
        entry->loaded_alive=false;
        if (entry->state==State::claimed) {
            invalidate_entry(*entry);
            return make_result(ErrorCode::loaded_destroyed,result.slot,
                entry->claim_serial);
        }
        return make_result(ErrorCode::loaded_detached,result.slot,
            entry->claim_serial);
    }

    OperationResult destroy_target(const Context& context,
        const ClaimTicket& ticket,ObjectRef target) noexcept {
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
        if (target.address==entry->target.address
                && target.generation!=entry->target.generation)
            return make_result(ErrorCode::generation_mismatch,result.slot,
                entry->claim_serial);
        if (target!=entry->target)
            return target_identity_result(*entry,target);
        entry->target_alive=false;
        invalidate_entry(*entry);
        return make_result(ErrorCode::target_destroyed,result.slot,
            entry->claim_serial);
    }

    OperationResult revoke_request(const Context& context,
        const SeedReceipt& receipt) noexcept {
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
        invalidate_entry(*entry);
        return make_result(ErrorCode::request_revoked,result.slot,
            entry->claim_serial?entry->claim_serial:entry->seed_serial);
    }

    InvalidationResult invalidate_expired(const Context& context) noexcept {
        InvalidationResult output{};
        OperationResult context_result=check_context(context);
        if (!context_result.ok()) {
            output.result=context_result;
            return output;
        }
        for (std::uint16_t slot=0;slot<kLedgerCapacity;++slot) {
            Entry& entry=entries_[slot];
            if (!is_live_state(entry.state)) continue;
            if (context.current_tick>entry.deadline_tick
                || context.current_date!=entry.payload.date_raw) {
                invalidate_entry(entry);
                ++output.invalidated;
            }
        }
        output.result=make_result(ErrorCode::ok);
        return output;
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
        output.result=result;
        fill_view(*entry,output.view);
        return output;
    }

private:
    struct Entry {
        char request_id[kMaxRequestId+1]{};
        State state=State::empty;
        RivalPayload payload{};
        ObjectRef source{};
        ObjectRef loaded{};
        ObjectRef target{};
        NativeHeader source_header{};
        NativeHeader loaded_header{};
        NativeHeader target_header{};
        std::uint64_t deadline_tick=0;
        std::uint64_t seed_serial=0;
        std::uint64_t claim_serial=0;
        bool source_header_bound=false;
        bool source_alive=false;
        bool loaded_alive=false;
        bool target_alive=false;
    };

    std::array<Entry,kLedgerCapacity> entries_{};
    std::uint64_t session_epoch_=0;
    std::uint64_t next_seed_serial_=0;
    std::uint64_t next_claim_serial_=0;

    static constexpr bool valid_phase(Phase phase) noexcept {
        return phase==Phase::initiate;
    }

    static bool valid_payload(const RivalPayload& payload) noexcept {
        return payload.family==Family::rival
            && (payload.command==CommandKind::set_rival
                || payload.command==CommandKind::remove_rival)
            && payload.actor!=0 && payload.target!=0
            && payload.actor!=payload.target && payload.old_rival==0;
    }

    static bool valid_deadline(std::uint64_t current_tick,
        std::uint64_t deadline_tick) noexcept {
        return deadline_tick>current_tick
            && deadline_tick-current_tick<=kMaxDeadlineTtlMs;
    }

    static bool valid_request_id(const char* request_id) noexcept {
        if (!request_id) return false;
        for (std::size_t index=0;index<=kMaxRequestId;++index) {
            const unsigned char value=static_cast<unsigned char>(request_id[index]);
            if (value==0) return index!=0;
            const bool alpha_numeric=(value>='A' && value<='Z')
                || (value>='a' && value<='z')
                || (value>='0' && value<='9');
            if ((!alpha_numeric && value!='_' && value!='-')
                || index==kMaxRequestId) return false;
        }
        return false;
    }

    static void copy_request_id(char (&destination)[kMaxRequestId+1],
        const char* source) noexcept {
        std::size_t index=0;
        for (;index<kMaxRequestId && source[index]!=0;++index)
            destination[index]=source[index];
        destination[index]=0;
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
        return context.session_epoch==session_epoch_
            ? make_result(ErrorCode::ok) : make_result(ErrorCode::wrong_epoch);
    }

    static bool is_live_state(State state) noexcept {
        return state==State::seeded || state==State::serialized
            || state==State::claimed || state==State::postcloned;
    }

    std::uint16_t slot_of(const Entry& entry) const noexcept {
        return static_cast<std::uint16_t>(&entry-entries_.data());
    }

    OperationResult check_live(const Context& context,Entry& entry) noexcept {
        const std::uint16_t slot=slot_of(entry);
        const std::uint64_t serial=entry.claim_serial
            ? entry.claim_serial : entry.seed_serial;
        if (is_live_state(entry.state)
            && context.current_date!=entry.payload.date_raw) {
            invalidate_entry(entry);
            return make_result(ErrorCode::date_mismatch,slot,serial);
        }
        if (is_live_state(entry.state)
            && context.current_tick>entry.deadline_tick) {
            invalidate_entry(entry);
            return make_result(ErrorCode::deadline_expired,slot,serial);
        }
        return make_result(ErrorCode::ok,slot,serial);
    }

    static void invalidate_entry(Entry& entry) noexcept {
        entry.state=State::invalidated;
        entry.source_alive=false;
        entry.loaded_alive=false;
        entry.target_alive=false;
    }

    OperationResult stage_result(const Entry& entry) const noexcept {
        const std::uint16_t slot=slot_of(entry);
        const std::uint64_t serial=entry.claim_serial
            ? entry.claim_serial : entry.seed_serial;
        if (entry.state==State::consumed)
            return make_result(ErrorCode::already_consumed,slot,serial);
        if (entry.state==State::invalidated)
            return make_result(ErrorCode::already_invalidated,slot,serial);
        return make_result(ErrorCode::invalid_stage,slot,serial);
    }

    OperationResult source_identity_result(const Entry& entry,
        ObjectRef object) const noexcept {
        const std::uint16_t slot=slot_of(entry);
        const std::uint64_t serial=entry.claim_serial
            ? entry.claim_serial : entry.seed_serial;
        if (object.address==entry.source.address
            && object.generation!=entry.source.generation)
            return make_result(ErrorCode::generation_mismatch,slot,serial);
        return make_result(ErrorCode::identity_mismatch,slot,serial);
    }

    OperationResult loaded_identity_result(const Entry& entry,
        ObjectRef object) const noexcept {
        const std::uint16_t slot=slot_of(entry);
        const std::uint64_t serial=entry.claim_serial
            ? entry.claim_serial : entry.seed_serial;
        if (object.address==entry.loaded.address
            && object.generation!=entry.loaded.generation)
            return make_result(ErrorCode::generation_mismatch,slot,serial);
        return make_result(ErrorCode::identity_mismatch,slot,serial);
    }

    OperationResult target_identity_result(const Entry& entry,
        ObjectRef object) const noexcept {
        const std::uint16_t slot=slot_of(entry);
        const std::uint64_t serial=entry.claim_serial
            ? entry.claim_serial : entry.seed_serial;
        if (object.address==entry.target.address
            && object.generation!=entry.target.generation)
            return make_result(ErrorCode::generation_mismatch,slot,serial);
        return make_result(ErrorCode::identity_mismatch,slot,serial);
    }

    std::uint16_t find_empty_slot() const noexcept {
        for (std::uint16_t index=0;index<kLedgerCapacity;++index)
            if (entries_[index].state==State::empty) return index;
        return kInvalidSlot;
    }

    std::uint16_t find_request(const char* request_id) const noexcept {
        for (std::uint16_t index=0;index<kLedgerCapacity;++index)
            if (entries_[index].state!=State::empty
                && request_equal(entries_[index].request_id,request_id))
                return index;
        return kInvalidSlot;
    }

    std::uint16_t find_header(NativeHeader header) const noexcept {
        for (std::uint16_t index=0;index<kLedgerCapacity;++index)
            if (entries_[index].state!=State::empty
                && entries_[index].source_header_bound
                && entries_[index].source_header==header)
                return index;
        return kInvalidSlot;
    }

    static bool same_address_different_generation(ObjectRef left,
        ObjectRef right) noexcept {
        return left.address!=0 && left.address==right.address
            && left.generation!=right.generation;
    }

    bool identity_in_use(ObjectRef object,
        std::uint16_t except=kInvalidSlot) const noexcept {
        for (std::uint16_t index=0;index<kLedgerCapacity;++index) {
            if (index==except || !is_live_state(entries_[index].state)) continue;
            const Entry& entry=entries_[index];
            const ObjectRef refs[]={entry.source,entry.loaded,entry.target};
            const bool alive[]={entry.source_alive,entry.loaded_alive,
                entry.target_alive};
            for (std::size_t ref_index=0;ref_index<3;++ref_index)
                if (alive[ref_index] && refs[ref_index]==object) return true;
        }
        return false;
    }

    bool generation_conflict(ObjectRef object,
        std::uint16_t except=kInvalidSlot) const noexcept {
        for (std::uint16_t index=0;index<kLedgerCapacity;++index) {
            if (index==except || !is_live_state(entries_[index].state)) continue;
            const Entry& entry=entries_[index];
            const ObjectRef refs[]={entry.source,entry.loaded,entry.target};
            const bool alive[]={entry.source_alive,entry.loaded_alive,
                entry.target_alive};
            for (std::size_t ref_index=0;ref_index<3;++ref_index)
                if (alive[ref_index]
                    && same_address_different_generation(refs[ref_index],object))
                    return true;
        }
        return false;
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
        view.family=entry.payload.family;
        view.command=entry.payload.command;
        view.phase=Phase::initiate;
        view.payload=entry.payload;
        view.source=entry.source;
        view.loaded=entry.loaded;
        view.target=entry.target;
        view.source_header=entry.source_header;
        view.loaded_header=entry.loaded_header;
        view.target_header=entry.target_header;
        view.date_raw=entry.payload.date_raw;
        view.deadline_tick=entry.deadline_tick;
        view.seed_serial=entry.seed_serial;
        view.claim_serial=entry.claim_serial;
        view.source_header_bound=entry.source_header_bound;
        view.source_alive=entry.source_alive;
        view.loaded_alive=entry.loaded_alive;
        view.target_alive=entry.target_alive;
    }
};

} // namespace bridge::rival_command_authority
