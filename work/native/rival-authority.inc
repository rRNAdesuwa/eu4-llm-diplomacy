// Rival authority gate at the three native country-command entries.
//
// This include owns only the three native country-command entry hooks.  It is
// intentionally independent from the query and execution transports: no
// The request ledger may grant Set/Remove to one transported command. The
// hook path never performs file I/O. Every other actor is forwarded to the
// matching original trampoline exactly once.

#ifndef BRIDGE_RIVAL_AUTHORITY_INC
#define BRIDGE_RIVAL_AUTHORITY_INC

namespace rival_authority_detail {

enum class RivalEntryKind : unsigned char {
    set=1,
    replace=2,
    remove=3,
};

constexpr unsigned kRivalEntryCount=3;
constexpr unsigned kRivalRingCapacity=128;
constexpr unsigned kRivalFlushLimit=32;
constexpr uintptr_t kRivalTrampolineOffset=0x100;
constexpr uintptr_t kRivalVtableSet=0x1c55138;
constexpr uintptr_t kRivalVtableReplace=0x1c54b10;
constexpr uintptr_t kRivalVtableRemove=0x1c54a68;
constexpr uintptr_t kRivalSetRva=0x2aaad0;
constexpr uintptr_t kRivalReplaceRva=0x2ab8b0;
constexpr uintptr_t kRivalRemoveRva=0x2aca90;
constexpr uint32_t kRivalSetSelector=0x2fae;
constexpr uint32_t kRivalReplaceSelector=0x3005;
constexpr uint32_t kRivalRemoveSelector=0x2faf;
constexpr uint32_t kFranceTag=0x415246u;
constexpr uint32_t kPortugalTag=0x524f50u;

// These are the complete native prologues recorded in
// work/runtime/rival-rules-20261016-001/*-entry-prologue-001.txt.  The next
// instruction is copied only by the original function after the trampoline's
// absolute return jump.
static const unsigned char rival_set_signature[28]={
    0x48,0x89,0x5c,0x24,0x18,0x55,0x56,0x57,
    0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,
    0x48,0x8d,0x6c,0x24,0xa0,
    0x48,0x81,0xec,0x60,0x01,0x00,0x00};
static const unsigned char rival_replace_signature[32]={
    0x48,0x89,0x4c,0x24,0x08,0x55,0x53,0x56,
    0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,
    0x48,0x8d,0xac,0x24,0x68,0xff,0xff,0xff,
    0x48,0x81,0xec,0x98,0x01,0x00,0x00};
static const unsigned char rival_remove_signature[31]={
    0x48,0x89,0x5c,0x24,0x20,0x55,0x56,0x57,
    0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,
    0x48,0x8d,0xac,0x24,0x70,0xff,0xff,0xff,
    0x48,0x81,0xec,0x90,0x01,0x00,0x00};

struct RivalEntryObservation {
    uint64_t sequence=0;
    DWORD thread=0;
    uintptr_t sourcecaller=0;
    uint64_t actor=0;
    uint64_t target=0;
    uint64_t old_rival=0;
    uint32_t selector=0;
    RivalEntryKind kind=RivalEntryKind::set;
    bool shape=false;
    bool canonical=false;
    bool allowed=false;
    char reason[64]{};
};

static SRWLOCK rival_ring_lock=SRWLOCK_INIT;
static RivalEntryObservation rival_ring[kRivalRingCapacity]{};
static unsigned rival_ring_head=0;
static unsigned rival_ring_size=0;
static volatile LONG rival_ring_dropped=0;
static volatile LONG64 rival_sequence=0;
static volatile LONG rival_blocked_calls=0;

static wchar_t rival_authority_test_path[MAX_PATH]{};
static bool rival_authority_test_consumed=false;

using RivalHandler=void (*)(void*);
static RivalHandler rival_set_original=nullptr;
static RivalHandler rival_replace_original=nullptr;
static RivalHandler rival_remove_original=nullptr;

static unsigned char* rival_blocks[kRivalEntryCount]{};
static unsigned char* rival_trampolines[kRivalEntryCount]{};
static bool rival_unwind_registered[kRivalEntryCount]{};
static RUNTIME_FUNCTION rival_runtime_functions[kRivalEntryCount]{};
static bridge_entry_patch::PatchPlan rival_patch_plan{};
static unsigned char rival_replacements[kRivalEntryCount][32]{};
static bool rival_authority_installed=false;
static bool rival_authority_published=false;

static const uintptr_t rival_target_rvas[kRivalEntryCount]={
    kRivalSetRva,kRivalReplaceRva,kRivalRemoveRva};
static const unsigned rival_prologue_sizes[kRivalEntryCount]={28,32,31};
static const unsigned char* const rival_signatures[kRivalEntryCount]={
    rival_set_signature,rival_replace_signature,rival_remove_signature};
static const uintptr_t rival_vtable_rvas[kRivalEntryCount]={
    kRivalVtableSet,kRivalVtableReplace,kRivalVtableRemove};
static const uint32_t rival_selectors[kRivalEntryCount]={
    kRivalSetSelector,kRivalReplaceSelector,kRivalRemoveSelector};

static const char* rival_kind_name(RivalEntryKind kind) noexcept {
    switch (kind) {
    case RivalEntryKind::set: return "set_rival";
    case RivalEntryKind::replace: return "replace_rival";
    case RivalEntryKind::remove: return "remove_rival";
    default: return "unknown";
    }
}

static void rival_copy_reason(char (&destination)[64],const char* source) noexcept {
    destination[0]=0;
    if (!source) return;
    size_t length=strlen(source);
    if (length>=sizeof(destination)) length=sizeof(destination)-1;
    memcpy(destination,source,length);
    destination[length]=0;
}

static bool rival_actor_is_france(uint64_t handle) noexcept {
    return static_cast<uint32_t>(handle&0xffffffu)==kFranceTag;
}

static const char* rival_reason_for(bool actor_readable,bool shape,
    bool actor_france,bool original_available) noexcept {
    if (!actor_readable) return "ACTOR_UNREADABLE_FORWARD";
    if (actor_france) return "FRA_SUBMISSION_UNAUTHORIZED";
    if (!shape) return "SHAPE_MISMATCH_FORWARD";
    if (!original_available) return "ORIGINAL_UNAVAILABLE";
    return "FORWARD_NON_FRA";
}

static void rival_record(RivalEntryKind kind,uint32_t selector,uint64_t actor,
    uint64_t target,uint64_t old_rival,bool shape,bool canonical,bool allowed,
    const char* reason_text,uintptr_t sourcecaller) noexcept {
    RivalEntryObservation event{};
    event.sequence=static_cast<uint64_t>(InterlockedIncrement64(&rival_sequence));
    event.thread=GetCurrentThreadId();
    event.sourcecaller=sourcecaller;
    event.actor=actor;
    event.target=target;
    event.old_rival=old_rival;
    event.selector=selector;
    event.kind=kind;
    event.shape=shape;
    event.canonical=canonical;
    event.allowed=allowed;
    rival_copy_reason(event.reason,reason_text);
    if (!TryAcquireSRWLockExclusive(&rival_ring_lock)) {
        InterlockedIncrement(&rival_ring_dropped);
        return;
    }
    if (rival_ring_size<kRivalRingCapacity) {
        rival_ring[(rival_ring_head+rival_ring_size)%kRivalRingCapacity]=event;
        ++rival_ring_size;
    } else {
        InterlockedIncrement(&rival_ring_dropped);
    }
    ReleaseSRWLockExclusive(&rival_ring_lock);
}

static void rival_authority_entry(void* object,RivalEntryKind kind,
    RivalHandler original,uintptr_t sourcecaller) noexcept {
    const unsigned index=static_cast<unsigned>(kind)-1u;
    uint64_t actor=0,target=0,old_rival=0;
    uint32_t selector=0;
    uintptr_t vtable=0;
    const uintptr_t address=reinterpret_cast<uintptr_t>(object);
    const bool vtable_readable=address>=0x10000 && read(address,vtable);
    const bool selector_readable=address>=0x10000 && read(address+0x44,selector);
    const bool actor_readable=address>=0x10000 && read(address+0x50,actor);
    const bool target_readable=address>=0x10000 && read(address+0x58,target);
    const bool old_readable=kind!=RivalEntryKind::replace
        || (address>=0x10000 && read(address+0x60,old_rival));
    const bool shape=vtable_readable && selector_readable && actor_readable
        && target_readable && old_readable
        && vtable==base+rival_vtable_rvas[index]
        && selector==rival_selectors[index];
    const bool canonical=actor_readable && target_readable
        && observation_country_handle(actor) && observation_country_handle(target)
        && (kind!=RivalEntryKind::replace || (old_readable
            && observation_country_handle(old_rival)));
    const bool actor_france=actor_readable && rival_actor_is_france(actor);
    const int binding=actor_france && shape && canonical && original
        ?rival_execution_begin(object,static_cast<unsigned>(kind)):-1;
    const bool allowed=!actor_france || binding>=0;
    const char* reason_text=binding>=0?"FRA_REQUEST_BOUND_NATIVE_RULES_VERIFIED":
        rival_reason_for(actor_readable,shape,actor_france,original!=nullptr);
    rival_record(kind,selector,actor,target,old_rival,shape,canonical,allowed,
        reason_text,sourcecaller);
    if (actor_france && binding<0) {
        InterlockedIncrement(&rival_blocked_calls);
        return;
    }
    if (original) {
        // The matching trampoline contains the complete original prologue and
        // the return jump.  Forward exactly once for every non-FRA actor.
        original(object);
        if (binding>=0) rival_execution_finish(static_cast<unsigned>(binding));
    }
}

extern "C" void rival_set_entry(void* object) noexcept {
    rival_authority_entry(object,RivalEntryKind::set,rival_set_original,
        reinterpret_cast<uintptr_t>(__builtin_return_address(0)));
}

extern "C" void rival_replace_entry(void* object) noexcept {
    rival_authority_entry(object,RivalEntryKind::replace,rival_replace_original,
        reinterpret_cast<uintptr_t>(__builtin_return_address(0)));
}

extern "C" void rival_remove_entry(void* object) noexcept {
    rival_authority_entry(object,RivalEntryKind::remove,rival_remove_original,
        reinterpret_cast<uintptr_t>(__builtin_return_address(0)));
}

static bool rival_prepare_trampoline(unsigned index) noexcept {
    const unsigned prologue_size=rival_prologue_sizes[index];
    const unsigned trampoline_size=prologue_size+14;
    unsigned char* block=bridge_alliance_inbound_detail::inbound_allocate_near();
    if (!block) return false;
    unsigned char* trampoline=block+kRivalTrampolineOffset;
    memcpy(trampoline,rival_signatures[index],prologue_size);
    absolute_jump(trampoline+prologue_size,base+rival_target_rvas[index]+prologue_size);

    DWORD64 image_base=0;
    PRUNTIME_FUNCTION parent=RtlLookupFunctionEntry(
        static_cast<DWORD64>(base+rival_target_rvas[index]),&image_base,nullptr);
    const uintptr_t trampoline_rva=reinterpret_cast<uintptr_t>(trampoline)-base;
    if (!parent || image_base!=static_cast<DWORD64>(base)
        || parent->BeginAddress!=rival_target_rvas[index]
        || trampoline_rva+trampoline_size>0xffffffffull) {
        VirtualFree(block,0,MEM_RELEASE);
        return false;
    }
    rival_runtime_functions[index].BeginAddress=static_cast<DWORD>(trampoline_rva);
    rival_runtime_functions[index].EndAddress=
        static_cast<DWORD>(trampoline_rva+trampoline_size);
    rival_runtime_functions[index].UnwindData=parent->UnwindData;
    if (!RtlAddFunctionTable(&rival_runtime_functions[index],1,
        static_cast<DWORD64>(base))) {
        VirtualFree(block,0,MEM_RELEASE);
        return false;
    }
    rival_unwind_registered[index]=true;
    DWORD protection=0;
    if (!VirtualProtect(block,0x1000,PAGE_EXECUTE_READ,&protection)) {
        RtlDeleteFunctionTable(&rival_runtime_functions[index]);
        rival_unwind_registered[index]=false;
        VirtualFree(block,0,MEM_RELEASE);
        return false;
    }
    FlushInstructionCache(GetCurrentProcess(),block,0x1000);
    rival_blocks[index]=block;
    rival_trampolines[index]=trampoline;
    return true;
}

static void rival_release_unpublished() noexcept {
    if (rival_authority_published) return;
    for (unsigned index=0;index<kRivalEntryCount;++index) {
        if (rival_unwind_registered[index]) {
            RtlDeleteFunctionTable(&rival_runtime_functions[index]);
            rival_unwind_registered[index]=false;
        }
        if (rival_blocks[index]) VirtualFree(rival_blocks[index],0,MEM_RELEASE);
        rival_blocks[index]=nullptr;
        rival_trampolines[index]=nullptr;
        rival_runtime_functions[index]=RUNTIME_FUNCTION{};
    }
    rival_set_original=nullptr;
    rival_replace_original=nullptr;
    rival_remove_original=nullptr;
}

static bool rival_target_bytes(unsigned index,unsigned char (&bytes)[32]) noexcept {
    return read(base+rival_target_rvas[index],bytes)
        && !memcmp(bytes,rival_signatures[index],rival_prologue_sizes[index]);
}

static void rival_make_replacements() noexcept {
    for (unsigned index=0;index<kRivalEntryCount;++index) {
        memset(rival_replacements[index],0x90,sizeof(rival_replacements[index]));
    }
    absolute_jump(rival_replacements[0],reinterpret_cast<uintptr_t>(&rival_set_entry));
    absolute_jump(rival_replacements[1],reinterpret_cast<uintptr_t>(&rival_replace_entry));
    absolute_jump(rival_replacements[2],reinterpret_cast<uintptr_t>(&rival_remove_entry));
}

static bool rival_trampolines_ready() noexcept {
    for (unsigned index=0;index<kRivalEntryCount;++index)
        if (!rival_blocks[index] || !rival_trampolines[index]
            || !rival_unwind_registered[index]) return false;
    return true;
}

[[maybe_unused]] static bool rival_authority_install() {
    if (rival_authority_installed) return true;
    unsigned char actual[32]{};
    for (unsigned index=0;index<kRivalEntryCount;++index) {
        if (!rival_target_bytes(index,actual)) return false;
    }
    if (!rival_trampolines_ready()) {
        rival_release_unpublished();
        for (unsigned index=0;index<kRivalEntryCount;++index) {
            if (!rival_prepare_trampoline(index)) {
                rival_release_unpublished();
                return false;
            }
        }
    }
    // Publish all original call targets before any entry jump becomes live.
    rival_set_original=reinterpret_cast<RivalHandler>(rival_trampolines[0]);
    rival_replace_original=reinterpret_cast<RivalHandler>(rival_trampolines[1]);
    rival_remove_original=reinterpret_cast<RivalHandler>(rival_trampolines[2]);
    rival_make_replacements();
    rival_patch_plan=bridge_entry_patch::PatchPlan{};
    rival_patch_plan.count=kRivalEntryCount;
    for (unsigned index=0;index<kRivalEntryCount;++index) {
        rival_patch_plan.targets[index]={
            reinterpret_cast<void*>(base+rival_target_rvas[index]),
            rival_prologue_sizes[index],rival_signatures[index],
            rival_replacements[index],rival_trampolines[index],
            rival_prologue_sizes[index]+14};
    }
    const bridge_entry_patch::PatchResult result=
        bridge_entry_patch::guarded_patch_apply(rival_patch_plan);
    rival_authority_published=rival_authority_published || result.published;
    rival_authority_installed=result.success;
    if (!result.success) {
        const auto cleanup=bridge_entry_patch::guarded_patch_retry_pending();
        if (!cleanup.success || !result.protection_restored)
            lifecycle_rollback_incomplete=true;
        if (!result.published) {
            rival_patch_plan=bridge_entry_patch::PatchPlan{};
            rival_release_unpublished();
        } else {
            char message[420];
            snprintf(message,sizeof(message),
                "{\"event\":\"native_rival_authority_install_failed\",\"published\":true,\"threads_resumed\":%s,\"rollback_complete\":%s,\"failure_stage\":%u,\"win32_error\":%lu,\"restart_required\":true}\n",
                result.threads_resumed?"true":"false",
                result.rollback_complete?"true":"false",
                static_cast<unsigned>(result.failure_stage),
                static_cast<unsigned long>(result.error));
            line(message);
        }
        return false;
    }
    line("{\"event\":\"native_rival_authority_installed\",\"native_rival_submission\":false,\"targets\":3,\"original_unwind_registered\":true,\"covers_direct_calls\":true,\"covers_vtable_calls\":true}\n");
    return true;
}

[[maybe_unused]] static bool rival_authority_rollback() {
    if (!rival_patch_plan.count) return true;
    unsigned char actual[32]{};
    bool all_original=true;
    bool all_replacement=true;
    for (unsigned index=0;index<kRivalEntryCount;++index) {
        if (!read(base+rival_target_rvas[index],actual)) return false;
        all_original=all_original
            && !memcmp(actual,rival_signatures[index],rival_prologue_sizes[index]);
        all_replacement=all_replacement
            && !memcmp(actual,rival_replacements[index],rival_prologue_sizes[index]);
    }
    if (all_original) {
        rival_authority_installed=false;
        return true;
    }
    if (!all_replacement) return false;
    const bridge_entry_patch::PatchResult result=
        bridge_entry_patch::guarded_patch_rollback(rival_patch_plan);
    const bool ok=result.success && result.threads_resumed
        && result.protection_restored && result.rollback_complete;
    if (ok) rival_authority_installed=false;
    return ok;
}

[[maybe_unused]] static void rival_authority_flush() {
    for (unsigned count=0;count<kRivalFlushLimit;++count) {
        RivalEntryObservation event{};
        AcquireSRWLockExclusive(&rival_ring_lock);
        if (!rival_ring_size) {
            ReleaseSRWLockExclusive(&rival_ring_lock);
            break;
        }
        event=rival_ring[rival_ring_head];
        rival_ring_head=(rival_ring_head+1)%kRivalRingCapacity;
        --rival_ring_size;
        ReleaseSRWLockExclusive(&rival_ring_lock);
        const unsigned long long sourcecaller=static_cast<unsigned long long>(event.sourcecaller);
        char message[900];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_rival_command_entry\",\"session_id\":\"%lu-%llx\",\"event_sequence\":%llu,\"scope\":\"%s\",\"canonical\":%s,\"shape\":%s,\"actor\":\"0x%llx\",\"target\":\"0x%llx\",\"old_rival\":\"0x%llx\",\"kind\":\"%s\",\"selector\":\"0x%x\",\"allowed\":%s,\"reason\":\"%s\",\"sourcecaller\":\"0x%llx\",\"thread\":%lu}\n",
            static_cast<unsigned long>(GetCurrentProcessId()),
            static_cast<unsigned long long>(observation_creation),event.sequence,
            event.canonical&&event.shape?"canonical":"unresolved",
            event.canonical?"true":"false",event.shape?"true":"false",
            static_cast<unsigned long long>(event.actor),
            static_cast<unsigned long long>(event.target),
            static_cast<unsigned long long>(event.old_rival),
            rival_kind_name(event.kind),event.selector,event.allowed?"true":"false",
            event.reason,sourcecaller,static_cast<unsigned long>(event.thread));
        line(message);
    }
    LONG dropped=InterlockedExchange(&rival_ring_dropped,0);
    if (dropped) {
        char message[180];
        snprintf(message,sizeof(message),
            "{\"event\":\"native_rival_command_entry_drop\",\"dropped\":%ld,\"complete\":false}\n",
            static_cast<long>(dropped));
        line(message);
    }
}

