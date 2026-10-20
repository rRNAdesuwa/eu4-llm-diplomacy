// Independent common-control/command-observation build. Legacy source and DLL
// remain intact. All observed commands continue through the original executor.
#define BRIDGE_TRACE_PEACE_RESPONSES 1
#define BRIDGE_TRACE_COMMAND_EXECUTION 1
#define bridge_response_observe observer_legacy_response
#define bridge_frame_tick observer_legacy_frame
#define BridgeStart ObserverControlStart
#include "control-probe.cpp"
#undef bridge_response_observe
#undef bridge_frame_tick
#undef BridgeStart

struct ObservedCommand {
    DWORD thread;
    uintptr_t command,action,action_vtable;
    unsigned char protocol_flags;
    int32_t raw38,raw3c,raw44;
    uint16_t raw40;
    unsigned char raw10;
    bool prefix_readable;
    uint16_t origin;
    uint32_t sequence;
    bool readable;
    uint64_t alliance_actor,alliance_recipient;
    int32_t alliance_state;
    unsigned char alliance_variant;
    bool alliance_identified;
    bool royal_marriage;
    bool improve_relations;
    bool spy_network;
    bool guarantee;
    bool support_independence;
    bool military_access;
    bool vassalization;
    bool favor_gold;
    bool favor_trust;
    bool favor_men;
    bool curry_favors;
    uint64_t callback_sequence;
    char alliance_shape_json[1200];
};
static SRWLOCK observation_lock=SRWLOCK_INIT;
static ObservedCommand observation_events[128]{};
static unsigned observation_head=0,observation_size=0;
static volatile LONG observation_dropped=0;
static uint64_t observation_creation=0;
static uint64_t observation_sequence=0;
static volatile LONG64 observation_callback_sequence=0;
static volatile LONG observation_frame_inside=0;
static ULONGLONG observation_last_health=0;
static void* observation_alliance_validity_original=nullptr;
struct ObservedAllianceRule {
    uint64_t actor,recipient;
    DWORD thread;
    int32_t state_before,state_after;
    unsigned char variant;
    bool result,state_read;
    char query_id[65];
};
static SRWLOCK alliance_rule_lock=SRWLOCK_INIT;
static ObservedAllianceRule alliance_rule_events[128]{};
static unsigned alliance_rule_head=0,alliance_rule_size=0;
static volatile LONG alliance_rule_dropped=0;
static const char* observation_active_query=nullptr;

static bool observation_country_handle(uint64_t handle) {
    uintptr_t database=0,array=0,country=0; uint64_t actual=0;
    unsigned slot=static_cast<unsigned>((handle>>32)&0xffff);
    return slot<4096 && read(base+0x233d8b0,database) && read(database+0x118,array)
        && read(array+static_cast<uintptr_t>(slot)*8,country) && read(country+0x20,actual) && actual==handle;
}
static bool observation_alliance_validity(void* object,void* diagnostic,unsigned char flags) {
    ObservedAllianceRule event{};
    uintptr_t address=reinterpret_cast<uintptr_t>(object),vtable=0;
    int32_t discriminator=0;
    bool identified=read(address,vtable) && vtable==base+0x1c80720
        && read(address+8,discriminator) && discriminator==0x165
        && read(address+0x10,event.actor) && observation_country_handle(event.actor)
        && read(address+0x20,event.recipient) && observation_country_handle(event.recipient)
        && read(address+0x38,event.variant) && event.variant<=1;
    // Keep high-frequency observations bounded to the experiment countries.
    uint32_t actor=static_cast<uint32_t>(event.actor&0xffffff);
    uint32_t recipient=static_cast<uint32_t>(event.recipient&0xffffff);
    identified=identified && (actor==0x415246 || recipient==0x415246 || actor==0x524f50 || recipient==0x524f50 || actor==0x564153 || recipient==0x564153);
    event.thread=GetCurrentThreadId();
    if (event.thread==frame_thread && observation_active_query)
        strcpy(event.query_id,observation_active_query);
    event.state_read=identified && read(address+0x34,event.state_before);
    using NativeValidity=bool (*)(void*,void*,unsigned char);
    // The original method is called exactly once, with the exact arguments.
    // No new evaluation and no forced result is introduced by observation.
    bool result=reinterpret_cast<NativeValidity>(observation_alliance_validity_original)(object,diagnostic,flags);
    if (identified) {
        event.result=result;
        event.state_read=read(address+0x34,event.state_after) && event.state_read;
        if (TryAcquireSRWLockExclusive(&alliance_rule_lock)) {
            if (alliance_rule_size<128) {
                alliance_rule_events[(alliance_rule_head+alliance_rule_size)%128]=event;
                ++alliance_rule_size;
            } else InterlockedIncrement(&alliance_rule_dropped);
            ReleaseSRWLockExclusive(&alliance_rule_lock);
        } else InterlockedIncrement(&alliance_rule_dropped);
    }
    return result;
}

static bool observation_install_alliance_rule() {
    auto slot=reinterpret_cast<void**>(base+0x1c80720+0x80);
    uintptr_t original=0;
    if (!read(reinterpret_cast<uintptr_t>(slot),original) || original!=base+0x511d90) return false;
    observation_alliance_validity_original=reinterpret_cast<void*>(original);
    DWORD old=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&old)) return false;
    void* previous=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),
        reinterpret_cast<void*>(&observation_alliance_validity),observation_alliance_validity_original);
    bool patched=previous==observation_alliance_validity_original;
    if (!VirtualProtect(slot,8,old,&ignored)) {
        if (patched) InterlockedExchangePointer(reinterpret_cast<void* volatile*>(slot),observation_alliance_validity_original);
        VirtualProtect(slot,8,old,&ignored);
        return false;
    }
    return patched;
}

