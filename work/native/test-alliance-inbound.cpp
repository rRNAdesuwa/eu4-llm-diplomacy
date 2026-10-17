#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>

extern "C" void bridge_inbound_predicate_stub();
extern "C" unsigned char bridge_inbound_predicate_classify(
    std::uintptr_t,std::uintptr_t,std::uintptr_t,std::uintptr_t);
extern "C" std::uint64_t fixture_inbound_controlled_caller(
    std::uint64_t,std::uint64_t,std::uint64_t,std::uint64_t,std::uint64_t);
extern "C" void fixture_inbound_controlled_pending();
extern "C" std::uint64_t fixture_inbound_classifier_caller();
extern "C" void fixture_inbound_classifier_pending();
extern "C" {
void* bridge_inbound_predicate_original=nullptr;
std::uintptr_t bridge_inbound_pending_target=0;
volatile LONG64 fixture_inbound_pending_count=0;
std::uint64_t fixture_inbound_seen_rcx=0;
std::uint64_t fixture_inbound_seen_rdx=0;
std::uint64_t fixture_inbound_seen_r8=0;
std::uint64_t fixture_inbound_seen_r9=0;
std::uint64_t fixture_inbound_seen_stack=0;
volatile std::uintptr_t fixture_inbound_classifier_expected_return=0;
volatile std::uintptr_t fixture_inbound_classifier_seen_return=0;
volatile std::uintptr_t fixture_inbound_classifier_seen_action=0;
volatile std::uintptr_t fixture_inbound_classifier_seen_command=0;
volatile std::uintptr_t fixture_inbound_classifier_seen_recipient=0;
volatile unsigned char fixture_inbound_classifier_seen_al=0;
volatile LONG64 fixture_inbound_classifier_returned=0;
volatile LONG64 fixture_inbound_classifier_pending_count=0;
}

// frame_stub.S is a shared assembly unit.  These inert definitions resolve
// its unrelated shims so the fixture can execute the actual inbound stub in
// a standalone process; no game object or DLL is loaded.
extern "C" {
void bridge_direct_break_observe(...) {}
void* bridge_direct_break_original=nullptr;
void bridge_execution_execute(...) {}
void bridge_field_reader_observe(...) {}
void* bridge_field_reader_original=nullptr;
void bridge_frame_tick(...) {}
void bridge_serializer_observe(...) {}
void* bridge_serializer_original=nullptr;
void bridge_transport_observe(...) {}
void bridge_wrapper_clone_observe(...) {}
void bridge_wrapper_load_observe(...) {}
void bridge_wrapper_reader_observe(...) {}
void* bridge_wrapper_reader_original=nullptr;
void* bridge_trampoline=nullptr;
}

static volatile LONG64 g_classifier_calls=0;
static volatile LONG64 g_original_calls=0;
static volatile LONG64 g_pending_calls=0;
static volatile LONG64 g_failures=0;
static volatile LONG g_mode=0;
static volatile std::uintptr_t g_expected_call_return=0;
static constexpr std::uintptr_t kClassifierAction=
    UINT64_C(0xa1a2a3a4a5a6a7a8);
static constexpr std::uintptr_t kClassifierCommand=
    UINT64_C(0xb1b2b3b4b5b6b7b8);
static constexpr std::uintptr_t kClassifierRecipient=
    UINT64_C(0xc1c2c3c4c5c6c7c8);
static std::uint64_t g_seen_int[5]{};
static double g_seen_fp[4]{};

static void fail(const char* label) {
    InterlockedIncrement64(&g_failures);
    std::printf("FAIL %s\n",label);
}

static void check(bool condition,const char* label) {
    if (!condition) fail(label);
}

extern "C" unsigned char bridge_inbound_predicate_classify(
    std::uintptr_t caller_return,
    std::uintptr_t action_from_native_r8,
    std::uintptr_t command_from_native_rsi,
    std::uintptr_t recipient_country_from_native_rcx) {
    const std::uintptr_t expected=g_expected_call_return;
    const std::uintptr_t classifier_expected=
        fixture_inbound_classifier_expected_return;
    if (expected && caller_return!=expected)
        InterlockedIncrement64(&g_failures);
    if (classifier_expected && caller_return!=classifier_expected)
        InterlockedIncrement64(&g_failures);
    fixture_inbound_classifier_seen_return=caller_return;
    fixture_inbound_classifier_seen_action=action_from_native_r8;
    fixture_inbound_classifier_seen_command=command_from_native_rsi;
    fixture_inbound_classifier_seen_recipient=recipient_country_from_native_rcx;
    InterlockedIncrement64(&g_classifier_calls);
    return static_cast<unsigned char>(InterlockedCompareExchange(&g_mode,0,0));
}