[[maybe_unused]] static bool rival_authority_set_paths(const wchar_t* directory) noexcept {
    rival_authority_test_path[0]=0;
    rival_authority_test_consumed=false;
    if (!directory || !directory[0]) return false;
    if (swprintf(rival_authority_test_path,MAX_PATH,
        L"%ls\\rival-authority-test.req",directory)<0) {
        rival_authority_test_path[0]=0;
        return false;
    }
    if (GetFileAttributesW(rival_authority_test_path)!=INVALID_FILE_ATTRIBUTES
        && !DeleteFileW(rival_authority_test_path)) {
        rival_authority_test_path[0]=0;
        return false;
    }
    return true;
}

struct RivalGuardSnapshot {
    bool readable=false;
    bool active=false;
    int32_t since_date_raw=-1;
    int32_t count=-1;
    int32_t max_rivals=-1;
    int32_t diplomatic_power_raw=-1;
    bool at_war=false;
};

static bool rival_guard_context(int32_t& date,uint64_t& player,
    unsigned char& paused) noexcept {
    uintptr_t game=0,server=0,server_vtable=0,get_pause=0,pause=0;
    if (thread_changed || !frame_thread || frame_thread!=GetCurrentThreadId()
        || !control_ready() || !read(base+0x233fe58,game)
        || !read(game+0x1dd0,date) || !read(game+0x1e60,player)
        || static_cast<uint32_t>(player&0xffffffu)!=kPortugalTag
        || static_cast<unsigned>((player>>32)&0xffffu)!=189
        || !read(game+0x1e00,server) || !read(server,server_vtable)
        || !read(server_vtable+0x100,get_pause)
        || get_pause<base+0x1000 || get_pause>=base+0x1c00000) return false;
    pause=reinterpret_cast<uintptr_t (*)(void*)>(get_pause)(
        reinterpret_cast<void*>(server));
    return pause>=0x10000 && read(pause+0x48,paused) && paused==1;
}

