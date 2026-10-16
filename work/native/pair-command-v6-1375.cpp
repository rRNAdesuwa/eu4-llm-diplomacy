// EU4 1.37.5 experimental command lifecycle draft. NO SUBMIT/EXECUTE PATH.
// This standalone module is intentionally not linked into the current DLL.
// Caller prerequisites: same-process full SHA256 lifecycle pin has passed;
// invoke once on the independently observed game/frame thread, after a separate
// explicit command-lifecycle marker, with the world/identity gates satisfied.
// Evidence: native-command-1.37.5.json and native-preview-1375.json.
// The only engine calls are action factory, command wrapper, command gate,
// command deleting destructor (owns its clone), and original action destructor.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
using Logger = void (*)(const char*);
using Factory = void* (__fastcall*)(std::uint32_t, const void*);
using CommandWrapper = void** (__fastcall*)(void*, void**);
using CommandGate = bool (__fastcall*)(void*);
using Destructor = void* (__fastcall*)(void*, unsigned int);

constexpr std::uintptr_t kFactory = 0x35d210;
constexpr std::uintptr_t kWrapper = 0x4e9930;
constexpr std::uintptr_t kGate = 0x4e8630;
constexpr std::uintptr_t kCommandDestructor = 0x4e7470;
constexpr std::uintptr_t kCommandVtable = 0x1c814b0;
constexpr std::uintptr_t kNotSharedPredicate = 0x8f450;
constexpr std::uintptr_t kDatabasePointer = 0x233d8d0;
constexpr std::uintptr_t kGamePointer = 0x233fe78;
constexpr std::uintptr_t kFactorySentinel = 0x1fd1ca0;

struct FunctionPin {
    std::uintptr_t rva;
    const char* prefix;
};
constexpr FunctionPin kFunctionPins[] = {
    {kFactory, "40555357488dac24a0feffff4881ec60020000488bda33ff89bd8001000081f9"},
    {kWrapper, "48895c2408574883ec20488b01488bfaff90b0000000488b0d2b65e501488bd8"},
    {kGate, "48896c24184889742420574883ec20488bf9488b4950837934007567488b01ff"},
    {kCommandDestructor, "48895c2408574883ec208bfa488bd9488d052aa07901488901488b49504885c9"},
    {0x129450, "40534883ec20488d051b51b101488bd9488901f6c201740aba40000000e87e00"},
    {0x4ed5b0, "48895c2408574883ec20488bf98bda4883c140e89880baff488d05a90f750148"},
    // Command destructor calls action+0xa8 before deciding ownership. All five
    // pinned types return false; no speculative runtime predicate call needed.
    {kNotSharedPredicate, "32c0c3"},
    {0x8f440, "b001c3"},
    {0x4e4d50, "0fb64138c3"},
};

struct Country {
    const char* tag;
    std::uint32_t slot;
    std::uint64_t expected_handle;
};
constexpr Country kFrance{"FRA", 122, 0x0100007a00415246ULL};
constexpr Country kTargets[] = {
    {"ENG", 46, 0x0100002e00474e45ULL},
    {"POR", 189, 0x010000bd00524f50ULL},
};