#include "alliance-lifecycle.inc"
#include "rival-command-observer.inc"
#include "alliance-entry-observer.inc"
#include "alliance-protocol-observer.inc"
#include "alliance-transport.inc"
#include "peace-effects.h"
#include "peace-execution-wire.h"
#include "alliance-query.inc"
#include "alliance-authority-ledger.h"
#include "alliance-execution-wire.h"
#include "alliance-inbound-response-wire.h"
#include "alliance-inbound.inc"
#include "inbound-pending-recovery.inc"
#include "alliance-execution.inc"
#include "peace-handler-authority.inc"
#include "peace-receiver-observer.inc"
static int rival_execution_begin(void* object,unsigned kind) noexcept;
static void rival_execution_finish(unsigned binding) noexcept;
#include "rival-authority.inc"
#include "rival-execution.inc"
#include "vassal-test-context.inc"
#include "religion-war-context.inc"
#include "vassal-inbound-test-context.inc"

static bool observation_rollback_family() {
    struct Slot { uintptr_t address; void* original; void* replacement; } slots[]={
        {base+0x1c80720,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c80720+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c80720+0xb0,reinterpret_cast<void*>(base+0x513090),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c80720+0x80,reinterpret_cast<void*>(base+0x511d90),reinterpret_cast<void*>(&observation_alliance_validity)},
        {base+0x1c80720+0x20,reinterpret_cast<void*>(base+0x4e8b70),reinterpret_cast<void*>(&bridge_field_reader_stub)},
        {base+0x1c80ab0,reinterpret_cast<void*>(base+0x4ed5e0),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c80ab0+0x20,reinterpret_cast<void*>(base+0x4f0900),reinterpret_cast<void*>(&bridge_royal_field_reader_stub)},
        {base+0x1c80ab0+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c80ab0+0xb0,reinterpret_cast<void*>(base+0x4f0800),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7dd68,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7dd68+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7dd68+0xb0,reinterpret_cast<void*>(base+0x574b50),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7cc48+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7cc48+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7cc48+0xb0,reinterpret_cast<void*>(base+0x586230),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7fe50+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7fe50+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7fe50+0xb0,reinterpret_cast<void*>(base+0x5224f0),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c805f0+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c805f0+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c805f0+0xb0,reinterpret_cast<void*>(base+0x50f0c0),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7fb70+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7fb70+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7fb70+0xb0,reinterpret_cast<void*>(base+0x525da0),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7fd20+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7fd20+0x20,reinterpret_cast<void*>(base+0x4e8b70),reinterpret_cast<void*>(&bridge_field_reader_stub)},
        {base+0x1c7fd20+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7fd20+0xb0,reinterpret_cast<void*>(base+0x51fa30),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        // Favor-for-gold uses the common lifecycle hooks at +0x00/+0x40 and
        // its confirmed clone at +0xb0.  Its response-choice gate is a
        // separate inbound hook at +0xd0; rollback for that hook is handled
        // by inbound_rollback(), never by the lifecycle slots below.
        {base+0x1c80980+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c80980+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c80980+0xb0,reinterpret_cast<void*>(base+0x4f5c00),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c80c60+0x00,reinterpret_cast<void*>(base+0x129500),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c80c60+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c80c60+0xb0,reinterpret_cast<void*>(base+0x4fe770),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c80ff0+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c80ff0+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c80ff0+0xb0,reinterpret_cast<void*>(base+0x4f8420),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7aef8+0x00,reinterpret_cast<void*>(base+0x129450),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7aef8+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7aef8+0xb0,reinterpret_cast<void*>(base+0x5ae2e0),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7f6b0+0x00,reinterpret_cast<void*>(base+0x129500),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7f6b0+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7f6b0+0xb0,reinterpret_cast<void*>(base+0x538e50),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c7b840+0x00,reinterpret_cast<void*>(base+0x598b90),reinterpret_cast<void*>(&lifecycle_destructor_observe)},
        {base+0x1c7b840+0x40,reinterpret_cast<void*>(base+0x4e9960),reinterpret_cast<void*>(&lifecycle_wrapper_observe)},
        {base+0x1c7b840+0xb0,reinterpret_cast<void*>(base+0x59ba70),reinterpret_cast<void*>(&lifecycle_clone_observe)},
        {base+0x1c814b0+0x10,reinterpret_cast<void*>(base+0x4e8470),reinterpret_cast<void*>(&bridge_serializer_stub)},
        {base+0x1c814b0+0x20,reinterpret_cast<void*>(base+0x4e84c0),reinterpret_cast<void*>(&bridge_wrapper_reader_stub)},
        {base+0x1c814b0+0x60,reinterpret_cast<void*>(base+0x4e8550),reinterpret_cast<void*>(&bridge_wrapper_clone_stub)}
    };
    bool complete=true;
    complete=lifecycle_rollback_declarewar_field_reader() && complete;
    complete=lifecycle_rollback_declarewar() && complete;
    complete=lifecycle_rollback_peace_field_reader() && complete;
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
    complete=bridge_alliance_reason_metadata_rollback() && complete;
#endif
    for (const auto& slot:slots) {
        void* current=nullptr;
        if (!read(slot.address,current)) { complete=false; continue; }
        if (current==slot.original) continue;
        if (current!=slot.replacement) { complete=false; continue; }
        DWORD protection=0,ignored=0;
        if (!VirtualProtect(reinterpret_cast<void*>(slot.address),8,PAGE_READWRITE,&protection)) { complete=false; continue; }
        void* previous=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot.address),slot.original,slot.replacement);
        complete=(previous==slot.replacement || previous==slot.original) && complete;
        complete=VirtualProtect(reinterpret_cast<void*>(slot.address),8,protection,&ignored)!=FALSE && complete;
    }
    complete=direct_break_rollback() && complete;
    complete=inbound_rollback() && complete;
    complete=rival_authority_rollback() && complete;
    rival_execution_detail::enabled=false;
    complete=rival_command_observer_rollback() && complete;
    complete=execution_rollback() && complete;
    complete=peace_handler_authority_rollback() && complete;
    complete=peace_receiver_observer_rollback() && complete;
    complete=transport_rollback() && complete;
    complete=control_rollback_hooks() && complete;
    // Original pointers/trampolines remain alive after publication: a native
    // thread may already have fetched a replacement virtual-method pointer.
    return complete;
}

