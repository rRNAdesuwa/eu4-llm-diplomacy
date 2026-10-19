#pragma once
#include "v18-preimage/spy_core.h"

namespace eu4_spy19 {
using Fields=eu4_spy18::Fields;
enum class Operation:std::uint32_t { begin=1, next_item=2, later_health=3 };
enum class State:std::uint32_t { fresh, ready, awaiting_health, complete, frozen };
enum class Step:std::uint32_t { none, batch_claim, item_claim, factory, initialize,
    full_preview, wrap_owned, command_gate, destroy_original, destroy_command, submit };
enum class Kind:std::uint32_t { batch_claimed, item_claimed, step_intent, step_return,
    dispatch_intent, item_return, later_health, batch_complete, fault };
enum class Reason:std::uint32_t { none,bad_host,busy,frozen,order,wrong_thread,image_pin,
    root_guard,rejected_guard,audit_failed,resolver_failed,factory_unknown,
    fields_mismatch,alias_or_ownership,native_exception,read_budget,claim_failed,
    transfer_unknown,event_budget };
enum class Point:std::uint32_t { before_work, after_work, before_cleanup };
enum class Outcome:std::uint32_t { unattempted, in_progress, full_preview_rejected,
    command_gate_rejected, dispatch_unknown, dispatched };
struct Identity {
    std::uint32_t pid;
    std::uint64_t creation_filetime;
    char session[33],dll_sha256[65],manifest_sha256[65];
};
struct Stamp:eu4_spy18::Stamp {
    std::uintptr_t holder,context,transport;
    std::uint64_t actor_overlord,target_overlord,effective_player;
    std::uint32_t country_count;
    std::uint8_t context_ready55,context_ready80d;
    std::int32_t native_speed_index;
};
struct Item {
    std::uint32_t ordinal,family,token,original_id,clone_id,command_id;
    std::uint64_t owner_frame;
    Step step;Outcome outcome;
    bool claimed,call_entered,call_returned,preview_observed,preview_allowed,
         gate_observed,gate_allowed,original_destroyed,command_destroyed,clone_destroyed,
         submit_entered,submit_returned,submit_value_observed,submit_value,slot_observed,slot_consumed;
    bool has_local_original,has_local_command,has_local_clone,current;
    Fields original_fields,clone_fields;
};
struct Event {
    Kind kind;Operation operation;Identity identity;Stamp stamp;Item item;
    std::uint32_t request_sequence,completed,exception_code;
    std::uint64_t frame,uptime_ms,expires_uptime_ms;
    Reason reason;State state;
    bool mock_resolver,production_ready,strict_sp_verified,epoch_verified,effect_verified;
};
struct Result {
    State state;Reason reason;Item current_item;Outcome completed_outcomes[5];
    std::uint32_t completed,exception_code,read_calls;
    std::size_t bytes_read;
    bool accepted_call,audit_complete,freeze_session,ownership_uncertain;
    bool retry_allowed,runtime_verified,production_ready,effect_verified,strict_sp_verified,epoch_verified;
};
// Claim and log must return true only after a unique claim / complete append
// has been durably flushed. A stage/claim assertion alone cannot authorize a
// production process. No actual filesystem/host implementation is provided.
using Guard=bool (*)(void*,Point,Step,const Identity*,const Stamp*);
using Logger=bool (*)(void*,const Event*);
using Claim=bool (*)(void*,std::uint32_t request_sequence,std::uint32_t item_ordinal,
                    const Identity*,const Stamp*);
struct Host {
    std::uint32_t struct_size,abi_version,expected_game_thread,request_sequence;
    std::uintptr_t image_base;Identity identity;
    const char* game_sha256;
    std::uint64_t frame_id,expires_uptime_ms;
    bool full_sha256_verified,same_session_preflight_verified,disposable_test_authorized,isolated_mock_resolver;
    eu4_spy18::Read read;eu4_spy18::WriteOwned write_owned;eu4_spy18::Resolve resolve;
    eu4_spy18::Clock clock;Guard guard;Logger log;Claim claim;void* user;
};
// Private fixed-family core only. Never reset/copy/rearm. A future host must
// guarantee a single process instance and real successive owner callbacks.
class Core {
public:
    Core() noexcept;
    Core(const Core&)=delete;Core& operator=(const Core&)=delete;
    Result invoke(Operation,const Host&);
private:
    volatile LONG active_,frozen_;
    Host locked_host_;Stamp locked_;Result saved_;
    std::uint32_t next_object_id_,events_,total_reads_;
    std::size_t total_bytes_;
    std::uint64_t last_clock_,last_frame_,completion_frame_;
    friend struct Runner;
};
const char* family_name(std::uint32_t) noexcept;
} // namespace eu4_spy19
