; Standalone offline EXE model only. No installer/replay/continuation pointer.
option casemap:none
EXTERN model_capture_impl:PROC
EXTERN model_outer_root:QWORD
EXTERN model_map:QWORD
EXTERN model_server:QWORD
EXTERN model_mode:DWORD
EXTERN model_callback_entry_rsp:QWORD
EXTERN model_after_rsp:QWORD
EXTERN model_after_gprs:BYTE
EXTERN model_after_xmm:OWORD
EXTERN model_before_nonvolatile:BYTE
EXTERN model_after_nonvolatile:BYTE
EXTERN model_before_nonvolatile_xmm:OWORD
EXTERN model_after_nonvolatile_xmm:OWORD
EXTERN model_xmm_patterns:OWORD
EXTERN model_clobber_count:DWORD
PUBLIC model_run, model_adapter, model_jump_thunk
PUBLIC model_return_to_wrapper_call, model_return_to_wrapper_jump
PUBLIC model_return_to_server, model_return_to_relay
PUBLIC model_return_to_loop, model_return_to_main
.code

model_adapter PROC FRAME
    sub rsp, 0e8h
    .allocstack 0e8h
    .endprolog
    mov [rsp+20h], rax
    mov [rsp+28h], rcx
    mov [rsp+30h], rdx
    mov [rsp+38h], r8
    mov [rsp+40h], r9
    mov [rsp+48h], r10
    mov [rsp+50h], r11
    movdqu [rsp+60h], xmm0
    movdqu [rsp+70h], xmm1
    movdqu [rsp+80h], xmm2
    movdqu [rsp+90h], xmm3
    movdqu [rsp+0a0h], xmm4
    movdqu [rsp+0b0h], xmm5
    lea rax, [rsp+0e8h]
    mov [rsp+0c0h], rax
    mov rax, [rsp+28h]
    mov [rsp+0c8h], rax
    mov rax, [rsp+38h]
    mov [rsp+0d0h], rax
    mov [rsp+0d8h], rsp
    lea rcx, [rsp+0c0h]
    call model_capture_entry
    movdqu xmm0, [rsp+60h]
    movdqu xmm1, [rsp+70h]
    movdqu xmm2, [rsp+80h]
    movdqu xmm3, [rsp+90h]
    movdqu xmm4, [rsp+0a0h]
    movdqu xmm5, [rsp+0b0h]
    mov rax, [rsp+20h]
    mov rcx, [rsp+28h]
    mov rdx, [rsp+30h]
    mov r8, [rsp+38h]
    mov r9, [rsp+40h]
    mov r10, [rsp+48h]
    mov r11, [rsp+50h]
    add rsp, 0e8h
    ret
model_adapter ENDP

model_capture_entry PROC FRAME
    ; Numeric diagnostic only: no pointer is retained for later dereference.
    mov model_callback_entry_rsp, rsp
    mov rax, 0a1a1a1a1a1a1a1a1h
    mov [rsp+8], rax
    mov [rsp+10h], rax
    mov [rsp+18h], rax
    mov [rsp+20h], rax
    sub rsp, 28h
    .allocstack 28h
    .endprolog
    call model_capture_impl
    call model_clobber_volatiles
    add rsp, 28h
    ret
model_capture_entry ENDP

model_clobber_volatiles PROC
    inc model_clobber_count
    mov rax, 0eeeeeeeeeeeeeeeeh
    mov rcx, rax
    mov rdx, rax
    mov r8, rax
    mov r9, rax
    mov r10, rax
    mov r11, rax
    pxor xmm0, xmm0
    pxor xmm1, xmm1
    pxor xmm2, xmm2
    pxor xmm3, xmm3
    pxor xmm4, xmm4
    pxor xmm5, xmm5
    ret
model_clobber_volatiles ENDP

model_jump_thunk PROC
    jmp model_adapter
model_jump_thunk ENDP