extern "C" int bridge_response_observe(void* value) {
    ObservedCommand event{};
    event.thread=GetCurrentThreadId();
    event.command=reinterpret_cast<uintptr_t>(value);
    event.callback_sequence=static_cast<uint64_t>(InterlockedIncrement64(&observation_callback_sequence));
    uintptr_t vtable=0;
    // This is the verified generic diplomatic command, not an assumed layout
    // for each action. Unknown action payloads are never interpreted here.
    event.readable=read(event.command,vtable) && vtable==base+0x1c814b0
        && read(event.command+0x50,event.action) && read(event.action,event.action_vtable)
        && read(event.command+0x48,event.origin) && read(event.command+0x4a,event.protocol_flags)
        && read(event.command+0x4c,event.sequence);
    event.prefix_readable=event.readable && read(event.command+0x10,event.raw10)
        && read(event.command+0x38,event.raw38) && read(event.command+0x3c,event.raw3c)
        && read(event.command+0x40,event.raw40) && read(event.command+0x44,event.raw44);
    if (event.readable && (event.action_vtable==base+0x1c80720
        || event.action_vtable==base+0x1c80ab0 || event.action_vtable==base+0x1c7dd68
        || event.action_vtable==base+0x1c7cc48 || event.action_vtable==base+0x1c7fe50 || event.action_vtable==base+0x1c805f0
        || event.action_vtable==base+0x1c7fb70 || event.action_vtable==base+0x1c7fd20
        || event.action_vtable==base+0x1c80980 || event.action_vtable==base+0x1c80c60
        || event.action_vtable==base+0x1c80ff0 || event.action_vtable==base+0x1c7aef8)) {
        LifecycleActionShape shape=lifecycle_capture_shape(reinterpret_cast<void*>(event.action));
        event.alliance_identified=shape.matched && shape.tracked;
        if (event.alliance_identified) {
            event.alliance_actor=shape.actor10;
            event.alliance_recipient=shape.recipient20;
            event.alliance_state=shape.state34;
            event.alliance_variant=shape.variant38;
            event.royal_marriage=shape.royal_marriage;
            event.improve_relations=shape.improve_relations;
            event.spy_network=shape.spy_network;
            event.guarantee=shape.guarantee;
            event.support_independence=shape.support_independence;
            event.military_access=shape.military_access;
            event.vassalization=shape.vassalization;
            event.favor_gold=shape.favor_gold;
            event.favor_trust=shape.favor_trust;
            event.favor_men=shape.favor_men;
            event.curry_favors=shape.curry_favors;
            lifecycle_shape_json(event.alliance_shape_json,sizeof(event.alliance_shape_json),shape);
        }
    }
    if (!TryAcquireSRWLockExclusive(&observation_lock)) {
        InterlockedIncrement(&observation_dropped); return 1;
    }
    if (observation_size<128) {
        observation_events[(observation_head+observation_size)%128]=event;
        ++observation_size;
    } else InterlockedIncrement(&observation_dropped);
    ReleaseSRWLockExclusive(&observation_lock);
    // The assembly stub restores every register and calls the original exactly
    // once. Observation cannot turn an AI decision into an authorized choice.
    return 1;
}

static void observation_flush() {
    // Bounded and reusable rather than a lifetime-only 64-event array.
    for (unsigned i=0;i<32;++i) {
        ObservedCommand event{};
        AcquireSRWLockExclusive(&observation_lock);
        if (!observation_size) { ReleaseSRWLockExclusive(&observation_lock); break; }
        event=observation_events[observation_head];
        observation_head=(observation_head+1)%128; --observation_size;
        ReleaseSRWLockExclusive(&observation_lock);
        char message[600];
        snprintf(message,sizeof(message),
            "{\"event\":\"diplomatic_command_observed\",\"version\":10,\"pid\":%lu,\"session_id\":\"%lu-%llx\",\"event_sequence\":%llu,\"thread\":%lu,\"readable\":%s,\"command\":\"0x%llx\",\"action\":\"0x%llx\",\"action_vtable_rva\":\"0x%llx\",\"origin\":%u,\"protocol_sequence\":%u,\"protocol_flags\":%u,\"forward_to_original\":true,\"business_result\":\"unknown\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),static_cast<unsigned long long>(++observation_sequence),
            static_cast<unsigned long>(event.thread),event.readable?"true":"false",
            static_cast<unsigned long long>(event.command),static_cast<unsigned long long>(event.action),
            static_cast<unsigned long long>(event.action_vtable>=base?event.action_vtable-base:0),
            event.origin,event.sequence,event.protocol_flags);
        line(message);
        if (event.alliance_identified) {
            char alliance[2400];
            snprintf(alliance,sizeof(alliance),"{\"event\":\"native_alliance_command_entry_observed\",\"session_id\":\"%lu-%llx\",\"event_sequence\":%llu,\"callback_sequence\":%llu,\"protocol_sequence\":%u,\"origin\":%u,\"protocol_flags\":%u,\"command\":\"0x%llx\",\"action\":\"0x%llx\",\"readable\":true,\"prefix_readable\":%s,\"raw10\":%u,\"raw38\":%d,\"raw3c\":%d,\"raw40\":%u,\"raw44\":%d,\"source\":%s,\"actor_field\":\"%c%c%c\",\"recipient_field\":\"%c%c%c\",\"action_id\":\"%s\",\"state_raw\":%d,\"decision_country\":null,\"business_result\":\"unknown\",\"rule_result\":\"unknown\",\"complete\":false}\n",
                static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
                static_cast<unsigned long long>(observation_sequence),static_cast<unsigned long long>(event.callback_sequence),
                event.sequence,event.origin,event.protocol_flags,static_cast<unsigned long long>(event.command),
                static_cast<unsigned long long>(event.action),event.prefix_readable?"true":"false",
                static_cast<unsigned>(event.raw10),event.raw38,event.raw3c,static_cast<unsigned>(event.raw40),event.raw44,event.alliance_shape_json,
                static_cast<char>(event.alliance_actor),static_cast<char>(event.alliance_actor>>8),static_cast<char>(event.alliance_actor>>16),
                static_cast<char>(event.alliance_recipient),static_cast<char>(event.alliance_recipient>>8),static_cast<char>(event.alliance_recipient>>16),
                event.spy_network?(event.alliance_variant?"build_spy_network":"stop_building_spy_network"):
                event.improve_relations?(event.alliance_variant?"improve_relations":"stop_improving_relations"):
                event.guarantee?(event.alliance_variant?"proclaim_guarantee":"revoke_guarantee"):
                event.support_independence?(event.alliance_variant?"support_independence":"revoke_support_independence"):
                event.military_access?(event.alliance_variant?"ask_military_access":"cancel_military_access"):
                event.vassalization?(event.alliance_variant?"offer_vassalization":"cancel_vassalization"):
                event.favor_gold?"trade_favors_for_gold":event.favor_trust?"trade_favors_for_trust":event.favor_men?"trade_favors_for_men":
                event.curry_favors?(event.alliance_variant?"curry_favors":"stop_curry_favors"):
                event.royal_marriage?(event.alliance_variant?"offer_royal_marriage":"break_royal_ties"):
                    (event.alliance_variant?"offer_alliance":"dissolve_alliance"),event.alliance_state);
            line(alliance);
        }
    }
    LONG dropped=InterlockedExchange(&observation_dropped,0);
    if (dropped) {
        char message[180];
        snprintf(message,sizeof(message),"{\"event\":\"observation_incomplete\",\"dropped\":%ld,\"business_result\":\"unknown\"}\n",static_cast<long>(dropped));
        line(message);
    }
    for (unsigned i=0;i<32;++i) {
        ObservedAllianceRule event{};
        AcquireSRWLockExclusive(&alliance_rule_lock);
        if (!alliance_rule_size) { ReleaseSRWLockExclusive(&alliance_rule_lock); break; }
        event=alliance_rule_events[alliance_rule_head];
        alliance_rule_head=(alliance_rule_head+1)%128; --alliance_rule_size;
        ReleaseSRWLockExclusive(&alliance_rule_lock);
        char message[640];
        snprintf(message,sizeof(message),"{\"event\":\"native_alliance_validity_observed\",\"session_id\":\"%lu-%llx\",\"query_id\":\"%s\",\"actor_field\":\"%c%c%c\",\"recipient_field\":\"%c%c%c\",\"action_id\":\"%s\",\"thread\":%lu,\"native_result\":%s,\"state_before\":%d,\"state_after\":%d,\"state_read\":%s,\"extra_engine_calls\":false,\"full_rules_complete\":false,\"reasons_complete\":false}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            event.query_id,
            static_cast<char>(event.actor),static_cast<char>(event.actor>>8),static_cast<char>(event.actor>>16),
            static_cast<char>(event.recipient),static_cast<char>(event.recipient>>8),static_cast<char>(event.recipient>>16),
            event.variant?"offer_alliance":"dissolve_alliance",static_cast<unsigned long>(event.thread),
            event.result?"true":"false",event.state_before,event.state_after,event.state_read?"true":"false");
        line(message);
    }
    dropped=InterlockedExchange(&alliance_rule_dropped,0);
    if (dropped) {
        char message[180];
        snprintf(message,sizeof(message),"{\"event\":\"alliance_rules_observation_incomplete\",\"dropped\":%ld}\n",static_cast<long>(dropped));
        line(message);
    }
}