struct Action {
    const char* name;
    std::uint32_t token;
    std::uintptr_t vtable;
    std::uintptr_t clone;
    std::uintptr_t destructor;
    std::uintptr_t token_getter;
    std::uintptr_t validity;
    std::uintptr_t envoy_predicate;
    std::uintptr_t favor_predicate;
    const char* clone_prefix;
    const char* validity_prefix;
};
constexpr Action kActions[] = {
    {"vassalaction", 0x2940, 0x1c7fd20, 0x51fa00, 0x129450, 0x51f570, 0x51f020, 0x8f440, 0x8f450,
     "40534883ec20488bd9b940000000e8c13851014c8bc04889442438c740086501",
     "48895c24105556574154415541564157488d6c24d94881ecc0000000488bf24c"},
    {"royal_marriage", 0x28df, 0x1c80ab0, 0x4f07d0, 0x4ed5b0, 0x4e3df0, 0x4ef3b0, 0x8f440, 0x8f450,
     "40534883ec20488bd9b968000000e8f12a54014c8bc04889442438c740086501",
     "48895c2410488974241848897c2420554154415541564157488bec4883ec6048"},
    {"improve_relation", 0x2ddb, 0x1c7dd68, 0x574b20, 0x129450, 0x4e3dc0, 0x574460, 0x4e4d50, 0x8f450,
     "40534883ec20488bd9b940000000e8a1e74b014c8bc04889442438c740086501",
     "48895c2408488974241048897c241841564883ec40488bda488bf140b701488b"},
    {"guaranteeaction", 0x2941, 0x1c7fe50, 0x5224c0, 0x129450, 0x5220b0, 0x521ad0, 0x8f440, 0x8f450,
     "40534883ec20488bd9b940000000e8010e51014c8bc04889442438c740086501",
     "48895c241048897424185557415541564157488bec4881ec80000000488bda4c"},
    {"spy_network", 0x3378, 0x1c7cc48, 0x586200, 0x129450, 0x585bc0, 0x5856a0, 0x4e4d50, 0x8f440,
     "40534883ec20488bd9b940000000e8c1d04a014c8bc04889442438c740086501",
     "48895c24104889742418574883ec60488bda488bf140b7014c8b4120488b050d"},
};

