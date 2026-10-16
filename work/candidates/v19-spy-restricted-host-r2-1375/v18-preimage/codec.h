#pragma once
#include "../v18-spy-no-send-core-1375/spy_core.h"
#include <cstdio>
#include <cstring>

namespace eu4_spy_host18 {
constexpr std::size_t kWireMax=1024;
constexpr char kGameSha[]="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a";
constexpr char kPurpose[]="restricted_spy_no_send_lab_1375_v18";
constexpr char kProfile[]="spy5_true_state0_v1";
struct Identity { std::uint32_t pid;std::uint64_t creation;char session[33],dll_sha256[65],manifest_sha256[65]; };
struct Request { Identity identity;std::uint32_t sequence;std::uint64_t expires;eu4_spy18::Stage stage; };
inline bool lower_hex(const char* s,std::size_t length) {
    if(!s)return false;bool nonzero=false;
    for(std::size_t i=0;i<length;++i) { if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return false;if(s[i]!='0')nonzero=true; }
    return nonzero && s[length]==0;
}
inline bool identity_valid(const Identity& id) {
    return id.pid!=0 && id.creation!=0 && lower_hex(id.session,32) && lower_hex(id.dll_sha256,64) && lower_hex(id.manifest_sha256,64);
}
inline bool same_identity(const Identity& a,const Identity& b) {
    return a.pid==b.pid && a.creation==b.creation && !std::strcmp(a.session,b.session)
        && !std::strcmp(a.dll_sha256,b.dll_sha256) && !std::strcmp(a.manifest_sha256,b.manifest_sha256);
}
inline const char* stage_name(eu4_spy18::Stage stage) {
    switch(stage) { case eu4_spy18::Stage::lifecycle:return "lifecycle";
        case eu4_spy18::Stage::family_preview:return "family_preview";
        case eu4_spy18::Stage::owned_command:return "owned_command";default:return nullptr; }
}
inline int render(const Request& r,char* out,std::size_t size) {
    const char* stage=stage_name(r.stage);
    if(!out || !identity_valid(r.identity) || !stage || r.sequence!=static_cast<std::uint32_t>(r.stage) || !r.expires)return -1;
    return std::snprintf(out,size,"EU4SPYLAB/1\npurpose=%s\ngame_sha256=%s\npid=%u\ncreation=%016llx\nsession=%s\ndll_sha256=%s\nmanifest_sha256=%s\nsequence=%u\nexpires=%llu\nstage=%s\nprofile=%s\nactor=FRA\ntarget=ENG\nvalue=1\nstate=0\nenvoy=-1\n",
        kPurpose,kGameSha,r.identity.pid,static_cast<unsigned long long>(r.identity.creation),r.identity.session,
        r.identity.dll_sha256,r.identity.manifest_sha256,r.sequence,static_cast<unsigned long long>(r.expires),stage,kProfile);
}
inline bool decimal(const char* text,std::uint64_t& value) {
    if(!text || !*text || (*text=='0' && text[1]))return false;
    std::uint64_t n=0;unsigned count=0;
    for(const char* p=text;*p;++p) { if(++count>20 || *p<'0'||*p>'9')return false;
        const auto digit=static_cast<unsigned>(*p-'0');if(n>(UINT64_MAX-digit)/10)return false;n=n*10+digit; }
    value=n;return true;
}
inline bool parse(const char* raw,std::size_t size,Request& output) {
    if(!raw || !size || size>kWireMax || raw[size-1]!='\n')return false;
    char copy[kWireMax+1]{};
    for(std::size_t i=0;i<size;++i)if((raw[i]<32||raw[i]>126)&&raw[i]!='\n')return false;
    std::memcpy(copy,raw,size);char* lines[18]{};unsigned count=0;char* start=copy;
    for(std::size_t i=0;i<size;++i)if(copy[i]=='\n') { if(count>=18)return false;lines[count++]=start;copy[i]=0;start=copy+i+1; }
    if(count!=17 || std::strcmp(lines[0],"EU4SPYLAB/1"))return false;
    const char* keys[]={"purpose=","game_sha256=","pid=","creation=","session=","dll_sha256=","manifest_sha256=","sequence=","expires=","stage=","profile=","actor=","target=","value=","state=","envoy="};
    const char* values[16]{};
    for(unsigned i=0;i<16;++i) { const auto n=std::strlen(keys[i]);if(std::strncmp(lines[i+1],keys[i],n))return false;values[i]=lines[i+1]+n; }
    if(std::strcmp(values[0],kPurpose)||std::strcmp(values[1],kGameSha)||std::strcmp(values[10],kProfile)
        ||std::strcmp(values[11],"FRA")||std::strcmp(values[12],"ENG")||std::strcmp(values[13],"1")
        ||std::strcmp(values[14],"0")||std::strcmp(values[15],"-1")||!lower_hex(values[3],16)
        ||!lower_hex(values[4],32)||!lower_hex(values[5],64)||!lower_hex(values[6],64))return false;
    Request r{};std::uint64_t pid=0,seq=0;
    if(!decimal(values[2],pid)||!pid||pid>UINT32_MAX||!decimal(values[7],seq)||seq<1||seq>3||!decimal(values[8],r.expires)||!r.expires)return false;
    r.identity.pid=static_cast<std::uint32_t>(pid);r.sequence=static_cast<std::uint32_t>(seq);
    for(unsigned i=0;i<16;++i)r.identity.creation=(r.identity.creation<<4)|static_cast<unsigned>(values[3][i]<='9'?values[3][i]-'0':values[3][i]-'a'+10);
    std::memcpy(r.identity.session,values[4],33);std::memcpy(r.identity.dll_sha256,values[5],65);std::memcpy(r.identity.manifest_sha256,values[6],65);
    r.stage=static_cast<eu4_spy18::Stage>(r.sequence);
    if(std::strcmp(values[9],stage_name(r.stage)))return false;
    char canonical[kWireMax+1]{};const int n=render(r,canonical,sizeof(canonical));
    if(n<1 || static_cast<std::size_t>(n)!=size || std::memcmp(canonical,raw,size))return false;
    output=r;return true; // Failed parse never mutates output.
}
} // namespace eu4_spy_host18
