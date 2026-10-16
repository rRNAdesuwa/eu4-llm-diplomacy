// Exact-build, fixed FRA -> ENG positive improve_relation submit experiment.
// DRAFT ONLY: intentionally not linked into the current research DLL.
// Caller MUST independently require the same-session full-SHA lifecycle,
// preview and command selftests to have passed, an explicit separate marker,
// and the verified live game/frame thread plus single-player/world gates.
// No hook, loader, DllMain, arbitrary action arguments, retries or API here.
// Evidence: native-preview-1375.json, native-command-1.37.5.json,
// local-transport-submit-1375.json and native-pair-effects-1375.json.
// audit_ready checks durable logger health AND the caller's current world/thread
// identity gate. It must have no engine calls or game-state writes.
// Returned true means only: context_submit returned true, consumed the caller
// container, and the final audit remained healthy. It NEVER means effect applied.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
using Logger = void (*)(const char*);
using Factory = void* (__fastcall*)(std::uint32_t, const void*);
using Preview = bool (__fastcall*)(void*, void*, bool);
using Wrapper = void** (__fastcall*)(void*, void**);
using Gate = bool (__fastcall*)(void*);
using Destructor = void* (__fastcall*)(void*, unsigned int);
using ContextSubmit = bool (__fastcall*)(void*, void**);

constexpr std::uintptr_t kFactory = 0x35d210;
constexpr std::uintptr_t kPreview = 0x4e9d00;
constexpr std::uintptr_t kWrapper = 0x4e9930;
constexpr std::uintptr_t kGate = 0x4e8630;
constexpr std::uintptr_t kActionVtable = 0x1c7dd68;
constexpr std::uintptr_t kActionDestructor = 0x129450;
constexpr std::uintptr_t kCommandVtable = 0x1c814b0;
constexpr std::uintptr_t kCommandDestructor = 0x4e7470;
constexpr std::uintptr_t kContextSubmit = 0x14ca210;
constexpr std::uintptr_t kServerVtable = 0x1cb8460;
constexpr std::uintptr_t kContextGetter = 0x811aa0;
constexpr std::uintptr_t kTransportVtable = 0x1d96178;
constexpr std::uintptr_t kTransportSubmit = 0x1580370;
constexpr std::uintptr_t kDatabasePointer = 0x233d8d0;
constexpr std::uintptr_t kGamePointer = 0x233fe78;
constexpr std::uintptr_t kFactorySentinel = 0x1fd1ca0;
constexpr std::uint64_t kFrance = 0x0100007a00415246ULL;
constexpr std::uint64_t kEngland = 0x0100002e00474e45ULL;
constexpr std::uint32_t kToken = 0x2ddb;
volatile LONG g_attempted = 0;

struct Pin { std::uintptr_t rva; const char* bytes; };
constexpr Pin kPins[] = {
    {kFactory, "40555357488dac24a0feffff4881ec60020000488bda33ff89bd8001000081f9"},
    {kPreview, "48895c2410448844241848894c24085556574154415541564157488d6c24d948"},
    {kWrapper, "48895c2408574883ec20488b01488bfaff90b0000000488b0d2b65e501488bd8"},
    {kGate, "48896c24184889742420574883ec20488bf9488b4950837934007567488b01ff"},
    {kCommandDestructor, "48895c2408574883ec208bfa488bd9488d052aa07901488901488b49504885c9"},
    {kActionDestructor, "40534883ec20488d051b51b101488bd9488901f6c201740aba40000000e87e00"},
    {0x574b20, "40534883ec20488bd9b940000000e8a1e74b014c8bc04889442438c740086501"},
    {0x574460, "48895c2408488974241048897c241841564883ec40488bda488bf140b701488b"},
    {0x4e3dc0, "b8db2d0000c3"},
    {0x8f450, "32c0c3"},
    {0x4e4d50, "0fb64138c3"},
    {kContextGetter, "488b8130030000488b8070030000c3"},
    {kContextSubmit, "48895c240848897424184889542410574883ec20488bf2488bf9488b1a48c702"},
    // Explicit true after transport, followed by movzx eax,bl at 14ca2b1.
    {0x14ca29c, "b301488b0e4885c9740b4c8b01ba0100000041ff100fb6c3"},
    {kTransportSubmit, "4885d20f8434090000488954241048894c240853565741544155415641574881"},
};

