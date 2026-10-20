// Passive observation of the native alliance transport and its wrapper load.
// The including translation unit supplies base, read, line, and the lifecycle
// and protocol shapes.  This include never authorizes an action or marks a
// queue receipt as verified.

static const uintptr_t transport_vtable_rva=0x1d95fd8;
static const uintptr_t transport_method_rva=0x1580270;
static const uintptr_t transport_load_return_rva=0x15808f2;
static const uintptr_t transport_load_method_rva=0x17067e0;
static const unsigned transport_vtable_slot=0x30;
static const unsigned transport_load_vtable_slot=0x18;
static const unsigned transport_event_capacity=32;
static const unsigned transport_load_capacity=8;

extern "C" void bridge_transport_stub();
extern "C" void bridge_wrapper_load_stub();
extern "C" void* bridge_transport_original;
extern "C" void* bridge_wrapper_load_original;
extern "C" {
    void* bridge_transport_original=nullptr;
    void* bridge_wrapper_load_original=nullptr;
}

using TransportMethod=void (*)(void*,void*);
using WrapperLoadMethod=void (*)(void*,void*);

struct TransportLoadedRecord {
    uint64_t callback_sequence;
    uintptr_t native_return;
    uintptr_t peer,peer_vtable,peer_owner,peer_input_ring;
    uintptr_t world_dispatcher,world_transport;
    ProtocolWrapperShape loaded;
    bool caller_verified,header_equal,payload_equal;
    bool peer_readable,world_transport_readable,peer_is_world_transport;
};

struct TransportCompletedEvent {
    uint64_t callback_begin,callback_end;
    uintptr_t transport,outgoing;
    ProtocolWrapperShape source;
    TransportLoadedRecord loaded[transport_load_capacity];
    unsigned load_count,matching_count;
    bool source_captured,loads_truncated,completed;
};

struct TransportThreadContext {
    bool active;
    TransportCompletedEvent event;
};

// Defined by alliance-execution.inc, which is included after this observer.
// It is called while the native outgoing wrapper is still alive and receives
// only copied transport data.
static void execution_transport_loaded(const TransportCompletedEvent& event,
    const TransportLoadedRecord& record);

static thread_local TransportThreadContext transport_thread_context{};
static SRWLOCK transport_event_lock=SRWLOCK_INIT;
static TransportCompletedEvent transport_events[transport_event_capacity]{};
static unsigned transport_event_head=0,transport_event_size=0;
static volatile LONG transport_event_dropped=0;
static volatile LONG transport_install_state=0;
static bool transport_rollback_incomplete=false;

static bool transport_payload_equal(const LifecycleActionShape& left,const LifecycleActionShape& right) {
    return protocol_shape_equal(left,right);
}

static bool transport_header_equal(const ProtocolWrapperShape& left,const ProtocolWrapperShape& right) {
    return left.identity && right.identity && left.readable && right.readable
        && left.prefix_readable && right.prefix_readable
        && left.raw10==right.raw10 && left.raw38==right.raw38
        && left.raw3c==right.raw3c && left.raw40==right.raw40
        && left.raw44==right.raw44 && left.origin48==right.origin48
        && left.flags4a==right.flags4a && left.sequence4c==right.sequence4c;
}

static void transport_capture_peer(TransportLoadedRecord& record,void* peer) {
    record.peer=reinterpret_cast<uintptr_t>(peer);
    if (record.peer<0x10000) return;
    record.peer_readable=read(record.peer,record.peer_vtable)
        && read(record.peer+0x70,record.peer_owner)
        && read(record.peer+0x118,record.peer_input_ring);
    uintptr_t game=0,server=0,world=0;
    record.world_transport_readable=read(base+0x233fe58,game)
        && read(game+0x1e00,server) && read(server+0x330,world)
        && read(world+0x370,record.world_dispatcher)
        && read(record.world_dispatcher+0x58,record.world_transport);
    record.peer_is_world_transport=record.peer_readable
        && record.world_transport_readable && record.peer==record.world_transport;
}

static void transport_enqueue(const TransportCompletedEvent& event) {
    if (!TryAcquireSRWLockExclusive(&transport_event_lock)) {
        InterlockedIncrement(&transport_event_dropped);
        return;
    }
    if (transport_event_size<transport_event_capacity) {
        transport_events[(transport_event_head+transport_event_size)%transport_event_capacity]=event;
        ++transport_event_size;
    } else {
        InterlockedIncrement(&transport_event_dropped);
    }
    ReleaseSRWLockExclusive(&transport_event_lock);
}

