// Win64 function-entry shims use one recorded fixed stack allocation.
// Volatile GPR/XMM arguments and the caller stack are restored before tailjump.
// Arithmetic condition flags are volatile in the Win64 call ABI; these shims
// do not promise to preserve them. The native entry prologues set their own
// flags before any flag-dependent branch. DF is never modified.
.text
// Standalone assembly fixtures that reuse this shared unit do not define the
// family-specific Royal/Declare-War/Peace original slots. Keep these
// references weak; the production observer supplies the strong C++ definitions before
// installing either hook. A fixture never calls one of these shims when its
// weak slot is null.
.weak bridge_royal_field_reader_original
.weak bridge_declarewar_field_reader_original
.weak bridge_peace_field_reader_original
.globl bridge_transport_stub
.def bridge_transport_stub; .scl 2; .type 32; .endef
.seh_proc bridge_transport_stub
bridge_transport_stub:
    .seh_endprologue
    // 1580270 is void(this, wrapper); no stack or nonvolatile state changes.
    jmp bridge_transport_observe
.seh_endproc

.globl bridge_wrapper_load_stub
.def bridge_wrapper_load_stub; .scl 2; .type 32; .endef
.seh_proc bridge_wrapper_load_stub
bridge_wrapper_load_stub:
    .seh_endprologue
    // 17067e0 consumes only RCX/RDX. At the verified transport callsite,
    // R13 identifies the peer whose input queue receives the loaded wrapper.
    movq (%rsp), %r8
    movq %r13, %r9
    jmp bridge_wrapper_load_observe
.seh_endproc

.globl bridge_wrapper_clone_stub
.def bridge_wrapper_clone_stub; .scl 2; .type 32; .endef
.seh_proc bridge_wrapper_clone_stub
bridge_wrapper_clone_stub:
    .seh_endprologue
    // The original 4e8550 method does not consume R8/R9. This leaf shim
    // forwards its two original arguments plus the native caller context.
    movq (%rsp), %r8
    movq %rbp, %r9
    jmp bridge_wrapper_clone_observe
.seh_endproc

.globl bridge_rival_command_load_stub
.def bridge_rival_command_load_stub; .scl 2; .type 32; .endef
.seh_proc bridge_rival_command_load_stub
bridge_rival_command_load_stub:
    .seh_endprologue
    // Rival is a direct country-command.  Its +0x18 method has the same
    // observed two-argument body surface as the existing 17067e0 hook.  R8
    // carries the verified return address and R9 carries the peer from R13;
    // the callback invokes the exact original method once.
    movq (%rsp), %r8
    movq %r13, %r9
    jmp bridge_rival_command_load_observe
.seh_endproc

.globl bridge_rival_command_clone_stub
.def bridge_rival_command_clone_stub; .scl 2; .type 32; .endef
.seh_proc bridge_rival_command_clone_stub
bridge_rival_command_clone_stub:
    .seh_endprologue
    // Rival +0x60 is a direct command clone.  Preserve the existing receive
    // callsite proof convention: R8 is the return address after 15800c0 and
    // R9 is the receiver held in RBP at 15801e2.
    movq (%rsp), %r8
    movq %rbp, %r9
    jmp bridge_rival_command_clone_observe
.seh_endproc

.globl bridge_direct_break_stub
.def bridge_direct_break_stub; .scl 2; .type 32; .endef
.seh_proc bridge_direct_break_stub
bridge_direct_break_stub:
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
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
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_direct_break_original(%rip)
.seh_endproc

.globl bridge_field_reader_stub
.def bridge_field_reader_stub; .scl 2; .type 32; .endef
.seh_proc bridge_field_reader_stub
bridge_field_reader_stub:
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    movq 0xc8(%rsp), %r9
    call bridge_field_reader_observe
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_field_reader_original(%rip)
.seh_endproc

.globl bridge_royal_field_reader_stub
.def bridge_royal_field_reader_stub; .scl 2; .type 32; .endef
.seh_proc bridge_royal_field_reader_stub
bridge_royal_field_reader_stub:
    // Royal Marriage has a distinct native field-reader entry.  Preserve the
    // complete volatile Win64 argument/return surface exactly as the existing
    // field-reader shim does; the callback receives only a read-only prefix
    // and the original is tail-jumped without an ABI guess.
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    movq 0xc8(%rsp), %r9
    call bridge_field_reader_observe
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_royal_field_reader_original(%rip)
.seh_endproc

.globl bridge_declarewar_field_reader_stub
.def bridge_declarewar_field_reader_stub; .scl 2; .type 32; .endef
.seh_proc bridge_declarewar_field_reader_stub
bridge_declarewar_field_reader_stub:
    // Declare War has a distinct +0x20 field-reader entry. Preserve all
    // volatile arguments and tail-jump to its independently captured native
    // original after the shared read-only observer callback.
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    movq 0xc8(%rsp), %r9
    call bridge_field_reader_observe
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_declarewar_field_reader_original(%rip)
.seh_endproc

