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

// FUN_140525e30 uses the same RBP throughout. At these exact constructor
// calls RCX is RBP+0x20 / RBP+0xc0. Its text flag is RBP+0x1a0 and the
// native key-selection flag is RBP+0x1a8. No caller-frame walk is needed.
constexpr ConditionalBinding kBindings[]={
    {0x20,{0x5275bc,0x1c5da68,"DIPLO_ATTITUDE"},
          {0x5275bc,0x1c85180,"DIPLO_OVERLORDS_ATTITUDE"}},
    {0xc0,{0x526e3f,0x1c85218,"DIPLO_WAR_WITH_NEIGHBOUR_RIVAL"},
          {0x526e3f,0x1c851e8,"DIPLO_WAR_WITH_NEIGHBOUR_OVERLORDS_RIVAL"}},
};

struct Observation {
    bool matched=false;
    bool flags_readable=false;
    unsigned char text_flag=0;
    unsigned char overlord_flag=0;
    uintptr_t text_offset=0;
    uintptr_t overlord_offset=0;
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
    return nullptr;
}

} // namespace bridge_reason_key_branch
