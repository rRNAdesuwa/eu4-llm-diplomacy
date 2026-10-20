// Offline synthetic-memory tests; never invokes an engine function or opens a process.
#include "../../native/v10/pair-engine-1375.cpp"
#include <initializer_list>
namespace {
using namespace eu4_pair_1375;
constexpr std::uintptr_t image = 0x140000000ULL;
alignas(8) unsigned char france[0x1900]{}, england[0x1900]{}, relation[0x80]{}, other[0x80]{};
alignas(8) unsigned char fra_records[190 * 0x48]{}, eng_records[190 * 0x48]{};
alignas(8) unsigned char fra_root[0x200]{}, eng_root[0x200]{}, fra_index[32]{}, eng_index[32]{};
unsigned checks = 0, failures = 0;
template<class T> void put(unsigned char* p, std::size_t offset, T value) { std::memcpy(p + offset, &value, sizeof(value)); }
std::uintptr_t addr(const void* p) { return reinterpret_cast<std::uintptr_t>(p); }
void expect(bool result, const char* label) { ++checks; if (!result) { ++failures; std::printf("FAIL: %s\n", label); } }
const Country& fra = kCountries[0]; const Country& eng = kCountries[1];
Live live{};
void reset() {
    std::memset(france,0,sizeof(france)); std::memset(england,0,sizeof(england));
    std::memset(relation,0,sizeof(relation)); std::memset(other,0,sizeof(other));
    std::memset(fra_records,0,sizeof(fra_records)); std::memset(eng_records,0,sizeof(eng_records));
    std::memset(fra_root,0,sizeof(fra_root)); std::memset(eng_root,0,sizeof(eng_root));
    std::memset(fra_index,0,sizeof(fra_index)); std::memset(eng_index,0,sizeof(eng_index));
    live = {}; live.actor_object=addr(france);live.target_object=addr(england);
    live.stamp.actor_handle=fra.handle;live.stamp.target_handle=eng.handle;live.stamp.raw_date=56456976;
    put(france,0x1510,addr(fra_records));put(england,0x1510,addr(eng_records));
    put(fra_records,eng.slot*0x48,addr(fra_root));put(eng_records,fra.slot*0x48,addr(eng_root));
    put(fra_records,eng.slot*0x48+0x10,eng.handle);put(eng_records,fra.slot*0x48+0x10,fra.handle);
}
void indexes(std::size_t fo, std::size_t fc, std::size_t eo, std::size_t ec) {
    put(fra_root,fo,addr(fra_index));put(fra_root,fc,std::uint32_t{1});
    put(eng_root,eo,addr(eng_index));put(eng_root,ec,std::uint32_t{1});
    put(fra_index,0,eng.slot);put(eng_index,0,fra.slot);
    put(fra_index,8,addr(relation));put(eng_index,8,addr(relation));
}
bool cancel(ActionId id) { Binding result{}; return cancellation_binding(image,live,fra,eng,id,result); }
void relation_header(std::uintptr_t vt, bool actor_first) {
    put(relation,0,image+vt);put(relation,0x10,actor_first ? fra.handle:eng.handle);
    put(relation,0x18,actor_first ? eng.handle:fra.handle);put(relation,0x20,std::uint32_t{56456970});
}
}
int main() {
    using namespace eu4_pair_1375;
    expect(sizeof(kActions)/sizeof(kActions[0])==12,"exact family count");
    expect(sizeof(kNames)/sizeof(kNames[0])==24,"exact action count");
    for (unsigned i=0;i<24;++i) {
        const auto id=static_cast<ActionId>(i);ActionId decoded{};
        expect(parse_action_id(action_name(id),std::strlen(action_name(id)),&decoded) && decoded==id,"all modes roundtrip");
    }
    for (const auto& action:kActions) {
        reset();alignas(8) unsigned char temporary[0x80]{};
        const auto object=addr(temporary);
        put(temporary,0,image+action.vtable);put(temporary,8,std::uint32_t{0x165});
        for (auto offset:{0x10,0x18,0x20})put(temporary,static_cast<std::size_t>(offset),std::uint64_t{0x2d2d2d});
        put(temporary,0x28,std::uint32_t{0x29c77f8});put(temporary,0x2c,std::uint32_t{0x29c77f8});
        put(temporary,0x30,std::int32_t{-1});put(temporary,0x38,std::uint16_t{1});
        if(action.size==0x68)put(temporary,0x58,std::uint64_t{15});
        expect(factory_fields(object,action),"factory defaults all families");
        for(bool mode:{false,true}) {
            initialize(object,action,live);put(temporary,0x38,static_cast<unsigned char>(mode));
            Binding binding{-1,0,0,0};
            expect(fields_match(object,action,live,mode,binding),"initialized fields all families and modes");
            if(action.token==0x2a25) {
                put(temporary,0x40,std::int32_t{0});expect(!fields_match(object,action,live,mode,binding),"zero subsidy rejected");
                put(temporary,0x40,std::int32_t{1000});put(temporary,0x44,std::int32_t{120});
                expect(!fields_match(object,action,live,mode,binding),"months instead of years rejected");
            }
        }
    }
    for(bool fleet:{false,true})for(bool holder:{false,true}) {
        reset();const auto id=fleet ? (holder?ActionId::cancel_fleet_basing_rights:ActionId::revoke_fleet_basing_rights)
                                   : (holder?ActionId::cancel_military_access:ActionId::revoke_military_access);
        const std::size_t ho=fleet?0xe0:0xb0,hc=fleet?0xec:0xbc,go=fleet?0xf8:0xc8,gc=fleet?0x104:0xd4;
        indexes(holder?ho:go,holder?hc:gc,holder?go:ho,holder?gc:hc);
        relation_header(fleet?0x1cddee0:0x1cdde60,holder);
        expect(cancel(id),"valid directed right");
        const auto opposite=fleet ? (holder?ActionId::revoke_fleet_basing_rights:ActionId::cancel_fleet_basing_rights)
                                  : (holder?ActionId::revoke_military_access:ActionId::cancel_military_access);
        expect(!cancel(opposite),"opposite direction rejected");
        put(relation,0x40,static_cast<unsigned char>(1));expect(!cancel(id),"enforce peace variant rejected");put(relation,0x40,static_cast<unsigned char>(0));
        put(relation,0x28,static_cast<unsigned char>(1));expect(!cancel(id),"removed relation rejected");put(relation,0x28,static_cast<unsigned char>(0));
        put(eng_index,8,addr(other));expect(!cancel(id),"different bilateral object rejected");put(eng_index,8,addr(relation));
        put(relation,0x10,holder?eng.handle:fra.handle);expect(!cancel(id),"wrong holder full handle rejected");
    }
    reset();indexes(0x110,0x11c,0x110,0x11c);relation_header(0x1c815d8,true);
    put(relation,0x40,std::int32_t{1000});put(relation,0x44,std::int32_t{10});
    expect(cancel(ActionId::cancel_subsidies),"payer cancellation fixed contract");
    relation_header(0x1c815d8,false);expect(!cancel(ActionId::cancel_subsidies),"payee cannot cancel payer contract");relation_header(0x1c815d8,true);
    put(relation,0x44,std::int32_t{120});expect(!cancel(ActionId::cancel_subsidies),"cancel refuses nonfixed years");put(relation,0x44,std::int32_t{10});
    put(relation,0x40,std::int32_t{2000});expect(!cancel(ActionId::cancel_subsidies),"cancel refuses nonfixed amount");
    reset();indexes(0x80,0x8c,0x80,0x8c);relation_header(0x1c7a740,true);
    expect(cancel(ActionId::dissolve_alliance),"alliance orientation one");relation_header(0x1c7a740,false);
    expect(cancel(ActionId::dissolve_alliance),"alliance orientation two");put(relation,0x28,static_cast<unsigned char>(1));
    expect(!cancel(ActionId::dissolve_alliance),"removed alliance rejected");
    reset();expect(!cancel(ActionId::revoke_embargo),"missing embargo rejected");
    put(fra_records,eng.slot*0x48+0x46,static_cast<unsigned char>(4));expect(!cancel(ActionId::revoke_embargo),"dirty bit is not embargo");
    put(eng_records,fra.slot*0x48+0x46,static_cast<unsigned char>(2));expect(!cancel(ActionId::revoke_embargo),"reverse embargo is not own embargo");
    put(fra_records,eng.slot*0x48+0x46,static_cast<unsigned char>(2));expect(cancel(ActionId::revoke_embargo),"outgoing embargo accepted");
    std::printf("v10 synthetic extension: %u checks, %u failures; no engine or process calls.\n",checks,failures);
    return failures?1:0;
}
