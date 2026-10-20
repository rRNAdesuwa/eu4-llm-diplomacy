// Actual ownership adapter exercised against a byte-addressed fake platform.
// No Windows process is opened and no game function is called.
#include "../v24-pair-send-port-r2-1375/native_pair_engine.h"
#include <cassert>
#include <cstring>
#include <map>
#include <vector>
#include <cstdio>
using namespace v21pair;
namespace {
constexpr std::uint64_t Base=0x140000000ULL,Definition=0x400000000ULL;
struct Model final:v24port::Platform {
    std::map<std::uint64_t,std::vector<unsigned char>> objects;
    std::uint64_t next=0x500000000ULL;bool corrupt{},bad_union_state{},sent{};unsigned submitted{};
    std::uint64_t module()const noexcept override{return Base;}
    bool ready()override{return true;}
    std::uint64_t allocate(unsigned size){const auto p=next;next+=0x1000;objects[p]=std::vector<unsigned char>(size);return p;}
    template<class T>void put(std::uint64_t p,unsigned off,T value){std::memcpy(objects.at(p).data()+off,&value,sizeof(value));}
    template<class T>T get(std::uint64_t p,unsigned off){T value{};std::memcpy(&value,objects.at(p).data()+off,sizeof(value));return value;}
    bool region(std::uint64_t p,v24port::Region& out)override {
        for(const auto& x:objects)if(p>=x.first&&p<x.first+x.second.size()){out={x.first,x.second.size(),true,true,true};return true;}return false;
    }
    bool read(std::uint64_t p,void* out,std::size_t n)override {
        for(const auto& x:objects)if(p>=x.first&&p+n<=x.first+x.second.size()){std::memcpy(out,x.second.data()+p-x.first,n);return true;}return false;
    }
    bool write(std::uint64_t p,const void* in,std::size_t n)override {
        for(auto& x:objects)if(p>=x.first&&p+n<=x.first+x.second.size()){std::memcpy(x.second.data()+p-x.first,in,n);return true;}return false;
    }
    v24port::Return invoke(v24port::Call call,const Profile& profile,std::uint64_t object,bool mode)override {
        using v24port::Call;v24port::Return r{};r.normal=true;r.boolean=true;
        if(call==Call::Factory){
            const auto p=allocate(profile.size);r.object=p;put(p,0,Base+profile.vtable);put(p,8,std::uint32_t{0x165});
            for(unsigned off:{0x10,0x18,0x20})put(p,off,std::uint64_t{0x2d2d2d});
            for(unsigned off:{0x28,0x2c})put(p,off,std::uint32_t{0x29c77f8});
            // Independent constructor fixture, including the exact-PE 0x35f620 write.
            put(p,0x30,std::int32_t{-1});put(p,0x34,std::uint32_t{profile.family==Family::Coalition||profile.family==Family::N_abandon_union?2u:0u});put(p,0x38,std::uint8_t{1});
            if(bad_union_state&&profile.family==Family::N_abandon_union)put(p,0x34,std::uint32_t{0});
            if(profile.family==Family::Marriage||profile.family==Family::N_invite_to_federation)put(p,0x58,std::uint64_t{15});
            if(profile.family==Family::Insult)put(p,0x40,std::int32_t{-1});
            if(profile.family==Family::FavorTrust){put(p,0x40,std::int32_t{3000});put(p,0x44,std::int32_t{7});}
            if(profile.family==Family::N_scriptable_diplomatic_action){assert(object==Definition);put(p,0x40,object);}
            if(profile.family==Family::N_tributary_state_action)put(p,0x40,std::int32_t{2});
            if(profile.family==Family::N_transfer_trade_power)put(p,0x40,std::int32_t{500});
            if(profile.family==Family::N_warsubsidy){put(p,0x40,std::int32_t{1000});put(p,0x44,std::int32_t{10});}
        } else if(call==Call::Setter)put(object,0x38,std::uint8_t{mode?1u:0u});
        else if(call==Call::Wrapper){
            const auto copy=objects.at(object);const auto clone=allocate(profile.size);objects.at(clone)=copy;
            if(profile.wrapper!=0x4e9930&&!mode)put(clone,0x30,std::int32_t{17});
            if(corrupt&&profile.family==Family::N_scriptable_diplomatic_action)put(clone,0x40,Definition+8);
            const auto cmd=allocate(0x58);r.object=cmd;r.returned_same_slot=true;put(cmd,0,Base+0x1c814b0);put(cmd,8,std::uint32_t{0x165});
            put(cmd,0x30,std::uint64_t{15});put(cmd,0x38,std::int32_t{-1});put(cmd,0x44,std::uint32_t{0x2934});put(cmd,0x48,std::uint64_t{0xffff});put(cmd,0x50,clone);
        } else if(call==Call::ActionDestructor)objects.erase(object);
        else if(call==Call::CommandDestructor){objects.erase(get<std::uint64_t>(object,0x50));objects.erase(object);}
        return r;
    }
    TransferReturn submit(const v24port::TransferEnvelope& e)override {
        assert(!sent);sent=true;++submitted;
        for(unsigned i=0;i<e.extra_count;++i){const auto& x=e.extra[i];std::uint64_t value=0;assert(read(e.clone+x.offset,&value,x.width));assert(value==x.value);}
        objects.erase(e.clone);objects.erase(e.command);return {true,true,true,0};
    }
};
PairStamp stamp(){PairStamp s{};s.process_creation=s.session=s.module_pin=s.owner_thread=s.world_witness=1;
    s.database=0x200000000ULL;s.game=0x210000000ULL;s.array=0x220000000ULL;s.actor_object=0x230000000ULL;s.target_object=0x240000000ULL;
    s.count=200;s.date=56456976;s.actor.value=(1ULL<<56)|(189ULL<<32)|0x524f50;s.target.value=(1ULL<<56)|(116ULL<<32)|0x495242;
    s.current_player.value=(1ULL<<56)|(122ULL<<32)|0x415246;s.effective_player=s.current_player;assert(valid(s));return s;}
}
int main(){unsigned cases=0;
    for(const auto& p:profiles()) {
        Model m;v24port::NativePairEngineDraft e(m,Definition);const auto original=e.factory(p);assert(original.value&&e.initialize_owned(original,stamp()));
        const bool mode=p.wrapper==0x4e9930; // Exercise native stop-wrapper envoy binding for both annexation families.
        e.mode_setter(p,original,mode);assert(e.full88(p,original,nullptr,false));const auto wrapped=e.wrapper(p,original);assert(wrapped.command.value);
        CommandView c{};assert(e.command_view(wrapped.command,c)&&c.clone.value);assert(e.command_gate(wrapped.command));assert(e.destroy_action(p,original));
        const auto sent=e.transfer_owned(wrapped.command);assert(sent.normal&&sent.value&&sent.slot_consumed&&m.submitted==1&&m.objects.empty());
        const auto d=e.diagnostics();assert(!d.frozen&&d.live==0&&d.quarantined==0);++cases;
    }
    {Model m;m.corrupt=true;v24port::NativePairEngineDraft e(m,Definition);const Profile* p=nullptr;
     for(const auto& x:profiles())if(x.family==Family::N_scriptable_diplomatic_action)p=&x;assert(p);
     const auto original=e.factory(*p);assert(e.initialize_owned(original,stamp()));e.mode_setter(*p,original,true);assert(e.full88(*p,original,nullptr,false));
     bool rejected=false;try{e.wrapper(*p,original);}catch(const v24port::NativeFault&){rejected=true;}
     assert(rejected&&e.diagnostics().frozen&&e.diagnostics().quarantined&&m.submitted==0);++cases;}
    {Model m;m.bad_union_state=true;v24port::NativePairEngineDraft e(m);const Profile* p=nullptr;
     for(const auto& x:profiles())if(x.family==Family::N_abandon_union)p=&x;assert(p);
     bool rejected=false;try{e.factory(*p);}catch(const v24port::NativeFault& f){rejected=f.reason==v24port::Fault::Fields;}
     assert(rejected&&e.diagnostics().frozen&&e.diagnostics().quarantined&&m.submitted==0);++cases;}
    std::printf("native_expansion_cases=%u native_calls=0 game_access=0\n",cases);return 0;
}