extern "C" std::uint64_t fixture_classifier_original() {
    InterlockedIncrement64(&g_original_calls);
    return UINT64_C(0x1111222233334445);
}

extern "C" std::uint64_t fixture_original_int(std::uint64_t a,
    std::uint64_t b,std::uint64_t c,std::uint64_t d,std::uint64_t e) {
    InterlockedIncrement64(&g_original_calls);
    g_seen_int[0]=a; g_seen_int[1]=b; g_seen_int[2]=c;
    g_seen_int[3]=d; g_seen_int[4]=e;
    return UINT64_C(0x1122334455667788);
}

extern "C" std::uint64_t fixture_pending_int(std::uint64_t a,
    std::uint64_t b,std::uint64_t c,std::uint64_t d,std::uint64_t e) {
    InterlockedIncrement64(&g_pending_calls);
    g_seen_int[0]=a; g_seen_int[1]=b; g_seen_int[2]=c;
    g_seen_int[3]=d; g_seen_int[4]=e;
    return UINT64_C(0x8877665544332211);
}

extern "C" double fixture_original_fp(double a,double b,double c,double d) {
    InterlockedIncrement64(&g_original_calls);
    g_seen_fp[0]=a; g_seen_fp[1]=b; g_seen_fp[2]=c; g_seen_fp[3]=d;
    return 42.25;
}

extern "C" double fixture_pending_fp(double a,double b,double c,double d) {
    InterlockedIncrement64(&g_pending_calls);
    g_seen_fp[0]=a; g_seen_fp[1]=b; g_seen_fp[2]=c; g_seen_fp[3]=d;
    return 24.5;
}

using IntCall=std::uint64_t (*)(std::uint64_t,std::uint64_t,
    std::uint64_t,std::uint64_t,std::uint64_t);
using FpCall=double (*)(double,double,double,double);

static void reset_counters() {
    InterlockedExchange64(&g_classifier_calls,0);
    InterlockedExchange64(&g_original_calls,0);
    InterlockedExchange64(&g_pending_calls,0);
    fixture_inbound_classifier_expected_return=0;
    fixture_inbound_classifier_seen_return=0;
    fixture_inbound_classifier_seen_action=0;
    fixture_inbound_classifier_seen_command=0;
    fixture_inbound_classifier_seen_recipient=0;
    fixture_inbound_classifier_seen_al=0;
    InterlockedExchange64(&fixture_inbound_classifier_returned,0);
    InterlockedExchange64(&fixture_inbound_classifier_pending_count,0);
    std::memset(g_seen_int,0,sizeof(g_seen_int));
    std::memset(g_seen_fp,0,sizeof(g_seen_fp));
}

static void test_classifier_abi() {
    reset_counters();
    InterlockedExchange(&g_mode,0);
    bridge_inbound_predicate_original=
        reinterpret_cast<void*>(&fixture_classifier_original);
    bridge_inbound_pending_target=
        reinterpret_cast<std::uintptr_t>(&fixture_inbound_classifier_pending);
    const std::uint64_t forward_result=fixture_inbound_classifier_caller();
    check(forward_result==UINT64_C(0xd1d2d3d4d5d6d7d8),
        "classifier ABI forward return");
    check(g_classifier_calls==1 && g_original_calls==1
        && g_pending_calls==0,"classifier ABI forward calls");
    check(fixture_inbound_classifier_seen_action==kClassifierAction
        && fixture_inbound_classifier_seen_command==kClassifierCommand
        && fixture_inbound_classifier_seen_recipient==kClassifierRecipient,
        "classifier ABI four arguments");
    check(fixture_inbound_classifier_seen_return!=0
        && fixture_inbound_classifier_returned==1,
        "classifier ABI forward return point");

    reset_counters();
    InterlockedExchange(&g_mode,1);
    bridge_inbound_predicate_original=
        reinterpret_cast<void*>(&fixture_classifier_original);
    bridge_inbound_pending_target=
        reinterpret_cast<std::uintptr_t>(&fixture_inbound_classifier_pending);
    const std::uint64_t pending_result=fixture_inbound_classifier_caller();
    check(pending_result==UINT64_C(0xd1d2d3d4d5d6d7d8),
        "classifier ABI pending return");
    check(g_classifier_calls==1 && g_original_calls==0
        && g_pending_calls==0 && fixture_inbound_classifier_pending_count==1,
        "classifier ABI pending calls");
    check(fixture_inbound_classifier_seen_action==kClassifierAction
        && fixture_inbound_classifier_seen_command==kClassifierCommand
        && fixture_inbound_classifier_seen_recipient==kClassifierRecipient,
        "classifier ABI pending arguments");

    reset_counters();
    InterlockedExchange(&g_mode,2);
    bridge_inbound_predicate_original=
        reinterpret_cast<void*>(&fixture_classifier_original);
    bridge_inbound_pending_target=
        reinterpret_cast<std::uintptr_t>(&fixture_inbound_classifier_pending);
    const std::uint64_t hold_result=fixture_inbound_classifier_caller();
    check(hold_result==UINT64_C(0xd1d2d3d4d5d6d7d8),
        "classifier ABI hold return point");
    check(g_classifier_calls==1 && g_original_calls==0
        && g_pending_calls==0,"classifier ABI hold skips targets");
    check(fixture_inbound_classifier_returned==1
        && fixture_inbound_classifier_seen_al==0,
        "classifier ABI hold returns AL zero");
    check(fixture_inbound_classifier_seen_action==kClassifierAction
        && fixture_inbound_classifier_seen_command==kClassifierCommand
        && fixture_inbound_classifier_seen_recipient==kClassifierRecipient,
        "classifier ABI hold arguments");
}

