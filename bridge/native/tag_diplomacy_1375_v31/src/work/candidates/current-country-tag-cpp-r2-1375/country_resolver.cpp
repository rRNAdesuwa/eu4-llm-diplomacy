#include "country_resolver.h"
#include "selected_pins.h"
#include <algorithm>
#include <limits>
#include <set>

namespace country1375 {
namespace {
constexpr std::uint64_t Limit=std::uint64_t{1}<<47, ImageSize=0x25e0000, CountryVT=0x1c574a0;
constexpr std::uint64_t InvalidHandle=0x2d2d2d;
bool pointer(std::uint64_t p, bool nullable=false) noexcept { return (nullable&&p==0)||(p>=0x10000&&p<Limit&&p%8==0); }
bool ascii(char c) noexcept { return (c>='A'&&c<='Z')||(c>='0'&&c<='9'); }
struct Failure { Status status; const char* reason; };
void demand(bool ok, Status s, const char* reason) { if(!ok) throw Failure{s,reason}; }
class Budget {
    ReadPort& port;
public:
    std::uint32_t calls{}; std::uint64_t bytes{};
    explicit Budget(ReadPort& p):port(p){}
    void read(std::uint64_t a, void* b, std::size_t n) {
        demand(a>=0x10000&&a<Limit&&n>0&&n<=32768&&n<=Limit-a&&calls<20000&&bytes+n<=512*1024,
            Status::InvalidObservation,"read range or shared budget");
        ++calls;bytes+=n;
        demand(port.read(a,b,n),Status::UnavailableRead,"unavailable exact read");
    }
    template<class T> T get(std::uint64_t a) { T value{};read(a,&value,sizeof(value));return value; }
};
void pins(Budget& r, std::uint64_t module) {
    for(const auto& pin:SelectedPins) {
        std::array<std::uint8_t,8> actual{};r.read(module+pin.rva,actual.data(),pin.length);
        demand(std::equal(actual.begin(),actual.begin()+pin.length,pin.bytes.begin()),Status::UnsupportedLayout,"selected instruction bytes");
    }
}
Roots roots(Budget& r,std::uint64_t base) {
    Roots z{};z.module=base;
    z.database=r.get<std::uint64_t>(base+0x233d8d0);z.game=r.get<std::uint64_t>(base+0x233fe78);
    demand(pointer(z.database)&&pointer(z.game),Status::InvalidObservation,"root pointers");
    z.array=r.get<std::uint64_t>(z.database+0x118);
    const auto cap=r.get<std::int32_t>(z.database+0x120), count=r.get<std::int32_t>(z.database+0x124);
    demand(pointer(z.array)&&cap>=1&&cap<=4096&&count>=1&&count<=cap,
        Status::InvalidObservation,"country array signed bounds");
    z.capacity=static_cast<std::uint32_t>(cap);z.count=static_cast<std::uint32_t>(count);
    demand(static_cast<std::uint64_t>(count)*8<=Limit-z.array,Status::InvalidObservation,"country array extent");
    const auto date=r.get<std::int32_t>(z.game+0x1dd0);
    demand(date>0,Status::InvalidObservation,"positive signed date");z.date=static_cast<std::uint32_t>(date);
    z.current=r.get<std::uint64_t>(z.game+0x1e60);z.selector=r.get<std::uint8_t>(z.game+0x1e66);
    z.alternate_flag=r.get<std::uint8_t>(z.game+0x1e6f);z.alternate=r.get<std::uint64_t>(z.game+0x1e68);
    demand(z.selector==((z.current>>48)&255)&&z.alternate_flag==(z.alternate>>56),Status::Changed,"overlapping selectors");
    demand(z.selector==0,Status::UnsupportedLayout,"only ordinary selector0");
    z.reset=r.get<std::uint8_t>(z.game+0x7485);z.load=r.get<std::uint64_t>(z.game+0x74c8);
    demand(z.reset==0&&z.load==0,Status::InvalidObservation,"reset or load exclusion");return z;
}
Tag decode(std::uint64_t handle,std::uint32_t slot) {
    demand(((handle>>32)&65535)==slot,Status::InvalidObservation,"complete handle ordinal");
    demand((handle>>56)!=0&&((handle>>48)&255)<=7&&((handle>>24)&255)==0,
        Status::UnsupportedLayout,"bounded passive selector/generation profile");
    Tag t{};for(std::size_t i=0;i<3;++i)t.bytes[i]=static_cast<char>((handle>>(i*8))&255);
    demand(std::all_of(t.bytes.begin(),t.bytes.end(),ascii),Status::UnsupportedLayout,"ASCII handle TAG");return t;
}
Snapshot pass(Budget& r,std::uint64_t base) {
    Snapshot s{};s.roots=roots(r,base);s.array.resize(s.roots.count);
    r.read(s.roots.array,s.array.data(),s.array.size()*8);
    std::set<std::uint64_t> addresses,handles;std::set<std::array<char,3>> tags;
    bool player=false;s.rows.reserve(s.roots.count);
    for(std::uint32_t slot=0;slot<s.roots.count;++slot) {
        Row e{};e.slot=slot;e.address=s.array[slot];
        demand(pointer(e.address,true),Status::InvalidObservation,"country pointer");
        if(e.address) {
            demand(addresses.insert(e.address).second,Status::InvalidObservation,"alias before header dereference");
            std::array<std::uint8_t,12> h{};r.read(e.address,h.data(),h.size());
            for(std::size_t i=0;i<8;++i)e.vtable|=std::uint64_t{h[i]}<<(8*i);
            for(std::size_t i=0;i<4;++i)e.marker|=std::uint32_t{h[8+i]}<<(8*i);
            demand(e.vtable==base+CountryVT&&e.marker==0x165,Status::UnsupportedLayout,"country type before derived handle");
            e.handle=r.get<std::uint64_t>(e.address+0x20);
            demand(handles.insert(e.handle).second,Status::InvalidObservation,"duplicate full handle");
            if(slot==0&&e.handle==InvalidHandle)e.sentinel=true;
            else {demand(slot!=0,Status::InvalidObservation,"reserved slot0");e.tag=decode(e.handle,slot);
                demand(tags.insert(e.tag.bytes).second,Status::InvalidObservation,"duplicate TAG");
                if(e.handle==s.roots.current)player=true;
            }
        }
        s.rows.push_back(e);
    }
    std::vector<std::uint64_t> after(s.roots.count);r.read(s.roots.array,after.data(),after.size()*8);
    demand(after==s.array&&roots(r,base)==s.roots,Status::Changed,"in-pass table or roots changed");
    demand(player,Status::InvalidObservation,"current player must resolve to same complete object");return s;
}
}
bool Tag::operator==(const Tag& b) const noexcept {return bytes==b.bytes;}
bool parse_tag(std::string_view text,Tag& tag) noexcept {
    if(text.size()!=3||!std::all_of(text.begin(),text.end(),ascii))return false;
    std::copy(text.begin(),text.end(),tag.bytes.begin());return true;
}
bool Roots::operator==(const Roots& b) const noexcept {
    return module==b.module&&database==b.database&&game==b.game&&array==b.array&&current==b.current&&alternate==b.alternate&&load==b.load&&
        capacity==b.capacity&&count==b.count&&date==b.date&&selector==b.selector&&alternate_flag==b.alternate_flag&&reset==b.reset;
}
bool Row::operator==(const Row& b) const noexcept {
    return address==b.address&&vtable==b.vtable&&handle==b.handle&&marker==b.marker&&slot==b.slot&&tag==b.tag&&sentinel==b.sentinel;
}
bool Snapshot::operator==(const Snapshot& b) const noexcept {return roots==b.roots&&array==b.array&&rows==b.rows;}
Result resolve(ReadPort& port,std::uint64_t module,const std::vector<std::string_view>& names) noexcept {
    Result out{};Budget budget(port);
    try {
        demand(pointer(module)&&module%65536==0&&ImageSize<Limit-module,Status::InvalidRequest,"image base bounds");
        demand(!names.empty()&&names.size()<=16,Status::InvalidRequest,"bounded TAG list");
        std::vector<Tag> requested;std::set<std::array<char,3>> unique;
        for(auto name:names) {Tag tag{};demand(parse_tag(name,tag)&&unique.insert(tag.bytes).second,Status::InvalidRequest,"unique ASCII TAG requests");requested.push_back(tag);}
        pins(budget,module);auto a=pass(budget,module);auto b=pass(budget,module);pins(budget,module);
        demand(a==b,Status::Changed,"whole typed passes differ");
        std::vector<Binding> bindings;
        for(const auto& tag:requested) {
            const auto found=std::find_if(a.rows.begin(),a.rows.end(),[&](const Row& row){return row.address&&!row.sentinel&&row.tag==tag;});
            demand(found!=a.rows.end(),Status::MissingTag,"requested TAG unavailable; no gameplay absence claim");
            // Passive selectors 1..7 are retained and compared, never authorized.
            demand(((found->handle>>48)&255)==0,Status::UnsupportedLayout,"requested TAG requires ordinary selector0");
            bindings.push_back(Binding{tag,found->slot,found->address,found->handle});
        }
        out.snapshot=std::move(a);out.bindings=std::move(bindings);out.stable_two_pass=true;
        out.status=Status::Resolved;out.reason="equal bounded typed observations";
    } catch(const Failure& error) {out.status=error.status;out.reason=error.reason;}
      catch(...) {out.status=Status::UnavailableRead;out.reason="exception; no inferred absence";}
    out.read_calls=budget.calls;out.read_bytes=budget.bytes;return out;
}
}
