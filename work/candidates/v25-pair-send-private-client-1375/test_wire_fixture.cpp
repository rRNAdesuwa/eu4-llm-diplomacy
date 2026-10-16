#include "../v25-pair-send-bootstrap-1375/codec.h"
#include <cassert>
void output(const char* bytes,int length) {
 assert(length>0&&length<=1024);
 for(int i=0;i<length;++i)std::printf("%02x",static_cast<unsigned char>(bytes[i]));
 std::puts("");
}
int main() {
 pair25::Identity id{};id.pid=77;id.creation=0x01dd123456789012ULL;
 std::memset(id.session,'1',32);std::memset(id.dll_sha256,'a',64);
 std::memcpy(id.manifest_sha256,"40738e72bdbf1c6442d9a6b55ef83ac6bf8e6211669db9b83bda41660e8f9929",65);
 char bytes[1025]{};output(bytes,pair25::render_boot(id,bytes,sizeof(bytes)));
 for(unsigned i=0;i<6;++i) {
  pair25::Packet p{};p.identity=id;p.sequence=i+1;p.expires=123456;
  assert(v21pair::make_request(pair25::Names[i*2],"FRA","ENG",p.request));
  const auto n=pair25::render(p,bytes,sizeof(bytes));pair25::Packet parsed{};
  assert(n>0&&pair25::parse(bytes,n,parsed));output(bytes,n);
 }
}
