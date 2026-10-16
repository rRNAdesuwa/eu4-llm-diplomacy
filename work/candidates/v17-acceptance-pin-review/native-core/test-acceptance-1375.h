#pragma once
#include "test-controls-1375.h"
#include <cstddef>
#include <cstdint>

// Isolated research candidate only. No mailbox, hook, raw console input,
// arbitrary address/argument surface, ownership repair or production API.
namespace eu4_test_acceptance_1375 {
constexpr std::uint32_t kAbiVersion = 1;
enum class Operation : std::uint32_t { enable = 1, disable = 2 };
enum class GuardPoint : std::uint32_t { before_call, after_call, before_result_destroy };
using Snapshot = eu4_test_controls_1375::Snapshot;
struct GuardInput {
    GuardPoint point;
    Operation operation;
    Snapshot observed;
    std::uint32_t raw_flag;
};
using Guard = bool (*)(void* user, const GuardInput* input);
using Logger = bool (*)(void* user, const char* json, std::size_t bytes);
struct Host {
    std::uint32_t struct_size;
    std::uint32_t abi_version;
    std::uint32_t expected_game_thread;
    bool durable_attempt_claimed;
    bool full_sha256_and_preflight_verified;
    Guard guard;
    Logger log;
    void* user;
};
enum class Reason : std::uint32_t {
    none, invalid_request, host_contract, wrong_thread, busy, frozen,
    image_pin, unreadable_state, wrong_world, guard_rejected, audit_failed,
    already_desired, callback_contract, callback_rejected, input_modified,
    result_string_contract, readback_mismatch, native_exception
};
enum class Stage : std::uint32_t {
    entry, image_pin, before_observation, before_guard, begin_audit,
    final_observation, final_guard, callback, after_observation,
    after_guard, output_contract, destroy_guard, result_destructor,
    final_readback, final_after_guard, complete
};
struct Result {
    Operation operation;
    Reason reason;
    Stage stage; // Last entered phase; retained on SEH/failure.
    Snapshot before;
    Snapshot after;
    std::uint32_t before_raw_flag;
    std::uint32_t after_raw_flag;
    bool before_flag_observed;
    bool after_flag_observed;
    bool no_native;
    bool native_invoked;
    bool callback_returned;
    bool callback_success;
    bool callback_result_identity;
    bool zero_arguments_confirmed;
    bool arguments_unchanged;
    bool result_destroyed;
    bool world_identity_unchanged;
    bool readback_observed;
    bool readback_matches;
    bool audit_complete; // True only after complete log callback returns true.
    bool freeze_session;
    bool retry_allowed; // Always false, including clean/no-native rejection.
    std::uint32_t exception_code;
};

// Host must bind the original immutable grant and durable CREATE_NEW claim
// before entry; it owns the fixed on/submit/off sequence and all window states.
// Callbacks must not throw, call engine methods, change/load/advance the world
// or reenter this module. Logger true means the entire record was flushed.
// before_call may reject expiry; after_call/before_result_destroy are cleanup
// guards that still enforce thread/world/date/pause/audit and the original
// grant, without treating elapsed request TTL as permission to replay a call.
// This core checks the reviewed classifier and ironman byte, but neither is
// a strict-SP/world-generation proof. The disposable research scope remains
// the caller's responsibility. Full build SHA/preflight are caller evidence.
// A desired-state match is a no-native diagnostic, never an authorization.
// Once the handler is entered, any failure freezes: no second toggle, unknown
// string destructor, deferred cleanup, direct flag store or retry follows.
Result invoke(Operation operation, const Host& host);

// RO helper only: exact module pins plus controls.observe and full FRA identity.
// May observe a running world; invoke separately requires paused state. False
// means unknown and supplies no authorization. No game method is called.
bool observe(Snapshot& output, std::uint32_t& raw_flag, std::uint32_t& fault_code);
} // namespace eu4_test_acceptance_1375
