// Restricted, session-bound v6 research host. Not a production backend.
// Three explicit preflight markers precede a canonical ten-ID/speed mailbox.
// Roots/player/date checks are conservative invariants, NOT a load-generation
// proof. Never unload/rearm a live host, automatically retry, or infer applied
// diplomacy from a native dispatch acknowledgement.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <sddl.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "pair-engine-1375.h"
#include "test-controls-1375.h"
#include "lab-request-1375.h"

extern "C" void research_frame_stub();
extern "C" void research_original_trampoline();
extern "C" { void* research_trampoline = nullptr; }
extern "C" { void* research_return = nullptr; }
extern bool pair_selftest(uintptr_t, void (*)(const char*));
extern bool pair_preview(uintptr_t, void (*)(const char*));
extern bool pair_command_selftest(uintptr_t, void (*)(const char*));

static HMODULE self_module;
static uintptr_t game_base;
static HANDLE output = INVALID_HANDLE_VALUE;
static volatile LONG installed = 0, active = 0, frames = 0, research_enabled = 0;
static volatile LONG thread_changed = 0;
static DWORD window_thread;
static bool tested = false, selftest_passed = false, preview_tested = false, preview_passed = false;
static bool command_tested = false, command_passed = false, audit_failed = false;
static bool world_locked = false, world_changed = false, session_frozen = false, any_dispatch_entered = false;
static uintptr_t locked_world = 0, locked_database = 0, locked_array = 0;
static uint64_t locked_player = 0, process_created = 0, last_sequence = 0;
static int32_t locked_date = 0;
static ULONGLONG last_log = 0;
static LONG last_health_frame = 0, last_phase_frame = 0;
static wchar_t session_directory[MAX_PATH]{};
static wchar_t request_file[MAX_PATH]{}, preview_request_file[MAX_PATH]{}, command_request_file[MAX_PATH]{};
using NextThread = LONG (NTAPI*)(HANDLE, HANDLE, ACCESS_MASK, ULONG, ULONG, PHANDLE);
static NextThread next_thread;
static const unsigned char prefix[20] = {
    0x4c,0x89,0x44,0x24,0x18,0x55,0x53,0x57,0x48,0x8d,
    0x6c,0x24,0xb0,0x48,0x81,0xec,0x50,0x01,0x00,0x00};
static constexpr uintptr_t frame_rva = 0x10a6ec0;
static constexpr DWORD audit_exception = 0xe1375006;
static constexpr uint64_t france_handle = 0x0100007a00415246ULL;
// Research-only: positive speed requires an external exact-process watchdog.
// The in-process lease attempts pause at its next healthy frame; a stalled or
// frozen host cannot guarantee cleanup. The manifest records both constraints.
static constexpr bool running_speed_enabled = true;

static bool durable_log(const char* message) {
    if (output == INVALID_HANDLE_VALUE || audit_failed) { audit_failed = true; session_frozen = true; return false; }
    char complete[4096]{};
    size_t length = strnlen_s(message, sizeof(complete));
    if (length == 0 || length >= sizeof(complete) - 1) { audit_failed = true; session_frozen = true; return false; }
    memcpy(complete, message, length);
    if (complete[length - 1] != '\n') complete[length++] = '\n';
    DWORD written = 0;
    const bool okay = WriteFile(output, complete, static_cast<DWORD>(length), &written, nullptr)
        && written == static_cast<DWORD>(length) && FlushFileBuffers(output);
    if (!okay) { audit_failed = true; session_frozen = true; }
    return okay;
}
// Compatibility with unchanged, separately copied v5 phase functions. Their
// per-case logging occurs after destruction/exception handling. Failed durable
// logging raises immediately into the host SEH; no next case can be invoked.
static void log_line(const char* message) { if (!durable_log(message)) RaiseException(audit_exception, 0, 0, nullptr); }