template <typename T>
T read_at(std::uintptr_t address) {
    T value{};
    std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(value));
    return value;
}
template <typename T>
void write_owned(std::uintptr_t object, std::size_t offset, T value) {
    // Only called for the independently verified, newly allocated action.
    std::memcpy(reinterpret_cast<void*>(object + offset), &value, sizeof(value));
}
bool object_pointer(std::uintptr_t value) {
    return value >= 0x10000 && value < 0x0000800000000000ULL && value % 8 == 0;
}
unsigned nibble(char value) {
    return value >= '0' && value <= '9' ? static_cast<unsigned>(value - '0')
                                       : static_cast<unsigned>(value - 'a' + 10);
}
bool prefix_matches(std::uintptr_t address, const char* expected) {
    const auto bytes = reinterpret_cast<const unsigned char*>(address);
    for (std::size_t index = 0; expected[index * 2] != 0; ++index) {
        if (expected[index * 2 + 1] == 0
            || bytes[index] != ((nibble(expected[index * 2]) << 4) | nibble(expected[index * 2 + 1]))) return false;
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
    for (const FunctionPin& pin : kFunctionPins) {
        if (!prefix_matches(base + pin.rva, pin.prefix)) return false;
    }
    if (read_at<std::uintptr_t>(base + kCommandVtable) != base + kCommandDestructor
        || read_at<std::uintptr_t>(base + kCommandVtable + 0x40) != base + kGate) return false;
    for (const Action& action : kActions) {
        if (read_at<std::uintptr_t>(base + action.vtable) != base + action.destructor
            || read_at<std::uintptr_t>(base + action.vtable + 0x40) != base + kWrapper
            || read_at<std::uintptr_t>(base + action.vtable + 0x80) != base + action.validity
            || read_at<std::uintptr_t>(base + action.vtable + 0x98) != base + action.token_getter
            || read_at<std::uintptr_t>(base + action.vtable + 0xa8) != base + kNotSharedPredicate
            || read_at<std::uintptr_t>(base + action.vtable + 0xb0) != base + action.clone
            || read_at<std::uintptr_t>(base + action.vtable + 0x100) != base + action.envoy_predicate
            || read_at<std::uintptr_t>(base + action.vtable + 0x108) != base + action.favor_predicate
            || !prefix_matches(base + action.clone, action.clone_prefix)
            || !prefix_matches(base + action.validity, action.validity_prefix)
            || read_at<unsigned char>(base + action.token_getter) != 0xb8
            || read_at<std::uint32_t>(base + action.token_getter + 1) != action.token
            || read_at<unsigned char>(base + action.token_getter + 5) != 0xc3) return false;
    }
    return true;
}

struct State {
    std::uint64_t actor;
    std::uint64_t target;
    std::int32_t date;
};
bool country_handle(std::uintptr_t array, const Country& country, std::uint64_t& handle) {
    if (country.slot >= 4096) return false;
    const auto slot_address = array + static_cast<std::uintptr_t>(country.slot) * 8;
    const auto country_object = read_at<std::uintptr_t>(slot_address);
    if (!object_pointer(country_object)) return false;
    handle = read_at<std::uint64_t>(country_object + 0x20);
    return handle == country.expected_handle && (handle >> 56) != 0
        && ((handle >> 32) & 0xffff) == country.slot
        && read_at<std::uintptr_t>(slot_address) == country_object
        && read_at<std::uint64_t>(country_object + 0x20) == handle;
}
bool current_state(std::uintptr_t base, const Country& target, State& state) {
    const auto database = read_at<std::uintptr_t>(base + kDatabasePointer);
    const auto game = read_at<std::uintptr_t>(base + kGamePointer);
    if (!object_pointer(database) || !object_pointer(game)) return false;
    const auto array = read_at<std::uintptr_t>(database + 0x118);
    if (!object_pointer(array) || !country_handle(array, kFrance, state.actor)
        || !country_handle(array, target, state.target)) return false;
    state.date = read_at<std::int32_t>(game + 0x1dd0);
    return state.date > 0 && state.actor != state.target
        && read_at<std::uint64_t>(game + 0x1e60) == state.actor
        && read_at<std::uintptr_t>(base + kDatabasePointer) == database
        && read_at<std::uintptr_t>(base + kGamePointer) == game;
}
bool action_identity(std::uintptr_t base, std::uintptr_t object, const Action& action) {
    return object_pointer(object) && object != base + kFactorySentinel
        && read_at<std::uintptr_t>(object) == base + action.vtable
        && read_at<std::uint32_t>(object + 8) == 0x165;
}
bool fields_match(std::uintptr_t object, const State& state, bool value) {
    return read_at<std::uint64_t>(object + 0x10) == state.actor
        && read_at<std::uint64_t>(object + 0x18) == state.actor
        && read_at<std::uint64_t>(object + 0x20) == state.target
        && read_at<std::int32_t>(object + 0x28) == state.date
        && read_at<std::int32_t>(object + 0x2c) == state.date
        && read_at<std::int32_t>(object + 0x30) == -1
        && read_at<std::uint32_t>(object + 0x34) == 0
        && read_at<unsigned char>(object + 0x38) == static_cast<unsigned char>(value ? 1 : 0)
        && read_at<unsigned char>(object + 0x39) == 0
        && read_at<std::uint32_t>(object + 0x3c) == 0;
}
bool initialize_owned(std::uintptr_t base, std::uintptr_t object, const Action& action,
                      const State& state, bool value) {
    if (!action_identity(base, object, action)) return false;
    write_owned(object, 0x10, state.actor);
    write_owned(object, 0x18, state.actor);
    write_owned(object, 0x20, state.target);
    write_owned(object, 0x28, state.date);
    write_owned(object, 0x2c, state.date);
    write_owned(object, 0x30, static_cast<std::int32_t>(-1));
    write_owned(object, 0x34, static_cast<std::uint32_t>(0));
    write_owned(object, 0x38, static_cast<unsigned char>(value ? 1 : 0));
    write_owned(object, 0x39, static_cast<unsigned char>(0));
    write_owned(object, 0x3c, static_cast<std::uint32_t>(0));
    // Derived factory defaults, including marriage EngineString32/+0x60,
    // remain engine-initialized. No guessed derived fields are written.
    return fields_match(object, state, value);
}
bool command_identity(std::uintptr_t base, std::uintptr_t object) {
    return object_pointer(object) && object != base + kFactorySentinel
        && read_at<std::uintptr_t>(object) == base + kCommandVtable
        && read_at<std::uint32_t>(object + 8) == 0x165
        && read_at<std::uint32_t>(object + 0x44) == 0x2934;
}
bool command_defaults(std::uintptr_t object) {
    return read_at<unsigned char>(object + 0x10) == 0
        && read_at<std::uint64_t>(object + 0x18) == 0
        && read_at<std::uint64_t>(object + 0x28) == 0
        && read_at<std::uint64_t>(object + 0x30) == 15
        && read_at<std::int32_t>(object + 0x38) == -1
        && read_at<std::uint32_t>(object + 0x3c) == 0
        && read_at<std::uint16_t>(object + 0x40) == 0
        && read_at<std::uint64_t>(object + 0x48) == 0xffff;
}
const char* json_bool(bool value) { return value ? "true" : "false"; }

bool run_case(std::uintptr_t base, const Action& action, const Country& target,
              bool value, unsigned case_index, Logger logger, bool& allowed_result) {
    void* original = nullptr;
    void* command = nullptr;
    std::uintptr_t clone_address = 0;
    State state{};
    bool state_ok = false;
    bool initialized = false;
    bool wrapper_return_matches = false;
    bool command_ok = false;
    bool command_fields = false;
    bool clone_distinct = false;
    bool clone_fields = false;
    bool original_fields = false;
    bool gate_called = false;
    bool allowed = false;
    bool identities_after_gate = false;
    bool command_destructor_returned = false;
    bool original_destructor_returned = false;
    bool ownership_uncertain = false;
    DWORD exception = 0;
    __try {
        state_ok = current_state(base, target, state);
        if (state_ok) {
            original = reinterpret_cast<Factory>(base + kFactory)(action.token, nullptr);
            const auto original_address = reinterpret_cast<std::uintptr_t>(original);
            initialized = initialize_owned(base, original_address, action, state, value);
            if (initialized) {
                void** result = reinterpret_cast<CommandWrapper>(base + kWrapper)(original, &command);
                wrapper_return_matches = result == &command;
                const auto command_address = reinterpret_cast<std::uintptr_t>(command);
                command_ok = command_identity(base, command_address);
                if (command_ok) {
                    command_fields = command_defaults(command_address);
                    clone_address = read_at<std::uintptr_t>(command_address + 0x50);
                    clone_distinct = clone_address != original_address && clone_address != command_address
                        && action_identity(base, clone_address, action);
                }
                if (wrapper_return_matches && command_ok && command_fields && clone_distinct) {
                    clone_fields = fields_match(clone_address, state, value);
                    original_fields = fields_match(original_address, state, value);
                    if (clone_fields && original_fields) {
                        // This is vtable+0x40 validation, never vtable+0x48 execution.
                        gate_called = true;
                        allowed = reinterpret_cast<CommandGate>(base + kGate)(command);
                        State after{};
                        identities_after_gate = current_state(base, target, after)
                            && after.actor == state.actor && after.target == state.target && after.date == state.date
                            && command_identity(base, command_address)
                            && read_at<std::uintptr_t>(command_address + 0x50) == clone_address
                            && action_identity(base, clone_address, action)
                            && action_identity(base, original_address, action);
                    }
                    // Recheck ownership before destruction even if gate was not
                    // called because the field-value verification failed.
                    const bool cleanup_verified = command_identity(base, command_address)
                        && read_at<std::uintptr_t>(command_address + 0x50) == clone_address
                        && action_identity(base, clone_address, action)
                        && action_identity(base, original_address, action);
                    if (cleanup_verified) {
                        // Pinned +0xa8 returns false. The command destructor
                        // destroys and frees its clone. NEVER free clone separately.
                        reinterpret_cast<Destructor>(base + kCommandDestructor)(command, 1);
                        command_destructor_returned = true;
                        command = nullptr;
                        clone_address = 0; // No access to either freed allocation.
                        reinterpret_cast<Destructor>(base + action.destructor)(original, 1);
                        original_destructor_returned = true;
                        original = nullptr;
                    } else {
                        ownership_uncertain = true;
                    }
                } else {
                    // A corrupted/unknown output or unexpected alias makes
                    // ownership uncertain. Do not guess destructors or retry.
                    ownership_uncertain = true;
                }
            } else if (action_identity(base, original_address, action)) {
                reinterpret_cast<Destructor>(base + action.destructor)(original, 1);
                original_destructor_returned = true;
                original = nullptr;
            }
        }
    } __except ((exception = GetExceptionCode()), EXCEPTION_EXECUTE_HANDLER) {
        // Stop immediately after a fault, including destructor faults. No
        // second engine call, guessed cleanup, retry or continuation is allowed.
    }
    char line[1536]{};
    std::snprintf(line, sizeof(line),
        "{\"event\":\"pair_command_case\",\"case_index\":%u,\"action\":\"%s\",\"mode\":\"%s\","
        "\"value\":%s,\"actor\":\"FRA\",\"target\":\"%s\",\"actor_handle\":\"0x%016llx\","
        "\"target_handle\":\"0x%016llx\",\"current_raw_date\":%d,\"state_verified\":%s,"
        "\"initialized\":%s,\"wrapper_return_matches\":%s,\"command_verified\":%s,"
        "\"command_fields_verified\":%s,"
        "\"clone_distinct\":%s,\"clone_fields_verified\":%s,\"original_fields_verified\":%s,"
        "\"gate_called\":%s,\"allowed\":%s,\"identities_after_gate\":%s,"
        "\"command_destructor_returned\":%s,\"original_destructor_returned\":%s,"
        "\"clone_lifetime_observation\":\"pinned_command_destructor_path_only\","
        "\"ownership_uncertain\":%s,\"exception\":%lu,\"thread_id\":%lu,\"submitted\":false}",
        case_index, action.name, value ? "positive" : "cancel", json_bool(value), target.tag,
        static_cast<unsigned long long>(state.actor), static_cast<unsigned long long>(state.target), state.date,
        json_bool(state_ok), json_bool(initialized), json_bool(wrapper_return_matches), json_bool(command_ok),
        json_bool(command_fields), json_bool(clone_distinct), json_bool(clone_fields), json_bool(original_fields), json_bool(gate_called),
        json_bool(allowed), json_bool(identities_after_gate), json_bool(command_destructor_returned),
        json_bool(original_destructor_returned), json_bool(ownership_uncertain), exception, GetCurrentThreadId());
    logger(line);
    allowed_result = allowed;
    // Native allowed=false is a normal gate result. Only infrastructure,
    // identity, wrapper/clone/ownership or destructor failures fail the suite.
    return exception == 0 && state_ok && initialized && wrapper_return_matches && command_ok && command_fields && clone_distinct
        && clone_fields && original_fields && gate_called && identities_after_gate
        && command_destructor_returned && original_destructor_returned && !ownership_uncertain;
}
} // namespace

