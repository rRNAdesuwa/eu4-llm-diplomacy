// Passive lifecycle observation for the alliance action vtable.
//
// This file is intentionally an include, rather than a complete DLL.  The
// including observer supplies the existing `base`, `read`, `line`,
// `frame_thread`, `observation_active_query`, and
// `observation_country_handle` symbols.  No native method is called by this
// observer except the original virtual method being observed, exactly once.
// The hooks only enqueue bounded records; JSONL output is done by
// lifecycle_flush() on the frame thread.

#include "declarewar-native-payload.inc"
static bool peace_query_country_pointer(uint64_t handle,uintptr_t& country) noexcept;
#include "peace-native-payload.inc"
#include "peace-action-native-payload.inc"

enum LifecycleEventKind : unsigned char {
    lifecycle_clone_event=1,
    lifecycle_wrapper_event=2,
    lifecycle_destructor_event=3,
    lifecycle_serialization_event=4,
    lifecycle_destructor_return_event=5
};

struct LifecycleActionShape {
    uintptr_t address;
    uintptr_t vtable;
    uint64_t actor10;
    uint64_t mirror18;
    uint64_t recipient20;
    int32_t date28;
    int32_t date2c;
    int32_t envoy30;
    int32_t state34;
    unsigned char variant38;
    int32_t proposal3c;
    int32_t discriminator;
    // The common type discriminator is 0x165 for the supported diplomatic
    // action families. The vtable is therefore part of family identity, and
    // Royal Marriage additionally carries the serialized +0x60 flag.
    bool royal_marriage=false;
    bool improve_relations=false;
    bool spy_network=false;
    bool guarantee=false;
    bool support_independence=false;
    bool military_access=false;
    bool vassalization=false;
    bool insult=false;
    bool declare_war=false;
    bridge::declarewar_payload::WarPayloadExtension war{};
    bool peace_offer=false;
    bridge::peace_payload::PeaceActionPayload peace{};
    int32_t parameter40=0;
    unsigned char extra60=0;
    bool readable;
    bool handles_canonical;
    bool matched;
    bool tracked;
};

// The production execution layer is included after this observer.  The
// callback is intentionally a narrow, read-only identity hand-off: it is
// invoked before the native destructor and must never dereference the object
// after the original returns.
static void execution_lifecycle_source_destroyed(void* source,
    const LifecycleActionShape& snapshot,unsigned flags);

struct LifecycleEvent {
    uint64_t sequence;
    uintptr_t caller_return;
    uint64_t source_event_id;
    uint64_t target_event_id;
    DWORD thread;
    LifecycleEventKind kind;
    LifecycleActionShape source;
    LifecycleActionShape target;
    uintptr_t native_result;
    uintptr_t out_pointer;
    uintptr_t out_value;
    uintptr_t wrapper_vtable;
    uintptr_t wrapper_action;
    uint16_t origin48;
    uint32_t seq4c;
    unsigned char rawflag4a;
    int32_t wrapper_raw38,wrapper_raw3c,wrapper_raw44;
    uint16_t wrapper_raw40;
    unsigned char wrapper_raw10;
    bool wrapper_prefix_readable;
    unsigned native_flags;
    bool wrapper_readable;
    bool wrapper_identity;
    bool result_readable;
    char query_id[65];
};

struct AllianceFieldReadEvent {
    uint64_t callback_sequence;
    DWORD thread;
    uint32_t field_id;
    uintptr_t context;
    uintptr_t context_first_word;
    uintptr_t caller_return;
    LifecycleActionShape source;
    unsigned char input16[16];
    bool input_readable;
    bool context_word_readable;
};
static SRWLOCK field_read_lock=SRWLOCK_INIT;
static AllianceFieldReadEvent field_read_events[128]{};
static unsigned field_read_head=0,field_read_size=0;
static volatile LONG field_read_dropped=0;
extern "C" void* bridge_field_reader_original;
extern "C" void bridge_field_reader_stub();
extern "C" { void* bridge_field_reader_original=nullptr; }
// Royal Marriage uses the same field-reader slot offset but a distinct
// native method/ABI entry.  Keep its original pointer separate so each hook
// tail-jumps to the exact method installed in its own vtable.
extern "C" void* bridge_royal_field_reader_original;
extern "C" void bridge_royal_field_reader_stub();
extern "C" { void* bridge_royal_field_reader_original=nullptr; }
// Declare War has a distinct native field-reader entry. Keep its original
// independent so its tail-jump and rollback never cross family ABIs.
extern "C" void* bridge_declarewar_field_reader_original;
extern "C" void bridge_declarewar_field_reader_stub();
extern "C" { void* bridge_declarewar_field_reader_original=nullptr; }
extern "C" void* bridge_peace_field_reader_original;
extern "C" void bridge_peace_field_reader_stub();
extern "C" { void* bridge_peace_field_reader_original=nullptr; }

static SRWLOCK lifecycle_lock=SRWLOCK_INIT;
static LifecycleEvent lifecycle_events[128]{};
static unsigned lifecycle_head=0;
static unsigned lifecycle_size=0;
static volatile LONG lifecycle_dropped=0;
// Callback ordering shares observation_callback_sequence with command entry.
// A sequence identifies an observation, never an object's allocation lifetime.
static volatile LONG lifecycle_install_state=0;
static volatile LONG lifecycle_royal_install_state=0;
static volatile LONG lifecycle_improve_install_state=0;
static volatile LONG lifecycle_spy_install_state=0;
static volatile LONG lifecycle_guarantee_install_state=0;
static volatile LONG lifecycle_support_install_state=0;
static volatile LONG lifecycle_military_access_install_state=0;
static volatile LONG lifecycle_vassalization_install_state=0;
static volatile LONG lifecycle_vassalization_field_reader_install_state=0;
static volatile LONG lifecycle_insult_install_state=0;
static volatile LONG lifecycle_royal_field_reader_install_state=0;
static volatile LONG lifecycle_declarewar_install_state=0;
static volatile LONG lifecycle_declarewar_field_reader_install_state=0;
static volatile LONG lifecycle_peace_install_state=0;
static volatile LONG lifecycle_peace_field_reader_install_state=0;
static bool lifecycle_rollback_incomplete=false;

using LifecycleCloneMethod=void* (*)(void*);
using LifecycleWrapperMethod=void* (*)(void*,void**);
using LifecycleDestructorMethod=void* (*)(void*,unsigned);
static LifecycleCloneMethod lifecycle_clone_original=nullptr;
static LifecycleWrapperMethod lifecycle_wrapper_original=nullptr;
static LifecycleDestructorMethod lifecycle_destructor_original=nullptr;
static LifecycleCloneMethod lifecycle_royal_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_improve_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_spy_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_guarantee_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_support_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_military_access_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_vassalization_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_insult_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_declarewar_clone_original=nullptr;
static LifecycleCloneMethod lifecycle_peace_clone_original=nullptr;
static LifecycleDestructorMethod lifecycle_insult_destructor_original=nullptr;
static LifecycleDestructorMethod lifecycle_royal_destructor_original=nullptr;
static LifecycleDestructorMethod lifecycle_declarewar_destructor_original=nullptr;
static LifecycleDestructorMethod lifecycle_peace_destructor_original=nullptr;

