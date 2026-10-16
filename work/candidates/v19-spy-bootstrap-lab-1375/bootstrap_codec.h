#pragma once
#include "../v19-spy-restricted-host-r2-1375/preflight/codec.h"

namespace eu4_spy_boot19 {
using eu4_spy_host18::Identity;
constexpr char kBootstrapSchema[]="EU4SPYBOOT19/1";
constexpr wchar_t kDllName[]=L"eu4_spy_send_lab_1375_v19.dll";
// Private bootstrap file, derived from current PID+creation beside this DLL.
// It contains no pointers, directories, arbitrary action or call target.
inline int render_boot(const Identity& id,char* out,std::size_t size) {
    if(!out||!eu4_spy_host18::identity_valid(id))return -1;
    return std::snprintf(out,size,"EU4SPYBOOT19/1\npurpose=%s\ngame_sha256=%s\npid=%u\ncreation=%016llx\nsession=%s\ndll_sha256=%s\nmanifest_sha256=%s\ndisposable_test=1\nrestricted_spy_send=1\n",
        eu4_spy_host18::kPurpose,eu4_spy_host18::kGameSha,id.pid,static_cast<unsigned long long>(id.creation),
        id.session,id.dll_sha256,id.manifest_sha256);
}
inline bool parse_boot(const char* raw,std::size_t length,Identity& out) {
    if(!raw||!length||length>1024||raw[length-1]!='\n')return false;
    char copy[1025]{};std::memcpy(copy,raw,length);char* lines[10]{};unsigned count=0;char* next=copy;
    for(std::size_t i=0;i<length;++i) {
        if((raw[i]<32||raw[i]>126)&&raw[i]!='\n')return false;
        if(copy[i]=='\n') { if(count==10)return false;lines[count++]=next;copy[i]=0;next=copy+i+1; }
    }
    if(count!=10||std::strcmp(lines[0],kBootstrapSchema))return false;
    constexpr const char* keys[]={"purpose=","game_sha256=","pid=","creation=","session=","dll_sha256=","manifest_sha256=","disposable_test=","restricted_spy_send="};
    const char* values[9]{};
    for(unsigned i=0;i<9;++i) { const auto n=std::strlen(keys[i]);if(std::strncmp(lines[i+1],keys[i],n))return false;values[i]=lines[i+1]+n; }
    using namespace eu4_spy_host18;
    if(std::strcmp(values[0],kPurpose)||std::strcmp(values[1],kGameSha)||!lower_hex(values[3],16)
        ||!lower_hex(values[4],32)||!lower_hex(values[5],64)||!lower_hex(values[6],64)
        ||std::strcmp(values[7],"1")||std::strcmp(values[8],"1"))return false;
    std::uint64_t pid=0;if(!decimal(values[2],pid)||!pid||pid>UINT32_MAX)return false;
    Identity id{};id.pid=static_cast<std::uint32_t>(pid);
    for(unsigned i=0;i<16;++i)id.creation=(id.creation<<4)|static_cast<unsigned>(values[3][i]<='9'?values[3][i]-'0':values[3][i]-'a'+10);
    std::memcpy(id.session,values[4],33);std::memcpy(id.dll_sha256,values[5],65);std::memcpy(id.manifest_sha256,values[6],65);
    char expected[1025]{};const int n=render_boot(id,expected,sizeof(expected));
    if(n<1||static_cast<std::size_t>(n)!=length||std::memcmp(raw,expected,length))return false;
    out=id;return true;
}
}