template <typename T> T read_at(std::uintptr_t address) {
    T value{};
    std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(value));
    return value;
}
template <typename T> void write_owned(std::uintptr_t object, std::size_t offset, T value) {
    // Only used for this module's newly factory-created and identity-pinned action.
    std::memcpy(reinterpret_cast<void*>(object + offset), &value, sizeof(value));
}
bool pointer_ok(std::uintptr_t value) {
    return value >= 0x10000 && value < 0x0000800000000000ULL && value % 8 == 0;
}
unsigned nibble(char c) {
    return c >= '0' && c <= '9' ? static_cast<unsigned>(c - '0')
                               : static_cast<unsigned>(c - 'a' + 10);
}
bool prefix_matches(std::uintptr_t address, const char* expected) {
    const auto bytes = reinterpret_cast<const unsigned char*>(address);
    for (std::size_t i = 0; expected[i * 2] != 0; ++i) {
        if (expected[i * 2 + 1] == 0
            || bytes[i] != ((nibble(expected[i * 2]) << 4) | nibble(expected[i * 2 + 1]))) return false;
    }
    return true;
}
bool image_matches(std::uintptr_t base) {
    if (base != reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr))) return false;
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto pe = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (pe->Signature != IMAGE_NT_SIGNATURE || pe->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || pe->FileHeader.TimeDateStamp != 0x66fe6ab9 || pe->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC
        || pe->OptionalHeader.SizeOfImage != 0x25e0000) return false;
    for (const Pin& pin : kPins) if (!prefix_matches(base + pin.rva, pin.bytes)) return false;
    return read_at<std::uintptr_t>(base + kActionVtable) == base + kActionDestructor
        && read_at<std::uintptr_t>(base + kActionVtable + 0x40) == base + kWrapper
        && read_at<std::uintptr_t>(base + kActionVtable + 0x80) == base + 0x574460
        && read_at<std::uintptr_t>(base + kActionVtable + 0x98) == base + 0x4e3dc0
        && read_at<std::uintptr_t>(base + kActionVtable + 0xa8) == base + 0x8f450
        && read_at<std::uintptr_t>(base + kActionVtable + 0xb0) == base + 0x574b20
        && read_at<std::uintptr_t>(base + kActionVtable + 0x100) == base + 0x4e4d50
        && read_at<std::uintptr_t>(base + kActionVtable + 0x108) == base + 0x8f450
        && read_at<std::uintptr_t>(base + kCommandVtable) == base + kCommandDestructor
        && read_at<std::uintptr_t>(base + kCommandVtable + 0x40) == base + kGate
        && read_at<std::uintptr_t>(base + kServerVtable) == base + 0x80b420
        && read_at<std::uintptr_t>(base + kServerVtable + 0x80) == base + kContextGetter
        && read_at<std::uintptr_t>(base + kTransportVtable) == base + 0x15800d0
        && read_at<std::uintptr_t>(base + kTransportVtable + 0x30) == base + kTransportSubmit;
}