static bool rival_guard_snapshot(uint64_t actor,uint64_t target,
    RivalGuardSnapshot& snapshot) noexcept {
    uintptr_t actor_country=0;
    RivalQueryState state{};
    if (!insult_query_country(actor,actor_country)
        || !rival_query_membership(actor_country,target,state)
        || !state.state_verified) return false;
    snapshot.readable=true;
    snapshot.active=state.active;
    snapshot.since_date_raw=state.since_date_raw;
    snapshot.count=state.count;
    snapshot.max_rivals=state.max_rivals;
    snapshot.diplomatic_power_raw=state.diplomatic_power_raw;
    snapshot.at_war=state.at_war;
    return true;
}

static void rival_guard_write_u64(unsigned char* view,unsigned offset,uint64_t value) noexcept {
    memcpy(view+offset,&value,sizeof(value));
}

static void rival_guard_write_u32(unsigned char* view,unsigned offset,uint32_t value) noexcept {
    memcpy(view+offset,&value,sizeof(value));
}

static void rival_guard_write_i32(unsigned char* view,unsigned offset,int32_t value) noexcept {
    memcpy(view+offset,&value,sizeof(value));
}

static bool rival_guard_invoke(unsigned index,uint64_t actor,uint64_t target,
    uint64_t old_rival,bool vtable_call) noexcept {
    alignas(16) unsigned char view[0x68]{};
    rival_guard_write_u64(view,0,base+rival_vtable_rvas[index]);
    rival_guard_write_u32(view,8,0x165);
    rival_guard_write_u64(view,0x28,0);
    rival_guard_write_u64(view,0x30,0xf);
    rival_guard_write_i32(view,0x38,-1);
    rival_guard_write_u32(view,0x44,rival_selectors[index]);
    const uint16_t transfer_header=0xffffu;
    memcpy(view+0x48,&transfer_header,sizeof(transfer_header));
    rival_guard_write_u64(view,0x50,actor);
    rival_guard_write_u64(view,0x58,target);
    rival_guard_write_u64(view,0x60,old_rival);
    if (vtable_call) {
        uintptr_t method=0;
        if (!read(base+rival_vtable_rvas[index]+0x48,method)
            || method!=base+rival_target_rvas[index]) return false;
        reinterpret_cast<RivalHandler>(method)(view);
    } else {
        reinterpret_cast<RivalHandler>(base+rival_target_rvas[index])(view);
    }
    return true;
}

