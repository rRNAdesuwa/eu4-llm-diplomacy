#include "country_resolver.h"
#include "selected_pins.h"
#include <cassert>
#include <cstdio>
#include <functional>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>

using namespace country1375;
namespace {
constexpr std::uint64_t Base=0x140000000, DB=0x200000000, Game=0x200100000, Array=0x200200000, Objects=0x210000000;
std::uint64_t handle(const std::string& tag,std::uint32_t slot,std::uint8_t generation=2) {
    return (std::uint64_t{generation}<<56)|(std::uint64_t{slot}<<32)|
        (std::uint64_t{static_cast<std::uint8_t>(tag[0])})|(std::uint64_t{static_cast<std::uint8_t>(tag[1])}<<8)|(std::uint64_t{static_cast<std::uint8_t>(tag[2])}<<16);
}
class Memory final:public ReadPort {
public:
    std::map<std::uint64_t,std::uint8_t> data;
    std::vector<std::pair<std::uint64_t,std::size_t>> reads;
    std::function<void(Memory&,std::uint64_t,std::size_t)> callback;
    bool fail{},throw_read{};
    template<class T>void put(std::uint64_t address,T value) {
        const auto* p=reinterpret_cast<const std::uint8_t*>(&value);
        for(std::size_t i=0;i<sizeof(T);++i)data[address+i]=p[i];
    }
    bool read(std::uint64_t a,void* out,std::size_t n) override {
        reads.emplace_back(a,n);if(callback)callback(*this,a,n);
        if(throw_read)throw std::runtime_error("synthetic read");if(fail)return false;
        auto* b=static_cast<std::uint8_t*>(out);
        for(std::size_t i=0;i<n;++i) {const auto p=data.find(a+i);if(p==data.end())return false;b[i]=p->second;}
        return true;
    }
    void row(std::uint32_t slot,const std::string& tag,std::uint8_t generation=2) {
        const auto addr=Objects+std::uint64_t{slot}*0x1000;
        put(Array+std::uint64_t{slot}*8,addr);put(addr,Base+0x1c574a0);put(addr+8,std::uint32_t{0x165});
        put(addr+0x20,slot==0?std::uint64_t{0x2d2d2d}:handle(tag,slot,generation));
    }
    explicit Memory(std::uint32_t count=3) {
        for(const auto& pin:SelectedPins)for(std::uint32_t i=0;i<pin.length;++i)data[Base+pin.rva+i]=pin.bytes[i];
        put(Base+0x233d8d0,DB);put(Base+0x233fe78,Game);put(DB+0x118,Array);
        put(DB+0x120,static_cast<std::int32_t>(count));put(DB+0x124,static_cast<std::int32_t>(count));
        put(Game+0x1dd0,std::int32_t{56456976});put(Game+0x1e60,handle("FRA",1));
        put(Game+0x1e68,std::uint64_t{0x2d2d2d});put(Game+0x7485,std::uint8_t{0});put(Game+0x74c8,std::uint64_t{0});
        for(std::uint32_t i=0;i<count;++i)put(Array+std::uint64_t{i}*8,std::uint64_t{0});
        row(1,"FRA");if(count>=3)row(2,"ENG");
    }
};
std::size_t groups{};
void group(const char* name,const std::function<void()>& test) {test();++groups;std::printf("PASS %s\n",name);}
Result run(Memory& m,const std::vector<std::string_view>& tags={"FRA","ENG"}) {return resolve(m,Base,tags);}
void rejected(Memory& m,Status status) {const auto r=run(m);assert(r.status==status&&!r.stable_two_pass&&r.bindings.empty()&&!r.runtime_verified&&!r.native_authorized&&!r.production_ready&&!r.atomic);}
}
int main() {
    group("valid_full_handles_and_budget",[] {Memory m;const auto r=run(m);assert(r.status==Status::Resolved&&r.stable_two_pass&&!r.atomic);
        assert(r.bindings.size()==2&&r.bindings[0].handle==handle("FRA",1)&&r.bindings[1].address==Objects+0x2000);
        assert(r.snapshot.rows.size()==3&&r.read_calls==60+2*SelectedPins.size());
        std::uint64_t pinbytes=0;for(const auto& p:SelectedPins)pinbytes+=p.length;
        assert(r.read_bytes==252+32*3+40*2+2*pinbytes);});
    group("request_validation_before_reads",[] {for(const auto& tags:std::vector<std::vector<std::string_view>>{{},{"fra"},{"FRA","FRA"},{"F RA"},{"FR"},{"FRA0"}}) {Memory m;assert(run(m,tags).status==Status::InvalidRequest&&m.reads.empty());}});
    group("at_most_sixteen",[] {Memory m;std::vector<std::string_view> tags(17,"FRA");assert(run(m,tags).status==Status::InvalidRequest&&m.reads.empty());});
    group("module_range_before_reads",[] {Memory m;assert(resolve(m,Base+8,{"FRA"}).status==Status::InvalidRequest&&m.reads.empty());});
    group("selected_code_pin",[] {Memory m;m.data[Base+SelectedPins[0].rva]^=1;rejected(m,Status::UnsupportedLayout);});
    group("signed_capacity_count_date",[] {for(const auto address:std::array<std::uint64_t,3>{DB+0x120,DB+0x124,Game+0x1dd0}) {Memory m;m.put(address,std::int32_t{-1});rejected(m,Status::InvalidObservation);}});
    group("unknown_selector",[] {Memory m;m.put(Game+0x1e60,handle("FRA",1)|(std::uint64_t{7}<<48));rejected(m,Status::UnsupportedLayout);});
    group("reset_load",[] {Memory a;a.put(Game+0x7485,std::uint8_t{1});rejected(a,Status::InvalidObservation);Memory b;b.put(Game+0x74c8,std::uint64_t{0x12340000});rejected(b,Status::InvalidObservation);});
    group("header_guards_derived_handle",[] {for(bool vt:{false,true}) {Memory m;m.put(Objects+0x2000+(vt?0:8),vt?std::uint64_t{Base+0x1000}:std::uint64_t{0});
        rejected(m,Status::UnsupportedLayout);for(const auto& read:m.reads)assert(read.first!=Objects+0x2020);}});
    group("aliased_before_second_header",[] {Memory m;m.put(Array+16,Objects+0x1000);rejected(m,Status::InvalidObservation);std::size_t n=0;for(const auto& r:m.reads)if(r.first==Objects+0x1000)++n;assert(n==1);});
    group("duplicate_tag_different_handle",[] {Memory m;m.row(2,"FRA",255);rejected(m,Status::InvalidObservation);});
    group("wrong_ordinal",[] {Memory m;m.put(Objects+0x2020,handle("ENG",1));rejected(m,Status::InvalidObservation);});
    group("generation_byte_is_preserved",[] {for(std::uint8_t generation:{std::uint8_t{128},std::uint8_t{255}}) {Memory m;m.row(2,"ENG",generation);const auto r=run(m);assert(r.status==Status::Resolved&&r.bindings[1].handle==handle("ENG",2,generation));}});
    group("unsupported_handle_profile",[] {for(std::uint64_t mask:{std::uint64_t{1}<<24,std::uint64_t{1}<<48}) {Memory m;m.put(Objects+0x2020,handle("ENG",2)|mask);rejected(m,Status::UnsupportedLayout);}});
    group("reserved_slot",[] {Memory good;good.row(0,"---");assert(run(good).status==Status::Resolved);Memory bad;bad.row(0,"---");bad.put(Objects+0x20,handle("AAA",0));rejected(bad,Status::InvalidObservation);});
    group("current_player_complete_identity",[] {Memory m;m.put(Game+0x1e60,handle("FRA",1,3));rejected(m,Status::InvalidObservation);});
    group("missing_tag_not_absence",[] {Memory m;const auto r=run(m,{"POR"});assert(r.status==Status::MissingTag&&r.bindings.empty());});
    group("inside_pass_mutation",[] {Memory m;m.callback=[](Memory& x,std::uint64_t a,std::size_t){if(a==Objects+0x2020)x.put(Game+0x1dd0,std::int32_t{56456977});};rejected(m,Status::Changed);});
    group("between_pass_mutation",[] {Memory m;std::size_t n=0;m.callback=[&](Memory& x,std::uint64_t a,std::size_t){if(a==Base+0x233d8d0&&++n==3)x.row(2,"ENG",3);};rejected(m,Status::Changed);});
    group("missing_short_and_throw_reads",[] {Memory a;a.fail=true;rejected(a,Status::UnavailableRead);Memory b;b.throw_read=true;rejected(b,Status::UnavailableRead);Memory c;c.data.erase(Objects+0x2027);rejected(c,Status::UnavailableRead);});
    group("full_bound_and_shared_budget",[] {Memory m(4096);for(std::uint32_t i=3;i<4096;++i) {std::string tag(3,'A');const std::string alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
        tag[0]=alphabet[(i/(36*36))%36];tag[1]=alphabet[(i/36)%36];tag[2]=alphabet[i%36];m.row(i,tag);}
        const auto r=run(m);assert(r.status==Status::Resolved&&r.snapshot.rows.size()==4096&&r.read_calls<20000&&r.read_bytes<512*1024);});
    group("same_value_aba_not_excluded",[] {Memory m;m.callback=[](Memory& x,std::uint64_t a,std::size_t){if(a==Objects+0x2020){x.put(Game+0x1dd0,std::int32_t{1});x.put(Game+0x1dd0,std::int32_t{56456976});}};
        const auto r=run(m);assert(r.status==Status::Resolved&&!r.atomic&&!r.native_authorized);});
    std::printf("groups=%zu native_calls=0 game_access=0\n",groups);return 0;
}
