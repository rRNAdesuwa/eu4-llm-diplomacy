#define main sealed_core_mock_main
#include "../v18-spy-no-send-core-1375/test_spy_core.cpp"
#undef main
#include "host.h"
#include "journal.h"
#include <string>
#include <fstream>

namespace h18=eu4_spy_host18;
namespace {
struct Rig {
    Mock mock;h18::Controller controller;h18::Environment env{};h18::Journal journal{};h18::Frame observed{};
    std::vector<std::string> records,claims;unsigned appends=0,fail_append=0,samples=0;bool fail_claim=false,reenter=false,wrong_thread=false;
    bool change_second=false,expire_claim=false,reenter_resolve=false;std::uint64_t wire_expiry=70000;
    Rig() {
        env.identity.pid=1234;env.identity.creation=0x123456789abcdefULL;
        std::memset(env.identity.session,'a',32);std::memset(env.identity.dll_sha256,'b',64);std::memset(env.identity.manifest_sha256,'c',64);
        observed.stamp={GAME,DB,COUNTRIES,FRA,ENG,SERVER,PAUSE,FRA_HANDLE,ENG_HANDLE,FRA_HANDLE,DATE};
        observed.countries_count=4096;observed.thread=GetCurrentThreadId();observed.actor_overlord=observed.target_overlord=0x2d2d2d;
        observed.effective_player=FRA_HANDLE;observed.manual_pause=1;
        env.user=this;env.image_base=BASE;env.owner_thread=GetCurrentThreadId();env.mock=true;env.exact_disk_and_loaded_image_verified=true;
        env.read=[](void* p,std::uintptr_t a,void* b,std::size_t n) { return read_cb(&static_cast<Rig*>(p)->mock,a,b,n); };
        env.write=[](void* p,std::uintptr_t a,const void* b,std::size_t n) { return write_cb(&static_cast<Rig*>(p)->mock,a,b,n); };
        env.resolve=[](void* p,std::uintptr_t r) { auto& rig=*static_cast<Rig*>(p);if(rig.reenter_resolve) { rig.reenter_resolve=false;rig.controller.frame(); }
            return resolve_cb(&rig.mock,r); };
        env.clock=[](void* p) { return static_cast<Rig*>(p)->mock.now; };
        env.current_thread=[](void* p)->std::uint32_t { return static_cast<Rig*>(p)->wrong_thread?0U:GetCurrentThreadId(); };
        env.begin_frame=[](void*) { return true; };
        env.sample=[](void* p,h18::Frame* out) { auto& r=*static_cast<Rig*>(p);*out=r.observed;++r.samples;
            if(r.change_second && r.samples%2==0)++out->stamp.date;return true; };
        journal.user=this;
        journal.append=[](void* p,const char* data,std::size_t n) { auto& r=*static_cast<Rig*>(p);++r.appends;
            r.records.emplace_back(data,n);if(r.reenter) { r.reenter=false;r.controller.frame(); }
            return r.appends!=r.fail_append; };
        journal.claim=[](void* p,std::uint32_t,const char* data,std::size_t n) { auto& r=*static_cast<Rig*>(p);r.claims.emplace_back(data,n);
            if(r.expire_claim)r.mock.now=r.wire_expiry;return !r.fail_claim; };
    }
    bool start() { return controller.start(env,journal); }
    std::string packet(unsigned stage) { h18::Request request{env.identity,stage,wire_expiry,static_cast<Stage>(stage)};
        char wire[1025]{};const int n=h18::render(request,wire,sizeof(wire));return n>0?std::string(wire,static_cast<std::size_t>(n)):std::string(); }
    bool run(unsigned stage) { current=&mock;mock.stage=static_cast<Stage>(stage);auto wire=packet(stage);return controller.frame(wire.data(),wire.size()); }
    bool health() { current=&mock;return controller.frame(); }
    bool setup(unsigned stage) { if(!start())return false;for(unsigned i=1;i<stage;++i)if(!run(i)||!health())return false;return true; }
    unsigned native_count() const { return mock.factory_calls+mock.clone_calls+mock.preview_calls+mock.wrapper_calls+mock.gate_calls+mock.action_dtors+mock.command_dtors; }
    void terminal() { const auto before=native_count();check(controller.status().state==h18::State::frozen,"host terminal");
        check(!health()&&!run(1)&&native_count()==before,"terminal cannot resume native"); }
};
void normal(const char* output) {
    for(unsigned mask=0;mask<4;++mask) { Rig r;r.mock.allow_preview=(mask&1)!=0;r.mock.allow_gate=(mask&2)!=0;
        check(r.start(),"host start");
        for(unsigned stage=1;stage<=3;++stage) { check(r.run(stage),"host stage complete");check(r.controller.status().state==h18::State::awaiting_health,"requires later independent health");
            check(r.health(),"later health");check(r.controller.status().completed==stage,"completed stages");check(!r.mock.live()&&!r.mock.abi_errors&&!r.mock.invalid_writes,"owned cleanup"); }
        check(r.controller.status().state==h18::State::complete&&r.claims.size()==3,"all claims permanent");
        check(!r.controller.status().send_supported&&!r.controller.status().runtime_verified&&!r.controller.status().production_ready,"no runtime permissions");
        if(mask==0 && output) { std::ofstream f(output,std::ios::binary|std::ios::trunc);for(const auto& line:r.records)f<<line;check(f.good(),"mock JSON capture"); }
        check(r.mock.factory_calls==15&&r.mock.preview_calls==5&&r.mock.wrapper_calls==5&&r.mock.gate_calls==5,"all fixed family routes");
        const auto before=r.native_count();check(!r.run(3)&&r.native_count()==before,"no stage replay");r.terminal();
    }
}
void codecs() {
    Rig r;for(unsigned stage=1;stage<=3;++stage) { auto raw=r.packet(stage);h18::Request parsed{};
        check(h18::parse(raw.data(),raw.size(),parsed)&&parsed.sequence==stage,"canonical codec");
        for(std::size_t i=0;i<raw.size();++i) { auto broken=raw;broken[i]='\0';parsed.sequence=99;
            check(!h18::parse(broken.data(),broken.size(),parsed)&&parsed.sequence==99,"NUL rejection no output mutation"); }
        const std::vector<std::pair<std::string,std::string>> changes={{"pid=1234","pid=01234"},{"pid=1234","pid=4294967296"},{"envoy=-1","envoy=0"},{"state=0","state=2"},{"value=1","value=false"},{"actor=FRA","actor=ENG"},{"target=ENG","target=POR"},{"EU4SPYLAB/1","EU4LAB/3"},{"expires=70000","expires=18446744073709551616"},{"expires=70000","expires=+70000"}};
        for(const auto& change:changes) { auto broken=raw;const auto at=broken.find(change.first);broken.replace(at,change.first.size(),change.second);
            check(!h18::parse(broken.data(),broken.size(),parsed),"reject unknown/flexible codec"); }
        check(!h18::parse(raw.data(),raw.size()-1,parsed),"requires final LF");raw+='\n';check(!h18::parse(raw.data(),raw.size(),parsed),"no tail"); }
}
void faults() {
    { Rig r;check(r.start(),"start duplicate");check(!r.start(),"no rearm");r.terminal(); }
    for(unsigned variant=0;variant<10;++variant) { Rig r;check(r.start(),"bad initial start");
        switch(variant) { case 0:r.observed.countries_count=122;break;case 1:r.observed.countries_count=4097;break;
        case 2:r.observed.target_overlord=FRA_HANDLE;break;case 3:r.observed.effective_player=ENG_HANDLE;break;
        case 4:r.observed.ironman=1;break;case 5:r.observed.manual_pause=0;break;case 6:r.observed.multiplayer_classifier=true;break;
        case 7:r.observed.stamp.target=0;break;case 8:r.change_second=true;break;case 9:r.wrong_thread=true;break; }
        check(!r.run(1)&&r.native_count()==0,"initial unavailable rejects all calls");r.terminal(); }
    { Rig r;check(r.start(),"sequence start");check(!r.run(2)&&r.claims.empty(),"strict next no hole");r.terminal(); }
    { Rig r;check(r.start(),"expired start");r.wire_expiry=r.mock.now;check(!r.run(1)&&r.claims.empty(),"expiry equality rejects before claim");r.terminal(); }
    { Rig r;check(r.start(),"ttl start");r.wire_expiry=r.mock.now+60001;check(!r.run(1)&&r.claims.empty(),"ttl greater60 rejects");r.terminal(); }
    { Rig r;check(r.start(),"claim fail start");r.fail_claim=true;check(!r.run(1)&&r.claims.size()==1&&r.native_count()==0,"partial claim no native");r.terminal(); }
    { Rig r;check(r.start(),"expire claim start");r.expire_claim=true;check(!r.run(1)&&r.claims.size()==1&&r.native_count()==0,"expiry after durableclaim no native");r.terminal(); }
    { Rig r;check(r.start(),"reentry start");r.reenter=true;check(!r.run(1)&&r.native_count()==0,"journal reentry terminal");r.terminal(); }
    { Rig r;check(r.start(),"resolver reentry start");r.reenter_resolve=true;check(!r.run(1)&&r.native_count()==0,"resolver reentry prevents actual call");r.terminal(); }
    { Rig r;check(r.setup(2),"changed setup");++r.observed.stamp.date;check(!r.run(2),"date changed terminal");r.terminal(); }
    const Fault cases[]={Fault::factory_null,Fault::factory_throw,Fault::clone_alias,Fault::clone_fields,Fault::preview_throw,
        Fault::wrapper_throw,Fault::gate_throw,Fault::dtor_throw,Fault::write_fail,Fault::wrapper_clone_alias};
    for(auto fault:cases) { Rig r;const unsigned stage=(fault==Fault::preview_throw||fault==Fault::write_fail)?2U:
        (fault==Fault::wrapper_throw||fault==Fault::gate_throw||fault==Fault::wrapper_clone_alias)?3U:1U;
        check(r.setup(stage),"native fault setup");r.mock.fault=fault;check(!r.run(stage),"native fault no promotion");r.terminal();
        bool raw=false,result=false;for(const auto& line:r.records) { if(line.find("\"kind\":5")!=std::string::npos)raw=true;if(line.find("terminal_result")!=std::string::npos)result=true; }
        check(raw&&result,"retain fault and terminal result diagnostics"); }
    { Rig r;check(r.setup(2),"late cleanup setup");r.mock.host.expires_uptime_ms=r.wire_expiry;r.mock.fault=Fault::expire_after_preview;
        const auto before=r.mock.action_dtors;check(!r.run(2)&&r.mock.action_dtors==before+1,"known return cleanup after TTL then stop");r.terminal(); }
    // Fail every durable audit boundary in a full stage, including final result.
    for(unsigned stage=1;stage<=3;++stage) { Rig reference;check(reference.setup(stage),"audit setup");const auto prefix=reference.appends;
        check(reference.run(stage),"audit reference");const auto count=reference.appends-prefix;
        for(unsigned n=1;n<=count;++n) { Rig r;check(r.setup(stage),"audit start");r.fail_append=r.appends+n;check(!r.run(stage),"audit failure stops");
            check(r.appends==r.fail_append,"failed audit is never retried");r.terminal(); } }
}
void filesystem() {
    wchar_t temp[MAX_PATH]{},root[MAX_PATH]{};check(GetTempPathW(MAX_PATH,temp)>0,"temp path");
    check(swprintf_s(root,L"%sspy-host18-%u-%llu",temp,GetCurrentProcessId(),static_cast<unsigned long long>(GetTickCount64()))>0&&CreateDirectoryW(root,nullptr),"new temporary parent");
    Rig r;h18::FileJournal journal;check(journal.create(root,r.env.identity),"private journal create");auto callbacks=journal.callbacks();auto wire=r.packet(1);
    check(callbacks.append(callbacks.user,"{}\n",3),"real append flush");check(callbacks.claim(callbacks.user,1,wire.data(),wire.size()),"real permanent claim flush");
    check(!callbacks.claim(callbacks.user,1,wire.data(),wire.size()),"duplicate claim terminal");check(!callbacks.append(callbacks.user,"{}\n",3),"failed journal stays closed");check(journal.close(),"close checked");
    h18::FileJournal duplicate;check(!duplicate.create(root,r.env.identity),"existing session cannot reopen");
    r.env.identity.session[0]='b';h18::FileJournal bounded;check(bounded.create(root,r.env.identity),"new bound session");auto limit=bounded.callbacks();
    std::string big(8192,' ');big[0]='{';big[1]='}';big.back()='\n';
    for(unsigned i=0;i<128;++i)check(limit.append(limit.user,big.data(),big.size()),"bounded flush <=1MiB");
    check(!limit.append(limit.user,"{}\n",3),"total budget hard stop");check(bounded.close(),"bounded close checked");
    std::printf("temporary_journal_retained=%ls\n",root); // Retained for audit; no recursive deletion.
}
}
int main(int argc,char** argv) {
    codecs();normal(argc==2?argv[1]:nullptr);faults();filesystem();
    std::printf("host_checks=%u failures=%u native_environment_invoked=false\n",checks,failures);return failures?1:0;
}