static const uintptr_t lifecycle_alliance_vtable_rva=0x1c80720;
static const uintptr_t lifecycle_royal_vtable_rva=0x1c80ab0;
static const uintptr_t lifecycle_improve_vtable_rva=0x1c7dd68;
static const uintptr_t lifecycle_spy_vtable_rva=0x1c7cc48;
static const uintptr_t lifecycle_guarantee_vtable_rva=0x1c7fe50;
static const uintptr_t lifecycle_support_vtable_rva=0x1c805f0;
static const uintptr_t lifecycle_military_access_vtable_rva=0x1c7fb70;
static const uintptr_t lifecycle_vassalization_vtable_rva=0x1c7fd20;
static const uintptr_t lifecycle_insult_vtable_rva=0x1c7f6b0;
static const uintptr_t lifecycle_declarewar_vtable_rva=0x1c80d90;
static const uintptr_t lifecycle_peace_vtable_rva=0x1c7b840;
static const uintptr_t lifecycle_insult_clone_rva=0x538e50;
static const uintptr_t lifecycle_insult_destructor_rva=0x129500;
static const uintptr_t lifecycle_declarewar_clone_rva=0x50b920;
static const uintptr_t lifecycle_declarewar_destructor_rva=0x500550;
static const uintptr_t lifecycle_clone_rva=0x513090;
static const uintptr_t lifecycle_royal_clone_rva=0x4f0800;
static const uintptr_t lifecycle_guarantee_clone_rva=0x5224f0;
static const uintptr_t lifecycle_support_clone_rva=0x50f0c0;
static const uintptr_t lifecycle_military_access_clone_rva=0x525da0;
static const uintptr_t lifecycle_vassalization_clone_rva=0x51fa30;
static const uintptr_t lifecycle_wrapper_rva=0x4e9960;
static const uintptr_t lifecycle_destructor_rva=0x129450;
static const uintptr_t lifecycle_royal_destructor_rva=0x4ed5e0;
static const uintptr_t lifecycle_royal_field_reader_rva=0x4f0900;
static const uintptr_t lifecycle_declarewar_field_reader_rva=0x50bc40;
static const uintptr_t lifecycle_generic_wrapper_vtable_rva=0x1c814b0;
static const unsigned lifecycle_slot_range=0xb8;
extern "C" void* bridge_serializer_original;
extern "C" void bridge_serializer_stub();
extern "C" { void* bridge_serializer_original=nullptr; }

// The serializer ABI is forwarded by assembly, including all extra arguments
// and the original return value. This callback only takes a read-only snapshot
// before the original payload serializer; it is not a queue/submit receipt.
extern "C" void bridge_serializer_observe(void* wrapper);

static bool lifecycle_country_of_interest(uint64_t handle) {
    uint32_t tag=static_cast<uint32_t>(handle&0xffffff);
    // Bound the event rate by the controlled and experiment endpoints.
    // Country database slot numbers are resolved per session, not assumed.
    return tag==0x415246 || tag==0x524f50 || tag==0x564153 || tag==0x54494c;
}

static void lifecycle_copy_query(char (&destination)[65]) {
    destination[0]=0;
    if (GetCurrentThreadId()!=frame_thread || !observation_active_query) return;
    unsigned at=0;
    for (;at<64 && observation_active_query[at];++at) {
        char value=observation_active_query[at];
        bool identifier=(value>='A' && value<='Z') || (value>='a' && value<='z')
            || (value>='0' && value<='9') || value=='_' || value=='-';
        if (!identifier) { destination[0]=0; return; }
        destination[at]=value;
    }
    destination[at]=0;
}

static LifecycleActionShape lifecycle_capture_shape(void* object) {
    LifecycleActionShape shape{};
    shape.address=reinterpret_cast<uintptr_t>(object);
    if (!object || shape.address<0x10000) return shape;

    int32_t discriminator=0;
    bool bytes=read(shape.address,shape.vtable)
        && read(shape.address+0x08,discriminator)
        && read(shape.address+0x10,shape.actor10)
        && read(shape.address+0x18,shape.mirror18)
        && read(shape.address+0x20,shape.recipient20)
        && read(shape.address+0x28,shape.date28)
        && read(shape.address+0x2c,shape.date2c)
        && read(shape.address+0x30,shape.envoy30)
        && read(shape.address+0x34,shape.state34)
        && read(shape.address+0x38,shape.variant38)
        && read(shape.address+0x3c,shape.proposal3c);
    shape.discriminator=discriminator;
    shape.readable=bytes;
    if (!bytes || shape.discriminator!=0x165) return shape;

    bool alliance=shape.vtable==base+lifecycle_alliance_vtable_rva;
    bool royal=shape.vtable==base+lifecycle_royal_vtable_rva;
    bool improve=shape.vtable==base+lifecycle_improve_vtable_rva;
    bool spy=shape.vtable==base+lifecycle_spy_vtable_rva;
    bool guarantee=shape.vtable==base+lifecycle_guarantee_vtable_rva;
    bool support=shape.vtable==base+lifecycle_support_vtable_rva;
    bool military=shape.vtable==base+lifecycle_military_access_vtable_rva;
    bool vassalization=shape.vtable==base+lifecycle_vassalization_vtable_rva;
    bool insult=shape.vtable==base+lifecycle_insult_vtable_rva;
    bool declare_war=shape.vtable==base+lifecycle_declarewar_vtable_rva;
    bool peace=shape.vtable==base+lifecycle_peace_vtable_rva;
    if (!alliance && !royal && !improve && !spy && !guarantee && !support
        && !military && !vassalization && !insult && !declare_war && !peace) return shape;
    shape.royal_marriage=royal;
    shape.improve_relations=improve;
    shape.spy_network=spy;
    shape.guarantee=guarantee;
    shape.support_independence=support;
    shape.military_access=military;
    shape.vassalization=vassalization;
    shape.insult=insult;
    shape.declare_war=declare_war;
    shape.peace_offer=peace;
    if (insult && !read(shape.address+0x40,shape.parameter40)) {
        shape.readable=false; return shape;
    }
    if (royal) {
        // +0x60 is a serialized Royal Marriage flag.  A Royal object is not
        // matched unless the field was read and has the native 0/1 domain;
        // the authority layer applies its stricter flag==0 policy later.
        if (!read(shape.address+0x60,shape.extra60)) {
            shape.readable=false;
            return shape;
        }
        if (shape.extra60>1) return shape;
    }
    if (declare_war
        && !lifecycle_declarewar_capture_payload(shape.address,shape.war)) {
        // A Declare War object is only complete when its three native vector
        // spans and, when present, its owned payload have all been read.
        // Never allow a partial extension to establish a clone/transport match.
        shape.readable=false;
        return shape;
    }
    if (peace && !lifecycle_peace_capture_payload(shape.address,shape.peace)) {
        shape.readable=false;
        return shape;
    }
    if (shape.variant38>1) return shape;

    // +0x18 is the constructor's mirror of the actor handle.  Require all
    // three handles to be canonical before interpreting this as a diplomatic
    // action; an arbitrary pointer is never treated as an authority token.
    shape.handles_canonical=observation_country_handle(shape.actor10)
        && observation_country_handle(shape.mirror18)
        && observation_country_handle(shape.recipient20)
        && shape.mirror18==shape.actor10;
    shape.tracked=shape.handles_canonical
        && (lifecycle_country_of_interest(shape.actor10)
            || lifecycle_country_of_interest(shape.recipient20));
    shape.matched=shape.handles_canonical;
    return shape;
}

static uint64_t lifecycle_next_sequence() {
    return static_cast<uint64_t>(InterlockedIncrement64(&observation_callback_sequence));
}

static void lifecycle_enqueue(const LifecycleEvent& event) {
    if (!TryAcquireSRWLockExclusive(&lifecycle_lock)) {
        InterlockedIncrement(&lifecycle_dropped);
        return;
    }
    if (lifecycle_size<128) {
        lifecycle_events[(lifecycle_head+lifecycle_size)%128]=event;
        ++lifecycle_size;
    } else {
        InterlockedIncrement(&lifecycle_dropped);
    }
    ReleaseSRWLockExclusive(&lifecycle_lock);
}

