.text

// The production direct-break pass-through lives in frame_stub.S.  This
// fixture adds a second copy only so two targets can be patched in one plan;
// each target has its own caller-owned original trampoline selector.
.globl bridge_direct_break_float_stub
.def bridge_direct_break_float_stub; .scl 2; .type 32; .endef
.seh_proc bridge_direct_break_float_stub
bridge_direct_break_float_stub:
    pushfq
    pushq %rax
    pushq %rcx
    pushq %rdx
    pushq %r8
    pushq %r9
    pushq %r10
    pushq %r11
    subq $0x88, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    movq 0xc8(%rsp), %r9
    call bridge_direct_break_observe
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    addq $0x88, %rsp
    popq %r11
    popq %r10
    popq %r9
    popq %r8
    popq %rdx
    popq %rcx
    popq %rax
    popfq
    jmp *bridge_direct_break_float_original(%rip)
.seh_endproc

// Synthetic caller for the real bridge_wrapper_clone_stub in frame_stub.S.
// The fixed RBP marker is visible to the shim as R9; the call return label is
// visible as R8.  The caller owns the shadow space and restores its incoming
// nonvolatile RBP before returning the original clone result in RAX.
.globl fixture_wrapper_clone_caller
.def fixture_wrapper_clone_caller; .scl 2; .type 32; .endef
.seh_proc fixture_wrapper_clone_caller
fixture_wrapper_clone_caller:
    pushq %rbp
    .seh_pushreg %rbp
    subq $0x20, %rsp
    .seh_stackalloc 0x20
    .seh_endprologue
    movabs $0x6a6b6c6d6e6f7071, %rbp
    call bridge_wrapper_clone_stub
.globl fixture_wrapper_clone_return_label
fixture_wrapper_clone_return_label:
    movabs $0x6a6b6c6d6e6f7071, %r11
    cmpq %r11, %rbp
    jne 1f
    movl $1, g_wrapper_clone_rbp_ok(%rip)
1:
    addq $0x20, %rsp
    popq %rbp
    ret
.seh_endproc

// Both synthetic targets start with the exact 15-byte register-home prefix
// used by the transaction fixture.  The caller-provided 29-byte trampoline
// copies these bytes and jumps to byte 15, which is the body tail below.
.globl fixture_integer_target
.def fixture_integer_target; .scl 2; .type 32; .endef
.seh_proc fixture_integer_target
fixture_integer_target:
    movq %rbx, 8(%rsp)
    movq %rbp, 16(%rsp)
    movq %rsi, 24(%rsp)
    .seh_endprologue
    jmp fixture_integer_body
.seh_endproc

.globl fixture_float_target
.def fixture_float_target; .scl 2; .type 32; .endef
.seh_proc fixture_float_target
fixture_float_target:
    movq %rbx, 8(%rsp)
    movq %rbp, 16(%rsp)
    movq %rsi, 24(%rsp)
    .seh_endprologue
    jmp fixture_float_body
.seh_endproc