template<typename T> static bool read_value(uintptr_t address, T& value) {
    SIZE_T actual = 0;
    return address >= 0x10000 && address < 0x0000800000000000ULL - sizeof(value)
        && ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<const void*>(address), &value, sizeof(value), &actual)
        && actual == sizeof(value);
}
static bool object_pointer(uintptr_t p) { return p >= 0x10000 && p < 0x0000800000000000ULL && p % 8 == 0; }
static bool in_session_path(wchar_t (&out)[MAX_PATH], const wchar_t* name) {
    return wcscpy_s(out, session_directory) == 0 && wcscat_s(out, name) == 0;
}
static bool sequence_path(wchar_t (&out)[MAX_PATH], uint64_t sequence, const wchar_t* suffix) {
    wchar_t name[64]{};
    return swprintf_s(name, L"%020llu.%s", static_cast<unsigned long long>(sequence), suffix) > 0 && in_session_path(out, name);
}
static bool marker_absent(const wchar_t* path) {
    if (GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES) return false;
    return GetLastError() == ERROR_FILE_NOT_FOUND;
}
static bool create_durable_file(const wchar_t* path, const char* contents, DWORD length) {
    HANDLE file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    const bool okay = WriteFile(file, contents, length, &written, nullptr) && written == length && FlushFileBuffers(file);
    const bool closed = CloseHandle(file) != FALSE;
    // Partial or complete claims are deliberately retained forever.
    return okay && closed;
}
static bool freeze(const char* reason) {
    const bool newly_frozen = !session_frozen;
    session_frozen = true;
    if (newly_frozen && !audit_failed) {
        char line[768]{};
        sprintf_s(line, "{\"event\":\"lab_session_frozen\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"reason\":\"%s\",\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), reason);
        durable_log(line);
    }
    return false;
}

static bool observe_world(bool require_pause, bool acquire, eu4_test_controls_1375::Snapshot* snapshot = nullptr) {
    eu4_test_controls_1375::Snapshot observed{};
    uint32_t fault = 0;
    uintptr_t world = 0, database = 0, array = 0, country = 0;
    uint64_t player = 0;
    if (!eu4_test_controls_1375::observe(observed, fault)
        || !read_value(game_base + 0x233fe78, world) || !object_pointer(world)
        || !read_value(game_base + 0x233d8d0, database) || !object_pointer(database)
        || !read_value(database + 0x118, array) || !object_pointer(array)
        || !read_value(world + 0x1e60, player) || player != france_handle
        || observed.game_cookie != world || observed.player_handle != player || observed.raw_date <= 0
        || observed.world_reset_active || observed.load_source_present || observed.native_multiplayer_classifier
        || !read_value(array + 122 * 8, country) || !object_pointer(country)) {
        if (world_locked) freeze("world_unavailable_or_loading_flag");
        return false;
    }
    uint64_t identity = 0;
    if (!read_value(country + 0x20, identity) || identity != player) {
        if (world_locked) freeze("player_full_identity_changed");
        return false;
    }
    if (world_locked && (world != locked_world || database != locked_database || array != locked_array
        || player != locked_player || observed.raw_date < locked_date)) {
        world_changed = true;
        return freeze("world_roots_player_or_date_regressed");
    }
    if (require_pause && !observed.paused) return false; // Running speed itself never invalidates the session.
    if (!world_locked && acquire) {
        locked_world = world; locked_database = database; locked_array = array;
        locked_player = player; locked_date = observed.raw_date; world_locked = true;
    }
    if (world_locked) locked_date = observed.raw_date; // Monotonic, not a permanent date equality gate.
    if (snapshot) *snapshot = observed;
    return true;
}

struct ActiveRequest {
    eu4_lab_1375::MailboxRequest request;
    bool durable_claim;
    bool operation_entered;
    bool lease_pause;
};
static ActiveRequest lease_operation{};
static bool lease_active = false;
static ULONGLONG lease_deadline = 0;
static int32_t lease_start_date = 0;
static constexpr ULONGLONG lease_duration_ms = 5000;
static constexpr int32_t lease_max_raw_date_delta = 48; // Two native 24-hour dates.
static bool request_guard(const ActiveRequest& operation, bool require_pause) {
    return operation.durable_claim && !session_frozen && !audit_failed && !world_changed && world_locked
        && tested && selftest_passed && preview_tested && preview_passed && command_tested && command_passed
        && GetCurrentThreadId() == window_thread && !InterlockedCompareExchange(&thread_changed, 0, 0)
        && operation.request.pid == GetCurrentProcessId() && operation.request.creation == process_created
        && operation.request.sequence == last_sequence
        && (operation.operation_entered || GetTickCount64() < operation.request.expires)
        && observe_world(require_pause, false);
}
static bool pair_guard(void* user, const eu4_pair_1375::GuardInput* input) {
    auto operation = static_cast<ActiveRequest*>(user);
    return input != nullptr && !std::strcmp(operation->request.operation, "pair")
        && request_guard(*operation, true) && input->observed.pid == GetCurrentProcessId()
        && input->observed.process_creation_filetime == process_created && input->observed.thread_id == window_thread
        && input->observed.world_cookie == locked_world && input->observed.player_handle == locked_player
        && input->observed.raw_date == locked_date;
}
static bool controls_guard(void* user, const eu4_test_controls_1375::GuardInput* input) {
    auto operation = static_cast<ActiveRequest*>(user);
    if (input == nullptr || std::strcmp(operation->request.operation, "speed") || input->requested_speed != operation->request.speed) return false;
    // TTL applies before native entry; after-call cleanup/readback must not be
    // mistaken for a retry when the original request expires during the call.
    if (input->point == eu4_test_controls_1375::GuardPoint::after_call) operation->operation_entered = true;
    return request_guard(*operation, false) && input->observed.game_cookie == locked_world
        && input->observed.player_handle == locked_player && input->observed.raw_date == locked_date;
}
static bool request_logger(void* user, const char* json, size_t length) {
    auto operation = static_cast<ActiveRequest*>(user);
    if (json == nullptr || length == 0 || length >= 3000 || strnlen_s(json, length + 1) != length) return freeze("invalid_native_audit_record");
    char line[4096]{};
    const int count = std::snprintf(line, sizeof(line),
        "{\"event\":\"lab_native_record\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"lease_pause\":%s,\"record\":%s}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(operation->request.sequence),
        operation->lease_pause ? "true" : "false", json);
    return count > 0 && static_cast<size_t>(count) < sizeof(line) && durable_log(line);
}

// Request remains exclusively open through parsing and durable claim creation.
// Deletion is performed on that same verified handle, eliminating path swaps.
enum class InputState { absent, consumed, failed };
static InputState consume_input(const wchar_t* path, const wchar_t* claim_path, const char* expected, size_t expected_length,
                                char (&raw)[eu4_lab_1375::kMaxRequestBytes + 1], DWORD& length) {
    HANDLE file = CreateFileW(path, GENERIC_READ | DELETE, 0, nullptr, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) return GetLastError() == ERROR_FILE_NOT_FOUND ? InputState::absent : InputState::failed;
    LARGE_INTEGER size{};
    BY_HANDLE_FILE_INFORMATION info{};
    const bool shape = GetFileType(file) == FILE_TYPE_DISK && GetFileInformationByHandle(file, &info)
        && !(info.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY)) && info.nNumberOfLinks == 1
        && GetFileSizeEx(file, &size) && size.QuadPart > 0 && size.QuadPart <= static_cast<LONGLONG>(eu4_lab_1375::kMaxRequestBytes)
        && ReadFile(file, raw, static_cast<DWORD>(eu4_lab_1375::kMaxRequestBytes), &length, nullptr)
        && length == static_cast<DWORD>(size.QuadPart);
    bool valid = shape;
    if (expected) valid = valid && length == expected_length && memcmp(raw, expected, length) == 0;
    else {
        eu4_lab_1375::MailboxRequest parsed{};
        valid = valid && eu4_lab_1375::parse_request(raw, length, parsed)
            && parsed.pid == GetCurrentProcessId() && parsed.creation == process_created
            && parsed.sequence == last_sequence + 1 && parsed.sequence <= eu4_lab_1375::kMaxSequence;
        const auto now = GetTickCount64();
        valid = valid && parsed.expires > now && parsed.expires - now <= eu4_lab_1375::kMaxTtlMs;
    }
    if (valid) valid = create_durable_file(claim_path, raw, length);
    if (valid) {
        FILE_DISPOSITION_INFO disposition{}; disposition.DeleteFile = TRUE;
        valid = SetFileInformationByHandle(file, FileDispositionInfo, &disposition, sizeof(disposition)) != FALSE;
    }
    const bool closed = CloseHandle(file) != FALSE;
    return valid && closed ? InputState::consumed : InputState::failed;
}