static void* lifecycle_clone_observe(void* source) {
    const uintptr_t caller_return=reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    LifecycleActionShape before=lifecycle_capture_shape(source);
    uintptr_t class_vtable=0;
    read(reinterpret_cast<uintptr_t>(source),class_vtable);
    LifecycleCloneMethod original=class_vtable==base+lifecycle_peace_vtable_rva
        ? lifecycle_peace_clone_original : class_vtable==base+lifecycle_declarewar_vtable_rva
        ? lifecycle_declarewar_clone_original : class_vtable==base+lifecycle_royal_vtable_rva
        ? lifecycle_royal_clone_original : class_vtable==base+lifecycle_improve_vtable_rva
        ? lifecycle_improve_clone_original : class_vtable==base+lifecycle_spy_vtable_rva
        ? lifecycle_spy_clone_original : class_vtable==base+lifecycle_guarantee_vtable_rva
        ? lifecycle_guarantee_clone_original : class_vtable==base+lifecycle_support_vtable_rva
        ? lifecycle_support_clone_original : class_vtable==base+lifecycle_military_access_vtable_rva
        ? lifecycle_military_access_clone_original : class_vtable==base+lifecycle_vassalization_vtable_rva
        ? lifecycle_vassalization_clone_original : class_vtable==base+lifecycle_insult_vtable_rva
        ? lifecycle_insult_clone_original : lifecycle_clone_original;
    // Installation cannot publish this hook without an original.  Keeping a
    // null guard prevents an accidental manual call from inventing a native
    // result; the installed path always reaches the exact original once.
    if (!original) return nullptr;
    void* result=original(source);
    if (!before.tracked) return result;

    LifecycleEvent event{};
    event.sequence=lifecycle_next_sequence();
    event.source_event_id=event.sequence;
    event.target_event_id=event.sequence;
    event.thread=GetCurrentThreadId();
    event.kind=lifecycle_clone_event;
    event.caller_return=caller_return;
    event.source=before;
    event.target=lifecycle_capture_shape(result);
    event.native_result=reinterpret_cast<uintptr_t>(result);
    event.result_readable=event.target.readable;
    lifecycle_copy_query(event.query_id);
    lifecycle_enqueue(event);
    return result;
}

static void* lifecycle_wrapper_observe(void* source,void** out) {
    LifecycleActionShape before=lifecycle_capture_shape(source);
    LifecycleWrapperMethod original=lifecycle_wrapper_original;
    if (!original) return nullptr;
    void* result=original(source,out);
    if (!before.tracked) return result;

    LifecycleEvent event{};
    event.sequence=lifecycle_next_sequence();
    event.source_event_id=event.sequence;
    event.target_event_id=event.sequence;
    event.thread=GetCurrentThreadId();
    event.kind=lifecycle_wrapper_event;
    event.source=before;
    event.native_result=reinterpret_cast<uintptr_t>(result);
    event.out_pointer=reinterpret_cast<uintptr_t>(out);
    lifecycle_copy_query(event.query_id);

    uintptr_t wrapper=0;
    if (out && read(reinterpret_cast<uintptr_t>(out),wrapper)) {
        event.out_value=wrapper;
        event.wrapper_readable=read(wrapper,event.wrapper_vtable)
            && event.wrapper_vtable==base+lifecycle_generic_wrapper_vtable_rva;
        event.wrapper_identity=event.wrapper_readable;
        if (event.wrapper_readable) {
            event.wrapper_readable=read(wrapper+0x50,event.wrapper_action)
                && read(wrapper+0x48,event.origin48)
                && read(wrapper+0x4a,event.rawflag4a)
                && read(wrapper+0x4c,event.seq4c);
            if (event.wrapper_readable) event.target=lifecycle_capture_shape(
                reinterpret_cast<void*>(event.wrapper_action));
        }
    }
    lifecycle_enqueue(event);
    return result;
}

static void* lifecycle_destructor_observe(void* source,unsigned flags) {
    LifecycleActionShape before=lifecycle_capture_shape(source);
    uintptr_t class_vtable=0;
    read(reinterpret_cast<uintptr_t>(source),class_vtable);
    LifecycleDestructorMethod original=class_vtable==base+lifecycle_peace_vtable_rva
        ? lifecycle_peace_destructor_original : class_vtable==base+lifecycle_declarewar_vtable_rva
        ? lifecycle_declarewar_destructor_original : class_vtable==base+lifecycle_royal_vtable_rva
        ? lifecycle_royal_destructor_original : class_vtable==base+lifecycle_insult_vtable_rva
        ? lifecycle_insult_destructor_original : lifecycle_destructor_original;
    if (!original) return nullptr;
    if (before.tracked)
        execution_lifecycle_source_destroyed(source,before,flags);
    if (before.tracked) {
        LifecycleEvent event{};
        event.sequence=lifecycle_next_sequence();
        event.source_event_id=event.sequence;
        event.target_event_id=0;
        event.thread=GetCurrentThreadId();
        event.kind=lifecycle_destructor_event;
        event.source=before;
        event.native_flags=flags;
        lifecycle_copy_query(event.query_id);
        // This is intentionally before the native destructor.  No field of
        // the object is read after the original can release it.
        lifecycle_enqueue(event);
    }
    void* result=original(source,flags);
    if (before.tracked) {
        LifecycleEvent event{};
        event.sequence=lifecycle_next_sequence();
        event.source_event_id=event.sequence;
        event.thread=GetCurrentThreadId();
        event.kind=lifecycle_destructor_return_event;
        event.source=before; // Snapshot from before the call; never dereference a released object.
        event.native_flags=flags;
        event.native_result=reinterpret_cast<uintptr_t>(result);
        lifecycle_copy_query(event.query_id);
        lifecycle_enqueue(event);
    }
    return result;
}

extern "C" void bridge_serializer_observe(void* object) {
    uintptr_t wrapper=reinterpret_cast<uintptr_t>(object),vtable=0,action=0;
    if (!read(wrapper,vtable) || vtable!=base+lifecycle_generic_wrapper_vtable_rva
        || !read(wrapper+0x50,action)) return;
    LifecycleActionShape shape=lifecycle_capture_shape(reinterpret_cast<void*>(action));
    if (!shape.tracked) return;
    LifecycleEvent event{};
    event.sequence=lifecycle_next_sequence();
    event.source_event_id=event.sequence;
    event.thread=GetCurrentThreadId();
    event.kind=lifecycle_serialization_event;
    event.source=shape;
    event.out_value=wrapper;
    event.wrapper_vtable=vtable;
    event.wrapper_action=action;
    event.wrapper_identity=true;
    event.wrapper_readable=read(wrapper+0x48,event.origin48)
        && read(wrapper+0x4a,event.rawflag4a) && read(wrapper+0x4c,event.seq4c);
    event.wrapper_prefix_readable=read(wrapper+0x10,event.wrapper_raw10)
        && read(wrapper+0x38,event.wrapper_raw38) && read(wrapper+0x3c,event.wrapper_raw3c)
        && read(wrapper+0x40,event.wrapper_raw40) && read(wrapper+0x44,event.wrapper_raw44);
    lifecycle_copy_query(event.query_id);
    lifecycle_enqueue(event);
}

static bool lifecycle_install_serializer() {
    void** slot=reinterpret_cast<void**>(base+lifecycle_generic_wrapper_vtable_rva+0x10);
    void* expected=reinterpret_cast<void*>(base+0x4e8470);
    void* original=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),original) || original!=expected) return false;
    // Publish the exact original before the single aligned pointer exchange.
    bridge_serializer_original=original;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    void* hook=reinterpret_cast<void*>(&bridge_serializer_stub);
    bool installed=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),hook,expected)==expected;
    if (!VirtualProtect(slot,8,protection,&ignored)) {
        bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(slot),expected,hook)==hook;
        bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
        lifecycle_rollback_incomplete=!reverted || !restored;
        return false;
    }
    return installed;
}

