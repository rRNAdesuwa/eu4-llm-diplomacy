#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstring>

#include "entry-patch-transaction.inc"

// frame_stub.S supplies the production direct-break pass-through.  The
// fixture supplies the other callbacks/globals only to make that complete
// assembly unit linkable in an isolated process; none of them touches EU4.
extern "C" void bridge_direct_break_stub();
extern "C" void bridge_direct_break_float_stub();
extern "C" void bridge_wrapper_reader_stub();
extern "C" void* bridge_wrapper_clone_stub(void*,void*);
extern "C" void* fixture_wrapper_clone_caller(void*,void*);
extern "C" void fixture_wrapper_clone_return_label();
extern "C" void bridge_direct_break_observe(void*, std::uint64_t,
    std::uint64_t, std::uint64_t);
extern "C" void bridge_wrapper_reader_observe(void*, std::uint64_t,
    std::uint64_t, std::uint64_t);
extern "C" void* bridge_wrapper_clone_observe(void*,void*,std::uintptr_t,
    void*);

extern "C" {
void* bridge_direct_break_original=nullptr;
void* bridge_direct_break_float_original=nullptr;
void* bridge_wrapper_reader_original=nullptr;
void* bridge_wrapper_clone_original=nullptr;
void* bridge_field_reader_original=nullptr;
void* bridge_trampoline=nullptr;
void* bridge_serializer_original=nullptr;
void* bridge_response_original=nullptr;
}

extern "C" void bridge_field_reader_observe(...) {}
extern "C" void bridge_frame_tick(...) {}
extern "C" void bridge_serializer_observe(...) {}
extern "C" int bridge_response_observe(...) { return 1; }

extern "C" volatile LONG g_wrapper_clone_rbp_ok=0;

extern "C" std::uint64_t fixture_integer_target(std::uint64_t,
    std::uint64_t, std::uint64_t, std::uint64_t, std::uint64_t,
    std::uint64_t);
extern "C" double fixture_float_target(double, double, double, double,
    double, double);
extern "C" std::uint64_t fixture_integer_body(std::uint64_t,
    std::uint64_t, std::uint64_t, std::uint64_t, std::uint64_t,
    std::uint64_t);
extern "C" double fixture_float_body(double, double, double, double,
    double, double);

static volatile LONG64 g_integer_original_calls=0;
static volatile LONG64 g_float_original_calls=0;
static volatile LONG64 g_observer_calls=0;
static volatile LONG64 g_direct_observer_calls=0;
static volatile LONG64 g_wrapper_observer_calls=0;
static volatile LONG64 g_wrapper_clone_callback_calls=0;
static volatile LONG64 g_wrapper_clone_original_calls=0;
static volatile LONG64 g_wrapper_clone_bad=0;
static volatile LONG64 g_wrapper_clone_return_ok=0;
static volatile LONG64 g_bad_results=0;
static volatile LONG64 g_spawned_workers=0;
static volatile LONG g_stop=0;

static std::uint64_t integer_expected(std::uint64_t a,std::uint64_t b,
    std::uint64_t c,std::uint64_t d,std::uint64_t e,std::uint64_t f) {
    return a*17u+b*19u+c*23u+d*29u+e*31u+f*37u+
        UINT64_C(0x9e3779b97f4a7c15);
}

static double float_expected(double a,double b,double c,double d,double e,
    double f) {
    return a+2.0*b+3.0*c+4.0*d+5.0*e+6.0*f+0.125;
}

extern "C" void bridge_direct_break_observe(void*,std::uint64_t,
    std::uint64_t,std::uint64_t) {
    InterlockedIncrement64(&g_observer_calls);
    InterlockedIncrement64(&g_direct_observer_calls);
}

// The wrapper-reader symbol is supplied here only for the isolated fixture.
// It deliberately leaves every argument and floating-point register alone;
// the production assembly stub is responsible for saving/restoring them.
extern "C" void bridge_wrapper_reader_observe(void*,std::uint64_t,
    std::uint64_t,std::uint64_t) {
    InterlockedIncrement64(&g_observer_calls);
    InterlockedIncrement64(&g_wrapper_observer_calls);
}

static void* g_expected_clone_receiver=nullptr;
static void* g_expected_clone_action=nullptr;
static void* g_expected_clone_result=nullptr;
static const std::uintptr_t kCloneCallerMarker=
    UINT64_C(0x6a6b6c6d6e6f7071);

extern "C" void* fixture_wrapper_clone_body(void* receiver,void* action) {
    InterlockedIncrement64(&g_wrapper_clone_original_calls);
    if (receiver!=g_expected_clone_receiver || action!=g_expected_clone_action)
        InterlockedIncrement64(&g_wrapper_clone_bad);
    return g_expected_clone_result;
}