static void run_phase(unsigned phase) {
    const wchar_t* paths[] = {request_file, preview_request_file, command_request_file};
    const wchar_t* claims[] = {L"phase-lifecycle.claim", L"phase-preview.claim", L"phase-command.claim"};
    const char* tokens[] = {"PAIR_SELFTEST_1375\n", "PAIR_PREVIEW_1375\n", "PAIR_COMMAND_1375\n"};
    if (marker_absent(paths[phase])) return;
    if (!observe_world(true, true)) { freeze("phase_requires_valid_paused_world"); return; }
    wchar_t claim[MAX_PATH]{};
    char raw[eu4_lab_1375::kMaxRequestBytes + 1]{};
    DWORD length = 0;
    if (!in_session_path(claim, claims[phase])) { freeze("phase_claim_path_failed"); return; }
    const InputState state = consume_input(paths[phase], claim, tokens[phase], strlen(tokens[phase]), raw, length);
    if (state != InputState::consumed) { if (state == InputState::failed) freeze("invalid_or_claimed_phase_marker"); return; }
    bool passed = false;
    if (phase == 0) {
        tested = true;
        log_line("{\"event\":\"pair_selftest_begin\",\"send_enabled\":false,\"submitted\":false}");
        passed = pair_selftest(game_base, log_line);
        selftest_passed = passed && !audit_failed && observe_world(true, false);
        log_line(selftest_passed ? "{\"event\":\"pair_selftest_complete\",\"passed\":true,\"submitted\":false}"
                                : "{\"event\":\"pair_selftest_complete\",\"passed\":false,\"submitted\":false}");
    } else if (phase == 1) {
        preview_tested = true;
        log_line("{\"event\":\"pair_preview_begin\",\"submitted\":false,\"send_enabled\":false}");
        passed = pair_preview(game_base, log_line);
        preview_passed = passed && !audit_failed && observe_world(true, false);
        log_line(preview_passed ? "{\"event\":\"pair_preview_complete\",\"passed\":true,\"submitted\":false}"
                               : "{\"event\":\"pair_preview_complete\",\"passed\":false,\"submitted\":false}");
    } else {
        command_tested = true;
        log_line("{\"event\":\"pair_command_begin\",\"submitted\":false,\"send_enabled\":false}");
        passed = pair_command_selftest(game_base, log_line);
        command_passed = passed && !audit_failed && observe_world(true, false);
        log_line(command_passed ? "{\"event\":\"pair_command_complete\",\"passed\":true,\"submitted\":false}"
                               : "{\"event\":\"pair_command_complete\",\"passed\":false,\"submitted\":false}");
    }
    last_phase_frame = InterlockedCompareExchange(&frames, 0, 0);
    const bool phase_passed = phase == 0 ? selftest_passed : (phase == 1 ? preview_passed : command_passed);
    if (!passed || !phase_passed || audit_failed || session_frozen) freeze("preflight_failed");
}

