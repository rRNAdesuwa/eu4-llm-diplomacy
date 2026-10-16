#pragma once
#include "../v21-core-pair-nosend-r2-1375/pair_component.h"
#include <vector>
namespace cancel1375 {
struct Read {
    std::uint64_t address{};
    std::vector<std::uint8_t> bytes;
    bool operator==(const Read& b) const noexcept {return address==b.address&&bytes==b.bytes;}
};
struct Snapshot {
    v21pair::CancelObservation selected{};
    std::vector<Read> reads;
    bool operator==(const Snapshot& b) const noexcept {return selected==b.selected&&reads==b.reads;}
};
// Private read-only graph resolver for five typed negative modes. No native calls.
// SpyNetwork uses the separate spy task binder and is deliberately unsupported.
bool once(v21pair::SyntheticReadPort&,std::uint64_t module,v21pair::Family,const v21pair::PairStamp&,Snapshot&) noexcept;
bool two_pass(v21pair::SyntheticReadPort&,std::uint64_t module,v21pair::Family,const v21pair::PairStamp&,Snapshot&) noexcept;
bool recheck(v21pair::SyntheticReadPort&,std::uint64_t module,v21pair::Family,const v21pair::PairStamp&,const Snapshot&) noexcept;
}
