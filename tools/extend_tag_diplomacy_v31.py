"""Extend the isolated V31 ownership and TAG guard ports. File-only operation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'bridge/native/tag_diplomacy_1375_v31/src/work/candidates'


def edit(name, old, new, count=1):
    path = SRC / name
    text = path.read_text()
    assert text.count(old) == count, (name, old[:100], text.count(old))
    path.write_text(text.replace(old, new), newline='\n')


def main():
    port = 'v24-pair-send-port-r2-1375/'
    core = 'v24-pair-send-core-r2-1375/'
    guard = 'v21-native-pair-guard-r3-1375/'
    host = 'v26-gap-curry-bootstrap-1375/'
    for file in ('native_pair_engine.cpp', 'native_platform.cpp'):
        edit(port + file, 'a.full_caller==b.full_caller;' if file.startswith('native_pair') else 'x.full_caller==p.full_caller)',
             'a.full_caller==b.full_caller && a.wrapper==b.wrapper;' if file.startswith('native_pair') else 'x.full_caller==p.full_caller && x.wrapper==p.wrapper)')
    edit(port+'native_platform.cpp', '>(base+0x35d210)(p.token,nullptr)', '>(base+0x35d210)(p.token,reinterpret_cast<const void*>(object))')
    edit(port+'native_platform.cpp', '>(base+0x4e9930)(reinterpret_cast<void*>(object),&result)', '>(base+p.wrapper)(reinterpret_cast<void*>(object),&result)')
    edit(port+'native_platform.cpp', 'p.vtable+0x40,0x4e9930', 'p.vtable+0x40,p.wrapper')
    edit(port+'native_pair_engine.h', 'struct TransferEnvelope {',
         'struct ExtraField {std::uint32_t offset{},width{};std::uint64_t value{};};\nstruct TransferEnvelope {')
    edit(port+'native_pair_engine.h', 'std::int32_t trust_cost_milli{},trust_gain{};\n};',
         'std::int32_t trust_cost_milli{},trust_gain{};\n    std::array<ExtraField,4> extra{};std::uint32_t extra_count{};\n};')
    edit(port+'native_pair_engine.h', 'explicit NativePairEngineDraft(Platform&) noexcept;',
         'explicit NativePairEngineDraft(Platform&,Address borrowed_definition=0) noexcept;\n    void definition(Address p) noexcept {definition_=p;}')
    edit(port+'native_pair_engine.h', 'v21pair::OwnedId peer{},source{}; };',
         'v21pair::OwnedId peer{},source{};std::array<ExtraField,4> extra{};std::uint32_t extra_count{}; };')
    edit(port+'native_pair_engine.h', 'Platform& platform_;', 'Platform& platform_;Address definition_{};')
    edit(port+'native_pair_engine.cpp', 'NativePairEngineDraft::NativePairEngineDraft(Platform& p) noexcept:platform_(p),',
         'NativePairEngineDraft::NativePairEngineDraft(Platform& p,Address definition) noexcept:platform_(p),definition_(definition),')
    edit(port+'native_pair_engine.cpp', 'if(e.profile->family==Family::Marriage) {',
         'if(e.profile->family==Family::Marriage || e.profile->family==Family::N_invite_to_federation) {')
    edit(port+'native_pair_engine.cpp', 'v.text.force=get<std::uint8_t>(p+0x60);',
         'v.text.force=e.profile->family==Family::Marriage?get<std::uint8_t>(p+0x60):0;')
    edit(port+'native_pair_engine.cpp', 'const auto v=view(e);const auto h=',
         'for(std::uint32_t i=0;i<e.extra_count;++i) {const auto& f=e.extra[i];std::uint64_t actual=0;read(e.address+f.offset,&actual,f.width);if(actual!=f.value)fail(Fault::Fields);}\n    const auto v=view(e);const auto h=')
    edit(port+'native_pair_engine.cpp', 'if(e.profile->family==Family::Marriage && empty',
         'if((e.profile->family==Family::Marriage || e.profile->family==Family::N_invite_to_federation) && empty')
    edit(port+'native_pair_engine.cpp', 'const auto result=call(Call::Factory,f,0);',
         'if(f.family==Family::N_scriptable_diplomatic_action && !pointer(definition_))fail(Fault::Fields);\n    const auto result=call(Call::Factory,f,f.family==Family::N_scriptable_diplomatic_action?definition_:0);')
    edit(port+'native_pair_engine.cpp', '    expected(e,true);return e.id;', r'''
    auto extra=[&](std::uint32_t offset,std::uint32_t width) {
        if(e.extra_count>=e.extra.size() || offset+width>f.size || (width!=4&&width!=8))fail(Fault::Fields);
        auto& field=e.extra[e.extra_count++];field.offset=offset;field.width=width;read(e.address+offset,&field.value,width);
    };
    if(f.family==Family::N_tributary_state_action || f.family==Family::N_transfer_trade_power)extra(0x40,4);
    if(f.family==Family::N_warsubsidy){extra(0x40,4);extra(0x44,4);}
    if(f.family==Family::N_scriptable_diplomatic_action){extra(0x40,8);if(e.extra[0].value!=definition_)fail(Fault::Fields);}
    expected(e,true);return e.id;''')
    edit(port+'native_pair_engine.cpp', 'clone.trust_cost_milli=e.trust_cost_milli;',
         'clone.extra=e.extra;clone.extra_count=e.extra_count;\n    if(f.wrapper!=0x4e9930){clone.envoy=get<std::int32_t>(clone.address+0x30);if(clone.envoy<-1 || (e.mode&&clone.envoy!=-1))fail(Fault::Fields);}\n    clone.trust_cost_milli=e.trust_cost_milli;')
    edit(port+'native_pair_engine.cpp', 'clone.trust_cost_milli,clone.trust_gain};',
         'clone.trust_cost_milli,clone.trust_gain,clone.extra,clone.extra_count};')
    edit(port+'submission_guard.cpp', '    if(e.profile.family==Family::Marriage) {',
         '    if(e.extra_count>e.extra.size())return false;\n'
         '    for(std::uint32_t i=0;i<e.extra_count;++i){const auto& f=e.extra[i];Address actual=0;\n'
         '      if(f.offset<0x40 || f.offset+f.width>e.profile.size || (f.width!=4&&f.width!=8) || !read(e.clone+f.offset,&actual,f.width) || actual!=f.value)return false;}\n'
         '    if(e.profile.family==Family::Marriage || e.profile.family==Family::N_invite_to_federation) {')
    edit(port+'submission_guard.cpp', '|| !at(e.clone,0x60,b) || b)return false;',
         '|| (e.profile.family==Family::Marriage&&(!at(e.clone,0x60,b)||b)))return false;')
    edit(core+'pair_send.cpp', 'if (p.family!=Family::Marriage) return true;',
         'if (p.family!=Family::Marriage && p.family!=Family::N_invite_to_federation) return true;')
    edit(core+'pair_send.cpp', 'std::uint64_t last_clock=0; bool got_clock=false;',
         'std::uint64_t last_clock=0; bool got_clock=false;std::int32_t clone_envoy=-1;')
    edit(core+'pair_send.cpp', 'initialized(p,v,baseline,mode,envoy,true);\n        };',
         'initialized(p,v,baseline,mode,clone_envoy,true);\n        };')
    edit(core+'pair_send.cpp', 'if (clone==original || clone==command || !e.action_view(clone,v) || !initialized(p,v,baseline,mode,envoy,true))',
         'if(!e.action_view(clone,v))return freeze("clone_unreadable");\n'
         '        clone_envoy=p.wrapper==0x4e9930?envoy:v.envoy;\n'
         '        if(clone_envoy<-1 || (p.wrapper!=0x4e9930&&mode&&clone_envoy!=-1))return freeze("clone_envoy_untrusted");\n'
         '        if (clone==original || clone==command || !initialized(p,v,baseline,mode,clone_envoy,true))')
    edit(guard+'native_guard.h', 'bool frozen() const noexcept',
         'std::uint64_t definition() const noexcept {return definition_;}\n    bool frozen() const noexcept')
    edit(guard+'native_guard.h', 'bool light() noexcept;',
         'std::uint64_t definition_{},definition_registry_{},definition_begin_{},definition_end_{},definition_cap_{},definition_slot_{};\n'
         'bool bind_definition() noexcept;\n    bool definition_current() noexcept;\n    bool requested_direction() noexcept;\n    bool light() noexcept;')
    edit(guard+'native_guard.cpp', 'if(!sample_pair(request,baseline_,roots_))return false;bound_=true;',
         'if(!sample_pair(request,baseline_,roots_))return false;bound_=true;\n'
         '        if(!requested_direction() || !bind_definition())return fail();')
    edit(guard+'native_guard.cpp', '        if(!light())return false;', '        if(!light() || !definition_current() || !requested_direction())return false;')
    edit(guard+'native_guard.cpp', 'Busy lock(self.busy_);return self.light();',
         'Busy lock(self.busy_);return self.light()&&self.definition_current()&&self.requested_direction();')
    edit(guard+'native_guard.cpp', 'bool NativePairGuardDraft::light() noexcept {', r'''
namespace {
bool name_at(NativePairGuardDraft& reader,std::uint64_t definition,const char* wanted) {
    std::uint64_t n=0,capacity=0,chars=definition+0x10;
    if(!reader.read(definition+0x20,&n,8)||!reader.read(definition+0x28,&capacity,8)
        ||n==0||n>128||n!=std::strlen(wanted)||n>capacity||capacity>1048576)return false;
    if(capacity>=16){if(!reader.read(definition+0x10,&chars,8)||chars<0x10000||chars>=0x800000000000ULL)return false;}
    else if(capacity!=15||n>=16)return false;
    char text[129]{};return reader.read(chars,text,static_cast<std::size_t>(n+1))&&!text[n]&&!std::memcmp(text,wanted,static_cast<std::size_t>(n));
}
}
bool NativePairGuardDraft::bind_definition() noexcept {
    try {
        const auto key=v21pair::script_key(request_.action);if(!*key)return true;
        if(!get(env_.image_base+0x242bba8,definition_registry_)||definition_registry_<0x10000
          ||!get(definition_registry_,definition_begin_)||!get(definition_registry_+8,definition_end_)
          ||!get(definition_registry_+16,definition_cap_)||definition_begin_<0x10000
          ||definition_end_<definition_begin_||definition_cap_<definition_end_||(definition_end_-definition_begin_)%8
          ||(definition_cap_-definition_begin_)%8||(definition_cap_-definition_begin_)/8>4096)return false;
        unsigned matches=0;
        for(auto slot=definition_begin_;slot<definition_end_;slot+=8) {
            std::uint64_t p=0,vt=0;std::uint32_t marker=0;
            if(!get(slot,p)||p<0x10000||!get(p,vt)||vt!=env_.image_base+0x1ce1f70||!get(p+8,marker)||marker!=0x165)return false;
            if(name_at(*this,p,key)){definition_=p;definition_slot_=slot;if(++matches!=1)return false;}
        }
        return matches==1&&definition_current();
    }catch(...){return false;}
}
bool NativePairGuardDraft::definition_current() noexcept {
    try {
        const auto key=v21pair::script_key(request_.action);if(!*key)return !definition_;
        std::uint64_t p=0,vt=0;std::uint32_t marker=0;
        return definition_&&get(env_.image_base+0x242bba8,p)&&p==definition_registry_
          &&get(definition_registry_,p)&&p==definition_begin_&&get(definition_registry_+8,p)&&p==definition_end_
          &&get(definition_registry_+16,p)&&p==definition_cap_&&get(definition_slot_,p)&&p==definition_
          &&get(p,vt)&&vt==env_.image_base+0x1ce1f70&&get(p+8,marker)&&marker==0x165&&name_at(*this,p,key);
    }catch(...){return false;}
}
bool NativePairGuardDraft::requested_direction() noexcept {
    using namespace v21pair;
    try {
        const auto action=request_.action;
        if(action==Action::N_join_coalition){std::int32_t active=0;return get(baseline_.target_object+0x1920,active)&&active>0;}
        if(action==Action::N_kick_from_trade_league || action==Action::N_leave_trade_league) {
            std::uint64_t league=0,other=0,begin=0,end=0,leader=0;
            if(!get(baseline_.actor_object+0x1948,league)||league<0x10000||!get(baseline_.target_object+0x1948,other)
              ||other!=league||!get(league+0x20,begin)||!get(league+0x28,end)||begin<0x10000||end<=begin||(end-begin)%8||(end-begin)/8>4096||!get(begin,leader))return false;
            return action==Action::N_kick_from_trade_league?leader==baseline_.actor.value:leader!=baseline_.actor.value;
        }
        if(action==Action::Independence || action==Action::N_ask_support_independence
          ||action==Action::N_cancel_offered_independence_support ||action==Action::N_cancel_requested_independence_support) {
            std::uint64_t overlord=0;bool dependent=false;
            if(!get(baseline_.actor_object+0x18f0,overlord))return false;
            if(valid(FullHandle{overlord})) {
                std::uint64_t records=0,root=0,array=0;std::int32_t count=0;
                const auto slot=(overlord>>32)&65535;
                if(slot>=baseline_.count||!get(baseline_.actor_object+0x1510,records)||records<0x10000
                 ||!get(records+slot*0x48,root)||root<0x10000||!get(root+0x128,array)||!get(root+0x134,count)
                 ||count<0||count>4096||(count&&array<0x10000))return false;
                for(std::int32_t i=0;i<count;++i) {
                    std::uint32_t id=0;std::uint64_t relation=0,definition=0,vt=0;std::uint8_t flag=0;
                    if(!get(array+std::uint64_t(i)*16,id))return false;
                    if(id!=slot)continue;
                    if(!get(array+std::uint64_t(i)*16+8,relation)||relation<0x10000||!get(relation,vt)||vt!=env_.image_base+0x1c81758
                      ||!get(relation+0x40,definition)||definition<0x10000||!get(definition+0x11a,flag))return false;
                    dependent=flag!=0;break;
                }
            }
            const bool requested=action==Action::N_ask_support_independence||action==Action::N_cancel_requested_independence_support;
            return requested==dependent;
        }
        return true;
    }catch(...){return false;}
}
bool NativePairGuardDraft::light() noexcept {''')
    edit(guard+'native_guard.cpp', '#include <limits>', '#include <limits>\n#include <cstring>')
    edit('v21-five-cancel-reader-1375/cancel_reader.cpp', 'case v21pair::Family::SpyNetwork:return false;',
         'case v21pair::Family::SpyNetwork:return false;\n        default:return false;')
    edit(host+'bootstrap.cpp',
         'if(!job->guard.begin_frame()||!job->guard.lease(packet.request,packet.expires)){record("lease_rejected",",\\\"native_call_attempts\\\":0,\\\"unknown_no_retry\\\":true");terminal();return;}',
         'if(!job->guard.begin_frame()||!job->guard.lease(packet.request,packet.expires)){\n'
         '  if(!record("request_result",",\\\"status\\\":1,\\\"reason\\\":\\\"lease_precondition_rejected\\\",\\\"submitted\\\":false,\\\"adapter_call_attempts\\\":0"))return;\n'
         '  ++next_sequence;current_sequence=0;return;\n }\n job->engine.definition(job->guard.definition());')
    print('V31 ownership, wrapper, definition and direction ports extended; no game access')


if __name__ == '__main__':
    main()