static void test_noncontrolled_int() {
    reset_counters();
    InterlockedExchange(&g_mode,0);
    bridge_inbound_predicate_original=
        reinterpret_cast<void*>(&fixture_original_int);
    bridge_inbound_pending_target=
        reinterpret_cast<std::uintptr_t>(&fixture_pending_int);
    const IntCall stub=reinterpret_cast<IntCall>(&bridge_inbound_predicate_stub);
    const std::uint64_t result=stub(UINT64_C(0x101),UINT64_C(0x202),
        UINT64_C(0x303),UINT64_C(0x404),UINT64_C(0x505));
    check(result==UINT64_C(0x1122334455667788),"noncontrolled result");
    check(g_classifier_calls==1,"noncontrolled classifier once");
    check(g_original_calls==1,"noncontrolled original once");
    check(g_pending_calls==0,"noncontrolled no pending jump");
    check(g_seen_int[0]==UINT64_C(0x101) && g_seen_int[1]==UINT64_C(0x202)
        && g_seen_int[2]==UINT64_C(0x303) && g_seen_int[3]==UINT64_C(0x404)
        && g_seen_int[4]==UINT64_C(0x505),"noncontrolled args");
}

static void test_controlled_int() {
    reset_counters();
    InterlockedExchange(&g_mode,1);
    bridge_inbound_predicate_original=
        reinterpret_cast<void*>(&fixture_original_int);
    bridge_inbound_pending_target=
        reinterpret_cast<std::uintptr_t>(&fixture_inbound_controlled_pending);
    InterlockedExchange64(&fixture_inbound_pending_count,0);
    const std::uint64_t result=fixture_inbound_controlled_caller(
        UINT64_C(0x606),UINT64_C(0x707),
        UINT64_C(0x808),UINT64_C(0x909),UINT64_C(0xa0a));
    check(result==UINT64_C(0x8877665544332211),"controlled result");
    check(g_classifier_calls==1,"controlled classifier once");
    check(g_original_calls==0,"controlled skips predicate");
    check(fixture_inbound_pending_count==1,"controlled pending once");
    check(fixture_inbound_seen_rcx==UINT64_C(0x606)
        && fixture_inbound_seen_rdx==UINT64_C(0x707)
        && fixture_inbound_seen_r8==UINT64_C(0x808)
        && fixture_inbound_seen_r9==UINT64_C(0x909)
        && fixture_inbound_seen_stack==UINT64_C(0xa0a),
        "controlled args and stack");
}

static void test_xmm_restore() {
    reset_counters();
    InterlockedExchange(&g_mode,0);
    bridge_inbound_predicate_original=
        reinterpret_cast<void*>(&fixture_original_fp);
    const FpCall stub=reinterpret_cast<FpCall>(&bridge_inbound_predicate_stub);
    const double result=stub(1.25,2.5,3.75,5.0);
    check(result==42.25,"xmm noncontrolled result");
    check(g_classifier_calls==1 && g_original_calls==1,
        "xmm noncontrolled calls");
    check(g_seen_fp[0]==1.25 && g_seen_fp[1]==2.5
        && g_seen_fp[2]==3.75 && g_seen_fp[3]==5.0,"xmm args");
}

