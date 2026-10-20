// Scoped observation of the native AE/coalition sorting helper.
//
// FUN_140388d20 is a void sort(std::vector<Row>*) entry.  The two callers
// relevant to the peace query return at 0x3898bb (the treaty-risk list) and
// 0x38a07e (the public coalition-country list).  This include deliberately
// observes only those two return addresses.  Every other call is forwarded
// without touching the vector argument.

#ifndef BRIDGE_PEACE_COALITION_CAPTURE_INC
#define BRIDGE_PEACE_COALITION_CAPTURE_INC

#include <windows.h>
#include <cstddef>
#include <cstdint>
#include <cstring>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

#include "entry-patch-transaction.inc"

namespace bridge_peace_coalition_capture_detail {

constexpr uintptr_t kSortRva=0x388d20;
constexpr uint32_t kTreatyRiskReturnRva=0x3898bb;
constexpr uint32_t kCoalitionReturnRva=0x38a07e;
constexpr unsigned kPatchBytes=15;
constexpr unsigned kAbsoluteJumpBytes=14;
constexpr unsigned kRowBytes=0x10;
constexpr unsigned kMaxRows=256;
constexpr unsigned kNearBlockBytes=0x1000;
constexpr unsigned kTrampolineOffset=0x200;
constexpr unsigned kUnwindInfoOffset=0x100;

// 48 89 5c 24 10; 48 89 6c 24 18; 48 89 74 24 20.
// There is no RIP-relative instruction or branch in the copied bytes.
static const unsigned char kExpectedPrologue[kPatchBytes]={
    0x48,0x89,0x5c,0x24,0x10,
    0x48,0x89,0x6c,0x24,0x18,
    0x48,0x89,0x74,0x24,0x20
};

struct CoalitionRow {
    uint64_t country=0;
    int32_t delta=0;
    int32_t current=0;
};
static_assert(sizeof(CoalitionRow)==kRowBytes,
    "the native coalition row is exactly 16 bytes");

struct CoalitionGroup {
    uint32_t caller_return_rva=0;
    uint32_t count=0;             // rows copied into rows[]
    uint32_t native_count=0;     // vector length before the 256-row bound
    DWORD returned_last_error=ERROR_SUCCESS;
    bool vector_readable=false;
    bool vector_shape_valid=false;
    bool complete=false;
    bool overflow=false;
    CoalitionRow rows[kMaxRows]{};
};

struct CoalitionCapture {
    CoalitionGroup treaty_risk{};
    CoalitionGroup coalition{};
    bool treaty_seen=false;
    bool coalition_seen=false;
    bool nested_scope=false;
    bool complete=false;
    bool overflow=false;
};

struct ScopeState {
    unsigned depth=0;
    CoalitionCapture capture{};
};

static thread_local ScopeState coalition_scope{};
static void* coalition_original=nullptr;
static unsigned char* coalition_block=nullptr;
static unsigned char* coalition_trampoline=nullptr;
static unsigned char* coalition_unwind_info=nullptr;
static SIZE_T coalition_trampoline_size=kAbsoluteJumpBytes+kPatchBytes;
static unsigned char coalition_replacement[kPatchBytes]{};
static bridge_entry_patch::PatchPlan coalition_patch_plan{};
static RUNTIME_FUNCTION coalition_runtime_function{};
static bool coalition_runtime_registered=false;
static bool coalition_installed=false;
static bool coalition_published=false;

static bool coalition_read_bytes(uintptr_t address,void* output,
    SIZE_T size) noexcept {
    if (!size) return true;
    if (!address || !output) return false;
    SIZE_T copied=0;
    return ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address),output,size,&copied)!=FALSE
        && copied==size;
}

static uint32_t coalition_rva(uintptr_t address) noexcept {
    if (!base || address<base) return 0;
    const uintptr_t difference=address-base;
    return difference<=0xffffffffull?static_cast<uint32_t>(difference):0;
}

static void coalition_absolute_jump(unsigned char* destination,
    uintptr_t target) noexcept {
    destination[0]=0xff;
    destination[1]=0x25;
    memset(destination+2,0,4);
    memcpy(destination+6,&target,sizeof(target));
}