static void rival_guard_test_failure(const char* reason_text,const char* session,
    int32_t date,unsigned char paused) noexcept {
    char message[600];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_rival_authority_test\",\"session_id\":\"%s\",\"request\":\"RIVAL_GUARD_TEST1\",\"date_raw\":%d,\"paused\":%s,\"direct_calls\":0,\"vtable_calls\":0,\"blocked_calls\":0,\"all_blocked\":false,\"state_unchanged\":false,\"reason\":\"%s\",\"business_result\":\"unknown\",\"complete\":false}\n",
        session?session:"",date,paused==1?"true":"false",reason_text?reason_text:"unknown");
    line(message);
}

static void rival_guard_test_tick() noexcept {
    if (!rival_authority_test_path[0]
        || GetFileAttributesW(rival_authority_test_path)==INVALID_FILE_ATTRIBUTES) return;
    char request[128]{};
    DWORD got=0;
    HANDLE file=CreateFileW(rival_authority_test_path,GENERIC_READ,FILE_SHARE_READ,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return;
    const DWORD size=GetFileSize(file,nullptr);
    const bool size_ok=size<sizeof(request)
        && ReadFile(file,request,sizeof(request)-1,&got,nullptr) && got==size;
    CloseHandle(file);
    DeleteFileW(rival_authority_test_path);
    if (!size_ok) {
        rival_guard_test_failure("TEST_WIRE_INVALID","",0,0);
        return;
    }
    char command[32]{},session[96]{};
    int consumed=0;
    if (sscanf(request,"%31s %95s%n",command,session,&consumed)!=2
        || strcmp(command,"RIVAL_GUARD_TEST1")!=0
        || strcmp(request+consumed,"\n")!=0) {
        rival_guard_test_failure("TEST_WIRE_INVALID",session,0,0);
        return;
    }
    char expected_session[96]{};
    snprintf(expected_session,sizeof(expected_session),"%lu-%llx",
        static_cast<unsigned long>(GetCurrentProcessId()),
        static_cast<unsigned long long>(observation_creation));
    if (strcmp(session,expected_session)!=0) {
        rival_guard_test_failure("SESSION_MISMATCH",session,0,0);
        return;
    }
    if (rival_authority_test_consumed) {
        rival_guard_test_failure("TEST_ALREADY_CONSUMED",session,0,0);
        return;
    }
    rival_authority_test_consumed=true;
    if (!rival_authority_installed || !rival_trampolines_ready()
        || rival_set_original!=reinterpret_cast<RivalHandler>(rival_trampolines[0])
        || rival_replace_original!=reinterpret_cast<RivalHandler>(rival_trampolines[1])
        || rival_remove_original!=reinterpret_cast<RivalHandler>(rival_trampolines[2])) {
        rival_guard_test_failure("RIVAL_AUTHORITY_NOT_INSTALLED",session,0,0);
        return;
    }
    int32_t date=0;
    uint64_t player=0;
    unsigned char paused=0;
    if (!rival_guard_context(date,player,paused)) {
        rival_guard_test_failure("POR_PAUSED_FRAME_CONTEXT_UNREADABLE",session,date,paused);
        return;
    }
    uint64_t actor=0,bur=0,eng=0;
    if (!alliance_query_country("FRA",actor)
        || !alliance_query_country("BUR",bur)
        || !alliance_query_country("ENG",eng)) {
        rival_guard_test_failure("CANONICAL_COUNTRY_HANDLE_UNREADABLE",session,date,paused);
        return;
    }
    RivalGuardSnapshot before{},after{};
    if (!rival_guard_snapshot(actor,bur,before)) {
        rival_guard_test_failure("RIVAL_STATE_BEFORE_UNREADABLE",session,date,paused);
        return;
    }
    InterlockedExchange(&rival_blocked_calls,0);
    const bool direct_set=rival_guard_invoke(0,actor,bur,eng,false);
    const bool direct_replace=rival_guard_invoke(1,actor,bur,eng,false);
    const bool direct_remove=rival_guard_invoke(2,actor,bur,eng,false);
    const bool vtable_set=rival_guard_invoke(0,actor,bur,eng,true);
    const bool vtable_replace=rival_guard_invoke(1,actor,bur,eng,true);
    const bool vtable_remove=rival_guard_invoke(2,actor,bur,eng,true);
    const bool calls_ok=direct_set && direct_replace && direct_remove
        && vtable_set && vtable_replace && vtable_remove;
    const bool after_readable=rival_guard_snapshot(actor,bur,after);
    const bool unchanged=after_readable && before.readable==after.readable
        && before.active==after.active && before.since_date_raw==after.since_date_raw
        && before.count==after.count && before.max_rivals==after.max_rivals
        && before.diplomatic_power_raw==after.diplomatic_power_raw
        && before.at_war==after.at_war;
    const bool blocked=InterlockedCompareExchange(&rival_blocked_calls,0,0)==6;
    char message[1500];
    snprintf(message,sizeof(message),
        "{\"event\":\"native_rival_authority_test\",\"session_id\":\"%s\",\"request\":\"RIVAL_GUARD_TEST1\",\"scope\":\"FRA\",\"frame_thread\":%lu,\"paused\":%s,\"player\":\"%c%c%c\",\"date_raw\":%d,\"before\":{\"state_readable\":%s,\"rival_active\":%s,\"rival_since_date_raw\":%d,\"rival_count\":%d,\"max_rivals\":%d,\"diplomatic_power_raw\":%d,\"at_war\":%s},\"after\":{\"state_readable\":%s,\"rival_active\":%s,\"rival_since_date_raw\":%d,\"rival_count\":%d,\"max_rivals\":%d,\"diplomatic_power_raw\":%d,\"at_war\":%s},\"direct_calls\":3,\"vtable_calls\":3,\"blocked_calls\":%ld,\"all_blocked\":%s,\"state_unchanged\":%s,\"business_result\":\"blocked\",\"complete\":%s}\n",
        session,static_cast<unsigned long>(frame_thread),paused==1?"true":"false",
        static_cast<char>(player),static_cast<char>(player>>8),static_cast<char>(player>>16),date,
        before.readable?"true":"false",before.active?"true":"false",before.since_date_raw,
        before.count,before.max_rivals,before.diplomatic_power_raw,before.at_war?"true":"false",
        after.readable?"true":"false",after.active?"true":"false",after.since_date_raw,
        after.count,after.max_rivals,after.diplomatic_power_raw,after.at_war?"true":"false",
        static_cast<long>(InterlockedCompareExchange(&rival_blocked_calls,0,0)),
        blocked?"true":"false",unchanged?"true":"false",
        calls_ok && blocked && unchanged?"true":"false");
    line(message);
}

[[maybe_unused]] static void rival_authority_tick() noexcept {
    if (!frame_thread || thread_changed || frame_thread!=GetCurrentThreadId()) return;
    rival_guard_test_tick();
}

} // namespace rival_authority_detail

using rival_authority_detail::rival_authority_flush;
using rival_authority_detail::rival_authority_install;
using rival_authority_detail::rival_authority_rollback;
using rival_authority_detail::rival_authority_set_paths;
using rival_authority_detail::rival_authority_tick;

#endif // BRIDGE_RIVAL_AUTHORITY_INC
