// Scoped observation of the native recipient-owned Alliance pending path.
//
// This include is intentionally narrower than the generic executor hook.  The
// executor supplies a TLS scope only for a canonical state-0 Offer whose full
// recipient handle is FRA and whose actor is another canonical country.  The
// patched callsite at 0x4e81b8 then either tail-jumps to the original
// 0x2cd5a0 predicate, returns directly to 0x4e8235 for first delivery, or
// returns false at 0x4e81bd for an exact, already-bound FRA pending action.
// The latter skips native AI choice but retains native validity and cleanup.
// No native method is called by this observer.

#ifndef BRIDGE_ALLIANCE_INBOUND_INC
#define BRIDGE_ALLIANCE_INBOUND_INC

#include "alliance-pending-membership.h"

extern "C" void bridge_inbound_predicate_stub();
extern "C" void* bridge_inbound_predicate_original;
extern "C" uintptr_t bridge_inbound_pending_target;
extern "C" {
void* bridge_inbound_predicate_original=nullptr;
uintptr_t bridge_inbound_pending_target=0;
}

namespace alliance_execution_detail {
static bool execution_world_dispatcher(uintptr_t& dispatcher,
    uintptr_t& transport) noexcept;
static void execution_release_constructed(void* wrapper,unsigned char* action,
    bool action_constructed) noexcept;
}