static void transport_record_load(void* wrapper,uintptr_t native_return,void* peer) {
    TransportThreadContext& context=transport_thread_context;
    if (!context.active || native_return!=base+transport_load_return_rva) return;
    ProtocolWrapperShape loaded=protocol_capture(wrapper);
    ProtocolWrapperShape source=protocol_capture(reinterpret_cast<void*>(context.event.outgoing));
    context.event.source=source;
    context.event.source_captured=source.address!=0;
    unsigned index=context.event.load_count++;
    TransportLoadedRecord record{};
    record.callback_sequence=lifecycle_next_sequence();
    record.native_return=native_return;
    record.loaded=loaded;
    record.caller_verified=true;
    record.header_equal=transport_header_equal(source,loaded);
    record.payload_equal=transport_payload_equal(source.payload,loaded.payload);
    transport_capture_peer(record,peer);
    if (record.header_equal && record.payload_equal) ++context.event.matching_count;
    if (index<transport_load_capacity) context.event.loaded[index]=record;
    else context.event.loads_truncated=true;
    if (index<transport_load_capacity)
        execution_transport_loaded(context.event,context.event.loaded[index]);
}

// The assembly stub forwards RCX/RDX unchanged and supplies R8=the return
// address after the native load call and R9=the verified R13 peer object.
extern "C" void bridge_wrapper_load_observe(void* wrapper,void* input_context,
    uintptr_t native_return,void* peer) {
    DWORD incoming_error=GetLastError();
    WrapperLoadMethod original=reinterpret_cast<WrapperLoadMethod>(bridge_wrapper_load_original);
    if (!original) { SetLastError(incoming_error); return; }
    SetLastError(incoming_error);
    original(wrapper,input_context);
    DWORD returned_error=GetLastError();
    if (transport_thread_context.active && native_return==base+transport_load_return_rva)
        transport_record_load(wrapper,native_return,peer);
    SetLastError(returned_error);
}

// The transport hook owns the one native call.  All data needed after that
// call is copied by bridge_wrapper_load_observe while the outgoing wrapper is
// still alive; the native transport destroys it before this function returns.
extern "C" void bridge_transport_observe(void* transport,void* outgoing) {
    DWORD incoming_error=GetLastError();
    TransportThreadContext previous=transport_thread_context;
    transport_thread_context=TransportThreadContext{};
    ProtocolWrapperShape initial=protocol_capture(outgoing);
    transport_thread_context.active=initial.identity
        && (initial.payload.vtable==base+lifecycle_alliance_vtable_rva
            || initial.payload.vtable==base+lifecycle_royal_vtable_rva
            || initial.payload.vtable==base+lifecycle_improve_vtable_rva
            || initial.payload.vtable==base+lifecycle_spy_vtable_rva
            || initial.payload.vtable==base+lifecycle_guarantee_vtable_rva
            || initial.payload.vtable==base+lifecycle_support_vtable_rva
            || initial.payload.vtable==base+lifecycle_military_access_vtable_rva
            || initial.payload.vtable==base+lifecycle_vassalization_vtable_rva
            || initial.payload.vtable==base+lifecycle_favor_gold_vtable_rva
            || initial.payload.vtable==base+lifecycle_favor_trust_vtable_rva
            || initial.payload.vtable==base+lifecycle_favor_men_vtable_rva
            || initial.payload.vtable==base+lifecycle_curry_favors_vtable_rva
            || initial.payload.vtable==base+lifecycle_gift_vtable_rva
            || initial.payload.vtable==base+lifecycle_influence_vtable_rva
            || initial.payload.vtable==base+lifecycle_insult_vtable_rva
            || initial.payload.vtable==base+lifecycle_declarewar_vtable_rva
            || initial.payload.vtable==base+lifecycle_peace_vtable_rva)
        && initial.payload.tracked;
    transport_thread_context.event.callback_begin=lifecycle_next_sequence();
    transport_thread_context.event.transport=reinterpret_cast<uintptr_t>(transport);
    transport_thread_context.event.outgoing=reinterpret_cast<uintptr_t>(outgoing);
    TransportMethod original=reinterpret_cast<TransportMethod>(bridge_transport_original);
    const RivalCommandTransportContext previous_rival=rival_command_transport_context;
    rival_command_transport_begin(transport,outgoing);
    SetLastError(incoming_error);
    if (original) original(transport,outgoing);
    DWORD returned_error=GetLastError();
    rival_command_transport_end();
    rival_command_transport_context=previous_rival;
    transport_thread_context.event.completed=original!=nullptr;
    transport_thread_context.event.callback_end=lifecycle_next_sequence();
    if (transport_thread_context.active) transport_enqueue(transport_thread_context.event);
    transport_thread_context=previous;
    SetLastError(returned_error);
}

