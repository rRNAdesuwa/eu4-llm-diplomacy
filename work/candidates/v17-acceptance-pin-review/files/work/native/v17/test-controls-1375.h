#pragma once
#include <cstddef>
#include <cstdint>

// Private research support only. No console/script text, file names, addresses,
// mailbox operations or claims can be supplied as a public request.
namespace eu4_test_controls_1375 {
constexpr std::uint32_t kAbiVersion = 1;
struct Snapshot {
    std::uint64_t game_cookie;
    std::uint64_t server_cookie;
    std::uint64_t pause_manager_cookie;
    std::uint64_t player_handle;
    std::int32_t raw_date;
    std::int32_t native_speed_index;
    bool paused;
    bool manual_pause;
    bool native_multiplayer_classifier;
    bool world_reset_active; // game+7485 transient guard, NOT a generation.
    bool load_source_present; // game+74c8 nonnull, NOT complete load coverage.
};
enum class GuardPoint : std::uint32_t { before_call, after_call };
struct GuardInput {
    GuardPoint point;
    unsigned requested_speed;
    Snapshot observed;
};
using Guard = bool (*)(void* user, const GuardInput* input);
using Logger = bool (*)(void* user, const char* json, std::size_t bytes);
struct Host {
    std::uint32_t struct_size;
    std::uint32_t abi_version;
    std::uint32_t expected_game_thread;
    bool durable_attempt_claimed;
    bool full_sha256_verified;
    Guard guard;
    Logger log;
    void* user;
};
enum class Reason : std::uint32_t {
    none, invalid_request, busy, frozen, host_contract, wrong_thread,
    image_pin, unreadable_state, guard_rejected, audit_failed,
    callback_contract, result_string_contract, readback_mismatch,
    native_exception
};
struct Result {
    Reason reason;
    unsigned requested_speed;
    Snapshot before;
    Snapshot after;
    bool write_entered;
    bool callback_returned;
    bool callback_success;
    bool result_destroyed;
    bool readback_observed;
    bool readback_matches;
    bool audit_complete;
    bool freeze_session;
    bool retry_allowed; // Always false.
    std::uint32_t exception_code;
};

// Caller must CREATE_NEW and durably flush a unique attempt claim first, then
// invoke on the verified game thread in a disposable non-Ironman offline lab.
// Host guard enforces session/world epoch, fixed roots/player, monotonic date,
// authorized operation and log health. It may allow a running world for this
// speed control. No callback may call engine code, load/advance or reenter.
// 0 requests pause; 1..5 request running. Engine stores min(request,4), so 4/5
// both select native index4. A speed index alone does not establish pause.
// No automatic retry, native save call or own request/claim management occurs.
Result set_speed(unsigned requested_speed, const Host& host);
// Read-only, exact-pin observation; no native calls, host callbacks or files.
// Host should run this on its verified frame thread. False means unknown;
// exception_code is nonzero only when a guarded read faults.
bool observe(Snapshot& output, std::uint32_t& fault_code);
} // namespace eu4_test_controls_1375