static void service_lease() {
    if (!lease_active || session_frozen || audit_failed) return;
    const auto now = GetTickCount64();
    const int64_t elapsed_date = static_cast<int64_t>(locked_date) - lease_start_date;
    if (now < lease_deadline && elapsed_date < lease_max_raw_date_delta) return;
    // No next mailbox request is processed while this lease exists. Its origin
    // sequence therefore remains current, and pause is authorized by that
    // operation's explicit, documented bounded-running contract.
    wchar_t claim[MAX_PATH]{};
    if (!sequence_path(claim, lease_operation.request.sequence, L"lease-pause.claim")) { freeze("lease_claim_path_failed"); return; }
    char line[1024]{};
    const int count = sprintf_s(line,
        "{\"purpose\":\"bounded_running_lease_pause\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"origin_sequence\":%llu,\"deadline_uptime_ms\":%llu,\"maximum_raw_date_delta\":%d,\"speed\":0,\"retry_allowed\":false}\n",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(lease_operation.request.sequence),
        static_cast<unsigned long long>(lease_deadline), lease_max_raw_date_delta);
    if (count <= 0 || !create_durable_file(claim, line, static_cast<DWORD>(count))) { freeze("lease_pause_claim_failed"); return; }
    lease_operation.durable_claim = true;
    lease_operation.operation_entered = true; // Original authorized speed operation already entered; TTL is not a retry timer.
    lease_operation.lease_pause = true;
    lease_operation.request.speed = 0;
    eu4_test_controls_1375::Host host{sizeof(host), eu4_test_controls_1375::kAbiVersion, window_thread, true,
        selftest_passed, controls_guard, request_logger, &lease_operation};
    const auto result = eu4_test_controls_1375::set_speed(0, host);
    lease_active = false; // One attempt only, including uncertainty or failure.
    if (result.freeze_session || result.exception_code || !result.audit_complete || !result.readback_matches || !result.after.paused)
        freeze("lease_pause_not_verified");
    sprintf_s(line,
        "{\"event\":\"lab_lease_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"reason\":%u,\"write_entered\":%s,\"callback_returned\":%s,\"paused_readback\":%s,\"readback_matches\":%s,\"session_frozen\":%s,\"retry_allowed\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), static_cast<unsigned>(result.reason),
        result.write_entered ? "true" : "false", result.callback_returned ? "true" : "false", result.after.paused ? "true" : "false",
        result.readback_matches ? "true" : "false", session_frozen ? "true" : "false");
    durable_log(line);
}

