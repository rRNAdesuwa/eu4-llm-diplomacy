// Isolated synthetic bytes only; no Windows, executable loading, or game calls.
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <initializer_list>

struct Action { std::uintptr_t vtable; std::uint32_t token; std::size_t size; };
template <typename T> T read_at(std::uintptr_t address) {
    T value{}; std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(value)); return value;
}
#include "contract-diagnostic.inc"

static unsigned checks = 0, failures = 0;
static void check(bool value) { ++checks; if (!value) ++failures; }
template <typename T> static void put(unsigned char* bytes, std::size_t offset, T value) {
    std::memcpy(bytes + offset, &value, sizeof(value));
}
static void initialize(unsigned char* bytes, const Action& action, std::uintptr_t base, bool fixed) {
    std::memset(bytes, 0, 0x80);
    put(bytes, 0, base + action.vtable);
    put(bytes, 8, static_cast<std::uint32_t>(0x165));
    for (unsigned offset : {0x10U, 0x18U, 0x20U}) put(bytes, offset, static_cast<std::uint64_t>(0x2d2d2d));
    put(bytes, 0x28, static_cast<std::uint32_t>(0x29c77f8));
    put(bytes, 0x2c, static_cast<std::uint32_t>(0x29c77f8));
    put(bytes, 0x30, static_cast<std::uint32_t>(0xffffffff));
    put(bytes, 0x34, action.token == 0x2de0 ? 2U : 0U);
    put(bytes, 0x38, static_cast<std::uint16_t>(1));
    if (action.token == 0x2947) put(bytes, 0x40, static_cast<std::int32_t>(-1));
    if (action.token == 0x2948) put(bytes, 0x40, fixed ? 25000 : 0);
    if (action.token == 0x2e09) put(bytes, 0x40, fixed ? 500 : 0);
    if (action.token == 0x2a25) { put(bytes, 0x40, fixed ? 1000 : 0); put(bytes, 0x44, fixed ? 10 : 0); }
    if (action.size == 0x68) put(bytes, 0x58, static_cast<std::uint64_t>(15));
}
int main() {
    constexpr std::uintptr_t base = 0x140000000;
    unsigned char bytes[0x80]{};
    const auto object = reinterpret_cast<std::uintptr_t>(bytes);
    const Action actions[] = {{0x100,0x2de0,0x40}, {0x200,0x2942,0x40}, {0x300,0x2947,0x48},
                              {0x400,0x2948,0x48}, {0x500,0x2e09,0x48}, {0x600,0x2a25,0x48}, {0x700,0x1,0x68}};
    for (const Action& action : actions) {
        for (bool fixed : {false, true}) {
            initialize(bytes, action, base, fixed);
            ContractDiagnostic d{};
            check(default_fields_match(object, action, base, d, fixed));
            check(d.completed && d.state_read && d.failure_mask == 0 && d.state == (action.token == 0x2de0 ? 2U : 0U));
        }
    }
    initialize(bytes, actions[0], base, false);
    put(bytes, 0x34, 0U); // Old synthetic fixture wrongly used zero for coalition.
    ContractDiagnostic coalition{};
    check(!default_fields_match(object, actions[0], base, coalition));
    check(coalition.completed && coalition.state == 0 && coalition.failure_mask == (1U << 9));
    const unsigned offsets[] = {0,8,0x10,0x18,0x20,0x28,0x2c,0x30,0x34,0x38,0x3c};
    for (unsigned index = 0; index < sizeof(offsets)/sizeof(offsets[0]); ++index) {
        initialize(bytes, actions[1], base, false);
        bytes[offsets[index]] ^= 1;
        ContractDiagnostic d{};
        check(!default_fields_match(object, actions[1], base, d) && d.completed && d.failure_mask == (1U << (index + 1)));
    }
    const unsigned action_index[] = {2,3,4,4,5,5,6,6,6,6};
    const unsigned derived_offset[] = {0x40,0x40,0x40,0x44,0x40,0x44,0x40,0x50,0x58,0x60};
    for (unsigned index = 0; index < sizeof(action_index)/sizeof(action_index[0]); ++index) {
        const Action& action = actions[action_index[index]];
        initialize(bytes, action, base, true);
        bytes[derived_offset[index]] ^= 1;
        ContractDiagnostic d{};
        check(!default_fields_match(object, action, base, d, true) && d.completed && d.failure_mask == (1U << (index + 12)));
    }
    ContractDiagnostic absent{};
    char state[16]{}, mask[16]{};
    format_diagnostic(absent, state, mask);
    check(!absent.completed && std::strcmp(state,"null") == 0 && std::strcmp(mask,"null") == 0);
    check(!default_fields_match(0, actions[0], base, absent) && absent.completed && !absent.state_read && absent.failure_mask == 1);
    format_diagnostic(absent, state, mask);
    check(std::strcmp(state,"null") == 0 && std::strcmp(mask,"1") == 0);
    std::printf("v12 synthetic contract: %u checks, %u failures; no game or process access.\n", checks, failures);
    return failures ? 1 : 0;
}
