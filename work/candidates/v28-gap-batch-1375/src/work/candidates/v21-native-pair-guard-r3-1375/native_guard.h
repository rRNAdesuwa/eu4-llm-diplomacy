#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "native_env.h"
#include "../current-country-tag-cpp-r2-1375/country_resolver.h"
#include "../v21-five-cancel-reader-1375/cancel_reader.h"
#include "../v21-native-pair-port-r2-1375/native_platform.h"

namespace v21guard {
// Private composition with the already reviewed NativeEnvironment. The
// Environment value must come from its actual initialize() in a future Host.
// Fake tests inject function callbacks only; that is not actual attestation.
class NativePairGuardDraft final : public v21pair::SyntheticGuard,
    public country1375::ReadPort, public v21pair::SyntheticReadPort {
public:
    explicit NativePairGuardDraft(const eu4_spy_host18::Environment&) noexcept;
    bool begin_frame() noexcept;
    // One lease only. A future Host must hold its durable claim before this call.
    // This class does not create claims, requests, DLLs, exports or a sender.
    bool lease(const v21pair::Request&,std::uint64_t original_expires) noexcept;
    std::uint64_t clock() override;
    bool stamp(const v21pair::Request&,v21pair::PairStamp&) override;
    bool cancellation(v21pair::Family,const v21pair::PairStamp&,v21pair::CancelObservation&) override;
    bool read(std::uint64_t,void*,std::size_t) override;
    v21port::Authority authority() noexcept;
    std::uint64_t module() const noexcept {return env_.image_base;}
    std::uint32_t owner() const noexcept {return env_.owner_thread;}
    bool frozen() const noexcept {return failed_;}
    const v21pair::PairStamp& baseline() const noexcept {return baseline_;}
private:
    eu4_spy_host18::Environment env_;
    eu4_spy_host18::Frame world_{};
    v21pair::Request request_{};
    v21pair::PairStamp baseline_{};
    country1375::Roots roots_{};
    cancel1375::Snapshot cancel_{};
    v21pair::SpyBinding spy_{};bool spy_bound_{};
    std::uint64_t expires_{},last_clock_{},frames_{};
    bool attempted_{},bound_{},failed_{},busy_{},got_clock_{},cancel_bound_{};
    bool fail() noexcept {failed_=true;return false;}
    bool environment() noexcept;
    bool health(eu4_spy_host18::Frame&) noexcept;
    bool sample_pair(const v21pair::Request&,v21pair::PairStamp&,country1375::Roots&) noexcept;
    bool light() noexcept;
    bool final(bool cleanup) noexcept;
    template<class T> bool get(std::uint64_t p,T& value) {return read(p,&value,sizeof(value));}
    static bool fresh_cb(void*,v21port::Address,std::uint32_t);
    static bool final_cb(void*,v21port::Call);
    static bool write_cb(void*);
};
}