static void process_mailbox() {
    if (last_sequence >= eu4_lab_1375::kMaxSequence) { freeze("sequence_exhausted"); return; }
    wchar_t path[MAX_PATH]{}, claim[MAX_PATH]{};
    if (!sequence_path(path, last_sequence + 1, L"request") || !sequence_path(claim, last_sequence + 1, L"claim")) { freeze("request_path_failed"); return; }
    char raw[eu4_lab_1375::kMaxRequestBytes + 1]{};
    DWORD length = 0;
    const InputState state = consume_input(path, claim, nullptr, 0, raw, length);
    if (state == InputState::absent) return;
    if (state != InputState::consumed) { freeze("request_invalid_expired_or_already_claimed"); return; }
    ActiveRequest operation{};
    if (!eu4_lab_1375::parse_request(raw, length, operation.request)) { freeze("claimed_request_roundtrip_failed"); return; }
    operation.durable_claim = true;
    last_sequence = operation.request.sequence;
    char line[1024]{};
    sprintf_s(line, "{\"event\":\"lab_request_claimed\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"%s\",\"mode\":\"%s\",\"action\":\"%s\",\"actor\":\"%s\",\"target\":\"%s\",\"expires\":%llu,\"speed\":%u,\"durable_claim\":true,\"retry_allowed\":false}",
        GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence),
        operation.request.operation, operation.request.mode, operation.request.action, operation.request.actor, operation.request.target,
        static_cast<unsigned long long>(operation.request.expires), operation.request.speed);
    if (!durable_log(line)) return;
    if (!std::strcmp(operation.request.operation, "speed") && operation.request.speed > 0 && !running_speed_enabled) {
        sprintf_s(line, "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"speed\",\"speed\":%u,\"pre_dispatch_rejected\":true,\"reason\":\"running_speed_lease_not_enabled\",\"write_entered\":false,\"session_frozen\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), operation.request.speed);
        durable_log(line);
        return;
    }
    if (!std::strcmp(operation.request.operation, "pair")) {
        eu4_pair_1375::Request request{};
        if (!eu4_pair_1375::parse_action_id(operation.request.action, strlen(operation.request.action), &request.action)) { freeze("claimed_action_invalid"); return; }
        memcpy(request.actor, operation.request.actor, 4); memcpy(request.target, operation.request.target, 4);
        const auto mode = !std::strcmp(operation.request.mode, "submit") ? eu4_pair_1375::Mode::submit : eu4_pair_1375::Mode::legality_only;
        eu4_pair_1375::Host host{sizeof(host), eu4_pair_1375::kAbiVersion, window_thread, true,
            selftest_passed && preview_passed && command_passed, pair_guard, request_logger, &operation};
        const auto result = eu4_pair_1375::invoke(request, mode, host);
        any_dispatch_entered = any_dispatch_entered || result.submit_entered;
        if (result.freeze_session || result.ownership_uncertain || result.exception_code || !result.audit_complete) freeze("pair_core_uncertain_or_audit_failed");
        sprintf_s(line, "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"pair\",\"action\":\"%s\",\"status\":%u,\"reason\":%u,\"submit_entered\":%s,\"submit_returned\":%s,\"ownership_uncertain\":%s,\"session_frozen\":%s,\"applied_verified\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), operation.request.action,
            static_cast<unsigned>(result.status), static_cast<unsigned>(result.reason), result.submit_entered ? "true" : "false",
            result.submit_returned ? "true" : "false", result.ownership_uncertain ? "true" : "false", session_frozen ? "true" : "false");
    } else {
        if (operation.request.speed > 0) {
            lease_operation = operation;
            lease_deadline = GetTickCount64() + lease_duration_ms;
            lease_start_date = locked_date;
            sprintf_s(line,
                "{\"event\":\"lab_lease_armed\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"deadline_uptime_ms\":%llu,\"maximum_raw_date_delta\":%d,\"initial_raw_date\":%d,\"automatic_pause\":true,\"reliable_generation_verified\":false}",
                GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence),
                static_cast<unsigned long long>(lease_deadline), lease_max_raw_date_delta, lease_start_date);
            if (!durable_log(line)) return;
        }
        eu4_test_controls_1375::Host host{sizeof(host), eu4_test_controls_1375::kAbiVersion, window_thread, true,
            selftest_passed, controls_guard, request_logger, &operation};
        const auto result = eu4_test_controls_1375::set_speed(operation.request.speed, host);
        if (result.freeze_session || result.exception_code || !result.audit_complete) freeze("controls_uncertain_or_audit_failed");
        if (operation.request.speed > 0 && !session_frozen && result.readback_matches && !result.after.paused) lease_active = true;
        sprintf_s(line, "{\"event\":\"lab_request_complete\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"operation\":\"speed\",\"speed\":%u,\"reason\":%u,\"write_entered\":%s,\"callback_returned\":%s,\"readback_matches\":%s,\"session_frozen\":%s,\"applied_verified\":false,\"retry_allowed\":false}",
            GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), operation.request.speed,
            static_cast<unsigned>(result.reason), result.write_entered ? "true" : "false", result.callback_returned ? "true" : "false",
            result.readback_matches ? "true" : "false", session_frozen ? "true" : "false");
    }
    durable_log(line);
}

