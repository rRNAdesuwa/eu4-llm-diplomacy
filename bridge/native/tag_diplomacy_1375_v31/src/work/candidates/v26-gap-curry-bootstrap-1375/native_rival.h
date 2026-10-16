#pragma once
#include "../v21-native-pair-guard-r3-1375/native_guard.h"
#include "../v24-pair-send-port-r2-1375/native_pair_engine.h"
namespace tagcommand31 {
struct RivalResult {v21pair::SendResult result{};v24port::Diagnostics diagnostics{};};
using Audit=bool(*)(const char*,const char*,...);
RivalResult rival(const v21pair::Request&,v21guard::NativePairGuardDraft&,v24port::Platform&,std::uint64_t,Audit) noexcept;
}