extern "C" void* bridge_wrapper_clone_observe(void* receiver,void* action,
    std::uintptr_t return_label,void* caller_marker) {
    InterlockedIncrement64(&g_wrapper_clone_callback_calls);
    if (receiver!=g_expected_clone_receiver || action!=g_expected_clone_action
        || return_label!=reinterpret_cast<std::uintptr_t>(
            &fixture_wrapper_clone_return_label)
        || reinterpret_cast<std::uintptr_t>(caller_marker)
            !=kCloneCallerMarker) {
        InterlockedIncrement64(&g_wrapper_clone_bad);
    }
    using CloneOriginal=void* (*)(void*,void*);
    const CloneOriginal original=reinterpret_cast<CloneOriginal>(
        bridge_wrapper_clone_original);
    if (!original) {
        InterlockedIncrement64(&g_wrapper_clone_bad);
        return nullptr;
    }
    void* result=original(receiver,action);
    if (result==g_expected_clone_result)
        InterlockedIncrement64(&g_wrapper_clone_return_ok);
    else
        InterlockedIncrement64(&g_wrapper_clone_bad);
    return result;
}

extern "C" std::uint64_t fixture_integer_body(std::uint64_t a,
    std::uint64_t b,std::uint64_t c,std::uint64_t d,std::uint64_t e,
    std::uint64_t f) {
    InterlockedIncrement64(&g_integer_original_calls);
    return integer_expected(a,b,c,d,e,f);
}

extern "C" double fixture_float_body(double a,double b,double c,double d,
    double e,double f) {
    InterlockedIncrement64(&g_float_original_calls);
    return float_expected(a,b,c,d,e,f);
}

static const unsigned kPatchSize=15;
static const unsigned kTrampolineSize=29;
static const unsigned char kExpected[kPatchSize]={
    0x48,0x89,0x5c,0x24,0x08,
    0x48,0x89,0x6c,0x24,0x10,
    0x48,0x89,0x74,0x24,0x18
};

static void write_absolute_jump(unsigned char* destination,const void* target) {
    const std::uint64_t address=reinterpret_cast<std::uint64_t>(target);
    destination[0]=0x48;
    destination[1]=0xb8;
    std::memcpy(destination+2,&address,sizeof(address));
    destination[10]=0xff;
    destination[11]=0xe0;
    destination[12]=0x90;
    destination[13]=0x90;
}

struct FixtureTrampoline {
    unsigned char* code=nullptr;
};

