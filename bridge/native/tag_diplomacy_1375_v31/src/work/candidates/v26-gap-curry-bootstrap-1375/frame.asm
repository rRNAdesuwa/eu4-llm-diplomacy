; Original prologue's SUB overwrites arithmetic flags before any use.
; Both callback and replay trampoline have static Windows unwind metadata.
option casemap:none
EXTERN research_frame_tick:PROC
EXTERN research_trampoline:QWORD
EXTERN research_return:QWORD
.code
research_frame_stub PROC FRAME
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
    call research_frame_tick
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
    jmp QWORD PTR [research_trampoline]
research_frame_stub ENDP

research_original_trampoline PROC FRAME
    mov [rsp+18h], r8
    push rbp
    .pushreg rbp
    push rbx
    .pushreg rbx
    push rdi
    .pushreg rdi
    lea rbp, [rsp-50h]
    sub rsp, 150h
    .allocstack 150h
    .endprolog
    ; Register jump is deliberately not a tailcall epilogue: keep the frame.
    ; The original continuation immediately overwrites RDX with a RIP load.
    mov rdx, QWORD PTR [research_return]
    jmp rdx
research_original_trampoline ENDP
END
