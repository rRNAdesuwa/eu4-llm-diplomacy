// Regression of the independently reproduced heap ownership defect.
#define main retained_author_main
#include "test_native_pair_engine.cpp"
#undef main
#include <algorithm>
unsigned groups=0;
void group(const char* name,const std::function<void()>& f){f();++groups;std::cout<<"PASS "<<name<<'\n';}
void heap(Fake& f,Address owner,Address chars,Address length=0,Address cap=16) {
    f.set(owner+0x40,chars);f.set(owner+0x50,length);f.set(owner+0x58,cap);
}
void no_delete(Fake& f,NativePairEngineDraft& e,const std::function<void()>& operation) {
    const auto calls=f.native_entries;f.read_addresses.clear();
    rejects(operation,e,f);CHECK(f.native_entries==calls && f.deletes==0);
    CHECK(e.diagnostics().fault==Fault::Ownership);
}
int main(){try {
    group("known_original_command_clone_aliases_refuse_before_pointer_read",[]{
        for(unsigned alias=0;alias<3;++alias)for(unsigned operation=0;operation<3;++operation) {
            Fake f;NativePairEngineDraft e(f);const auto& p=profiles()[1];const auto x=wrapped(e,p);
            const Address chars=alias==0?f.last_original+0x48:alias==1?f.last_command+0x20:f.last_clone+0x40;
            CHECK(f.get<std::uint8_t>(chars)==0);heap(f,f.last_original,chars);
            no_delete(f,e,[&]{if(operation==0){ActionView view{};e.action_view(x.a,view);}
                else if(operation==1)e.destroy_action(p,x.a);else e.command_gate(x.c);});
            CHECK(e.diagnostics().quarantined==3);
            CHECK(std::find(f.read_addresses.begin(),f.read_addresses.end(),f.last_original+0x40)==f.read_addresses.end());
        }
    });
    group("whole_marriage_path_quarantines_heap_alias",[]{
        Fake f;NativePairEngineDraft e(f);Guard g;
        f.after=[](Call c,Fake& q){if(c==Call::Full88)heap(q,q.last_original,q.last_original+0x48);};
        Request r{};r.action=Action::Marriage;r.actor.bytes={'F','R','A'};r.target.bytes={'E','N','G'};
        const auto result=preflight_no_send(r,g,e,100);
        CHECK(result.status==Status::Frozen && e.diagnostics().frozen && f.deletes==0 && f.native_entries==3);
        CHECK(e.diagnostics().live==1 && e.diagnostics().quarantined==1);
    });
    group("independent_rw_allocation_is_not_allocator_certificate",[]{
        for(Address cap:{16ULL,128ULL,0x800000000000ULL}) {
            Fake f;NativePairEngineDraft e(f);const auto& p=profiles()[1];const auto x=wrapped(e,p);
            const auto chars=f.allocate(129);heap(f,f.last_original,chars,0,cap);
            no_delete(f,e,[&]{e.destroy_action(p,x.a);});CHECK(f.memory.at(chars).live);
        }
    });
    group("unknown_unaligned_and_boundary_heap_pointers_never_dereferenced",[]{
        for(Address chars:{0ULL,0x10001ULL,0x800000000000ULL,0xffffffffffffffffULL}) {
            Fake f;NativePairEngineDraft e(f);const auto& p=profiles()[1];const auto x=wrapped(e,p);
            heap(f,f.last_original,chars);no_delete(f,e,[&]{e.destroy_action(p,x.a);});
        }
    });
    group("heap_clone_blocks_command_destructor",[]{
        Fake f;NativePairEngineDraft e(f);const auto x=wrapped(e,profiles()[1]);
        heap(f,f.last_clone,f.last_command+0x20);no_delete(f,e,[&]{e.destroy_command(x.c);});
        CHECK(e.diagnostics().quarantined==3);
    });
    group("factory_heap_default_is_quarantined",[]{
        Fake f;NativePairEngineDraft e(f);
        f.after=[](Call c,Fake& q){if(c==Call::Factory)heap(q,q.last_original,q.last_original+0x48);};
        rejects([&]{e.factory(profiles()[1]);},e,f);
        CHECK(f.native_entries==1 && f.deletes==0 && e.diagnostics().fault==Fault::Ownership);
    });
    group("valid_inline_original_and_empty_clone_cleanup",[]{
        Fake f;NativePairEngineDraft e(f);const auto& p=profiles()[1];const auto x=wrapped(e,p);ActionView v{};
        CHECK(e.action_view(x.a,v) && v.text.capacity==15 && v.text.length==2 && v.text.storage_valid);
        CHECK(e.action_view(x.k,v) && v.text.length==0 && v.text.capacity==15);
        CHECK(e.destroy_action(p,x.a) && e.destroy_command(x.c));CHECK(f.deletes==2 && !e.diagnostics().frozen);
    });
    group("inline_capacity_corruption_refuses",[]{
        for(Address cap:{0ULL,1ULL,14ULL}) {
            Fake f;NativePairEngineDraft e(f);const auto x=wrapped(e,profiles()[1]);f.set(f.last_original+0x58,cap);
            const auto entries=f.native_entries;rejects([&]{e.destroy_action(profiles()[1],x.a);},e,f);
            CHECK(f.native_entries==entries && f.deletes==0);
        }
    });
    CHECK(groups==8);std::cout<<"heap_groups="<<groups<<" checks="<<checks<<" fake_only=true native_calls=0\n";return 0;
}catch(const std::exception& e){std::cerr<<"HEAP FAIL "<<e.what()<<'\n';return 1;}
catch(...){std::cerr<<"HEAP unexpected fault\n";return 2;}}