model_wrapper PROC FRAME
    sub rsp, 38h
    .allocstack 38h
    .endprolog
    mov QWORD PTR model_before_nonvolatile[0], rbx
    mov QWORD PTR model_before_nonvolatile[8], rbp
    mov QWORD PTR model_before_nonvolatile[16], rsi
    mov QWORD PTR model_before_nonvolatile[24], rdi
    mov QWORD PTR model_before_nonvolatile[32], r12
    mov QWORD PTR model_before_nonvolatile[40], r13
    mov QWORD PTR model_before_nonvolatile[48], r14
    mov QWORD PTR model_before_nonvolatile[56], r15
    movdqu model_before_nonvolatile_xmm[0], xmm6
    movdqu model_before_nonvolatile_xmm[16], xmm7
    movdqu model_before_nonvolatile_xmm[32], xmm8
    movdqu model_before_nonvolatile_xmm[48], xmm9
    movdqu model_before_nonvolatile_xmm[64], xmm10
    movdqu model_before_nonvolatile_xmm[80], xmm11
    movdqu model_before_nonvolatile_xmm[96], xmm12
    movdqu model_before_nonvolatile_xmm[112], xmm13
    movdqu model_before_nonvolatile_xmm[128], xmm14
    movdqu model_before_nonvolatile_xmm[144], xmm15
    mov rax, 01111111111111111h
    mov rcx, model_map
    mov rdx, 02222222222222222h
    mov r8, model_server
    mov r9, 04444444444444444h
    mov r10, 05555555555555555h
    mov r11, 06666666666666666h
    movdqu xmm0, model_xmm_patterns[0]
    movdqu xmm1, model_xmm_patterns[16]
    movdqu xmm2, model_xmm_patterns[32]
    movdqu xmm3, model_xmm_patterns[48]
    movdqu xmm4, model_xmm_patterns[64]
    movdqu xmm5, model_xmm_patterns[80]
    cmp model_mode, 0
    jne wrapper_jump
    call model_adapter
model_return_to_wrapper_call LABEL BYTE
    jmp wrapper_after
wrapper_jump:
    call model_jump_thunk
model_return_to_wrapper_jump LABEL BYTE
wrapper_after:
    mov QWORD PTR model_after_gprs[0], rax
    mov QWORD PTR model_after_gprs[8], rcx
    mov QWORD PTR model_after_gprs[16], rdx
    mov QWORD PTR model_after_gprs[24], r8
    mov QWORD PTR model_after_gprs[32], r9
    mov QWORD PTR model_after_gprs[40], r10
    mov QWORD PTR model_after_gprs[48], r11
    movdqu model_after_xmm[0], xmm0
    movdqu model_after_xmm[16], xmm1
    movdqu model_after_xmm[32], xmm2
    movdqu model_after_xmm[48], xmm3
    movdqu model_after_xmm[64], xmm4
    movdqu model_after_xmm[80], xmm5
    mov model_after_rsp, rsp
    mov QWORD PTR model_after_nonvolatile[0], rbx
    mov QWORD PTR model_after_nonvolatile[8], rbp
    mov QWORD PTR model_after_nonvolatile[16], rsi
    mov QWORD PTR model_after_nonvolatile[24], rdi
    mov QWORD PTR model_after_nonvolatile[32], r12
    mov QWORD PTR model_after_nonvolatile[40], r13
    mov QWORD PTR model_after_nonvolatile[48], r14
    mov QWORD PTR model_after_nonvolatile[56], r15
    movdqu model_after_nonvolatile_xmm[0], xmm6
    movdqu model_after_nonvolatile_xmm[16], xmm7
    movdqu model_after_nonvolatile_xmm[32], xmm8
    movdqu model_after_nonvolatile_xmm[48], xmm9
    movdqu model_after_nonvolatile_xmm[64], xmm10
    movdqu model_after_nonvolatile_xmm[80], xmm11
    movdqu model_after_nonvolatile_xmm[96], xmm12
    movdqu model_after_nonvolatile_xmm[112], xmm13
    movdqu model_after_nonvolatile_xmm[128], xmm14
    movdqu model_after_nonvolatile_xmm[144], xmm15
    add rsp, 38h
    ret
model_wrapper ENDP

model_server_frame PROC FRAME
    sub rsp, 328h
    .allocstack 328h
    .endprolog
    call model_wrapper
model_return_to_server LABEL BYTE
    add rsp, 328h
    ret
model_server_frame ENDP

model_relay PROC FRAME
    sub rsp, 78h
    .allocstack 78h
    .endprolog
    call model_server_frame
model_return_to_relay LABEL BYTE
    add rsp, 78h
    ret
model_relay ENDP

model_loop PROC FRAME
    sub rsp, 48h
    .allocstack 48h
    .endprolog
    call model_relay
model_return_to_loop LABEL BYTE
    add rsp, 48h
    ret
model_loop ENDP

model_run PROC FRAME
    sub rsp, 88h
    .allocstack 88h
    .endprolog
    mov rax, model_outer_root
    mov [rsp+60h], rax
    call model_loop
model_return_to_main LABEL BYTE
    add rsp, 88h
    ret
model_run ENDP
END