static bool make_trampoline(void* target,FixtureTrampoline& out) {
    unsigned char* code=static_cast<unsigned char*>(VirtualAlloc(nullptr,
        kTrampolineSize,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if (!code) return false;
    std::memcpy(code,kExpected,kPatchSize);
    write_absolute_jump(code+kPatchSize,
        static_cast<unsigned char*>(target)+kPatchSize);
    DWORD old_protection=0;
    if (!VirtualProtect(code,kTrampolineSize,PAGE_EXECUTE_READ,
        &old_protection)) {
        VirtualFree(code,0,MEM_RELEASE);
        return false;
    }
    if (!FlushInstructionCache(GetCurrentProcess(),code,kTrampolineSize)) {
        VirtualFree(code,0,MEM_RELEASE);
        return false;
    }
    out.code=code;
    return true;
}

static void make_replacement(unsigned char (&replacement)[kPatchSize],
    void* stub) {
    std::memset(replacement,0x90,sizeof(replacement));
    write_absolute_jump(replacement,stub);
}

static bool bytes_equal(const void* address,const unsigned char* expected) {
    return std::memcmp(address,expected,kPatchSize)==0;
}

struct UnwindReport {
    bool passed=false;
    unsigned points=0;
    unsigned lookup_failures=0;
    unsigned unwind_failures=0;
    bool found_sub=false;
    bool found_add=false;
    bool found_tailjmp=false;
};

static const unsigned char* find_opcode(const unsigned char* start,
    std::size_t length,const unsigned char* pattern,std::size_t pattern_length) {
    if (!start || !pattern || !pattern_length || length<pattern_length)
        return nullptr;
    for (std::size_t offset=0;offset+pattern_length<=length;++offset) {
        if (!std::memcmp(start+offset,pattern,pattern_length))
            return start+offset;
    }
    return nullptr;
}

static bool unwind_at(const unsigned char* pc,unsigned char* current_rsp,
    unsigned char* caller_rsp,std::uint64_t return_address,
    UnwindReport& report) {
    DWORD64 image_base=0;
    PRUNTIME_FUNCTION function=RtlLookupFunctionEntry(
        reinterpret_cast<DWORD64>(pc),&image_base,nullptr);
    if (!function) {
        ++report.lookup_failures;
        return false;
    }

    CONTEXT context{};
    context.ContextFlags=CONTEXT_CONTROL;
    context.Rip=reinterpret_cast<DWORD64>(pc);
    context.Rsp=reinterpret_cast<DWORD64>(current_rsp);
    PVOID handler_data=nullptr;
    DWORD64 establisher_frame=0;
    KNONVOLATILE_CONTEXT_POINTERS nonvolatile{};
    (void)RtlVirtualUnwind(UNW_FLAG_NHANDLER,image_base,
        reinterpret_cast<DWORD64>(pc),function,&context,&handler_data,
        &establisher_frame,&nonvolatile);
    if (context.Rip!=return_address
        || context.Rsp!=reinterpret_cast<DWORD64>(caller_rsp+sizeof(DWORD64))) {
        ++report.unwind_failures;
        return false;
    }
    ++report.points;
    return true;
}

// This uses the real PE unwind metadata emitted by the current frame_stub.S.
// It locates instruction boundaries in the linked stub, then feeds an
// artificial caller stack to the Windows unwind API.  No replacement or
// hand-written mirror of the production stub is involved.
static UnwindReport validate_frame_stub_unwind() {
    UnwindReport report{};
    const unsigned char* entry=reinterpret_cast<const unsigned char*>(
        &bridge_direct_break_stub);
    const unsigned char sub_pattern[]={0x48,0x81,0xec,0xc8,0x00,0x00,0x00};
    const unsigned char add_pattern[]={0x48,0x81,0xc4,0xc8,0x00,0x00,0x00};
    const unsigned char tail_pattern[]={0xff,0x25};
    const unsigned char* sub=find_opcode(entry,0x100,sub_pattern,
        sizeof(sub_pattern));
    const unsigned char* add=find_opcode(entry,0x100,add_pattern,
        sizeof(add_pattern));
    const unsigned char* tail=find_opcode(entry,0x100,tail_pattern,
        sizeof(tail_pattern));
    report.found_sub=sub && sub==entry;
    report.found_add=add && add>entry;
    report.found_tailjmp=tail && tail>add;
    if (!report.found_sub || !report.found_add || !report.found_tailjmp)
        return report;

    constexpr SIZE_T kStackBytes=0x1000;
    unsigned char* synthetic_stack=static_cast<unsigned char*>(VirtualAlloc(
        nullptr,kStackBytes,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if (!synthetic_stack) return report;
    unsigned char* caller_rsp=synthetic_stack+0x208; // 8 mod 16 at entry.
    const std::uint64_t return_address=UINT64_C(0x1122334455667788);
    *reinterpret_cast<std::uint64_t*>(caller_rsp)=return_address;

    // Before SUB the function has the caller's RSP.  At the first body
    // instruction the real SUB has executed.  The ADD-after and tail-jump
    // points use the restored caller RSP.
    const bool before_ok=unwind_at(entry,caller_rsp,caller_rsp,
        return_address,report);
    const bool body_ok=unwind_at(sub+sizeof(sub_pattern),
        caller_rsp-0xc8,caller_rsp,return_address,report);
    const bool add_after_ok=unwind_at(add+sizeof(add_pattern),caller_rsp,
        caller_rsp,return_address,report);
    const bool jmp_ok=unwind_at(tail,caller_rsp,caller_rsp,return_address,
        report);
    VirtualFree(synthetic_stack,0,MEM_RELEASE);
    report.passed=before_ok && body_ok && add_after_ok && jmp_ok
        && report.points==4 && report.lookup_failures==0
        && report.unwind_failures==0;
    return report;
}

// Calls the actual bridge_wrapper_clone_stub from the current frame_stub.S
// through a legal synthetic Win64 caller.  The shim obtains R8 from the
// pushed return address and R9 from the caller's fixed RBP marker; the
// callback then invokes the two-argument original exactly once.
static bool validate_wrapper_clone_abi() {
    const void* receiver=reinterpret_cast<void*>(
        static_cast<std::uintptr_t>(UINT64_C(0x1111222233334444)));
    const void* action=reinterpret_cast<void*>(
        static_cast<std::uintptr_t>(UINT64_C(0x5555666677778888)));
    void* expected_result=reinterpret_cast<void*>(
        static_cast<std::uintptr_t>(UINT64_C(0x9999aaaabbbbcccc)));
    g_expected_clone_receiver=const_cast<void*>(receiver);
    g_expected_clone_action=const_cast<void*>(action);
    g_expected_clone_result=expected_result;
    bridge_wrapper_clone_original=reinterpret_cast<void*>(
        &fixture_wrapper_clone_body);
    InterlockedExchange64(&g_wrapper_clone_callback_calls,0);
    InterlockedExchange64(&g_wrapper_clone_original_calls,0);
    InterlockedExchange64(&g_wrapper_clone_bad,0);
    InterlockedExchange64(&g_wrapper_clone_return_ok,0);
    InterlockedExchange(&g_wrapper_clone_rbp_ok,0);

    void* actual=fixture_wrapper_clone_caller(
        const_cast<void*>(receiver),const_cast<void*>(action));
    return actual==expected_result
        && InterlockedCompareExchange64(&g_wrapper_clone_callback_calls,0,0)
            ==1
        && InterlockedCompareExchange64(&g_wrapper_clone_original_calls,0,0)
            ==1
        && InterlockedCompareExchange64(&g_wrapper_clone_return_ok,0,0)==1
        && InterlockedCompareExchange64(&g_wrapper_clone_bad,0,0)==0
        && InterlockedCompareExchange(&g_wrapper_clone_rbp_ok,0,0)==1;
}

static bool stop_requested() {
    return InterlockedCompareExchange(&g_stop,0,0)!=0;
}

static void run_one_probe() {
    const std::uint64_t seed=static_cast<std::uint64_t>(
        InterlockedIncrement64(&g_spawned_workers));
    const std::uint64_t a=seed+1;
    const std::uint64_t b=seed+2;
    const std::uint64_t c=seed+3;
    const std::uint64_t d=seed+4;
    const std::uint64_t e=seed+5;
    const std::uint64_t f=seed+6;
    if (fixture_integer_target(a,b,c,d,e,f)!=integer_expected(a,b,c,d,e,f))
        InterlockedIncrement64(&g_bad_results);
    const double base=static_cast<double>(seed)*0.03125;
    if (fixture_float_target(base,base+0.25,base+0.5,base+0.75,
        base+1.0,base+1.25)!=float_expected(base,base+0.25,base+0.5,
        base+0.75,base+1.0,base+1.25))
        InterlockedIncrement64(&g_bad_results);
}

static DWORD WINAPI target_worker(void*) {
    std::uint64_t sequence=1;
    while (!stop_requested()) {
        const std::uint64_t a=sequence+1;
        const std::uint64_t b=sequence+3;
        const std::uint64_t c=sequence+5;
        const std::uint64_t d=sequence+7;
        const std::uint64_t e=sequence+9;
        const std::uint64_t f=sequence+11;
        if (fixture_integer_target(a,b,c,d,e,f)!=integer_expected(a,b,c,d,e,f))
            InterlockedIncrement64(&g_bad_results);
        const double base=static_cast<double>(sequence&0x3ffu)*0.0625;
        const double actual=fixture_float_target(base,base+0.5,base+1.0,
            base+1.5,base+2.0,base+2.5);
        if (actual!=float_expected(base,base+0.5,base+1.0,base+1.5,
            base+2.0,base+2.5)) InterlockedIncrement64(&g_bad_results);
        ++sequence;
        // Keep calls continuous for the duration of the fixture, but give
        // the transaction's bounded RIP check a normal instruction boundary
        // between calls instead of deliberately spinning in the 15-byte
        // prologue.
        Sleep(1);
    }
    return 0;
}

static DWORD WINAPI short_probe_worker(void*) {
    for (unsigned i=0;i<8 && !stop_requested();++i) {
        run_one_probe();
        Sleep(1);
    }
    return 0;
}

static DWORD WINAPI spawner_worker(void*) {
    while (!stop_requested()) {
        HANDLE child=CreateThread(nullptr,0,short_probe_worker,nullptr,0,
            nullptr);
        if (child) {
            WaitForSingleObject(child,INFINITE);
            CloseHandle(child);
        }
        // Keep creation active during the transaction while leaving a small
        // interval in which the Toolhelp snapshot cannot observe a child
        // that has just terminated.
        Sleep(10);
    }
    return 0;
}

static bool drain_pending() {
    for (unsigned i=0;i<8;++i) {
        bridge_entry_patch::PatchResult result=
            bridge_entry_patch::guarded_patch_retry_pending();
        if (!result.pending_count) return true;
        Sleep(1);
    }
    return false;
}

static bool stop_and_join(HANDLE* workers,unsigned worker_count,HANDLE spawner) {
    InterlockedExchange(&g_stop,1);
    bool complete=true;
    if (spawner) {
        if (WaitForSingleObject(spawner,10000)!=WAIT_OBJECT_0) complete=false;
        CloseHandle(spawner);
    }
    for (unsigned i=0;i<worker_count;++i) {
        if (!workers[i]) continue;
        if (WaitForSingleObject(workers[i],10000)!=WAIT_OBJECT_0)
            complete=false;
        CloseHandle(workers[i]);
    }
    return complete;
}

struct FixtureReport {
    bool passed=false;
    bool unwind_passed=false;
    unsigned unwind_points=0;
    unsigned unwind_lookup_failures=0;
    unsigned unwind_failures=0;
    unsigned rounds=0;
    unsigned attempts=0;
    bool signature_invalid_published=true;
    bool direct_float_frame_passed=false;
    bool wrapper_clone_passed=false;
    bool wrapper_integer_passed=false;
    bool wrapper_float_passed=false;
    bool bytes_restored=false;
    bool threads_joined=false;
    bool pending_zero=false;
    unsigned last_apply_status=0;
    unsigned last_rollback_status=0;
    unsigned last_failure_stage=0;
};

static FixtureReport execute_fixture() {
    FixtureReport report{};
    HANDLE workers[4]{};
    unsigned worker_count=0;
    HANDLE spawner=nullptr;
    FixtureTrampoline integer_trampoline{};
    FixtureTrampoline float_trampoline{};
    unsigned char integer_replacement[kPatchSize]{};
    unsigned char float_replacement[kPatchSize]{};
    bridge_entry_patch::PatchPlan plan{};
    UnwindReport unwind{};

    report.wrapper_clone_passed=validate_wrapper_clone_abi();
    if (!report.wrapper_clone_passed) goto cleanup;

    unwind=validate_frame_stub_unwind();
    report.unwind_passed=unwind.passed;
    report.unwind_points=unwind.points;
    report.unwind_lookup_failures=unwind.lookup_failures;
    report.unwind_failures=unwind.unwind_failures;
    if (!report.unwind_passed) goto cleanup;

    if (!make_trampoline(reinterpret_cast<void*>(&fixture_integer_target),
        integer_trampoline)
        || !make_trampoline(reinterpret_cast<void*>(&fixture_float_target),
            float_trampoline)) goto cleanup;
    make_replacement(integer_replacement,
        reinterpret_cast<void*>(&bridge_direct_break_stub));
    make_replacement(float_replacement,
        reinterpret_cast<void*>(&bridge_direct_break_float_stub));

    bridge_direct_break_original=integer_trampoline.code;
    bridge_direct_break_float_original=float_trampoline.code;

    plan.count=2;
    plan.targets[0].address=reinterpret_cast<void*>(&fixture_integer_target);
    plan.targets[0].size=kPatchSize;
    plan.targets[0].expected=kExpected;
    plan.targets[0].replacement=integer_replacement;
    plan.targets[0].original_trampoline=integer_trampoline.code;
    plan.targets[0].original_trampoline_size=kTrampolineSize;
    plan.targets[1].address=reinterpret_cast<void*>(&fixture_float_target);
    plan.targets[1].size=kPatchSize;
    plan.targets[1].expected=kExpected;
    plan.targets[1].replacement=float_replacement;
    plan.targets[1].original_trampoline=float_trampoline.code;
    plan.targets[1].original_trampoline_size=kTrampolineSize;

    InterlockedExchange(&g_stop,0);
    for (unsigned i=0;i<3;++i) {
        workers[worker_count]=CreateThread(nullptr,0,target_worker,nullptr,0,
            nullptr);
        if (!workers[worker_count]) goto cleanup;
        ++worker_count;
    }
    spawner=CreateThread(nullptr,0,spawner_worker,nullptr,0,nullptr);
    if (!spawner) goto cleanup;
    Sleep(50);

    while (report.rounds<10 && report.attempts<40) {
        ++report.attempts;
        bridge_entry_patch::PatchResult applied=
            bridge_entry_patch::guarded_patch_apply(plan);
        report.last_apply_status=static_cast<unsigned>(applied.status);
        report.last_failure_stage=static_cast<unsigned>(applied.failure_stage);
        if (!applied.success) {
            if (applied.pending_count) drain_pending();
            // A barrier-only failure is safe to retry after the helper has
            // restored the source image.  A committed or otherwise
            // unreconciled transaction is intentionally not retried.
            if (applied.status==bridge_entry_patch::PatchStatus::restart_required
                || (applied.published && !applied.rollback_complete)
                || !bytes_equal(reinterpret_cast<void*>(&fixture_integer_target),
                    kExpected)
                || !bytes_equal(reinterpret_cast<void*>(&fixture_float_target),
                    kExpected)) goto cleanup;
            continue;
        }
        if (!bytes_equal(reinterpret_cast<void*>(&fixture_integer_target),
            integer_replacement)
            || !bytes_equal(reinterpret_cast<void*>(&fixture_float_target),
                float_replacement)) goto cleanup;
        Sleep(1);
        bool rollback_ok=false;
        for (unsigned rollback_try=0;rollback_try<4 && !rollback_ok;
            ++rollback_try) {
            bridge_entry_patch::PatchResult rolled=
                bridge_entry_patch::guarded_patch_rollback(plan);
            report.last_rollback_status=static_cast<unsigned>(rolled.status);
            report.last_failure_stage=static_cast<unsigned>(rolled.failure_stage);
            const bool restored=bytes_equal(
                reinterpret_cast<void*>(&fixture_integer_target),kExpected)
                && bytes_equal(reinterpret_cast<void*>(&fixture_float_target),
                    kExpected);
            if (rolled.status!=bridge_entry_patch::PatchStatus::restart_required
                && (!rolled.published || rolled.rollback_complete)
                && restored) {
                rollback_ok=true;
                break;
            }
            if (rolled.pending_count) drain_pending();
            if (rolled.status==bridge_entry_patch::PatchStatus::restart_required)
                break;
        }
        if (!rollback_ok) goto cleanup;
        // A thread-open/termination race can make the helper report a safe
        // rollback_complete result with success=false; source bytes and
        // cleanup state are the acceptance conditions for this fixture.
        ++report.rounds;
    }

    // The two-target stress plan above keeps the historical fixture float
    // shim as a second target.  Also run the current production direct shim
    // against the floating-point target by itself, so its XMM save/restore
    // path is independently exercised.
    {
        unsigned char direct_float_current_replacement[kPatchSize]{};
        make_replacement(direct_float_current_replacement,
            reinterpret_cast<void*>(&bridge_direct_break_stub));
        bridge_direct_break_original=float_trampoline.code;
        bridge_entry_patch::PatchPlan direct_float_plan{};
        direct_float_plan.count=1;
        direct_float_plan.targets[0].address=
            reinterpret_cast<void*>(&fixture_float_target);
        direct_float_plan.targets[0].size=kPatchSize;
        direct_float_plan.targets[0].expected=kExpected;
        direct_float_plan.targets[0].replacement=
            direct_float_current_replacement;
        direct_float_plan.targets[0].original_trampoline=float_trampoline.code;
        direct_float_plan.targets[0].original_trampoline_size=kTrampolineSize;

        bool apply_ok=false;
        for (unsigned apply_try=0;apply_try<8 && !apply_ok;++apply_try) {
            bridge_entry_patch::PatchResult applied=
                bridge_entry_patch::guarded_patch_apply(direct_float_plan);
            report.last_apply_status=static_cast<unsigned>(applied.status);
            report.last_failure_stage=static_cast<unsigned>(
                applied.failure_stage);
            if (applied.success && bytes_equal(
                    reinterpret_cast<void*>(&fixture_float_target),
                    direct_float_current_replacement)) {
                apply_ok=true;
                break;
            }
            if (applied.pending_count && !drain_pending()) goto cleanup;
            if (applied.status
                    ==bridge_entry_patch::PatchStatus::restart_required
                || (applied.published && !applied.rollback_complete)
                || !bytes_equal(reinterpret_cast<void*>(&fixture_float_target),
                    kExpected)) goto cleanup;
        }
        if (!apply_ok) goto cleanup;

        bool float_calls_ok=true;
        for (unsigned i=0;i<24;++i) {
            const double base=0.5+static_cast<double>(i)*0.0625;
            const double actual=fixture_float_target(base,base+0.5,
                base+1.0,base+1.5,base+2.0,base+2.5);
            if (actual!=float_expected(base,base+0.5,base+1.0,base+1.5,
                base+2.0,base+2.5)) float_calls_ok=false;
        }

        bool rollback_ok=false;
        for (unsigned rollback_try=0;rollback_try<4 && !rollback_ok;
            ++rollback_try) {
            bridge_entry_patch::PatchResult rolled=
                bridge_entry_patch::guarded_patch_rollback(direct_float_plan);
            report.last_rollback_status=static_cast<unsigned>(rolled.status);
            report.last_failure_stage=static_cast<unsigned>(
                rolled.failure_stage);
            if (rolled.status!=bridge_entry_patch::PatchStatus::restart_required
                && (!rolled.published || rolled.rollback_complete)
                && bytes_equal(reinterpret_cast<void*>(&fixture_float_target),
                    kExpected)) {
                rollback_ok=true;
                break;
            }
            if (rolled.pending_count && !drain_pending()) goto cleanup;
            if (rolled.status==bridge_entry_patch::PatchStatus::restart_required)
                break;
        }
        report.direct_float_frame_passed=float_calls_ok && rollback_ok;
        if (!report.direct_float_frame_passed) goto cleanup;
    }

    // Exercise the new production wrapper-reader shim independently for both
    // ABI families.  The same caller-owned trampolines are reused only after
    // the direct plan has been fully rolled back; the wrapper global is
    // changed while its one-target transaction is quiescent.
    {
        unsigned char wrapper_integer_replacement[kPatchSize]{};
        unsigned char wrapper_float_replacement[kPatchSize]{};
        make_replacement(wrapper_integer_replacement,
            reinterpret_cast<void*>(&bridge_wrapper_reader_stub));
        make_replacement(wrapper_float_replacement,
            reinterpret_cast<void*>(&bridge_wrapper_reader_stub));

        auto wrapper_probe=[&](void* target,
            unsigned char* replacement,const void* trampoline,
            bool floating_point)->bool {
            bridge_wrapper_reader_original=const_cast<void*>(trampoline);
            bridge_entry_patch::PatchPlan wrapper_plan{};
            wrapper_plan.count=1;
            wrapper_plan.targets[0].address=target;
            wrapper_plan.targets[0].size=kPatchSize;
            wrapper_plan.targets[0].expected=kExpected;
            wrapper_plan.targets[0].replacement=replacement;
            wrapper_plan.targets[0].original_trampoline=trampoline;
            wrapper_plan.targets[0].original_trampoline_size=kTrampolineSize;
            bool applied_ok=false;
            for (unsigned apply_try=0;apply_try<8 && !applied_ok;
                ++apply_try) {
                bridge_entry_patch::PatchResult applied=
                    bridge_entry_patch::guarded_patch_apply(wrapper_plan);
                report.last_apply_status=static_cast<unsigned>(applied.status);
                report.last_failure_stage=static_cast<unsigned>(
                    applied.failure_stage);
                if (applied.success && bytes_equal(target,replacement)) {
                    applied_ok=true;
                    break;
                }
                if (applied.pending_count && !drain_pending()) return false;
                if (applied.status
                        ==bridge_entry_patch::PatchStatus::restart_required
                    || (applied.published && !applied.rollback_complete)
                    || !bytes_equal(target,kExpected)) return false;
            }
            if (!applied_ok) return false;

            bool calls_ok=true;
            for (unsigned i=0;i<24;++i) {
                if (floating_point) {
                    const double base=0.25+static_cast<double>(i)*0.03125;
                    const double actual=fixture_float_target(base,base+0.5,
                        base+1.0,base+1.5,base+2.0,base+2.5);
                    if (actual!=float_expected(base,base+0.5,base+1.0,
                        base+1.5,base+2.0,base+2.5)) calls_ok=false;
                } else {
                    const std::uint64_t seed=UINT64_C(0x1000)+i;
                    const std::uint64_t actual=fixture_integer_target(
                        seed+1,seed+2,seed+3,seed+4,seed+5,seed+6);
                    if (actual!=integer_expected(seed+1,seed+2,seed+3,
                        seed+4,seed+5,seed+6)) calls_ok=false;
                }
            }

            bool rollback_ok=false;
            for (unsigned rollback_try=0;rollback_try<4 && !rollback_ok;
                ++rollback_try) {
                bridge_entry_patch::PatchResult rolled=
                    bridge_entry_patch::guarded_patch_rollback(wrapper_plan);
                report.last_rollback_status=static_cast<unsigned>(rolled.status);
                report.last_failure_stage=static_cast<unsigned>(
                    rolled.failure_stage);
                const bool restored=bytes_equal(target,kExpected);
                if (rolled.status
                        !=bridge_entry_patch::PatchStatus::restart_required
                    && (!rolled.published || rolled.rollback_complete)
                    && restored) {
                    rollback_ok=true;
                    break;
                }
                if (rolled.pending_count && !drain_pending()) return false;
                if (rolled.status
                    ==bridge_entry_patch::PatchStatus::restart_required)
                    break;
            }
            return calls_ok && rollback_ok;
        };

        report.wrapper_integer_passed=wrapper_probe(
            reinterpret_cast<void*>(&fixture_integer_target),
            wrapper_integer_replacement,integer_trampoline.code,false);
        if (!report.wrapper_integer_passed) goto cleanup;
        report.wrapper_float_passed=wrapper_probe(
            reinterpret_cast<void*>(&fixture_float_target),
            wrapper_float_replacement,float_trampoline.code,true);
        if (!report.wrapper_float_passed) goto cleanup;
    }

    {
        unsigned char invalid_expected[kPatchSize]{};
        std::memcpy(invalid_expected,kExpected,kPatchSize);
        invalid_expected[0]^=0xffu;
        bridge_entry_patch::PatchPlan invalid_plan=plan;
        invalid_plan.count=1;
        invalid_plan.targets[0].expected=invalid_expected;
        bridge_entry_patch::PatchResult invalid=
            bridge_entry_patch::guarded_patch_apply(invalid_plan);
        report.signature_invalid_published=invalid.published;
        if (invalid.published || invalid.success
            || !bytes_equal(reinterpret_cast<void*>(&fixture_integer_target),
                kExpected)) goto cleanup;
    }

    report.bytes_restored=bytes_equal(
        reinterpret_cast<void*>(&fixture_integer_target),kExpected)
        && bytes_equal(reinterpret_cast<void*>(&fixture_float_target),kExpected);

cleanup:
    if (!drain_pending()) report.pending_zero=false;
    else report.pending_zero=true;
    report.bytes_restored=bytes_equal(
        reinterpret_cast<void*>(&fixture_integer_target),kExpected)
        && bytes_equal(reinterpret_cast<void*>(&fixture_float_target),kExpected);
    report.threads_joined=stop_and_join(workers,worker_count,spawner);
    report.passed=report.unwind_passed && report.unwind_points==4
        && report.direct_float_frame_passed
        && report.wrapper_clone_passed
        && report.wrapper_integer_passed && report.wrapper_float_passed
        && report.rounds>=10 && report.attempts<=40
        && !report.signature_invalid_published && report.bytes_restored
        && report.pending_zero && report.threads_joined
        && InterlockedCompareExchange64(&g_bad_results,0,0)==0
        && InterlockedCompareExchange64(&g_wrapper_observer_calls,0,0)>0;
    return report;
}

int main() {
    const FixtureReport report=execute_fixture();
    const unsigned long long integer_calls=static_cast<unsigned long long>(
        InterlockedCompareExchange64(&g_integer_original_calls,0,0));
    const unsigned long long float_calls=static_cast<unsigned long long>(
        InterlockedCompareExchange64(&g_float_original_calls,0,0));
    const unsigned long long observer_calls=static_cast<unsigned long long>(
        InterlockedCompareExchange64(&g_observer_calls,0,0));
    const unsigned long long direct_observer_calls=static_cast<unsigned long long>(
        InterlockedCompareExchange64(&g_direct_observer_calls,0,0));
    const unsigned long long wrapper_observer_calls=static_cast<unsigned long long>(
        InterlockedCompareExchange64(&g_wrapper_observer_calls,0,0));
    const unsigned long long wrapper_clone_callback_calls=
        static_cast<unsigned long long>(InterlockedCompareExchange64(
            &g_wrapper_clone_callback_calls,0,0));
    const unsigned long long wrapper_clone_original_calls=
        static_cast<unsigned long long>(InterlockedCompareExchange64(
            &g_wrapper_clone_original_calls,0,0));
    const unsigned long long wrapper_clone_bad=static_cast<unsigned long long>(
        InterlockedCompareExchange64(&g_wrapper_clone_bad,0,0));
    const unsigned long long wrapper_clone_return_ok=
        static_cast<unsigned long long>(InterlockedCompareExchange64(
            &g_wrapper_clone_return_ok,0,0));
    const unsigned long long bad_results=static_cast<unsigned long long>(
        InterlockedCompareExchange64(&g_bad_results,0,0));
    std::printf(
        "{\"passed\":%s,\"unwind_passed\":%s,\"unwind_points\":%u,"
        "\"unwind_lookup_failures\":%u,\"unwind_failures\":%u,"
        "\"direct_float_frame_passed\":%s,"
        "\"wrapper_clone_passed\":%s,"
        "\"wrapper_integer_passed\":%s,\"wrapper_float_passed\":%s,"
        "\"rounds\":%u,\"attempts\":%u,"
        "\"signature_invalid_published\":%s,\"bytes_restored\":%s,"
        "\"pending_zero\":%s,\"threads_joined\":%s,"
        "\"integer_original_calls\":%llu,\"float_original_calls\":%llu,"
        "\"observer_calls\":%llu,\"direct_observer_calls\":%llu,"
        "\"wrapper_observer_calls\":%llu,"
        "\"wrapper_clone_callback_calls\":%llu,"
        "\"wrapper_clone_original_calls\":%llu,"
        "\"wrapper_clone_bad\":%llu,"
        "\"wrapper_clone_return_ok\":%llu,\"bad_results\":%llu,"
        "\"last_apply_status\":%u,\"last_rollback_status\":%u,"
        "\"last_failure_stage\":%u}\n",
        report.passed?"true":"false",report.unwind_passed?"true":"false",
        report.unwind_points,report.unwind_lookup_failures,
        report.unwind_failures,report.direct_float_frame_passed?"true":"false",
        report.wrapper_clone_passed?"true":"false",
        report.wrapper_integer_passed?"true":"false",
        report.wrapper_float_passed?"true":"false",report.rounds,
        report.attempts,
        report.signature_invalid_published?"true":"false",
        report.bytes_restored?"true":"false",report.pending_zero?"true":"false",
        report.threads_joined?"true":"false",integer_calls,float_calls,
        observer_calls,direct_observer_calls,wrapper_observer_calls,
        wrapper_clone_callback_calls,wrapper_clone_original_calls,
        wrapper_clone_bad,wrapper_clone_return_ok,bad_results,
        report.last_apply_status,
        report.last_rollback_status,report.last_failure_stage);
    return report.passed?0:1;
}