static bool transport_publish_slot(uintptr_t address,void* expected,void* replacement) {
    void* actual=nullptr;
    if (!read(address,actual) || actual!=expected) return false;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(reinterpret_cast<void*>(address),8,PAGE_READWRITE,&protection)) return false;
    void* prior=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(address),replacement,expected);
    bool installed=prior==expected;
    bool restored=VirtualProtect(reinterpret_cast<void*>(address),8,protection,&ignored)!=FALSE;
    if (!restored) {
        bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(address),expected,replacement)==replacement;
        DWORD retry_protection=0,retry_ignored=0;
        bool retry=VirtualProtect(reinterpret_cast<void*>(address),8,PAGE_READWRITE,&retry_protection)
            && VirtualProtect(reinterpret_cast<void*>(address),8,protection,&retry_ignored);
        transport_rollback_incomplete=transport_rollback_incomplete || !reverted || !retry;
        return false;
    }
    return installed;
}

static bool transport_restore_slot(uintptr_t address,void* original,void* replacement) {
    void* actual=nullptr;
    if (!read(address,actual)) return false;
    if (actual==original) return true;
    if (actual!=replacement) return false;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(reinterpret_cast<void*>(address),8,PAGE_READWRITE,&protection)) return false;
    void* prior=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(address),original,replacement);
    bool swapped=prior==replacement || prior==original;
    bool restored=VirtualProtect(reinterpret_cast<void*>(address),8,protection,&ignored)!=FALSE;
    if (!restored) {
        DWORD retry_protection=0,retry_ignored=0;
        restored=VirtualProtect(reinterpret_cast<void*>(address),8,PAGE_READWRITE,&retry_protection)
            && VirtualProtect(reinterpret_cast<void*>(address),8,protection,&retry_ignored);
    }
    return swapped && restored;
}

static bool transport_rollback() {
    bool complete=true;
    complete=transport_restore_slot(base+transport_vtable_rva+transport_vtable_slot,
        reinterpret_cast<void*>(base+transport_method_rva),reinterpret_cast<void*>(&bridge_transport_stub))
        && complete;
    complete=transport_restore_slot(base+lifecycle_generic_wrapper_vtable_rva+transport_load_vtable_slot,
        reinterpret_cast<void*>(base+transport_load_method_rva),reinterpret_cast<void*>(&bridge_wrapper_load_stub))
        && complete;
    if (!complete) transport_rollback_incomplete=true;
    else {
        transport_rollback_incomplete=false;
        InterlockedExchange(&transport_install_state,0);
    }
    return complete;
}

