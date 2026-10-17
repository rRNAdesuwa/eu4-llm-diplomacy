#include "alliance-reason-row.h"
#include <cassert>
#include <initializer_list>

int main() {
    using bridge_alliance_reason_row::same_initialized_storage;
    unsigned char a[48]{}, b[48]{};
    uint64_t size=24, capacity=31, pointer=0x123400;
    std::memcpy(a+8,&pointer,8);
    std::memcpy(a+24,&size,8);
    std::memcpy(a+32,&capacity,8);
    a[0]=20; a[40]=1;
    std::memcpy(b,a,48);
    b[4]=123; b[16]=42; b[47]=99;
    assert(same_initialized_storage(a,b));
    for (unsigned index: {0u,8u,24u,32u,40u}) {
        b[index]^=1;
        assert(!same_initialized_storage(a,b));
        b[index]^=1;
    }
    size=3; capacity=15;
    std::memset(a+8,0,16); std::memcpy(a+8,"abc",4);
    std::memcpy(a+24,&size,8); std::memcpy(a+32,&capacity,8);
    std::memcpy(b,a,48); b[12]=71; b[45]=91;
    assert(same_initialized_storage(a,b));
    b[9]='z'; assert(!same_initialized_storage(a,b)); b[9]='b';
    b[11]=1; assert(!same_initialized_storage(a,b));
    assert(!same_initialized_storage(nullptr,b));
    return 0;
}
