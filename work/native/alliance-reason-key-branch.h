#pragma once

#include <cstdint>
#include <limits>

namespace bridge_reason_key_branch {

struct KeyBinding {
    uint32_t caller_return_rva;
    uint32_t rdata_rva;
    const char* key;
};

struct ConditionalBinding {
    uintptr_t row_rbp_offset;
    KeyBinding standard;
    KeyBinding overlord;
};

// Independent one-key conditional bindings.  These do not enter the
// unconditional kConfirmedKeyBindings table: the caller's row carries the
// branch condition at a verified row-relative offset.
struct ConditionalKeyBinding {
    uint32_t caller_return_rva;
    uintptr_t row_rbp_offset;
    uintptr_t condition_row_offset;
    KeyBinding key;
};

// FUN_140525e30 uses the same RBP throughout. At these exact constructor
// calls RCX is RBP+0x20 / RBP+0xc0. Its text flag is RBP+0x1a0 and the
// native key-selection flag is RBP+0x1a8. No caller-frame walk is needed.
constexpr ConditionalBinding kBindings[]={
    {0x20,{0x5275bc,0x1c5da68,"DIPLO_ATTITUDE"},
          {0x5275bc,0x1c85180,"DIPLO_OVERLORDS_ATTITUDE"}},
    {0xc0,{0x526e3f,0x1c85218,"DIPLO_WAR_WITH_NEIGHBOUR_RIVAL"},
          {0x526e3f,0x1c851e8,"DIPLO_WAR_WITH_NEIGHBOUR_OVERLORDS_RIVAL"}},
};

// FUN_140370be0, caller return 0x3728dd: RCX is RBP+0x68 and the fixed-key
// branch is selected only when row+0xf8 (caller RBP+0x160) is non-zero.
// Zero or unreadable condition bytes intentionally return no fixed key.
constexpr ConditionalKeyBinding kConditionalKeyBindings[]={
    {0x3728dd,0x68,0xf8,{0x3728dd,0x1c5d950,"DIPLO_WAR_DESPERATION"}},
};

struct Observation {
    bool matched=false;
    bool flags_readable=false;
    unsigned char text_flag=0;
    unsigned char overlord_flag=0;
    uintptr_t text_offset=0;
    uintptr_t overlord_offset=0;
    bool condition_readable=false;
    unsigned char condition_value=0;
    uintptr_t condition_offset=0;
};

template<class ReadByte>
const KeyBinding* select(uint32_t caller_return_rva,uintptr_t row,
    ReadByte read_byte,Observation& observed) noexcept {
    observed=Observation{};
    for (const ConditionalBinding& binding:kBindings) {
        if (binding.standard.caller_return_rva!=caller_return_rva) continue;
        observed.matched=true;
        observed.text_offset=0x1a0-binding.row_rbp_offset;
        observed.overlord_offset=0x1a8-binding.row_rbp_offset;
        if (!row || row>std::numeric_limits<uintptr_t>::max()-observed.overlord_offset)
            return nullptr;
        observed.flags_readable=read_byte(row+observed.text_offset,observed.text_flag)
            && read_byte(row+observed.overlord_offset,observed.overlord_flag);
        // The native no-text path produces an empty label at these same
        // calls. It must not acquire a localization ID from the caller alone.
        if (!observed.flags_readable || observed.text_flag!=1
            || observed.overlord_flag>1) return nullptr;
        return observed.overlord_flag?&binding.overlord:&binding.standard;
    }
    for (const ConditionalKeyBinding& binding:kConditionalKeyBindings) {
        if (binding.caller_return_rva!=caller_return_rva) continue;
        observed.matched=true;
        observed.condition_offset=binding.condition_row_offset;
        if (!row || row>std::numeric_limits<uintptr_t>::max()
                -binding.condition_row_offset)
            return nullptr;
        observed.condition_readable=read_byte(
            row+binding.condition_row_offset,observed.condition_value);
        if (!observed.condition_readable || observed.condition_value==0)
            return nullptr;
        return &binding.key;
    }
    return nullptr;
}

} // namespace bridge_reason_key_branch