static const char* lifecycle_kind_name(LifecycleEventKind kind) {
    switch (kind) {
    case lifecycle_clone_event: return "clone";
    case lifecycle_wrapper_event: return "wrapper";
    case lifecycle_destructor_event: return "destructor";
    case lifecycle_serialization_event: return "serialization_begin";
    case lifecycle_destructor_return_event: return "destructor_return";
    default: return "unknown";
    }
}

static void lifecycle_shape_json(char* output,size_t capacity,const LifecycleActionShape& shape) {
    unsigned long long vtable_rva=(shape.vtable>=base && shape.vtable<base+0x2000000)
        ? static_cast<unsigned long long>(shape.vtable-base) : 0;
    const char* family=shape.peace_offer ? "peace" : shape.declare_war ? "declare_war"
        : shape.royal_marriage ? "royal_marriage"
        : shape.spy_network ? "spy_network"
        : shape.improve_relations ? "improve_relations"
        : shape.guarantee ? "guarantee"
        : shape.support_independence ? "support_independence"
        : shape.military_access ? "military_access"
        : shape.vassalization ? "vassalization"
        : shape.insult ? "insult"
        : (shape.vtable==base+lifecycle_alliance_vtable_rva ? "alliance" : "unknown");
    char war_json[1200]{};
    if (shape.declare_war) {
        lifecycle_declarewar_payload_json(war_json,sizeof(war_json),shape.war,
            shape.readable && shape.war.valid(),capacity<1800);
    } else {
        strcpy(war_json,"null");
    }
    char peace_json[256]{};
    if (shape.peace_offer) lifecycle_peace_payload_json(peace_json,sizeof(peace_json),shape.peace);
    else strcpy(peace_json,"null");
    snprintf(output,capacity,
        "{\"addr\":\"0x%llx\",\"readable\":%s,\"matched\":%s,\"handles_canonical\":%s,\"tracked\":%s,\"family\":\"%s\",\"declare_war\":%s,\"extra60\":%u,\"parameter40\":%d,\"vtable_rva\":\"0x%llx\",\"discriminator\":%d,\"actor10\":\"0x%llx\",\"mirror18\":\"0x%llx\",\"recipient20\":\"0x%llx\",\"date28\":%d,\"date2c\":%d,\"envoy30\":%d,\"state34\":%d,\"variant38\":%u,\"proposal3c\":%d,\"war\":%s,\"peace\":%s}",
        static_cast<unsigned long long>(shape.address),shape.readable?"true":"false",
        shape.matched?"true":"false",shape.handles_canonical?"true":"false",
        shape.tracked?"true":"false",family,shape.declare_war?"true":"false",
        static_cast<unsigned>(shape.extra60),shape.parameter40,vtable_rva,
        shape.discriminator,
        static_cast<unsigned long long>(shape.actor10),static_cast<unsigned long long>(shape.mirror18),
        static_cast<unsigned long long>(shape.recipient20),shape.date28,shape.date2c,
        shape.envoy30,shape.state34,static_cast<unsigned>(shape.variant38),shape.proposal3c,
        war_json,peace_json);
}

extern "C" void bridge_field_reader_observe(void* action,void* context,unsigned field_id,uintptr_t caller_return) {
    LifecycleActionShape shape=lifecycle_capture_shape(action);
    // During decoding handles may not yet be initialized. Record exact class
    // snapshots even when incomplete; incomplete handles never grant authority.
    bool known_family=shape.vtable==base+lifecycle_alliance_vtable_rva
        || shape.royal_marriage || shape.vassalization || shape.declare_war || shape.peace_offer;
    if (!shape.readable || !known_family || shape.discriminator!=0x165) return;
    AllianceFieldReadEvent event{};
    event.callback_sequence=lifecycle_next_sequence();
    event.thread=GetCurrentThreadId();
    event.field_id=field_id;
    event.context=reinterpret_cast<uintptr_t>(context);
    event.caller_return=caller_return;
    event.source=shape;
    event.input_readable=read(event.context+0x444,event.input16);
    event.context_word_readable=read(event.context,event.context_first_word);
    if (!TryAcquireSRWLockExclusive(&field_read_lock)) { InterlockedIncrement(&field_read_dropped); return; }
    if (field_read_size<128) {
        field_read_events[(field_read_head+field_read_size)%128]=event;
        ++field_read_size;
    } else InterlockedIncrement(&field_read_dropped);
    ReleaseSRWLockExclusive(&field_read_lock);
}

static bool lifecycle_install_field_reader() {
    void** slot=reinterpret_cast<void**>(base+lifecycle_alliance_vtable_rva+0x20);
    void* expected_method=reinterpret_cast<void*>(base+0x4e8b70);
    void* actual=nullptr;
    static const unsigned char signature[16]={0x48,0x89,0x5c,0x24,0x08,0x57,0x48,0x83,0xec,0x20,0x48,0x8b,0xda,0x48,0x8b,0xf9};
    unsigned char bytes[16]{};
    if (!read(reinterpret_cast<uintptr_t>(slot),actual) || actual!=expected_method
        || !read(base+0x4e8b70,bytes) || memcmp(bytes,signature,sizeof(bytes))) return false;
    bridge_field_reader_original=actual;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    void* hook=reinterpret_cast<void*>(&bridge_field_reader_stub);
    bool installed=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),hook,actual)==actual;
    if (!VirtualProtect(slot,8,protection,&ignored)) {
        bool reverted=!installed || InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),actual,hook)==hook;
        bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !reverted || !restored;
        return false;
    }
    return installed;
}

