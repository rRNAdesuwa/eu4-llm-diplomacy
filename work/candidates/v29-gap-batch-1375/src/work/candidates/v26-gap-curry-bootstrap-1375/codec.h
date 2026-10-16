#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "../v19-spy-restricted-host-r2-1375/preflight/codec.h"
#include "../v21-core-pair-nosend-r2-1375/pair_component.h"
#include <array>
namespace pair29 {
using Identity=eu4_spy_host18::Identity;
constexpr char Purpose[]="restricted_pair_send_1375_v29";
constexpr wchar_t DllName[]=L"eu4_pair_send_lab_1375_v29.dll";
inline constexpr std::array<const char*,21> Names{{"offer_vassalization","cancel_vassalization","royal_marriage","break_marriage",
 "improve_relations","stop_improving_relations","guarantee","revoke_guarantee","build_spy_network","stop_building_spy_network","curry_favors","stop_currying_favors","offer_fleet_basing_rights","insult","form_coalition","support_independence","trade_favors_for_gold","trade_favors_for_men","trade_favors_for_sailors","trade_favors_for_trust","trade_favors_for_war_prep"}};
struct Packet {Identity identity{};std::uint32_t sequence{};std::uint64_t expires{};v21pair::Request request{};};
struct Lines {char data[1025]{};const char* values[16]{};};
inline bool lines(const char* raw,std::size_t n,const char* header,const char* const* keys,unsigned count,Lines& out) {
 if(!raw||!n||n>1024||raw[n-1]!='\n'||count>16)return false;
 for(std::size_t i=0;i<n;++i)if((raw[i]<32||raw[i]>126)&&raw[i]!='\n')return false;
 std::memcpy(out.data,raw,n);char* start=out.data;unsigned line=0;
 for(std::size_t i=0;i<n;++i)if(out.data[i]=='\n') {
  out.data[i]=0;
  if(line==0){if(std::strcmp(start,header))return false;}
  else {if(line>count)return false;const auto k=std::strlen(keys[line-1]);if(std::strncmp(start,keys[line-1],k))return false;out.values[line-1]=start+k;}
  ++line;start=out.data+i+1;
 }
 return line==count+1;
}
inline bool identity(const Lines& l,Identity& out) {
 using namespace eu4_spy_host18;
 if(std::strcmp(l.values[0],Purpose)||std::strcmp(l.values[1],kGameSha)||!lower_hex(l.values[3],16)
  ||!lower_hex(l.values[4],32)||!lower_hex(l.values[5],64)||!lower_hex(l.values[6],64))return false;
 std::uint64_t pid=0;if(!decimal(l.values[2],pid)||!pid||pid>UINT32_MAX)return false;
 Identity id{};id.pid=static_cast<std::uint32_t>(pid);
 for(unsigned i=0;i<16;++i)id.creation=(id.creation<<4)|static_cast<unsigned>(l.values[3][i]<='9'?l.values[3][i]-'0':l.values[3][i]-'a'+10);
 std::memcpy(id.session,l.values[4],33);std::memcpy(id.dll_sha256,l.values[5],65);std::memcpy(id.manifest_sha256,l.values[6],65);
 if(!identity_valid(id))return false;out=id;return true;
}
inline int render_boot(const Identity& id,char* out,std::size_t size) {
 if(!out||!eu4_spy_host18::identity_valid(id))return -1;
 return std::snprintf(out,size,"EU4PAIRSENDBOOT/1\npurpose=%s\ngame_sha256=%s\npid=%u\ncreation=%016llx\nsession=%s\ndll_sha256=%s\nmanifest_sha256=%s\ndisposable=1\nsend=1\n",
 Purpose,eu4_spy_host18::kGameSha,id.pid,static_cast<unsigned long long>(id.creation),id.session,id.dll_sha256,id.manifest_sha256);
}
inline bool parse_boot(const char* raw,std::size_t n,Identity& out) {
 const char* keys[]={"purpose=","game_sha256=","pid=","creation=","session=","dll_sha256=","manifest_sha256=","disposable=","send="};
 Lines l{};Identity id{};if(!lines(raw,n,"EU4PAIRSENDBOOT/1",keys,9,l)||!identity(l,id)||std::strcmp(l.values[7],"1")||std::strcmp(l.values[8],"1"))return false;
 char exact[1025]{};const int length=render_boot(id,exact,sizeof(exact));
 if(length<1||static_cast<std::size_t>(length)!=n||std::memcmp(exact,raw,n))return false;out=id;return true;
}
inline int render(const Packet& p,char* out,std::size_t n) {
 const auto a=static_cast<unsigned>(p.request.action);
 if(!out||!eu4_spy_host18::identity_valid(p.identity)||p.sequence<1||p.sequence>64||!p.expires||a>=Names.size()||(a<16))return -1;
 v21pair::Request check{};
 if(!v21pair::make_request(Names[a],std::string_view(p.request.actor.bytes.data(),3),std::string_view(p.request.target.bytes.data(),3),check))return -1;
 return std::snprintf(out,n,"EU4PAIRSEND/1\npurpose=%s\ngame_sha256=%s\npid=%u\ncreation=%016llx\nsession=%s\ndll_sha256=%s\nmanifest_sha256=%s\nsequence=%u\nexpires=%llu\naction=%s\nactor=%.3s\ntarget=%.3s\nsend=1\n",
 Purpose,eu4_spy_host18::kGameSha,p.identity.pid,static_cast<unsigned long long>(p.identity.creation),p.identity.session,p.identity.dll_sha256,p.identity.manifest_sha256,
 p.sequence,static_cast<unsigned long long>(p.expires),Names[a],p.request.actor.bytes.data(),p.request.target.bytes.data());
}
inline bool parse(const char* raw,std::size_t n,Packet& out) {
 const char* keys[]={"purpose=","game_sha256=","pid=","creation=","session=","dll_sha256=","manifest_sha256=","sequence=","expires=","action=","actor=","target=","send="};
 Lines l{};Packet p{};std::uint64_t seq=0;
 if(!lines(raw,n,"EU4PAIRSEND/1",keys,13,l)||!identity(l,p.identity)||!eu4_spy_host18::decimal(l.values[7],seq)||seq<1||seq>64
  ||!eu4_spy_host18::decimal(l.values[8],p.expires)||!p.expires||std::strcmp(l.values[12],"1")
  ||!v21pair::make_request(l.values[9],l.values[10],l.values[11],p.request))return false;
 p.sequence=static_cast<std::uint32_t>(seq);char exact[1025]{};const int length=render(p,exact,sizeof(exact));
 if(length<1||static_cast<std::size_t>(length)!=n||std::memcmp(exact,raw,n))return false;out=p;return true;
}
}
