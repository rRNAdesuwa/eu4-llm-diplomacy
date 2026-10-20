#include "codec.h"
#include <cassert>
#include <string>
#include <algorithm>
pair28::Identity identity() {
 pair28::Identity id{};id.pid=77;id.creation=0x1dd123456789012ULL;
 std::memset(id.session,'1',32);std::memset(id.dll_sha256,'a',64);std::memset(id.manifest_sha256,'b',64);return id;
}
int main() {
 unsigned groups=0;char buffer[1025]{};const auto id=identity();pair28::Identity decoded{};
 const int boot_length=pair28::render_boot(id,buffer,sizeof(buffer));assert(boot_length>0&&boot_length<=1024);
 assert(pair28::parse_boot(buffer,boot_length,decoded)&&eu4_spy_host18::same_identity(id,decoded));++groups;
 for(unsigned action=0;action<17;++action) {
  pair28::Packet p{};p.identity=id;p.sequence=action+1;p.expires=123456;
  assert(v21pair::make_request(pair28::Names[action],"FRA","ENG",p.request));
  const int length=pair28::render(p,buffer,sizeof(buffer));if(action!=11 && action<14){assert(length<0);++groups;continue;} assert(length>0&&length<=1024);pair28::Packet out{};
  assert(pair28::parse(buffer,length,out)&&out.sequence==p.sequence&&out.expires==p.expires&&out.request.action==p.request.action);
  assert(eu4_spy_host18::same_identity(out.identity,id));++groups;
 }
 pair28::Packet p{};p.identity=id;p.sequence=64;p.expires=1;assert(v21pair::make_request("stop_currying_favors","FRA","ENG",p.request));
 const int n=pair28::render(p,buffer,sizeof(buffer));const std::string valid(buffer,n);
 for(std::size_t i=0;i<valid.size();++i){pair28::Packet out{};out.sequence=99;assert(!pair28::parse(valid.data(),i,out)&&out.sequence==99);}++groups;
 for(const auto& edit:std::array<std::pair<const char*,const char*>,10>{{
  {"sequence=64","sequence=65"},{"sequence=64","sequence=064"},{"expires=1","expires=0"},{"expires=1","expires=18446744073709551616"},
  {"send=1","send=0"},{"actor=FRA","actor=fra"},{"target=ENG","target=FRA"},{"actor=FRA","actor=0x12340000"},
  {"action=stop_currying_favors","action=unknown"},{"EU4PAIRSEND/1","EU4PAIRSEND/2"}}}) {
  auto changed=valid;const auto at=changed.find(edit.first);assert(at!=std::string::npos);changed.replace(at,std::strlen(edit.first),edit.second);
  pair28::Packet out{};out.sequence=99;assert(!pair28::parse(changed.data(),changed.size(),out)&&out.sequence==99);
 }++groups;
 for(char c:{'\0','\r','\t',static_cast<char>(0x80)}){auto changed=valid;changed[10]=c;pair28::Packet out{};assert(!pair28::parse(changed.data(),changed.size(),out));}++groups;
 {auto changed=valid+"send=1\n";pair28::Packet out{};assert(!pair28::parse(changed.data(),changed.size(),out));}++groups;
 {p.sequence=0;assert(pair28::render(p,buffer,sizeof(buffer))<0);p.sequence=65;assert(pair28::render(p,buffer,sizeof(buffer))<0);}++groups;
 {auto changed=valid;const auto a=changed.find("actor=");const auto b=changed.find("target=");std::swap_ranges(changed.begin()+a,changed.begin()+a+5,changed.begin()+b);pair28::Packet out{};assert(!pair28::parse(changed.data(),changed.size(),out));}++groups;
 std::printf("codec_groups=%u native_calls=0 game_access=0\n",groups);return 0;
}