namespace bridge_alliance_inbound_detail {

constexpr uintptr_t kPredicateCallRva=0x4e81b8;
constexpr uintptr_t kPredicateReturnRva=0x4e81bd;
constexpr uintptr_t kPredicateRva=0x2cd5a0;
constexpr uintptr_t kPendingTargetRva=0x4e8235;
constexpr uintptr_t kParentExecutorRva=0x4e7c80;
constexpr uintptr_t kAllianceVtableRva=0x1c80720;
constexpr unsigned kPatchBytes=5;
constexpr unsigned kQueueCapacity=64;
constexpr SIZE_T kNearBlockBytes=0x1000;
constexpr unsigned kTrampolineOffset=0x200;
constexpr unsigned kRelayOffset=0x100;
constexpr unsigned kTrampolinePrefix=0x40;

struct InboundScope {
    bool active=false;
    bool call_redirected=false;
    bool before_readable=false;
    bool royal_marriage=false;
    bool support_independence=false;
    bool military_access=false;
    bool vassalization=false;
    bool peace_offer=false;
    bridge::peace_payload::PeaceActionPayload peace{};
    unsigned char extra60=0;
    uintptr_t action=0;
    uintptr_t country=0;
    uint64_t actor=0;
    uint64_t recipient=0;
    uint32_t before_count=0;
    uintptr_t before_tail=0;
};

struct InboundOfferEvent {
    uint64_t proposal_id=0;
    char actor[4]{};
    char mirror[4]{};
    char recipient[4]{};
    int32_t date28=0;
    int32_t date2c=0;
    int32_t envoy30=0;
    int32_t state34=0;
    unsigned char variant38=0;
    bool royal_marriage=false;
    bool support_independence=false;
    bool military_access=false;
    bool vassalization=false;
    bool peace_offer=false;
    bridge::peace_payload::PeaceActionPayload peace{};
    unsigned char extra60=0;
    int32_t proposal3c=0;
    uint32_t token3c=0;
    int32_t created2c=0;
    uint32_t queue_before=0;
    uint32_t queue_after=0;
    bool queue_readable=false;
    bool list_integrity=false;
    bool new_entry=false;
    bool payload_readable=false;
    bool decision_country_verified=false;
    bool source_verified=false;
};

// A pending record is live only while the exact native queue node and clone
// still match every captured field.  Addresses are retained for identity
// checks, never exposed to the request protocol.
struct InboundPendingView {
    bool active=false;
    bool response_reserved=false;
    bool response_submitted=false;
    uint64_t proposal_id=0;
    uint64_t generation=0;
    uint64_t actor=0;
    uint64_t mirror=0;
    uint64_t recipient=0;
    int32_t date28=0;
    int32_t date2c=0;
    int32_t envoy30=0;
    int32_t state34=0;
    unsigned char variant38=0;
    bool royal_marriage=false;
    bool support_independence=false;
    bool military_access=false;
    bool vassalization=false;
    bool peace_offer=false;
    bridge::peace_payload::PeaceActionPayload peace{};
    unsigned char extra60=0;
    int32_t proposal3c=0;
    uint32_t token3c=0;
    uintptr_t country=0;
    uintptr_t node=0;
    uintptr_t clone=0;
    uintptr_t action=0;
};

struct InboundPendingRecord {
    bool active=false;
    bool response_reserved=false;
    bool response_submitted=false;
    uint64_t proposal_id=0;
    uint64_t generation=0;
    uint64_t actor=0;
    uint64_t mirror=0;
    uint64_t recipient=0;
    int32_t date28=0;
    int32_t date2c=0;
    int32_t envoy30=0;
    int32_t state34=0;
    unsigned char variant38=0;
    bool royal_marriage=false;
    bool support_independence=false;
    bool military_access=false;
    bool vassalization=false;
    bool peace_offer=false;
    bridge::peace_payload::PeaceActionPayload peace{};
    unsigned char extra60=0;
    int32_t proposal3c=0;
    uint32_t token3c=0;
    uintptr_t country=0;
    uintptr_t node=0;
    uintptr_t clone=0;
    uintptr_t action=0;
    int32_t ai_hold_last_date=0;
    uint32_t ai_hold_count=0;
};

struct InboundAiHoldEvent {
    uint64_t proposal_id=0;
    uint64_t generation=0;
    uintptr_t command=0;
    uintptr_t action=0;
    uint32_t token3c=0;
    uint32_t hold_count=0;
    int32_t date=0;
    DWORD thread=0;
    bool royal_marriage=false;
    bool support_independence=false;
    bool military_access=false;
    bool vassalization=false;
    bool peace_offer=false;
    uintptr_t caller_return_rva=0;
};

static thread_local InboundScope inbound_scope{};
static SRWLOCK inbound_lock=SRWLOCK_INIT;
static InboundOfferEvent inbound_events[kQueueCapacity]{};
static unsigned inbound_head=0,inbound_size=0;
static volatile LONG inbound_dropped=0;
static InboundAiHoldEvent inbound_hold_events[kQueueCapacity]{};
static unsigned inbound_hold_head=0,inbound_hold_size=0;
static volatile LONG inbound_hold_dropped=0;
static volatile LONG64 inbound_sequence=0;
static volatile LONG64 inbound_generation=0;
static SRWLOCK inbound_pending_lock=SRWLOCK_INIT;
static InboundPendingRecord inbound_pending_records[kQueueCapacity]{};
static wchar_t inbound_test_request_path[MAX_PATH]{};
static bool inbound_test_consumed=false;

static bridge_entry_patch::PatchPlan inbound_patch_plan{};
static unsigned char inbound_expected[kPatchBytes]{};
static unsigned char inbound_replacement[kPatchBytes]{};
static unsigned char* inbound_block=nullptr;
static unsigned char* inbound_relay=nullptr;
static unsigned char* inbound_trampoline=nullptr;
static SIZE_T inbound_trampoline_size=19;
static RUNTIME_FUNCTION inbound_runtime_function{};
static bool inbound_runtime_registered=false;
static bool inbound_installed=false;
static bool inbound_published=false;
using InboundChoicePredicate=unsigned char (*)(void*);
static InboundChoicePredicate inbound_royal_choice_original=nullptr;
static bool inbound_royal_choice_installed=false;
static InboundChoicePredicate inbound_support_choice_original=nullptr;
static bool inbound_support_choice_installed=false;
static InboundChoicePredicate inbound_military_choice_original=nullptr;
static bool inbound_military_choice_installed=false;
static InboundChoicePredicate inbound_vassal_choice_original=nullptr;
static bool inbound_vassal_choice_installed=false;
static InboundChoicePredicate inbound_peace_choice_original=nullptr;
static bool inbound_peace_choice_installed=false;

static bool inbound_read_country(uint64_t handle,uintptr_t& country) noexcept {
    country=0;
    const unsigned slot=static_cast<unsigned>((handle>>32)&0xffffu);
    uintptr_t database=0,array=0,actual=0;
    if (slot>=4096 || !read(base+0x233d8b0,database)
        || !read(database+0x118,array)
        || !read(array+static_cast<uintptr_t>(slot)*8,country)
        || !read(country+0x20,actual)) return false;
    return actual==handle;
}

static bool inbound_is_fra(uint64_t handle,uintptr_t& country) noexcept {
    return static_cast<uint32_t>(handle&0xffffffu)==0x415246u
        && inbound_read_country(handle,country);
}

static void inbound_tag(char (&output)[4],uint64_t handle) noexcept {
    output[0]=static_cast<char>(handle&0xffu);
    output[1]=static_cast<char>((handle>>8)&0xffu);
    output[2]=static_cast<char>((handle>>16)&0xffu);
    output[3]=0;
}

static bool inbound_tag_matches(uint64_t handle,const char* tag) noexcept {
    return tag && static_cast<unsigned char>(tag[0])==static_cast<unsigned char>(handle&0xffu)
        && static_cast<unsigned char>(tag[1])==static_cast<unsigned char>((handle>>8)&0xffu)
        && static_cast<unsigned char>(tag[2])==static_cast<unsigned char>((handle>>16)&0xffu)
        && tag[3]==0;
}

static void inbound_pending_copy(const InboundPendingRecord& source,
    InboundPendingView& destination) noexcept {
    destination.active=source.active;
    destination.response_reserved=source.response_reserved;
    destination.response_submitted=source.response_submitted;
    destination.proposal_id=source.proposal_id;
    destination.generation=source.generation;
    destination.actor=source.actor;
    destination.mirror=source.mirror;
    destination.recipient=source.recipient;
    destination.date28=source.date28;
    destination.date2c=source.date2c;
    destination.envoy30=source.envoy30;
    destination.state34=source.state34;
    destination.variant38=source.variant38;
    destination.royal_marriage=source.royal_marriage;
    destination.support_independence=source.support_independence;
    destination.military_access=source.military_access;
    destination.vassalization=source.vassalization;
    destination.peace_offer=source.peace_offer;
    destination.peace=source.peace;
    destination.extra60=source.extra60;
    destination.proposal3c=source.proposal3c;
    destination.token3c=source.token3c;
    destination.country=source.country;
    destination.node=source.node;
    destination.clone=source.clone;
    destination.action=source.action;
}

static bool inbound_pending_shape_matches(const InboundPendingRecord& record,
    const LifecycleActionShape& shape) noexcept {
    const bool peace_payload_match=shape.peace_offer==record.peace_offer
        && (shape.peace_offer
            ? shape.peace.valid() && record.peace.valid() && shape.peace==record.peace
            : shape.peace.empty() && record.peace.empty());
    return shape.readable && shape.matched && shape.handles_canonical
        && !shape.improve_relations && !shape.spy_network && !shape.guarantee && !shape.insult
        && !shape.declare_war
        && shape.royal_marriage==record.royal_marriage
        && shape.support_independence==record.support_independence
        && shape.military_access==record.military_access
        && shape.vassalization==record.vassalization
        && peace_payload_match
        && shape.extra60==record.extra60
        && shape.address==record.action && shape.actor10==record.actor
        && shape.mirror18==record.mirror && shape.recipient20==record.recipient
        && shape.date28==record.date28 && shape.date2c==record.date2c
        && shape.envoy30==record.envoy30 && shape.state34==record.state34
        && shape.variant38==record.variant38 && shape.proposal3c==record.proposal3c
        && static_cast<uint32_t>(shape.proposal3c)==record.token3c;
}

static bool inbound_pending_queue_valid_locked(InboundPendingRecord& record,
    LifecycleActionShape& current) noexcept {
    uintptr_t country=0;
    if (!record.active || !record.country || !record.node || !record.clone
        || !inbound_is_fra(record.recipient,country) || country!=record.country)
        return false;
    uintptr_t head=0,tail=0;
    uint32_t count=0;
    if (!read(country+0x18d8,head) || !read(country+0x18e0,tail)
        || !read(country+0x18e8,count) || count==0 || count>kQueueCapacity
        || !head || !tail) return false;
    uintptr_t node=head,last=0,found_clone=0;
    bool found=false;
    for (uint32_t index=0;index<count && node;++index) {
        uintptr_t clone=0,next=0,previous=0;
        if (!read(node,clone) || !read(node+0x08,previous)
            || !read(node+0x10,next)) return false;
        if ((index==0 && previous!=0) || (index>0 && previous!=last)) return false;
        if (node==record.node) {
            if (found || clone!=record.clone) return false;
            found=true; found_clone=clone;
        }
        last=node;
        node=next;
    }
    if (!found || found_clone!=record.clone || node!=0 || last!=tail) return false;
    current=lifecycle_capture_shape(reinterpret_cast<void*>(record.clone));
    return inbound_pending_shape_matches(record,current);
}

static void inbound_pending_record_new(const InboundScope& scope,
    const InboundOfferEvent& event,uintptr_t node,uintptr_t clone,
    const LifecycleActionShape& shape,bool restored=false) noexcept {
    InboundPendingRecord candidate{};
    candidate.active=true;
    candidate.proposal_id=event.proposal_id;
    candidate.actor=shape.actor10;
    candidate.mirror=shape.mirror18;
    candidate.recipient=shape.recipient20;
    candidate.date28=shape.date28;
    candidate.date2c=shape.date2c;
    candidate.envoy30=shape.envoy30;
    candidate.state34=shape.state34;
    candidate.variant38=shape.variant38;
    candidate.royal_marriage=shape.royal_marriage;
    candidate.support_independence=shape.support_independence;
    candidate.military_access=shape.military_access;
    candidate.vassalization=shape.vassalization;
    candidate.peace_offer=shape.peace_offer;
    candidate.peace=shape.peace;
    candidate.extra60=shape.extra60;
    candidate.proposal3c=shape.proposal3c;
    candidate.token3c=static_cast<uint32_t>(shape.proposal3c);
    candidate.country=scope.country;
    candidate.node=node;
    candidate.clone=clone;
    candidate.action=shape.address;
    if ((!event.new_entry && !restored) || !event.payload_readable || !event.decision_country_verified
        || !scope.country || !node || !clone
        || !inbound_pending_shape_matches(candidate,shape))
        return;
    if (!TryAcquireSRWLockExclusive(&inbound_pending_lock)) return;
    for (const auto& record:inbound_pending_records) {
        if (record.active && record.node==node && record.clone==clone) {
            ReleaseSRWLockExclusive(&inbound_pending_lock);
            return;
        }
    }
    for (auto& record:inbound_pending_records) {
        if (record.active) continue;
        record=InboundPendingRecord{};
        record.active=true;
        record.proposal_id=event.proposal_id;
        record.generation=static_cast<uint64_t>(InterlockedIncrement64(&inbound_generation));
        record.actor=shape.actor10;
        record.mirror=shape.mirror18;
        record.recipient=shape.recipient20;
        record.date28=shape.date28;
        record.date2c=shape.date2c;
        record.envoy30=shape.envoy30;
        record.state34=shape.state34;
        record.variant38=shape.variant38;
        record.royal_marriage=shape.royal_marriage;
        record.support_independence=shape.support_independence;
        record.military_access=shape.military_access;
        record.vassalization=shape.vassalization;
        record.peace_offer=shape.peace_offer;
        record.peace=shape.peace;
        record.extra60=shape.extra60;
        record.proposal3c=shape.proposal3c;
        record.token3c=static_cast<uint32_t>(shape.proposal3c);
        record.country=scope.country;
        record.node=node;
        record.clone=clone;
        record.action=shape.address;
        break;
    }
    ReleaseSRWLockExclusive(&inbound_pending_lock);
}

static bool inbound_rel32(uintptr_t next,uintptr_t destination,int32_t& displacement) noexcept {
    const int64_t difference=static_cast<int64_t>(destination)-static_cast<int64_t>(next);
    if (difference<static_cast<int64_t>(INT32_MIN)
        || difference>static_cast<int64_t>(INT32_MAX)) return false;
    displacement=static_cast<int32_t>(difference);
    return true;
}

static void inbound_absolute_jump(unsigned char* destination,uintptr_t target) noexcept {
    destination[0]=0xff;
    destination[1]=0x25;
    memset(destination+2,0,4);
    memcpy(destination+6,&target,sizeof(target));
}

static unsigned char* inbound_allocate_near() noexcept {
    const uintptr_t first=base+0x10000000u;
    for (unsigned index=0;index<2048;++index) {
        const uintptr_t desired=first+static_cast<uintptr_t>(index)*0x100000u;
        void* memory=VirtualAlloc(reinterpret_cast<void*>(desired),kNearBlockBytes,
            MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
        if (!memory) continue;
        const uintptr_t address=reinterpret_cast<uintptr_t>(memory);
        int32_t unused=0;
        if (address>=base && address-base<=0xffffffffull
            && inbound_rel32(base+kPredicateCallRva+5,address+kRelayOffset,unused))
            return static_cast<unsigned char*>(memory);
        VirtualFree(memory,0,MEM_RELEASE);
    }
    return nullptr;
}

static bool inbound_register_unwind(unsigned char* trampoline) noexcept {
    DWORD64 image_base=0;
    PRUNTIME_FUNCTION parent=RtlLookupFunctionEntry(
        static_cast<DWORD64>(base+kParentExecutorRva),&image_base,nullptr);
    if (!parent || image_base!=static_cast<DWORD64>(base)) return false;
    unsigned char prologue=0;
    if (!read(base+parent->UnwindData+1,prologue)) return false;
    const uintptr_t trampoline_rva=reinterpret_cast<uintptr_t>(trampoline)-base;
    const uintptr_t prefix=static_cast<uintptr_t>(prologue)+0x10u;
    if (trampoline_rva<=prefix || trampoline_rva+inbound_trampoline_size>0xffffffffull)
        return false;
    inbound_runtime_function.BeginAddress=static_cast<DWORD>(trampoline_rva-prefix);
    inbound_runtime_function.EndAddress=static_cast<DWORD>(trampoline_rva+inbound_trampoline_size);
    // Reuse the complete 4e7c80 unwind recipe.  The registration range starts
    // before the trampoline entry so RtlVirtualUnwind sees a body PC, not the
    // parent's prologue window.
    inbound_runtime_function.UnwindData=parent->UnwindData;
    if (!RtlAddFunctionTable(&inbound_runtime_function,1,static_cast<DWORD64>(base)))
        return false;
    inbound_runtime_registered=true;
    return true;
}

static void inbound_release_unpublished() noexcept {
    if (inbound_runtime_registered && !inbound_published) {
        RtlDeleteFunctionTable(&inbound_runtime_function);
        inbound_runtime_registered=false;
    }
    if (inbound_block && !inbound_published) {
        VirtualFree(inbound_block,0,MEM_RELEASE);
        inbound_block=nullptr;
        inbound_relay=nullptr;
        inbound_trampoline=nullptr;
    }
}

static void inbound_queue(const InboundOfferEvent& event) noexcept {
    if (!TryAcquireSRWLockExclusive(&inbound_lock)) {
        InterlockedIncrement(&inbound_dropped); return;
    }
    if (inbound_size<kQueueCapacity) {
        inbound_events[(inbound_head+inbound_size)%kQueueCapacity]=event;
        ++inbound_size;
    } else InterlockedIncrement(&inbound_dropped);
    ReleaseSRWLockExclusive(&inbound_lock);
}

static bool inbound_read_queue(uintptr_t country,InboundScope& scope,
    InboundOfferEvent& event) noexcept {
    uintptr_t head=0,tail=0;
    uint32_t count=0;
    if (!read(country+0x18d8,head) || !read(country+0x18e0,tail)
        || !read(country+0x18e8,count) || count>kQueueCapacity) return false;
    event.queue_before=scope.before_count;
    event.queue_after=count;
    event.queue_readable=true;
    if (count==0) {
        event.list_integrity=head==0 && tail==0;
        return event.list_integrity;
    }
    if (!head || !tail) return false;
    uintptr_t node=head,last=0;
    for (uint32_t index=0;index<count && node;++index) {
        uintptr_t clone=0,next=0;
        if (!read(node,clone) || !read(node+0x10,next)) return false;
        last=node;
        node=next;
    }
    event.list_integrity=node==0 && last==tail;
    if (!event.list_integrity) return false;
    if (scope.before_count==0xffffffffu || count!=scope.before_count+1
        || tail==scope.before_tail) return true;
    uintptr_t previous=0,clone=0;
    if (!read(tail+0x08,previous) || !read(tail,clone)
        || (scope.before_count ? previous!=scope.before_tail : previous!=0)) return true;
    event.new_entry=true;
    LifecycleActionShape shape=lifecycle_capture_shape(reinterpret_cast<void*>(clone));
    const bool peace_payload_match=shape.peace_offer==scope.peace_offer
        && (shape.peace_offer
            ? shape.peace.valid() && scope.peace.valid() && shape.peace==scope.peace
            : shape.peace.empty() && scope.peace.empty());
    if (!shape.matched || !shape.handles_canonical || shape.guarantee || shape.insult
        || shape.declare_war || !peace_payload_match
        || shape.royal_marriage!=scope.royal_marriage
        || shape.support_independence!=scope.support_independence
        || shape.military_access!=scope.military_access
        || shape.vassalization!=scope.vassalization
        || shape.extra60!=scope.extra60 || shape.extra60!=0 || shape.variant38!=1
        || shape.state34!=0 || shape.actor10!=scope.actor
        || shape.recipient20!=scope.recipient || shape.mirror18!=scope.actor) return true;
    event.payload_readable=true;
    event.decision_country_verified=scope.country!=0
        && inbound_is_fra(shape.recipient20,scope.country);
    event.source_verified=scope.call_redirected && event.decision_country_verified;
    inbound_tag(event.actor,shape.actor10);
    inbound_tag(event.mirror,shape.mirror18);
    inbound_tag(event.recipient,shape.recipient20);
    event.date28=shape.date28;
    event.date2c=shape.date2c;
    event.envoy30=shape.envoy30;
    event.state34=shape.state34;
    event.variant38=shape.variant38;
    event.royal_marriage=shape.royal_marriage;
    event.support_independence=shape.support_independence;
    event.military_access=shape.military_access;
    event.vassalization=shape.vassalization;
    event.peace_offer=shape.peace_offer;
    event.peace=shape.peace;
    event.extra60=shape.extra60;
    event.proposal3c=shape.proposal3c;
    event.token3c=static_cast<uint32_t>(shape.proposal3c);
    event.created2c=shape.date2c;
    inbound_pending_record_new(scope,event,tail,clone,shape);
    return true;
}

static bool inbound_pending_find_locked(uint64_t proposal_id,const char* actor,
    InboundPendingView& view,bool reserve) noexcept {
    for (auto& record:inbound_pending_records) {
        if (!record.active || record.proposal_id!=proposal_id
            || !inbound_tag_matches(record.actor,actor)) continue;
        LifecycleActionShape current{};
        if (!inbound_pending_queue_valid_locked(record,current)) {
            record.active=false;
            record.response_reserved=false;
            return false;
        }
        if (reserve && (record.response_reserved || record.response_submitted)) return false;
        if (reserve) record.response_reserved=true;
        inbound_pending_copy(record,view);
        return true;
    }
    return false;
}

static bool inbound_pending_lookup(uint64_t proposal_id,const char* actor,
    InboundPendingView& view) noexcept {
    view=InboundPendingView{};
    if (!TryAcquireSRWLockExclusive(&inbound_pending_lock)) return false;
    const bool found=inbound_pending_find_locked(proposal_id,actor,view,false);
    ReleaseSRWLockExclusive(&inbound_pending_lock);
    return found;
}

static bool inbound_pending_reserve(uint64_t proposal_id,const char* actor,
    InboundPendingView& view) noexcept {
    view=InboundPendingView{};
    if (!TryAcquireSRWLockExclusive(&inbound_pending_lock)) return false;
    const bool found=inbound_pending_find_locked(proposal_id,actor,view,true);
    ReleaseSRWLockExclusive(&inbound_pending_lock);
    return found;
}

static void inbound_pending_release(uint64_t proposal_id,uint64_t generation) noexcept {
    if (!TryAcquireSRWLockExclusive(&inbound_pending_lock)) return;
    for (auto& record:inbound_pending_records) {
        if (record.active && record.proposal_id==proposal_id
            && record.generation==generation && record.response_reserved
            && !record.response_submitted) {
            record.response_reserved=false;
            break;
        }
    }
    ReleaseSRWLockExclusive(&inbound_pending_lock);
}

static bool inbound_pending_commit(uint64_t proposal_id,uint64_t generation) noexcept {
    if (!TryAcquireSRWLockExclusive(&inbound_pending_lock)) return false;
    bool committed=false;
    for (auto& record:inbound_pending_records) {
        if (record.active && record.proposal_id==proposal_id
            && record.generation==generation && record.response_reserved
            && !record.response_submitted) {
            record.response_submitted=true;
            committed=true;
            break;
        }
    }
    ReleaseSRWLockExclusive(&inbound_pending_lock);
    return committed;
}

static bool inbound_pending_is_active(uint64_t proposal_id,uint64_t generation,
    bool& active) noexcept {
    active=false;
    if (!TryAcquireSRWLockExclusive(&inbound_pending_lock)) return false;
    for (auto& record:inbound_pending_records) {
        if (record.proposal_id!=proposal_id || record.generation!=generation) continue;
        // Only a complete native list observation proves removal.  A stale
        // payload, destructor tombstone or failed read is not that proof.
        uintptr_t country=0,head=0,tail=0;
        uint32_t count=0;
        if (!inbound_is_fra(record.recipient,country) || country!=record.country
            || !read(country+0x18d8,head) || !read(country+0x18e0,tail)
            || !read(country+0x18e8,count)) {
            ReleaseSRWLockExclusive(&inbound_pending_lock);
            return false;
        }
        using Membership=bridge::alliance_pending_membership::Result;
        const Membership membership=bridge::alliance_pending_membership::inspect(
            head,tail,count,record.node,record.clone,kQueueCapacity,
            [](uintptr_t address,uintptr_t& value) noexcept { return read(address,value); });
        if (membership==Membership::unknown) {
            ReleaseSRWLockExclusive(&inbound_pending_lock);
            return false;
        }
        active=membership==Membership::present;
        if (!active) {
            record.active=false;
            record.response_reserved=false;
        }
        ReleaseSRWLockExclusive(&inbound_pending_lock);
        return true;
    }
    ReleaseSRWLockExclusive(&inbound_pending_lock);
    return false;
}

static void bridge_inbound_pending_destroyed(void* source,
    const LifecycleActionShape& snapshot,unsigned flags) noexcept {
    (void)source; (void)flags;
    if (!snapshot.readable || snapshot.state34!=0 || snapshot.variant38!=1) return;
    if (!TryAcquireSRWLockExclusive(&inbound_pending_lock)) return;
    for (auto& record:inbound_pending_records) {
        if (record.active && record.action==snapshot.address
            && inbound_pending_shape_matches(record,snapshot)) {
            record.active=false;
            record.response_reserved=false;
            break;
        }
    }
    ReleaseSRWLockExclusive(&inbound_pending_lock);
}

extern "C" void bridge_inbound_scope_begin(void* action,uint64_t actor,
    uint64_t recipient,int32_t state,unsigned char variant) noexcept {
    InboundScope next{};
    next.action=reinterpret_cast<uintptr_t>(action);
    next.actor=actor;
    next.recipient=recipient;
    uintptr_t country=0;
    uintptr_t actor_country=0;
    LifecycleActionShape shape=lifecycle_capture_shape(action);
    next.royal_marriage=shape.royal_marriage;
    next.support_independence=shape.support_independence;
    next.military_access=shape.military_access;
    next.vassalization=shape.vassalization;
    next.peace_offer=shape.peace_offer;
    next.peace=shape.peace;
    next.extra60=shape.extra60;
    const bool exact=shape.matched && shape.handles_canonical
        && !shape.improve_relations && !shape.spy_network && !shape.guarantee && !shape.insult
        && !shape.declare_war
        && (shape.peace_offer ? shape.peace.valid() : shape.peace.empty())
        && shape.address==next.action && shape.actor10==actor
        && shape.recipient20==recipient && shape.state34==state
        && shape.variant38==variant && variant==1 && state==0 && shape.extra60==0
        && actor!=recipient && inbound_read_country(actor,actor_country)
        && inbound_is_fra(recipient,country);
    if (exact) {
        next.active=true;
        next.country=country;
        next.before_readable=read(country+0x18e0,next.before_tail)
            && read(country+0x18e8,next.before_count)
            && next.before_count<=kQueueCapacity;
    }
    inbound_scope=next;
}

extern "C" bool bridge_inbound_scope_active() noexcept {
    return inbound_scope.active;
}

// Root's response/handler path may only forward a Peace action after the
// generic inbound classifier has established the same scope.  The full native
// offer is compared by value; scope.active alone is deliberately insufficient.
extern "C" bool bridge_inbound_scope_matches(void* action) noexcept {
    if (!inbound_scope.active || !inbound_scope.call_redirected || !action
        || reinterpret_cast<uintptr_t>(action)!=inbound_scope.action) return false;
    const LifecycleActionShape shape=lifecycle_capture_shape(action);
    if (!shape.readable || !shape.matched || !shape.handles_canonical
        || shape.address!=inbound_scope.action || shape.declare_war
        || shape.actor10!=inbound_scope.actor
        || shape.mirror18!=shape.actor10
        || shape.recipient20!=inbound_scope.recipient
        || shape.state34!=0 || shape.variant38!=1
        || shape.extra60!=0
        || shape.royal_marriage!=inbound_scope.royal_marriage
        || shape.support_independence!=inbound_scope.support_independence
        || shape.military_access!=inbound_scope.military_access
        || shape.vassalization!=inbound_scope.vassalization
        || shape.peace_offer!=inbound_scope.peace_offer
        || shape.extra60!=inbound_scope.extra60) return false;
    return shape.peace_offer
        ? shape.peace.valid() && inbound_scope.peace.valid()
            && shape.peace==inbound_scope.peace
        : shape.peace.empty() && inbound_scope.peace.empty();
}

extern "C" void bridge_inbound_scope_end() noexcept {
    inbound_scope=InboundScope{};
}

static bool inbound_hold_known_pending(const LifecycleActionShape& shape,
    uintptr_t country,uintptr_t command,uintptr_t caller_return_rva) noexcept {
    const uintptr_t action=shape.address;
    if (shape.proposal3c!=0 && TryAcquireSRWLockExclusive(&inbound_pending_lock)) {
        for (auto& record:inbound_pending_records) {
            if (!record.active || record.action!=action || record.country!=country
                || !inbound_pending_shape_matches(record,shape)) continue;
            LifecycleActionShape current{};
            if (!inbound_pending_queue_valid_locked(record,current)) continue;
            ++record.ai_hold_count;
            uintptr_t game=0; int32_t date=0;
            if (read(base+0x233fe58,game) && read(game+0x1dd0,date)
                && date!=record.ai_hold_last_date) {
                record.ai_hold_last_date=date;
                InboundAiHoldEvent event{record.proposal_id,record.generation,
                    command,action,record.token3c,record.ai_hold_count,date,
                    GetCurrentThreadId(),record.royal_marriage,record.support_independence,
                    record.military_access,record.vassalization,record.peace_offer,
                    caller_return_rva};
                if (TryAcquireSRWLockExclusive(&inbound_lock)) {
                    if (inbound_hold_size<kQueueCapacity) {
                        inbound_hold_events[(inbound_hold_head+inbound_hold_size)%kQueueCapacity]=event;
                        ++inbound_hold_size;
                    } else InterlockedIncrement(&inbound_hold_dropped);
                    ReleaseSRWLockExclusive(&inbound_lock);
                } else InterlockedIncrement(&inbound_hold_dropped);
            }
            ReleaseSRWLockExclusive(&inbound_pending_lock);
            return true;
        }
        ReleaseSRWLockExclusive(&inbound_pending_lock);
    }
    return false;
}

// The actual daily AI loop is FUN_1400b0fa0, independently observed cloning
// pending negotiated objects at return RVA 0xb22b9.  Its +0xd0 call returns to
// 0xb22a3; false advances the native iterator without choosing a response.
// Each hooked family retains its own original; other callers receive native behavior.
static unsigned char inbound_negotiated_pending_choice(void* action) noexcept {
    const uintptr_t caller=reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    if (caller==base+0xb22a3) {
        const LifecycleActionShape shape=lifecycle_capture_shape(action);
        uintptr_t country=0;
        if (shape.matched && shape.handles_canonical && (shape.royal_marriage || shape.support_independence || shape.military_access || shape.vassalization || shape.peace_offer)
            && !shape.declare_war
            && (shape.peace_offer ? shape.peace.valid() : shape.peace.empty())
            && shape.extra60==0 && shape.variant38==1 && shape.state34==0
            && inbound_is_fra(shape.recipient20,country)
            && inbound_hold_known_pending(shape,country,0,0xb22a3)) return 0;
    }
    uintptr_t vtable=0;
    read(reinterpret_cast<uintptr_t>(action),vtable);
    const InboundChoicePredicate original=vtable==base+lifecycle_peace_vtable_rva
        ? inbound_peace_choice_original:vtable==base+lifecycle_vassalization_vtable_rva
        ? inbound_vassal_choice_original:vtable==base+lifecycle_military_access_vtable_rva
        ? inbound_military_choice_original:vtable==base+lifecycle_support_vtable_rva
        ? inbound_support_choice_original:inbound_royal_choice_original;
    return original ? original(action) : 0;
}

extern "C" unsigned char bridge_inbound_predicate_classify(
    uintptr_t caller_return,uintptr_t action,uintptr_t command,
    uintptr_t recipient_country) noexcept {
    if (caller_return!=base+kPredicateReturnRva) return 0;
    uintptr_t command_vtable=0,command_action=0;
    const LifecycleActionShape shape=lifecycle_capture_shape(
        reinterpret_cast<void*>(action));
    if (!shape.matched || !shape.handles_canonical || shape.guarantee || shape.insult
        || shape.declare_war
        || (shape.peace_offer ? !shape.peace.valid() : !shape.peace.empty())
        || shape.state34!=0
        || shape.variant38!=1 || shape.extra60!=0
        || !read(command,command_vtable)
        || command_vtable!=base+lifecycle_generic_wrapper_vtable_rva
        || !read(command+0x50,command_action) || command_action!=action) return 0;
    uintptr_t country=0;
    if (!inbound_is_fra(shape.recipient20,country)
        || country!=recipient_country) return 0;
    // This command path is separate from the daily pending loop above.
    if (inbound_hold_known_pending(shape,country,command,kPredicateReturnRva)) return 2;
    if (!inbound_scope.active || inbound_scope.action!=action
        || inbound_scope.country!=country
        || inbound_scope.actor!=shape.actor10
        || inbound_scope.recipient!=shape.recipient20
        || inbound_scope.royal_marriage!=shape.royal_marriage
        || inbound_scope.support_independence!=shape.support_independence
        || inbound_scope.military_access!=shape.military_access
        || inbound_scope.vassalization!=shape.vassalization
        || inbound_scope.peace_offer!=shape.peace_offer
        || (shape.peace_offer
            ? !inbound_scope.peace.valid() || inbound_scope.peace!=shape.peace
            : !shape.peace.empty())
        || inbound_scope.extra60!=shape.extra60) return 0;
    inbound_scope.call_redirected=true;
    return 1;
}

extern "C" void bridge_inbound_observe_pending() noexcept {
    if (!inbound_scope.active) return;
    InboundOfferEvent event{};
    event.proposal_id=static_cast<uint64_t>(InterlockedIncrement64(&inbound_sequence));
    event.royal_marriage=inbound_scope.royal_marriage;
    event.support_independence=inbound_scope.support_independence;
    event.military_access=inbound_scope.military_access;
    event.vassalization=inbound_scope.vassalization;
    event.peace_offer=inbound_scope.peace_offer;
    event.peace=inbound_scope.peace;
    event.extra60=inbound_scope.extra60;
    event.source_verified=inbound_scope.call_redirected;
    event.decision_country_verified=inbound_scope.country!=0
        && inbound_is_fra(inbound_scope.recipient,inbound_scope.country);
    if (!inbound_scope.before_readable) {
        inbound_queue(event); return;
    }
    if (!inbound_read_queue(inbound_scope.country,inbound_scope,event)) {
        inbound_queue(event); return;
    }
    inbound_queue(event);
}

static void inbound_test_failure(const char* reason) noexcept {
    char message[360];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_inbound_test_failed\",\"session_id\":\"%lu-%llx\",\"reason\":\"%.180s\",\"submitted\":false,\"business_result\":\"unknown\"}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),reason?reason:"unknown");
    line(message);
}

static bool inbound_test_context(uintptr_t& game,int32_t& date,
    uint64_t& player) noexcept {
    if (thread_changed || !frame_thread || frame_thread!=GetCurrentThreadId()
        || !control_ready() || !read(base+0x233fe58,game)
        || !read(game+0x1dd0,date) || !read(game+0x1e60,player)
        || static_cast<uint32_t>(player&0xffffffu)!=0x524f50u
        || static_cast<unsigned>((player>>32)&0xffffu)!=189) return false;
    uintptr_t server=0,server_vtable=0,get_pause=0,pause=0;
    unsigned char paused=0;
    if (!read(game+0x1e00,server) || !read(server,server_vtable)
        || !read(server_vtable+0x100,get_pause)
        || get_pause<base+0x1000 || get_pause>=base+0x1c00000) return false;
    pause=reinterpret_cast<uintptr_t (*)(void*)>(get_pause)(
        reinterpret_cast<void*>(server));
    return pause>=0x10000 && read(pause+0x48,paused) && paused==1;
}

static bool inbound_test_native_send(bool marriage,bool support=false,
    const char* source_tag="SAV",bool military=false,bool vassalization=false) noexcept {
    uintptr_t game=0; int32_t date=0; uint64_t player=0;
    if (!inbound_test_context(game,date,player)) {
        inbound_test_failure("POR_PAUSED_READY_REQUIRED"); return false;
    }
    uint64_t source=0,recipient=0;
    uintptr_t source_country=0,recipient_country=0;
    if (!alliance_query_country(source_tag,source)
        || !alliance_query_country("FRA",recipient)
        || !inbound_read_country(source,source_country)
        || !inbound_is_fra(recipient,recipient_country)
        || source==recipient) {
        inbound_test_failure("COUNTRY_IDENTITY_UNAVAILABLE"); return false;
    }
    uintptr_t display=0,validity=0,initiation=0,requires_diplomat=0;
    const FactoryActionQueryMethods* negotiated=vassalization?&vassal_query_methods:
        military?&military_query_methods:support?&support_query_methods:nullptr;
    const uintptr_t expected_vtable=base+(negotiated?negotiated->vtable_rva:marriage?0x1c80ab0:0x1c80720);
    if (!read(expected_vtable+0x88,display) || display!=base+(negotiated?negotiated->display_rva:marriage?0x4ef7e0:0x512ca0)
        || !read(expected_vtable+0x80,validity)
        || (validity!=base+(negotiated?negotiated->validity_rva:marriage?0x4ef3e0:0x511d90)
            && (negotiated || marriage || validity!=reinterpret_cast<uintptr_t>(&observation_alliance_validity)))
        || !read(expected_vtable+0x90,initiation)
        || initiation!=base+(negotiated||marriage?0x4e9b40:0x512a00)
        || !read(expected_vtable+0x100,requires_diplomat)
        || requires_diplomat!=base+0x8f440) {
        inbound_test_failure("NATIVE_METHOD_IDENTITY_CHANGED"); return false;
    }
    bool visible=false;
    unsigned available=0;
    const bool visibility_read=negotiated?factory_query_visibility(source,recipient,true,visible,*negotiated)
        :alliance_query_visibility(source,recipient,true,visible,marriage?0x28df:0x293d);
    if (!visibility_read || !visible
        || !alliance_query_diplomats(source,available)) {
        inbound_test_failure("NATIVE_VISIBILITY_OR_DIPLOMAT_UNAVAILABLE"); return false;
    }
    alignas(16) unsigned char storage[0x58]{};
    unsigned char* action=storage;
    bool action_constructed=false;
    void* wrapper=nullptr;
    auto fail_after_construct=[&](const char* reason) noexcept {
        alliance_execution_detail::execution_release_constructed(
            wrapper,action,action_constructed);
        inbound_test_failure(reason); return false;
    };
    if (marriage || negotiated) {
        using UiCreator=void* (*)(void*,int32_t,uint64_t,unsigned char,void*);
        action=static_cast<unsigned char*>(reinterpret_cast<UiCreator>(base+0x35a8b0)(
            reinterpret_cast<void*>(source_country),negotiated?negotiated->selector:0x28df,recipient,1,nullptr));
        if (!action) return fail_after_construct("UI_CREATOR_FAILED");
    } else {
        using Constructor=void* (*)(void*,uint64_t,uint64_t,int32_t);
        reinterpret_cast<Constructor>(base+0x50f780)(action,source,recipient,date);
    }
    action_constructed=true;
    LifecycleActionShape action_shape=lifecycle_capture_shape(action);
    if (!action_shape.matched || !action_shape.handles_canonical
        || action_shape.actor10!=source || action_shape.mirror18!=source
        || action_shape.recipient20!=recipient || action_shape.state34!=0
        || action_shape.variant38!=1 || action_shape.royal_marriage!=marriage
        || action_shape.support_independence!=support
        || action_shape.military_access!=military
        || action_shape.vassalization!=vassalization
        || action_shape.extra60!=0) return fail_after_construct("ACTION_SHAPE_INVALID");
    if (marriage || negotiated) {
        std::memcpy(action+0x28,&date,sizeof(date));
        std::memcpy(action+0x2c,&date,sizeof(date));
    }
    using Predicate=bool (*)(void*,void*,unsigned char);
    const bool common=vassalization?reinterpret_cast<bool (*)(void*,void*)>(display)(action,nullptr)
        :reinterpret_cast<Predicate>(display)(action,nullptr,0);
    const bool native_valid=vassalization?reinterpret_cast<bool (*)(void*,void*)>(validity)(action,nullptr)
        :reinterpret_cast<Predicate>(validity)(action,nullptr,0);
    const bool init_ok=reinterpret_cast<Predicate>(initiation)(action,nullptr,0);
    const bool needs_diplomat=reinterpret_cast<bool (*)(void*)>(
        requires_diplomat)(action);
    if (!common || !native_valid || !init_ok || (needs_diplomat && !available))
        return fail_after_construct("NATIVE_SOURCE_TO_FRA_REJECTED");
    uintptr_t action_vtable=0,wrapper_slot=0;
    if (!read(reinterpret_cast<uintptr_t>(action),action_vtable)
        || action_vtable!=expected_vtable
        || !read(action_vtable+0x40,wrapper_slot)
        || (wrapper_slot!=base+0x4e9960
            && wrapper_slot!=reinterpret_cast<uintptr_t>(&lifecycle_wrapper_observe)))
        return fail_after_construct("WRAPPER_SLOT_IDENTITY_CHANGED");
    using Wrapper=void* (*)(void*,void**);
    if (!reinterpret_cast<Wrapper>(base+0x4e9960)(action,&wrapper) || !wrapper)
        return fail_after_construct("NATIVE_WRAPPER_FAILED");
    ProtocolWrapperShape source_shape=protocol_capture(wrapper);
    if (!source_shape.identity || !source_shape.readable
        || !source_shape.prefix_readable || !source_shape.payload.matched
        || source_shape.payload.actor10!=source
        || source_shape.payload.mirror18!=source
        || source_shape.payload.recipient20!=recipient
        || source_shape.payload.state34!=0 || source_shape.payload.variant38!=1)
        return fail_after_construct("WRAPPER_PAYLOAD_INVALID");
    uintptr_t dispatcher=0,transport=0;
    if (!alliance_execution_detail::execution_world_dispatcher(
            dispatcher,transport) || !dispatcher || !transport)
        return fail_after_construct("WORLD_DISPATCHER_UNAVAILABLE");
    void* outgoing=wrapper;
    using Submit=bool (*)(void*,void**);
    const bool accepted=reinterpret_cast<Submit>(base+0x14ca110)(
        reinterpret_cast<void*>(dispatcher),&outgoing);
    // This channel deliberately has no sender scope, ledger seed, or AI
    // decision.  The native dispatcher owns the wrapper after this call;
    // only the stack action remains ours to destroy.
    if (action_constructed) {
        alliance_execution_detail::execution_release_constructed(nullptr,action,true);
        action_constructed=false;
    }
    if (!accepted) {
        inbound_test_failure("NATIVE_DISPATCH_REJECTED"); return false;
    }
    char message[768];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_alliance_inbound_test_submitted\",\"session_id\":\"%lu-%llx\",\"source\":\"%.3s\",\"recipient\":\"FRA\",\"phase\":\"initiate\",\"date_raw\":%d,\"submitted\":true,\"dispatcher_accepted\":true,\"native_queue_verified\":false,\"business_result\":\"unknown\",\"defer_observation_expected\":true}\n",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation),source_tag,date);
    line(message);
    return true;
}

