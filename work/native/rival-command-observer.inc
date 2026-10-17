// Passive observation of direct Rival country-command objects.
//
// Rival commands are not the Alliance generic wrapper.  In particular,
// command+0x50 is the actor country handle, command+0x58 is the target handle,
// and Replace command+0x60 is the old-rival handle.  This include therefore
// owns a separate shape, generation registry, event ring, and set of vtable
// hooks.  It never interprets command+0x50 as a wrapper/action pointer and
// never authorizes, submits, or mutates a command.

enum RivalCommandKind : unsigned char {
    rival_command_unknown=0,
    rival_command_set=1,
    rival_command_replace=2,
    rival_command_remove=3
};

struct RivalCommandObjectRef {
    uintptr_t address=0;
    uint64_t generation=0;
};

struct RivalCommandShape {
    uintptr_t address=0;
    uint64_t generation=0;
    uintptr_t vtable=0;
    RivalCommandKind kind=rival_command_unknown;
    int32_t discriminator=0;
    unsigned char raw10=0;
    int32_t raw38=0;
    int32_t raw3c=0;
    uint16_t raw40=0;
    uint32_t raw44=0;
    uint16_t origin48=0;
    unsigned char flags4a=0;
    unsigned char raw4b=0;
    unsigned char reserved4b=0;
    uint32_t sequence4c=0;
    uint64_t actor50=0;
    uint64_t target58=0;
    uint64_t old_rival60=0;
    // Semantic aliases for execution consumers.  The offset-suffixed fields
    // remain the authoritative layout names above.
    uint64_t actor=0;
    uint64_t target=0;
    uint64_t old_rival=0;
    bool vtable_readable=false;
    bool header_readable=false;
    bool handles_readable=false;
    bool old_rival_readable=false;
    bool readable=false;
    bool matched=false;
    // Structural identity only: this means a known Rival vptr and the
    // command discriminator were observed.  It does not resolve a country
    // handle and is therefore separate from any authority-layer meaning.
    bool canonical=false;
};

enum RivalCommandEventKind : unsigned char {
    rival_command_serialization_event=1,
    rival_command_load_event=2,
    rival_command_clone_event=3,
    rival_command_destruction_event=4
};

struct RivalCommandEvent {
    uint64_t callback_sequence=0;
    DWORD thread=0;
    RivalCommandEventKind kind=rival_command_serialization_event;
    uintptr_t caller_return=0;
    uintptr_t native_return=0;
    uintptr_t native_result=0;
    uintptr_t transport=0;
    uintptr_t outgoing=0;
    uintptr_t peer=0;
    uintptr_t receiver=0;
    bool native_return_matches=false;
    bool receiver_readable=false;
    bool peer_readable=false;
    RivalCommandObjectRef source_ref{};
    RivalCommandObjectRef target_ref{};
    RivalCommandShape source{};
    RivalCommandShape target{};
    unsigned native_flags=0;
};

// These callbacks are deliberately declared before alliance-execution.inc.
// The root execution layer supplies the definitions after this include.  They
// receive copied snapshots and never receive an object lifetime contract.
static void rival_command_observer_on_serialization(const RivalCommandEvent& event);
static void rival_command_observer_on_load(const RivalCommandEvent& event);
static void rival_command_observer_on_clone(const RivalCommandEvent& event);
static void rival_command_observer_on_destruction(const RivalCommandEvent& event);

static const uintptr_t rival_command_set_vtable_rva=0x1c55138;
static const uintptr_t rival_command_replace_vtable_rva=0x1c54b10;
static const uintptr_t rival_command_remove_vtable_rva=0x1c54a68;
static const uintptr_t rival_command_set_serializer_rva=0x2ab3b0;
static const uintptr_t rival_command_replace_serializer_rva=0x2ac820;
static const uintptr_t rival_command_remove_serializer_rva=0x2ab3b0;
static const uintptr_t rival_command_shared_load_rva=0x17067e0;
static const uintptr_t rival_command_set_clone_rva=0x2ab6f0;
static const uintptr_t rival_command_replace_clone_rva=0x2ac8f0;
static const uintptr_t rival_command_remove_clone_rva=0x2ad370;
static const uintptr_t rival_command_set_destructor_rva=0x098940;
static const uintptr_t rival_command_replace_destructor_rva=0x099880;
static const uintptr_t rival_command_remove_destructor_rva=0x098940;
static const uintptr_t rival_command_native_load_return_rva=0x15808f2;
static const uintptr_t rival_command_native_clone_return_rva=0x15801e2;

