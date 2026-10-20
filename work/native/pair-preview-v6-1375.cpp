// EU4 1.37.5 no-submit preview experiment, scoped to the exact reviewed build.
// Call only after the separate lifecycle test passed, on the observed game
// thread, after a separate preview marker. No hook or DllMain in this module.
// Static specification: work/reports/native-preview-1375.json.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
using Logger = void (*)(const char*);
using Factory = void* (__fastcall*)(std::uint32_t, const void*);
using Preview = bool (__fastcall*)(void*, void*, bool);
using Destructor = void* (__fastcall*)(void*, unsigned int);
constexpr std::uintptr_t kFactory = 0x35d210;
constexpr std::uintptr_t kPreview = 0x4e9d00;
constexpr std::uintptr_t kDatabasePointer = 0x233d8d0;
constexpr std::uintptr_t kGamePointer = 0x233fe78;
constexpr const char* kFactoryPrefix = "40555357488dac24a0feffff4881ec60020000488bda33ff89bd8001000081f9";
constexpr const char* kPreviewPrefix = "48895c2410448844241848894c24085556574154415541564157488d6c24d948";

struct Country {
    const char* tag;
    std::uint32_t slot;
    std::uint64_t expected_handle;
};
// Slots and complete handles came from the last read-only identity-checked
// snapshot. Each case re-reads and verifies the actual live country objects.
constexpr Country kFrance{"FRA", 122, 0x0100007a00415246ULL};
constexpr Country kTargets[] = {
    {"ENG", 46, 0x0100002e00474e45ULL},
    {"POR", 189, 0x010000bd00524f50ULL},
};

