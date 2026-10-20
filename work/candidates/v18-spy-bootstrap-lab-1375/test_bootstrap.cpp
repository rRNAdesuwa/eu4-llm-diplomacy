#include "bootstrap_codec.h"
#include "scheduler.h"
#include <cstdio>
#include <cstring>
#include <initializer_list>
namespace {
unsigned checks=0,failures=0;
void check(bool value) { ++checks;if(!value)++failures; }
}
int main() {
    using namespace eu4_spy_boot18;
    Identity id{};id.pid=123;id.creation=0x01dd500000000001ULL;
    std::memset(id.session,'a',32);std::memset(id.dll_sha256,'b',64);std::memset(id.manifest_sha256,'c',64);
    char raw[1025]{};const int n=render_boot(id,raw,sizeof(raw));check(n>0&&n<=1024);
    Identity decoded{};check(parse_boot(raw,static_cast<std::size_t>(n),decoded)&&eu4_spy_host18::same_identity(id,decoded));
    for(int i=0;i<n;++i) {
        char changed[1025]{};std::memcpy(changed,raw,static_cast<std::size_t>(n));changed[i]='\r';
        Identity out=id;check(!parse_boot(changed,static_cast<std::size_t>(n),out)&&!std::memcmp(&out,&id,sizeof(id)));
    }
    check(!parse_boot(nullptr,1,decoded));check(!parse_boot(raw,0,decoded));check(!parse_boot(raw,1025,decoded));
    check(!parse_boot(raw,static_cast<std::size_t>(n-1),decoded));
    for(int invalid:{0,1,31,127,255}) {
        char changed[1025]{};std::memcpy(changed,raw,static_cast<std::size_t>(n));changed[0]=static_cast<char>(invalid);
        check(!parse_boot(changed,static_cast<std::size_t>(n),decoded));
    }
    Scheduler s{};check(s.start(7));check(s.enter(7,1000));check(s.owner_entries==1&&s.should_poll());
    check(s.decide(false)==Decision::health);check(s.enter(7,1050));check(!s.should_poll());
    check(s.enter(7,1100));check(s.should_poll());check(s.decide(false)==Decision::wait);
    check(s.enter(7,1200));check(s.decide(true)==Decision::request);check(s.owner_entries==4);
    check(s.enter(7,2200));check(s.decide(false)==Decision::health);s.finish();check(!s.should_poll());
    check(s.enter(7,2300));check(s.decide(true)==Decision::wait);
    for(unsigned scenario=0;scenario<4;++scenario) {
        Scheduler test{};check(test.start(7));check(test.enter(7,100));
        if(scenario==0)check(!test.enter(8,101));
        if(scenario==1)check(!test.enter(7,99));
        if(scenario==2)check(!test.start(7));
        if(scenario==3) { test.fail();check(!test.enter(7,101)); }
        check(test.frozen);check(test.decide(true)==Decision::terminal);check(!test.enter(7,102));
    }
    Scheduler zero{};check(!zero.start(0)&&zero.frozen);
    std::printf("bootstrap_codec_scheduler checks=%u failures=%u\n",checks,failures);
    return failures?1:0;
}
