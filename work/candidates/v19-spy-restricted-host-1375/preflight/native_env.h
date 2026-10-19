#pragma once
#include "host.h"
namespace eu4_spy_host18 {
// Private future bootstrap inputs, not public request fields. No bootstrap,
// DLL export, owner-hook installer or loader is implemented by this candidate.
struct Bootstrap {
    Identity expected;const wchar_t* manifest_path;bool disposable_test_authorized;
};
class NativeEnvironment {
public:
    NativeEnvironment() noexcept;~NativeEnvironment();
    NativeEnvironment(const NativeEnvironment&)=delete;NativeEnvironment& operator=(const NativeEnvironment&)=delete;
    bool initialize(const Bootstrap&,Environment&);
private:
    friend struct NativeEnvironmentTests; // Isolated-memory tests only, no exported entry.
    HANDLE files_[3];std::uintptr_t base_;std::uint32_t owner_,calls_;std::size_t bytes_;
    bool attempted_,ready_,failed_;
    bool read(std::uintptr_t,void*,std::size_t);bool write(std::uintptr_t,const void*,std::size_t);
    bool sample(Frame&);bool image();bool multiplayer(std::uintptr_t,std::uintptr_t,bool&);
    template<class T> bool get(std::uintptr_t p,T& v) { return read(p,&v,sizeof(v)); }
    static bool read_cb(void*,std::uintptr_t,void*,std::size_t);static bool write_cb(void*,std::uintptr_t,const void*,std::size_t);
    static std::uintptr_t resolve_cb(void*,std::uintptr_t);static std::uint64_t clock_cb(void*);
    static bool sample_cb(void*,Frame*);static std::uint32_t thread_cb(void*);static bool frame_cb(void*);
};
}