static void inbound_test_tick() noexcept {
    if (inbound_test_consumed || !inbound_test_request_path[0]
        || GetFileAttributesW(inbound_test_request_path)==INVALID_FILE_ATTRIBUTES)
        return;
    constexpr char expected[]="TEST_ONLY SAV_TO_FRA\n";
    constexpr char royal[]="TEST_ONLY SAV_ROYAL_TO_FRA\n";
    char wire[64]{};
    HANDLE file=CreateFileW(inbound_test_request_path,GENERIC_READ,
        FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return;
    DWORD size=GetFileSize(file,nullptr),got=0;
    const bool read_ok=size<sizeof(wire)
        && ReadFile(file,wire,size,&got,nullptr) && got==size;
    CloseHandle(file);
    inbound_test_consumed=true;
    DeleteFileW(inbound_test_request_path);
    const bool marriage=read_ok && size==sizeof(royal)-1
        && !memcmp(wire,royal,sizeof(royal)-1);
    const bool alliance=read_ok && size==sizeof(expected)-1
        && !memcmp(wire,expected,sizeof(expected)-1);
    char support_actor[4]{}; int consumed=0;
    const bool support=read_ok && sscanf(wire,"TEST_ONLY SUPPORT_TO_FRA %3s%n",support_actor,&consumed)==1
        && strcmp(wire+consumed,"\n")==0 && strlen(support_actor)==3;
    char military_actor[4]{}; int military_consumed=0;
    const bool military=read_ok && sscanf(wire,"TEST_ONLY MILITARY_ACCESS_TO_FRA %3s%n",military_actor,&military_consumed)==1
        && strcmp(wire+military_consumed,"\n")==0 && strlen(military_actor)==3;
    char vassal_actor[4]{}; int vassal_consumed=0;
    const bool vassalization=read_ok && sscanf(wire,"TEST_ONLY VASSALIZATION_TO_FRA %3s%n",vassal_actor,&vassal_consumed)==1
        && strcmp(wire+vassal_consumed,"\n")==0 && strlen(vassal_actor)==3;
    if (!alliance && !marriage && !support && !military && !vassalization) {
        inbound_test_failure("TEST_WIRE_INVALID"); return;
    }
    inbound_test_native_send(marriage,support,
        vassalization?vassal_actor:military?military_actor:support?support_actor:"SAV",
        military,vassalization);
}

static bool inbound_set_test_path(const wchar_t* directory) noexcept {
    inbound_test_request_path[0]=0;
    inbound_test_consumed=false;
    if (!directory || !directory[0]) return false;
    const int written=swprintf(inbound_test_request_path,MAX_PATH,
        L"%ls\\alliance-inbound-test.req",directory);
    if (written<0 || written>=MAX_PATH) {
        inbound_test_request_path[0]=0;
        return false;
    }
    if (GetFileAttributesW(inbound_test_request_path)!=INVALID_FILE_ATTRIBUTES
        && !DeleteFileW(inbound_test_request_path)) {
        inbound_test_request_path[0]=0;
        return false;
    }
    return true;
}

static void inbound_flush() noexcept {
    for (unsigned index=0;index<16;++index) {
        InboundAiHoldEvent event{};
        AcquireSRWLockExclusive(&inbound_lock);
        if (!inbound_hold_size) { ReleaseSRWLockExclusive(&inbound_lock); break; }
        event=inbound_hold_events[inbound_hold_head];
        inbound_hold_head=(inbound_hold_head+1)%kQueueCapacity;
        --inbound_hold_size;
        ReleaseSRWLockExclusive(&inbound_lock);
        char message[760];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_diplomacy_inbound_ai_choice_held\",\"session_id\":\"%lu-%llx\",\"proposal_id\":%llu,\"generation\":%llu,\"action_id\":\"%s\",\"decision_country\":\"FRA\",\"date_raw\":%d,\"token3c\":%u,\"hold_count\":%u,\"command\":\"0x%llx\",\"action\":\"0x%llx\",\"thread\":%lu,\"caller_return_rva\":\"0x%llx\",\"native_queue_verified\":true,\"native_ai_choice_skipped\":true}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(event.proposal_id),
            static_cast<unsigned long long>(event.generation),
            event.peace_offer?"peace_offer":event.vassalization?"offer_vassalization":event.military_access?"ask_military_access":event.support_independence?"support_independence":event.royal_marriage?"offer_royal_marriage":"offer_alliance",
            event.date,static_cast<unsigned>(event.token3c),
            static_cast<unsigned>(event.hold_count),
            static_cast<unsigned long long>(event.command),
            static_cast<unsigned long long>(event.action),
            static_cast<unsigned long>(event.thread),
            static_cast<unsigned long long>(event.caller_return_rva));
        line(message);
    }
    const LONG hold_dropped=InterlockedExchange(&inbound_hold_dropped,0);
    if (hold_dropped) {
        char message[180];
        snprintf(message,sizeof(message),"{\"event\":\"native_diplomacy_inbound_ai_hold_drop\",\"dropped\":%ld,\"complete\":false}\n",static_cast<long>(hold_dropped));
        line(message);
    }
    for (unsigned index=0;index<16;++index) {
        InboundOfferEvent event{};
        AcquireSRWLockExclusive(&inbound_lock);
        if (!inbound_size) { ReleaseSRWLockExclusive(&inbound_lock); break; }
        event=inbound_events[inbound_head];
        inbound_head=(inbound_head+1)%kQueueCapacity;
        --inbound_size;
        ReleaseSRWLockExclusive(&inbound_lock);
        char peace_json[256]{};
        if (event.peace_offer)
            lifecycle_peace_payload_json(peace_json,sizeof(peace_json),event.peace);
        else memcpy(peace_json,"null",5);
        char message[1500];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_alliance_inbound_offer\",\"session_id\":\"%lu-%llx\",\"proposal_id\":%llu,\"action_id\":\"%s\",\"family\":\"%s\",\"peace\":%s,\"extra60\":%u,\"phase\":\"initiate\",\"actor\":\"%.3s\",\"mirror\":\"%.3s\",\"recipient\":\"%.3s\",\"date28\":%d,\"date2c\":%d,\"envoy30\":%d,\"state34\":%d,\"variant38\":%u,\"proposal3c\":%d,\"token3c\":%u,\"created2c\":%d,\"queue_before_count\":%u,\"queue_after_count\":%u,\"queue_readable\":%s,\"list_integrity\":%s,\"new_entry\":%s,\"payload_readable\":%s,\"decision_country\":\"FRA\",\"decision_country_verified\":%s,\"pending_source\":\"native_executor_pending_block\",\"source_verified\":%s,\"call_redirected\":%s,\"business_result\":\"pending_observed\"}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),
            static_cast<unsigned long long>(event.proposal_id),
            event.peace_offer?"peace_offer":event.vassalization?"offer_vassalization":event.military_access?"ask_military_access":event.support_independence?"support_independence":event.royal_marriage?"offer_royal_marriage":"offer_alliance",
            event.peace_offer?"peace":event.vassalization?"vassalization":event.military_access?"military_access":event.support_independence?"support_independence":event.royal_marriage?"royal_marriage":"alliance",peace_json,static_cast<unsigned>(event.extra60),event.actor,event.mirror,event.recipient,
            event.date28,event.date2c,event.envoy30,event.state34,
            static_cast<unsigned>(event.variant38),event.proposal3c,
            static_cast<unsigned>(event.token3c),event.created2c,event.queue_before,event.queue_after,
            event.queue_readable?"true":"false",event.list_integrity?"true":"false",
            event.new_entry?"true":"false",event.payload_readable?"true":"false",
            event.decision_country_verified?"true":"false",event.source_verified?"true":"false",
            event.source_verified?"true":"false");
        line(message);
    }
    LONG dropped=InterlockedExchange(&inbound_dropped,0);
    if (dropped) {
        char message[180];
        snprintf(message,sizeof(message),"{\"event\":\"native_alliance_inbound_offer_drop\",\"dropped\":%ld,\"complete\":false}\n",static_cast<long>(dropped));
        line(message);
    }
}