// Royal Marriage has the same common action layout but a distinct vtable.
// Install the three lifecycle hooks against the exact Royal originals and
// retain those originals separately for family-aware forwarding.  The outer
// installer may roll these slots back using the same expected/replacement
// pairs listed here; this function also rolls back every slot it changed when
// a later local exchange or protection restore fails.
static bool lifecycle_rollback_royal_slots(void** table,unsigned changed) {
    struct Slot { unsigned offset; void* expected; void* replacement; } slots[3]={
        {0x00,reinterpret_cast<void*>(base+lifecycle_royal_destructor_rva),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {0x40,reinterpret_cast<void*>(base+lifecycle_wrapper_rva),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {0xb0,reinterpret_cast<void*>(base+lifecycle_royal_clone_rva),reinterpret_cast<void*>(&lifecycle_clone_observe)}
    };
    bool ok=true;
    for (unsigned i=0;i<changed;++i) {
        void* previous=InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(reinterpret_cast<unsigned char*>(table)+slots[i].offset),
            slots[i].expected,slots[i].replacement);
        if (previous!=slots[i].replacement && previous!=slots[i].expected) ok=false;
    }
    return ok;
}

[[maybe_unused]] static bool lifecycle_install_royal() {
    LONG state=InterlockedCompareExchange(&lifecycle_royal_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;

    void** table=reinterpret_cast<void**>(base+lifecycle_royal_vtable_rva);
    void* expected_destructor=nullptr;
    void* expected_wrapper=nullptr;
    void* expected_clone=nullptr;
    bool identities=read(reinterpret_cast<uintptr_t>(table)+0x00,expected_destructor)
        && read(reinterpret_cast<uintptr_t>(table)+0x40,expected_wrapper)
        && read(reinterpret_cast<uintptr_t>(table)+0xb0,expected_clone)
        && expected_destructor==reinterpret_cast<void*>(base+lifecycle_royal_destructor_rva)
        && expected_wrapper==reinterpret_cast<void*>(base+lifecycle_wrapper_rva)
        && expected_clone==reinterpret_cast<void*>(base+lifecycle_royal_clone_rva);
    if (!identities) {
        InterlockedExchange(&lifecycle_royal_install_state,-1);
        return false;
    }
    lifecycle_royal_destructor_original=reinterpret_cast<LifecycleDestructorMethod>(expected_destructor);
    lifecycle_royal_clone_original=reinterpret_cast<LifecycleCloneMethod>(expected_clone);
    // The wrapper implementation is shared by both action families.  Keep a
    // single exact original pointer so both hooks tail-call the same method.
    if (!lifecycle_wrapper_original)
        lifecycle_wrapper_original=reinterpret_cast<LifecycleWrapperMethod>(expected_wrapper);
    if (lifecycle_wrapper_original!=reinterpret_cast<LifecycleWrapperMethod>(expected_wrapper)) {
        InterlockedExchange(&lifecycle_royal_install_state,-1);
        return false;
    }

    DWORD original_protection=0;
    if (!VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&original_protection)) {
        InterlockedExchange(&lifecycle_royal_install_state,-1);
        return false;
    }
    struct Slot { unsigned offset; void* expected; void* replacement; } slots[3]={
        {0x00,expected_destructor,reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {0x40,expected_wrapper,reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {0xb0,expected_clone,reinterpret_cast<void*>(&lifecycle_clone_observe)}
    };
    unsigned changed=0;
    bool installed=true;
    for (unsigned i=0;i<3;++i) {
        void* previous=InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(reinterpret_cast<unsigned char*>(table)+slots[i].offset),
            slots[i].replacement,slots[i].expected);
        if (previous!=slots[i].expected) { installed=false; break; }
        ++changed;
    }
    DWORD ignored=0;
    bool protection_restored=VirtualProtect(table,lifecycle_slot_range,original_protection,&ignored)!=FALSE;
    if (!installed || !protection_restored) {
        DWORD temporary=0;
        bool rollback=VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&temporary)!=FALSE;
        if (rollback) {
            rollback=lifecycle_rollback_royal_slots(table,changed);
            rollback=VirtualProtect(table,lifecycle_slot_range,original_protection,&ignored)!=FALSE && rollback;
        }
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !rollback;
        InterlockedExchange(&lifecycle_royal_install_state,-1);
        return false;
    }
    InterlockedExchange(&lifecycle_royal_install_state,2);
    return true;
}

// Improve Relations, Spy Network, and Guarantee share the common destructor
// and wrapper slots.  Their clone methods remain family-specific, so the
// installer takes the exact family addresses and original-storage location as
// explicit parameters.  The old Improve/Spy wrappers below are retained for
// callers that already use those entry points.
static bool lifecycle_install_small_action(volatile LONG* install_state,
    uintptr_t vtable_rva,uintptr_t clone_rva,LifecycleCloneMethod* clone_original,
    uintptr_t destructor_rva=lifecycle_destructor_rva) {
    LONG state=InterlockedCompareExchange(install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;
    auto table=reinterpret_cast<unsigned char*>(base+vtable_rva);
    struct Slot { unsigned offset; void* expected; void* replacement; } slots[]={
        {0x00,reinterpret_cast<void*>(base+destructor_rva),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {0x40,reinterpret_cast<void*>(base+lifecycle_wrapper_rva),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {0xb0,reinterpret_cast<void*>(base+clone_rva),reinterpret_cast<void*>(&lifecycle_clone_observe)}
    };
    for (const auto& slot:slots) {
        void* actual=nullptr;
        if (!read(reinterpret_cast<uintptr_t>(table)+slot.offset,actual) || actual!=slot.expected) {
            InterlockedExchange(install_state,-1); return false;
        }
    }
    if (lifecycle_destructor_original!=reinterpret_cast<LifecycleDestructorMethod>(base+lifecycle_destructor_rva)
        || lifecycle_wrapper_original!=reinterpret_cast<LifecycleWrapperMethod>(base+lifecycle_wrapper_rva)) {
        InterlockedExchange(install_state,-1); return false;
    }
    *clone_original=reinterpret_cast<LifecycleCloneMethod>(base+clone_rva);
    if (vtable_rva==lifecycle_insult_vtable_rva)
        lifecycle_insult_destructor_original=reinterpret_cast<LifecycleDestructorMethod>(base+destructor_rva);
    if (vtable_rva==lifecycle_peace_vtable_rva)
        lifecycle_peace_destructor_original=reinterpret_cast<LifecycleDestructorMethod>(base+destructor_rva);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&protection)) {
        InterlockedExchange(install_state,-1); return false;
    }
    unsigned changed=0;
    for (const auto& slot:slots) {
        void* previous=InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(table+slot.offset),slot.replacement,slot.expected);
        if (previous!=slot.expected) break;
        ++changed;
    }
    bool restored=VirtualProtect(table,lifecycle_slot_range,protection,&ignored)!=FALSE;
    if (changed!=3 || !restored) {
        DWORD temporary=0;
        bool rolled=VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&temporary)!=FALSE;
        if (rolled) {
            for (unsigned i=0;i<changed;++i) {
                void* previous=InterlockedCompareExchangePointer(
                    reinterpret_cast<void* volatile*>(table+slots[i].offset),slots[i].expected,slots[i].replacement);
                rolled=(previous==slots[i].replacement || previous==slots[i].expected) && rolled;
            }
            rolled=VirtualProtect(table,lifecycle_slot_range,protection,&ignored)!=FALSE && rolled;
        }
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !rolled;
        InterlockedExchange(install_state,-1); return false;
    }
    InterlockedExchange(install_state,2);
    return true;
}

static bool lifecycle_install_task(bool spy) {
    return lifecycle_install_small_action(
        spy?&lifecycle_spy_install_state:&lifecycle_improve_install_state,
        spy?lifecycle_spy_vtable_rva:lifecycle_improve_vtable_rva,
        spy?0x586230:0x574b50,
        spy?&lifecycle_spy_clone_original:&lifecycle_improve_clone_original);
}

static bool lifecycle_install_improve() { return lifecycle_install_task(false); }
static bool lifecycle_install_spy() { return lifecycle_install_task(true); }
static bool lifecycle_install_guarantee() {
    return lifecycle_install_small_action(&lifecycle_guarantee_install_state,
        lifecycle_guarantee_vtable_rva,lifecycle_guarantee_clone_rva,
        &lifecycle_guarantee_clone_original);
}
static bool lifecycle_install_support() {
    return lifecycle_install_small_action(&lifecycle_support_install_state,
        lifecycle_support_vtable_rva,lifecycle_support_clone_rva,
        &lifecycle_support_clone_original);
}
static bool lifecycle_install_military_access() {
    return lifecycle_install_small_action(&lifecycle_military_access_install_state,
        lifecycle_military_access_vtable_rva,lifecycle_military_access_clone_rva,
        &lifecycle_military_access_clone_original);
}

