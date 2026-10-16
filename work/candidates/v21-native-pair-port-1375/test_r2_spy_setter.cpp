// Preserve the real setter side effect against the unchanged sealed R2 caller.
#define main original_fake_suite_main
#include "test_native_pair_engine.cpp"
#undef main
namespace binding_fixture {
struct Memory final : SyntheticReadPort {
    std::map<std::uint64_t,std::uint8_t> bytes;std::size_t reads=0;std::vector<std::uint64_t> addresses;
    std::function<void(Memory&,std::uint64_t)> hook;
    template<class T>void put(std::uint64_t at,T value) {
        unsigned char buffer[sizeof(T)];std::memcpy(buffer,&value,sizeof(T));
        for(std::size_t i=0;i<sizeof(T);++i)bytes[at+i]=buffer[i];
    }
    bool read(std::uint64_t at,void* output,std::size_t size) override {
        ++reads;addresses.push_back(at);if(hook)hook(*this,at);auto* target=static_cast<unsigned char*>(output);
        for(std::size_t i=0;i<size;++i){auto it=bytes.find(at+i);if(it==bytes.end())return false;target[i]=it->second;}return true;
    }
};
constexpr std::uint64_t module=0x140000000ULL,records=0x80000,root=0x90000,holder=0xa0000,manager=0xb0000,
    begin=0xc0000,entry=0xd0000,mission=0xe0000,task=0xf0000,owner=0x100000,node=0x110000;
void spy_fixture(Memory& m,const PairStamp& s) {
    m.put(module+0x233d8d0,s.database);m.put(module+0x233fe78,s.game);m.put(s.database+0x118,s.array);m.put(s.database+0x124,s.count);
    m.put(s.array+122*8,s.actor_object);m.put(s.array+46*8,s.target_object);m.put(s.actor_object+0x20,s.actor.value);m.put(s.target_object+0x20,s.target.value);
    m.put(s.game+0x1dd0,s.date);m.put(s.game+0x1e60,s.current_player.value);m.put(s.game+0x7485,std::uint8_t{0});
    m.put(s.actor_object+0x1510,records);auto rec=records+46*0x48;m.put(rec,root);m.put(rec+8,s.actor.value);m.put(rec+0x10,s.target.value);m.put(rec+0x46,std::uint8_t{8});
    m.put(s.actor_object+0x1480,holder);m.put(holder+0x18,manager);m.put(manager+0x20,begin);m.put(manager+0x28,begin+8);
    m.put(begin,entry);m.put(entry+0x18,std::uint8_t{2});m.put(entry+0x10,mission);m.put(entry+0x44,std::int32_t{17});
    m.put(mission,module+0x1c4b2b8);m.put(mission+0xa0,task);m.put(mission+0x80,s.actor.value);m.put(mission+0x88,s.target.value);
    m.put(mission+0xa8,std::uint32_t{0x3378});m.put(mission+0x48,entry);m.put(mission+0x50,std::int32_t{17});
    m.put(task,module+0x1ce3ba0);m.put(task+0x20,s.target.value);m.put(task+0x18,s.actor.value);m.put(task+0x28,std::uint8_t{0});
    m.put(task+0x2c,std::int32_t{17});m.put(task+0x10,owner);
    m.put(s.target_object+0x14b0,owner);m.put(owner+0x4f0,node);m.put(owner+0x4f8,node);m.put(owner+0x500,std::uint32_t{1});
    m.put(node,task);m.put(node+8,std::uint64_t{0});m.put(node+0x10,std::uint64_t{0});m.put(node+0x18,std::uint8_t{0});
}
}
int main(){try{
 Fake f;f.native_envoy=17;Guard g;NativePairEngineDraft e(f);binding_fixture::Memory m;binding_fixture::spy_fixture(m,g.s);
 Request request{};request.action=Action::StopSpyNetwork;request.actor.bytes={'F','R','A'};request.target.bytes={'E','N','G'};
 auto result=preflight_no_send(request,g,e,100,&m,f.module());
 CHECK(result.status==Status::Frozen);CHECK(std::string(result.reason)=="envoy_binding_changed");
 CHECK(f.get<std::int32_t>(f.last_original+0x30)==17);CHECK(f.native_entries==2);CHECK(f.deletes==0);
 std::cout<<"r2_real_setter_integration_block_reproduced=true checks="<<checks<<" native_calls=0\n";return 0;
 }catch(...){std::cerr<<"R2 setter evidence failed\n";return 1;}}
