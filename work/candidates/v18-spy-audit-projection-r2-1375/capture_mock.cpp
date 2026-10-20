// Compile only in an isolated mock executable. The sealed core/test sources are
// included unmodified. This is not a producer of authenticated game evidence.
#define main sealed_mock_test_main
#include "../v18-spy-no-send-core-1375/test_spy_core.cpp"
#undef main

namespace {
const char* boolean(bool v) { return v?"true":"false"; }
void field_json(const Fields& f) {
    std::printf("{\"vtable\":%llu,\"marker\":%u,\"actor\":%llu,\"controller\":%llu,\"target\":%llu,"
        "\"primary_date\":%d,\"secondary_date\":%d,\"envoy\":%d,\"state\":%u,\"value\":%u,\"flag39\":%u,\"identifier\":%u}",
        static_cast<unsigned long long>(f.vtable),f.marker,static_cast<unsigned long long>(f.actor),
        static_cast<unsigned long long>(f.controller),static_cast<unsigned long long>(f.target),
        f.primary_date,f.secondary_date,f.envoy,f.state,static_cast<unsigned>(f.value),static_cast<unsigned>(f.flag39),f.identifier);
}
void stamp_json(const Stamp& s) {
    std::printf("{\"game\":%llu,\"database\":%llu,\"countries\":%llu,\"actor_country\":%llu,\"target_country\":%llu,"
        "\"server\":%llu,\"pause_manager\":%llu,\"actor\":%llu,\"target\":%llu,\"player\":%llu,\"date\":%d}",
        static_cast<unsigned long long>(s.game),static_cast<unsigned long long>(s.database),
        static_cast<unsigned long long>(s.countries),static_cast<unsigned long long>(s.actor_country),
        static_cast<unsigned long long>(s.target_country),static_cast<unsigned long long>(s.server),
        static_cast<unsigned long long>(s.pause_manager),static_cast<unsigned long long>(s.actor),
        static_cast<unsigned long long>(s.target),static_cast<unsigned long long>(s.player),s.date);
}
void prefix(const Mock& m,const char* kind) {
    std::printf("{\"kind\":\"%s\",\"frame\":%llu,\"uptime_ms\":%llu,\"thread\":%u,\"image_base\":%llu,",
        kind,static_cast<unsigned long long>(m.host.frame_id),static_cast<unsigned long long>(m.now),
        static_cast<unsigned>(GetCurrentThreadId()),static_cast<unsigned long long>(BASE));
}
bool capture_log(void* context,const Event* e) {
    auto& m=*static_cast<Mock*>(context);
    prefix(m,"core");std::printf("\"event\":{\"kind\":%u,\"stage\":%u,\"step\":%u,\"family\":%u,\"token\":%u,"
        "\"original_id\":%u,\"clone_id\":%u,\"command_id\":%u,\"call_entered\":%s,\"call_returned\":%s,"
        "\"allowed_observed\":%s,\"allowed\":%s,\"original_destroyed\":%s,\"clone_destroyed\":%s,"
        "\"command_destroyed\":%s,\"mock_resolver\":%s,\"send_supported\":%s,\"reason\":%u,\"exception_code\":%u,\"original_fields\":",
        static_cast<unsigned>(e->kind),static_cast<unsigned>(e->stage),static_cast<unsigned>(e->step),e->family,e->token,
        e->original_id,e->clone_id,e->command_id,boolean(e->call_entered),boolean(e->call_returned),boolean(e->allowed_observed),
        boolean(e->allowed),boolean(e->original_destroyed),boolean(e->clone_destroyed),boolean(e->command_destroyed),
        boolean(e->mock_resolver),boolean(e->send_supported),static_cast<unsigned>(e->reason),e->exception_code);
    field_json(e->original_fields);std::printf(",\"clone_fields\":");field_json(e->clone_fields);
    std::printf(",\"stamp\":");stamp_json(e->stamp);std::printf("}}\n");
    // This captures a mock logger invocation, not a durable game logger receipt.
    return std::ferror(stdout)==0 && log_cb(context,e);
}
void result_json(const Mock& m,const Result& r) {
    prefix(m,"result");std::printf("\"result\":{\"stage\":%u,\"reason\":%u,\"step\":%u,\"family\":%u,"
        "\"cases_complete\":%u,\"exception_code\":%u,\"completed\":%s,\"audit_complete\":%s,\"freeze_session\":%s,"
        "\"ownership_uncertain\":%s,\"retry_allowed\":%s,\"send_supported\":%s,\"runtime_verified\":%s,"
        "\"production_ready\":%s,\"reads\":%u,\"bytes_read\":%llu,\"allowed_observed\":[",
        static_cast<unsigned>(r.stage),static_cast<unsigned>(r.reason),static_cast<unsigned>(r.step),r.family,
        r.cases_complete,r.exception_code,boolean(r.completed),boolean(r.audit_complete),boolean(r.freeze_session),
        boolean(r.ownership_uncertain),boolean(r.retry_allowed),boolean(r.send_supported),boolean(r.runtime_verified),
        boolean(r.production_ready),r.reads,static_cast<unsigned long long>(r.bytes_read));
    for(unsigned i=0;i<5;++i)std::printf("%s%s",i?",":"",boolean(r.allowed_observed[i]));
    std::printf("],\"allowed\":[");for(unsigned i=0;i<5;++i)std::printf("%s%s",i?",":"",boolean(r.allowed[i]));
    std::printf("]}}\n");
}
}
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    const bool normal=std::strcmp(argv[1],"false")==0 || std::strcmp(argv[1],"mixed")==0 || std::strcmp(argv[1],"true")==0;
    const bool late=std::strcmp(argv[1],"late_cleanup")==0;
    const bool fault=std::strcmp(argv[1],"factory_exception")==0;
    const bool final_audit=std::strcmp(argv[1],"final_audit_failure")==0;
    if(!normal && !late && !fault && !final_audit)return 2;
    Mock m;m.host.log=capture_log;m.allow_preview=std::strcmp(argv[1],"false")!=0;m.allow_gate=std::strcmp(argv[1],"true")==0;
    for(auto stage:{Stage::lifecycle,Stage::family_preview,Stage::owned_command}) {
        if(late && stage==Stage::family_preview)m.fault=Fault::expire_after_preview;
        if(fault)m.fault=Fault::factory_throw;
        if(final_audit)m.fault=Fault::logger_complete;
        const auto r=m.run(stage);result_json(m,r);
        if(!r.completed)break;
        ++m.host.frame_id;++m.now;
    }
    return std::ferror(stdout)?3:0;
}