// Vassalization uses the common 4e8b70 field-reader ABI at vtable +0x20.
// This is a separate optional slot installation because the existing Alliance
// and Royal readers have independent installers and rollback state.
static bool lifecycle_install_vassalization_field_reader() {
    LONG state=InterlockedCompareExchange(
        &lifecycle_vassalization_field_reader_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;

    void** slot=reinterpret_cast<void**>(
        base+lifecycle_vassalization_vtable_rva+0x20);
    void* expected_method=reinterpret_cast<void*>(base+0x4e8b70);
    void* actual=nullptr;
    static const unsigned char signature[16]={
        0x48,0x89,0x5c,0x24,0x08,0x57,0x48,0x83,
        0xec,0x20,0x48,0x8b,0xda,0x48,0x8b,0xf9};
    unsigned char bytes[16]{};
    if (!read(reinterpret_cast<uintptr_t>(slot),actual)
        || actual!=expected_method
        || !read(base+0x4e8b70,bytes)
        || memcmp(bytes,signature,sizeof(bytes))) {
        InterlockedExchange(&lifecycle_vassalization_field_reader_install_state,-1);
        return false;
    }
    bridge_field_reader_original=actual;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) {
        InterlockedExchange(&lifecycle_vassalization_field_reader_install_state,-1);
        return false;
    }
    void* hook=reinterpret_cast<void*>(&bridge_field_reader_stub);
    bool installed=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),hook,actual)==actual;
    if (!VirtualProtect(slot,8,protection,&ignored)) {
        bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(slot),actual,hook)==hook;
        bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete
            || !reverted || !restored;
        InterlockedExchange(&lifecycle_vassalization_field_reader_install_state,-1);
        return false;
    }
    if (!installed) {
        InterlockedExchange(&lifecycle_vassalization_field_reader_install_state,-1);
        return false;
    }
    InterlockedExchange(&lifecycle_vassalization_field_reader_install_state,2);
    return true;
}

// Vassalization uses the common destructor/wrapper slots and its own native
// clone implementation.  The exact +0x00/+0x40/+0xb0 originals are checked
// by lifecycle_install_small_action before any slot is published.
static bool lifecycle_install_vassalization() {
    return lifecycle_install_small_action(&lifecycle_vassalization_install_state,
        lifecycle_vassalization_vtable_rva,lifecycle_vassalization_clone_rva,
        &lifecycle_vassalization_clone_original);
}

static bool lifecycle_install_insult() {
    return lifecycle_install_small_action(&lifecycle_insult_install_state,
        lifecycle_insult_vtable_rva,lifecycle_insult_clone_rva,
        &lifecycle_insult_clone_original,lifecycle_insult_destructor_rva);
}

static bool lifecycle_install_peace() {
    return lifecycle_install_small_action(&lifecycle_peace_install_state,
        lifecycle_peace_vtable_rva,0x59ba70,&lifecycle_peace_clone_original,0x598b90);
}

static bool lifecycle_rollback_declarewar_slots(unsigned char* table,unsigned changed) {
    struct Slot { unsigned offset; void* expected; void* replacement; } slots[3]={
        {0x00,reinterpret_cast<void*>(base+lifecycle_declarewar_destructor_rva),
            reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {0x40,reinterpret_cast<void*>(base+lifecycle_wrapper_rva),
            reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {0xb0,reinterpret_cast<void*>(base+lifecycle_declarewar_clone_rva),
            reinterpret_cast<void*>(&lifecycle_clone_observe)}
    };
    bool complete=true;
    for (unsigned index=0;index<changed;++index) {
        void* previous=InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(table+slots[index].offset),
            slots[index].expected,slots[index].replacement);
        complete=(previous==slots[index].replacement || previous==slots[index].expected)
            && complete;
    }
    return complete;
}

// Declare War has a distinct destructor and clone method.  Its wrapper slot
// is the same native 4e9960 method used by the other diplomatic actions, but
// the family-specific originals are stored independently and each native
// method is forwarded exactly once.
[[maybe_unused]] static bool lifecycle_install_declarewar() {
    LONG state=InterlockedCompareExchange(&lifecycle_declarewar_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;

    unsigned char* table=reinterpret_cast<unsigned char*>(
        base+lifecycle_declarewar_vtable_rva);
    void* expected_destructor=nullptr;
    void* expected_wrapper=nullptr;
    void* expected_clone=nullptr;
    bool identities=read(reinterpret_cast<uintptr_t>(table+0x00),expected_destructor)
        && read(reinterpret_cast<uintptr_t>(table+0x40),expected_wrapper)
        && read(reinterpret_cast<uintptr_t>(table+0xb0),expected_clone)
        && expected_destructor==reinterpret_cast<void*>(base+lifecycle_declarewar_destructor_rva)
        && expected_wrapper==reinterpret_cast<void*>(base+lifecycle_wrapper_rva)
        && expected_clone==reinterpret_cast<void*>(base+lifecycle_declarewar_clone_rva);
    if (!identities) {
        InterlockedExchange(&lifecycle_declarewar_install_state,-1);
        return false;
    }
    lifecycle_declarewar_destructor_original=
        reinterpret_cast<LifecycleDestructorMethod>(expected_destructor);
    lifecycle_declarewar_clone_original=
        reinterpret_cast<LifecycleCloneMethod>(expected_clone);
    if (!lifecycle_wrapper_original)
        lifecycle_wrapper_original=reinterpret_cast<LifecycleWrapperMethod>(expected_wrapper);
    if (lifecycle_wrapper_original!=reinterpret_cast<LifecycleWrapperMethod>(expected_wrapper)) {
        InterlockedExchange(&lifecycle_declarewar_install_state,-1);
        return false;
    }

    DWORD protection=0,ignored=0;
    if (!VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&protection)) {
        InterlockedExchange(&lifecycle_declarewar_install_state,-1);
        return false;
    }
    struct Slot { unsigned offset; void* expected; void* replacement; } slots[3]={
        {0x00,expected_destructor,reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {0x40,expected_wrapper,reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {0xb0,expected_clone,reinterpret_cast<void*>(&lifecycle_clone_observe)}
    };
    unsigned changed=0;
    bool installed=true;
    for (const auto& slot:slots) {
        void* previous=InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(table+slot.offset),
            slot.replacement,slot.expected);
        if (previous!=slot.expected) { installed=false; break; }
        ++changed;
    }
    bool restored=VirtualProtect(table,lifecycle_slot_range,protection,&ignored)!=FALSE;
    if (!installed || !restored) {
        DWORD rollback_protection=0;
        bool rollback=VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,
            &rollback_protection)!=FALSE;
        if (rollback) {
            rollback=lifecycle_rollback_declarewar_slots(table,changed);
            rollback=VirtualProtect(table,lifecycle_slot_range,protection,&ignored)!=FALSE
                && rollback;
        }
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !rollback;
        InterlockedExchange(&lifecycle_declarewar_install_state,-1);
        return false;
    }
    InterlockedExchange(&lifecycle_declarewar_install_state,2);
    return true;
}


// The Royal field-reader method has a separately captured original and a
// separate assembly tail-jump.  Its unknown extra arguments are preserved by
// the existing full volatile-register/stack-frame shim, so this callback does
// not guess or truncate the native ABI.
[[maybe_unused]] static bool lifecycle_install_royal_field_reader() {
    LONG state=InterlockedCompareExchange(&lifecycle_royal_field_reader_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;

    void** slot=reinterpret_cast<void**>(base+lifecycle_royal_vtable_rva+0x20);
    void* expected_method=reinterpret_cast<void*>(base+lifecycle_royal_field_reader_rva);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual) || actual!=expected_method) {
        InterlockedExchange(&lifecycle_royal_field_reader_install_state,-1);
        return false;
    }
    bridge_royal_field_reader_original=actual;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) {
        InterlockedExchange(&lifecycle_royal_field_reader_install_state,-1);
        return false;
    }
    void* hook=reinterpret_cast<void*>(&bridge_royal_field_reader_stub);
    bool installed=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),hook,actual)==actual;
    if (!VirtualProtect(slot,8,protection,&ignored)) {
        bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(slot),actual,hook)==hook;
        bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete || !reverted || !restored;
        InterlockedExchange(&lifecycle_royal_field_reader_install_state,-1);
        return false;
    }
    if (!installed) {
        InterlockedExchange(&lifecycle_royal_field_reader_install_state,-1);
        return false;
    }
    InterlockedExchange(&lifecycle_royal_field_reader_install_state,2);
    return true;
}

