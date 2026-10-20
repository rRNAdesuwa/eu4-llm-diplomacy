#include "../v22-pair-nosend-bootstrap-1375/codec.h"
#include <cassert>
void output(const char* bytes,int length) {
 assert(length>0&&length<=1024);
 for(int i=0;i<length;++i)std::printf("%02x",static_cast<unsigned char>(bytes[i]));
 std::puts("");
}
int main() {
 pair22::Identity id{};id.pid=77;id.creation=0x01dd123456789012ULL;
 std::memset(id.session,'1',32);std::memset(id.dll_sha256,'a',64);
 std::memcpy(id.manifest_sha256,"a938c06e8acd8ff1be9fe8606aeba882d3d8baeeb3acb6b3575156146f8f0aae",65);
 char bytes[1025]{};output(bytes,pair22::render_boot(id,bytes,sizeof(bytes)));
 for(unsigned i=0;i<6;++i) {
  pair22::Packet p{};p.identity=id;p.sequence=i+1;p.expires=123456;
  assert(v21pair::make_request(pair22::Names[i*2],"FRA","ENG",p.request));
  const auto n=pair22::render(p,bytes,sizeof(bytes));pair22::Packet parsed{};
  assert(n>0&&pair22::parse(bytes,n,parsed));output(bytes,n);
 }
}