static const unsigned rival_command_event_capacity=128;
static const unsigned rival_command_registry_capacity=256;

using RivalCommandSerializerMethod=void (*)(void*,void*);
using RivalCommandLoadMethod=void (*)(void*,void*);
using RivalCommandCloneMethod=void* (*)(void*,void*);
using RivalCommandDestructorMethod=void* (*)(void*,unsigned);

extern "C" void bridge_rival_command_load_stub();
extern "C" void bridge_rival_command_clone_stub();
extern "C" {
    void* bridge_rival_command_load_original=nullptr;
    void* bridge_rival_command_clone_set_original=nullptr;
    void* bridge_rival_command_clone_replace_original=nullptr;
    void* bridge_rival_command_clone_remove_original=nullptr;
}

static RivalCommandSerializerMethod rival_command_serializer_shared_original=nullptr;
static RivalCommandSerializerMethod rival_command_serializer_replace_original=nullptr;
static RivalCommandDestructorMethod rival_command_destructor_shared_original=nullptr;
static RivalCommandDestructorMethod rival_command_destructor_replace_original=nullptr;

struct RivalCommandRegistryEntry {
    uintptr_t address=0;
    uint64_t generation=0;
    RivalCommandKind kind=rival_command_unknown;
    bool live=false;
};

struct RivalCommandTransportContext {
    bool active=false;
    uintptr_t transport=0;
    uintptr_t outgoing=0;
    RivalCommandObjectRef outgoing_ref{};
    RivalCommandShape outgoing_shape{};
};

static SRWLOCK rival_command_registry_lock=SRWLOCK_INIT;
static RivalCommandRegistryEntry rival_command_registry[rival_command_registry_capacity]{};
static uint64_t rival_command_generation=0;
static SRWLOCK rival_command_event_lock=SRWLOCK_INIT;
static RivalCommandEvent rival_command_events[rival_command_event_capacity]{};
static unsigned rival_command_event_head=0;
static unsigned rival_command_event_size=0;
static volatile LONG rival_command_event_dropped=0;
static volatile LONG64 rival_command_callback_sequence=0;
static volatile LONG rival_command_observer_install_state=0;
static bool rival_command_observer_rollback_incomplete=false;
static thread_local RivalCommandTransportContext rival_command_transport_context{};

static RivalCommandKind rival_command_kind_from_vtable(uintptr_t vtable) {
    if (vtable==base+rival_command_set_vtable_rva) return rival_command_set;
    if (vtable==base+rival_command_replace_vtable_rva) return rival_command_replace;
    if (vtable==base+rival_command_remove_vtable_rva) return rival_command_remove;
    return rival_command_unknown;
}

static const char* rival_command_kind_name(RivalCommandKind kind) {
    switch (kind) {
    case rival_command_set: return "set_rival";
    case rival_command_replace: return "replace_rival";
    case rival_command_remove: return "remove_rival";
    default: return "unknown";
    }
}

static RivalCommandShape rival_command_capture(void* object) {
    RivalCommandShape shape{};
    shape.address=reinterpret_cast<uintptr_t>(object);
    if (!object || shape.address<0x10000) return shape;
    shape.vtable_readable=read(shape.address,shape.vtable);
    if (!shape.vtable_readable) return shape;
    shape.kind=rival_command_kind_from_vtable(shape.vtable);
    bool common=read(shape.address+0x08,shape.discriminator)
        && read(shape.address+0x10,shape.raw10)
        && read(shape.address+0x38,shape.raw38)
        && read(shape.address+0x3c,shape.raw3c)
        && read(shape.address+0x40,shape.raw40)
        && read(shape.address+0x44,shape.raw44)
        && read(shape.address+0x48,shape.origin48)
        && read(shape.address+0x4a,shape.flags4a)
        && read(shape.address+0x4b,shape.raw4b)
        && read(shape.address+0x4c,shape.sequence4c);
    shape.header_readable=common;
    shape.handles_readable=read(shape.address+0x50,shape.actor50)
        && read(shape.address+0x58,shape.target58);
    if (shape.kind==rival_command_replace)
        shape.old_rival_readable=read(shape.address+0x60,shape.old_rival60);
    else
        shape.old_rival_readable=true;
    shape.readable=shape.header_readable && shape.handles_readable
        && shape.old_rival_readable;
    shape.matched=shape.readable && shape.kind!=rival_command_unknown
        && shape.discriminator==0x165;
    shape.reserved4b=shape.raw4b;
    shape.actor=shape.actor50;
    shape.target=shape.target58;
    shape.old_rival=shape.old_rival60;
    shape.canonical=shape.matched;
    // Handles are recorded as opaque 64-bit values.  In particular, this
    // capture never treats actor50/target58/old_rival60 as pointers.
    return shape;
}