// Declare War's +0x20 field-reader method is a separate native entry.  The
// assembly shim preserves the full volatile register/stack surface and
// tail-jumps to this family-specific original after the shared observation
// callback, so no Alliance/Royal ABI is reused.
[[maybe_unused]] static bool lifecycle_install_declarewar_field_reader() {
    LONG state=InterlockedCompareExchange(
        &lifecycle_declarewar_field_reader_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;

    void** slot=reinterpret_cast<void**>(
        base+lifecycle_declarewar_vtable_rva+0x20);
    void* expected_method=reinterpret_cast<void*>(base+lifecycle_declarewar_field_reader_rva);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual)
        || actual!=expected_method) {
        InterlockedExchange(&lifecycle_declarewar_field_reader_install_state,-1);
        return false;
    }
    bridge_declarewar_field_reader_original=actual;
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) {
        InterlockedExchange(&lifecycle_declarewar_field_reader_install_state,-1);
        return false;
    }
    void* hook=reinterpret_cast<void*>(&bridge_declarewar_field_reader_stub);
    bool installed=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),hook,actual)==actual;
    bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    if (!restored) {
        bool reverted=!installed || InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(slot),actual,hook)==hook;
        DWORD retry_protection=0,retry_ignored=0;
        bool retry=VirtualProtect(slot,8,PAGE_READWRITE,&retry_protection)
            && VirtualProtect(slot,8,protection,&retry_ignored);
        lifecycle_rollback_incomplete=lifecycle_rollback_incomplete
            || !reverted || !retry;
        InterlockedExchange(&lifecycle_declarewar_field_reader_install_state,-1);
        return false;
    }
    if (!installed) {
        InterlockedExchange(&lifecycle_declarewar_field_reader_install_state,-1);
        return false;
    }
    InterlockedExchange(&lifecycle_declarewar_field_reader_install_state,2);
    return true;
}

// These two narrow rollback helpers are exposed to the outer installer in
// diplomacy-observer-v10.cpp. They restore only the Declare War slots and
// accept an already-restored slot, so a later family failure cannot touch a
// different action table.
[[maybe_unused]] static bool lifecycle_rollback_declarewar() {
    LONG state=InterlockedCompareExchange(&lifecycle_declarewar_install_state,0,0);
    if (state==0) return true;
    unsigned char* table=reinterpret_cast<unsigned char*>(
        base+lifecycle_declarewar_vtable_rva);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&protection)) {
        lifecycle_rollback_incomplete=true;
        return false;
    }
    bool complete=lifecycle_rollback_declarewar_slots(table,3);
    bool restored=VirtualProtect(table,lifecycle_slot_range,protection,&ignored)!=FALSE;
    complete=complete && restored;
    if (complete) InterlockedExchange(&lifecycle_declarewar_install_state,0);
    else lifecycle_rollback_incomplete=true;
    return complete;
}

[[maybe_unused]] static bool lifecycle_rollback_declarewar_field_reader() {
    LONG state=InterlockedCompareExchange(
        &lifecycle_declarewar_field_reader_install_state,0,0);
    if (state==0) return true;
    void** slot=reinterpret_cast<void**>(
        base+lifecycle_declarewar_vtable_rva+0x20);
    void* actual=nullptr;
    if (!read(reinterpret_cast<uintptr_t>(slot),actual)) {
        lifecycle_rollback_incomplete=true;
        return false;
    }
    void* expected=reinterpret_cast<void*>(base+lifecycle_declarewar_field_reader_rva);
    void* hook=reinterpret_cast<void*>(&bridge_declarewar_field_reader_stub);
    if (actual==expected) {
        InterlockedExchange(&lifecycle_declarewar_field_reader_install_state,0);
        return true;
    }
    if (actual!=hook) {
        lifecycle_rollback_incomplete=true;
        return false;
    }
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) {
        lifecycle_rollback_incomplete=true;
        return false;
    }
    void* previous=InterlockedCompareExchangePointer(
        reinterpret_cast<void* volatile*>(slot),expected,hook);
    bool swapped=previous==hook || previous==expected;
    bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    if (swapped && restored) InterlockedExchange(
        &lifecycle_declarewar_field_reader_install_state,0);
    else lifecycle_rollback_incomplete=true;
    return swapped && restored;
}

#include "peace-lifecycle-hooks.inc"

static void field_read_flush() {
    for (unsigned i=0;i<32;++i) {
        AllianceFieldReadEvent event{};
        AcquireSRWLockExclusive(&field_read_lock);
        if (!field_read_size) { ReleaseSRWLockExclusive(&field_read_lock); break; }
        event=field_read_events[field_read_head];
        field_read_events[field_read_head]=AllianceFieldReadEvent{};
        field_read_head=(field_read_head+1)%128; --field_read_size;
        ReleaseSRWLockExclusive(&field_read_lock);
        char source[1200]{},input[33]{},message[2400]{};
        lifecycle_shape_json(source,sizeof(source),event.source);
        if (event.input_readable) for (unsigned byte=0;byte<16;++byte) snprintf(input+byte*2,3,"%02x",event.input16[byte]);
        unsigned long long caller_rva=event.caller_return>=base+0x1000 && event.caller_return<base+0x1b66000
            ? static_cast<unsigned long long>(event.caller_return-base):0;
        snprintf(message,sizeof(message),"{\"event\":\"native_alliance_field_read_begin\",\"session_id\":\"%lu-%llx\",\"callback_sequence\":%llu,\"thread\":%lu,\"field_id\":%u,\"context\":\"0x%llx\",\"context_word_readable\":%s,\"context_first_word\":\"0x%llx\",\"input16_readable\":%s,\"input16_hex\":\"%s\",\"caller_return_rva\":\"0x%llx\",\"source\":%s,\"native_forward_count_by_hook_contract\":1,\"native_return_observed\":false,\"network_source_verified\":false,\"authorization\":\"unknown\",\"business_result\":\"unknown\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(event.callback_sequence),static_cast<unsigned long>(event.thread),event.field_id,
            static_cast<unsigned long long>(event.context),event.context_word_readable?"true":"false",
            static_cast<unsigned long long>(event.context_first_word),event.input_readable?"true":"false",input,caller_rva,source);
        line(message);
    }
    LONG dropped=InterlockedExchange(&field_read_dropped,0);
    if (dropped) {
        char message[180];
        snprintf(message,sizeof(message),"{\"event\":\"native_alliance_field_read_drop\",\"dropped\":%ld,\"complete\":false}\n",static_cast<long>(dropped));
        line(message);
    }
}

