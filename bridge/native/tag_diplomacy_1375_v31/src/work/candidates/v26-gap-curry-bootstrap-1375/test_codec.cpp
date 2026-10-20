#include "codec.h"
#include <cassert>
#include <string>
#include <algorithm>
tagcommand31::Identity identity() {
 tagcommand31::Identity id{};id.pid=77;id.creation=0x1dd123456789012ULL;
 std::memset(id.session,'1',32);std::memset(id.dll_sha256,'a',64);std::memset(id.manifest_sha256,'b',64);return id;
}
int main() {
 unsigned groups=0;char buffer[1025]{};const auto id=identity();tagcommand31::Identity decoded{};
 const int boot_length=tagcommand31::render_boot(id,buffer,sizeof(buffer));assert(boot_length>0&&boot_length<=1024);
 assert(tagcommand31::parse_boot(buffer,boot_length,decoded)&&eu4_spy_host18::same_identity(id,decoded));++groups;
 for(unsigned action=0;action<v21pair::ActionCount;++action) {
  tagcommand31::Packet p{};p.identity=id;p.sequence=action%64+1;p.expires=123456;
  assert(v21pair::make_request(tagcommand31::Names[action],"FRA","ENG",p.request));
  const int length=tagcommand31::render(p,buffer,sizeof(buffer));assert(length>0&&length<=1024);tagcommand31::Packet out{};
  assert(tagcommand31::parse(buffer,length,out)&&out.sequence==p.sequence&&out.expires==p.expires&&out.request.action==p.request.action);
  assert(eu4_spy_host18::same_identity(out.identity,id));++groups;
 }
 tagcommand31::Packet p{};p.identity=id;p.sequence=128;p.expires=1;assert(v21pair::make_request("trade_favors_for_gold","FRA","ENG",p.request));
 const int n=tagcommand31::render(p,buffer,sizeof(buffer));const std::string valid(buffer,n);
 for(std::size_t i=0;i<valid.size();++i){tagcommand31::Packet out{};out.sequence=99;assert(!tagcommand31::parse(valid.data(),i,out)&&out.sequence==99);}++groups;
 for(const auto& edit:std::array<std::pair<const char*,const char*>,10>{{
  {"sequence=128","sequence=129"},{"sequence=128","sequence=0128"},{"expires=1","expires=0"},{"expires=1","expires=18446744073709551616"},
  {"send=1","send=0"},{"actor=FRA","actor=fra"},{"target=ENG","target=FRA"},{"actor=FRA","actor=0x12340000"},
  {"action=trade_favors_for_gold","action=unknown"},{"EU4TAGCOMMAND/1","EU4PAIRSEND/2"}}}) {
  auto changed=valid;const auto at=changed.find(edit.first);assert(at!=std::string::npos);changed.replace(at,std::strlen(edit.first),edit.second);
  tagcommand31::Packet out{};out.sequence=99;assert(!tagcommand31::parse(changed.data(),changed.size(),out)&&out.sequence==99);
 }++groups;
 for(char c:{'\0','\r','\t',static_cast<char>(0x80)}){auto changed=valid;changed[10]=c;tagcommand31::Packet out{};assert(!tagcommand31::parse(changed.data(),changed.size(),out));}++groups;
 {auto changed=valid+"send=1\n";tagcommand31::Packet out{};assert(!tagcommand31::parse(changed.data(),changed.size(),out));}++groups;
 {p.sequence=0;assert(tagcommand31::render(p,buffer,sizeof(buffer))<0);p.sequence=129;assert(tagcommand31::render(p,buffer,sizeof(buffer))<0);}++groups;
 {auto changed=valid;const auto a=changed.find("actor=");const auto b=changed.find("target=");std::swap_ranges(changed.begin()+a,changed.begin()+a+5,changed.begin()+b);tagcommand31::Packet out{};assert(!tagcommand31::parse(changed.data(),changed.size(),out));}++groups;
 {v21pair::PairStamp s{};s.process_creation=s.session=s.module_pin=s.owner_thread=s.world_witness=1;
  s.database=0x10000;s.game=0x20000;s.array=0x30000;s.actor_object=0x40000;s.target_object=0x50000;s.count=200;s.date=1;
  s.actor.value=0x0100000000000000ULL|(122ULL<<32)|0x415246;s.target.value=0x0100000000000000ULL|(46ULL<<32)|0x474e45;
  s.current_player.value=0x0100000000000000ULL|(189ULL<<32)|0x524f50;s.effective_player=s.current_player;
  assert(v21pair::valid(s));auto changed=s;changed.effective_player=s.actor;assert(!v21pair::valid(changed));
  changed=s;changed.current_player=s.actor;changed.effective_player=s.actor;assert(!(s==changed));++groups;}
 std::printf("codec_groups=%u native_calls=0 game_access=0\n",groups);return 0;
}