struct State { std::uintptr_t database; std::uintptr_t game; std::int32_t date; };
bool handle_matches(std::uintptr_t array, std::uint32_t slot, std::uint64_t expected) {
    const auto address = array + static_cast<std::uintptr_t>(slot) * 8;
    const auto country = read_at<std::uintptr_t>(address);
    return pointer_ok(country) && read_at<std::uint64_t>(country + 0x20) == expected
        && read_at<std::uintptr_t>(address) == country;
}
bool current_state(std::uintptr_t base, State& state) {
    state.database = read_at<std::uintptr_t>(base + kDatabasePointer);
    state.game = read_at<std::uintptr_t>(base + kGamePointer);
    if (!pointer_ok(state.database) || !pointer_ok(state.game)) return false;
    const auto array = read_at<std::uintptr_t>(state.database + 0x118);
    if (!pointer_ok(array) || !handle_matches(array, 122, kFrance) || !handle_matches(array, 46, kEngland)) return false;
    state.date = read_at<std::int32_t>(state.game + 0x1dd0);
    return state.date > 0 && read_at<std::uint64_t>(state.game + 0x1e60) == kFrance
        && read_at<std::uintptr_t>(base + kDatabasePointer) == state.database
        && read_at<std::uintptr_t>(base + kGamePointer) == state.game;
}
bool same_state(std::uintptr_t base, const State& expected) {
    State live{};
    return current_state(base, live) && live.database == expected.database
        && live.game == expected.game && live.date == expected.date;
}
bool action_identity(std::uintptr_t base, std::uintptr_t action) {
    return pointer_ok(action) && action != base + kFactorySentinel
        && read_at<std::uintptr_t>(action) == base + kActionVtable
        && read_at<std::uint32_t>(action + 8) == 0x165;
}
bool action_fields(std::uintptr_t action, const State& state) {
    return read_at<std::uint64_t>(action + 0x10) == kFrance
        && read_at<std::uint64_t>(action + 0x18) == kFrance
        && read_at<std::uint64_t>(action + 0x20) == kEngland
        && read_at<std::int32_t>(action + 0x28) == state.date
        && read_at<std::int32_t>(action + 0x2c) == state.date
        && read_at<std::int32_t>(action + 0x30) == -1
        && read_at<std::uint32_t>(action + 0x34) == 0
        && read_at<unsigned char>(action + 0x38) == 1
        && read_at<unsigned char>(action + 0x39) == 0
        && read_at<std::uint32_t>(action + 0x3c) == 0;
}
void initialize_owned(std::uintptr_t action, const State& state) {
    write_owned(action, 0x10, kFrance);
    write_owned(action, 0x18, kFrance);
    write_owned(action, 0x20, kEngland);
    write_owned(action, 0x28, state.date);
    write_owned(action, 0x2c, state.date);
    write_owned(action, 0x30, static_cast<std::int32_t>(-1));
    write_owned(action, 0x34, static_cast<std::uint32_t>(0));
    write_owned(action, 0x38, static_cast<unsigned char>(1));
    write_owned(action, 0x39, static_cast<unsigned char>(0));
    write_owned(action, 0x3c, static_cast<std::uint32_t>(0));
}
bool command_identity(std::uintptr_t base, std::uintptr_t command) {
    return pointer_ok(command) && command != base + kFactorySentinel
        && read_at<std::uintptr_t>(command) == base + kCommandVtable
        && read_at<std::uint32_t>(command + 8) == 0x165
        && read_at<std::uint32_t>(command + 0x44) == 0x2934;
}
bool command_defaults(std::uintptr_t command) {
    return read_at<unsigned char>(command + 0x10) == 0
        && read_at<std::uint64_t>(command + 0x18) == 0
        && read_at<std::uint64_t>(command + 0x28) == 0
        && read_at<std::uint64_t>(command + 0x30) == 15
        && read_at<std::int32_t>(command + 0x38) == -1
        && read_at<std::uint32_t>(command + 0x3c) == 0
        && read_at<std::uint16_t>(command + 0x40) == 0
        && read_at<std::uint64_t>(command + 0x48) == 0xffff;
}
bool owned_command(std::uintptr_t base, std::uintptr_t command, std::uintptr_t clone, const State& state) {
    return command_identity(base, command) && command_defaults(command)
        && read_at<std::uintptr_t>(command + 0x50) == clone && clone != command
        && action_identity(base, clone) && action_fields(clone, state);
}

struct Context {
    std::uintptr_t server;
    std::uintptr_t holder;
    std::uintptr_t context;
    std::uintptr_t transport;
    unsigned char ready55;
    unsigned char ready80d;
};
bool live_context(std::uintptr_t base, const State& state, Context& found) {
    if (!same_state(base, state)) return false;
    found.server = read_at<std::uintptr_t>(state.game + 0x1e00);
    if (!pointer_ok(found.server) || read_at<std::uintptr_t>(found.server) != base + kServerVtable) return false;
    found.holder = read_at<std::uintptr_t>(found.server + 0x330);
    if (!pointer_ok(found.holder)) return false;
    // Static getter 811aa0 inlined as reads, never called as a method.
    found.context = read_at<std::uintptr_t>(found.holder + 0x370);
    if (!pointer_ok(found.context)) return false;
    found.transport = read_at<std::uintptr_t>(found.context + 0x58);
    if (!pointer_ok(found.transport)
        || read_at<std::uintptr_t>(found.transport) != base + kTransportVtable) return false;
    found.ready55 = read_at<unsigned char>(found.context + 0x55);
    found.ready80d = read_at<unsigned char>(found.context + 0x80d);
    return (found.ready55 != 0 || found.ready80d != 0)
        && read_at<std::uintptr_t>(state.game + 0x1e00) == found.server
        && read_at<std::uintptr_t>(found.server + 0x330) == found.holder
        && read_at<std::uintptr_t>(found.holder + 0x370) == found.context
        && read_at<std::uintptr_t>(found.context + 0x58) == found.transport;
}
const char* yes(bool value) { return value ? "true" : "false"; }
} // namespace