static bool inbound_install_choice(uintptr_t vtable_rva,uintptr_t method_rva,
    const unsigned char* expected,SIZE_T size,InboundChoicePredicate& original,
    bool& installed) noexcept {
    void** slot=reinterpret_cast<void**>(base+vtable_rva+0xd0);
    void* actual=nullptr; unsigned char bytes[24]{}; SIZE_T got=0;
    if (size>sizeof(bytes) || !read(reinterpret_cast<uintptr_t>(slot),actual)
        || actual!=reinterpret_cast<void*>(base+method_rva)
        || !ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(base+method_rva),bytes,size,&got)
        || got!=size || memcmp(bytes,expected,size)) return false;
    original=reinterpret_cast<InboundChoicePredicate>(actual);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    installed=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),
        reinterpret_cast<void*>(&inbound_negotiated_pending_choice),actual)==actual;
    const bool restored=VirtualProtect(slot,8,protection,&ignored)!=FALSE;
    if (!restored) lifecycle_rollback_incomplete=true;
    return installed && restored;
}

static bool inbound_rollback_choice(uintptr_t vtable_rva,InboundChoicePredicate original,
    bool& installed) noexcept {
    if (!installed) return true;
    void** slot=reinterpret_cast<void**>(base+vtable_rva+0xd0);
    DWORD protection=0,ignored=0;
    if (!VirtualProtect(slot,8,PAGE_READWRITE,&protection)) return false;
    void* previous=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),
        reinterpret_cast<void*>(original),reinterpret_cast<void*>(&inbound_negotiated_pending_choice));
    bool ok=previous==reinterpret_cast<void*>(&inbound_negotiated_pending_choice)
        || previous==reinterpret_cast<void*>(original);
    ok=(VirtualProtect(slot,8,protection,&ignored)!=FALSE) && ok;
    if (ok) installed=false;
    return ok;
}

