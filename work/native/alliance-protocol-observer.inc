// Passive generic-wrapper decode and clone observations. They bind native
// object transformations; they never authorize an action or infer a receipt.
struct ProtocolWrapperShape {
    uintptr_t address,vtable,action;
    int32_t raw38,raw3c,raw44;
    uint16_t raw40;
    unsigned char raw10;
    uint16_t origin48;
    unsigned char flags4a;
    uint32_t sequence4c;
    bool readable,identity,prefix_readable;
    LifecycleActionShape payload;
};
struct ProtocolReadEvent {
    uint64_t callback_sequence;
    DWORD thread;
    unsigned field_id;
    uintptr_t context,caller_return;
    unsigned char input16[16];
    bool input_readable;
    ProtocolWrapperShape source;
};
struct ProtocolCloneEvent {
    uint64_t begin_sequence,end_sequence;
    DWORD thread;
    uintptr_t opaque_context,caller_return,native_result;
    uintptr_t receiver,receiver_vtable,receiver_host,world_dispatcher,world_transport;
    uintptr_t receiver_counter,receiver_input_ring;
    bool caller_return_matches,receiver_readable,world_transport_readable,receiver_is_world_transport;
    ProtocolWrapperShape source,target;
};
// Defined by the production execution layer included after this observer.
// The callback receives copied shapes after the original clone returns.
static void execution_protocol_clone_completed(const ProtocolCloneEvent& event);
static SRWLOCK protocol_read_lock=SRWLOCK_INIT;
static ProtocolReadEvent protocol_read_events[256]{};
static unsigned protocol_read_head=0,protocol_read_size=0;
static volatile LONG protocol_read_dropped=0;
static SRWLOCK protocol_clone_lock=SRWLOCK_INIT;
static ProtocolCloneEvent protocol_clone_events[128]{};
static unsigned protocol_clone_head=0,protocol_clone_size=0;
static volatile LONG protocol_clone_dropped=0;
extern "C" void* bridge_wrapper_reader_original;
extern "C" void bridge_wrapper_reader_stub();
extern "C" void bridge_wrapper_clone_stub();
extern "C" { void* bridge_wrapper_reader_original=nullptr; }
using ProtocolCloneMethod=void* (*)(void*,void*);
static ProtocolCloneMethod protocol_clone_original=nullptr;

static ProtocolWrapperShape protocol_capture(void* object) {
    ProtocolWrapperShape shape{};
    shape.address=reinterpret_cast<uintptr_t>(object);
    shape.identity=read(shape.address,shape.vtable)
        && shape.vtable==base+lifecycle_generic_wrapper_vtable_rva;
    shape.readable=shape.identity && read(shape.address+0x48,shape.origin48)
        && read(shape.address+0x4a,shape.flags4a)
        && read(shape.address+0x4c,shape.sequence4c)
        && read(shape.address+0x50,shape.action);
    shape.prefix_readable=shape.identity && read(shape.address+0x10,shape.raw10)
        && read(shape.address+0x38,shape.raw38) && read(shape.address+0x3c,shape.raw3c)
        && read(shape.address+0x40,shape.raw40) && read(shape.address+0x44,shape.raw44);
    if (shape.readable) shape.payload=lifecycle_capture_shape(reinterpret_cast<void*>(shape.action));
    return shape;
}

// Transport matching compares copied action payloads after the wrapper clone.
// Keep the family discriminator in this protocol-layer equality contract so a
// Guarantee payload can never match an Alliance, Improve, Spy, or Royal
// payload that happens to share the common 0x165 layout.
static bool protocol_shape_equal(const LifecycleActionShape& left,
    const LifecycleActionShape& right) {
    return left.readable && right.readable
        && left.actor10==right.actor10 && left.mirror18==right.mirror18
        && left.recipient20==right.recipient20 && left.date28==right.date28
        && left.date2c==right.date2c && left.envoy30==right.envoy30
        && left.state34==right.state34 && left.variant38==right.variant38
        && left.proposal3c==right.proposal3c
        && left.royal_marriage==right.royal_marriage
        && left.improve_relations==right.improve_relations
        && left.spy_network==right.spy_network
        && left.guarantee==right.guarantee
        && left.support_independence==right.support_independence
        && left.military_access==right.military_access
        && left.vassalization==right.vassalization
        && left.insult==right.insult && left.declare_war==right.declare_war
        && left.peace_offer==right.peace_offer
        && left.parameter40==right.parameter40
        && left.extra60==right.extra60
        && (!left.declare_war || (left.war.valid() && right.war.valid()
            && left.war==right.war))
        && (!left.peace_offer || (left.peace.valid() && right.peace.valid()
            && left.peace==right.peace));
}