bool pair_submit_improve_experiment(std::uintptr_t base, void (*logger)(const char*), bool (*audit_ready)()) {
    if (logger == nullptr || audit_ready == nullptr) return false;
    if (InterlockedCompareExchange(&g_attempted, 1, 0) != 0) {
        logger("{\"event\":\"pair_submit_rejected\",\"reason\":\"attempt_already_used\",\"submitted\":false,\"applied\":null}");
        return false;
    }
    void* original = nullptr;
    void* command = nullptr;
    std::uintptr_t clone = 0;
    State state{};
    Context context{};
    bool original_owned = false;
    bool command_owned = false;
    bool initialized = false;
    bool preview_called = false;
    bool preview_allowed = false;
    bool gate_called = false;
    bool gate_allowed = false;
    bool context_verified = false;
    bool original_destroyed = false;
    bool command_destroyed = false;
    bool ownership_uncertain = false;
    bool submit_entered = false;
    bool submit_returned = false;
    bool submit_value = false;
    bool caller_consumed = false;
    DWORD exception = 0;
    const char* stage = "begin";
    char line[2048]{};
    __try {
        sprintf_s(line, "{\"event\":\"pair_submit_attempt_begin\",\"action\":\"improve_relation\","
            "\"mode\":\"positive\",\"actor\":\"FRA\",\"target\":\"ENG\",\"thread_id\":%lu,"
            "\"submitted\":false,\"applied\":null,\"attempt_lock_acquired\":true}", GetCurrentThreadId());
        logger(line);
        do {
            stage = "initial_audit_gate";
            if (!audit_ready()) break;
            stage = "image_pin";
            if (!image_matches(base)) break;
            stage = "live_identity";
            if (!current_state(base, state)) break;
            stage = "factory";
            original = reinterpret_cast<Factory>(base + kFactory)(kToken, nullptr);
            const auto original_address = reinterpret_cast<std::uintptr_t>(original);
            if (!action_identity(base, original_address)) { ownership_uncertain = true; break; }
            original_owned = true;
            initialize_owned(original_address, state);
            initialized = action_fields(original_address, state);
            if (!initialized) { ownership_uncertain = true; break; }
            stage = "preview";
            preview_called = true;
            preview_allowed = reinterpret_cast<Preview>(base + kPreview)(original, nullptr, false);
            if (!action_identity(base, original_address) || !action_fields(original_address, state)) {
                ownership_uncertain = true; break;
            }
            if (!preview_allowed || !same_state(base, state)) break;
            stage = "wrapper";
            const auto result = reinterpret_cast<Wrapper>(base + kWrapper)(original, &command);
            const auto command_address = reinterpret_cast<std::uintptr_t>(command);
            if (result != &command || !command_identity(base, command_address)) {
                ownership_uncertain = true; break;
            }
            clone = read_at<std::uintptr_t>(command_address + 0x50);
            if (clone == original_address || command_address == original_address
                || !owned_command(base, command_address, clone, state)
                || !action_identity(base, original_address) || !action_fields(original_address, state)) {
                ownership_uncertain = true; break;
            }
            command_owned = true;
            stage = "command_gate";
            gate_called = true;
            gate_allowed = reinterpret_cast<Gate>(base + kGate)(command);
            if (!owned_command(base, command_address, clone, state)
                || !action_identity(base, original_address) || !action_fields(original_address, state)) {
                ownership_uncertain = true; break;
            }
            if (!gate_allowed || !same_state(base, state)) break;
            stage = "original_destructor";
            reinterpret_cast<Destructor>(base + kActionDestructor)(original, 1);
            original_destroyed = true;
            original_owned = false;
            original = nullptr;
            stage = "context_pin";
            context_verified = live_context(base, state, context);
            if (!context_verified || !owned_command(base, command_address, clone, state)) break;
            // The durable caller logger receives this BEFORE entering transfer.
            stage = "submit_begin";
            sprintf_s(line, "{\"event\":\"pair_submit_begin\",\"action\":\"improve_relation\","
                "\"mode\":\"positive\",\"actor\":\"FRA\",\"target\":\"ENG\","
                "\"actor_handle\":\"0x%016llx\",\"target_handle\":\"0x%016llx\","
                "\"raw_date\":%d,\"thread_id\":%lu,\"preview_allowed\":true,\"gate_allowed\":true,"
                "\"context_verified\":true,\"context_byte_55\":%u,\"context_byte_80d\":%u,"
                "\"original_destroyed\":true,\"submitted\":false,\"applied\":null}",
                static_cast<unsigned long long>(kFrance), static_cast<unsigned long long>(kEngland),
                state.date, GetCurrentThreadId(), static_cast<unsigned>(context.ready55),
                static_cast<unsigned>(context.ready80d));
            logger(line);
            stage = "submit_audit_gate";
            if (!audit_ready()) break;
            Context final_context{};
            stage = "submit_final_pin";
            if (!live_context(base, state, final_context)
                || final_context.server != context.server || final_context.holder != context.holder
                || final_context.context != context.context || final_context.transport != context.transport
                || !owned_command(base, command_address, clone, state)) break;
            if (!audit_ready()) break;
            // Irreversible local ownership boundary. No engine cleanup from here
            // onward, even if the function returns false, container is nonnull,
            // or an exception interrupts the call. Never retry this attempt.
            stage = "context_submit";
            submit_entered = true;
            command_owned = false;
            submit_value = reinterpret_cast<ContextSubmit>(base + kContextSubmit)(
                reinterpret_cast<void*>(context.context), &command);
            submit_returned = true;
            caller_consumed = command == nullptr;
            ownership_uncertain = !submit_value || !caller_consumed;
            stage = "dispatch_returned";
        } while (false);

        // Only pre-transfer, identity-confirmed ownership can be cleaned up.
        if (!submit_entered && !ownership_uncertain) {
            if (command_owned) {
                if (!owned_command(base, reinterpret_cast<std::uintptr_t>(command), clone, state)) {
                    ownership_uncertain = true;
                } else {
                    reinterpret_cast<Destructor>(base + kCommandDestructor)(command, 1);
                    command = nullptr;
                    command_owned = false;
                    command_destroyed = true; // Includes clone through pinned native dtor path.
                }
            }
            if (original_owned && !ownership_uncertain) {
                if (!action_identity(base, reinterpret_cast<std::uintptr_t>(original))) {
                    ownership_uncertain = true;
                } else {
                    reinterpret_cast<Destructor>(base + kActionDestructor)(original, 1);
                    original = nullptr;
                    original_owned = false;
                    original_destroyed = true;
                }
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        exception = GetExceptionCode();
        ownership_uncertain = true;
        // A native exception is a hard stop; no speculative destructor call.
    }
    const bool dispatched = submit_entered && submit_returned && submit_value && caller_consumed && exception == 0;
    sprintf_s(line, "{\"event\":\"pair_submit_complete\",\"action\":\"improve_relation\","
        "\"mode\":\"positive\",\"actor\":\"FRA\",\"target\":\"ENG\",\"stage\":\"%s\","
        "\"raw_date\":%d,\"initialized\":%s,\"preview_called\":%s,\"preview_allowed\":%s,"
        "\"gate_called\":%s,\"gate_allowed\":%s,\"context_verified\":%s,"
        "\"original_destroyed\":%s,\"command_destroyed_before_submit\":%s,"
        "\"submit_entered\":%s,\"submit_returned\":%s,\"context_submit_return\":%s,"
        "\"caller_container_consumed\":%s,\"ownership_uncertain\":%s,\"exception\":%lu,"
        "\"thread_id\":%lu,\"dispatched\":%s,\"submitted\":%s,\"applied\":null,\"retry_allowed\":false}",
        stage, state.date, yes(initialized), yes(preview_called), yes(preview_allowed),
        yes(gate_called), yes(gate_allowed), yes(context_verified), yes(original_destroyed),
        yes(command_destroyed), yes(submit_entered), yes(submit_returned),
        submit_returned ? yes(submit_value) : "null", submit_returned ? yes(caller_consumed) : "null",
        yes(ownership_uncertain), exception, GetCurrentThreadId(), yes(dispatched),
        dispatched ? "true" : (submit_entered ? "null" : "false"));
    logger(line);
    return dispatched && audit_ready();
}
