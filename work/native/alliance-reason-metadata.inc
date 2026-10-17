// Typed, scoped capture at the native alliance-reason row constructor.
//
// The row constructor is FUN_1401c3fd0 (RVA 0x1c3fd0) in the verified
// EU4 1.37.4 image.  Its cached prologue is 15 bytes and contains no
// RIP-relative instruction:
//
//   48 89 5c 24 08  48 89 74 24 10  57  48 83 ec 20
//
// The wrapper is reached by an absolute jump, so __builtin_return_address(0)
// is the native call-site return address.  The native constructor is called
// exactly once through the original trampoline and its return value and
// post-call LastError are restored.  Capture is inactive unless the caller
// explicitly opens the frame-query TLS scope.

#ifndef BRIDGE_ALLIANCE_REASON_METADATA_INC
#define BRIDGE_ALLIANCE_REASON_METADATA_INC

#include <windows.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#if defined(_MSC_VER)
#include <intrin.h>
#endif

#include "entry-patch-transaction.inc"
#include "alliance-reason-key-branch.h"

namespace bridge_alliance_reason_metadata_detail {

constexpr uintptr_t kRowConstructorRva=0x1c3fd0;
constexpr unsigned kRowBytes=48;
constexpr unsigned kPatchBytes=15;
constexpr unsigned kAbsoluteJumpBytes=14;
constexpr unsigned kRecordCapacity=32;
constexpr unsigned kTextCapacity=512;
constexpr unsigned kNearBlockBytes=0x1000;
constexpr unsigned kTrampolineOffset=0x200;
constexpr unsigned kMaxStringCapacity=131072;

static const unsigned char kExpectedPrologue[kPatchBytes]={
    0x48,0x89,0x5c,0x24,0x08,
    0x48,0x89,0x74,0x24,0x10,
    0x57,
    0x48,0x83,0xec,0x20
};

// These are direct row-constructor call-site return RVAs (CALL is five
// bytes).  The key is marked confirmed only after the corresponding .rdata
// NUL-terminated bytes have been checked in the target image.
using KeyBinding=bridge_reason_key_branch::KeyBinding;

static const KeyBinding kConfirmedKeyBindings[]={
    // Peace evaluation (FUN_1401bf180).  These are the exact row-constructor
    // return RVAs reached by the mode=1 key branches.  The rdata RVAs and
    // strings below were matched against the LEA/call sequence in the same
    // branch; mode=0 uses the generic text object and must not inherit these
    // IDs.  0x1c120f is intentionally absent: its mode=1 text is assembled
    // from a dynamic reason context rather than one fixed localization key.
    {0x1bf419,0x1c43a88,"DIPLO_UNCONDITIONALLY_SURRENDERED"},
    {0x1bf5c6,0x1c43a88,"DIPLO_UNCONDITIONALLY_SURRENDERED"},
    {0x1bf7c6,0x1c43a10,"DIPLO_DEFEATED"},
    {0x1bf8df,0x1c43a20,"DIPLO_UNREASONABLE_DEMANDS"},
    {0x1bfa3b,0x1c43a40,"DIPLO_WAR_UNOCCUPIED_FORTS"},
    {0x1bfb5f,0x1c43a60,"DIPLO_WAR_INCONCLUSIVE"},
    {0x1bfc7d,0x1c43b00,"DIPLO_WAR_SCORE"},
    {0x1bfdd0,0x1c43b10,"DIPLO_PEACEOFFER_VALUE"},
    {0x1bffbf,0x1c43b28,"DIPLO_ANNEX_US"},
    {0x1c014f,0x1c43b38,"DIPLO_PUNISH_TRIBUTARY"},
    {0x1c02c4,0x1c43ab8,"DIPLO_HAS_PERSONALITY"},
    {0x1c055c,0x1c43ad0,"DIPLO_WARGOAL_BESIEGED"},
    {0x1c062b,0x1c43ae8,"DIPLO_HIGH_DEMANDS"},
    {0x1c08bd,0x1c43ba8,"DIPLO_OCCUPYING_WARLEADER"},
    {0x1c0979,0x1c43bc8,"DIPLO_NON_BELLIGERENT"},
    {0x1c1339,0x1c43b70,"DIPLO_UNACCEPTABLE_PEACE"},
    {0x1c145b,0x1c43b90,"DIPLO_NOT_WANT_GOLD"},
    {0x1c1540,0x1c43c10,"DIPLO_NOT_WANT_BRIBE"},
    {0x1c1789,0x1c43c30,"DIPLO_BEST_POSSIBLE_PEACE_OFFER"},
    {0x1c1888,0x1c43c50,"DIPLO_WANTS_END_TO_WAR"},
    // Peace factors from FUN_140370be0.  Each row-constructor call uses
    // incoming_flag/mode=1 and has one direct RDX -> .rdata localization key.
    // The return RVAs are the five real callers observed in the R39-D money
    // query; the RDX targets were checked as NUL-terminated strings in the
    // verified image.  No conditional alternate key is used by these paths.
    {0x3729b4,0x1c5d968,"DIPLO_WAR_REBELS"},
    {0x372e7b,0x1c5db70,"DIPLO_HOLD_CAPITAL"},
    {0x373114,0x1c5dbb8,"DIPLO_WAR_TIME_PASSED"},
    {0x373496,0x1c5dc08,"DIPLO_MILITARY_STRENGTH"},
    {0x373564,0x1c5dad0,"DIPLO_WAR_FORCE_BALANCE"},

    {0x39f478,0x1c5f880,"DIPLO_ENEMY_ALLIES"},
    {0x39f859,0x1c5f880,"DIPLO_ENEMY_ALLIES"},
    {0x3a0361,0x1c5f580,"DIPLO_ARMY_SIZE"},
    {0x3a044f,0x1c5f8d8,"DIPLO_NAVY_SIZE"},
    {0x3a05cd,0x1c5f098,"DIPLO_OPINION"},
    {0x3a0fa9,0x1c5da68,"DIPLO_ATTITUDE"},
    {0x3a1866,0x1c5eee0,"DIPLO_DIPLOMATIC_REP"},
    {0x3a19d6,0x1c5f130,"DIPLO_BORDER_DISTANCE"},
    {0x3a9328,0x1c5f098,"DIPLO_OPINION"},
    {0x3a992a,0x1c5eee0,"DIPLO_DIPLOMATIC_REP"},
    // Support Independence: each entry is keyed by the constructor return
    // RVA and its exact .rdata LEA target in FUN_1403a8270.  The two
    // attitude entries are separate native branches and must remain separate
    // caller bindings even though they use the same localization key.
    {0x3ab307,0x1c5f580,"DIPLO_ARMY_SIZE"},
    {0x3ab3f7,0x1c5f8d8,"DIPLO_NAVY_SIZE"},
    {0x3ab611,0x1c5da68,"DIPLO_ATTITUDE"},
    {0x3ab792,0x1c5da68,"DIPLO_ATTITUDE"},
    {0x3ab899,0x1c5f130,"DIPLO_BORDER_DISTANCE"},
    {0x3aa048,0x1c5f580,"DIPLO_ARMY_SIZE"},
    {0x3aa12e,0x1c5f8d8,"DIPLO_NAVY_SIZE"},
    {0x3aa750,0x1c5da68,"DIPLO_ATTITUDE"},
    // Military Access (+0x120 = FUN_140525e30): these constructor return
    // RVAs below each have a single verified key. The shared attitude and
    // neighbour-rival callsites use the conditional resolver below.
    {0x52660c,0x1c5f098,"DIPLO_OPINION"},
    {0x526887,0x1c5f580,"DIPLO_ARMY_SIZE"},
    {0x527acc,0x1c5eee0,"DIPLO_DIPLOMATIC_REP"},
    // Vassalization score 38e710: each constructor return has one direct
    // localization-key reference in its own branch. The two government
    // branches format their text through 424880, whose fixed key is proved
    // separately; their distinct -10/-30 caller records stay separate.
    {0x38e8fe,0x1c5edb0,"DIPLO_OWNS_CORE_PROVINES"},
    {0x38ebc9,0x1c5edd0,"DIPLO_HAS_SUBJECTS"},
    {0x38ed61,0x1c5ef90,"DIPLO_AT_WAR_AGAINST"},
    {0x38eed0,0x1c5efa8,"DIPLO_IS_DEPENDENT_ON"},
    {0x38f047,0x1c5efc0,"DIPLO_TRADING_CITY"},
    {0x38f180,0x1c5efd8,"DIPLO_HAS_NO_PROVINCES"},
    {0x38f295,0x1c5eff0,"DIPLO_WE_HAVE_ROYAL_MARRIAGE"},
    {0x38f3b9,0x1c5f010,"DIPLO_GOVERNMENT"},
    {0x38f4e2,0x1c5f010,"DIPLO_GOVERNMENT"},
    {0x38f656,0x1c5f028,"DIPLO_NOT_SAME_RELIGION_GROUP"},
    {0x38f74f,0x1c5f048,"DIPLO_NOT_SAME_RELIGION"},
    {0x38f8a6,0x1c5da68,"DIPLO_ATTITUDE"},
    {0x38fa35,0x1c5eee0,"DIPLO_DIPLOMATIC_REP"},
    {0x38fe08,0x1c5eef8,"DIPLO_MORE_BASE_TAX_THAN"},
    {0x38ff25,0x1c5ef18,"DIPLO_BASE_TAX"},
    {0x390024,0x1c5ef28,"DIPLO_MILITARY_POWER"},
    {0x390132,0x1c5ef40,"DIPLO_GOV_RANK"},
    {0x390227,0x1c5ef50,"DIPLO_GOV_RANK_DIFF"},
    {0x39032f,0x1c5ef68,"DIPLO_POPE"},
    {0x39043f,0x1c5ef78,"DIPLO_IS_EMPEROR"},
    {0x39054f,0x1c5f100,"DIPLO_ELECTOR"},
    {0x390652,0x1c5f110,"DIPLO_FREE_CITY"},
    {0x390779,0x1c5f120,"DIPLO_IN_HRE"},
    {0x39089f,0x1c5f130,"DIPLO_BORDER_DISTANCE"},
    {0x3909be,0x1c5f148,"DIPLO_TRUST"},
    {0x4f109a,0x1c5f098,"DIPLO_OPINION"},
    {0x4f1369,0x1c5da68,"DIPLO_ATTITUDE"},
    {0x4f167f,0x1c81d90,"DIPLO_SAME_RELIGION"},
    {0x4f1b3e,0x1c81d58,"DIPLO_MSG_FILTER_NEIGHBOURS"},
    {0x4f1d78,0x1c43ab8,"DIPLO_HAS_PERSONALITY"},
    {0x4f1f84,0x1c5eee0,"DIPLO_DIPLOMATIC_REP"},
    {0x4f2128,0x1c5f130,"DIPLO_BORDER_DISTANCE"}
};

struct ReasonMetadataRecord {
    uint64_t sequence=0;
    uint32_t caller_return_rva=0;
    uint32_t constructor_call_rva=0;
    int32_t constructor_argument_value=0;
    int32_t raw_value=0;
    unsigned char incoming_flag=0;
    unsigned char derived_flag=0;
    bool row_readable=false;
    bool returned_row_matches=false;
    bool string_shape_valid=false;
    bool string_inline=false;
    bool text_readable=false;
    bool text_truncated=false;
    bool constructor_source_confirmed=false;
    bridge_reason_key_branch::Observation key_branch{};
    uint64_t string_size=0;
    uint64_t string_capacity=0;
    unsigned text_bytes=0;
    DWORD returned_last_error=ERROR_SUCCESS;
    uint32_t localization_rdata_rva=0;
    char localization_key[48]{};
    unsigned char row_raw[kRowBytes]{};
    unsigned char text[kTextCapacity]{};
};

struct ScopeState {
    unsigned depth=0;
    unsigned count=0;
    bool overflow=false;
    uint64_t next_sequence=0;
    ReasonMetadataRecord records[kRecordCapacity]{};
};

static thread_local ScopeState reason_metadata_scope{};
static void* reason_metadata_original=nullptr;
static bridge_entry_patch::PatchPlan reason_metadata_patch_plan{};
static unsigned char reason_metadata_replacement[kPatchBytes]{};
static unsigned char* reason_metadata_block=nullptr;
static unsigned char* reason_metadata_trampoline=nullptr;
static SIZE_T reason_metadata_trampoline_size=kAbsoluteJumpBytes+kPatchBytes;
static RUNTIME_FUNCTION reason_metadata_runtime_function{};
static bool reason_metadata_runtime_registered=false;
static bool reason_metadata_keys_verified=false;
static bool reason_metadata_installed=false;
static bool reason_metadata_published=false;

static uint32_t reason_metadata_rva(uintptr_t address) noexcept {
    if (!base || address<base) return 0;
    const uintptr_t difference=address-base;
    return difference<=0xffffffffull?static_cast<uint32_t>(difference):0;
}

static bool reason_metadata_read_bytes(uintptr_t address,void* output,
    SIZE_T size) noexcept {
    if (!address || !output || !size) return size==0;
    SIZE_T copied=0;
    return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),
        output,size,&copied)!=FALSE && copied==size;
}