static RivalCommandObjectRef rival_command_registry_ensure(uintptr_t address,
    RivalCommandKind kind,bool reissue) {
    RivalCommandObjectRef result{};
    if (address<0x10000 || kind==rival_command_unknown) return result;
    if (!TryAcquireSRWLockExclusive(&rival_command_registry_lock)) return result;
    int free_index=-1;
    int found=-1;
    for (unsigned index=0;index<rival_command_registry_capacity;++index) {
        const auto& item=rival_command_registry[index];
        if (item.live && item.address==address) { found=static_cast<int>(index); break; }
        if (!item.live && free_index<0) free_index=static_cast<int>(index);
    }
    int index=found;
    if (index<0) index=free_index;
    if (index<0) {
        ReleaseSRWLockExclusive(&rival_command_registry_lock);
        InterlockedIncrement(&rival_command_event_dropped);
        return result;
    }
    auto& item=rival_command_registry[static_cast<unsigned>(index)];
    if (found>=0 && item.kind==kind && !reissue) {
        result=RivalCommandObjectRef{item.address,item.generation};
        ReleaseSRWLockExclusive(&rival_command_registry_lock);
        return result;
    }
    item.address=address;
    item.kind=kind;
    item.generation=++rival_command_generation;
    item.live=true;
    result=RivalCommandObjectRef{item.address,item.generation};
    ReleaseSRWLockExclusive(&rival_command_registry_lock);
    return result;
}

static RivalCommandObjectRef rival_command_registry_lookup(uintptr_t address,
    RivalCommandKind kind) {
    RivalCommandObjectRef result{};
    if (address<0x10000 || kind==rival_command_unknown) return result;
    if (!TryAcquireSRWLockShared(&rival_command_registry_lock)) return result;
    for (const auto& item:rival_command_registry) {
        if (item.live && item.address==address && item.kind==kind) {
            result=RivalCommandObjectRef{item.address,item.generation};
            break;
        }
    }
    ReleaseSRWLockShared(&rival_command_registry_lock);
    return result;
}

static void rival_command_registry_release(const RivalCommandObjectRef& ref) {
    if (!ref.address || !ref.generation) return;
    if (!TryAcquireSRWLockExclusive(&rival_command_registry_lock)) return;
    for (auto& item:rival_command_registry) {
        if (item.live && item.address==ref.address && item.generation==ref.generation) {
            item.live=false;
            break;
        }
    }
    ReleaseSRWLockExclusive(&rival_command_registry_lock);
}

static RivalCommandObjectRef rival_command_event_ref(
    const RivalCommandShape& shape) {
    if (!shape.matched) return RivalCommandObjectRef{};
    RivalCommandObjectRef ref=rival_command_registry_lookup(
        shape.address,shape.kind);
    if (!ref.address)
        ref=rival_command_registry_ensure(shape.address,shape.kind,false);
    return ref;
}

static void rival_command_event_enqueue(const RivalCommandEvent& event) {
    if (!TryAcquireSRWLockExclusive(&rival_command_event_lock)) {
        InterlockedIncrement(&rival_command_event_dropped);
        return;
    }
    if (rival_command_event_size<rival_command_event_capacity) {
        rival_command_events[(rival_command_event_head+rival_command_event_size)
            %rival_command_event_capacity]=event;
        ++rival_command_event_size;
    } else InterlockedIncrement(&rival_command_event_dropped);
    ReleaseSRWLockExclusive(&rival_command_event_lock);
}