.globl bridge_peace_field_reader_stub
.def bridge_peace_field_reader_stub; .scl 2; .type 32; .endef
.seh_proc bridge_peace_field_reader_stub
bridge_peace_field_reader_stub:
    // Peace Offer has a distinct +0x20 field-reader entry. Preserve all
    // volatile arguments and tail-jump to its independently captured native
    // original after the shared read-only observer callback.
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    movq 0xc8(%rsp), %r9
    call bridge_field_reader_observe
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_peace_field_reader_original(%rip)
.seh_endproc

.globl bridge_wrapper_reader_stub
.def bridge_wrapper_reader_stub; .scl 2; .type 32; .endef
.seh_proc bridge_wrapper_reader_stub
bridge_wrapper_reader_stub:
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    movq 0xc8(%rsp), %r9
    call bridge_wrapper_reader_observe
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_wrapper_reader_original(%rip)
.seh_endproc

.globl bridge_frame_stub
.def bridge_frame_stub; .scl 2; .type 32; .endef
.seh_proc bridge_frame_stub
bridge_frame_stub:
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    call bridge_frame_tick
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_trampoline(%rip)
.seh_endproc

.globl bridge_serializer_stub
.def bridge_serializer_stub; .scl 2; .type 32; .endef
.seh_proc bridge_serializer_stub
bridge_serializer_stub:
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    call bridge_serializer_observe
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    jmp *bridge_serializer_original(%rip)
.seh_endproc

.globl bridge_response_stub
.def bridge_response_stub; .scl 2; .type 32; .endef
.seh_proc bridge_response_stub
bridge_response_stub:
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    // bridge_execution_execute owns the confirmed void(this) original call.
    // It returns only after the optional authority check and post-entry
    // observation; the original is therefore not tail-jumped a second time.
    call bridge_execution_execute
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    addq $0xc8, %rsp
    ret
.seh_endproc

.globl bridge_inbound_predicate_stub
.def bridge_inbound_predicate_stub; .scl 2; .type 32; .endef
.seh_proc bridge_inbound_predicate_stub
bridge_inbound_predicate_stub:
    // The patched E8 callsite enters here through an absolute relay.  The
    // caller's return address therefore remains at [rsp] and still points at
    // 4e81bd.  A fixed 0xc8 frame preserves every volatile register and six
    // XMM argument registers while keeping the Win64 call alignment: entry
    // RSP%16=8, after 0xc8 bytes RSP%16=0, and the nested C++ call sees 8.
    subq $0xc8, %rsp
    .seh_stackalloc 0xc8
    .seh_endprologue
    movq %rax, 0x80(%rsp)
    movq %rcx, 0x88(%rsp)
    movq %rdx, 0x90(%rsp)
    movq %r8, 0x98(%rsp)
    movq %r9, 0xa0(%rsp)
    movq %r10, 0xa8(%rsp)
    movq %r11, 0xb0(%rsp)
    movdqu %xmm0, 0x20(%rsp)
    movdqu %xmm1, 0x30(%rsp)
    movdqu %xmm2, 0x40(%rsp)
    movdqu %xmm3, 0x50(%rsp)
    movdqu %xmm4, 0x60(%rsp)
    movdqu %xmm5, 0x70(%rsp)
    movq 0xc8(%rsp), %rcx
    movq 0x98(%rsp), %rdx
    movq %rsi, %r8
    movq 0x88(%rsp), %r9
    call bridge_inbound_predicate_classify
    movb %al, 0x10(%rsp)
    movdqu 0x20(%rsp), %xmm0
    movdqu 0x30(%rsp), %xmm1
    movdqu 0x40(%rsp), %xmm2
    movdqu 0x50(%rsp), %xmm3
    movdqu 0x60(%rsp), %xmm4
    movdqu 0x70(%rsp), %xmm5
    movq 0xb0(%rsp), %r11
    movq 0xa8(%rsp), %r10
    movq 0xa0(%rsp), %r9
    movq 0x98(%rsp), %r8
    movq 0x90(%rsp), %rdx
    movq 0x88(%rsp), %rcx
    movq 0x80(%rsp), %rax
    cmpb $0, 0x10(%rsp)
    je .L_bridge_inbound_forward
    cmpb $2, 0x10(%rsp)
    je .L_bridge_inbound_hold
    movq bridge_inbound_pending_target(%rip), %rax
    movq %rax, 0xc8(%rsp)
    addq $0xc8, %rsp
    ret
.L_bridge_inbound_hold:
    # Return false to the original TEST AL / JZ at 4e81bd.  Its native
    # continuation skips AI clone/choice while retaining the common tail.
    xorl %eax, %eax
    addq $0xc8, %rsp
    ret
.L_bridge_inbound_forward:
    addq $0xc8, %rsp
    jmp *bridge_inbound_predicate_original(%rip)
.seh_endproc
