// Link the exact production bootstrap/Host objects, but call only its private
// admission wrapper with synthetic packets/callbacks. Never call BridgeStart.
#include "bootstrap.cpp"
#include <cstdio>

namespace {
unsigned checks=0,failures=0,mock_claims=0;bool mock_accept=true;
void check(bool value) { ++checks;if(!value)++failures; }
bool claim_sink(void*,std::uint32_t,std::uint32_t,const char*,std::size_t) { ++mock_claims;return mock_accept; }
void reset_mock() {
    // These resets exist only in this standalone isolated test executable.
    InterlockedExchange(&frozen,0);in_controller=true;original.owner_thread=GetCurrentThreadId();
    durable={nullptr,nullptr,claim_sink};input_file=INVALID_HANDLE_VALUE;input_sequence=0;input_length=0;
    stage_claims=batch_item_claims=0;batch_claim_bound=false;fixed_batch={};mock_claims=0;mock_accept=true;
}
host::Identity test_id() {
    host::Identity id{};id.pid=123;id.creation=0x01dd500000000001ULL;
    std::memset(id.session,'a',32);std::memset(id.dll_sha256,'b',64);std::memset(id.manifest_sha256,'c',64);return id;
}
bool stage_packet(unsigned q) {
    input_sequence=q;input_file=reinterpret_cast<HANDLE>(static_cast<std::uintptr_t>(0x10000));
    int n=0;
    if(q<4) { preflight::Request r{test_id(),q,60000,static_cast<eu4_spy18::Stage>(q)};n=preflight::render(r,input_packet,sizeof(input_packet)); }
    else { fixed_batch={test_id(),60000};n=host::render(fixed_batch,input_packet,sizeof(input_packet)); }
    if(n<1)return false;input_length=static_cast<std::size_t>(n);
    return raw_claim(nullptr,q,0,input_packet,input_length);
}
void batch_ready() {
    for(unsigned q=1;q<=4;++q)check(stage_packet(q));
    input_file=INVALID_HANDLE_VALUE;input_sequence=0;
}
bool child(unsigned q) {
    char raw[1025]{};const int n=host::render_item(fixed_batch,q,raw,sizeof(raw));
    return n>0&&raw_claim(nullptr,4,q,raw,static_cast<std::size_t>(n));
}
}
int main() {
    reset_mock();batch_ready();for(unsigned q=1;q<=5;++q)check(child(q));check(mock_claims==9&&batch_item_claims==5&&stage_claims==4);
    check(!child(5)&&!running()&&mock_claims==9);
    reset_mock();check(stage_packet(1));check(!stage_packet(1)&&!running()&&mock_claims==1);
    reset_mock();check(!stage_packet(2)&&!running()&&mock_claims==0);
    reset_mock();check(!stage_packet(4)&&!running()&&mock_claims==0);
    reset_mock();batch_ready();check(!child(2)&&!running()&&mock_claims==4);
    reset_mock();batch_ready();input_file=reinterpret_cast<HANDLE>(static_cast<std::uintptr_t>(0x10000));check(!child(1)&&!running()&&mock_claims==4);
    reset_mock();batch_ready();char raw[1025]{};int n=host::render_item(fixed_batch,1,raw,sizeof(raw));raw[n-2]='9';
    check(!raw_claim(nullptr,4,1,raw,static_cast<std::size_t>(n))&&!running()&&mock_claims==4);
    reset_mock();mock_accept=false;check(!stage_packet(1)&&!running()&&mock_claims==1&&stage_claims==0);check(!stage_packet(1)&&mock_claims==1);
    reset_mock();in_controller=false;check(!stage_packet(1)&&!running()&&mock_claims==0);
    reset_mock();original.owner_thread=GetCurrentThreadId()+1;check(!stage_packet(1)&&!running()&&mock_claims==0);
    reset_mock();input_sequence=1;input_file=reinterpret_cast<HANDLE>(static_cast<std::uintptr_t>(0x10000));
    check(!raw_claim(nullptr,1,0,nullptr,1)&&!running()&&mock_claims==0);
    std::printf("isolated_bootstrap_claim_checks=%u failures=%u game_accessed=false\n",checks,failures);return failures?1:0;
}