extern "C" void research_frame_tick() {
    if (!InterlockedCompareExchange(&research_enabled, 0, 0)) return;
    const DWORD thread = GetCurrentThreadId();
    if (thread != window_thread) InterlockedExchange(&thread_changed, 1);
    if (InterlockedCompareExchange(&active, 1, 0)) return;
    __try {
        if (InterlockedCompareExchange(&thread_changed, 0, 0)) freeze("frame_thread_changed");
        const LONG count = InterlockedIncrement(&frames);
        eu4_test_controls_1375::Snapshot observed{};
        const bool ready = observe_world(false, false, &observed);
        const ULONGLONG now = GetTickCount64();
        if (now - last_log >= 1000 && !audit_failed) {
            last_log = now;
            char line[1536]{};
            sprintf_s(line, "{\"event\":\"research_frame\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"thread\":%lu,\"uptime_ms\":%llu,\"frames\":%ld,\"thread_changed\":%s,\"world_ready\":%s,\"world_changed\":%s,\"session_frozen\":%s,\"world_cookie\":\"0x%llx\",\"player_handle\":\"0x%016llx\",\"raw_date\":%d,\"paused\":%s,\"native_speed_index\":%d,\"lifecycle_passed\":%s,\"preview_passed\":%s,\"command_passed\":%s,\"last_sequence\":%llu,\"mailbox_ready\":%s,\"running_speed_enabled\":%s,\"lease_active\":%s,\"lease_deadline_uptime_ms\":%llu,\"send_enabled\":%s}",
                GetCurrentProcessId(), static_cast<unsigned long long>(process_created), thread, static_cast<unsigned long long>(now), count,
                InterlockedCompareExchange(&thread_changed, 0, 0) ? "true" : "false", ready ? "true" : "false", world_changed ? "true" : "false",
                session_frozen ? "true" : "false", static_cast<unsigned long long>(observed.game_cookie), static_cast<unsigned long long>(observed.player_handle),
                observed.raw_date, observed.paused ? "true" : "false", observed.native_speed_index, selftest_passed ? "true" : "false",
                preview_passed ? "true" : "false", command_passed ? "true" : "false", static_cast<unsigned long long>(last_sequence),
                ready && world_locked && selftest_passed && preview_passed && command_passed && !session_frozen && !lease_active ? "true" : "false",
                running_speed_enabled ? "true" : "false", lease_active ? "true" : "false", static_cast<unsigned long long>(lease_deadline), any_dispatch_entered ? "true" : "false");
            if (durable_log(line) && ready && !session_frozen) last_health_frame = count;
        }
        if (!session_frozen && !audit_failed && ready && count >= 100) {
            // Exactly one phase or mailbox request per callback. No polling wait.
            if (lease_active) service_lease();
            else if (!tested) run_phase(0);
            else if (selftest_passed && !preview_tested && last_health_frame > last_phase_frame) run_phase(1);
            else if (preview_passed && !command_tested && last_health_frame > last_phase_frame) run_phase(2);
            else if (selftest_passed && preview_passed && command_passed && last_health_frame > last_phase_frame) process_mailbox();
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        const DWORD exception = GetExceptionCode();
        session_frozen = true;
        if (!audit_failed) {
            char line[512]{};
            sprintf_s(line, "{\"event\":\"lab_host_exception\",\"pid\":%lu,\"process_creation_filetime\":\"%016llx\",\"sequence\":%llu,\"exception\":%lu,\"session_frozen\":true,\"retry_allowed\":false}",
                GetCurrentProcessId(), static_cast<unsigned long long>(process_created), static_cast<unsigned long long>(last_sequence), exception);
            durable_log(line);
        }
        // Do not attempt any native cleanup or continue a phase after a fault.
    }
    InterlockedExchange(&active, 0);
}

static bool create_private_session(const wchar_t* dll_directory) {
    wchar_t folder[MAX_PATH]{};
    if (swprintf_s(folder, L"%ssession-%lu-%016llx", dll_directory, GetCurrentProcessId(), static_cast<unsigned long long>(process_created)) <= 0) return false;
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    alignas(TOKEN_USER) unsigned char information[4096]{};
    DWORD needed = 0;
    const bool queried = GetTokenInformation(token, TokenUser, information, sizeof(information), &needed) != FALSE;
    CloseHandle(token);
    if (!queried || needed > sizeof(information)) return false;
    LPWSTR sid = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(information)->User.Sid, &sid)) return false;
    wchar_t sddl[512]{};
    const int count = swprintf_s(sddl, L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;%s)", sid);
    LocalFree(sid);
    if (count <= 0) return false;
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, SDDL_REVISION_1, &descriptor, nullptr)) return false;
    SECURITY_ATTRIBUTES attributes{sizeof(attributes), descriptor, FALSE};
    const bool created = CreateDirectoryW(folder, &attributes) != FALSE;
    LocalFree(descriptor);
    if (!created) return false; // Existing directories/claims can never be rearmed.
    if (wcscpy_s(session_directory, folder) || wcscat_s(session_directory, L"\\")) return false;
    return true;
}

// Copied audited frame installation/thread suspension logic in its own v6
// source. v4/v5 source files and binaries are never edited or overwritten.
#include "research-lab-bootstrap-1375.inc"