static const KeyBinding* reason_metadata_key_binding(uint32_t caller_return_rva) noexcept {
    if (!reason_metadata_keys_verified) return nullptr;
    for (const KeyBinding& binding:kConfirmedKeyBindings) {
        if (binding.caller_return_rva==caller_return_rva) return &binding;
    }
    return nullptr;
}

static bool reason_metadata_validate_keys() noexcept {
    if (!base) return false;
    for (const KeyBinding& binding:kConfirmedKeyBindings) {
        const SIZE_T bytes=static_cast<SIZE_T>(strlen(binding.key)+1);
        unsigned char actual[64]{};
        if (bytes>sizeof(actual)
            || !reason_metadata_read_bytes(base+binding.rdata_rva,actual,bytes)
            || memcmp(actual,binding.key,bytes)!=0) return false;
    }
    for (const auto& conditional:bridge_reason_key_branch::kBindings) {
        const KeyBinding* variants[]={&conditional.standard,&conditional.overlord};
        for (const KeyBinding* binding:variants) {
            const SIZE_T bytes=static_cast<SIZE_T>(strlen(binding->key)+1);
            unsigned char actual[64]{};
            if (bytes>sizeof(actual)
                || !reason_metadata_read_bytes(base+binding->rdata_rva,actual,bytes)
                || memcmp(actual,binding->key,bytes)!=0) return false;
        }
    }
    return true;
}