static void fixture_write_absolute_jump(unsigned char* destination,
    std::uintptr_t target) {
    destination[0]=0xff;
    destination[1]=0x25;
    std::memset(destination+2,0,4);
    std::memcpy(destination+6,&target,sizeof(target));
}

static bool fixture_write_call(unsigned char* callsite,
    unsigned char* relay) {
    const std::int64_t difference=static_cast<std::int64_t>(
        reinterpret_cast<std::uintptr_t>(relay))-
        static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(callsite+5));
    if (difference<std::numeric_limits<std::int32_t>::min()
        || difference>std::numeric_limits<std::int32_t>::max()) return false;
    callsite[0]=0xe8;
    const auto displacement=static_cast<std::int32_t>(difference);
    std::memcpy(callsite+1,&displacement,sizeof(displacement));
    return true;
}

static void fixture_write_load_rax(unsigned char* destination,
    std::uintptr_t value) {
    destination[0]=0x48; destination[1]=0xb8;
    std::memcpy(destination+2,&value,sizeof(value));
}

static void test_patched_callsite() {
    reset_counters();
    auto block=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1000,
        MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    check(block!=nullptr,"patched-call allocation");
    if (!block) return;
    unsigned char* callsite=block;
    unsigned char* relay=block+0x80;
    unsigned char* pending=block+0x40;
    fixture_write_absolute_jump(relay,
        reinterpret_cast<std::uintptr_t>(&bridge_inbound_predicate_stub));
    // Reserve the Win64 shadow space before the synthetic E8 relay call.
    // Without this reservation the original callee's argument home slots
    // overlap the outer caller's return address.
    callsite[0]=0x48; callsite[1]=0x83; callsite[2]=0xec; callsite[3]=0x20;
    check(fixture_write_call(callsite+4,relay),"patched-call rel32");
    callsite[9]=0x48; callsite[10]=0x83; callsite[11]=0xc4; callsite[12]=0x20;
    // The native continuation tests AL and branches around the AI choice.
    // Nonzero AL from either the original or pending path selects marker A;
    // mode 2 returns AL=0 and selects marker B through TEST/JZ.
    callsite[13]=0x84; callsite[14]=0xc0; // test %al,%al
    callsite[15]=0x74; callsite[16]=0x0b; // jz +0x0b to +28
    fixture_write_load_rax(callsite+17,UINT64_C(0xaaaaaaaaaaaaaaaa));
    callsite[27]=0xc3;
    fixture_write_load_rax(callsite+28,UINT64_C(0xbbbbbbbbbbbbbbbb));
    callsite[38]=0xc3;
    // Controlled return path: the stub rewrites the callsite return address
    // to this continuation, which increments a private counter and returns a
    // different marker.  It is deliberately a continuation, not a function
    // entered by CALL, so the stack shape matches the native pending block.
    fixture_write_load_rax(pending,
        reinterpret_cast<std::uintptr_t>(&fixture_inbound_pending_count));
    pending[10]=0x48; pending[11]=0xff; pending[12]=0x00;
    fixture_write_load_rax(pending+13,UINT64_C(0xcccccccccccccccc));
    pending[23]=0x48; pending[24]=0x83; pending[25]=0xc4; pending[26]=0x20;
    pending[27]=0xc3;
    DWORD old_protection=0;
    check(VirtualProtect(block,0x1000,PAGE_EXECUTE_READ,&old_protection)!=FALSE,
        "patched-call protection");
    FlushInstructionCache(GetCurrentProcess(),block,0x1000);
    check(callsite[4]==0xe8,"patched-call opcode is CALL");
    g_expected_call_return=reinterpret_cast<std::uintptr_t>(callsite+9);
    InterlockedExchange64(&fixture_inbound_pending_count,0);
    bridge_inbound_predicate_original=
        reinterpret_cast<void*>(&fixture_original_int);
    bridge_inbound_pending_target=reinterpret_cast<std::uintptr_t>(pending);
    const IntCall patched=reinterpret_cast<IntCall>(callsite);
    InterlockedExchange(&g_mode,0);
    const std::uint64_t native_result=patched(UINT64_C(0x111),
        UINT64_C(0x222),UINT64_C(0x333),UINT64_C(0x444),UINT64_C(0x555));
    check(native_result==UINT64_C(0xaaaaaaaaaaaaaaaa),
        "patched noncontrolled return");
    check(g_classifier_calls==1 && g_original_calls==1
        && fixture_inbound_pending_count==0,
        "patched noncontrolled branch");
    reset_counters();
    InterlockedExchange64(&fixture_inbound_pending_count,0);
    InterlockedExchange(&g_mode,1);
    const std::uint64_t pending_result=patched(UINT64_C(0x666),
        UINT64_C(0x777),UINT64_C(0x888),UINT64_C(0x999),UINT64_C(0xaaa));
    check(pending_result==UINT64_C(0xcccccccccccccccc),
        "patched controlled return");
    check(g_classifier_calls==1 && g_original_calls==0
        && fixture_inbound_pending_count==1,
        "patched controlled branch");
    reset_counters();
    InterlockedExchange64(&fixture_inbound_pending_count,0);
    InterlockedExchange(&g_mode,2);
    const std::uint64_t hold_result=patched(UINT64_C(0x6a6),
        UINT64_C(0x7b7),UINT64_C(0x8c8),UINT64_C(0x9d9),UINT64_C(0xae0));
    check(hold_result==UINT64_C(0xbbbbbbbbbbbbbbbb),
        "patched hold TEST/JZ return");
    check(g_classifier_calls==1 && g_original_calls==0
        && fixture_inbound_pending_count==0,
        "patched hold skips predicate and pending");
    g_expected_call_return=0;
    VirtualFree(block,0,MEM_RELEASE);
}

