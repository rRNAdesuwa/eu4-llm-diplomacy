// Pure synthetic memory: no invoke(), process handle, or native function call.
#include "generated/pair-engine-1375.cpp"
#include <initializer_list>
namespace {
using namespace eu4_pair_1375;
alignas(8) unsigned char countries[3][0x1a00]{}, records[3][190 * 0x48]{}, roots[3][0x300]{};
alignas(8) unsigned char indexes[3][4][32]{}, relation[0x80]{}, other[0x80]{}, dependency[0x80]{};
alignas(8) unsigned char nodes[2][0x20]{}, registry[0x80]{}, definition[0x130]{};
alignas(8) unsigned char database[0x130]{};
alignas(8) std::uintptr_t country_array[4096]{}, registry_reference = 0;
std::uintptr_t image = 0;
Live live{};
unsigned checks = 0, failures = 0;
char last_audit[2048]{};
bool audit_accept=true;
bool capture_audit(void*,const char* text,std::size_t length) {
    if(length>=sizeof(last_audit))return false;
    std::memcpy(last_audit,text,length);last_audit[length]=0;return audit_accept;
}
const Country& fra = kCountries[0]; const Country& eng = kCountries[1]; const Country& por = kCountries[2];
std::uintptr_t addr(const void* p) { return reinterpret_cast<std::uintptr_t>(p); }
template<class T> void put(unsigned char* p, std::size_t off, T value) { std::memcpy(p + off, &value, sizeof(value)); }
void expect(bool result, const char* label) { ++checks; if (!result) { ++failures; std::printf("FAIL: %s\n", label); } }
void reset() {
    std::memset(countries,0,sizeof(countries));std::memset(records,0,sizeof(records));std::memset(roots,0,sizeof(roots));
    std::memset(indexes,0,sizeof(indexes));std::memset(relation,0,sizeof(relation));std::memset(other,0,sizeof(other));
    std::memset(dependency,0,sizeof(dependency));std::memset(nodes,0,sizeof(nodes));std::memset(registry,0,sizeof(registry));
    std::memset(definition,0,sizeof(definition));std::memset(country_array,0,sizeof(country_array));
    std::memset(database,0,sizeof(database));put(database,0x118,addr(country_array));put(database,0x124,std::uint32_t{190});
    registry_reference=addr(registry);image=addr(&registry_reference)-kSubjectRegistry;
    for(unsigned i=0;i<3;++i) {
        const Country& self=kCountries[i];country_array[self.slot]=addr(countries[i]);
        put(countries[i],0x20,self.handle);put(countries[i],0x1510,addr(records[i]));
        put(countries[i],0x18f0,std::uint64_t{0x2d2d2d});put(countries[i],0x18f8,std::uint64_t{0x2d2d2d});
        for(unsigned j=0;j<3;++j) {
            put(records[i],kCountries[j].slot*0x48,addr(roots[i]));
            put(records[i],kCountries[j].slot*0x48+0x10,kCountries[j].handle);
        }
    }
    live={};live.database=addr(database);live.array=addr(country_array);live.actor_object=addr(countries[0]);live.target_object=addr(countries[1]);
    live.stamp.actor_handle=fra.handle;live.stamp.target_handle=eng.handle;live.stamp.raw_date=56456976;
}
void index(unsigned owner,unsigned counterpart,std::size_t off,std::size_t count,unsigned bank,unsigned char* object) {
    put(roots[owner],off,addr(indexes[owner][bank]));put(roots[owner],count,std::uint32_t{1});
    put(indexes[owner][bank],0,kCountries[counterpart].slot);put(indexes[owner][bank],8,addr(object));
}
void pair(std::size_t a,std::size_t ac,std::size_t b,std::size_t bc,unsigned bank=0) {
    index(0,1,a,ac,bank,relation);index(1,0,b,bc,bank,relation);
}
void header(unsigned char* object,std::uintptr_t vt,std::uint64_t first,std::uint64_t second) {
    put(object,0,image+vt);put(object,8,std::uint32_t{0x165});put(object,0x10,first);put(object,0x18,second);
    put(object,0x20,std::uint32_t{56456970});put(object,0x28,static_cast<unsigned char>(0));
}
bool bind(ActionId id,Binding* result=nullptr) {
    Binding temp{};return cancellation_binding(image,live,fra,eng,id,result==nullptr?temp:*result);
}
void subject(bool actor_subject) {
    const unsigned dependent=actor_subject?0:1;
    put(countries[dependent],0x18f0,por.handle);
    index(2,dependent,0x128,0x134,2,dependency);index(dependent,2,0x128,0x134,2,dependency);
    header(dependency,0x1c81758,por.handle,kCountries[dependent].handle);
    put(dependency,0x40,addr(definition));put(registry,0x58,addr(definition));
    std::memcpy(definition+0x10,"vassal",7);put(definition,0x20,std::uint64_t{6});put(definition,0x28,std::uint64_t{15});
    put(definition,0x11a,static_cast<unsigned char>(1));
}
void coalition() {
    put(countries[0],0x18f8,eng.handle);put(countries[1],0x1910,addr(nodes[0]));
    put(countries[1],0x1918,addr(nodes[0]));put(countries[1],0x1920,std::uint32_t{1});put(nodes[0],0,fra.handle);
}
}
int main() {
    using namespace eu4_pair_1375;
    expect(sizeof(kActions)/sizeof(kActions[0])==20,"20 families");
    expect(sizeof(kNames)/sizeof(kNames[0])==36,"36 action IDs");
    unsigned positive_only=0, matrix_count=0;
    for(unsigned family=0;family<20;++family) {
        unsigned modes=0;for(const auto& mode:kModes)if(mode.family==family)++modes;
        positive_only+=modes==1?1U:0U;matrix_count+=modes*2;
        expect(modes==(family==12||family==13||family==18||family==19?1U:2U),"exact real modes per family");
    }
    expect(positive_only==4&&matrix_count==72,"4 positive-only and 72 pair cases");
    for(unsigned i=0;i<36;++i) {
        ActionId decoded{};const auto id=static_cast<ActionId>(i);
        expect(parse_action_id(action_name(id),std::strlen(action_name(id)),&decoded)&&decoded==id,"36 names roundtrip");
        if(i<24)expect(kModes[i].family==i/2&&kModes[i].positive==(i%2==0),"old 24 ordinals stable");
        Host host{};host.log=capture_audit;Request request{};request.action=id;
        std::memcpy(request.actor,"FRA",4);std::memcpy(request.target,"ENG",4);Result result{};
        expect(audit(host,request,result,"pair_engine_complete"),"bounded core audit accepted");
        char expected[256]{};
        std::snprintf(expected,sizeof(expected),"\"fixed_subsidy_amount_milli\":%d,\"fixed_subsidy_duration_years\":%d,\"fixed_gift_amount_milli\":%d,\"fixed_transfer_fraction_milli\":%d,\"fixed_insult_index\":%d}",
            i==22||i==23?1000:0,i==22||i==23?10:0,i==34?25000:0,i==30||i==31?500:0,i==25?-1:0);
        expect(std::strstr(last_audit,expected)!=nullptr,"per-ID audit scalars include only own family");
        audit_accept=false;expect(!audit(host,request,result,"pair_engine_dispatch_intent"),"audit failure remains failure");audit_accept=true;
    }
    for(const char* name:{"cancel_warning","cancel_insult","cancel_gift","cancel_trade_favors_for_gold"}) {
        ActionId decoded{};expect(!parse_action_id(name,std::strlen(name),&decoded),"fabricated cancel rejected");
    }
    for(const auto& action:kActions) {
        reset();alignas(8) unsigned char memory[0x80]{};const auto object=addr(memory);
        put(memory,0,image+action.vtable);put(memory,8,std::uint32_t{0x165});
        for(const auto off:{0x10,0x18,0x20})put(memory,static_cast<std::size_t>(off),std::uint64_t{0x2d2d2d});
        put(memory,0x28,std::uint32_t{0x29c77f8});put(memory,0x2c,std::uint32_t{0x29c77f8});
        put(memory,0x30,std::int32_t{-1});put(memory,0x38,std::uint16_t{1});
        if(action.size==0x68)put(memory,0x58,std::uint64_t{15});
        if(action.token==0x2947)put(memory,0x40,std::int32_t{-1});
        expect(factory_fields(object,action),"exact factory defaults");
        if(action.size==0x40)std::memset(memory+0x40,0xa5,0x10);
        initialize(object,action,live);
        Binding binding{-1,0,0,0};expect(fields_match(object,action,live,true,binding),"fixed initialization");
        if(action.size==0x40)expect(read_at<std::uint64_t>(object+0x40)==0xa5a5a5a5a5a5a5a5ULL&&read_at<std::uint64_t>(object+0x48)==0xa5a5a5a5a5a5a5a5ULL,"base-only family has no out-of-size fixed field write");
        if(action.token==0x2947||action.token==0x2948||action.token==0x2e09) {
            put(memory,0x40,std::int32_t{42});expect(!fields_match(object,action,live,true,binding),"wrong fixed scalar rejected");
            v11_initialize_fixed(object,action.token);expect(fields_match(object,action,live,true,binding),"fixed scalar restored");
            if(action.token==0x2e09) {put(memory,0x44,static_cast<unsigned char>(1));expect(!fields_match(object,action,live,true,binding),"special transfer flag rejected");}
        }
    }
    reset();expect(bind(ActionId::warn),"warning absent pair accepted");pair(0x1b8,0x1c4,0x1b8,0x1c4);
    expect(!bind(ActionId::warn),"existing warning not overwritten");reset();put(roots[0],0x1c4,std::uint32_t{1});
    expect(!bind(ActionId::warn),"missing index storage is not absent warning");
    for(bool transfer:{false,true})for(bool incoming:{false,true}) {
        reset();const auto positive=transfer?ActionId::request_trade_power:ActionId::steer_trade;
        const auto cancel=transfer?ActionId::cancel_trade_power_transfer:ActionId::cancel_steer_trade;
        const std::size_t so=transfer?0x230:0x260,sc=transfer?0x23c:0x26c,ro=transfer?0x248:0x278,rc=transfer?0x254:0x284;
        expect(bind(positive)&&!bind(cancel),"absent trade allows request not cancellation");
        pair(incoming?ro:so,incoming?rc:sc,incoming?so:ro,incoming?sc:rc);
        header(relation,transfer?0x1c571f0:0x1c7d498,incoming?eng.handle:fra.handle,incoming?fra.handle:eng.handle);
        if(transfer)put(relation,0x40,std::int32_t{500});
        Binding before{},after{};expect(bind(cancel,&before)&&!bind(positive),"directed existing trade cancellation");
        expect(before.scope[0]==(incoming?1U:2U),"binding retains exact trade direction");
        expect(bind(cancel,&after)&&same_binding(before,after),"unchanged trade binding equal");
        put(relation,0x20,std::uint32_t{56456971});expect(bind(cancel,&after)&&!same_binding(before,after),"recreated trade start changes binding");
        put(relation,0x20,std::uint32_t{56456970});put(relation,0x28,static_cast<unsigned char>(1));expect(!bind(cancel),"removed trade rejected");put(relation,0x28,static_cast<unsigned char>(0));
        put(relation,transfer?0x44:0x40,static_cast<unsigned char>(1));expect(!bind(cancel),"special trade variant rejected");put(relation,transfer?0x44:0x40,static_cast<unsigned char>(0));
        if(transfer) {put(relation,0x40,std::int32_t{499});expect(!bind(cancel),"nonfixed trade fraction rejected");put(relation,0x40,std::int32_t{500});}
        put(relation,0x10,incoming?fra.handle:eng.handle);expect(!bind(cancel),"opposite header rejected");put(relation,0x10,incoming?eng.handle:fra.handle);
        put(indexes[1][0],8,addr(other));expect(!bind(cancel),"bilateral pointer mismatch rejected");put(indexes[1][0],8,addr(relation));
        put(records[0],eng.slot*0x48+0x10,eng.handle^0x0100000000000000ULL);expect(!bind(cancel),"stale counterpart generation rejected");put(records[0],eng.slot*0x48+0x10,eng.handle);
        put(roots[0],incoming?rc:sc,std::uint32_t{4097});expect(!bind(cancel),"index bound rejected");put(roots[0],incoming?rc:sc,std::uint32_t{2});
        put(indexes[0][0],0x10,eng.slot);put(indexes[0][0],0x18,addr(relation));expect(!bind(cancel),"duplicate slot rejected");put(roots[0],incoming?rc:sc,std::uint32_t{1});
        pair(incoming?so:ro,incoming?sc:rc,incoming?ro:so,incoming?rc:sc,1);expect(!bind(cancel),"bidirectional trade ambiguous rejected");
    }
    for(bool actor_subject:{false,true})for(bool actor_first:{false,true}) {
        reset();subject(actor_subject);expect(bind(ActionId::support_independence),"supported subject can create absent support");
        pair(0x170,0x17c,0x170,0x17c);header(relation,0x1c80570,actor_first?fra.handle:eng.handle,actor_first?eng.handle:fra.handle);
        Binding before{},after{};expect(bind(ActionId::cancel_independence_support,&before),"support accepts native proposal order");
        expect(!bind(ActionId::support_independence),"existing support cannot be recreated");
        put(dependency,0x20,std::uint32_t{56456971});expect(bind(ActionId::cancel_independence_support,&after)&&!same_binding(before,after),"dependency recreation invalidates binding");
        put(definition,0x11a,static_cast<unsigned char>(0));expect(!bind(ActionId::cancel_independence_support),"disabled subject role rejected");put(definition,0x11a,static_cast<unsigned char>(1));
        put(registry,0x58,std::uintptr_t{0});expect(!bind(ActionId::cancel_independence_support),"unregistered definition rejected");put(registry,0x58,addr(definition));
        definition[0x10]='x';expect(!bind(ActionId::cancel_independence_support),"wrong definition name rejected");definition[0x10]='v';
        put(dependency,0x28,static_cast<unsigned char>(1));expect(!bind(ActionId::cancel_independence_support),"removed dependency rejected");put(dependency,0x28,static_cast<unsigned char>(0));
        const unsigned dependent=actor_subject?0:1,provider=actor_subject?1:0;
        put(countries[dependent],0x18f0,kCountries[provider].handle);expect(!bind(ActionId::cancel_independence_support),"own subject support rejected");
        put(countries[dependent],0x18f0,0x0100004400434241ULL);expect(!bind(ActionId::cancel_independence_support),"unknown overlord not scanned");
        put(countries[dependent],0x18f0,por.handle);put(countries[provider],0x18f0,por.handle);expect(!bind(ActionId::cancel_independence_support),"two subjects rejected");
    }
    reset();expect(bind(ActionId::form_coalition)&&!bind(ActionId::leave_coalition),"coalition empty direction");coalition();
    Binding before{},after{};expect(bind(ActionId::leave_coalition,&before)&&!bind(ActionId::form_coalition),"coalition present direction");
    put(countries[0],0x1940,std::uint32_t{1});expect(bind(ActionId::leave_coalition,&after)&&!same_binding(before,after),"coalition timeout changes binding");
    put(countries[1],0x1924,static_cast<unsigned char>(1));expect(!bind(ActionId::leave_coalition),"iterating coalition rejected");put(countries[1],0x1924,static_cast<unsigned char>(0));
    put(nodes[0],0x10,addr(nodes[0]));expect(!bind(ActionId::leave_coalition),"cycle rejected by finite count");put(nodes[0],0x10,std::uintptr_t{0});
    put(countries[1],0x1920,std::uint32_t{1025});expect(!bind(ActionId::leave_coalition),"coalition count bound");put(countries[1],0x1920,std::uint32_t{1});
    put(countries[0],0x20,fra.handle^0x0100000000000000ULL);expect(!bind(ActionId::leave_coalition),"coalition stale full handle");put(countries[0],0x20,fra.handle);
    put(nodes[0],0,0x010000ff00434241ULL);country_array[255]=1;
    expect(!bind(ActionId::leave_coalition),"member within 4096 but outside actual lookup never dereferenced");put(nodes[0],0,fra.handle);
    put(database,0x124,std::uint32_t{4097});expect(!bind(ActionId::leave_coalition),"database count bound");put(database,0x124,std::uint32_t{190});
    put(nodes[0],0x18,static_cast<unsigned char>(1));put(nodes[0],0,std::uint64_t{0xffffffffffffffffULL});
    country_array[fra.slot]=1;put(countries[0],0x18f8,std::uint64_t{0x2d2d2d});
    expect(bind(ActionId::form_coalition),"marked node never dereferences stale member");
    expect(!bind(ActionId::leave_coalition),"marked node not an active membership");
    // Comparison of all new scope fields must participate in the final guard.
    before={-1,0,0,0};for(unsigned i=0;i<8;++i){after=before;after.scope[i]=1;expect(!same_binding(before,after),"every scope field affects rebinding");}
    std::printf("v11 synthetic extension: %u checks, %u failures; no engine or process calls.\n",checks,failures);
    return failures?1:0;
}
