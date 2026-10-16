#pragma once
#include "native_platform.h"
namespace v24port {
// A future private Host binds this to the actual same NativePairGuard lease.
// Injected callbacks do not certify OS identity/SP/epoch by themselves.
struct SubmissionEnvironment {
    Address base{};std::uint64_t original_expires{};void* user{};
    bool (*world)(void*){};
    bool (*read)(void*,Address,void*,std::size_t){};
    std::uint64_t (*clock)(void*){};
};
class SubmissionGuard {
public:
    explicit SubmissionGuard(SubmissionEnvironment e) noexcept:env_(e){}
    SubmissionAuthority authority() noexcept {return {this,prepare_cb,final_cb};}
private:
    SubmissionEnvironment env_;SubmissionContext prepared_{};bool attempted_{},final_attempted_{},failed_{};
    unsigned reads_{};std::uint64_t last_clock_{};
    bool read(Address,void*,std::size_t);
    template<class T>bool at(Address p,std::uint32_t off,T& out){return p>=0x10000 && (p&7)==0 && p<0x800000000000ULL-0x810 && read(p+off,&out,sizeof(out));}
    bool context(SubmissionContext&);
    bool owned(const TransferEnvelope&);
    bool prepare(SubmissionContext&);
    bool final(const SubmissionContext&,const TransferEnvelope&);
    static bool prepare_cb(void*,SubmissionContext&);
    static bool final_cb(void*,const SubmissionContext&,const TransferEnvelope&);
};
}
