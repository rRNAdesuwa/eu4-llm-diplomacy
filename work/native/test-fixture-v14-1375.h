#pragma once
#include "v14/test-controls-1375.h"
#include <cstddef>
#include <cstdint>

// Private, compile-only v14 research core. No mailbox, hook, dispatcher or
// arbitrary console/script/target input. Link with the unchanged test controls.
namespace eu4_test_fixture_1375 {
constexpr std::uint32_t kAbiVersion = 1;
enum class Operation : std::uint32_t { enable = 1, disable = 2 };
enum class GuardPoint : std::uint32_t { before_call, before_result_destroy, after_call };
using Snapshot = eu4_test_controls_1375::Snapshot;
struct GuardInput { GuardPoint point; Operation operation; Snapshot observed; };
using Guard = bool (*)(void* user, const GuardInput* input);
using Logger = bool (*)(void* user, const char* json, std::size_t bytes);
struct Host {
    std::uint32_t struct_size;
    std::uint32_t abi_version;
    std::uint32_t expected_game_thread;
    bool durable_attempt_claimed;
    bool full_sha256_verified;
    // Host verifies the reviewed profile's files and enabled-mod settings were
    // installed before this PID's creation, with current hashes matching the
    // manifest. This is file/startup evidence, NOT proof of engine registration.
    // The native callback itself looks up the event and can reject its absence.
    bool fixture_definition_files_verified;
    // Host-owned NUL-terminated 64-character hex digest of reviewed fixture
    // manifest; copied before native entry. Not an API-supplied script path.
    const char* fixture_profile_sha256;
    Guard guard;
    Logger log;
    void* user;
};
enum class Reason : std::uint32_t {
    none, invalid_request, host_contract, wrong_thread, busy, frozen,
    image_pin, unreadable_state, wrong_world, guard_rejected, audit_failed,
    callback_contract, callback_rejected, input_modified,
    result_string_contract, callback_flag_changed, native_exception
};
struct Result {
    Operation operation;
    Reason reason;
    Snapshot before;
    Snapshot after;
    bool native_invoked;
    bool callback_returned;
    bool callback_success;
    bool arguments_unchanged;
    bool result_destroyed;
    bool world_identity_unchanged;
    bool callback_flag_restored;
    bool audit_complete;
    bool freeze_session;
    bool retry_allowed; // Always false; host must never replay a claimed attempt.
    bool fixture_effect_verified; // Always false; inspect state independently.
    std::uint32_t exception_code;
};

// Maps enable/disable solely to {"llmt.1"/"llmt.2", "FRA"}; both arguments
// are String32 SSO, need no native allocator and are never native-destroyed.
// A successful callback means invoked/returned, not that modifiers or envoy
// availability changed. Host owns durable claim + audit, game-thread and
// disposable non-Ironman offline-session and fixture file/startup evidence. Pause and full
// FRA identity are checked here too. Exceptions permanently freeze this core;
// no destructor, callback retry or native repair follows an exception.
Result invoke(Operation operation, const Host& host);
} // namespace eu4_test_fixture_1375
