#include "host.h"
#include "journal.h"
#include <string>
#include <fstream>
#include "mock_support.inc"
namespace h=eu4_spy_send_host19;
namespace p18=eu4_spy_host18;
// mock_support.inc intentionally leaves its anonymous namespace open.
struct Rig {
    Mock mock;h::Controller controller;h::Environment env{};h::Journal journal{};h::Frame observed{};
    std::vector<std::string> records,claims;unsigned appends=0,fail_append=0,claim_calls=0,fail_claim=0;
    bool reenter=false,bad_world=false,wrong_thread=false,expire_claim=false;std::uint64_t expiry=70000;
    Rig() {
        env.identity.pid=1234;env.identity.creation=1;
        std::memset(env.identity.session,'a',32);std::memset(env.identity.dll_sha256,'b',64);std::memset(env.identity.manifest_sha256,'c',64);
        observed.stamp={GAME,DB,COUNTRIES,FRA,ENG,SERVER,PAUSE,FRA_HANDLE,ENG_HANDLE,FRA_HANDLE,DATE};
        observed.countries_count=256;observed.thread=GetCurrentThreadId();observed.actor_overlord=observed.target_overlord=0x2d2d2d;
        observed.effective_player=FRA_HANDLE;observed.manual_pause=1;
        env.user=this;env.image_base=BASE;env.owner_thread=GetCurrentThreadId();env.mock=true;env.exact_disk_and_loaded_image_verified=true;
        env.read=[](void* p,std::uintptr_t a,void* b,std::size_t n) { return read_cb(&static_cast<Rig*>(p)->mock,a,b,n); };
        env.write=[](void* p,std::uintptr_t a,const void* b,std::size_t n) { return write_cb(&static_cast<Rig*>(p)->mock,a,b,n); };
        env.resolve=[](void* p,std::uintptr_t r) { return resolve_cb(&static_cast<Rig*>(p)->mock,r); };
        env.clock=[](void* p) { return static_cast<Rig*>(p)->mock.now; };
        env.current_thread=[](void* p)->std::uint32_t { return static_cast<Rig*>(p)->wrong_thread?0U:GetCurrentThreadId(); };
        env.begin_frame=[](void*) { return true; };
        env.sample=[](void* p,h::Frame* out) { auto& r=*static_cast<Rig*>(p);*out=r.observed;if(r.bad_world)++out->stamp.date;return true; };
        journal.user=this;
        journal.append=[](void* p,const char* text,std::size_t size) {
            auto& r=*static_cast<Rig*>(p);r.records.emplace_back(text,size);++r.appends;
            if(r.reenter) { r.reenter=false;r.controller.frame(); }
            return r.appends!=r.fail_append;
        };
        journal.claim=[](void* p,std::uint32_t seq,std::uint32_t item,const char* text,std::size_t size) {
            auto& r=*static_cast<Rig*>(p);r.claims.emplace_back(text,size);++r.claim_calls;
            const auto expected=r.claim_calls<=4?r.claim_calls:4;
            if(seq!=expected||item!=(r.claim_calls<=4?0:r.claim_calls-4))++r.mock.abi_errors;
            if(r.expire_claim)r.mock.now=r.expiry;
            return r.claim_calls!=r.fail_claim;
        };
    }
    bool start() { return controller.start(env,journal); }
    std::string packet(unsigned n) {
        char raw[1025]{};int len=0;
        if(n==4)len=h::render({env.identity,expiry},raw,sizeof(raw));
        else len=p18::render({env.identity,n,expiry,static_cast<eu4_spy18::Stage>(n)},raw,sizeof(raw));
        return len>0?std::string(raw,static_cast<std::size_t>(len)):std::string();
    }
    bool run(unsigned n) { current=&mock;auto raw=packet(n);return controller.frame(raw.data(),raw.size()); }
    bool frame() { current=&mock;return controller.frame(); }
    bool preflight(bool final_health=true) { if(!start())return false;for(unsigned s=1;s<=3;++s)if(!run(s)||((s<3||final_health)&&!frame()))return false;return true; }
    unsigned calls() const { return mock.factory_calls+mock.clone_calls+mock.preview_calls+mock.wrapper_calls+mock.gate_calls+mock.action_dtors+mock.command_dtors+mock.submit_calls; }
    void terminal() { const auto n=calls();check(controller.status().state==h::State::frozen,"host frozen");check(!frame()&&!run(4)&&calls()==n,"never resume after terminal"); }
};
void full_batches(const char* capture) {
    for(unsigned mask=0;mask<4;++mask) {
        Rig r;r.mock.allow_preview=(mask&1)!=0;r.mock.allow_gate=(mask&2)!=0;
        check(r.preflight(),"actual nested three-stage preflight");
        auto initial=r.controller.status();check(initial.preflight_stages==3&&initial.authenticated_stages==3&&initial.claimed_sequence==3&&!initial.batch_claimed,"preflight itself never grants automatic batch");
        check(r.mock.factory_calls==15&&r.mock.preview_calls==5&&r.mock.gate_calls==5&&r.mock.submit_calls==0&&r.mock.live()==0,"actual fifteen preflight cases clean");
        check(r.run(4)&&r.controller.status().batch_claimed&&r.mock.submit_calls==0,"explicit seq4 claims without sending same callback");
        for(unsigned i=0;i<5;++i) {
            const auto factory=r.mock.factory_calls;check(r.frame()&&r.mock.factory_calls==factory+1,"only one family per owner frame");
            auto s=r.controller.status();check(s.state==h::State::awaiting_health&&s.completed_items==i,"owned result awaits independent health");
            const auto n=r.calls();check(r.frame()&&r.calls()==n&&r.controller.status().completed_items==i+1,"later health never invokes family native");
        }
        auto s=r.controller.status();check(s.state==h::State::complete&&s.completed_items==5&&r.claims.size()==9,"three stage batch and five item claims");
        check(r.mock.submit_calls==(mask==3?5U:0U)&&r.mock.live()==0&&r.mock.invalid_reads==0&&r.mock.abi_errors==0,"known full/gate false cleanup or dispatched");
        check(!s.runtime_verified&&!s.effect_verified&&!s.production_ready&&!s.strict_sp_verified&&!s.epoch_verified,"no runtime permissions");
        if(capture&&mask==3) { std::ofstream f(capture,std::ios::binary|std::ios::trunc);for(const auto& row:r.records)f<<row;check(f.good(),"complete synthetic raw journal"); }
        check(!r.run(4),"seq4 cannot repeat");r.terminal();
    }
}
void proofs() {
    { Rig r;check(r.start(),"start preflight gap");check(!r.run(4)&&r.claims.empty()&&r.calls()==0,"missing preflight cannot assert readiness");r.terminal(); }
    { Rig r;check(r.preflight(false),"three actual stages no last health");check(r.controller.status().authenticated_stages==0,"missing independent health no proof");
      const auto calls=r.calls();check(!r.run(4)&&r.calls()==calls&&r.claims.size()==3,"seq4 cannot provide third later health simultaneously");r.terminal(); }
    { Rig r;check(r.preflight(),"changed selected world setup");r.bad_world=true;check(!r.run(4)&&r.claims.size()==3,"same-session changed world rejected");r.terminal(); }
    { Rig r;check(r.preflight(),"changed identity setup");auto raw=r.packet(4);auto at=raw.find("pid=1234");raw.replace(at,8,"pid=4321");current=&r.mock;
      check(!r.controller.frame(raw.data(),raw.size())&&r.claims.size()==3,"foreign seq4 identity");r.terminal(); }
    { Rig r;check(r.preflight(),"false preflight setup");r.mock.allow_preview=false;r.mock.allow_gate=false;check(r.run(4)&&r.frame(),"current false legal gate still safe research result");
      check(r.mock.submit_calls==0&&r.controller.status().result.current_item.outcome==Outcome::full_preview_rejected,"no promotion by old positive preflight"); }
    { Rig r;r.mock.allow_preview=false;r.mock.allow_gate=false;check(r.preflight(),"all false preflight still completes cleanup");r.mock.allow_preview=true;r.mock.allow_gate=true;
      check(r.run(4)&&r.frame()&&r.mock.submit_calls==1,"send uses current full gate and wrapper gate separately"); }
    { Rig r;check(r.start()&&r.run(1),"first stage complete before health");auto s=r.controller.status();
      check(s.preflight_stages==s.claimed_sequence&&!s.preflight_ready,"equal counters do not permit another stage before health");
      check(!r.run(2)&&r.claims.size()==1,"no next stage in health callback");r.terminal(); }
    {
        Rig r;p18::Controller c;p18::Journal j{&r,
            [](void* p,const char* b,std::size_t n) { auto& x=*static_cast<Rig*>(p);return x.journal.append(x.journal.user,b,n); },
            [](void* p,std::uint32_t q,const char* b,std::size_t n) { auto& x=*static_cast<Rig*>(p);return x.journal.claim(x.journal.user,q,0,b,n); }};
        check(c.start(r.env,j),"private receipt controller start");p18::PreflightProof proof{};
        check(!c.completed_preflight(proof),"no externally supplied proof");
        r.mock.allow_preview=false;r.mock.allow_gate=true;
        for(unsigned q=1;q<=3;++q) {
            current=&r.mock;const auto raw=r.packet(q);check(c.frame(raw.data(),raw.size()),"real receipt stage run");
            check(!c.completed_preflight(proof),"run_result alone cannot create proof");check(c.frame(),"independent later receipt health");
        }
        check(c.completed_preflight(proof),"all three authenticated typed results");
        for(unsigned q=0;q<3;++q)for(unsigned f=0;f<5;++f) {
            const auto& s=proof.stages[q];check(s.durable_result&&s.later_health&&s.later_health_frame>s.completion_frame,"typed receipt strict later frame");
            check(s.result.allowed_observed[f]==(q!=0)&&s.result.allowed[f]==(q==2),"actual result false and true arrays preserved");
        }
        proof.stages[0].result.cases_complete=99;proof.world.stamp.date=1;
        p18::PreflightProof copy{};check(c.completed_preflight(copy)&&copy.stages[0].result.cases_complete==5&&copy.world.stamp.date==DATE,"proof returns isolated immutable copy");
    }
}
void fault_cases() {
    for(unsigned failed=1;failed<=9;++failed) {
        Rig r;r.fail_claim=failed;bool ok=r.preflight();if(ok)ok=r.run(4);for(unsigned i=0;ok&&i<10;++i)ok=r.frame();
        check(!ok&&r.claim_calls==failed,"each permanent claim failure stops once");r.terminal();
    }
    { Rig r;check(r.preflight(),"expired setup");r.expiry=r.mock.now;check(!r.run(4)&&r.claims.size()==3,"expiry equality before permanent batch claim");r.terminal(); }
    { Rig r;check(r.preflight(),"claim ttl setup");r.expire_claim=true;check(!r.run(4)&&r.claims.size()==4&&r.mock.submit_calls==0,"expiry after permanent batch claim no native");r.terminal(); }
    for(auto fault:{Fault::submit_throw,Fault::submit_false_consumed,Fault::submit_true_unconsumed,Fault::preview_throw,Fault::wrapper_alias}) {
        Rig r;check(r.preflight()&&r.run(4),"unknown setup");r.mock.fault=fault;check(!r.frame(),"unknown core terminal");
        auto s=r.controller.status();check(s.result.current_item.current&&s.completed_items==0,"unknown current item retained");r.terminal();
    }
    { Rig r;check(r.preflight()&&r.run(4),"postenter journal fault setup");r.reenter=true;check(!r.frame()&&r.mock.submit_calls==0,"reentry callback freezes before further calls");r.terminal(); }
    { Rig r;check(r.preflight()&&r.run(4),"owner thread setup");r.wrong_thread=true;check(!r.frame()&&r.mock.submit_calls==0,"wrong owner rejects");r.terminal(); }
    // Test every new-layer append boundary within one complete send item and later health.
    unsigned count=0;
    { Rig r;check(r.preflight(),"boundary reference setup");const auto n=r.appends;check(r.run(4)&&r.frame()&&r.frame(),"boundary reference");count=r.appends-n; }
    for(unsigned n=1;n<=count;++n) {
        Rig r;check(r.preflight(),"boundary setup");r.fail_append=r.appends+n;
        bool ok=r.run(4);if(ok)ok=r.frame();if(ok)ok=r.frame();check(!ok,"new append callback failure never promotes");
        check(r.appends==r.fail_append,"failed append not retried");r.terminal();
    }
}
void codec() {
    Rig r;auto raw=r.packet(4);h::BatchRequest out{};check(h::parse(raw.data(),raw.size(),out)&&out.expires==r.expiry,"canonical seq4");
    for(std::size_t n=0;n<raw.size();++n) { auto b=raw;b[n]='\0';out.expires=99;check(!h::parse(b.data(),b.size(),out)&&out.expires==99,"each NUL rejected without output mutation"); }
    const std::pair<const char*,const char*> mutations[]={{"pid=1234","pid=01234"},{"sequence=4","sequence=5"},{"stage=send_batch","stage=family_preview"},{"actor=FRA","actor=ENG"},{"target=ENG","target=POR"},{"value=1","value=0"},{"state=0","state=2"},{"envoy=-1","envoy=0"},{"expires=70000","expires=18446744073709551616"},{"EU4SPYSEND/1","EU4SPYLAB/1"}};
    for(const auto& m:mutations) { auto b=raw;const auto at=b.find(m.first);b.replace(at,std::strlen(m.first),m.second);check(!h::parse(b.data(),b.size(),out),"fixed bounded wire no free parameters"); }
    check(!h::parse(nullptr,0,out)&&!h::parse(raw.data(),raw.size()-1,out),"null and missing final LF reject");
    raw+='\n';check(!h::parse(raw.data(),raw.size(),out),"additional tail rejects");
}
void file_journal() {
    wchar_t temp[MAX_PATH]{},root[MAX_PATH]{};check(GetTempPathW(MAX_PATH,temp)>0,"temporary path");
    check(swprintf_s(root,L"%sspy19-host-%u-%llu",temp,GetCurrentProcessId(),static_cast<unsigned long long>(GetTickCount64()))>0&&CreateDirectoryW(root,nullptr),"CREATE_NEW mock parent");
    Rig r;h::FileJournal file;check(file.create(root,r.env.identity),"private journal create");auto j=file.callbacks();
    for(unsigned q=1;q<=4;++q) { const auto raw=r.packet(q);check(j.claim(j.user,q,0,raw.data(),raw.size()),"ordered durable stage/batch claim"); }
    for(unsigned i=1;i<=5;++i) { char raw[1025]{};const int n=h::render_item({r.env.identity,r.expiry},i,raw,sizeof(raw));check(n>0&&j.claim(j.user,4,i,raw,static_cast<std::size_t>(n)),"five fixed item claims"); }
    check(j.append(j.user,"{}\n",3),"durable append");auto raw=r.packet(4);
    check(!j.claim(j.user,4,0,raw.data(),raw.size())&&!j.append(j.user,"{}\n",3),"duplicate permanent claim poisons journal");check(file.close(),"explicit checked close");
    h::FileJournal retry;check(!retry.create(root,r.env.identity),"existing session no reopen");
    std::fprintf(stderr,"retained_private_mock_journal=%ls\n",root);
}
} // namespace
int main(int argc,char** argv) {
    codec();proofs();full_batches(argc==2?argv[1]:nullptr);fault_cases();file_journal();
    std::printf("{\"checks\":%u,\"failures\":%u,\"mock_only\":true,\"game_access\":false}\n",checks,failures);return failures?1:0;
}