extern "C" void bridge_frame_tick(void* context) {
    // Use the same reentrancy/thread policy as the control build.
    if (InterlockedCompareExchange(&observation_frame_inside,1,0)) return;
    observer_legacy_frame(context);
    if (!thread_changed && frame_thread==GetCurrentThreadId()) {
        uintptr_t vassal_context_game=0;
        if (read(base+0x233fe58,vassal_context_game)) {
            vassal_test_context_tick(vassal_context_game);
            religion_war_context_tick(vassal_context_game);
            vassal_inbound_test_context_tick(vassal_context_game);
        }
        inbound_saved_queue_tick();
        inbound_test_tick();
        execution_inbound_tick();
        observation_flush();
        lifecycle_flush();
        field_read_flush();
        direct_break_flush();
        protocol_flush();
        transport_flush();
        inbound_flush();
        execution_flush();
        rival_authority_flush();
        rival_command_observer_flush();
        rival_execution_flush();
        if (frame_count>=100) alliance_query_tick();
        if (frame_count>=100) rival_authority_tick();
        execution_tick();
        rival_execution_tick();
    }
    if (GetTickCount64()-observation_last_health>=1000) {
        observation_last_health=GetTickCount64();
        uintptr_t game=0; uint64_t player=0; int32_t date=0;
        bool readable=read(base+0x233fe58,game) && read(game+0x1e60,player) && read(game+0x1dd0,date);
        char message[360];
        snprintf(message,sizeof(message),"{\"event\":\"diplomacy_observer_health\",\"session_id\":\"%lu-%llx\",\"thread_changed\":%s,\"frames\":%ld,\"state_readable\":%s,\"player\":\"%c%c%c\",\"date_raw\":%d}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long long>(observation_creation),
            thread_changed?"true":"false",static_cast<long>(frame_count),readable?"true":"false",
            readable?static_cast<char>(player):'-',readable?static_cast<char>(player>>8):'-',
            readable?static_cast<char>(player>>16):'-',date);
        line(message);
    }
    InterlockedExchange(&observation_frame_inside,0);
}