static void rival_command_event_common(RivalCommandEvent& event,
    RivalCommandEventKind kind,const RivalCommandShape& source,
    uintptr_t caller_return=0) {
    event.callback_sequence=static_cast<uint64_t>(
        InterlockedIncrement64(&rival_command_callback_sequence));
    event.thread=GetCurrentThreadId();
    event.kind=kind;
    event.caller_return=caller_return;
    event.source=source;
    event.source_ref=rival_command_event_ref(source);
    event.source.generation=event.source_ref.generation;
    event.transport=rival_command_transport_context.transport;
    event.outgoing=rival_command_transport_context.outgoing;
}

static void rival_command_dispatch_event(const RivalCommandEvent& event) {
    rival_command_event_enqueue(event);
    switch (event.kind) {
    case rival_command_serialization_event:
        rival_command_observer_on_serialization(event); break;
    case rival_command_load_event:
        rival_command_observer_on_load(event); break;
    case rival_command_clone_event:
        rival_command_observer_on_clone(event); break;
    case rival_command_destruction_event:
        rival_command_observer_on_destruction(event); break;
    default: break;
    }
}

static RivalCommandSerializerMethod rival_command_serializer_for(
    RivalCommandKind kind) {
    switch (kind) {
    case rival_command_set:
    case rival_command_remove:
        return rival_command_serializer_shared_original;
    case rival_command_replace:
        return rival_command_serializer_replace_original;
    default:
        return nullptr;
    }
}

static RivalCommandDestructorMethod rival_command_destructor_for(
    RivalCommandKind kind) {
    switch (kind) {
    case rival_command_set:
    case rival_command_remove:
        return rival_command_destructor_shared_original;
    case rival_command_replace:
        return rival_command_destructor_replace_original;
    default:
        return nullptr;
    }
}

static RivalCommandCloneMethod rival_command_clone_for(RivalCommandKind kind) {
    switch (kind) {
    case rival_command_set:
        return reinterpret_cast<RivalCommandCloneMethod>(bridge_rival_command_clone_set_original);
    case rival_command_replace:
        return reinterpret_cast<RivalCommandCloneMethod>(bridge_rival_command_clone_replace_original);
    case rival_command_remove:
        return reinterpret_cast<RivalCommandCloneMethod>(bridge_rival_command_clone_remove_original);
    default: return nullptr;
    }
}

static void rival_command_serializer_entry(void* command,void* writer) {
    const uintptr_t caller_return=reinterpret_cast<uintptr_t>(
        __builtin_return_address(0));
    RivalCommandShape before=rival_command_capture(command);
    RivalCommandSerializerMethod original=rival_command_serializer_for(before.kind);
    if (!original) return;
    original(command,writer);
    if (!before.matched) return;
    RivalCommandEvent event{};
    rival_command_event_common(event,rival_command_serialization_event,before,
        caller_return);
    rival_command_dispatch_event(event);
}

extern "C" void bridge_rival_command_load_observe(void* command,void* context,
    uintptr_t native_return,void* peer) {
    RivalCommandShape before=rival_command_capture(command);
    RivalCommandLoadMethod original=reinterpret_cast<RivalCommandLoadMethod>(
        bridge_rival_command_load_original);
    if (!original) return;
    original(command,context);
    RivalCommandShape after=rival_command_capture(command);
    if (!after.matched && !before.matched) return;
    const RivalCommandShape& source=after.matched?after:before;
    RivalCommandEvent event{};
    rival_command_event_common(event,rival_command_load_event,source,native_return);
    event.native_return=native_return;
    event.native_return_matches=native_return==base+rival_command_native_load_return_rva;
    event.peer=reinterpret_cast<uintptr_t>(peer);
    event.peer_readable=peer!=nullptr && reinterpret_cast<uintptr_t>(peer)>=0x10000;
    event.target=after;
    event.target_ref=rival_command_event_ref(after);
    event.target.generation=event.target_ref.generation;
    rival_command_dispatch_event(event);
}

