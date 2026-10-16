# Current-country TAG resolver, exact 1.37.5 research candidate

This directory implements a **pure injectable byte-reader model**, not a live
process reader, a game getter or a diplomacy backend. It imports no formal API.
No code here opens a process, injects/loads a DLL, reads a session, publishes a
request or executes a native function. All tests use synthetic sparse memory.

## Interface

```python
request = {"tags": ["FRA", "POR", "D00"]}
result = resolver.resolve(private_reader, privately_bound_module_base, request)
public = resolver.public_result(result)
```

The public request accepts only 1..16 distinct `[A-Z0-9]{3}` strings. It rejects
raw addresses, ready/control fields, bool/number aliases, Unicode lookalikes,
case folding and unknown fields. `module_base` and `reader` are private host
inputs, never client parameters. The public projection returns each unique TAG,
its observed slot ordinal and the **entire QWORD** as canonical 16-digit hex.
It does not reconstruct a handle from a hard-coded generation, known initial
slot or TAG arithmetic. Slot ordinal and the three TAG bytes are separate fields
of the observed QWORD.

## Existing exact-byte evidence, no new decoding

`trace.py --check` reselects small slices from five already-saved reports and
seeks their bytes in the full-SHA-pinned disk EXE. It does not disassemble again.
The report records original source/function, instructions and raw file offsets.

- `2897c0..2897e5` copies a QWORD country-table bucket entry to the stack and
  compares **three bytes** starting at that QWORD to the textual input. Its
  failure path writes the exact invalid `---` QWORD. This establishes byte/TAG
  binding, not a formula that converts TAG bytes into a country slot.
- `4ea87f..4ea895` reads global `233d8d0`, array `+118`, then shifts the handle
  by32 and sign-extends the resulting WORD for an 8-byte index. The resolver's
  0..4095 restriction is a research subset of that signed-word representation.
- `749207` passes database+110 to `74e8e0`; there `+14` is the signed DWORD
  count, `+8` is the pointer array with stride8. `28314a/151` uses `+10`
  capacity, yielding database+124/+118/+120 respectively.
- `2c997f..2c999b` writes country marker165, vtable1c574a0 and the constructor's
  full QWORD at+20. Only this type header is supported. Unknown headers stop
  before reading+20; no derived field is guessed.
- `28318d..2831b2` constructs the first country with invalid `0x2d2d2d`, then
  begins normal country construction at1. The supported model allows a null
  slot0 or that exact typed sentinel, not an arbitrary invalid handle elsewhere.
- `522ba7..522bea` shows the effective-player variant: alternate+1e68 is used
  only when selector byte+1e66 is7 and byte+1e6f is nonzero. **This version only
  supports selector0.** It captures/rechecks both overlapping raw QWORD/byte
  forms; variant7 or any other selector explicitly raises Unsupported.

The nonzero high byte, zero byte3/type-byte6, uppercase/digit TAG syntax,
4096 count/cap and16 request cap are conservative **research filters**, not
claims of complete game validity. The high byte is preserved in the full
identity; no monotonic lifetime/generation theorem is inferred from it.

## Observation checks and limits

Each pass reads the lookup header, date, current/effective player, alternate
selection fields and known reset/load exclusions; then the full bounded pointer
array and every non-null object's guarded type/handle. Addresses, TAGs and full
handles must be unique. A handle's ordinal must match its exact array slot.
Current/effective player must resolve to the same full object identity. Dangling
or unreadable pointers, unknown types, missing requested tags and malformed
entries stop the whole operation; they are never silently omitted.

Each pass rereads the complete pointer array and roots. Two complete typed
passes must match, and selected instruction-byte pins are read before and
after. There is one shared budget: <=20000 calls, <=512KiB, <=32768B/read.
The maximum4096 fully populated fake table is tested. Report budget counts are
recomputed from the exact successful sampling shape, not accepted as arbitrary
caller assertions. `public_result` revalidates both complete passes and derives
the exposed binding list again; its input remains a supplied record, not an
independent origin attestation.

Null slots and missing TAGs do not prove gameplay absence, annexation state,
legal target, visibility or authorization. The normal constructor's type header
is a supported static profile; no runtime test of arbitrary-country coverage
has been performed. There is no `sample_process` or held-process wrapper here.
A future caller must separately bind PID+creation, full EXE/module origin,
owner-thread/context and the moment of native use, then recheck under its own
lifetime guard. The selected byte pins are not a whole loaded-image hash.

Equal pointers, handles and dates do **not** exclude same-address replacement,
CCountry::Clear(), changes between reads, ABA or world reload. The ABA test
explicitly demonstrates an invisible change/restoration while all authority,
epoch, SP, lifetime/effect and production claims remain false.

## Reproduce without game access

```powershell
python -B work/candidates/current-country-tag-resolver-1375/trace.py --check
python -B work/candidates/current-country-tag-resolver-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/current-country-tag-resolver-1375 -p test_*.py -v
```

The only actual file exploration is exact selected instruction bytes and the
fixed EXE's streaming SHA. No large disassembly is read and new decode is0.