struct Action {
    const char* name;
    std::uint32_t token;
    std::uintptr_t vtable;
    std::uintptr_t validity;
    std::uintptr_t destructor;
    std::uintptr_t token_getter;
    const char* validity_prefix;
};
constexpr Action kActions[] = {
    {"vassalaction", 0x2940, 0x1c7fd20, 0x51f020, 0x129450, 0x51f570,
     "48895c24105556574154415541564157488d6c24d94881ecc0000000488bf24c"},
    {"royal_marriage", 0x28df, 0x1c80ab0, 0x4ef3b0, 0x4ed5b0, 0x4e3df0,
     "48895c2410488974241848897c2420554154415541564157488bec4883ec6048"},
    {"improve_relation", 0x2ddb, 0x1c7dd68, 0x574460, 0x129450, 0x4e3dc0,
     "48895c2408488974241048897c241841564883ec40488bda488bf140b701488b"},
    {"guaranteeaction", 0x2941, 0x1c7fe50, 0x521ad0, 0x129450, 0x5220b0,
     "48895c241048897424185557415541564157488bec4881ec80000000488bda4c"},
    {"spy_network", 0x3378, 0x1c7cc48, 0x5856a0, 0x129450, 0x585bc0,
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
    // The only memory writes in this module are into a checked, newly allocated
    // temporary action owned by this function. No country/world memory writes.
    std::memcpy(reinterpret_cast<void*>(object + offset), &value, sizeof(value));
}
bool object_pointer(std::uintptr_t value) {
    return value >= 0x10000 && value < 0x0000800000000000ULL && value % 8 == 0;
}
unsigned nibble(char c) {
    return c >= '0' && c <= '9' ? static_cast<unsigned>(c - '0') : static_cast<unsigned>(c - 'a' + 10);
}
bool prefix_matches(std::uintptr_t address, const char* hex) {
    const auto bytes = reinterpret_cast<const unsigned char*>(address);
    for (std::size_t i = 0; hex[i * 2] != 0; ++i) {
        if (hex[i * 2 + 1] == 0 || bytes[i] != ((nibble(hex[i * 2]) << 4) | nibble(hex[i * 2 + 1]))) return false;
    }
    return true;
}
bool image_matches(std::uintptr_t base) {
    if (base != reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr))) return false;
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 4096) return false;
    const auto pe = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (pe->Signature != IMAGE_NT_SIGNATURE || pe->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64
        || pe->FileHeader.TimeDateStamp != 0x66fe6ab9 || pe->OptionalHeader.SizeOfImage != 0x25e0000) return false;
    if (!prefix_matches(base + kFactory, kFactoryPrefix) || !prefix_matches(base + kPreview, kPreviewPrefix)) return false;
    for (const Action& action : kActions) {
        if (read_at<std::uintptr_t>(base + action.vtable) != base + action.destructor
            || read_at<std::uintptr_t>(base + action.vtable + 0x80) != base + action.validity
            || read_at<std::uintptr_t>(base + action.vtable + 0x98) != base + action.token_getter
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
    const auto object = read_at<std::uintptr_t>(array + static_cast<std::uintptr_t>(country.slot) * 8);
    if (!object_pointer(object)) return false;
    handle = read_at<std::uint64_t>(object + 0x20);
    if (handle != country.expected_handle || (handle >> 56) == 0
        || ((handle >> 32) & 0xffff) != country.slot) return false;
    // Recheck identity in the array before passing any handle to engine code.
    return read_at<std::uintptr_t>(array + static_cast<std::uintptr_t>(country.slot) * 8) == object
        && read_at<std::uint64_t>(object + 0x20) == handle;
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
        && read_at<std::uintptr_t>(base + kDatabasePointer) == database
        && read_at<std::uintptr_t>(base + kGamePointer) == game;
}
bool initialize_owned(std::uintptr_t base, std::uintptr_t object, const Action& action,
                      const State& state, bool value) {
    if (!object_pointer(object) || object == base + 0x1fd1ca0
        || read_at<std::uintptr_t>(object) != base + action.vtable
        || read_at<std::uint32_t>(object + 8) != 0x165) return false;
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
    // Retain every derived default, particularly the marriage string/+0x60.
    return read_at<std::uint64_t>(object + 0x10) == state.actor
        && read_at<std::uint64_t>(object + 0x18) == state.actor
        && read_at<std::uint64_t>(object + 0x20) == state.target
        && read_at<std::int32_t>(object + 0x28) == state.date
        && read_at<std::int32_t>(object + 0x2c) == state.date
        && read_at<std::int32_t>(object + 0x30) == -1
        && read_at<unsigned char>(object + 0x38) == static_cast<unsigned char>(value ? 1 : 0);
}

bool run_case(std::uintptr_t base, const Action& action, const Country& target,
              bool value, unsigned case_index, Logger logger, bool& allowed_result) {
    void* owned = nullptr;
    State state{};
    bool state_ok = false;
    bool initialized = false;
    bool allowed = false;
    bool destroyed = false;
    DWORD exception = 0;
    __try {
        state_ok = current_state(base, target, state);
        if (state_ok) {
            owned = reinterpret_cast<Factory>(base + kFactory)(action.token, nullptr);
            const auto address = reinterpret_cast<std::uintptr_t>(owned);
            initialized = initialize_owned(base, address, action, state, value);
            if (initialized) {
                // RDX=null: bool-only, no CString ABI. R8=false: retain normal
                // cooldown/diplomat requirements. The generic method itself
                // invokes the type-specific validity method when appropriate.
                allowed = reinterpret_cast<Preview>(base + kPreview)(owned, nullptr, false);
            }
            if (object_pointer(address) && address != base + 0x1fd1ca0
                && read_at<std::uintptr_t>(address) == base + action.vtable) {
                reinterpret_cast<Destructor>(base + action.destructor)(owned, 1);
                destroyed = true;
            }
        }
    } __except ((exception = GetExceptionCode()), EXCEPTION_EXECUTE_HANDLER) {
        // No speculative second engine call after any fault; stop the suite.
    }
    char line[768]{};
    std::snprintf(line, sizeof(line),
        "{\"event\":\"pair_preview_case\",\"case_index\":%u,\"action\":\"%s\",\"mode\":\"%s\","
        "\"value\":%s,\"actor\":\"FRA\",\"target\":\"%s\",\"actor_handle\":\"0x%016llx\","
        "\"target_handle\":\"0x%016llx\",\"current_raw_date\":%d,\"state_verified\":%s,"
        "\"initialized\":%s,\"allowed\":%s,\"exception\":%lu,\"destroyed\":%s,\"thread_id\":%lu,\"submitted\":false}",
        case_index, action.name, value ? "positive" : "cancel", value ? "true" : "false", target.tag,
        static_cast<unsigned long long>(state.actor), static_cast<unsigned long long>(state.target), state.date,
        state_ok ? "true" : "false", initialized ? "true" : "false", allowed ? "true" : "false",
        exception, destroyed ? "true" : "false", GetCurrentThreadId());
    logger(line);
    allowed_result = allowed;
    // Native rejection is a valid preview result. Infrastructure/ownership
    // failure or a structured exception fails the suite and stops all calls.
    return exception == 0 && state_ok && initialized && destroyed;
}
} // namespace

bool pair_preview(std::uintptr_t base, void (*logger)(const char*)) {
    if (logger == nullptr) return false;
    static volatile LONG attempted = 0;
    if (InterlockedCompareExchange(&attempted, 1, 0)) {
        logger("{\"event\":\"pair_preview_rejected\",\"reason\":\"already_attempted\",\"submitted\":false}");
        return false;
    }
    bool pinned = false;
    __try { pinned = image_matches(base); }
    __except (EXCEPTION_EXECUTE_HANDLER) { pinned = false; }
    if (!pinned) {
        logger("{\"event\":\"pair_preview_rejected\",\"reason\":\"build_identity_mismatch\",\"submitted\":false}");
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
        "{\"event\":\"pair_preview_all_cases_complete\",\"cases\":%u,\"accepted\":%u,\"rejected\":%u,\"thread_id\":%lu,\"submitted\":false}",
        count, accepted, count - accepted, GetCurrentThreadId());
    logger(line);
    return count == 20;
}
