#pragma once
#include "preflight/codec.h"
#include "core/spy_send_core.h"
namespace eu4_spy_send_host19 {
using Identity=eu4_spy_host18::Identity;
struct BatchRequest { Identity identity;std::uint64_t expires; };
inline int render(const BatchRequest& r,char* out,std::size_t size) {
    if(!out||!eu4_spy_host18::identity_valid(r.identity)||!r.expires)return -1;
    return std::snprintf(out,size,"EU4SPYSEND/1\npurpose=%s\ngame_sha256=%s\npid=%u\ncreation=%016llx\nsession=%s\ndll_sha256=%s\nmanifest_sha256=%s\nsequence=4\nexpires=%llu\nstage=send_batch\nprofile=spy5_true_state0_v1\nactor=FRA\ntarget=ENG\nvalue=1\nstate=0\nenvoy=-1\n",
        eu4_spy_host18::kPurpose,eu4_spy_host18::kGameSha,r.identity.pid,static_cast<unsigned long long>(r.identity.creation),
        r.identity.session,r.identity.dll_sha256,r.identity.manifest_sha256,static_cast<unsigned long long>(r.expires));
}
inline bool parse(const char* raw,std::size_t size,BatchRequest& out) {
    if(!raw||!size||size>1024||raw[size-1]!='\n')return false;
    char text[1025]{};for(std::size_t i=0;i<size;++i)if((raw[i]<32||raw[i]>126)&&raw[i]!='\n')return false;
    std::memcpy(text,raw,size);char* rows[17]{};char* start=text;unsigned count=0;
    for(std::size_t i=0;i<size;++i)if(text[i]=='\n') { if(count>=17)return false;rows[count++]=start;text[i]=0;start=text+i+1; }
    if(count!=17||std::strcmp(rows[0],"EU4SPYSEND/1"))return false;
    const char* keys[]={"purpose=","game_sha256=","pid=","creation=","session=","dll_sha256=","manifest_sha256=","sequence=","expires=","stage=","profile=","actor=","target=","value=","state=","envoy="};
    const char* values[16]{};for(unsigned i=0;i<16;++i) { const auto n=std::strlen(keys[i]);if(std::strncmp(rows[i+1],keys[i],n))return false;values[i]=rows[i+1]+n; }
    using eu4_spy_host18::lower_hex;
    if(std::strcmp(values[0],eu4_spy_host18::kPurpose)||std::strcmp(values[1],eu4_spy_host18::kGameSha)
        ||!lower_hex(values[3],16)||!lower_hex(values[4],32)||!lower_hex(values[5],64)||!lower_hex(values[6],64))return false;
    BatchRequest r{};std::uint64_t pid=0;
    if(!eu4_spy_host18::decimal(values[2],pid)||pid==0||pid>UINT32_MAX||!eu4_spy_host18::decimal(values[8],r.expires)||!r.expires)return false;
    r.identity.pid=static_cast<std::uint32_t>(pid);
    for(unsigned i=0;i<16;++i)r.identity.creation=(r.identity.creation<<4)|static_cast<unsigned>(values[3][i]<='9'?values[3][i]-'0':values[3][i]-'a'+10);
    std::memcpy(r.identity.session,values[4],33);std::memcpy(r.identity.dll_sha256,values[5],65);std::memcpy(r.identity.manifest_sha256,values[6],65);
    char canonical[1025]{};const int n=render(r,canonical,sizeof(canonical));
    if(n<1||static_cast<std::size_t>(n)!=size||std::memcmp(raw,canonical,size))return false;out=r;return true;
}
inline int render_item(const BatchRequest& r,std::uint32_t item,char* out,std::size_t size) {
    if(!out||item<1||item>5||!r.expires||!eu4_spy_host18::identity_valid(r.identity))return -1;
    return std::snprintf(out,size,"EU4SPYITEM/1\npid=%u\ncreation=%016llx\nsession=%s\ndll_sha256=%s\nmanifest_sha256=%s\nsequence=4\nitem=%u\nfamily=%s\nexpires=%llu\n",
        r.identity.pid,static_cast<unsigned long long>(r.identity.creation),r.identity.session,r.identity.dll_sha256,r.identity.manifest_sha256,
        item,eu4_spy19::family_name(item-1),static_cast<unsigned long long>(r.expires));
}
} // namespace