extern "C" void bridge_wrapper_reader_observe(void* wrapper,void* context,unsigned field_id,uintptr_t caller_return) {
    DWORD native_error=GetLastError();
    ProtocolWrapperShape source=protocol_capture(wrapper);
    if (source.identity) {
        ProtocolReadEvent event{};
        event.callback_sequence=lifecycle_next_sequence();
        event.thread=GetCurrentThreadId(); event.field_id=field_id;
        event.context=reinterpret_cast<uintptr_t>(context);
        event.caller_return=caller_return; event.source=source;
        event.input_readable=read(event.context+0x444,event.input16);
        if (TryAcquireSRWLockExclusive(&protocol_read_lock)) {
            if (protocol_read_size<256) {
                protocol_read_events[(protocol_read_head+protocol_read_size)%256]=event;
                ++protocol_read_size;
            } else InterlockedIncrement(&protocol_read_dropped);
            ReleaseSRWLockExclusive(&protocol_read_lock);
        } else InterlockedIncrement(&protocol_read_dropped);
    }
    SetLastError(native_error);
}

// Full bounded 4e8550..4e865c disassembly proves RCX=this, RDX=opaque
// context consumed by the original, RAX=new wrapper. R8/R9 are unused.
extern "C" void* bridge_wrapper_clone_observe(void* wrapper,void* context,uintptr_t native_return,void* receiver) {
    DWORD incoming_error=GetLastError();
    ProtocolCloneEvent event{};
    event.source=protocol_capture(wrapper);
    event.begin_sequence=lifecycle_next_sequence();
    event.thread=GetCurrentThreadId();
    event.opaque_context=reinterpret_cast<uintptr_t>(context);
    event.caller_return=native_return;
    event.caller_return_matches=native_return==reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    // RBP belongs to the verified 15800c0 receive loop only at this exact
    // call boundary. For other callers it remains opaque and is not read.
    if (native_return==base+0x15801e2 && event.caller_return_matches) {
        event.receiver=reinterpret_cast<uintptr_t>(receiver);
        event.receiver_readable=read(event.receiver,event.receiver_vtable)
            && read(event.receiver+0x70,event.receiver_host)
            && read(event.receiver+0x118,event.receiver_input_ring)
            && read(event.receiver+0x128,event.receiver_counter);
        uintptr_t game=0,server=0,world=0;
        event.world_transport_readable=read(base+0x233fe58,game) && read(game+0x1e00,server)
            && read(server+0x330,world) && read(world+0x370,event.world_dispatcher)
            && read(event.world_dispatcher+0x58,event.world_transport);
        event.receiver_is_world_transport=event.receiver_readable && event.world_transport_readable
            && event.receiver==event.world_transport;
    }
    SetLastError(incoming_error);
    void* result=protocol_clone_original(wrapper,context);
    DWORD returned_error=GetLastError();
    event.native_result=reinterpret_cast<uintptr_t>(result);
    event.target=protocol_capture(result);
    event.end_sequence=lifecycle_next_sequence();
    // Limit clone records to exact supported diplomatic objects, including partially
    // decoded snapshots. Dummy handles never establish endpoint authority.
    if (event.source.payload.vtable==base+lifecycle_alliance_vtable_rva
        || event.target.payload.vtable==base+lifecycle_alliance_vtable_rva
        || event.source.payload.vtable==base+lifecycle_royal_vtable_rva
        || event.target.payload.vtable==base+lifecycle_royal_vtable_rva
        || event.source.payload.vtable==base+lifecycle_improve_vtable_rva
        || event.target.payload.vtable==base+lifecycle_improve_vtable_rva
        || event.source.payload.vtable==base+lifecycle_spy_vtable_rva
        || event.target.payload.vtable==base+lifecycle_spy_vtable_rva
        || event.source.payload.vtable==base+lifecycle_guarantee_vtable_rva
        || event.target.payload.vtable==base+lifecycle_guarantee_vtable_rva
        || event.source.payload.vtable==base+lifecycle_support_vtable_rva
        || event.target.payload.vtable==base+lifecycle_support_vtable_rva
        || event.source.payload.vtable==base+lifecycle_military_access_vtable_rva
        || event.target.payload.vtable==base+lifecycle_military_access_vtable_rva
        || event.source.payload.vtable==base+lifecycle_vassalization_vtable_rva
        || event.target.payload.vtable==base+lifecycle_vassalization_vtable_rva
        || event.source.payload.vtable==base+lifecycle_insult_vtable_rva
        || event.target.payload.vtable==base+lifecycle_insult_vtable_rva
        || event.source.payload.vtable==base+lifecycle_declarewar_vtable_rva
        || event.target.payload.vtable==base+lifecycle_declarewar_vtable_rva
        || event.source.payload.vtable==base+lifecycle_peace_vtable_rva
        || event.target.payload.vtable==base+lifecycle_peace_vtable_rva) {
        if (TryAcquireSRWLockExclusive(&protocol_clone_lock)) {
            if (protocol_clone_size<128) {
                protocol_clone_events[(protocol_clone_head+protocol_clone_size)%128]=event;
                ++protocol_clone_size;
            } else InterlockedIncrement(&protocol_clone_dropped);
            ReleaseSRWLockExclusive(&protocol_clone_lock);
        } else InterlockedIncrement(&protocol_clone_dropped);
    }
    execution_protocol_clone_completed(event);
    SetLastError(returned_error);
    return result;
}

