# R86 selected cc220 machine fragment

The exact selected pdata interval is [0xcc220,0xcc266), 70 owned/decoded bytes in twenty contiguous rows. It is not a closed helper: JE at cc259 goes to cc32c, and the unequal path falls through cc266. No CALL or RET is present.

The fragment saves four registers by PUSH (32 bytes of implicit stack writes), reserves another 0x28 bytes, and reads two QWORDs through incoming RCX. It subtracts the loaded base from incoming RDX and from the other loaded value, arithmetic-shifts both differences by three, saves incoming R8 in R13, and compares the latter result with 0x1fffffffffffffff. The unequal path reads RCX+0x10, subtracts the same base, and leaves the owned interval. These are opaque machine values; they do not recover a C++ class, allocator contract, return value, ownership transfer or successful append.

The capture records 19 pdata reads/228 bytes (16 unique/192 bytes), one 70-byte code read, and two full EXE SHA streams totaling 76,925,008 bytes: PE total 76,925,306. Decoder lookahead input278/union70/overlap208 is a separate layer. Its completed explicit source journal is148 events/16,772,282 bytes; engine file hashes are producer witness only for this retained stage, and no engine body was reopened here.

Root's execution tool record c2313d reports exit0/1.217s with no live session. Original stdout/stderr were not separately retained, so root-execution-witness.json is explicitly a conversation/tool-record summary, not manufactured raw logs or independent OS observation. Normal target-context exit and publication after postguards are producer fields supported by the frozen producer source ordering.

No producer, decoder, PE, game process or native operation ran in this seal. Sources and all new authority flags stay unchanged/false. Independent full actual review is pending. A separate future38-byte suffix scope could follow cc266, but none is authorized by this report.