static bool reason_metadata_copy_key(ReasonMetadataRecord& record,
    const KeyBinding* binding) noexcept {
    if (!binding) return false;
    const SIZE_T size=strlen(binding->key);
    if (size>=sizeof(record.localization_key)) return false;
    memcpy(record.localization_key,binding->key,size);
    record.localization_key[size]='\0';
    record.localization_rdata_rva=binding->rdata_rva;
    record.constructor_source_confirmed=true;
    return true;
}

static void reason_metadata_capture_string(ReasonMetadataRecord& record,
    const unsigned char* row) noexcept {
    memcpy(&record.string_size,row+0x08+0x10,sizeof(record.string_size));
    memcpy(&record.string_capacity,row+0x08+0x18,sizeof(record.string_capacity));
    record.string_inline=record.string_capacity<16;
    record.text_truncated=record.string_size>kTextCapacity;
    record.text_bytes=static_cast<unsigned>(record.string_size<=kTextCapacity
        ? record.string_size:kTextCapacity);
    record.string_shape_valid=record.string_size<=record.string_capacity
        && record.string_capacity<=kMaxStringCapacity
        && (record.string_inline || record.string_capacity>=16);
    if (!record.string_shape_valid) return;
    if (!record.text_bytes) {
        record.text_readable=true;
        return;
    }
    uintptr_t text_address=reinterpret_cast<uintptr_t>(row+0x08);
    if (!record.string_inline) memcpy(&text_address,row+0x08,sizeof(text_address));
    if (!text_address) return;
    record.text_readable=reason_metadata_read_bytes(text_address,record.text,
        record.text_bytes);
}

