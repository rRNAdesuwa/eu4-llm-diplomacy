#include "cancel_reader.h"
#include <algorithm>
#include <cstring>
#include <set>
#include <string_view>
#include <utility>

namespace cancel1375 {
namespace {
constexpr std::uint64_t Limit=std::uint64_t{1}<<47;
bool pointer(std::uint64_t p,bool null=false) {return (null&&p==0)||(p>=0x10000&&p<Limit&&p%8==0);}
void need(bool ok) {if(!ok)throw false;}
struct Budget {std::uint64_t bytes{};std::size_t calls{};};
class Reader {
    v21pair::SyntheticReadPort& source;
    std::vector<Read>& trace;
    Budget& budget;
public:
    Reader(v21pair::SyntheticReadPort& s,std::vector<Read>& t,Budget& b):source(s),trace(t),budget(b){}
    void read(std::uint64_t a,void* out,std::size_t n) {
        need(a>=0x10000&&a<Limit&&n>0&&n<=32768&&n<=Limit-a&&budget.calls<20000&&budget.bytes+n<=512*1024);
        Read row{};row.address=a;row.bytes.resize(n);budget.bytes+=n;++budget.calls;
        need(source.read(a,row.bytes.data(),n));std::memcpy(out,row.bytes.data(),n);trace.push_back(std::move(row));
    }
    template<class T>T at(std::uint64_t object,std::uint64_t offset=0) {
        need(pointer(object)&&offset<Limit-object&&sizeof(T)<=Limit-object-offset);
        T value{};read(object+offset,&value,sizeof(value));return value;
    }
    std::vector<std::uint8_t> block(std::uint64_t address,std::size_t size) {
        std::vector<std::uint8_t> data(size);
        for(std::size_t i=0;i<size;) {const auto n=std::min<std::size_t>(size-i,32768);read(address+i,data.data()+i,n);i+=n;}return data;
    }
};
std::uint32_t dword(const std::uint8_t* p) {std::uint32_t value{};for(unsigned i=0;i<4;++i)value|=std::uint32_t{p[i]}<<(8*i);return value;}
std::uint64_t qword(const std::uint8_t* p) {std::uint64_t value{};for(unsigned i=0;i<8;++i)value|=std::uint64_t{p[i]}<<(8*i);return value;}
void typed(Reader& r,std::uint64_t object,std::uint64_t vt,std::uint32_t marker=0x165) {
    need(pointer(object)&&r.at<std::uint64_t>(object)==vt&&r.at<std::uint32_t>(object,8)==marker);
}
// Same ordinary-handle research profile as the sealed TAG resolver. This is
// a shape restriction, never a substitute for current country-object lookup.
bool handle_shape(v21pair::FullHandle h,std::uint32_t count) {
    const auto slot=(h.value>>32)&65535;
    if(!v21pair::valid(h)||slot==0||slot>=count||((h.value>>48)&255)!=0||((h.value>>24)&255)!=0)return false;
    for(unsigned i=0;i<3;++i) {const auto c=(h.value>>(i*8))&255;if(!((c>='A'&&c<='Z')||(c>='0'&&c<='9')))return false;}
    return true;
}
void roots(Reader& r,std::uint64_t m,const v21pair::PairStamp& s) {
    need(v21pair::valid(s)&&s.date<=0x7fffffff&&pointer(m)&&m%65536==0&&0x25e0000<Limit-m);
    need(handle_shape(s.actor,s.count)&&handle_shape(s.target,s.count));
    need(r.at<std::uint64_t>(m,0x233d8d0)==s.database&&r.at<std::uint64_t>(m,0x233fe78)==s.game);
    need(r.at<std::uint64_t>(s.database,0x118)==s.array);
    const auto cap=r.at<std::int32_t>(s.database,0x120),count=r.at<std::int32_t>(s.database,0x124);
    need(cap>=1&&cap<=4096&&count>=1&&count<=cap&&static_cast<std::uint32_t>(count)==s.count);
    for(const auto& pair:std::array<std::pair<std::uint64_t,v21pair::FullHandle>,2>{{{s.actor_object,s.actor},{s.target_object,s.target}}}) {
        need(r.at<std::uint64_t>(s.array,((pair.second.value>>32)&65535)*8)==pair.first);
        typed(r,pair.first,m+0x1c574a0);need(r.at<std::uint64_t>(pair.first,0x20)==pair.second.value);
    }
    need(r.at<std::uint32_t>(s.game,0x1dd0)==s.date&&r.at<std::uint64_t>(s.game,0x1e60)==s.current_player.value);
    need(r.at<std::uint8_t>(s.game,0x1e66)==0&&r.at<std::uint8_t>(s.game,0x7485)==0&&r.at<std::uint64_t>(s.game,0x74c8)==0);
}
std::uint64_t index(Reader& r,const v21pair::PairStamp& s,std::uint64_t owner,v21pair::FullHandle owner_h,
    v21pair::FullHandle other,std::uint32_t offset) {
    const auto records=r.at<std::uint64_t>(owner,0x1510);need(pointer(records));
    const auto slot=static_cast<std::uint32_t>((other.value>>32)&65535);
    const auto record=records+std::uint64_t{slot}*0x48;
    const auto root=r.at<std::uint64_t>(record);need(pointer(root));
    need(r.at<std::uint64_t>(record,8)==owner_h.value&&r.at<std::uint64_t>(record,0x10)==other.value);
    const auto array=r.at<std::uint64_t>(root,offset);
    const auto cap=r.at<std::int32_t>(root,offset+8),count=r.at<std::int32_t>(root,offset+12);
    need(cap>=0&&cap<=4096&&count>=0&&count<=cap&&pointer(array,true)&&(cap==0?array==0:array!=0));
    const auto data=r.block(array,static_cast<std::size_t>(count)*16);
    std::set<std::uint32_t> slots;std::set<std::uint64_t> objects;std::uint64_t selected{};
    for(std::int32_t i=0;i<count;++i) {
        const auto* row=data.data()+static_cast<std::size_t>(i)*16;const auto id=dword(row);const auto object=qword(row+8);
        need(id<s.count&&slots.insert(id).second&&pointer(object)&&objects.insert(object).second);
        if(id==slot)selected=object;
    }
    // Header/current record reads are included in both exact full pass transcripts.
    need(r.at<std::uint64_t>(owner,0x1510)==records&&r.at<std::uint64_t>(record)==root&&r.at<std::uint64_t>(root,offset)==array);
    need(r.at<std::int32_t>(root,offset+8)==cap&&r.at<std::int32_t>(root,offset+12)==count);
    return selected;
}
bool name(Reader& r,std::uint64_t definition,std::string_view wanted) {
    need(pointer(definition));const auto string=definition+0x10;
    const auto length=r.at<std::uint64_t>(string,0x10),cap=r.at<std::uint64_t>(string,0x18);
    need(length>0&&length<=128&&length<=cap&&(cap>=16||length<16));
    const auto chars=cap<16?string:r.at<std::uint64_t>(string);need(pointer(chars));
    const auto data=r.block(chars,static_cast<std::size_t>(length)+1);
    need(data.back()==0&&std::find(data.begin(),data.end()-1,std::uint8_t{0})==data.end()-1);
    return length==wanted.size()&&std::equal(data.begin(),data.end()-1,wanted.begin());
}
void mission(Reader& r,std::uint64_t module,const v21pair::PairStamp& s,std::uint64_t selected,std::uint32_t token,bool curry) {
    const auto holder=r.at<std::uint64_t>(s.actor_object,0x1480),hend=r.at<std::uint64_t>(s.actor_object,0x1488),hcap=r.at<std::uint64_t>(s.actor_object,0x1490);
    need(pointer(holder)&&pointer(hend)&&pointer(hcap)&&holder<=hend&&hend<=hcap&&(hend-holder)%8==0&&(hcap-holder)%8==0&&(hend-holder)/8>=4&&(hcap-holder)/8<=16);
    const auto manager=r.at<std::uint64_t>(holder,0x18);typed(r,manager,module+0x1cac380);
    need(r.at<std::uint32_t>(manager,0x10)==0x2746&&r.at<std::uint8_t>(manager,0x14)==3&&r.at<std::uint64_t>(manager,0x16)==s.actor.value);
    const auto begin=r.at<std::uint64_t>(manager,0x20),end=r.at<std::uint64_t>(manager,0x28),cap=r.at<std::uint64_t>(manager,0x30);
    need(pointer(begin,true)&&pointer(end,true)&&pointer(cap,true)&&(begin==0?(end==0&&cap==0):(end>=begin&&cap>=end&&(end-begin)%8==0&&(cap-begin)%8==0&&(cap-begin)/8<=256)));
    const auto data=r.block(begin,static_cast<std::size_t>(end-begin));std::set<std::uint64_t> entries,missions;std::set<std::int32_t> ids;unsigned matches{};
    for(std::size_t i=0;i<data.size();i+=8) {
        const auto entry=qword(data.data()+i);need(entries.insert(entry).second);typed(r,entry,module+0x1cac2f0);
        need(r.at<std::uint8_t>(entry,0x40)==3);const auto status=r.at<std::uint8_t>(entry,0x18);need(status<=2);
        const auto envoy=r.at<std::int32_t>(entry,0x44);need(envoy>=0&&ids.insert(envoy).second);
        const auto mp=r.at<std::uint64_t>(entry,0x10);need(pointer(mp,true));
        if(!mp) {need(status==0);continue;}
        need(status==1||status==2);
        need(missions.insert(mp).second);typed(r,mp,module+0x1c4b2b8,0x182);
        need(r.at<std::uint64_t>(mp,0x48)==entry&&r.at<std::int32_t>(mp,0x50)==envoy&&r.at<std::uint64_t>(mp,0x80)==s.actor.value);
        const auto target=r.at<std::uint64_t>(mp,0x88);const auto action=r.at<std::uint32_t>(mp,0xa8);
        need(handle_shape(v21pair::FullHandle{target},s.count)&&action<=65535);
        if(((target>>32)&65535)==((s.target.value>>32)&65535))need(target==s.target.value);
        if(target==s.target.value&&action==token) {
            need(mp==selected&&(!curry||status==2)&&(status==1||status==2)&&++matches==1);
        } else need(mp!=selected);
    }
    need(matches==1&&r.at<std::uint64_t>(s.actor_object,0x1480)==holder&&r.at<std::uint64_t>(holder,0x18)==manager);
    need(r.at<std::uint64_t>(s.actor_object,0x1488)==hend&&r.at<std::uint64_t>(s.actor_object,0x1490)==hcap);
    need(r.at<std::uint64_t>(manager,0x20)==begin&&r.at<std::uint64_t>(manager,0x28)==end&&r.at<std::uint64_t>(manager,0x30)==cap);
}
}
static bool once_impl(v21pair::SyntheticReadPort& source,std::uint64_t module,v21pair::Family family,const v21pair::PairStamp& s,Snapshot& out,Budget& budget) noexcept {
    try {
        if(family==v21pair::Family::SpyNetwork||static_cast<unsigned>(family)>static_cast<unsigned>(v21pair::Family::Curry))return false;
        Snapshot result{};Reader r(source,result.reads,budget);roots(r,module,s);
        std::uint32_t aoff{},boff{},vt{};
        switch(family) {
        case v21pair::Family::Vassal:aoff=boff=0x128;vt=0x1c81758;break;
        case v21pair::Family::Marriage:aoff=boff=0x68;vt=0x1c80be0;break;
        case v21pair::Family::Improve:aoff=0x1d0;boff=0x1e8;vt=0x1c81658;break;
        case v21pair::Family::Guarantee:aoff=boff=0x1a0;vt=0x1c817d8;break;
        case v21pair::Family::Curry:aoff=0x158;vt=0x1c7b178;break;
        case v21pair::Family::SpyNetwork:return false;
        }
        const auto object=index(r,s,s.actor_object,s.actor,s.target,aoff);need(object!=0);
        if(family!=v21pair::Family::Curry)need(index(r,s,s.target_object,s.target,s.actor,boff)==object);
        typed(r,object,module+vt);need(r.at<std::uint8_t>(object,0x28)==0);
        const auto actor=r.at<std::uint64_t>(object,0x10),target=r.at<std::uint64_t>(object,0x18);
        need((actor==s.actor.value&&target==s.target.value)||(family==v21pair::Family::Marriage&&actor==s.target.value&&target==s.actor.value));
        const auto started=r.at<std::int32_t>(object,0x20);need(started>0&&static_cast<std::uint32_t>(started)<=s.date);
        auto& o=result.selected;o.family=family;o.active=true;o.known_type=true;o.outgoing=true;o.reciprocal=family!=v21pair::Family::Curry;
        o.actor=s.actor;o.target=s.target;o.object=object;o.revision=static_cast<std::uint32_t>(started);
        if(family==v21pair::Family::Vassal) {
            o.actor_overlord.value=r.at<std::uint64_t>(s.actor_object,0x18f0);o.target_overlord.value=r.at<std::uint64_t>(s.target_object,0x18f0);
            need(o.target_overlord==s.actor&&!(o.actor_overlord==s.target));
            const auto registry=r.at<std::uint64_t>(module,0x233ffd8);need(pointer(registry));
            const auto definition=r.at<std::uint64_t>(object,0x40);need(pointer(definition));
            const auto vassal=r.at<std::uint64_t>(registry,0x58),client=r.at<std::uint64_t>(registry,0x60);need(pointer(vassal)&&pointer(client)&&vassal!=client);
            if(definition==vassal&&name(r,definition,"vassal"))o.dependency=v21pair::Dependency::Vassal;
            else if(definition==client&&name(r,definition,"client_vassal"))o.dependency=v21pair::Dependency::ClientVassal;
            else return false;
            need(r.at<std::uint64_t>(module,0x233ffd8)==registry&&r.at<std::uint64_t>(registry,0x58)==vassal&&r.at<std::uint64_t>(registry,0x60)==client);
        }
        if(family==v21pair::Family::Improve||family==v21pair::Family::Curry) {
            o.mission=r.at<std::uint64_t>(object,0x30);need(pointer(o.mission));
            mission(r,module,s,o.mission,family==v21pair::Family::Curry?0x3acc:0x2ddb,family==v21pair::Family::Curry);o.mission_linked=true;
        }
        roots(r,module,s);out=std::move(result);return true;
    } catch(...) {return false;}
}
bool once(v21pair::SyntheticReadPort& source,std::uint64_t module,v21pair::Family family,const v21pair::PairStamp& s,Snapshot& out) noexcept {
    Budget budget{};return once_impl(source,module,family,s,out,budget);
}
bool two_pass(v21pair::SyntheticReadPort& r,std::uint64_t m,v21pair::Family f,const v21pair::PairStamp& s,Snapshot& out) noexcept {
    Budget budget{};Snapshot a{},b{};if(!once_impl(r,m,f,s,a,budget)||!once_impl(r,m,f,s,b,budget)||!(a==b))return false;out=std::move(b);return true;
}
bool recheck(v21pair::SyntheticReadPort& r,std::uint64_t m,v21pair::Family f,const v21pair::PairStamp& s,const Snapshot& old) noexcept {
    Snapshot now{};return once(r,m,f,s,now)&&now==old;
}
}
