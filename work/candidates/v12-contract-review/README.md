# v12 factory-contract review

The frozen v11 lifecycle test stopped at `form_coalition`: the factory aggregate
check failed, the original was destroyed, and no clone was created. The log
records exception zero and submitted false. It does **not** record the actual
value of `action+0x34`.

Disk evidence provides a sufficient explanation: factory block `0x35dfde`
writes `DWORD [rcx+0x34] = 2` at `0x35e051`, then jumps to `0x36045c`. It skips
the shared zero-state store at `0x360459`. Frozen v11 demanded zero for every
family. The coalition clone copies the source's state at `0x58a899` /
`0x58a89c`, so both uninitialized factory and clone contracts require two.

The following five families were checked through their complete factory tails:
support independence, trade-power transfer, steering trade, gift, and favors
for gold. All execute the shared zero-state store. Transfer and gift retain
their evidenced zero derived amounts; transfer's extra byte is zero. Insult's
default index is minus one. No additional default-field difference was found in
these bounded slices. `trace.py` reproduces `factory-contract-evidence.json`
against the exact executable SHA, decoding 2,501 bytes.

Normal coalition constructor `0x588dc0` also writes state two at `0x588def`.
Specialized legality construction at `0x5982b6`, script execution construction
at `0x6836f2`, and restored-action construction at `0x13b010` do likewise.
The ordinary native AI path is now closed: `0x12b860` initializes coalition
state two at `0x12c54f`, changes only value for cancellation at `0x12c691`, and
passes the action to `0x129b60`. At `0x12a6e3` the latter calls virtual `+0x40`
(`0x4e9930`), then transfers the resulting command into AI owner `+0xa68`.
The wrapper preserves the cloned state while updating the clone's date.
`work/reports/native-coalition-queue-1375.json`, SHA256
`b36c788c3eeb589abaa208df83cb3f97bf3697023188149588b41bb60dde5b65`,
contains that bounded proof. `trace.py` independently checks its 7,889 bytes
against the disk executable. This is an ordinary native queued-action path;
it does not establish a human GUI callback, final transport, or application.

The candidate therefore initializes **only token `0x2de0`** to state two in
core, preview, and command checks; the other nineteen families remain zero.
It does not assign state two to families that normally await a reply.

`prepare.py` verifies the frozen v11 manifest and all fourteen source hashes,
then writes fourteen version-isolated candidate sources under this directory.
Only four have functional changes beyond v11-to-v12 naming. It never
writes `work/native/v11`, an executable, a game file, or a runtime request.
`prepare.py --check` verifies deterministic candidate reproduction. The explicit
`--materialize` option can later copy the reviewed files into the new v12 paths;
it has not been used. It refuses an existing v12 DLL, build manifest, session,
or differing native source, and validates all destinations before any write.
No v12 DLL has been built by this candidate.

The existing `pair_lifecycle` event gains three diagnostic groups, prefixed
`factory`, `clone`, and `retained_original`:

- `*_contract_checked`: Boolean. The applicable reads completed, or a pointer /
  derived-identity rejection completed before further field reads.
- `*_state`: unsigned 32-bit number after a successful state read; otherwise null.
- `*_contract_failure_mask`: unsigned 32-bit number after the check completed;
  otherwise null. Success requires zero, not merely `checked=true`.

An absent clone has `checked=false`, state null, and mask null. Diagnostics are
captured within the same SEH region as the factory/clone operations, before
destruction. An exception does not trigger more reads. The existing lifecycle
success and destruction conditions remain mandatory. The output buffer is
4,096 bytes and the `snprintf` result must fit completely before logging.

The mask assigns these bits (numeric mask is `1 << bit`):

| Bit | Field or contract |
| --- | --- |
| 0 | Null or factory-sentinel pointer |
| 1 | Derived vtable |
| 2 | DWORD marker at `+0x08` |
| 3–5 | QWORD actor / original actor / target at `+0x10/+0x18/+0x20` |
| 6–7 | DWORD dates at `+0x28/+0x2c` |
| 8 | DWORD envoy at `+0x30` |
| 9 | DWORD state at `+0x34` |
| 10 | WORD value and flag at `+0x38/+0x39` |
| 11 | DWORD field at `+0x3c` |
| 12 | Insult DWORD index at `+0x40` |
| 13 | Gift DWORD amount at `+0x40` |
| 14–15 | Transfer DWORD amount / BYTE flag at `+0x40/+0x44` |
| 16–17 | Subsidy DWORD amount / years at `+0x40/+0x44` |
| 18 | Marriage string first byte at `+0x40` |
| 19–20 | Marriage QWORD string length / capacity at `+0x50/+0x58` |
| 21 | Marriage BYTE flag at `+0x60` |

`test_contract.cpp` uses the exact diagnostic helper against synthetic owned
bytes. It includes the previously missed coalition-state-zero counterexample,
individual mutations for every field bit, fixed nonzero derived parameters,
and absent-clone formatting. The separately authorized isolated compile/run
passed MSVC x64 `/W4 /WX`: **54 checks, zero failures**. Full output and hashes
are in `test-output-20261008a.txt` and `test-validation.json`. It contains no
Windows API or game calls. This test does not compile or invoke the v12 DLL.
The four changed target CPP files additionally passed separate MSVC `/c /W4
/WX` compilation. Those object files were not linked into a DLL; full compiler
output is in `compile-output-20261008a.txt`.