static bool inbound_install() {
    auto target=reinterpret_cast<unsigned char*>(base+kPredicateCallRva);
    unsigned char actual[kPatchBytes]{};
    if (!read(reinterpret_cast<uintptr_t>(target),actual) || actual[0]!=0xe8) return false;
    int32_t original_displacement=0;
    memcpy(&original_displacement,actual+1,sizeof(original_displacement));
    const uintptr_t original_target=static_cast<uintptr_t>(
        static_cast<intptr_t>(reinterpret_cast<uintptr_t>(target)+kPatchBytes)
        +original_displacement);
    if (original_target!=base+kPredicateRva) return false;
    memcpy(inbound_expected,actual,kPatchBytes);
    bridge_inbound_predicate_original=reinterpret_cast<void*>(original_target);
    bridge_inbound_pending_target=base+kPendingTargetRva;
    inbound_block=inbound_allocate_near();
    if (!inbound_block) return false;
    inbound_relay=inbound_block+kRelayOffset;
    inbound_trampoline=inbound_block+kTrampolineOffset;
    inbound_absolute_jump(inbound_relay,reinterpret_cast<uintptr_t>(&bridge_inbound_predicate_stub));
    int32_t call_displacement=0;
    if (!inbound_rel32(reinterpret_cast<uintptr_t>(inbound_trampoline)+5,original_target,call_displacement)) {
        inbound_release_unpublished(); return false;
    }
    inbound_trampoline[0]=0xe8;
    memcpy(inbound_trampoline+1,&call_displacement,sizeof(call_displacement));
    inbound_absolute_jump(inbound_trampoline+5,base+kPredicateReturnRva);
    if (!inbound_register_unwind(inbound_trampoline)) {
        inbound_release_unpublished(); return false;
    }
    DWORD protection=0;
    if (!VirtualProtect(inbound_block,kNearBlockBytes,PAGE_EXECUTE_READ,&protection)) {
        inbound_release_unpublished(); return false;
    }
    FlushInstructionCache(GetCurrentProcess(),inbound_block,kNearBlockBytes);
    int32_t relay_displacement=0;
    if (!inbound_rel32(reinterpret_cast<uintptr_t>(target)+kPatchBytes,
        reinterpret_cast<uintptr_t>(inbound_relay),relay_displacement)) {
        inbound_release_unpublished(); return false;
    }
    // Preserve the real CALL ABI: the relay must be entered with 4e81bd
    // pushed on the stack so the classifier can distinguish this exact site.
    inbound_replacement[0]=0xe8;
    memcpy(inbound_replacement+1,&relay_displacement,sizeof(relay_displacement));
    inbound_patch_plan=bridge_entry_patch::PatchPlan{};
    inbound_patch_plan.count=1;
    inbound_patch_plan.targets[0]={target,kPatchBytes,inbound_expected,inbound_replacement,
        inbound_trampoline,inbound_trampoline_size};
    const auto result=bridge_entry_patch::guarded_patch_apply(inbound_patch_plan);
    inbound_published=result.published;
    inbound_installed=result.success;
    if (!result.success) {
        char message[420];
        snprintf(message,sizeof(message),"{\"event\":\"alliance_inbound_guarded_install_failed\",\"published\":%s,\"threads_resumed\":%s,\"rollback_complete\":%s,\"failure_stage\":%u,\"win32_error\":%lu,\"restart_required\":true}\n",
            result.published?"true":"false",result.threads_resumed?"true":"false",
            result.rollback_complete?"true":"false",static_cast<unsigned>(result.failure_stage),
            static_cast<unsigned long>(result.error));
        line(message);
        if (!result.published) inbound_release_unpublished();
    }
    if (!result.success) return false;
    const unsigned char royal_choice[5]={0x0f,0xb6,0x41,0x38,0xc3};
    const unsigned char support_choice[8]={0x80,0x79,0x38,0x00,0x0f,0x95,0xc0,0xc3};
    const unsigned char military_choice[18]={0x83,0x79,0x34,0x00,0x75,0x09,0x80,0x79,
        0x38,0x00,0x74,0x03,0xb0,0x01,0xc3,0x32,0xc0,0xc3};
    // Vassalization +0xd0 is the same confirmed native state/mode predicate
    // at RVA 0x51fac0: AL=1 only for state34==0 and mode38!=0.  The vtable
    // slot is checked independently so the Vassal family cannot borrow the
    // Military Access object identity.
    const unsigned char vassal_choice[18]={0x83,0x79,0x34,0x00,0x75,0x09,0x80,0x79,
        0x38,0x00,0x74,0x03,0xb0,0x01,0xc3,0x32,0xc0,0xc3};
    // Peace +0xd0 is the native common-gate predicate at RVA 0x59bb30.
    // Keep the original callback separate from every other family: its ABI
    // is the same one-argument predicate, but its native relation gate is
    // family-specific and must be restored independently.
    const unsigned char peace_choice[16]={0x48,0x83,0xec,0x28,0x83,0x79,0x34,0x00,
        0x75,0x53,0x48,0x8b,0x41,0x20,0x4c,0x8b};
    return inbound_install_choice(lifecycle_royal_vtable_rva,0x4e4d80,
            royal_choice,sizeof(royal_choice),inbound_royal_choice_original,inbound_royal_choice_installed)
        && inbound_install_choice(lifecycle_support_vtable_rva,0x50f150,
            support_choice,sizeof(support_choice),inbound_support_choice_original,inbound_support_choice_installed)
        && inbound_install_choice(lifecycle_military_access_vtable_rva,0x51fac0,
            military_choice,sizeof(military_choice),inbound_military_choice_original,inbound_military_choice_installed)
        && inbound_install_choice(lifecycle_vassalization_vtable_rva,0x51fac0,
            vassal_choice,sizeof(vassal_choice),inbound_vassal_choice_original,inbound_vassal_choice_installed)
        && inbound_install_choice(lifecycle_peace_vtable_rva,0x59bb30,
            peace_choice,sizeof(peace_choice),inbound_peace_choice_original,inbound_peace_choice_installed);
}