static bool protocol_install_slot(uintptr_t offset,uintptr_t expected_rva,void* replacement) {
    void** slot=reinterpret_cast<void**>(base+lifecycle_generic_wrapper_vtable_rva+offset);
    void* expected=reinterpret_cast<void*>(base+expected_rva);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual) || actual!=expected) return false;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    bool installed=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),replacement,expected)==expected;
    if (!VirtualProtect(slot,8,protection,&ignored)) {
        bool reverted=!installed || InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),expected,replacement)==replacement;
        bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !reverted || !restored;
        return false;
    }
    return installed;
}

static bool protocol_rollback() {
    struct Slot { uintptr_t offset,rva; void* replacement; } slots[]={
        {0x20,0x4e84c0,reinterpret_cast<void*>(&bridge_wrapper_reader_stub)},
        {0x60,0x4e8550,reinterpret_cast<void*>(&bridge_wrapper_clone_stub)}
    };
    bool complete=true;
    for (const auto& item:slots) {
        void** slot=reinterpret_cast<void**>(base+lifecycle_generic_wrapper_vtable_rva+item.offset);
        void* expected=reinterpret_cast<void*>(base+item.rva);
        void* actual=nullptr;
        if (!read(reinterpret_cast<uintptr_t>(slot),actual)) { complete=false; continue; }
        if (actual==expected) continue;
        if (actual!=item.replacement) { complete=false; continue; }
        DWORD protection=0,ignored=0;
        if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) { complete=false; continue; }
        void* prior=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),expected,item.replacement);
        complete=(prior==item.replacement || prior==expected) && complete;
        complete=VirtualProtect(slot,8,protection,&ignored)!=FALSE && complete;
    }
    lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !complete;
    return complete;
}

static bool protocol_install() {
    static const unsigned char reader_signature[15]={0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x74,0x24,0x10,0x57,0x48,0x83,0xec,0x20};
    static const unsigned char clone_signature[15]={0x48,0x89,0x5c,0x24,0x18,0x48,0x89,0x74,0x24,0x20,0x48,0x89,0x54,0x24,0x10};
    unsigned char bytes[15]{};
    if (!read(base+0x4e84c0,bytes) || memcmp(bytes,reader_signature,sizeof(bytes))
        || !read(base+0x4e8550,bytes) || memcmp(bytes,clone_signature,sizeof(bytes))) return false;
    bridge_wrapper_reader_original=reinterpret_cast<void*>(base+0x4e84c0);
    protocol_clone_original=reinterpret_cast<ProtocolCloneMethod>(base+0x4e8550);
    // Originals are initialized before either aligned pointer is published.
    if (!protocol_install_slot(0x20,0x4e84c0,reinterpret_cast<void*>(&bridge_wrapper_reader_stub))) return false;
    if (protocol_install_slot(0x60,0x4e8550,reinterpret_cast<void*>(&bridge_wrapper_clone_stub))) return true;
    protocol_rollback();
    return false;
}

static void protocol_shape_json(char* output,size_t capacity,const ProtocolWrapperShape& shape) {
    char payload[1200]{};
    lifecycle_shape_json(payload,sizeof(payload),shape.payload);
    snprintf(output,capacity,"{\"addr\":\"0x%llx\",\"identity\":%s,\"readable\":%s,\"origin\":%u,\"protocol_flags\":%u,\"protocol_sequence\":%u,\"prefix_readable\":%s,\"raw10\":%u,\"raw38\":%d,\"raw3c\":%d,\"raw40\":%u,\"raw44\":%d,\"action\":\"0x%llx\",\"payload\":%s}",
        static_cast<unsigned long long>(shape.address),shape.identity?"true":"false",shape.readable?"true":"false",
        shape.origin48,shape.flags4a,shape.sequence4c,shape.prefix_readable?"true":"false",shape.raw10,
        shape.raw38,shape.raw3c,shape.raw40,shape.raw44,static_cast<unsigned long long>(shape.action),payload);
}

static unsigned long long protocol_caller_rva(uintptr_t caller) {
    return caller>=base+0x1000 && caller<base+0x1b66000?static_cast<unsigned long long>(caller-base):0;
}