static void reason_metadata_capture(void* thisrow,void* returned,
    int32_t argument_value,unsigned char incoming_flag,
    uintptr_t caller_return,DWORD returned_last_error) noexcept {
    if (!reason_metadata_scope.depth) return;
    if (reason_metadata_scope.count>=kRecordCapacity) {
        reason_metadata_scope.overflow=true;
        return;
    }
    ReasonMetadataRecord& record=reason_metadata_scope.records[
        reason_metadata_scope.count++];
    record=ReasonMetadataRecord{};
    record.sequence=++reason_metadata_scope.next_sequence;
    record.caller_return_rva=reason_metadata_rva(caller_return);
    record.constructor_call_rva=record.caller_return_rva>=5
        ?record.caller_return_rva-5:0;
    record.constructor_argument_value=argument_value;
    record.incoming_flag=incoming_flag;
    record.returned_last_error=returned_last_error;
    record.returned_row_matches=returned==thisrow;
    if (!thisrow) return;
    memcpy(record.row_raw,thisrow,kRowBytes);
    record.row_readable=true;
    memcpy(&record.raw_value,record.row_raw,sizeof(record.raw_value));
    record.derived_flag=record.row_raw[0x28];
    reason_metadata_capture_string(record,record.row_raw);
    const KeyBinding* binding=reason_metadata_key_binding(record.caller_return_rva);
    if (!binding && reason_metadata_keys_verified) {
        binding=bridge_reason_key_branch::select(record.caller_return_rva,
            reinterpret_cast<uintptr_t>(thisrow),
            [](uintptr_t address,unsigned char& value) noexcept {
                return reason_metadata_read_bytes(address,&value,sizeof(value));
            },record.key_branch);
    }
    reason_metadata_copy_key(record,binding);
}

