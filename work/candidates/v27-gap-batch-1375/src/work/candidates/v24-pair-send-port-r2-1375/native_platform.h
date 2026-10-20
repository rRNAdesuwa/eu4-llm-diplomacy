#pragma once
#include "native_pair_engine.h"

namespace v24port {
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
struct SubmissionContext {Address game{},server{},holder{},context{},transport{};std::uint8_t ready55{},ready80d{};
    bool operator==(const SubmissionContext& b) const noexcept {
        return game==b.game && server==b.server && holder==b.holder && context==b.context && transport==b.transport
            && ready55==b.ready55 && ready80d==b.ready80d;
    }};
struct SubmissionAuthority {
    void* user{};
    bool (*prepare)(void*,SubmissionContext&){};
    bool (*final)(void*,const SubmissionContext&,const TransferEnvelope&){};
};
class CompiledWin32Platform final : public Platform {
public:
    CompiledWin32Platform(Address base,std::uint32_t owner,Authority a,SubmissionAuthority send={}) noexcept:base_(base),owner_(owner),authority_(a),submission_(send){}
    Address module() const noexcept override {return base_;}
    bool ready() override;
    bool region(Address,Region&) override;
    bool read(Address,void*,std::size_t) override;
    bool write(Address,const void*,std::size_t) override;
    Return invoke(Call,const v21pair::Profile&,Address,bool) override;
    v21pair::TransferReturn submit(const TransferEnvelope&) override;
private:
    Address base_;std::uint32_t owner_;Authority authority_;SubmissionAuthority submission_;
};
}
