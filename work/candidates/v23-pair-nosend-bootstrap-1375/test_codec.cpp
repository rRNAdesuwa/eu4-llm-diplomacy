#include "codec.h"
#include <cassert>
#include <string>
#include <algorithm>
pair23::Identity identity() {
 pair23::Identity id{};id.pid=77;id.creation=0x1dd123456789012ULL;
 std::memset(id.session,'1',32);std::memset(id.dll_sha256,'a',64);std::memset(id.manifest_sha256,'b',64);return id;
}
int main() {
 unsigned groups=0;char buffer[1025]{};const auto id=identity();pair23::Identity decoded{};
 const int boot_length=pair23::render_boot(id,buffer,sizeof(buffer));assert(boot_length>0&&boot_length<=1024);
 assert(pair23::parse_boot(buffer,boot_length,decoded)&&eu4_spy_host18::same_identity(id,decoded));++groups;
 for(unsigned action=0;action<12;++action) {
  pair23::Packet p{};p.identity=id;p.sequence=action+1;p.expires=123456;
  assert(v21pair::make_request(pair23::Names[action],"FRA","ENG",p.request));
  const int length=pair23::render(p,buffer,sizeof(buffer));assert(length>0&&length<=1024);pair23::Packet out{};
  assert(pair23::parse(buffer,length,out)&&out.sequence==p.sequence&&out.expires==p.expires&&out.request.action==p.request.action);
  assert(eu4_spy_host18::same_identity(out.identity,id));++groups;
 }
 pair23::Packet p{};p.identity=id;p.sequence=64;p.expires=1;assert(v21pair::make_request("guarantee","FRA","ENG",p.request));
 const int n=pair23::render(p,buffer,sizeof(buffer));const std::string valid(buffer,n);
 for(std::size_t i=0;i<valid.size();++i){pair23::Packet out{};out.sequence=99;assert(!pair23::parse(valid.data(),i,out)&&out.sequence==99);}++groups;
 for(const auto& edit:std::array<std::pair<const char*,const char*>,10>{{
  {"sequence=64","sequence=65"},{"sequence=64","sequence=064"},{"expires=1","expires=0"},{"expires=1","expires=18446744073709551616"},
  {"no_send=1","no_send=0"},{"actor=FRA","actor=fra"},{"target=ENG","target=FRA"},{"actor=FRA","actor=0x12340000"},
  {"action=guarantee","action=unknown"},{"EU4PAIR/1","EU4PAIR/2"}}}) {
  auto changed=valid;const auto at=changed.find(edit.first);assert(at!=std::string::npos);changed.replace(at,std::strlen(edit.first),edit.second);
  pair23::Packet out{};out.sequence=99;assert(!pair23::parse(changed.data(),changed.size(),out)&&out.sequence==99);
 }++groups;
 for(char c:{'\0','\r','\t',static_cast<char>(0x80)}){auto changed=valid;changed[10]=c;pair23::Packet out{};assert(!pair23::parse(changed.data(),changed.size(),out));}++groups;
 {auto changed=valid+"no_send=1\n";pair23::Packet out{};assert(!pair23::parse(changed.data(),changed.size(),out));}++groups;
 {p.sequence=0;assert(pair23::render(p,buffer,sizeof(buffer))<0);p.sequence=65;assert(pair23::render(p,buffer,sizeof(buffer))<0);}++groups;
 {auto changed=valid;const auto a=changed.find("actor=");const auto b=changed.find("target=");std::swap_ranges(changed.begin()+a,changed.begin()+a+5,changed.begin()+b);pair23::Packet out{};assert(!pair23::parse(changed.data(),changed.size(),out));}++groups;
 std::printf("codec_groups=%u native_calls=0 game_access=0\n",groups);return 0;
}
