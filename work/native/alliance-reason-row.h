#ifndef BRIDGE_ALLIANCE_REASON_ROW_H
#define BRIDGE_ALLIANCE_REASON_ROW_H

#include <cstdint>
#include <cstring>

namespace bridge_alliance_reason_row {

// int32 at 0, std::string at 8, flag at 40. The native constructor does
// not initialize alignment padding or the unused half of heap storage.
// Preserve string ownership identity as well as its size and capacity.
inline bool same_initialized_storage(const unsigned char* captured,
                                     const unsigned char* final_row) noexcept {
    if (!captured || !final_row) return false;
    if (std::memcmp(captured, final_row, 4) != 0
        || std::memcmp(captured + 24, final_row + 24, 16) != 0
        || captured[40] != final_row[40]) return false;
    uint64_t size = 0, capacity = 0;
    std::memcpy(&size, captured + 24, sizeof(size));
    std::memcpy(&capacity, captured + 32, sizeof(capacity));
    if (size > capacity) return false;
    if (capacity < 16) {
        return std::memcmp(captured + 8, final_row + 8,
                           static_cast<std::size_t>(size + 1)) == 0;
    }
    return std::memcmp(captured + 8, final_row + 8, 8) == 0;
}

} // namespace bridge_alliance_reason_row
#endif