static void lifecycle_emit(const LifecycleEvent& event) {
    char source[1200]{},target[1200]{};
    lifecycle_shape_json(source,sizeof(source),event.source);
    lifecycle_shape_json(target,sizeof(target),event.target);
    char message[5000];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_lifecycle\",\"session_id\":\"%lu-%llx\",\"kind\":\"%s\",\"sequence\":%llu,\"source_event_id\":%llu,\"target_event_id\":%llu,\"thread\":%lu,\"caller_return_rva\":\"0x%llx\",\"query_id\":\"%s\",\"request_id\":null,\"authorization\":\"unknown\",\"business_result\":\"unknown\",\"native_forward_count_by_hook_contract\":1,\"native_return_observed\":%s,\"source\":%s,\"target\":%s,\"native_result\":\"0x%llx\",\"out_pointer\":\"0x%llx\",\"out_value\":\"0x%llx\",\"wrapper_vtable_rva\":\"0x%llx\",\"wrapper_identity\":%s,\"wrapper_readable\":%s,\"wrapper_action\":\"0x%llx\",\"origin48\":%u,\"seq4c\":%u,\"rawflag4a\":%u,\"wrapper_prefix_readable\":%s,\"wrapper_raw10\":%u,\"wrapper_raw38\":%d,\"wrapper_raw3c\":%d,\"wrapper_raw40\":%u,\"wrapper_raw44\":%d,\"native_flags\":%u,\"result_readable\":%s}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
        lifecycle_kind_name(event.kind),static_cast<unsigned long long>(event.sequence),
        static_cast<unsigned long long>(event.source_event_id),static_cast<unsigned long long>(event.target_event_id),
        static_cast<unsigned long>(event.thread),
        (event.caller_return>=base && event.caller_return<base+0x2000000)
            ? static_cast<unsigned long long>(event.caller_return-base) : 0,event.query_id,
        (event.kind==lifecycle_clone_event || event.kind==lifecycle_wrapper_event || event.kind==lifecycle_destructor_return_event)?"true":"false",source,target,
        static_cast<unsigned long long>(event.native_result),static_cast<unsigned long long>(event.out_pointer),
        static_cast<unsigned long long>(event.out_value),
        (event.wrapper_vtable>=base && event.wrapper_vtable<base+0x2000000)
            ? static_cast<unsigned long long>(event.wrapper_vtable-base) : 0,
        event.wrapper_identity?"true":"false",event.wrapper_readable?"true":"false",
        static_cast<unsigned long long>(event.wrapper_action),static_cast<unsigned>(event.origin48),
        event.seq4c,static_cast<unsigned>(event.rawflag4a),event.wrapper_prefix_readable?"true":"false",
        static_cast<unsigned>(event.wrapper_raw10),event.wrapper_raw38,event.wrapper_raw3c,
        static_cast<unsigned>(event.wrapper_raw40),event.wrapper_raw44,event.native_flags,
        event.result_readable?"true":"false");
    line(message);
}

static void lifecycle_flush() {
    // A drop report gets one of the 32 output slots.  A drop that races this
    // snapshot is reported on the next frame, so this function never writes
    // more than 32 JSONL records per call.
    LONG pending=InterlockedCompareExchange(&lifecycle_dropped,0,0);
    unsigned event_limit=pending?31:32;
    unsigned emitted=0;
    for (;emitted<event_limit;++emitted) {
        LifecycleEvent event{};
        AcquireSRWLockExclusive(&lifecycle_lock);
        if (!lifecycle_size) {
            ReleaseSRWLockExclusive(&lifecycle_lock);
            break;
        }
        event=lifecycle_events[lifecycle_head];
        lifecycle_events[lifecycle_head]=LifecycleEvent{};
        lifecycle_head=(lifecycle_head+1)%128;
        --lifecycle_size;
        ReleaseSRWLockExclusive(&lifecycle_lock);
        lifecycle_emit(event);
    }
    if (emitted<32) {
        LONG dropped=InterlockedExchange(&lifecycle_dropped,0);
        if (dropped) {
            char message[240];
            snprintf(message,sizeof(message),
                "{\"event\":\"native_alliance_lifecycle_drop\",\"dropped\":%ld,\"authorization\":\"unknown\",\"business_result\":\"unknown\"}\n",
                static_cast<long>(dropped));
            line(message);
        }
    }
}

static bool lifecycle_rollback_slots(void** table,unsigned changed) {
    struct Slot { unsigned offset; void* expected; void* replacement; } slots[3]={
        {0x00,reinterpret_cast<void*>(base+lifecycle_destructor_rva),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {0x40,reinterpret_cast<void*>(base+lifecycle_wrapper_rva),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {0xb0,reinterpret_cast<void*>(base+lifecycle_clone_rva),reinterpret_cast<void*>(&lifecycle_clone_observe)}
    };
    bool ok=true;
    for (unsigned i=0;i<changed;++i) {
        void* previous=InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(reinterpret_cast<unsigned char*>(table)+slots[i].offset),
            slots[i].expected,slots[i].replacement);
        if (previous!=slots[i].replacement && previous!=slots[i].expected) ok=false;
    }
    return ok;
}

static bool lifecycle_install() {
    LONG state=InterlockedCompareExchange(&lifecycle_install_state,1,0);
    if (state==2) return true;
    if (state!=0) return false;

    void** table=reinterpret_cast<void**>(base+lifecycle_alliance_vtable_rva);
    void* expected_destructor=nullptr;
    void* expected_wrapper=nullptr;
    void* expected_clone=nullptr;
    bool identities=read(reinterpret_cast<uintptr_t>(table+0x00/sizeof(void*)),expected_destructor)
        && read(reinterpret_cast<uintptr_t>(table+0x40/sizeof(void*)),expected_wrapper)
        && read(reinterpret_cast<uintptr_t>(table+0xb0/sizeof(void*)),expected_clone)
        && expected_destructor==reinterpret_cast<void*>(base+lifecycle_destructor_rva)
        && expected_wrapper==reinterpret_cast<void*>(base+lifecycle_wrapper_rva)
        && expected_clone==reinterpret_cast<void*>(base+lifecycle_clone_rva);
    if (!identities) {
        InterlockedExchange(&lifecycle_install_state,0);
        return false;
    }
    lifecycle_destructor_original=reinterpret_cast<LifecycleDestructorMethod>(expected_destructor);
    lifecycle_wrapper_original=reinterpret_cast<LifecycleWrapperMethod>(expected_wrapper);
    lifecycle_clone_original=reinterpret_cast<LifecycleCloneMethod>(expected_clone);

    // Each aligned vtable exchange is independently safe: originals are
    // initialized first and every observer forwards the exact native call.
    // Full-family failure is rolled back by the outer installer. No other
    // thread is suspended for these pointer-only publications.
    DWORD original_protection=0;
    if (!VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&original_protection)) {
        InterlockedExchange(&lifecycle_install_state,-1);
        return false;
    }
    struct Slot { unsigned offset; void* expected; void* replacement; } slots[3]={
        {0x00,expected_destructor,reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {0x40,expected_wrapper,reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {0xb0,expected_clone,reinterpret_cast<void*>(&lifecycle_clone_observe)}
    };
    unsigned changed=0;
    bool installed=true;
    for (unsigned i=0;i<3;++i) {
        void* previous=InterlockedCompareExchangePointer(
            reinterpret_cast<void* volatile*>(reinterpret_cast<unsigned char*>(table)+slots[i].offset),
            slots[i].replacement,slots[i].expected);
        if (previous!=slots[i].expected) { installed=false; break; }
        ++changed;
    }
    DWORD ignored=0;
    bool protection_restored=VirtualProtect(table,lifecycle_slot_range,original_protection,&ignored)!=FALSE;
    if (!installed || !protection_restored) {
        // If restoring the original protection failed, make one bounded
        // writable attempt so our own slots can still be rolled back.  No
        // native function is called in this failure path.
        DWORD temporary=0;
        bool rollback=VirtualProtect(table,lifecycle_slot_range,PAGE_READWRITE,&temporary)!=FALSE;
        if (rollback) {
            rollback=lifecycle_rollback_slots(table,changed);
            rollback=VirtualProtect(table,lifecycle_slot_range,original_protection,&ignored)!=FALSE && rollback;
        }
        lifecycle_rollback_incomplete=!rollback;
        // Originals must remain valid even if rollback fails or another
        // thread already captured a hook pointer. Never create a null-forward
        // path after a replacement may have been published.
        InterlockedExchange(&lifecycle_install_state,-1);
        return false;
    }
    InterlockedExchange(&lifecycle_install_state,2);
    return true;
}
