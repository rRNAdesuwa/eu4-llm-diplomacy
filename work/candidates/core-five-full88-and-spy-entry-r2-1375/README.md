# Static stack alias repair R2

Four original stack aliases are corrected from `rbp-0x81` to `rbp-0x89`.
The retained prologue bytes/annotations give `rbp = current_rsp + 0xb9`, hence
`current_rsp + 0x30 = rbp - 0x89`. Marriage's `rbp-0x49` is unchanged.
Saved field-store annotations are checked against all five objects' offsets,
including actor +10, target +20, dates, envoy, state, value and ID.

The original sealed report and independent FAIL are unchanged and pinned.
No PE is reopened, no instruction is newly disassembled, and no runtime,
constructor/deleting-destructor ownership or production status is promoted.
The original 16 tests are exact source copies; four new tests cover the repair.
