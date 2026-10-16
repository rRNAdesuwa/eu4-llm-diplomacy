#pragma once
#include "native_guard.h"
#include <cassert>
#include <cstring>
#include <functional>
#include <map>
#include <vector>
namespace fixture {
using namespace v21pair;using namespace v21port;
struct Fake final:Platform {
    struct Block {std::vector<unsigned char> bytes;bool live=true,priv=true,rw=true;};
    std::vector<Address> read_addresses;
    std::map<Address,Block> memory;Address next=0x100000,last_original{},last_command{},last_clone{};
    unsigned calls=0,deletes=0,reads=0,writes=0,read_after_free=0,native_entries=0;
    std::uint64_t now=1,expires=100,highwater=1;bool work_identity=true;
    std::function<void(Fake&)> ready_hook,read_hook,write_hook;
    bool authority=true,throw_ready=false,fail_read=false,fail_write=false,short_write=false,preview=true,gate=true;
    bool null_factory=false,null_wrapper=false,bad_slot=false,command_alias=false,clone_alias=false,clone_cmd_alias=false;
    bool fail_region=false,heap_string=false;Call fault_call=Call::Factory;bool fault=false,throw_call=false;
    std::int32_t native_envoy=0;
    std::function<void(Call,Fake&)> before,after;
    Address module()const noexcept override{return 0x140000000ULL;}
    bool ready()override {if(throw_ready)throw 7;if(ready_hook)ready_hook(*this);return authority;}
    bool final_gate(bool cleanup) {if(!work_identity || now<highwater)return false;highwater=now;return cleanup || now<expires;}
    auto locate(Address p,std::size_t n) {
        auto it=memory.upper_bound(p);if(it==memory.begin())return memory.end();--it;
        if(p-it->first>it->second.bytes.size() || n>it->second.bytes.size()-(p-it->first))return memory.end();return it;
    }
    bool region(Address p,Region& r)override {
        if(fail_region)return false;
        auto it=locate(p,1);if(it==memory.end())return false;
        r={it->first,it->second.bytes.size(),it->second.live,it->second.priv,it->second.rw};return true;
    }
    bool read(Address p,void* out,std::size_t n)override {
        ++reads;read_addresses.push_back(p);assert(n>0 && n<=64);auto it=locate(p,n);if(it==memory.end())return false;
        if(!it->second.live){++read_after_free;return false;}if(fail_read)return false;
        std::memcpy(out,it->second.bytes.data()+p-it->first,n);if(read_hook)read_hook(*this);return true;
    }
    bool write(Address p,const void* in,std::size_t n)override {
        ++writes;auto it=locate(p,n);if(it==memory.end() || !it->second.live || fail_write)return false;
        assert(n==1 || n==4 || n==8);assert(p-it->first>=0x10 && p-it->first+n<=0x40);
        if(write_hook)write_hook(*this);if(!final_gate(false))return false;
        if(!short_write)std::memcpy(it->second.bytes.data()+p-it->first,in,n);return true;
    }
    Address allocate(std::size_t n) {Address p=next;next+=0x1000;memory[p]={std::vector<unsigned char>(n,0)};return p;}
    template<class T>void set(Address p,T v) {auto it=locate(p,sizeof(v));assert(it!=memory.end());std::memcpy(it->second.bytes.data()+p-it->first,&v,sizeof(v));}
    template<class T>T get(Address p) {T v{};auto it=locate(p,sizeof(v));assert(it!=memory.end());std::memcpy(&v,it->second.bytes.data()+p-it->first,sizeof(v));return v;}
    Address action(const Profile& p) {
        const auto a=allocate(p.size);set(a,module()+p.vtable);set(a+8,std::uint32_t{0x165});
        for(unsigned off:{0x10U,0x18U,0x20U})set(a+off,Address{0x2d2d2d});
        set(a+0x28,std::uint32_t{0x29c77f8});set(a+0x2c,std::uint32_t{0x29c77f8});set(a+0x30,std::int32_t{-1});set(a+0x38,std::uint8_t{1});
        if(p.family==Family::Marriage)set(a+0x58,Address{15});return a;
    }
    Return invoke(Call kind,const Profile& p,Address a,bool mode)override {
        ++calls;if(before)before(kind,*this);
        if(!final_gate(kind==Call::ActionDestructor || kind==Call::CommandDestructor))return {};
        ++native_entries;
        if(throw_call && kind==fault_call)throw 5;
        if(fault && kind==fault_call)return {false,false,false,0,0xc0000005};
        Return r{};r.normal=true;
        switch(kind) {
        case Call::Factory:if(!null_factory)r.object=last_original=action(p);break;
        case Call::Setter:set(a+0x38,static_cast<std::uint8_t>(mode));if(p.family==Family::SpyNetwork && !mode)set(a+0x30,native_envoy);break;
        case Call::Full88:
            r.boolean=preview;
            if(p.family==Family::Marriage){const auto text=heap_string?allocate(129):a+0x40;set(text,std::uint8_t{'s'});set(text+1,std::uint8_t{'a'});set(text+2,std::uint8_t{0});
                if(heap_string)set(a+0x40,text);set(a+0x50,Address{2});set(a+0x58,Address{heap_string?128U:15U});}
            break;
        case Call::Wrapper:
            r.returned_same_slot=!bad_slot;if(null_wrapper)break;
            last_clone=action(p);
            // Synthetic engine emulates a native clone field-by-field. The adapter
            // never copies String32 storage or the original into a clone.
            for(unsigned off:{0x10U,0x18U,0x20U})set(last_clone+off,get<Address>(a+off));
            for(unsigned off:{0x28U,0x2cU,0x30U,0x34U,0x3cU})set(last_clone+off,get<std::uint32_t>(a+off));
            set(last_clone+0x38,get<std::uint8_t>(a+0x38));
            last_command=allocate(0x58);set(last_command,module()+0x1c814b0);set(last_command+8,std::uint32_t{0x165});
            set(last_command+0x30,Address{15});set(last_command+0x38,std::int32_t{-1});set(last_command+0x44,std::uint32_t{0x2934});set(last_command+0x48,Address{0xffff});
            set(last_command+0x50,clone_alias?a:clone_cmd_alias?last_command:last_clone);
            r.object=command_alias?a:last_command;break;
        case Call::Gate:r.boolean=gate;break;
        case Call::ActionDestructor:++deletes;memory.at(a).live=false;break;
        case Call::CommandDestructor:++deletes;memory.at(get<Address>(a+0x50)).live=false;memory.at(a).live=false;break;
        }
        if(after)after(kind,*this);return r;
    }
};
}
