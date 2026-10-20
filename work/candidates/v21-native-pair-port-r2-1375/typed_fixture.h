// Selected existing fixture copied locally; not a native observer.
#pragma once
namespace typed_fixture {
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
    m.put(s.actor_object+0x1480,holder);m.put(s.actor_object+0x1488,holder+32);m.put(s.actor_object+0x1490,holder+32);
    m.put(holder+0x18,manager);m.put(manager,module+0x1cac380);m.put(manager+8,std::uint32_t{0x165});m.put(manager+0x10,std::uint32_t{0x2746});
    m.put(manager+0x14,std::uint8_t{3});m.put(manager+0x16,s.actor.value);
    m.put(manager+0x20,begin);m.put(manager+0x28,begin+8);m.put(manager+0x30,begin+8);
    m.put(begin,entry);m.put(entry,module+0x1cac2f0);m.put(entry+8,std::uint32_t{0x165});m.put(entry+0x40,std::uint8_t{3});
    m.put(entry+0x18,std::uint8_t{2});m.put(entry+0x10,mission);m.put(entry+0x44,std::int32_t{17});
    m.put(mission,module+0x1c4b2b8);m.put(mission+8,std::uint32_t{0x182});m.put(mission+0xa0,task);m.put(mission+0x80,s.actor.value);m.put(mission+0x88,s.target.value);
    m.put(mission+0xa8,std::uint32_t{0x3378});m.put(mission+0x48,entry);m.put(mission+0x50,std::int32_t{17});
    m.put(task,module+0x1ce3ba0);m.put(task+0x20,s.target.value);m.put(task+0x18,s.actor.value);m.put(task+0x28,std::uint8_t{0});
    m.put(task+0x2c,std::int32_t{17});m.put(task+0x10,owner);
    m.put(s.target_object+0x14b0,owner);m.put(owner+0x4f0,node);m.put(owner+0x4f8,node);m.put(owner+0x500,std::uint32_t{1});
    m.put(node,task);m.put(node+8,std::uint64_t{0});m.put(node+0x10,std::uint64_t{0});m.put(node+0x18,std::uint8_t{0});
}
}