extern "C" void fixture_inbound_parent_frame();

static void test_dynamic_unwind() {
    DWORD64 image_base=0;
    PRUNTIME_FUNCTION parent=RtlLookupFunctionEntry(
        reinterpret_cast<DWORD64>(&fixture_inbound_parent_frame),
        &image_base,nullptr);
    check(parent!=nullptr,"parent unwind lookup");
    if (!parent) return;

    auto block=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1000,
        MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    auto stack=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1000,
        MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    check(block!=nullptr && stack!=nullptr,"unwind fixture allocation");
    if (!block || !stack) {
        if (block) VirtualFree(block,0,MEM_RELEASE);
        if (stack) VirtualFree(stack,0,MEM_RELEASE);
        return;
    }
    const auto parent_unwind=reinterpret_cast<const void*>(
        image_base+parent->UnwindData);
    std::memcpy(block+0x40,parent_unwind,64);
    RUNTIME_FUNCTION dynamic{0x100,0x120,0x40};
    check(RtlAddFunctionTable(&dynamic,1,
        reinterpret_cast<DWORD64>(block))!=FALSE,"dynamic unwind register");

    unsigned char* current=stack+0x100;
    const DWORD64 saved_rbx=UINT64_C(0xfeedfacecafebeef);
    const DWORD64 return_address=UINT64_C(0x123456789abcdef0);
    std::memcpy(current+0x20,&saved_rbx,sizeof(saved_rbx));
    std::memcpy(current+0x28,&return_address,sizeof(return_address));
    CONTEXT context{};
    context.ContextFlags=CONTEXT_CONTROL|CONTEXT_INTEGER;
    context.Rip=reinterpret_cast<DWORD64>(block+0x110);
    context.Rsp=reinterpret_cast<DWORD64>(current);
    context.Rbx=UINT64_C(0x1111111111111111);
    PVOID handler_data=nullptr;
    DWORD64 establisher=0;
    KNONVOLATILE_CONTEXT_POINTERS nonvolatile{};
    (void)RtlVirtualUnwind(UNW_FLAG_NHANDLER,
        reinterpret_cast<DWORD64>(block),context.Rip,&dynamic,&context,
        &handler_data,&establisher,&nonvolatile);
    if (context.Rsp!=reinterpret_cast<DWORD64>(current+0x30)) {
        std::printf("unwind rsp delta=%llx expected=%llx\n",
            static_cast<unsigned long long>(context.Rsp-
                reinterpret_cast<DWORD64>(current)),
            static_cast<unsigned long long>(0x30));
    }
    check(context.Rip==return_address,"trampoline parent return address");
    check(context.Rsp==reinterpret_cast<DWORD64>(current+0x30),
        "trampoline parent stack");
    check(context.Rbx==saved_rbx,"trampoline parent nonvolatile");
    RtlDeleteFunctionTable(&dynamic);
    VirtualFree(stack,0,MEM_RELEASE);
    VirtualFree(block,0,MEM_RELEASE);
}

int main() {
    test_classifier_abi();
    test_noncontrolled_int();
    test_controlled_int();
    test_xmm_restore();
    test_patched_callsite();
    test_dynamic_unwind();
    if (g_failures) {
        std::printf("alliance-inbound fixture FAILED count=%lld\n",
            static_cast<long long>(g_failures));
        return 1;
    }
    std::puts("alliance-inbound fixture PASS: classifier-abi, noncontrolled, controlled, hold, xmm, unwind");
    return 0;
}
