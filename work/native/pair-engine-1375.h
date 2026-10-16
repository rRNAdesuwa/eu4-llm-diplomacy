#pragma once
#include <cstddef>
#include <cstdint>

// Internal research core, linked only into the independent v6 lab host.
// Not exported or registered as a production execution API.
// All ten IDs remain unverified as a reusable execution backend. One prior
// fixed FRA->ENG improvement experiment does not validate the other operations.
namespace eu4_pair_1375 {
constexpr std::uint32_t kAbiVersion = 1;

enum class ActionId : std::uint32_t {
    offer_vassalization, cancel_vassalization,
    royal_marriage, break_marriage,
    improve_relations, stop_improving_relations,
    guarantee, revoke_guarantee,
    build_spy_network, stop_building_spy_network
};
enum class Mode : std::uint32_t { legality_only, submit };
enum class Status : std::uint32_t {
    pre_dispatch_rejected, legality_only, dispatched, dispatch_unknown
};
enum class Reason : std::uint32_t {
    none, bad_abi, invalid_request, busy, session_frozen, authorization_missing,
    preflight_missing, wrong_thread, guard_rejected, audit_failed, image_pin_failed,
    live_identity_failed, nonplayer_submit_unverified, cancellation_binding_failed,
    factory_unavailable, action_contract_failed, wrapper_contract_failed,
    preview_rejected, command_rejected, world_changed, context_unavailable,
    ownership_uncertain, native_exception, dispatch_not_acknowledged
};
enum class Phase : std::uint32_t {
    entry, image_pin, live_identity, cancellation_binding, factory, initialize,
    preview, wrapper, command_gate, original_destructor, context_pin,
    pre_dispatch_audit, final_guard, context_submit, pre_dispatch_cleanup, complete
};
enum class GuardPoint : std::uint32_t { before_allocation, before_dispatch };

// Public request data: no pointers, raw offsets, force/state fields or envoy IDs.
struct Request {
    ActionId action;
    char actor[4];   // Exactly "FRA", "ENG", or "POR", followed by NUL.
    char target[4];  // Different from actor. Only these fixed identities resolve.
};
struct Stamp {
    std::uint32_t pid;
    std::uint32_t thread_id;
    std::uint64_t process_creation_filetime;
    std::uint64_t world_cookie; // Comparison-only identity, never a caller input address.
    std::uint64_t actor_handle;
    std::uint64_t target_handle;
    std::uint64_t player_handle;
    std::int32_t raw_date;
};
struct GuardInput {
    GuardPoint point;
    Mode mode;
    Request request;
    Stamp observed;
};
using Guard = bool (*)(void* user, const GuardInput* input);
using Logger = bool (*)(void* user, const char* json, std::size_t bytes);

// Trusted integration state, never mailbox/public request fields. The caller
// must verify full executable SHA256 and its actual same-session lifecycle,
// preview and command preflight results; this core does not manufacture them.
// Callbacks must not throw, call game code, reenter this core, or advance/load
// the world. Logger true MUST mean the complete record was durably persisted.
// Guard independently enforces request authorization, freshness, session/world
// epoch, verified single-player authority, and the observed game thread.
// Transport existence is not a single-player/authority predicate.
// No mailbox, marker or request-id ledger
// is implemented here; caller provides those before setting authorized=true.
struct Host {
    std::uint32_t struct_size;
    std::uint32_t abi_version;
    std::uint32_t expected_game_thread;
    bool authorized;
    bool full_sha256_and_same_session_preflight_verified;
    Guard guard;
    Logger log;
    void* user;
};
struct Result {
    Status status;
    Reason reason;
    Phase phase;
    Stamp stamp;
    std::uint32_t exception_code;
    std::int32_t resolved_envoy_id; // Evidence only; never accepted as an input.
    bool initialized;
    bool preview_called;
    bool preview_allowed;
    bool gate_called;
    bool gate_allowed;
    bool original_destroyed;
    bool command_destroyed_before_dispatch; // Pinned dtor owns its clone.
    bool ownership_uncertain;
    bool submit_entered;
    bool submit_returned;
    bool context_submit_return;
    bool caller_container_consumed;
    bool audit_complete;
    bool freeze_session;
    bool retry_allowed; // Always false; caller must never auto-retry this call.
    bool applied_verified; // Always false; requires a separate effect observer.
};

const char* action_name(ActionId action);
bool parse_action_id(const char* text, std::size_t length, ActionId* output);
// Must run on the verified in-process game/frame thread. Submit currently
// requires actor == current player; other known actors can use legality_only.
// A frozen process-local core cannot be reset or hot-replaced by this module.
Result invoke(const Request& request, Mode mode, const Host& host);
} // namespace eu4_pair_1375
