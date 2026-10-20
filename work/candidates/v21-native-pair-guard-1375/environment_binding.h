#pragma once
#include "native_guard.h"
namespace v21guard {
// Compile-only actual binding path. No export or invocation is supplied.
class CompiledEnvironmentBinding {
public:
    bool initialize(const eu4_spy_host18::Bootstrap&);
    const eu4_spy_host18::Environment* environment() const noexcept {return ready_?&environment_:nullptr;}
private:
    eu4_spy_host18::NativeEnvironment native_;
    eu4_spy_host18::Environment environment_{};
    bool attempted_{},ready_{};
};
}
