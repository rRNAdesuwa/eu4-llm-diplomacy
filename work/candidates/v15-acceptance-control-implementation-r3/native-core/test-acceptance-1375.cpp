// Isolated candidate. No entry point, hooks, files, mailbox, arbitrary console
// strings or direct game-state writes. Only fixed e50180 and normal 95660 calls.
// Static lineage: offered-fleet-ai-response-1375/report.json SHA
// f7eeae58d29902ca3999c7bd00e47dacde43e64c72ca215a6df47417e015eee5.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "test-acceptance-1375.h"
#include <cstdio>
#include <cstring>

namespace eu4_test_acceptance_1375 {
namespace {
constexpr std::uintptr_t kCallback = 0xe50180;
constexpr std::uintptr_t kDestructor = 0x95660;
constexpr std::uint64_t kFrance = 0x0100007a00415246ULL;
volatile LONG g_active = 0;
volatile LONG g_frozen = 0;

struct NativeString { unsigned char storage[16]; std::uint64_t length, capacity; };
struct NativeVector { NativeString* begin; NativeString* end; NativeString* capacity; };
struct NativeResult { unsigned char success; unsigned char padding[7]; NativeString message; };
static_assert(sizeof(NativeString) == 32 && alignof(NativeString) == 8, "String32 ABI");
static_assert(offsetof(NativeString, length) == 16 && offsetof(NativeString, capacity) == 24, "String32 fields");
static_assert(sizeof(NativeVector) == 24 && alignof(NativeVector) == 8, "Vector24 ABI");
static_assert(offsetof(NativeVector, end) == 8 && offsetof(NativeVector, capacity) == 16, "Vector24 fields");
static_assert(sizeof(NativeResult) == 40 && alignof(NativeResult) == 8, "Result40 ABI");
static_assert(offsetof(NativeResult, message) == 8, "Result40 message");
using Callback = NativeResult* (__fastcall*)(NativeResult*, const NativeVector*);
using Destructor = void (__fastcall*)(NativeString*);
struct Identity {
    std::uintptr_t database, array, france;
    std::int32_t country_count;
    std::uint64_t effective_player;
    unsigned char selector, alternate_selector;
};
struct Pin { std::uintptr_t rva; const char* bytes; };
constexpr Pin kPins[] = {
    // Complete bounded handler and normal string destructor, including their
    // error tails; not merely a shared prologue. No unproved handler variant.
    {kCallback,
     "48895c241048896c241848894c2408565741564883ec704c8bf133f689742420408831488d79084889374889771048c747180f000000408837c744242001000000"
     "488b4208482b0248c1f80585c00f8eda000000408831488b5f184883fb227227488b1f48c7471022000000448d4622488d1529aaed00488bcbe85155be0040887322e9d6010000"
     "488bcb48d1e948beffffffffffffff7f488bc6482bc1483bd87710488d0419be2f000000483bc6480f47f0488d4e01e8744e24ff488be848c747102200000048897718"
     "0f1005cea9ed000f11000f100dd4a9ed000f1148100fb70dd9a9ed0066894820c64022004883fb107231488d5301488b0f4881fa00100000721c4883c2274c8b41f8492bc8"
     "488d41f84883f81f0f875e010000498bc8e84a928e0048892fe930010000488b0dc3fb4e0180b9a1230000000f94c08881a123000041c60601"
     "488d05a0b6ed00488d15a1b6ed0080b9a123000000480f45d04889742428660f6f05a119f700f30f7f442438c64424280049c7c0ffffffff49ffc042803c020075f6"
     "488d4c2428e8fb4d24ff904c8d442428488d150eb9ed00488d4c2448e8d44724ff488bd8483bf87466488b57184883fa107230488b0f48ffc24881fa00100000721c"
     "4883c2274c8b41f8492bc8488d41f84883f81f0f8790000000498bc8e882918e004889771048c747180f000000c607000f10030f11070f104b100f114f1048897310"
     "48c743180f000000c60300488d4c2448e8bc5224ff90488b5424404883fa10722e48ffc2488b4c2428488bc14881fa0010000072154883c227488b49f8482bc14883c0f8"
     "4883f81f7729e812918e00498bc64c8d5c2470498b5b28498b6b30498be3415e5f5ec3e87118bf0090e86b18bf00cce86518bf00cc"},
    {kDestructor, "40534883ec20488b5118488bd94883fa10722c488b0948ffc24881fa0010000072184c8b41f84883c227492bc8488d41f84883f81f7721498bc8e8513e6a0148c743100000000048c743180f000000c603004883c4205bc3e8afc59a01cc"},
    // ABI/data-use witnesses only; none of these methods is called here.
    {0x172b120, "40534883ec20488bd941ffd0488bc34883c4205bc3"},
    {0x1721674, "0f57c0f30f7f4424284533e44c89642438"},
    {0x172175c, "498b47384d8b4740488d542428488d4d08ffd090"},
    {0x1721938, "0fb645088807488d4f08488d5510e8353997fe90488d4d10e80b3d97fe90"},
    {0x5349af, "4c8b0dc2b4e0014138a9a1230000745c488b4910488b05068fe00148c1e920480fbfc9488b8018010000488b0cc84180b9661e00000775124138a96f1e00007409498b81681e0000eb07498b81601e0000488b492048c1e92048c1e820663bc8750ab89f860100e94f010000"},
    {0x6e9149, "0fb6b9d0240000"},
};
template <typename T> T read(std::uintptr_t p) {
    T v{}; std::memcpy(&v, reinterpret_cast<const void*>(p), sizeof(v)); return v;
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
    if (!pointer(module)) return false;
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(module + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || nt->FileHeader.TimeDateStamp != 0x66fe6ab9 || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC
        || nt->OptionalHeader.SizeOfImage != 0x25e0000) return false;
    for (const auto& pin : kPins) if (!prefix(module + pin.rva, pin.bytes)) return false;
    constexpr std::uintptr_t rows[] = {0x1fcb3a0, 0x1fccde0};
    for (const auto row : rows) {
        if (read<std::uintptr_t>(module + row + 8) != module + 0x1d34aec
            || read<std::uintptr_t>(module + row + 0x30) != module + 0x1d34af8
            || read<std::uintptr_t>(module + row + 0x38) != module + kCallback) return false;
    }
    return std::memcmp(reinterpret_cast<const void*>(module + 0x1d34aec), "yesman", 7) == 0
        && std::memcmp(reinterpret_cast<const void*>(module + 0x1d34af8), "Toggles AI positive responses", 30) == 0
        && read<std::uint64_t>(module + 0x1dc1c90) == 0
        && read<std::uint64_t>(module + 0x1dc1c98) == 15
        && std::memcmp(reinterpret_cast<const void*>(module + 0x1d2b970), "ENABLED", 8) == 0
        && std::memcmp(reinterpret_cast<const void*>(module + 0x1d2b978), "DISABLED", 9) == 0
        && std::memcmp(reinterpret_cast<const void*>(module + 0x1d2bc30), "AI positive response is now ", 28) == 0;
}
bool world(std::uintptr_t module, Snapshot& s, Identity& id, std::uint32_t& flag, std::uint32_t& fault) {
    if (!eu4_test_controls_1375::observe(s, fault)) return false;
    if (s.native_multiplayer_classifier || s.world_reset_active || s.load_source_present || s.player_handle != kFrance) return false;
    if (!pointer(static_cast<std::uintptr_t>(s.game_cookie))
        || read<std::uintptr_t>(module + 0x233fe78) != s.game_cookie
        || read<unsigned char>(static_cast<std::uintptr_t>(s.game_cookie) + 0x24d0) != 0) return false;
    id.database = read<std::uintptr_t>(module + 0x233d8d0);
    if (!pointer(id.database)) return false;
    id.country_count = read<std::int32_t>(id.database + 0x124);
    id.array = read<std::uintptr_t>(id.database + 0x118);
    if (id.country_count <= 122 || id.country_count > 4096 || !pointer(id.array)) return false;
    id.france = read<std::uintptr_t>(id.array + 122 * 8);
    if (!pointer(id.france) || read<std::uint64_t>(id.france + 0x20) != kFrance) return false;
    const auto game = static_cast<std::uintptr_t>(s.game_cookie);
    id.selector = read<unsigned char>(game + 0x1e66);
    id.alternate_selector = read<unsigned char>(game + 0x1e6f);
    id.effective_player = read<std::uint64_t>(game + ((id.selector == 7 && id.alternate_selector != 0) ? 0x1e68 : 0x1e60));
    if (id.effective_player != kFrance) return false;
    flag = read<unsigned char>(game + 0x23a1);
    return flag <= 1;
}
bool same(const Snapshot& a, const Snapshot& b, const Identity& x, const Identity& y) {
    return a.game_cookie == b.game_cookie && a.server_cookie == b.server_cookie
        && a.pause_manager_cookie == b.pause_manager_cookie && a.player_handle == b.player_handle
        && a.raw_date == b.raw_date && a.native_speed_index == b.native_speed_index
        && a.paused == b.paused && a.manual_pause == b.manual_pause
        && x.database == y.database && x.array == y.array && x.france == y.france
        && x.country_count == y.country_count && x.effective_player == y.effective_player
        && x.selector == y.selector && x.alternate_selector == y.alternate_selector;
}
bool guard(const Host& host, Operation operation, GuardPoint point, const Snapshot& s, std::uint32_t flag) {
    if (InterlockedCompareExchange(&g_frozen, 0, 0) || GetCurrentThreadId() != host.expected_game_thread) return false;
    const GuardInput input{point, operation, s, flag};
    return host.guard(host.user, &input) && !InterlockedCompareExchange(&g_frozen, 0, 0)
        && GetCurrentThreadId() == host.expected_game_thread;
}
bool overlaps(std::uintptr_t p, std::size_t n, std::uintptr_t q, std::size_t m) {
    return p < q + m && q < p + n;
}
bool string_contract(const NativeString& s, const NativeResult& result, const NativeVector& args) {
    if (s.length > 256 || s.length > s.capacity || s.capacity > 8191) return false;
    auto data = reinterpret_cast<std::uintptr_t>(s.storage);
    if (s.capacity >= 16) {
        std::memcpy(&data, s.storage, sizeof(data));
        if (!address(data) || !address(data + static_cast<std::uintptr_t>(s.capacity))
            || overlaps(data, static_cast<std::size_t>(s.capacity + 1), reinterpret_cast<std::uintptr_t>(&result), sizeof(result))
            || overlaps(data, static_cast<std::size_t>(s.capacity + 1), reinterpret_cast<std::uintptr_t>(&args), sizeof(args))) return false;
    } else if (s.capacity != 15) return false;
    for (std::uint64_t i = 0; i < s.length; ++i)
        if (read<unsigned char>(data + static_cast<std::uintptr_t>(i)) == 0) return false;
    return read<unsigned char>(data + static_cast<std::uintptr_t>(s.length)) == 0;
}
bool zeros(const void* p, std::size_t bytes) {
    const auto data = static_cast<const unsigned char*>(p);
    for (std::size_t i = 0; i < bytes; ++i) if (data[i] != 0) return false;
    return true;
}
const char* yes(bool x) { return x ? "true" : "false"; }
bool audit(const Host& host, const Result& r, const char* event, bool completion) {
    char before[16] = "null", after[16] = "null";
    if (r.before_flag_observed) {
        const int n = std::snprintf(before, sizeof(before), "%u", r.before_raw_flag);
        if (n <= 0 || static_cast<std::size_t>(n) >= sizeof(before)) return false;
    }
    if (r.after_flag_observed) {
        const int n = std::snprintf(after, sizeof(after), "%u", r.after_raw_flag);
        if (n <= 0 || static_cast<std::size_t>(n) >= sizeof(after)) return false;
    }
    char line[2048]{};
    const int n = std::snprintf(line, sizeof(line),
        "{\"event\":\"%s\",\"thread_id\":%lu,\"operation\":\"%s\",\"desired_enabled\":%s,"
        "\"reason\":%u,\"stage\":%u,\"before_date\":%d,\"after_date\":%d,"
        "\"before_raw_flag\":%s,\"after_raw_flag\":%s,\"no_native\":%s,\"native_invoked\":%s,"
        "\"callback_returned\":%s,\"callback_success\":%s,\"callback_result_identity\":%s,"
        "\"zero_arguments_confirmed\":%s,\"arguments_unchanged\":%s,\"result_destroyed\":%s,"
        "\"world_identity_unchanged\":%s,\"readback_observed\":%s,\"readback_matches\":%s,"
        "\"exception_code\":%lu,\"freeze_session\":%s,\"audit_complete\":%s,\"retry_allowed\":false,"
        "\"diplomacy_submitted\":false,\"diplomacy_effect_verified\":false,"
        "\"normal_ai_acceptance_verified\":false,\"strict_single_player_verified\":false,\"world_generation_verified\":false}",
        event, static_cast<unsigned long>(GetCurrentThreadId()), r.operation == Operation::enable ? "accept_on" : "accept_off",
        yes(r.operation == Operation::enable), static_cast<unsigned>(r.reason), static_cast<unsigned>(r.stage),
        r.before.raw_date, r.after.raw_date, before, after, yes(r.no_native), yes(r.native_invoked),
        yes(r.callback_returned), yes(r.callback_success), yes(r.callback_result_identity), yes(r.zero_arguments_confirmed),
        yes(r.arguments_unchanged), yes(r.result_destroyed), yes(r.world_identity_unchanged), yes(r.readback_observed),
        yes(r.readback_matches), static_cast<unsigned long>(r.exception_code), yes(r.freeze_session), yes(completion));
    return n > 0 && static_cast<std::size_t>(n) < sizeof(line)
        && host.log(host.user, line, static_cast<std::size_t>(n));
}
void execute(Operation operation, const Host& host, Result& r) {
    const auto module = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    NativeVector args{}; // All three qwords null. Never destroy or free this.
    NativeResult result{}; // Fresh exclusive storage, never a live prior message.
    Identity original{}, fresh_id{};
    Snapshot fresh{};
    std::uint32_t flag = 0;
    const std::uint32_t wanted = operation == Operation::enable ? 1U : 0U;
    __try {
        do {
            r.stage = Stage::image_pin;
            if (!image(module)) { r.reason = Reason::image_pin; r.freeze_session = true; break; }
            r.stage = Stage::before_observation;
            if (!world(module, r.before, original, flag, r.exception_code)) {
                r.reason = Reason::unreadable_state; r.freeze_session = true; break;
            }
            r.before_raw_flag = flag; r.before_flag_observed = true;
            if (!r.before.paused) { r.reason = Reason::wrong_world; break; }
            r.stage = Stage::before_guard;
            if (!guard(host, operation, GuardPoint::before_call, r.before, flag)) { r.reason = Reason::guard_rejected; break; }
            r.zero_arguments_confirmed = zeros(&args, sizeof(args));
            if (!r.zero_arguments_confirmed || !zeros(&result, sizeof(result))) { r.reason = Reason::input_modified; break; }
            r.stage = Stage::begin_audit;
            if (!audit(host, r, "test_acceptance_begin", false)) { r.reason = Reason::audit_failed; r.freeze_session = true; break; }
            r.stage = Stage::final_observation;
            if (!world(module, fresh, fresh_id, flag, r.exception_code) || !same(r.before, fresh, original, fresh_id)
                || !fresh.paused || flag != r.before_raw_flag) { r.reason = Reason::wrong_world; r.freeze_session = true; break; }
            r.stage = Stage::final_guard;
            if (!guard(host, operation, GuardPoint::before_call, fresh, flag)) { r.reason = Reason::guard_rejected; break; }
            if (flag == wanted) {
                // Diagnostic only. Host may not consume a reserved submit/off
                // slot to obtain this or turn it into a grant/reset result.
                r.after = fresh; r.after_raw_flag = flag; r.after_flag_observed = true;
                r.world_identity_unchanged = true; r.readback_observed = true; r.readback_matches = true;
                r.arguments_unchanged = true; r.reason = Reason::already_desired; r.stage = Stage::complete; break;
            }
            if (!zeros(&args, sizeof(args)) || !zeros(&result, sizeof(result))) { r.reason = Reason::input_modified; break; }
            // Exactly one handler entry. A unique persisted host claim and
            // immutable pending grant already exist; no catch block retries.
            r.stage = Stage::callback; r.native_invoked = true; r.no_native = false;
            NativeResult* returned = reinterpret_cast<Callback>(module + kCallback)(&result, &args);
            r.callback_returned = true; r.callback_result_identity = returned == &result;
            if (!r.callback_result_identity || result.success > 1) { r.reason = Reason::callback_contract; break; }
            r.callback_success = result.success != 0;
            r.arguments_unchanged = zeros(&args, sizeof(args));
            if (!r.arguments_unchanged) { r.reason = Reason::input_modified; break; }
            r.stage = Stage::after_observation;
            if (!world(module, r.after, fresh_id, flag, r.exception_code)) { r.reason = Reason::unreadable_state; break; }
            r.after_raw_flag = flag; r.after_flag_observed = true; r.readback_observed = true;
            r.world_identity_unchanged = same(r.before, r.after, original, fresh_id);
            r.readback_matches = flag == wanted;
            if (!r.world_identity_unchanged || !r.after.paused) { r.reason = Reason::wrong_world; break; }
            if (!r.readback_matches) { r.reason = Reason::readback_mismatch; break; }
            r.stage = Stage::after_guard;
            if (!guard(host, operation, GuardPoint::after_call, r.after, flag)) { r.reason = Reason::guard_rejected; break; }
            r.stage = Stage::output_contract;
            if (!string_contract(result.message, result, args)) { r.reason = Reason::result_string_contract; break; }
            r.stage = Stage::destroy_guard;
            if (!world(module, fresh, fresh_id, flag, r.exception_code) || !same(r.before, fresh, original, fresh_id)
                || !fresh.paused || flag != wanted
                || !guard(host, operation, GuardPoint::before_result_destroy, fresh, flag)) { r.reason = Reason::guard_rejected; break; }
            r.stage = Stage::result_destructor;
            reinterpret_cast<Destructor>(module + kDestructor)(&result.message);
            r.result_destroyed = true;
            r.stage = Stage::final_readback;
            if (!world(module, fresh, fresh_id, flag, r.exception_code) || !same(r.before, fresh, original, fresh_id)
                || !fresh.paused || flag != wanted) { r.readback_matches = false; r.reason = Reason::readback_mismatch; break; }
            r.after = fresh; r.after_raw_flag = flag;
            r.stage = Stage::final_after_guard;
            if (!guard(host, operation, GuardPoint::after_call, fresh, flag)) { r.reason = Reason::guard_rejected; break; }
            if (!r.callback_success) { r.reason = Reason::callback_rejected; break; }
            r.stage = Stage::complete;
        } while (false);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        r.exception_code = GetExceptionCode(); r.reason = Reason::native_exception; r.freeze_session = true;
        // Flag could already have changed before message allocation. No second
        // toggle, string destructor, game method or compensating write here.
    }
    if (r.exception_code || (r.native_invoked && r.reason != Reason::none)) r.freeze_session = true;
    if (InterlockedCompareExchange(&g_frozen, 0, 0)) r.freeze_session = true;
}
} // namespace

Result invoke(Operation operation, const Host& host) {
    Result r{}; r.operation = operation; r.no_native = true;
    if (operation != Operation::enable && operation != Operation::disable) { r.reason = Reason::invalid_request; return r; }
    if (host.struct_size != sizeof(Host) || host.abi_version != kAbiVersion || !host.expected_game_thread
        || !host.durable_attempt_claimed || !host.full_sha256_and_preflight_verified || !host.guard || !host.log) {
        r.reason = Reason::host_contract; return r;
    }
    if (GetCurrentThreadId() != host.expected_game_thread) { r.reason = Reason::wrong_thread; return r; }
    if (InterlockedCompareExchange(&g_frozen, 0, 0)) { r.reason = Reason::frozen; r.freeze_session = true; return r; }
    if (InterlockedCompareExchange(&g_active, 1, 0)) {
        r.reason = Reason::busy; r.freeze_session = true; InterlockedExchange(&g_frozen, 1); return r;
    }
    execute(operation, host, r);
    __try {
        // A complete record alone is never the full proof: the wrapper must
        // independently bind this returned audit_complete and later health.
        r.audit_complete = audit(host, r, "test_acceptance_complete", true);
        if (!r.audit_complete) { r.reason = Reason::audit_failed; r.freeze_session = true; }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        if (!r.exception_code) r.exception_code = GetExceptionCode();
        r.reason = Reason::audit_failed; r.freeze_session = true;
    }
    if (r.freeze_session) InterlockedExchange(&g_frozen, 1);
    InterlockedExchange(&g_active, 0);
    return r;
}

bool observe(Snapshot& output, std::uint32_t& raw_flag, std::uint32_t& fault_code) {
    output = {}; raw_flag = 0; fault_code = 0;
    __try {
        const auto module = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
        Identity identity{};
        return image(module) && world(module, output, identity, raw_flag, fault_code);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        fault_code = GetExceptionCode(); return false;
    }
}
} // namespace eu4_test_acceptance_1375