bool pair_command_selftest(std::uintptr_t base, void (*logger)(const char*)) {
    if (logger == nullptr) return false;
    static volatile LONG attempted = 0;
    if (InterlockedCompareExchange(&attempted, 1, 0)) {
        logger("{\"event\":\"pair_command_rejected\",\"reason\":\"already_attempted\",\"submitted\":false}");
        return false;
    }
    bool pinned = false;
    __try { pinned = image_matches(base); }
    __except (EXCEPTION_EXECUTE_HANDLER) { pinned = false; }
    if (!pinned) {
        logger("{\"event\":\"pair_command_rejected\",\"reason\":\"build_identity_mismatch\",\"submitted\":false}");
        return false;
    }
    unsigned count = 0;
    unsigned accepted = 0;
    for (const Country& target : kTargets) {
        for (const Action& action : kActions) {
            for (unsigned mode = 0; mode < 2; ++mode) {
                bool allowed = false;
                if (!run_case(base, action, target, mode == 0, ++count, logger, allowed)) return false;
                if (allowed) ++accepted;
            }
        }
    }
    char line[256]{};
    std::snprintf(line, sizeof(line),
        "{\"event\":\"pair_command_all_cases_complete\",\"cases\":%u,\"accepted\":%u,"
        "\"rejected\":%u,\"thread_id\":%lu,\"submitted\":false}",
        count, accepted, count - accepted, GetCurrentThreadId());
    logger(line);
    return count == 20;
}
