#pragma once
#include <Windows.h>
#include <cstdint>
#include <cstddef>
namespace eu4_spy_boot18 {
using InstallLog=bool(*)(void*,const char*,std::size_t);
// Private, fixed frame target. There is no request-selectable RVA or stub.
bool install_owner_hook(std::uintptr_t game_base,InstallLog,void*);
}
