#pragma once
#include "native_pair_engine.h"

namespace v21port {
// Private composition boundary. There is deliberately no constructor taking a
// public request, loader, export, module discovery or authority implementation.
// A future separately reviewed owner Host must freshly verify held PID/creation,
// full on-disk SHA, loaded PE and roots, date, manual pause and fixed owner thread.
struct Authority {
    void* user{};
    // Identity/world/pause only: normal known cleanup may outlive work TTL.
    bool (*fresh)(void*,Address,std::uint32_t){};
    // Last operation before ABI entry. Must obtain the new monotonic clock
    // AFTER its own fresh identity reads; compare ORIGINAL expires for work.
    // Only ActionDestructor/CommandDestructor may ignore expires (not rollback).
    bool (*final_operation)(void*,Call){};
    // Same final check for each exact original-owned scalar write.
    bool (*final_owned_write)(void*){};
};
class CompiledWin32Platform final : public Platform {
public:
    CompiledWin32Platform(Address base,std::uint32_t owner,Authority a) noexcept:base_(base),owner_(owner),authority_(a){}
    Address module() const noexcept override {return base_;}
    bool ready() override;
    bool region(Address,Region&) override;
    bool read(Address,void*,std::size_t) override;
    bool write(Address,const void*,std::size_t) override;
    Return invoke(Call,const v21pair::Profile&,Address,bool) override;
private:
    Address base_;std::uint32_t owner_;Authority authority_;
};
}