extern "C" __declspec(dllexport) DWORD WINAPI BridgeStart(void* argument) {
    FILETIME created{},exited{},kernel{},user{};
    if (!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user)) return 26;
    observation_creation=(static_cast<uint64_t>(created.dwHighDateTime)<<32)|created.dwLowDateTime;
    wchar_t module_path[MAX_PATH]{};
    DWORD length=GetModuleFileNameW(self_module,module_path,MAX_PATH);
    wchar_t* slash=length && length<MAX_PATH?wcsrchr(module_path,L'\\'):nullptr;
    if (!slash) return 27;
    *slash=0;
    if (swprintf(alliance_query_path,MAX_PATH,L"%ls\\diplomacy-query.request",module_path)<0) return 27;
    if (swprintf(execution_request_path,MAX_PATH,L"%ls\\diplomacy-execute.req",module_path)<0) return 27;
    if (swprintf(execution_authority_test_path,MAX_PATH,L"%ls\\diplomacy-authority-test.req",module_path)<0) return 27;
    if (!rival_authority_set_paths(module_path)) return 27;
    if (!rival_execution_set_paths(module_path)) return 27;
    if (!vassal_test_context_start(module_path)) return 27;
    if (!religion_war_context_start(module_path)) return 29;
    if (!vassal_inbound_test_context_start(module_path)) return 27;
    execution_authority_tests_consumed=0;
    if (!inbound_set_test_path(module_path)) return 27;
    if (!execution_set_inbound_response_paths(module_path)) return 27;
    if (!execution_peace_set_paths(module_path)) return 27;
    if (GetFileAttributesW(alliance_query_path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(alliance_query_path)) return 27;
    if (GetFileAttributesW(execution_request_path)!=INVALID_FILE_ATTRIBUTES && !DeleteFileW(execution_request_path)) return 27;
    DWORD result=ObserverControlStart(argument);
    if (result) return result;
    const bool coalition_capture_installed=coalition_install();
    line(coalition_capture_installed
        ?"{\"event\":\"peace_coalition_capture_installed\",\"all_native_returns_preserved\":true}\n"
        :"{\"event\":\"peace_coalition_capture_unavailable\",\"other_peace_consequences_available\":true}\n");
    bool rule_installed=observation_install_alliance_rule();
    line(rule_installed?"{\"event\":\"alliance_rule_observer_installed\",\"runtime_verified\":false,\"changes_rule_result\":false}\n":
        "{\"event\":\"alliance_rule_observer_unavailable\",\"base_observer_remains_installed\":true}\n");
    bool lifecycle_installed=lifecycle_install();
    line(lifecycle_installed?"{\"event\":\"alliance_lifecycle_observer_installed\",\"all_native_returns_preserved\":true,\"authority_enabled\":false}\n":
        "{\"event\":\"alliance_lifecycle_observer_unavailable\",\"authority_enabled\":false}\n");
    bool royal_lifecycle_installed=lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_royal();
    bool improve_lifecycle_installed=royal_lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_improve();
    bool spy_lifecycle_installed=improve_lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_spy();
    bool guarantee_lifecycle_installed=spy_lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_guarantee();
    line(guarantee_lifecycle_installed?"{\"event\":\"guarantee_lifecycle_observer_installed\",\"native_vtable_rva\":\"0x1c7fe50\",\"native_clone_rva\":\"0x5224f0\",\"slots\":\"0x00,0x40,0xb0\"}\n":
        "{\"event\":\"guarantee_lifecycle_observer_unavailable\"}\n");
    bool support_lifecycle_installed=guarantee_lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_support();
    line(support_lifecycle_installed?"{\"event\":\"support_independence_lifecycle_observer_installed\",\"native_vtable_rva\":\"0x1c805f0\",\"native_clone_rva\":\"0x50f0c0\"}\n":
        "{\"event\":\"support_independence_lifecycle_observer_unavailable\"}\n");
    bool military_lifecycle_installed=support_lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_military_access();
    line(military_lifecycle_installed?"{\"event\":\"military_access_lifecycle_observer_installed\",\"native_vtable_rva\":\"0x1c7fb70\",\"native_clone_rva\":\"0x525da0\"}\n":
        "{\"event\":\"military_access_lifecycle_observer_unavailable\"}\n");
    bool insult_lifecycle_installed=military_lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_insult();
    line(insult_lifecycle_installed?"{\"event\":\"insult_lifecycle_observer_installed\",\"native_vtable_rva\":\"0x1c7f6b0\",\"native_clone_rva\":\"0x538e50\"}\n":
        "{\"event\":\"insult_lifecycle_observer_unavailable\"}\n");
    bool vassal_lifecycle_installed=insult_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_vassalization();
    bool favor_gold_lifecycle_installed=vassal_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_favor_gold();
    line(favor_gold_lifecycle_installed
        ?"{\"event\":\"favor_gold_lifecycle_observer_installed\",\"native_vtable_rva\":\"0x1c80980\",\"native_clone_rva\":\"0x4f5c00\",\"slots\":\"0x00,0x40,0xb0\",\"choice_slot\":\"0xd0\",\"choice_method_rva\":\"0x8f440\"}\n"
        :"{\"event\":\"favor_gold_lifecycle_observer_unavailable\"}\n");
    bool favor_trust_lifecycle_installed=favor_gold_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_favor_trust();
    line(favor_trust_lifecycle_installed
        ?"{\"event\":\"favor_trust_lifecycle_observer_installed\",\"native_selector\":\"0x3bd3\",\"native_vtable_rva\":\"0x1c80c60\",\"native_rule_rva\":\"0x4fdfd0\",\"native_display_rva\":\"0x4fe2d0\",\"native_effect_rva\":\"0x4fd250\",\"native_clone_rva\":\"0x4fe770\",\"destructor_rva\":\"0x129500\",\"slots\":\"0x00,0x40,0xb0\",\"choice_slot\":\"0xd0\",\"choice_method_rva\":\"0x8f440\"}\n"
        :"{\"event\":\"favor_trust_lifecycle_observer_unavailable\"}\n");
    bool favor_men_lifecycle_installed=favor_trust_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_favor_men();
    line(favor_men_lifecycle_installed
        ?"{\"event\":\"favor_men_lifecycle_observer_installed\",\"native_selector\":\"0x3bcf\",\"native_vtable_rva\":\"0x1c80ff0\",\"native_rule_rva\":\"0x4f7600\",\"native_display_rva\":\"0x4f7ca0\",\"native_effect_rva\":\"0x4f67c0\",\"native_clone_rva\":\"0x4f8420\",\"destructor_rva\":\"0x129450\",\"slots\":\"0x00,0x40,0xb0\",\"choice_slot\":\"0xd0\",\"choice_method_rva\":\"0x8f440\"}\n"
        :"{\"event\":\"favor_men_lifecycle_observer_unavailable\"}\n");
    bool curry_favors_lifecycle_installed=favor_men_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_curry_favors();
    line(curry_favors_lifecycle_installed
        ?"{\"event\":\"curry_favors_lifecycle_observer_installed\",\"native_selector\":\"0x3acc\",\"native_vtable_rva\":\"0x1c7aef8\",\"native_rule_rva\":\"0x5ade90\",\"native_display_rva\":\"0x5ae140\",\"native_effect_rva\":\"0x5ace80\",\"native_clone_rva\":\"0x5ae2e0\",\"slots\":\"0x00,0x40,0xb0\",\"diplomat_slot\":\"0xf8\",\"diplomat_rva\":\"0x4e4d80\"}\n"
        :"{\"event\":\"curry_favors_lifecycle_observer_unavailable\"}\n");
    bool gift_lifecycle_installed=curry_favors_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_gift();
    line(gift_lifecycle_installed
        ?"{\"event\":\"gift_lifecycle_observer_installed\",\"native_selector\":\"0x2948\",\"native_vtable_rva\":\"0x1c7f450\",\"native_rule_rva\":\"0x53a630\",\"native_display_rva\":\"0x53a8d0\",\"native_effect_rva\":\"0x539570\",\"native_clone_rva\":\"0x53b0c0\",\"destructor_rva\":\"0x129500\",\"amount_offset\":\"0x40\"}\n"
        :"{\"event\":\"gift_lifecycle_observer_unavailable\"}\n");
    bool influence_lifecycle_installed=gift_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_influence();
    line(influence_lifecycle_installed
        ?"{\"event\":\"influence_lifecycle_observer_installed\",\"native_selector\":\"0x346e\",\"native_vtable_rva\":\"0x1cb3cf8\",\"native_rule_rva\":\"0x7c4430\",\"native_display_rva\":\"0x7c48a0\",\"native_effect_rva\":\"0x7c35b0\",\"native_clone_rva\":\"0x7c4d10\",\"destructor_rva\":\"0x129450\"}\n"
        :"{\"event\":\"influence_lifecycle_observer_unavailable\"}\n");
    bool declarewar_lifecycle_installed=influence_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_declarewar();
    bool peace_lifecycle_installed=declarewar_lifecycle_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_peace();
    line(peace_lifecycle_installed?"{\"event\":\"peace_lifecycle_observer_installed\",\"vtable_rva\":\"0x1c7b840\",\"clone_rva\":\"0x59ba70\",\"complete_offer_snapshot\":true}\n":
        "{\"event\":\"peace_lifecycle_observer_failed\"}\n");
    bool serializer_installed=peace_lifecycle_installed && !lifecycle_rollback_incomplete && lifecycle_install_serializer();
    line(serializer_installed?"{\"event\":\"alliance_serializer_observer_installed\",\"authority_enabled\":false,\"submit_receipt\":false}\n":
        "{\"event\":\"alliance_serializer_observer_unavailable\",\"authority_enabled\":false}\n");
    bool field_reader_installed=serializer_installed && !lifecycle_rollback_incomplete && lifecycle_install_field_reader();
    line(field_reader_installed?"{\"event\":\"alliance_field_reader_observer_installed\",\"authority_enabled\":false,\"native_arguments_preserved\":true}\n":
        "{\"event\":\"alliance_field_reader_observer_unavailable\",\"authority_enabled\":false}\n");
    bool royal_field_reader_installed=field_reader_installed && !lifecycle_rollback_incomplete && lifecycle_install_royal_field_reader();
    line(royal_field_reader_installed?"{\"event\":\"royal_lifecycle_observer_installed\",\"native_arguments_preserved\":true}\n":
        "{\"event\":\"royal_lifecycle_observer_unavailable\"}\n");
    bool vassal_field_reader_installed=royal_field_reader_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_vassalization_field_reader();
    bool declarewar_field_reader_installed=vassal_field_reader_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_declarewar_field_reader();
    bool peace_field_reader_installed=declarewar_field_reader_installed && !lifecycle_rollback_incomplete
        && lifecycle_install_peace_field_reader();
    bool direct_break_installed=peace_field_reader_installed && !lifecycle_rollback_incomplete && direct_break_install();
    line(direct_break_installed?"{\"event\":\"direct_break_entry_observer_installed\",\"authority_enabled\":false,\"before_relationship_writes\":true}\n":
        "{\"event\":\"direct_break_entry_observer_unavailable\",\"authority_enabled\":false}\n");
    bool protocol_installed=direct_break_installed && !lifecycle_rollback_incomplete && protocol_install();
    line(protocol_installed?"{\"event\":\"alliance_wrapper_protocol_observer_installed\",\"authority_enabled\":false,\"native_arguments_preserved\":true}\n":
        "{\"event\":\"alliance_wrapper_protocol_observer_unavailable\",\"authority_enabled\":false}\n");
    bool transport_installed=protocol_installed && !lifecycle_rollback_incomplete && transport_install();
    line(transport_installed?"{\"event\":\"alliance_transport_observer_installed\",\"authority_enabled\":false,\"native_arguments_preserved\":true}\n":
        "{\"event\":\"alliance_transport_observer_unavailable\",\"authority_enabled\":false}\n");
    bool rival_observer_installed=transport_installed && !lifecycle_rollback_incomplete
        && rival_command_observer_install();
    bool execution_installed=rival_observer_installed && !rival_command_observer_rollback_incomplete
        && !lifecycle_rollback_incomplete && execution_install();
    bool peace_handler_guard_installed=execution_installed && !lifecycle_rollback_incomplete
        && peace_handler_authority_install();
    line(peace_handler_guard_installed?"{\"event\":\"peace_handler_authority_installed\",\"slot\":\"0x48\",\"native_handler_rva\":\"0x598f00\"}\n":
        "{\"event\":\"peace_handler_authority_failed\"}\n");
    bool peace_receiver_observer_installed=peace_handler_guard_installed && !lifecycle_rollback_incomplete
        && peace_receiver_observer_install();
    line(peace_receiver_observer_installed?"{\"event\":\"peace_receiver_head_observer_installed\",\"slot\":\"0x48\",\"native_accessor_rva\":\"0x8b0e0\"}\n":
        "{\"event\":\"peace_receiver_head_observer_failed\"}\n");
    bool rival_authority_installed=peace_receiver_observer_installed && !lifecycle_rollback_incomplete
        && rival_authority_install();
    bool rival_execution_installed=rival_authority_installed && rival_execution_install();
    bool response_installed=rival_execution_installed && !lifecycle_rollback_incomplete
        && execution_inbound_response_install();
    bool inbound_installed=execution_installed && !lifecycle_rollback_incomplete && inbound_install();
    bool reason_metadata_required=false,reason_metadata_installed=false;
#if defined(BRIDGE_ALLIANCE_REASON_METADATA)
    reason_metadata_required=true;
    reason_metadata_installed=inbound_installed && response_installed
        && !lifecycle_rollback_incomplete && bridge_alliance_reason_metadata_install();
    line(reason_metadata_installed?"{\"event\":\"alliance_reason_metadata_installed\",\"native_alliance_reason_metadata\":true,\"scope\":\"text_bearing_alliance_query_only\"}\n":
        "{\"event\":\"alliance_reason_metadata_unavailable\",\"native_alliance_reason_metadata\":false}\n");
#endif
    const bool r74_lifecycle_ready=gift_lifecycle_installed
        && influence_lifecycle_installed;
    line(inbound_installed && response_installed && vassal_lifecycle_installed && favor_gold_lifecycle_installed && favor_trust_lifecycle_installed && favor_men_lifecycle_installed && curry_favors_lifecycle_installed && vassal_field_reader_installed?"{\"event\":\"alliance_execution_handler_installed\",\"native_offer_submission\":true,\"native_dissolve_submission\":true,\"native_guarantee_query\":true,\"native_guarantee_submission\":true,\"native_support_independence_query\":true,\"native_support_independence_submission\":true,\"native_inbound_support_independence_response\":true,\"native_military_access_query\":true,\"native_insult_query\":true,\"native_rival_query\":true,\"native_declare_war_query\":true,\"native_peace_context_query\":true,\"native_peace_empty_offer_query\":true,\"native_peace_offer_evaluation_query\":true,\"native_peace_money_offer_query\":true,\"native_peace_province_offer_query\":true,\"native_peace_combined_query\":true,\"native_peace_reparations_query\":true,\"native_peace_reparations_execution\":true,\"native_peace_trade_power_query\":true,\"native_peace_trade_power_execution\":true,\"native_peace_trade_power_sources\":true,\"native_peace_concede_defeat_query\":true,\"native_peace_concede_defeat_execution\":true,\"native_peace_annul_treaties_query\":true,\"native_peace_annul_treaties_execution\":true,\"native_peace_special_terms_query\":true,\"native_peace_special_terms_execution\":true,\"native_peace_core_terms_query\":true,\"native_peace_subject_terms_query\":true,\"native_peace_subject_terms_execution\":true,\"native_peace_country_terms_query\":true,\"native_peace_country_money_query\":true,\"native_peace_country_terms_execution\":true,\"native_peace_core_terms_execution\":true,\"native_peace_subject_terms_execution\":true,\"native_peace_country_terms_execution\":true,\"native_peace_core_terms_execution\":true,\"native_peace_war_context_query\":true,\"native_peace_serialized_payload_query\":true,\"native_declare_war_submission\":true,\"native_declare_war_participants\":true,\"native_declare_war_forces\":true,\"native_declare_war_peace_options\":true,\"native_peace_consequences\":true,\"native_peace_submission\":true,\"native_peace_wrapper_rule_query\":true,\"native_peace_inbound_pending\":true,\"native_inbound_peace_response\":true,\"native_vassalization_query\":true,\"native_vassalization_submission\":true,\"native_inbound_vassalization_response\":true,\"native_favor_gold_query\":true,\"native_favor_gold_submission\":true,\"native_inbound_favor_gold_response\":true,\"native_favor_trust_query\":true,\"native_favor_trust_submission\":true,\"native_inbound_favor_trust_response\":true,\"native_favor_men_query\":true,\"native_favor_men_submission\":true,\"native_inbound_favor_men_response\":true,\"native_curry_favors_query\":true,\"native_curry_favors_submission\":true,\"native_rival_submission\":true,\"native_rival_authority\":true,\"native_insult_submission\":true,\"native_military_access_submission\":true,\"native_inbound_military_access_response\":true,\"native_inbound_alliance\":true,\"native_inbound_alliance_response\":true,\"incoming_offer\":true,\"incoming_mode\":\"state0_deferred_pending_observe;state1_2_llm_response\",\"accept\":true,\"reject\":true,\"withdraw\":false,\"dissolve\":true,\"parameters_empty_only\":false,\"authority_lock_enabled\":true,\"authority_scope\":\"outbound FRA Alliance/Royal/Support/MilitaryAccess/Vassalization requests and revocations require generic-entry authority; FRA Improve/Spy/Guarantee/Insult/DeclareWar/CurryFavors unilateral operations require authority; FRA Rival Set/Replace/Remove native handlers deny ungranted choices; Alliance/Royal/Support/MilitaryAccess/Vassalization incoming recipient FRA deferred for LLM accept/reject; Peace incoming recipient FRA retained pending with native AI choice held; Peace incoming responses require a consumed full-payload pending binding; offer_alliance sender SAV|LIT; other implemented senders native-valid canonical recipients; unbound FRA receiver state1/2 blocked\",\"other_actions_forwarded\":true}\n":
        "{\"event\":\"alliance_execution_handler_unavailable\",\"native_offer_submission\":false}\n");
    if (lifecycle_rollback_incomplete || !lifecycle_installed || !royal_lifecycle_installed || !improve_lifecycle_installed || !spy_lifecycle_installed || !guarantee_lifecycle_installed || !support_lifecycle_installed || !military_lifecycle_installed || !insult_lifecycle_installed || !serializer_installed || !field_reader_installed || !royal_field_reader_installed || !direct_break_installed || !protocol_installed || !transport_installed || !execution_installed || !response_installed || !inbound_installed
        || !rival_authority_installed || !rival_observer_installed || !rival_execution_installed
        || !vassal_lifecycle_installed || !favor_gold_lifecycle_installed
        || !favor_trust_lifecycle_installed || !favor_men_lifecycle_installed
        || !curry_favors_lifecycle_installed || !vassal_field_reader_installed
        || !r74_lifecycle_ready
        || !declarewar_lifecycle_installed || !declarewar_field_reader_installed
        || !peace_lifecycle_installed || !peace_field_reader_installed
        || !peace_handler_guard_installed
        || !peace_receiver_observer_installed
        || (reason_metadata_required && !reason_metadata_installed)) {
        bool rolled_back=observation_rollback_family();
        line(rolled_back?"{\"event\":\"observer_family_install_failed\",\"all_hooks_rolled_back\":true,\"restart_required\":true}\n":
            "{\"event\":\"observer_family_rollback_incomplete\",\"restart_required\":true}\n"); return 28;
    }
    // Keep R74 capability literals in the exact installation ACK consumed by
    // the Python adapter.  The long legacy format string remains untouched;
    // bounded insertion avoids duplicating that contract here.
    auto append_r74_capabilities=[](char* text,size_t capacity) {
        if (!text || capacity==0) return;
        constexpr char marker[]="\"native_generic_execution_entry_guard\":true";
        constexpr char fields[]=",\"native_gift_query\":true,\"native_gift_submission\":true,\"native_influence_query\":true,\"native_influence_submission\":true,\"native_live_war_score_query\":true";
        char* at=strstr(text,marker);
        if (!at) return;
        const size_t marker_size=sizeof(marker)-1;
        const size_t fields_size=sizeof(fields)-1;
        const size_t used=strlen(text);
        const size_t offset=static_cast<size_t>(at-text)+marker_size;
        if (offset>used || used+fields_size+1>capacity) return;
        memmove(text+offset+fields_size,text+offset,used-offset+1);
        memcpy(text+offset,fields,fields_size);
    };
    char message[8192];
    snprintf(message,sizeof(message),"{\"event\":\"diplomacy_observer_installed\",\"version\":22,\"pid\":%lu,\"session_id\":\"%lu-%llx\",\"creation_filetime\":%llu,\"native_queries_enabled\":true,\"native_spy_network_query\":true,\"native_spy_network_submission\":true,\"native_improve_relations_query\":true,\"native_improve_relations_submission\":true,\"native_guarantee_query\":true,\"native_guarantee_submission\":true,\"native_support_independence_query\":true,\"native_support_independence_submission\":true,\"native_inbound_support_independence_response\":true,\"native_military_access_query\":true,\"native_insult_query\":true,\"native_rival_query\":true,\"native_declare_war_query\":true,\"native_peace_context_query\":true,\"native_peace_empty_offer_query\":true,\"native_peace_offer_evaluation_query\":true,\"native_peace_money_offer_query\":true,\"native_peace_province_offer_query\":true,\"native_peace_combined_query\":true,\"native_peace_reparations_query\":true,\"native_peace_reparations_execution\":true,\"native_peace_trade_power_query\":true,\"native_peace_trade_power_execution\":true,\"native_peace_trade_power_sources\":true,\"native_peace_concede_defeat_query\":true,\"native_peace_concede_defeat_execution\":true,\"native_peace_annul_treaties_query\":true,\"native_peace_annul_treaties_execution\":true,\"native_peace_special_terms_query\":true,\"native_peace_special_terms_execution\":true,\"native_peace_core_terms_query\":true,\"native_peace_subject_terms_query\":true,\"native_peace_subject_terms_execution\":true,\"native_peace_country_terms_query\":true,\"native_peace_country_money_query\":true,\"native_peace_country_terms_execution\":true,\"native_peace_core_terms_execution\":true,\"native_peace_war_context_query\":true,\"native_peace_serialized_payload_query\":true,\"native_declare_war_submission\":true,\"native_declare_war_participants\":true,\"native_declare_war_forces\":true,\"native_declare_war_peace_options\":true,\"native_peace_consequences\":true,\"native_peace_submission\":true,\"native_peace_wrapper_rule_query\":true,\"native_peace_inbound_pending\":true,\"native_inbound_peace_response\":true,\"native_vassalization_query\":true,\"native_vassalization_submission\":true,\"native_inbound_vassalization_response\":true,\"native_favor_gold_query\":true,\"native_favor_gold_submission\":true,\"native_inbound_favor_gold_response\":true,\"native_favor_trust_query\":true,\"native_favor_trust_submission\":true,\"native_inbound_favor_trust_response\":true,\"native_favor_men_query\":true,\"native_favor_men_submission\":true,\"native_inbound_favor_men_response\":true,\"native_curry_favors_query\":true,\"native_curry_favors_submission\":true,\"native_rival_submission\":true,\"native_rival_authority\":true,\"native_insult_submission\":true,\"native_military_access_submission\":true,\"native_inbound_military_access_response\":true,\"native_generic_execution_entry_guard\":true,\"native_royal_marriage_query\":true,\"native_royal_marriage_submission\":true,\"native_inbound_royal_marriage_response\":true,\"native_execution_enabled\":true,\"native_offer_submission\":true,\"native_dissolve_submission\":true,\"native_inbound_alliance\":true,\"native_inbound_alliance_response\":true,\"native_alliance_reason_metadata\":%s,\"incoming_offer\":true,\"incoming_mode\":\"state0_deferred_pending_observe;state1_2_llm_response\",\"accept\":true,\"reject\":true,\"withdraw\":false,\"dissolve\":true,\"authority_lock_enabled\":true,\"authority_scope\":\"outbound FRA Alliance/Royal/Support/MilitaryAccess/Vassalization requests and revocations require generic-entry authority; FRA Improve/Spy/Guarantee/Insult/DeclareWar/CurryFavors unilateral operations require authority; FRA Rival Set/Replace/Remove native handlers deny ungranted choices; Alliance/Royal/Support/MilitaryAccess/Vassalization incoming recipient FRA deferred for LLM accept/reject; Peace incoming recipient FRA retained pending with native AI choice held; Peace incoming responses require a consumed full-payload pending binding; offer_alliance sender SAV|LIT; other implemented senders native-valid canonical recipients; unbound FRA receiver state1/2 blocked\",\"other_actions_forwarded\":true,\"all_commands_forwarded\":false}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),static_cast<unsigned long long>(observation_creation),
        reason_metadata_installed?"true":"false");
    append_r74_capabilities(message,sizeof(message));
    line(message); return 0;
}