static void reason_metadata_absolute_jump(unsigned char* destination,
    uintptr_t target) noexcept {
    destination[0]=0xff;
    destination[1]=0x25;
    memset(destination+2,0,4);
    memcpy(destination+6,&target,sizeof(target));
}

static unsigned char* reason_metadata_allocate_near() noexcept {
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

static bool reason_metadata_register_unwind() noexcept {
    DWORD64 image_base=0;
    PRUNTIME_FUNCTION source=RtlLookupFunctionEntry(
        static_cast<DWORD64>(base+kRowConstructorRva),&image_base,nullptr);
    if (!source || image_base!=static_cast<DWORD64>(base)) return false;
    const uintptr_t trampoline_rva=reinterpret_cast<uintptr_t>(
        reason_metadata_trampoline)-base;
    if (trampoline_rva>0xffffffffull
        || trampoline_rva+reason_metadata_trampoline_size>0xffffffffull)
        return false;
    reason_metadata_runtime_function.BeginAddress=
        static_cast<DWORD>(trampoline_rva);
    reason_metadata_runtime_function.EndAddress=static_cast<DWORD>(
        trampoline_rva+reason_metadata_trampoline_size);
    reason_metadata_runtime_function.UnwindData=source->UnwindData;
    if (!RtlAddFunctionTable(&reason_metadata_runtime_function,1,
        static_cast<DWORD64>(base))) return false;
    reason_metadata_runtime_registered=true;
    return true;
}

static void reason_metadata_release_unpublished() noexcept {
    if (reason_metadata_runtime_registered && !reason_metadata_published) {
        RtlDeleteFunctionTable(&reason_metadata_runtime_function);
        reason_metadata_runtime_registered=false;
    }
    if (reason_metadata_block && !reason_metadata_published) {
        VirtualFree(reason_metadata_block,0,MEM_RELEASE);
        reason_metadata_block=nullptr;
        reason_metadata_trampoline=nullptr;
    }
}

// The wrapper deliberately has the native four-register Win64 signature.
// With an absolute JMP at the native entry there is no additional return
// address, so the builtin return address is the caller's address after CALL.
#if defined(__GNUC__)
extern "C" __attribute__((noinline))
#elif defined(_MSC_VER)
extern "C" __declspec(noinline)
#else
extern "C"
#endif
void* bridge_alliance_reason_metadata_ctor(void* thisrow,
    void* source,std::int32_t value,unsigned char incoming_flag) noexcept {
    using NativeConstructor=void* (*)(void*,void*,std::int32_t,unsigned char);
    const DWORD incoming_last_error=GetLastError();
    const NativeConstructor original=reinterpret_cast<NativeConstructor>(
        reason_metadata_original);
    if (!original) {
        SetLastError(incoming_last_error);
        return thisrow;
    }
    void* returned=original(thisrow,source,value,incoming_flag);
    const DWORD returned_last_error=GetLastError();
    if (reason_metadata_scope.depth) {
#if defined(_MSC_VER)
        const uintptr_t caller_return=reinterpret_cast<uintptr_t>(_ReturnAddress());
#else
        const uintptr_t caller_return=reinterpret_cast<uintptr_t>(
            __builtin_return_address(0));
#endif
        reason_metadata_capture(thisrow,returned,value,incoming_flag,
            caller_return,returned_last_error);
    }
    // ReadProcessMemory in capture may change the thread error slot.  The
    // native caller observes the original constructor's post-call value.
    SetLastError(returned_last_error);
    return returned;
}

extern "C" void bridge_alliance_reason_metadata_scope_begin() noexcept {
    if (!reason_metadata_scope.depth) {
        reason_metadata_scope=ScopeState{};
    }
    if (reason_metadata_scope.depth!=0xffffffffu) ++reason_metadata_scope.depth;
}

extern "C" bool bridge_alliance_reason_metadata_scope_active() noexcept {
    return reason_metadata_scope.depth!=0;
}

extern "C" void bridge_alliance_reason_metadata_scope_end() noexcept {
    if (reason_metadata_scope.depth) --reason_metadata_scope.depth;
}

extern "C" unsigned bridge_alliance_reason_metadata_scope_count(
    bool* overflow) noexcept {
    if (overflow) *overflow=reason_metadata_scope.overflow;
    return reason_metadata_scope.count;
}

extern "C" const ReasonMetadataRecord*
bridge_alliance_reason_metadata_scope_record(unsigned index) noexcept {
    return index<reason_metadata_scope.count
        ?&reason_metadata_scope.records[index]:nullptr;
}

extern "C" bool bridge_alliance_reason_metadata_keys_verified() noexcept {
    return reason_metadata_keys_verified;
}

static bool reason_metadata_prepare_trampoline() noexcept {
    reason_metadata_block=reason_metadata_allocate_near();
    if (!reason_metadata_block) return false;
    reason_metadata_trampoline=reason_metadata_block+kTrampolineOffset;
    memcpy(reason_metadata_trampoline,kExpectedPrologue,kPatchBytes);
    reason_metadata_absolute_jump(reason_metadata_trampoline+kPatchBytes,
        base+kRowConstructorRva+kPatchBytes);
    DWORD old_protection=0;
    if (!VirtualProtect(reason_metadata_block,kNearBlockBytes,PAGE_EXECUTE_READ,
        &old_protection)
        || !FlushInstructionCache(GetCurrentProcess(),reason_metadata_block,
            kNearBlockBytes)) {
        reason_metadata_release_unpublished();
        return false;
    }
    if (!reason_metadata_register_unwind()) {
        reason_metadata_release_unpublished();
        return false;
    }
    return true;
}

extern "C" bool bridge_alliance_reason_metadata_install() noexcept {
    if (reason_metadata_installed) return true;
    const bridge_entry_patch::PatchResult pending=
        bridge_entry_patch::guarded_patch_retry_pending();
    if (pending.pending_count || !pending.success) return false;
    reason_metadata_keys_verified=reason_metadata_validate_keys();
    if (!reason_metadata_keys_verified) return false;
    auto target=reinterpret_cast<unsigned char*>(base+kRowConstructorRva);
    unsigned char actual[kPatchBytes]{};
    if (!reason_metadata_read_bytes(reinterpret_cast<uintptr_t>(target),actual,
        sizeof(actual)) || memcmp(actual,kExpectedPrologue,kPatchBytes)!=0)
        return false;
    if (!reason_metadata_prepare_trampoline()) return false;
    reason_metadata_original=reason_metadata_trampoline;
    memset(reason_metadata_replacement,0x90,sizeof(reason_metadata_replacement));
    reason_metadata_absolute_jump(reason_metadata_replacement,
        reinterpret_cast<uintptr_t>(&bridge_alliance_reason_metadata_ctor));
    reason_metadata_patch_plan=bridge_entry_patch::PatchPlan{};
    reason_metadata_patch_plan.count=1;
    reason_metadata_patch_plan.targets[0]={target,kPatchBytes,kExpectedPrologue,
        reason_metadata_replacement,reason_metadata_trampoline,
        reason_metadata_trampoline_size};
    const bridge_entry_patch::PatchResult result=
        bridge_entry_patch::guarded_patch_apply(reason_metadata_patch_plan);
    reason_metadata_published=result.published;
    reason_metadata_installed=result.success;
    if (!result.success && !result.published) {
        reason_metadata_original=nullptr;
        reason_metadata_release_unpublished();
    }
    return result.success;
}

extern "C" bool bridge_alliance_reason_metadata_rollback() noexcept {
    reason_metadata_scope.depth=0;
    if (!reason_metadata_patch_plan.count) return true;
    unsigned char actual[kPatchBytes]{};
    auto target=reinterpret_cast<unsigned char*>(base+kRowConstructorRva);
    if (!reason_metadata_read_bytes(reinterpret_cast<uintptr_t>(target),actual,
        sizeof(actual))) return false;
    if (!memcmp(actual,kExpectedPrologue,kPatchBytes)) {
        reason_metadata_installed=false;
        reason_metadata_published=false;
        return true;
    }
    if (memcmp(actual,reason_metadata_replacement,kPatchBytes)!=0) return false;
    const bridge_entry_patch::PatchResult result=
        bridge_entry_patch::guarded_patch_rollback(reason_metadata_patch_plan);
    const bool complete=result.success && result.threads_resumed
        && result.protection_restored;
    if (complete) {
        reason_metadata_installed=false;
        reason_metadata_published=false;
    }
    return complete;
}

} // namespace bridge_alliance_reason_metadata_detail

using bridge_alliance_reason_metadata_detail::ReasonMetadataRecord;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_ctor;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_install;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_keys_verified;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_rollback;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_scope_active;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_scope_begin;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_scope_count;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_scope_end;
using bridge_alliance_reason_metadata_detail::bridge_alliance_reason_metadata_scope_record;

#endif
