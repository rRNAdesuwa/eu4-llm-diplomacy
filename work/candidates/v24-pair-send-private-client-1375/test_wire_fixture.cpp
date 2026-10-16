#include "../v24-pair-send-bootstrap-1375/codec.h"
#include <cassert>
void output(const char* bytes,int length) {
 assert(length>0&&length<=1024);
 for(int i=0;i<length;++i)std::printf("%02x",static_cast<unsigned char>(bytes[i]));
 std::puts("");
}
int main() {
 pair24::Identity id{};id.pid=77;id.creation=0x01dd123456789012ULL;
 std::memset(id.session,'1',32);std::memset(id.dll_sha256,'a',64);
 std::memcpy(id.manifest_sha256,"3e6a875c0dbe622d83e51b14a3a3d5206b614b7206eb600a62fa4a6a1d5b8268",65);
 char bytes[1025]{};output(bytes,pair24::render_boot(id,bytes,sizeof(bytes)));
 for(unsigned i=0;i<6;++i) {
  pair24::Packet p{};p.identity=id;p.sequence=i+1;p.expires=123456;
  assert(v21pair::make_request(pair24::Names[i*2],"FRA","ENG",p.request));
  const auto n=pair24::render(p,bytes,sizeof(bytes));pair24::Packet parsed{};
  assert(n>0&&pair24::parse(bytes,n,parsed));output(bytes,n);
 }
}
