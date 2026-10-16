// Compile-only research module. No DllMain, hooks, files, mailbox, save call,
// console dispatcher, script runner or arbitrary text argument surface.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "test-controls-1375.h"
#include <cstdio>
#include <cstring>

namespace eu4_test_controls_1375 {
namespace {
constexpr std::uintptr_t kGame = 0x233fe78;
constexpr std::uintptr_t kServerVtable = 0x1cb8460;
constexpr std::uintptr_t kCallback = 0xe913a0;
constexpr std::uintptr_t kStringDestructor = 0x95660;
volatile LONG g_active = 0;
volatile LONG g_frozen = 0;

struct NativeString {
    unsigned char storage[16];
    std::uint64_t length;
    std::uint64_t capacity;
};
struct NativeVector { NativeString* begin; NativeString* end; NativeString* capacity; };
struct NativeResult { unsigned char success; unsigned char padding[7]; NativeString message; };
static_assert(sizeof(NativeString) == 32 && alignof(NativeString) == 8, "String32 ABI");
static_assert(sizeof(NativeVector) == 24, "vector ABI");
static_assert(sizeof(NativeResult) == 40 && offsetof(NativeResult, message) == 8, "result ABI");
using Callback = NativeResult* (__fastcall*)(NativeResult*, const NativeVector*);
using StringDestructor = void (__fastcall*)(NativeString*);

struct Pin { std::uintptr_t rva; const char* bytes; };
constexpr Pin kPins[] = {
    {kCallback, "48895c241048896c2418488974242048894c240857415641574881ec90000000"},
    {0x7579f0, "4881ec8800000041b804000000413bd0440f4ec233c04585c0410f49c0898108"},
    {0x7e01b0, "40534883ec2080794800488bd9740e33c083f8020f95c04883c4205bc3488b49"},
    {0x7e0250, "40534883ec2080794800488bd9755c488b4950e8a8a7f0ff84c0750f488b4308"},
    {kStringDestructor, "40534883ec20488b5118488bd94883fa10722c488b0948ffc24881fa00100000"},
    {0x6eaa10, "48895c2408574883ec20488b01488bf9ff901803000084c07456488b07488bcf"},
    {0x811aa0, "488b8130030000488b8070030000c3"},
    {0x8024d0, "488b8118040000c3"},
    {0x80ff80, "0fb681f1190000c3"},
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
    for (std::size_t i = 0; hex[2 * i]; ++i) {
        if (!hex[2 * i + 1] || read<unsigned char>(p + i) != ((nibble(hex[2 * i]) << 4) | nibble(hex[2 * i + 1]))) return false;
    }
    return true;
}
bool image(std::uintptr_t module) {
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    if (!module || dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(module + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || nt->FileHeader.TimeDateStamp != 0x66fe6ab9 || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC
        || nt->OptionalHeader.SizeOfImage != 0x25e0000) return false;
    for (const auto& pin : kPins) if (!prefix(module + pin.rva, pin.bytes)) return false;
    return read<std::uintptr_t>(module + 0x1fce998) == module + kCallback
        && read<std::uintptr_t>(module + kServerVtable + 0x80) == module + 0x811aa0
        && read<std::uintptr_t>(module + kServerVtable + 0x100) == module + 0x8024d0
        && read<std::uintptr_t>(module + kServerVtable + 0x318) == module + 0x80ff80;
}

// Reproduces only the reviewed predicate, never claims strict offline identity.
bool multiplayer(std::uintptr_t game, std::uintptr_t server, bool& value) {
    const auto gate = read<unsigned char>(server + 0x19f1);
    if (gate > 1) return false;
    value = false;
    if (!gate) return true;
    const auto holder = read<std::uintptr_t>(server + 0x330);
    if (!pointer(holder)) return false;
    const auto context = read<std::uintptr_t>(holder + 0x370);
    if (!pointer(context)) return false;
    const auto a = read<unsigned char>(context + 0x54), b = read<unsigned char>(context + 0x55);
    if (a > 1 || b > 1) return false;
    if (!a && !b) { value = true; return true; }
    const auto local_id = read<std::uint32_t>(context + 0x8c);
    auto node = read<std::uintptr_t>(game + 0xa50);
    std::uintptr_t seen[256]{};
    for (unsigned n = 0; node; ++n) {
        if (n >= 256 || !pointer(node)) return false;
        for (unsigned i = 0; i < n; ++i) if (seen[i] == node) return false;
        seen[n] = node;
        if (read<std::uint32_t>(node + 0x18) != local_id) value = true;
        node = read<std::uintptr_t>(node + 0x60);
    }
    return true;
}
bool snapshot(std::uintptr_t module, Snapshot& out) {
    const auto game = read<std::uintptr_t>(module + kGame);
    if (!pointer(game)) return false;
    const auto server = read<std::uintptr_t>(game + 0x1e00);
    if (!pointer(server) || read<std::uintptr_t>(server) != module + kServerVtable) return false;
    const auto manager = read<std::uintptr_t>(server + 0x418);
    if (!pointer(manager) || read<std::uintptr_t>(manager + 0x50) != server) return false;
    const auto manual = read<unsigned char>(manager + 0x48);
    if (manual > 1) return false;
    const auto begin = read<std::uintptr_t>(manager), end = read<std::uintptr_t>(manager + 8);
    if ((begin == 0) != (end == 0) || (begin && (!pointer(begin) || !pointer(end)))
        || end < begin || (end - begin) % 8 || (end - begin) / 8 > 256) return false;
    bool mp = false;
    if (!multiplayer(game, server, mp)) return false;
    out.game_cookie = game;
    out.server_cookie = server;
    out.pause_manager_cookie = manager;
    out.player_handle = read<std::uint64_t>(game + 0x1e60);
    out.raw_date = read<std::int32_t>(game + 0x1dd0);
    out.native_speed_index = read<std::int32_t>(game + 0x1e08);
    out.manual_pause = manual != 0;
    out.native_multiplayer_classifier = mp;
    const auto resetting = read<unsigned char>(game + 0x7485);
    const auto load_source = read<std::uintptr_t>(game + 0x74c8);
    if (resetting > 1 || (load_source && !pointer(load_source))) return false;
    out.world_reset_active = resetting != 0;
    out.load_source_present = load_source != 0;
    out.paused = out.manual_pause || (!mp && begin != end);
    return out.native_speed_index >= 0 && out.native_speed_index <= 4 && out.raw_date > 0
        && (out.player_handle >> 56) != 0;
}
bool same_identity(const Snapshot& a, const Snapshot& b) {
    return a.game_cookie == b.game_cookie && a.server_cookie == b.server_cookie
        && a.pause_manager_cookie == b.pause_manager_cookie && a.player_handle == b.player_handle
        && a.raw_date == b.raw_date;
}
bool string_contract(const NativeString& s) {
    if (s.length > 256 || s.length > s.capacity || s.capacity > 4096) return false;
    std::uintptr_t data = reinterpret_cast<std::uintptr_t>(s.storage);
    if (s.capacity >= 16) std::memcpy(&data, s.storage, sizeof(data));
    else if (s.capacity != 15) return false;
    return address(data) && read<unsigned char>(data + static_cast<std::uintptr_t>(s.length)) == 0;
}
bool guard(const Host& host, unsigned speed, GuardPoint point, const Snapshot& state) {
    GuardInput input{point, speed, state};
    return GetCurrentThreadId() == host.expected_game_thread && host.guard(host.user, &input);
}
const char* yes(bool x) { return x ? "true" : "false"; }
bool audit(const Host& host, const Result& r, const char* event) {
    char record[1200]{};
    const int n = std::snprintf(record, sizeof(record),
        "{\"event\":\"%s\",\"thread_id\":%lu,\"requested_speed\":%u,\"reason\":%u,"
        "\"before_date\":%d,\"before_native_index\":%d,\"before_paused\":%s,"
        "\"write_entered\":%s,\"callback_returned\":%s,\"callback_success\":%s,"
        "\"result_destroyed\":%s,\"readback_observed\":%s,\"after_date\":%d,"
        "\"after_native_index\":%d,\"after_paused\":%s,\"readback_matches\":%s,"
        "\"exception_code\":%lu,\"freeze_session\":%s,\"retry_allowed\":false,\"diplomacy_submitted\":false}",
        event, static_cast<unsigned long>(GetCurrentThreadId()), r.requested_speed, static_cast<unsigned>(r.reason),
        r.before.raw_date, r.before.native_speed_index, yes(r.before.paused), yes(r.write_entered),
        yes(r.callback_returned), yes(r.callback_success), yes(r.result_destroyed), yes(r.readback_observed),
        r.after.raw_date, r.after.native_speed_index, yes(r.after.paused), yes(r.readback_matches),
        static_cast<unsigned long>(r.exception_code), yes(r.freeze_session));
    return n > 0 && static_cast<std::size_t>(n) < sizeof(record)
        && host.log(host.user, record, static_cast<std::size_t>(n));
}

void execute(unsigned speed, const Host& host, Result& r) {
    const auto module = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    NativeString argument{};
    argument.storage[0] = static_cast<unsigned char>('0' + speed);
    argument.length = 1;
    argument.capacity = 15;
    NativeVector arguments{&argument, &argument + 1, &argument + 1};
    NativeResult native{};
    __try {
        do {
            if (!image(module)) { r.reason = Reason::image_pin; break; }
            if (!snapshot(module, r.before)) { r.reason = Reason::unreadable_state; break; }
            if (!guard(host, speed, GuardPoint::before_call, r.before)) { r.reason = Reason::guard_rejected; break; }
            if (!audit(host, r, "test_speed_begin")) { r.reason = Reason::audit_failed; r.freeze_session = true; break; }
            Snapshot fresh{};
            if (!snapshot(module, fresh) || !same_identity(r.before, fresh)
                || !guard(host, speed, GuardPoint::before_call, fresh)) { r.reason = Reason::guard_rejected; break; }
            // The persisted intent and host claim precede this first native call.
            r.write_entered = true;
            NativeResult* returned = reinterpret_cast<Callback>(module + kCallback)(&native, &arguments);
            r.callback_returned = true;
            if (returned != &native || native.success > 1) { r.reason = Reason::callback_contract; break; }
            r.callback_success = native.success != 0;
            if (!string_contract(native.message)) { r.reason = Reason::result_string_contract; break; }
            reinterpret_cast<StringDestructor>(module + kStringDestructor)(&native.message);
            r.result_destroyed = true;
            if (!snapshot(module, r.after)) { r.reason = Reason::unreadable_state; break; }
            r.readback_observed = true;
            const auto expected_index = static_cast<std::int32_t>(speed > 4 ? 4 : speed);
            r.readback_matches = r.callback_success && same_identity(r.before, r.after)
                && r.after.native_speed_index == expected_index && r.after.paused == (speed == 0);
            if (!r.readback_matches) { r.reason = Reason::readback_mismatch; break; }
            if (!guard(host, speed, GuardPoint::after_call, r.after)) { r.reason = Reason::guard_rejected; break; }
        } while (false);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        r.exception_code = GetExceptionCode();
        r.reason = Reason::native_exception;
        r.freeze_session = true;
        // Do not run a destructor or any second native call after an exception.
    }
    if (r.write_entered && r.reason != Reason::none) r.freeze_session = true;
}
} // namespace

Result set_speed(unsigned speed, const Host& host) {
    Result r{};
    r.requested_speed = speed;
    if (speed > 5) { r.reason = Reason::invalid_request; return r; }
    if (host.struct_size != sizeof(Host) || host.abi_version != kAbiVersion || !host.durable_attempt_claimed
        || !host.full_sha256_verified || !host.expected_game_thread || !host.guard || !host.log) {
        r.reason = Reason::host_contract; return r;
    }
    if (GetCurrentThreadId() != host.expected_game_thread) { r.reason = Reason::wrong_thread; return r; }
    if (InterlockedCompareExchange(&g_frozen, 0, 0)) { r.reason = Reason::frozen; r.freeze_session = true; return r; }
    if (InterlockedCompareExchange(&g_active, 1, 0)) { r.reason = Reason::busy; return r; }
    execute(speed, host, r);
    __try {
        r.audit_complete = audit(host, r, "test_speed_complete");
        if (!r.audit_complete) { r.reason = Reason::audit_failed; r.freeze_session = true; }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        r.exception_code = GetExceptionCode(); r.reason = Reason::audit_failed; r.freeze_session = true;
    }
    if (r.freeze_session) InterlockedExchange(&g_frozen, 1);
    InterlockedExchange(&g_active, 0);
    return r;
}
bool observe(Snapshot& output, std::uint32_t& fault_code) {
    output = {};
    fault_code = 0;
    __try {
        const auto module = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
        return image(module) && snapshot(module, output);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        fault_code = GetExceptionCode();
        output = {};
        return false;
    }
}
} // namespace eu4_test_controls_1375