static unsigned char* coalition_allocate_near() noexcept {
    if (!base) return nullptr;
    const uintptr_t first=base+0x10000000u;
    for (unsigned index=0;index<2048;++index) {
        const uintptr_t desired=first+static_cast<uintptr_t>(index)*0x100000u;
        void* memory=VirtualAlloc(reinterpret_cast<void*>(desired),
            kNearBlockBytes,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
        if (!memory) continue;
        const uintptr_t address=reinterpret_cast<uintptr_t>(memory);
        if (address>=base && address-base<=0xffffffffull)
            return static_cast<unsigned char*>(memory);
        VirtualFree(memory,0,MEM_RELEASE);
    }
    return nullptr;
}

static bool coalition_register_unwind() noexcept {
    if (!base || !coalition_trampoline || !coalition_unwind_info) return false;
    const uintptr_t trampoline_rva=reinterpret_cast<uintptr_t>(
        coalition_trampoline)-base;
    const uintptr_t unwind_rva=reinterpret_cast<uintptr_t>(
        coalition_unwind_info)-base;
    if (trampoline_rva>0xffffffffull
        || trampoline_rva>UINTPTR_MAX-coalition_trampoline_size
        || trampoline_rva+coalition_trampoline_size>0xffffffffull
        || unwind_rva>0xffffffffull
        || unwind_rva>UINTPTR_MAX-16
        || unwind_rva+16>0xffffffffull)
        return false;
    coalition_runtime_function.BeginAddress=static_cast<DWORD>(trampoline_rva);
    coalition_runtime_function.EndAddress=static_cast<DWORD>(
        trampoline_rva+coalition_trampoline_size);
    // The own UNWIND_INFO describes only the 15 copied prologue bytes:
    // mov [rsp+0x10],rbx at offset 5, mov [rsp+0x18],rbp at offset 10,
    // and mov [rsp+0x20],rsi at offset 15.  The SAVE_NONVOL entries are in
    // descending prologue order and each consumes two UNWIND_CODE slots.
    coalition_runtime_function.UnwindData=static_cast<DWORD>(unwind_rva);
    if (!RtlAddFunctionTable(&coalition_runtime_function,1,
        static_cast<DWORD64>(base))) return false;
    coalition_runtime_registered=true;
    return true;
}

static void coalition_release_unpublished() noexcept {
    if (coalition_published) return;
    if (coalition_runtime_registered) {
        RtlDeleteFunctionTable(&coalition_runtime_function);
        coalition_runtime_registered=false;
    }
    if (coalition_block) VirtualFree(coalition_block,0,MEM_RELEASE);
    coalition_block=nullptr;
    coalition_trampoline=nullptr;
    coalition_unwind_info=nullptr;
    coalition_original=nullptr;
    coalition_runtime_function=RUNTIME_FUNCTION{};
}

static CoalitionGroup* coalition_group_for(CoalitionCapture& capture,
    uint32_t caller_rva) noexcept {
    if (caller_rva==kTreatyRiskReturnRva) {
        capture.treaty_seen=true;
        return &capture.treaty_risk;
    }
    if (caller_rva==kCoalitionReturnRva) {
        capture.coalition_seen=true;
        return &capture.coalition;
    }
    return nullptr;
}

static void coalition_capture_vector(void* vector,uintptr_t caller_return,
    DWORD returned_last_error) noexcept {
    if (!coalition_scope.depth) return;
    const uint32_t caller_rva=coalition_rva(caller_return);
    CoalitionGroup* group=coalition_group_for(coalition_scope.capture,
        caller_rva);
    // Other native callers are intentionally invisible to this observer.
    if (!group) return;
    if (group->caller_return_rva!=0) {
        // A query normally reaches each sort call once.  Keep the first
        // bounded result and make a duplicate explicitly incomplete rather
        // than silently replacing it.
        group->complete=false;
        group->overflow=true;
        coalition_scope.capture.overflow=true;
        return;
    }
    group->caller_return_rva=caller_rva;
    group->returned_last_error=returned_last_error;

    uintptr_t begin=0,end=0,capacity=0;
    unsigned char header[sizeof(uintptr_t)*3]{};
    if (!vector || !coalition_read_bytes(reinterpret_cast<uintptr_t>(vector),
        header,sizeof(header))) return;
    group->vector_readable=true;
    memcpy(&begin,header,sizeof(begin));
    memcpy(&end,header+sizeof(uintptr_t),sizeof(end));
    memcpy(&capacity,header+sizeof(uintptr_t)*2,sizeof(capacity));

    // A default empty vector may have three null pointers.  It is a complete
    // empty list; any other null/misaligned pointer shape is incomplete.
    if (!begin && !end && !capacity) {
        group->vector_shape_valid=true;
        group->complete=true;
        return;
    }
    if (!begin || !end || !capacity || begin>end || end>capacity) return;
    const uintptr_t bytes=end-begin;
    if (bytes%kRowBytes!=0) return;
    const uintptr_t native_count_wide=bytes/kRowBytes;
    group->vector_shape_valid=true;
    group->native_count=native_count_wide>0xffffffffull
        ?0xffffffffu:static_cast<uint32_t>(native_count_wide);
    if (native_count_wide>kMaxRows) {
        group->overflow=true;
        coalition_scope.capture.overflow=true;
        return;
    }
    const unsigned count=static_cast<unsigned>(native_count_wide);
    group->count=count;
    if (!count) {
        group->complete=true;
        return;
    }
    const SIZE_T row_bytes=static_cast<SIZE_T>(count)*kRowBytes;
    if (!coalition_read_bytes(begin,group->rows,row_bytes)) return;
    group->complete=true;
}

// The absolute entry jump preserves the native one-argument Win64 ABI.  The
// sort returns void; the original trampoline is called exactly once.
#if defined(__GNUC__)
extern "C" __attribute__((noinline))
#elif defined(_MSC_VER)
extern "C" __declspec(noinline)
#else
extern "C"
#endif
void bridge_peace_coalition_capture_sort(void* vector) noexcept {
    const DWORD incoming_last_error=GetLastError();
    uintptr_t caller_return=0;
#if defined(_MSC_VER)
    caller_return=reinterpret_cast<uintptr_t>(_ReturnAddress());
#else
    caller_return=reinterpret_cast<uintptr_t>(__builtin_return_address(0));
#endif
    const bool active=coalition_scope.depth!=0;
    using NativeSort=void (*)(void*);
    const NativeSort original=reinterpret_cast<NativeSort>(coalition_original);
    if (!original) {
        SetLastError(incoming_last_error);
        return;
    }
    original(vector);
    const DWORD returned_last_error=GetLastError();
    if (active) coalition_capture_vector(vector,caller_return,
        returned_last_error);
    // ReadProcessMemory in the capture path may set the Win32 error slot.  The
    // native caller must observe the post-original value exactly.
    SetLastError(returned_last_error);
}

static void coalition_scope_begin() noexcept {
    if (!coalition_scope.depth) coalition_scope=ScopeState{};
    if (coalition_scope.depth!=0xffffffffu) ++coalition_scope.depth;
    else coalition_scope.capture.nested_scope=true;
    if (coalition_scope.depth>1) coalition_scope.capture.nested_scope=true;
}

static CoalitionCapture coalition_scope_end() noexcept {
    CoalitionCapture result=coalition_scope.capture;
    if (coalition_scope.depth) --coalition_scope.depth;
    if (!coalition_scope.depth) {
        result.complete=!result.nested_scope && !result.overflow
            && (!result.treaty_seen || result.treaty_risk.complete)
            && (!result.coalition_seen || result.coalition.complete);
        coalition_scope.capture.complete=result.complete;
    }
    return result;
}

static bool coalition_install() noexcept {
    if (coalition_installed) return true;
    const bridge_entry_patch::PatchResult pending=
        bridge_entry_patch::guarded_patch_retry_pending();
    if (pending.pending_count || !pending.success || !base) return false;
    auto target=reinterpret_cast<unsigned char*>(base+kSortRva);
    unsigned char actual[kPatchBytes]{};
    if (!coalition_read_bytes(reinterpret_cast<uintptr_t>(target),actual,
        sizeof(actual)) || memcmp(actual,kExpectedPrologue,kPatchBytes)!=0)
        return false;
    coalition_block=coalition_allocate_near();
    if (!coalition_block) return false;
    coalition_trampoline=coalition_block+kTrampolineOffset;
    coalition_unwind_info=coalition_block+kUnwindInfoOffset;
    memcpy(coalition_trampoline,kExpectedPrologue,kPatchBytes);
    coalition_absolute_jump(coalition_trampoline+kPatchBytes,
        base+kSortRva+kPatchBytes);
    // UNWIND_INFO: version=1, flags=0, prolog=15, slots=6, frame=0.
    // Each UWOP_SAVE_NONVOL is followed by its 16-bit scaled stack offset.
    static const unsigned char kUnwindInfo[16]={
        0x01,0x0f,0x06,0x00,
        0x0f,0x64,0x04,0x00,
        0x0a,0x54,0x03,0x00,
        0x05,0x34,0x02,0x00
    };
    memcpy(coalition_unwind_info,kUnwindInfo,sizeof(kUnwindInfo));
    DWORD old_protection=0;
    if (!VirtualProtect(coalition_block,kNearBlockBytes,PAGE_EXECUTE_READ,
        &old_protection)
        || !FlushInstructionCache(GetCurrentProcess(),coalition_block,
            kNearBlockBytes)
        || !coalition_register_unwind()) {
        coalition_release_unpublished();
        return false;
    }
    coalition_original=coalition_trampoline;
    memset(coalition_replacement,0x90,sizeof(coalition_replacement));
    coalition_absolute_jump(coalition_replacement,
        reinterpret_cast<uintptr_t>(&bridge_peace_coalition_capture_sort));
    coalition_patch_plan=bridge_entry_patch::PatchPlan{};
    coalition_patch_plan.count=1;
    coalition_patch_plan.targets[0]={target,kPatchBytes,kExpectedPrologue,
        coalition_replacement,coalition_trampoline,coalition_trampoline_size};
    const bridge_entry_patch::PatchResult result=
        bridge_entry_patch::guarded_patch_apply(coalition_patch_plan);
    coalition_published=coalition_published || result.published;
    coalition_installed=result.success;
    if (!result.success && !result.published) coalition_release_unpublished();
    return result.success;
}

[[maybe_unused]] static bool coalition_rollback() noexcept {
    coalition_scope.depth=0;
    if (!coalition_patch_plan.count) return true;
    unsigned char actual[kPatchBytes]{};
    auto target=reinterpret_cast<unsigned char*>(base+kSortRva);
    if (!coalition_read_bytes(reinterpret_cast<uintptr_t>(target),actual,
        sizeof(actual))) return false;
    if (!memcmp(actual,kExpectedPrologue,kPatchBytes)) {
        coalition_installed=false;
        return true;
    }
    if (memcmp(actual,coalition_replacement,kPatchBytes)!=0) return false;
    const bridge_entry_patch::PatchResult result=
        bridge_entry_patch::guarded_patch_rollback(coalition_patch_plan);
    const bool complete=result.success && result.threads_resumed
        && result.protection_restored && result.rollback_complete;
    if (complete) coalition_installed=false;
    return complete;
}

static bool coalition_installed_state() noexcept { return coalition_installed; }

} // namespace bridge_peace_coalition_capture_detail

using bridge_peace_coalition_capture_detail::CoalitionCapture;
using bridge_peace_coalition_capture_detail::CoalitionGroup;
using bridge_peace_coalition_capture_detail::CoalitionRow;
using bridge_peace_coalition_capture_detail::bridge_peace_coalition_capture_sort;
using bridge_peace_coalition_capture_detail::coalition_install;
using bridge_peace_coalition_capture_detail::coalition_installed_state;
using bridge_peace_coalition_capture_detail::coalition_rollback;
using bridge_peace_coalition_capture_detail::coalition_scope_begin;
using bridge_peace_coalition_capture_detail::coalition_scope_end;

#endif // BRIDGE_PEACE_COALITION_CAPTURE_INC
