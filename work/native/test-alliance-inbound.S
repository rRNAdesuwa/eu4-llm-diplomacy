.text

// A small parent-frame producer for the isolated unwind fixture.  The test
// copies this function's emitted unwind recipe into a dynamic table whose
// BeginAddress is before the synthetic trampoline body, matching the r21
// registration strategy without touching the game process.
.globl fixture_inbound_parent_frame
.def fixture_inbound_parent_frame; .scl 2; .type 32; .endef
.seh_proc fixture_inbound_parent_frame
fixture_inbound_parent_frame:
    pushq %rbx
    .seh_pushreg %rbx
    subq $0x20, %rsp
    .seh_stackalloc 0x20
    .seh_endprologue
    nop
    ret
.seh_endproc

// ABI probe for the four values forwarded by the native predicate hook.
// RSI is saved because it is nonvolatile in Win64; the value installed after
// the save is therefore visible to the classifier and restored to the C++
// caller when this fixture returns.  The common post-call label records AL
// before returning a fixed marker, so mode 2 proves that the original CALL
// return point ran with AL=0 while both target functions stayed untouched.
.globl fixture_inbound_classifier_caller
.def fixture_inbound_classifier_caller; .scl 2; .type 32; .endef
.seh_proc fixture_inbound_classifier_caller
fixture_inbound_classifier_caller:
    pushq %rsi
    .seh_pushreg %rsi
    subq $0x20, %rsp
    .seh_stackalloc 0x20
    .seh_endprologue
    leaq .L_fixture_inbound_classifier_return(%rip), %rax
    movq %rax, fixture_inbound_classifier_expected_return(%rip)
    movabs $0xa1a2a3a4a5a6a7a8, %r8
    movabs $0xb1b2b3b4b5b6b7b8, %rsi
    movabs $0xc1c2c3c4c5c6c7c8, %rcx
    call bridge_inbound_predicate_stub
.L_fixture_inbound_classifier_return:
    movb %al, fixture_inbound_classifier_seen_al(%rip)
    movq $1, fixture_inbound_classifier_returned(%rip)
    movabs $0xd1d2d3d4d5d6d7d8, %rax
    addq $0x20, %rsp
    popq %rsi
    ret
.seh_endproc

// Mode 1 enters this continuation with the classifier caller's frame still
// live.  It mirrors the native pending block: record the jump, unwind the
// caller's shadow space and saved RSI, then return to the caller of the
// fixture.  A normal C++ callee cannot be used here because the stub's RET
// has already consumed the call return address.
.globl fixture_inbound_classifier_pending
.def fixture_inbound_classifier_pending; .scl 2; .type 32; .endef
fixture_inbound_classifier_pending:
    lock incq fixture_inbound_classifier_pending_count(%rip)
    movabs $0xd1d2d3d4d5d6d7d8, %rax
    addq $0x20, %rsp
    popq %rsi
    ret

// Controlled-path continuation: the stub's RET changes the callsite return
// address to this label.  It records the still-live R8/RDX and the fifth
// stack argument before returning through the wrapper's own parent frame.
.globl fixture_inbound_controlled_caller
.def fixture_inbound_controlled_caller; .scl 2; .type 32; .endef
.seh_proc fixture_inbound_controlled_caller
fixture_inbound_controlled_caller:
    pushq %rbp
    .seh_pushreg %rbp
    subq $0x20, %rsp
    .seh_stackalloc 0x20
    .seh_endprologue
    call bridge_inbound_predicate_stub
.globl fixture_inbound_controlled_pending
.def fixture_inbound_controlled_pending; .scl 2; .type 32; .endef
fixture_inbound_controlled_pending:
    movq %rcx, fixture_inbound_seen_rcx(%rip)
    movq %rdx, fixture_inbound_seen_rdx(%rip)
    movq %r8, fixture_inbound_seen_r8(%rip)
    movq %r9, fixture_inbound_seen_r9(%rip)
    // The wrapper's fifth incoming argument is at +0x50 after its
    // push/sub/call frame (the stub itself has no fifth native argument).
    movq 0x50(%rsp), %rax
    movq %rax, fixture_inbound_seen_stack(%rip)
    lock incq fixture_inbound_pending_count(%rip)
    movabs $0x8877665544332211, %rax
    addq $0x20, %rsp
    popq %rbp
    ret
.seh_endproc