static bool transport_install() {
    LONG state=InterlockedCompareExchange(&transport_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;
    transport_rollback_incomplete=false;
    void* transport_expected=reinterpret_cast<void*>(base+transport_method_rva);
    void* load_expected=reinterpret_cast<void*>(base+transport_load_method_rva);
    void* transport_slot=nullptr; void* load_slot=nullptr;
    if (!read(base+transport_vtable_rva+transport_vtable_slot,transport_slot)
        || transport_slot!=transport_expected
        || !read(base+lifecycle_generic_wrapper_vtable_rva+transport_load_vtable_slot,load_slot)
        || load_slot!=load_expected) {
        InterlockedExchange(&transport_install_state,0);
        return false;
    }
    bridge_transport_original=transport_expected;
    bridge_wrapper_load_original=load_expected;
    bool first=transport_publish_slot(base+transport_vtable_rva+transport_vtable_slot,
        transport_expected,reinterpret_cast<void*>(&bridge_transport_stub));
    bool second=first && transport_publish_slot(
        base+lifecycle_generic_wrapper_vtable_rva+transport_load_vtable_slot,
        load_expected,reinterpret_cast<void*>(&bridge_wrapper_load_stub));
    if (!second) {
        bool rolled_back=transport_rollback();
        if (!rolled_back) InterlockedExchange(&transport_install_state,-1);
        return false;
    }
    InterlockedExchange(&transport_install_state,2);
    return true;
}

static void transport_emit(const TransportCompletedEvent& event,
    const TransportLoadedRecord* loaded,unsigned load_index) {
    char source[2200]{},target[2200]{},message[7000]{};
    protocol_shape_json(source,sizeof(source),event.source);
    ProtocolWrapperShape empty{};
    protocol_shape_json(target,sizeof(target),loaded?loaded->loaded:empty);
    const TransportLoadedRecord empty_record{};
    if (!loaded) loaded=&empty_record;
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_transport_completed\",\"session_id\":\"%lu-%llx\",\"callback_begin\":%llu,\"callback_end\":%llu,\"transport\":\"0x%llx\",\"outgoing\":\"0x%llx\",\"load_index\":%u,\"load_count\":%u,\"matching_count\":%u,\"loads_truncated\":%s,\"completed\":%s,\"caller_verified\":%s,\"native_return_rva\":\"0x%llx\",\"load_callback_sequence\":%llu,\"header_equal\":%s,\"payload_equal\":%s,\"source_identity\":%s,\"loaded_identity\":%s,\"source_captured\":%s,\"peer\":\"0x%llx\",\"peer_vtable\":\"0x%llx\",\"peer_owner\":\"0x%llx\",\"peer_input_ring\":\"0x%llx\",\"peer_readable\":%s,\"world_dispatcher\":\"0x%llx\",\"world_transport\":\"0x%llx\",\"world_transport_readable\":%s,\"peer_is_world_transport\":%s,\"source\":%s,\"loaded\":%s,\"queue_verified\":false,\"authority\":false,\"all_commands_forwarded\":true}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        static_cast<unsigned long long>(event.callback_begin),static_cast<unsigned long long>(event.callback_end),
        static_cast<unsigned long long>(event.transport),static_cast<unsigned long long>(event.outgoing),load_index,
        event.load_count,event.matching_count,event.loads_truncated?"true":"false",event.completed?"true":"false",
        loaded->caller_verified?"true":"false",protocol_caller_rva(loaded->native_return),
        static_cast<unsigned long long>(loaded->callback_sequence),loaded->header_equal?"true":"false",
        loaded->payload_equal?"true":"false",event.source.identity?"true":"false",
        loaded->loaded.identity?"true":"false",event.source_captured?"true":"false",
        static_cast<unsigned long long>(loaded->peer),static_cast<unsigned long long>(loaded->peer_vtable),
        static_cast<unsigned long long>(loaded->peer_owner),static_cast<unsigned long long>(loaded->peer_input_ring),
        loaded->peer_readable?"true":"false",static_cast<unsigned long long>(loaded->world_dispatcher),
        static_cast<unsigned long long>(loaded->world_transport),loaded->world_transport_readable?"true":"false",
        loaded->peer_is_world_transport?"true":"false",source,target);
    line(message);
}

static void transport_flush() {
    for (unsigned at=0;at<transport_event_capacity;++at) {
        TransportCompletedEvent event{};
        AcquireSRWLockExclusive(&transport_event_lock);
        if (!transport_event_size) { ReleaseSRWLockExclusive(&transport_event_lock); break; }
        const unsigned slot=transport_event_head;
        event=transport_events[slot];
        transport_events[slot]=TransportCompletedEvent{};
        transport_event_head=(slot+1)%transport_event_capacity;
        --transport_event_size;
        ReleaseSRWLockExclusive(&transport_event_lock);
        unsigned count=event.load_count<transport_load_capacity?event.load_count:transport_load_capacity;
        if (!count) transport_emit(event,nullptr,0);
        else for (unsigned index=0;index<count;++index) transport_emit(event,&event.loaded[index],index);
    }
    LONG dropped=InterlockedExchange(&transport_event_dropped,0);
    if (dropped) {
        char message[220]{};
        snprintf(message,sizeof(message),"{\"event\":\"native_alliance_transport_dropped\",\"count\":%ld}\n",static_cast<long>(dropped));
        line(message);
    }
}
