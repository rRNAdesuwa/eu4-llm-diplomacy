#include "alliance-reason-key-branch.h"
#include <cstdio>
#include <cstring>

int main() {
    using namespace bridge_reason_key_branch;
    unsigned checks=0;
    auto require=[&](bool okay) { ++checks; if (!okay) {
        std::printf("failed check %u\n",checks); return false; } return true; };
    // Model the native frame, not a row-sized buffer: both flags belong to
    // the caller frame and must be read relative to its actual RCX row.
    unsigned char frame[0x1c0]{};
    const uintptr_t base=reinterpret_cast<uintptr_t>(frame);
    unsigned reads=0;
    auto read_byte=[&](uintptr_t address,unsigned char& value) noexcept {
        ++reads;
        if (address<base || address-base>=sizeof(frame)) return false;
        value=frame[address-base]; return true;
    };
    Observation observed{};
    for (const auto& binding:kBindings) {
        for (unsigned flag=0;flag<2;++flag) {
            frame[0x1a0]=1; frame[0x1a8]=static_cast<unsigned char>(flag);
            const auto* key=select(binding.standard.caller_return_rva,
                base+binding.row_rbp_offset,read_byte,observed);
            if (!require(key==(flag?&binding.overlord:&binding.standard))
                || !require(observed.flags_readable && observed.text_flag==1
                    && observed.overlord_flag==flag)) return 2;
        }
        frame[0x1a0]=0;
        if (!require(!select(binding.standard.caller_return_rva,
            base+binding.row_rbp_offset,read_byte,observed))) return 2;
        frame[0x1a0]=1; frame[0x1a8]=2;
        if (!require(!select(binding.standard.caller_return_rva,
            base+binding.row_rbp_offset,read_byte,observed))) return 2;
        if (!require(!select(binding.standard.caller_return_rva,base+sizeof(frame),
            read_byte,observed)) || !require(!observed.flags_readable)) return 2;
        const auto prior=reads;
        if (!require(!select(binding.standard.caller_return_rva,0,read_byte,observed))
            || !require(reads==prior)
            || !require(!select(binding.standard.caller_return_rva,
                std::numeric_limits<uintptr_t>::max()-1,read_byte,observed))
            || !require(reads==prior)) return 2;
    }
    const auto prior=reads;
    if (!require(!select(0x1234,base,read_byte,observed))
        || !require(!observed.matched && reads==prior)) return 2;
    for (const auto& binding:kConditionalKeyBindings) {
        const uintptr_t row=base+binding.row_rbp_offset;
        frame[0x160]=1;
        const auto* key=select(binding.caller_return_rva,row,read_byte,observed);
        if (!require(key==&binding.key)
            || !require(observed.matched && observed.condition_readable
                && observed.condition_value==1
                && observed.condition_offset==binding.condition_row_offset)) return 2;
        frame[0x160]=2;
        key=select(binding.caller_return_rva,row,read_byte,observed);
        if (!require(key==&binding.key)
            || !require(observed.condition_readable
                && observed.condition_value==2)) return 2;
        frame[0x160]=0;
        if (!require(!select(binding.caller_return_rva,row,read_byte,observed))
            || !require(observed.matched && observed.condition_readable
                && observed.condition_value==0)) return 2;
        const auto prior=reads;
        frame[0x160]=1;
        if (!require(!select(binding.caller_return_rva,
                base+sizeof(frame)-0x80,read_byte,observed))
            || !require(observed.matched && !observed.condition_readable)
            || !require(reads>prior)) return 2;
        if (!require(!select(binding.caller_return_rva,0,read_byte,observed))
            || !require(observed.matched && !observed.condition_readable)) return 2;
    }
    std::printf("{\"status\":\"passed\",\"checks\":%u}\n",checks);
    return 0;
}