extern "C" void* bridge_rival_command_clone_observe(void* command,void* context,
    uintptr_t native_return,void* receiver) {
    RivalCommandShape before=rival_command_capture(command);
    RivalCommandCloneMethod original=rival_command_clone_for(before.kind);
    if (!original) return nullptr;
    RivalCommandObjectRef source_ref=rival_command_event_ref(before);
    void* result=original(command,context);
    RivalCommandShape after=rival_command_capture(result);
    if (!after.matched && !before.matched) return result;
    RivalCommandEvent event{};
    rival_command_event_common(event,rival_command_clone_event,before,native_return);
    event.source_ref=source_ref;
    event.native_return=native_return;
    event.native_return_matches=native_return==base+rival_command_native_clone_return_rva;
    event.receiver=reinterpret_cast<uintptr_t>(receiver);
    event.receiver_readable=receiver!=nullptr && reinterpret_cast<uintptr_t>(receiver)>=0x10000;
    event.native_result=reinterpret_cast<uintptr_t>(result);
    event.target=after;
    event.target_ref=after.matched
        ? rival_command_registry_ensure(after.address,after.kind,true)
        : RivalCommandObjectRef{};
    event.target.generation=event.target_ref.generation;
    rival_command_dispatch_event(event);
    return result;
}

static void* rival_command_destructor_entry(void* command,unsigned flags) {
    const uintptr_t caller_return=reinterpret_cast<uintptr_t>(
        __builtin_return_address(0));
    RivalCommandShape before=rival_command_capture(command);
    RivalCommandDestructorMethod original=rival_command_destructor_for(before.kind);
    if (!original) return nullptr;
    RivalCommandObjectRef ref=rival_command_event_ref(before);
    void* result=original(command,flags);
    if (before.matched) {
        RivalCommandEvent event{};
        rival_command_event_common(event,rival_command_destruction_event,before,
            caller_return);
        event.source_ref=ref;
        event.native_flags=flags;
        event.native_result=reinterpret_cast<uintptr_t>(result);
        rival_command_dispatch_event(event);
    }
    rival_command_registry_release(ref);
    return result;
}

extern "C" void rival_command_transport_begin(void* transport,void* outgoing) {
    rival_command_transport_context=RivalCommandTransportContext{};
    rival_command_transport_context.transport=reinterpret_cast<uintptr_t>(transport);
    rival_command_transport_context.outgoing=reinterpret_cast<uintptr_t>(outgoing);
    rival_command_transport_context.outgoing_shape=rival_command_capture(outgoing);
    if (rival_command_transport_context.outgoing_shape.matched) {
        rival_command_transport_context.outgoing_ref=rival_command_registry_ensure(
            rival_command_transport_context.outgoing_shape.address,
            rival_command_transport_context.outgoing_shape.kind,false);
        rival_command_transport_context.outgoing_shape.generation=
            rival_command_transport_context.outgoing_ref.generation;
        rival_command_transport_context.active=true;
    }
}

extern "C" void rival_command_transport_end() {
    rival_command_transport_context=RivalCommandTransportContext{};
}

struct RivalCommandHookSlot {
    uintptr_t address_rva=0;
    uintptr_t expected_rva=0;
    void* replacement=nullptr;
    void* original=nullptr;
    bool installed=false;
};

static RivalCommandHookSlot rival_command_hook_slots[12]{};
static unsigned rival_command_hook_slot_count=0;

// Forward declaration is needed by the failure path in install().  The
// rollback routine is defined immediately below install so a failed partial
// publication can restore slots in reverse order.
extern "C" bool rival_command_observer_rollback();

static bool rival_command_publish_slot(RivalCommandHookSlot& slot) {
    void** address=reinterpret_cast<void**>(base+slot.address_rva);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(address),actual)
        || actual!=reinterpret_cast<void*>(base+slot.expected_rva)) return false;
    slot.original=actual;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(address,8,PAGE_READWRITE,&protection)) return false;
    void* prior=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(address),slot.replacement,actual);
    bool installed=prior==actual;
    bool restored=VirtualProtect(address,8,protection,&ignored)!=FALSE;
    if (!restored) {
        if (installed) InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(address),actual,slot.replacement);
        rival_command_observer_rollback_incomplete=true;
        return false;
    }
    slot.installed=installed;
    return installed;
}