static void protocol_flush() {
    for (unsigned i=0;i<64;++i) {
        ProtocolReadEvent event{};
        AcquireSRWLockExclusive(&protocol_read_lock);
        if (!protocol_read_size) { ReleaseSRWLockExclusive(&protocol_read_lock); break; }
        const unsigned slot=protocol_read_head;
        event=protocol_read_events[slot];
        protocol_read_events[slot]=ProtocolReadEvent{};
        protocol_read_head=(slot+1)%256; --protocol_read_size;
        ReleaseSRWLockExclusive(&protocol_read_lock);
        char source[1700]{},input[33]{},message[2600]{};
        protocol_shape_json(source,sizeof(source),event.source);
        if (event.input_readable) for (unsigned at=0;at<16;++at) snprintf(input+at*2,3,"%02x",event.input16[at]);
        snprintf(message,sizeof(message),"{\"event\":\"native_wrapper_field_read_begin\",\"session_id\":\"%lu-%llx\",\"callback_sequence\":%llu,\"thread\":%lu,\"field_id\":%u,\"context\":\"0x%llx\",\"input16_readable\":%s,\"input16_hex\":\"%s\",\"caller_return_rva\":\"0x%llx\",\"source\":%s,\"native_forward_count_by_hook_contract\":1,\"native_return_observed\":false,\"network_source_verified\":false,\"authorization\":\"unknown\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(event.callback_sequence),static_cast<unsigned long>(event.thread),event.field_id,
            static_cast<unsigned long long>(event.context),event.input_readable?"true":"false",input,
            protocol_caller_rva(event.caller_return),source);
        line(message);
    }
    for (unsigned i=0;i<32;++i) {
        ProtocolCloneEvent event{};
        AcquireSRWLockExclusive(&protocol_clone_lock);
        if (!protocol_clone_size) { ReleaseSRWLockExclusive(&protocol_clone_lock); break; }
        const unsigned slot=protocol_clone_head;
        event=protocol_clone_events[slot];
        protocol_clone_events[slot]=ProtocolCloneEvent{};
        protocol_clone_head=(slot+1)%128; --protocol_clone_size;
        ReleaseSRWLockExclusive(&protocol_clone_lock);
        char source[1900]{},target[1900]{},message[5200]{};
        protocol_shape_json(source,sizeof(source),event.source);
        protocol_shape_json(target,sizeof(target),event.target);
        snprintf(message,sizeof(message),"{\"event\":\"native_alliance_wrapper_clone\",\"session_id\":\"%lu-%llx\",\"begin_callback_sequence\":%llu,\"callback_sequence\":%llu,\"thread\":%lu,\"caller_return_rva\":\"0x%llx\",\"caller_return_matches\":%s,\"receiver\":\"0x%llx\",\"receiver_readable\":%s,\"receiver_vtable_rva\":\"0x%llx\",\"receiver_host\":\"0x%llx\",\"receiver_input_ring\":\"0x%llx\",\"receiver_counter\":\"0x%llx\",\"world_transport_readable\":%s,\"world_dispatcher\":\"0x%llx\",\"world_transport\":\"0x%llx\",\"receiver_is_world_transport\":%s,\"opaque_context\":\"0x%llx\",\"native_result\":\"0x%llx\",\"source\":%s,\"target\":%s,\"native_forward_count_by_hook_contract\":1,\"native_return_observed\":true,\"authorization\":\"unknown\",\"submit_receipt\":false}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(event.begin_sequence),static_cast<unsigned long long>(event.end_sequence),
            static_cast<unsigned long>(event.thread),protocol_caller_rva(event.caller_return),event.caller_return_matches?"true":"false",
            static_cast<unsigned long long>(event.receiver),event.receiver_readable?"true":"false",
            event.receiver_vtable>=base && event.receiver_vtable<base+0x2000000?static_cast<unsigned long long>(event.receiver_vtable-base):0,
            static_cast<unsigned long long>(event.receiver_host),static_cast<unsigned long long>(event.receiver_input_ring),
            static_cast<unsigned long long>(event.receiver_counter),event.world_transport_readable?"true":"false",
            static_cast<unsigned long long>(event.world_dispatcher),static_cast<unsigned long long>(event.world_transport),
            event.receiver_is_world_transport?"true":"false",
            static_cast<unsigned long long>(event.opaque_context),static_cast<unsigned long long>(event.native_result),source,target);
        line(message);
    }
    LONG reads=InterlockedExchange(&protocol_read_dropped,0),clones=InterlockedExchange(&protocol_clone_dropped,0);
    if (reads || clones) {
        char message[200]{};
        snprintf(message,sizeof(message),"{\"event\":\"native_wrapper_protocol_dropped\",\"field_reads\":%ld,\"clones\":%ld}\n",static_cast<long>(reads),static_cast<long>(clones));
        line(message);
    }
}