static bool inbound_rollback() {
    bridge_inbound_scope_end();
    const bool royal_ok=inbound_rollback_choice(lifecycle_royal_vtable_rva,
        inbound_royal_choice_original,inbound_royal_choice_installed);
    const bool support_ok=inbound_rollback_choice(lifecycle_support_vtable_rva,
        inbound_support_choice_original,inbound_support_choice_installed);
    const bool military_ok=inbound_rollback_choice(lifecycle_military_access_vtable_rva,
        inbound_military_choice_original,inbound_military_choice_installed);
    const bool vassal_ok=inbound_rollback_choice(lifecycle_vassalization_vtable_rva,
        inbound_vassal_choice_original,inbound_vassal_choice_installed);
    const bool peace_ok=inbound_rollback_choice(lifecycle_peace_vtable_rva,
        inbound_peace_choice_original,inbound_peace_choice_installed);
    const bool choice_ok=royal_ok && support_ok && military_ok && vassal_ok && peace_ok;
    if (!inbound_patch_plan.count) return choice_ok;
    unsigned char actual[kPatchBytes]{};
    auto target=reinterpret_cast<unsigned char*>(base+kPredicateCallRva);
    if (!read(reinterpret_cast<uintptr_t>(target),actual)) return false;
    if (!memcmp(actual,inbound_expected,kPatchBytes)) {
        inbound_installed=false; inbound_published=false; return choice_ok;
    }
    if (memcmp(actual,inbound_replacement,kPatchBytes)) return false;
    const auto result=bridge_entry_patch::guarded_patch_rollback(inbound_patch_plan);
    const bool ok=result.success && result.threads_resumed && result.protection_restored;
    if (ok) { inbound_installed=false; inbound_published=false; }
    return ok && choice_ok;
}

} // namespace bridge_alliance_inbound_detail

using bridge_alliance_inbound_detail::inbound_flush;
using bridge_alliance_inbound_detail::inbound_install;
using bridge_alliance_inbound_detail::inbound_rollback;
using bridge_alliance_inbound_detail::bridge_inbound_scope_begin;
using bridge_alliance_inbound_detail::bridge_inbound_scope_active;
using bridge_alliance_inbound_detail::bridge_inbound_scope_matches;
using bridge_alliance_inbound_detail::bridge_inbound_scope_end;
using bridge_alliance_inbound_detail::bridge_inbound_observe_pending;
using bridge_alliance_inbound_detail::bridge_inbound_pending_destroyed;
using bridge_alliance_inbound_detail::InboundPendingView;
using bridge_alliance_inbound_detail::inbound_pending_lookup;
using bridge_alliance_inbound_detail::inbound_pending_reserve;
using bridge_alliance_inbound_detail::inbound_pending_release;
using bridge_alliance_inbound_detail::inbound_pending_commit;
using bridge_alliance_inbound_detail::inbound_pending_is_active;
using bridge_alliance_inbound_detail::inbound_set_test_path;
using bridge_alliance_inbound_detail::inbound_test_tick;

#endif