static bool rival_command_restore_slot(RivalCommandHookSlot& slot) {
    if (!slot.installed) return true;
    void** address=reinterpret_cast<void**>(base+slot.address_rva);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(address),actual)) return false;
    if (actual==slot.original) { slot.installed=false; return true; }
    if (actual!=slot.replacement) return false;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(address,8,PAGE_READWRITE,&protection)) return false;
    void* prior=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(address),slot.original,slot.replacement);
    bool swapped=prior==slot.replacement || prior==slot.original;
    bool restored=VirtualProtect(address,8,protection,&ignored)!=FALSE;
    if (swapped && restored) slot.installed=false;
    return swapped && restored;
}

extern "C" bool rival_command_observer_install() {
    LONG state=InterlockedCompareExchange(&rival_command_observer_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;
    rival_command_observer_rollback_incomplete=false;
    rival_command_serializer_shared_original=reinterpret_cast<RivalCommandSerializerMethod>(base+rival_command_set_serializer_rva);
    rival_command_serializer_replace_original=reinterpret_cast<RivalCommandSerializerMethod>(base+rival_command_replace_serializer_rva);
    rival_command_destructor_shared_original=reinterpret_cast<RivalCommandDestructorMethod>(base+rival_command_set_destructor_rva);
    rival_command_destructor_replace_original=reinterpret_cast<RivalCommandDestructorMethod>(base+rival_command_replace_destructor_rva);
    bridge_rival_command_load_original=reinterpret_cast<void*>(base+rival_command_shared_load_rva);
    bridge_rival_command_clone_set_original=reinterpret_cast<void*>(base+rival_command_set_clone_rva);
    bridge_rival_command_clone_replace_original=reinterpret_cast<void*>(base+rival_command_replace_clone_rva);
    bridge_rival_command_clone_remove_original=reinterpret_cast<void*>(base+rival_command_remove_clone_rva);
    rival_command_hook_slot_count=0;
    const uintptr_t vtables[]={rival_command_set_vtable_rva,
        rival_command_replace_vtable_rva,rival_command_remove_vtable_rva};
    const uintptr_t serializers[]={rival_command_set_serializer_rva,
        rival_command_replace_serializer_rva,rival_command_remove_serializer_rva};
    const uintptr_t destructors[]={rival_command_set_destructor_rva,
        rival_command_replace_destructor_rva,rival_command_remove_destructor_rva};
    for (unsigned index=0;index<3;++index) {
        rival_command_hook_slots[rival_command_hook_slot_count++]={
            vtables[index]+0x10,serializers[index],
            reinterpret_cast<void*>(&rival_command_serializer_entry),nullptr,false};
        rival_command_hook_slots[rival_command_hook_slot_count++]={
            vtables[index]+0x18,rival_command_shared_load_rva,
            reinterpret_cast<void*>(&bridge_rival_command_load_stub),nullptr,false};
        rival_command_hook_slots[rival_command_hook_slot_count++]={
            vtables[index]+0x60,index==0?rival_command_set_clone_rva
                :index==1?rival_command_replace_clone_rva:rival_command_remove_clone_rva,
            reinterpret_cast<void*>(&bridge_rival_command_clone_stub),nullptr,false};
        rival_command_hook_slots[rival_command_hook_slot_count++]={
            vtables[index]+0x00,destructors[index],
            reinterpret_cast<void*>(&rival_command_destructor_entry),nullptr,false};
    }
    for (unsigned index=0;index<rival_command_hook_slot_count;++index) {
        if (!rival_command_publish_slot(rival_command_hook_slots[index])) {
            bool rolled=rival_command_observer_rollback();
            if (!rolled) InterlockedExchange(&rival_command_observer_install_state,-1);
            return false;
        }
    }
    InterlockedExchange(&rival_command_observer_install_state,2);
    return true;
}

extern "C" bool rival_command_observer_rollback() {
    bool complete=true;
    for (unsigned index=rival_command_hook_slot_count;index>0;--index)
        complete=rival_command_restore_slot(rival_command_hook_slots[index-1]) && complete;
    if (!complete) rival_command_observer_rollback_incomplete=true;
    else InterlockedExchange(&rival_command_observer_install_state,0);
    return complete;
}

static void rival_command_shape_json(char* output,size_t capacity,
    const RivalCommandShape& shape) {
    snprintf(output,capacity,
        "{\"addr\":\"0x%llx\",\"generation\":%llu,\"family\":\"%s\",\"matched\":%s,\"readable\":%s,\"canonical\":%s,\"vtable_rva\":\"0x%llx\",\"discriminator\":%d,\"raw10\":%u,\"raw38\":%d,\"raw3c\":%d,\"raw40\":%u,\"raw44\":%u,\"origin48\":%u,\"flags4a\":%u,\"raw4b\":%u,\"reserved4b\":%u,\"sequence4c\":%u,\"actor\":\"0x%llx\",\"target\":\"0x%llx\",\"old_rival\":\"0x%llx\",\"actor50\":\"0x%llx\",\"target58\":\"0x%llx\",\"old_rival60\":\"0x%llx\"}",
        static_cast<unsigned long long>(shape.address),
        static_cast<unsigned long long>(shape.generation),rival_command_kind_name(shape.kind),
        shape.matched?"true":"false",shape.readable?"true":"false",
        shape.canonical?"true":"false",
        shape.vtable>=base?static_cast<unsigned long long>(shape.vtable-base):0ull,
        shape.discriminator,static_cast<unsigned>(shape.raw10),shape.raw38,shape.raw3c,
        static_cast<unsigned>(shape.raw40),shape.raw44,static_cast<unsigned>(shape.origin48),
        static_cast<unsigned>(shape.flags4a),static_cast<unsigned>(shape.raw4b),
        static_cast<unsigned>(shape.reserved4b),shape.sequence4c,
        static_cast<unsigned long long>(shape.actor),static_cast<unsigned long long>(shape.target),
        static_cast<unsigned long long>(shape.old_rival),
        static_cast<unsigned long long>(shape.actor50),static_cast<unsigned long long>(shape.target58),
        static_cast<unsigned long long>(shape.old_rival60));
}

extern "C" void rival_command_observer_flush() {
    for (unsigned count=0;count<16;++count) {
        RivalCommandEvent event{};
        if (!TryAcquireSRWLockExclusive(&rival_command_event_lock)) break;
        if (!rival_command_event_size) {
            ReleaseSRWLockExclusive(&rival_command_event_lock); break;
        }
        event=rival_command_events[rival_command_event_head];
        rival_command_event_head=(rival_command_event_head+1)%rival_command_event_capacity;
        --rival_command_event_size;
        ReleaseSRWLockExclusive(&rival_command_event_lock);
        char source[900],target[900],message[2200];
        rival_command_shape_json(source,sizeof(source),event.source);
        rival_command_shape_json(target,sizeof(target),event.target);
        const char* name=event.kind==rival_command_serialization_event?"serialization":
            event.kind==rival_command_load_event?"load":
            event.kind==rival_command_clone_event?"clone":"destruction";
        snprintf(message,sizeof(message),
            "{\"event\":\"native_rival_command_%s\",\"sequence\":%llu,\"thread\":%lu,\"caller_return\":\"0x%llx\",\"native_return\":\"0x%llx\",\"native_return_matches\":%s,\"native_result\":\"0x%llx\",\"transport\":\"0x%llx\",\"outgoing\":\"0x%llx\",\"peer\":\"0x%llx\",\"receiver\":\"0x%llx\",\"source_generation\":%llu,\"target_generation\":%llu,\"source\":%s,\"target\":%s}\n",
            name,static_cast<unsigned long long>(event.callback_sequence),
            static_cast<unsigned long>(event.thread),static_cast<unsigned long long>(event.caller_return),
            static_cast<unsigned long long>(event.native_return),event.native_return_matches?"true":"false",
            static_cast<unsigned long long>(event.native_result),static_cast<unsigned long long>(event.transport),
            static_cast<unsigned long long>(event.outgoing),static_cast<unsigned long long>(event.peer),
            static_cast<unsigned long long>(event.receiver),static_cast<unsigned long long>(event.source_ref.generation),
            static_cast<unsigned long long>(event.target_ref.generation),source,target);
        line(message);
    }
    LONG dropped=InterlockedExchange(&rival_command_event_dropped,0);
    if (dropped) {
        char message[180];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_rival_command_observer_drop\",\"dropped\":%ld,\"complete\":false}\n",
            static_cast<long>(dropped));
        line(message);
    }
}
