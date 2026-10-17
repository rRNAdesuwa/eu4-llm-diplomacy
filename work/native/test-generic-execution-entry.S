.text

// The fixture's target has the same first 18 bytes as the native executor
// entry being guarded.  The bytes are written explicitly so the test can
// prove that the trampoline copies the complete prologue before execution.
.globl generic_entry_original
.def generic_entry_original; .scl 2; .type 32; .endef
.seh_proc generic_entry_original
generic_entry_original:
    .byte 0x48,0x89,0x5c,0x24,0x18       // mov [rsp+18h],rbx
    .byte 0x48,0x89,0x6c,0x24,0x20       // mov [rsp+20h],rbp
    .byte 0x56                              // push rsi
    .byte 0x57                              // push rdi
    .byte 0x41,0x56                         // push r14
    .byte 0x48,0x83,0xec,0x20               // sub rsp,20h
    .seh_endprologue
    call generic_entry_body
    addq $0x20, %rsp
    popq %r14
    popq %rdi
    popq %rsi
    movq 0x20(%rsp), %rbp
    movq 0x18(%rsp), %rbx
    ret
.seh_endproc

// The patched entry reaches this common guard for both a direct call and a
// virtual-table call.  The gate has no arguments, so the only state it may
// change before the original is the volatile return register.  An allowed
// call tail-jumps to the copied prologue; a blocked call returns a sentinel
// without entering the original body.
.globl generic_bridge_response_stub
.def generic_bridge_response_stub; .scl 2; .type 32; .endef
.seh_proc generic_bridge_response_stub
generic_bridge_response_stub:
    subq $0x28, %rsp
    .seh_stackalloc 0x28
    .seh_endprologue
    call generic_entry_gate
    testl %eax, %eax
    jz 1f
    addq $0x28, %rsp
    jmp *generic_entry_trampoline(%rip)
1:
    addq $0x28, %rsp
    movl $0x5a5a, %eax
    ret
.seh_endproc

// Each checked caller saves the incoming nonvolatile registers, installs
// markers, invokes the selected call path, returns the target result in the
// low 16 bits, and returns a five-bit preservation mask in the high 16 bits.
// The wrappers are deliberately separate so one path is a direct CALL to the
// entry symbol and the other path is an indirect virtual-table CALL.
.globl generic_call_direct_checked
.def generic_call_direct_checked; .scl 2; .type 32; .endef
generic_call_direct_checked:
    pushq %r15
    pushq %r14
    pushq %rdi
    pushq %rsi
    pushq %rbp
    pushq %rbx
    subq $0x28, %rsp
    movabs $0x1122334455667788, %rbx
    movabs $0x1122334455667788, %rbp
    movabs $0x1122334455667788, %rsi
    movabs $0x1122334455667788, %rdi
    movabs $0x1122334455667788, %r14
    call generic_entry_original
    jmp generic_checked_finish

.globl generic_call_virtual_checked
.def generic_call_virtual_checked; .scl 2; .type 32; .endef
generic_call_virtual_checked:
    pushq %r15
    pushq %r14
    pushq %rdi
    pushq %rsi
    pushq %rbp
    pushq %rbx
    subq $0x28, %rsp
    movabs $0x1122334455667788, %rbx
    movabs $0x1122334455667788, %rbp
    movabs $0x1122334455667788, %rsi
    movabs $0x1122334455667788, %rdi
    movabs $0x1122334455667788, %r14
    movq generic_vtable_slot(%rip), %rax
    call *%rax

generic_checked_finish:
    movl %eax, 0x24(%rsp)
    xorl %r11d, %r11d
    movabs $0x1122334455667788, %rax
    cmpq %rax, %rbx
    jne 2f
    orl $0x01, %r11d
2:
    cmpq %rax, %rbp
    jne 3f
    orl $0x02, %r11d
3:
    cmpq %rax, %rsi
    jne 4f
    orl $0x04, %r11d
4:
    cmpq %rax, %rdi
    jne 5f
    orl $0x08, %r11d
5:
    cmpq %rax, %r14
    jne 6f
    orl $0x10, %r11d
6:
    movl 0x24(%rsp), %eax
    andl $0xffff, %eax
    shll $16, %r11d
    orl %r11d, %eax
    addq $0x28, %rsp
    popq %rbx
    popq %rbp
    popq %rsi
    popq %rdi
    popq %r14
    popq %r15
    ret
