// Compile-only. No DLL entry, process writes, hooks, files, request transport,
// arbitrary console text, run-script invocation, yesman or direct state edits.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "test-fixture-v9-1375.h"
#include <cstdio>
#include <cstring>

namespace eu4_test_fixture_1375 {
namespace {
constexpr std::uintptr_t kCallback = 0xe5bb30;
constexpr std::uintptr_t kDestructor = 0x95660;
constexpr std::uintptr_t kCallbackFlag = 0x1fd10c4;
constexpr std::uint64_t kFrance = 0x0100007a00415246ULL;
constexpr std::uint64_t kNavarra = 0x010000bc0056414eULL;
volatile LONG g_active = 0;
volatile LONG g_frozen = 0;
struct NativeString { unsigned char storage[16]; std::uint64_t length, capacity; };
struct NativeVector { NativeString* begin; NativeString* end; NativeString* capacity; };
struct NativeResult { unsigned char success; unsigned char padding[7]; NativeString message; };
static_assert(sizeof(NativeString) == 32 && alignof(NativeString) == 8, "String32 ABI");
static_assert(sizeof(NativeVector) == 24, "Vector24 ABI");
static_assert(sizeof(NativeResult) == 40 && offsetof(NativeResult, message) == 8, "Result40 ABI");
using Callback = NativeResult* (__fastcall*)(NativeResult*, const NativeVector*);
using Destructor = void (__fastcall*)(NativeString*);
struct Identity { std::uintptr_t database, array, france; };
struct Pin { std::uintptr_t rva; const char* bytes; };
constexpr Pin kPins[] = {
    {kCallback, "48895c24085556574154415541564157488dac2450feffff4881ecb00200004c"},
    {0xe42b00, "4883ec484c8b01488b4108492bc048c1f8053bc20f8e4a0100008bd248c1e205"},
    {0x6ee1d0, "40534883ec20488bd9e8f26e010184c0741848837b1810488bcb7203488b0be8"},
    {kDestructor, "40534883ec20488b5118488bd94883fa10722c488b0948ffc24881fa00100000"},
    // Layout evidence only: none of these methods is called by the guard.
    {0xa68d90, "488b11488b411048c1e82098488b8a800000004c63828c00000049c1e0044c03"},
    {0xa675b0, "48895c24185556574154415541564157488d6c24a04881ec60010000488bf144"},
    {0x2f1620, "48895c241844884c242048895424105556574154415541564157488d6c24d948"},
};
template <typename T> T read(std::uintptr_t p) {
    T value{};
    std::memcpy(&value, reinterpret_cast<const void*>(p), sizeof(value));
    return value;
}
bool address(std::uintptr_t p) { return p >= 0x10000 && p < 0x0000800000000000ULL; }
bool pointer(std::uintptr_t p) { return address(p) && p % 8 == 0; }
unsigned nibble(char c) { return c <= '9' ? static_cast<unsigned>(c - '0') : static_cast<unsigned>(c - 'a' + 10); }
bool prefix(std::uintptr_t p, const char* hex) {
    for (std::size_t i = 0; hex[2 * i]; ++i)
        if (!hex[2 * i + 1] || read<unsigned char>(p + i) != ((nibble(hex[2 * i]) << 4) | nibble(hex[2 * i + 1]))) return false;
    return true;
}
bool image(std::uintptr_t module) {
    if (!module) return false;
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(module + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || nt->FileHeader.TimeDateStamp != 0x66fe6ab9 || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC
        || nt->OptionalHeader.SizeOfImage != 0x25e0000) return false;
    for (const auto& pin : kPins) if (!prefix(module + pin.rva, pin.bytes)) return false;
    return read<std::uintptr_t>(module + 0x1fc3638) == module + kCallback
        && read<std::uintptr_t>(module + 0x1fc3608) == module + 0x1cc1f50
        && std::memcmp(reinterpret_cast<const void*>(module + 0x1cc1f50), "event", 6) == 0;
}
bool world(std::uintptr_t module, Snapshot& state, Identity& id, std::uint32_t& fault) {
    if (!eu4_test_controls_1375::observe(state, fault)) return false;
    if (!state.paused || state.native_multiplayer_classifier || state.world_reset_active
        || state.load_source_present || state.player_handle != kFrance) return false;
    id.database = read<std::uintptr_t>(module + 0x233d8d0);
    if (!pointer(id.database)) return false;
    id.array = read<std::uintptr_t>(id.database + 0x118);
    if (!pointer(id.array)) return false;
    id.france = read<std::uintptr_t>(id.array + 122 * 8);
    return pointer(id.france) && read<std::uint64_t>(id.france + 0x20) == kFrance
        && read<std::uintptr_t>(module + 0x233fe78) == state.game_cookie;
}
bool same(const Snapshot& a, const Snapshot& b, const Identity& x, const Identity& y) {
    return a.game_cookie == b.game_cookie && a.server_cookie == b.server_cookie
        && a.pause_manager_cookie == b.pause_manager_cookie && a.player_handle == b.player_handle
        && a.raw_date == b.raw_date && a.native_speed_index == b.native_speed_index
        && a.paused == b.paused && a.manual_pause == b.manual_pause
        && x.database == y.database && x.array == y.array && x.france == y.france;
}
struct BaselineSide {
    std::uintptr_t records, record, root, array;
    std::uint32_t count;
    unsigned char truce_flags;
};
struct Baseline { std::uintptr_t navarra; std::uint64_t overlord; BaselineSide outgoing, incoming; };
bool no_alliance_or_truce(std::uintptr_t owner, std::uint64_t other, BaselineSide& state) {
    // a68d90 reads the alliance index at root+80/+8c, in 16-byte entries;
    // a675b0 maintains active-truce bit0 at relation record+45.
    const auto records = read<std::uintptr_t>(owner + 0x1510);
    if (!pointer(records)) return false;
    const auto slot = static_cast<std::uint32_t>((other >> 32) & 0xffff);
    const auto record = records + static_cast<std::uintptr_t>(slot) * 0x48;
    const auto root = read<std::uintptr_t>(record);
    const auto truce_flags = read<unsigned char>(record + 0x45);
    if (!pointer(root) || read<std::uint64_t>(record + 0x10) != other
        || (truce_flags & 1) != 0) return false;
    const auto array = read<std::uintptr_t>(root + 0x80);
    const auto count = read<std::uint32_t>(root + 0x8c);
    if (count > 4096 || (array != 0 && !pointer(array)) || (count != 0 && !array)) return false;
    for (std::uint32_t i = 0; i < count; ++i) {
        const auto item = array + static_cast<std::uintptr_t>(i) * 0x10;
        const auto indexed_slot = read<std::uint32_t>(item);
        if (indexed_slot >= 4096 || indexed_slot == slot
            || !pointer(read<std::uintptr_t>(item + 8))) return false;
    }
    state = {records, record, root, array, count, truce_flags};
    return true;
}
bool fixture_baseline(const Identity& id, Baseline& state) {
    // Fixed NAV identity only. Do not infer the loaded save or SP provenance.
    const auto navarra = read<std::uintptr_t>(id.array + 188 * 8);
    if (!pointer(navarra) || read<std::uint64_t>(navarra + 0x20) != kNavarra) return false;
    state.navarra = navarra; state.overlord = read<std::uint64_t>(navarra + 0x18f0);
    return (state.overlord >> 56) == 0 && no_alliance_or_truce(id.france, kNavarra, state.outgoing)
        && no_alliance_or_truce(navarra, kFrance, state.incoming);
}
bool same_side(const BaselineSide& a, const BaselineSide& b) {
    return a.records == b.records && a.record == b.record && a.root == b.root && a.array == b.array
        && a.count == b.count && a.truce_flags == b.truce_flags;
}
bool same_baseline(const Baseline& a, const Baseline& b) {
    return a.navarra == b.navarra && a.overlord == b.overlord
        && same_side(a.outgoing, b.outgoing) && same_side(a.incoming, b.incoming);
}
bool guard(const Host& host, Operation operation, GuardPoint point, const Snapshot& observed) {
    GuardInput input{point, operation, observed};
    return GetCurrentThreadId() == host.expected_game_thread && host.guard(host.user, &input);
}
bool string_contract(const NativeString& s) {
    if (s.length > 4096 || s.length > s.capacity || s.capacity > 8191) return false;
    std::uintptr_t data = reinterpret_cast<std::uintptr_t>(s.storage);
    if (s.capacity >= 16) std::memcpy(&data, s.storage, sizeof(data));
    else if (s.capacity != 15) return false;
    if (!address(data)) return false;
    for (std::uint64_t i = 0; i < s.length; ++i)
        if (read<unsigned char>(data + static_cast<std::uintptr_t>(i)) == 0) return false;
    return read<unsigned char>(data + static_cast<std::uintptr_t>(s.length)) == 0;
}
const char* yes(bool value) { return value ? "true" : "false"; }
const char* event_name(Operation operation) { return operation == Operation::enable ? "llmt.1" : "llmt.2"; }
bool digest_copy(const char* source, char (&out)[65]) {
    if (!source) return false;
    for (unsigned i = 0; i < 64; ++i) {
        const char c = source[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
        out[i] = c;
    }
    return source[64] == 0;
}
bool audit(const Host& host, const Result& r, const char* event, const char* digest) {
    char record[1600]{};
    const int n = std::snprintf(record, sizeof(record),
        "{\"event\":\"%s\",\"thread_id\":%lu,\"fixture_event\":\"%s\",\"target\":\"FRA\","
        "\"fixture_profile_sha256\":\"%s\",\"reason\":%u,\"before_date\":%d,\"after_date\":%d,"
        "\"native_invoked\":%s,\"callback_returned\":%s,\"callback_success\":%s,"
        "\"arguments_unchanged\":%s,\"result_destroyed\":%s,\"world_identity_unchanged\":%s,"
        "\"callback_flag_restored\":%s,\"exception_code\":%lu,\"freeze_session\":%s,"
        "\"retry_allowed\":false,\"fixture_effect_verified\":false,\"diplomacy_submitted\":false}",
        event, static_cast<unsigned long>(GetCurrentThreadId()), event_name(r.operation), digest,
        static_cast<unsigned>(r.reason), r.before.raw_date, r.after.raw_date, yes(r.native_invoked),
        yes(r.callback_returned), yes(r.callback_success), yes(r.arguments_unchanged), yes(r.result_destroyed),
        yes(r.world_identity_unchanged), yes(r.callback_flag_restored), static_cast<unsigned long>(r.exception_code), yes(r.freeze_session));
    return n > 0 && static_cast<std::size_t>(n) < sizeof(record)
        && host.log(host.user, record, static_cast<std::size_t>(n));
}
void execute(Operation operation, const Host& host, Result& r, char (&digest)[65]) {
    const auto module = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    NativeString arguments[2]{};
    std::memcpy(arguments[0].storage, event_name(operation), 7);
    arguments[0].length = 6; arguments[0].capacity = 15;
    std::memcpy(arguments[1].storage, "FRA", 4);
    arguments[1].length = 3; arguments[1].capacity = 15;
    NativeString original_arguments[2]{};
    std::memcpy(original_arguments, arguments, sizeof(arguments));
    NativeVector vector{arguments, arguments + 2, arguments + 2};
    NativeResult native{};
    Identity original{}, fresh_id{};
    Baseline original_baseline{}, fresh_baseline{};
    Snapshot fresh{};
    __try {
        do {
            if (!digest_copy(host.fixture_profile_sha256, digest)) { r.reason = Reason::host_contract; break; }
            if (!image(module)) { r.reason = Reason::image_pin; break; }
            if (!world(module, r.before, original, r.exception_code)) { r.reason = Reason::wrong_world; break; }
            if (operation == Operation::enable && !fixture_baseline(original, original_baseline)) { r.reason = Reason::wrong_world; break; }
            const auto flag_before = read<unsigned char>(module + kCallbackFlag);
            if (!guard(host, operation, GuardPoint::before_call, r.before)) { r.reason = Reason::guard_rejected; break; }
            if (!audit(host, r, "test_fixture_begin", digest)) { r.reason = Reason::audit_failed; r.freeze_session = true; break; }
            if (!world(module, fresh, fresh_id, r.exception_code) || !same(r.before, fresh, original, fresh_id)
                || read<unsigned char>(module + kCallbackFlag) != flag_before
                || !guard(host, operation, GuardPoint::before_call, fresh)) { r.reason = Reason::guard_rejected; break; }
            if (operation == Operation::enable && (!fixture_baseline(fresh_id, fresh_baseline)
                || !same_baseline(original_baseline, fresh_baseline))) { r.reason = Reason::guard_rejected; break; }
            // Unique flushed host claim and successful persistent begin precede
            // the only event invocation. Arguments remain local SSO objects.
            r.native_invoked = true;
            NativeResult* returned = reinterpret_cast<Callback>(module + kCallback)(&native, &vector);
            r.callback_returned = true;
            if (returned != &native || native.success > 1) { r.reason = Reason::callback_contract; break; }
            r.callback_success = native.success != 0;
            r.arguments_unchanged = vector.begin == arguments && vector.end == arguments + 2
                && vector.capacity == arguments + 2 && std::memcmp(arguments, original_arguments, sizeof(arguments)) == 0;
            if (!r.arguments_unchanged) { r.reason = Reason::input_modified; break; }
            r.callback_flag_restored = read<unsigned char>(module + kCallbackFlag) == flag_before;
            if (!r.callback_flag_restored) { r.reason = Reason::callback_flag_changed; break; }
            if (!string_contract(native.message)) { r.reason = Reason::result_string_contract; break; }
            if (!world(module, r.after, fresh_id, r.exception_code)) { r.reason = Reason::unreadable_state; break; }
            r.world_identity_unchanged = same(r.before, r.after, original, fresh_id);
            if (!r.world_identity_unchanged || !guard(host, operation, GuardPoint::before_result_destroy, r.after)) {
                r.reason = Reason::guard_rejected; break;
            }
            // Only this output string is engine-owned. Never destroy either
            // argument/vector; normal native callback has not taken ownership.
            reinterpret_cast<Destructor>(module + kDestructor)(&native.message);
            r.result_destroyed = true;
            if (!world(module, fresh, fresh_id, r.exception_code) || !same(r.after, fresh, original, fresh_id)
                || !guard(host, operation, GuardPoint::after_call, fresh)) { r.reason = Reason::guard_rejected; break; }
            if (!r.callback_success) r.reason = Reason::callback_rejected;
        } while (false);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        r.exception_code = GetExceptionCode(); r.reason = Reason::native_exception; r.freeze_session = true;
        // Do not repair the callback's temporary global flag, destroy uncertain
        // output, invoke another event or call any other native function.
    }
    if (r.exception_code || (r.native_invoked && r.reason != Reason::none)) r.freeze_session = true;
}
} // namespace

Result invoke(Operation operation, const Host& host) {
    Result r{}; r.operation = operation;
    if (operation != Operation::enable && operation != Operation::disable) { r.reason = Reason::invalid_request; return r; }
    if (host.struct_size != sizeof(Host) || host.abi_version != kAbiVersion || !host.expected_game_thread
        || !host.durable_attempt_claimed || !host.full_sha256_verified || !host.fixture_definition_files_verified
        || !host.fixture_profile_sha256 || !host.guard || !host.log) { r.reason = Reason::host_contract; return r; }
    if (GetCurrentThreadId() != host.expected_game_thread) { r.reason = Reason::wrong_thread; return r; }
    if (InterlockedCompareExchange(&g_frozen, 0, 0)) { r.reason = Reason::frozen; r.freeze_session = true; return r; }
    if (InterlockedCompareExchange(&g_active, 1, 0)) { r.reason = Reason::busy; return r; }
    char digest[65]{};
    execute(operation, host, r, digest);
    __try {
        // Do not interpolate a partial/unvalidated host string into JSON.
        if (!digest_copy(digest, digest)) { r.freeze_session = true; r.reason = Reason::host_contract; }
        else {
            r.audit_complete = audit(host, r, "test_fixture_complete", digest);
            if (!r.audit_complete) { r.reason = Reason::audit_failed; r.freeze_session = true; }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        r.exception_code = GetExceptionCode(); r.reason = Reason::audit_failed; r.freeze_session = true;
    }
    if (r.freeze_session) InterlockedExchange(&g_frozen, 1);
    InterlockedExchange(&g_active, 0);
    return r;
}
} // namespace eu4_test_fixture_1375
