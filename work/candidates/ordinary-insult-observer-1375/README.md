# Ordinary insult selected-state observer candidate

This directory contains disk-only static closure and a separately versioned,
read-only observer. It does not change the diplomacy catalogue, an existing
observer, a frozen native source, a DLL or a request publisher. No game process
was accessed while authoring or testing this candidate.

The only supported action is ordinary `insultaction` with negative index (the
research engine's fixed value is `-1`), fixed actor FRA and target ENG/POR/NAV/FOI.
Scornful insult and arbitrary actor/tag resolution are excluded.

## Exact static evidence

`trace.py` accepts only executable SHA-256
`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`.
It verifies the three root-authored initial reports, decodes ten bounded
functions plus one fixed 39-byte initializer slice, and emits `report.json` and
`contract.json`. No calls are followed recursively. The maximum is 32 KiB of
decoded instructions and 768 MiB committed analysis memory. `--check` recomputes
the bytes without overwriting either artifact.

The ordinary branch chooses the cached definition at `*(base+0x233ff08)+0x2f8`.
Its wrapper is initialized with the exact name `insulted`; the wrapper name is
String32 at `+8` and the pointed definition name is String32 at `+0x10`.
The observer requires both names, the exact cached definition pointer and
runtime opinion `-50`, duration `120` months and maximum `0`. It reads the
minimum separately and requires it to permit `-50`. Base script values are
evidence of that base file only; they do not prove mod load precedence.

The target country owns the affected bilateral record:

| Field | Layout and interpretation |
| --- | --- |
| Bilateral record | target `+0x1510` array plus actor slot × `0x48` |
| Direction | record `+8` owner full handle; `+0x10` actor full handle |
| Trust | target's trust toward actor, BYTE `+0x1e`; native effect clamps old minus 5 to 0..100 |
| Relation manager | record `+0`; manager `+0x10` owner country and `+0x18` bilateral array must agree |
| Outer container | manager `+0x308` data, signed capacity `+0x310`, signed count `+0x314`; actor slot selects a 24-byte entry |
| Inner container | vtable `base+0x1c38348`, data `+8`, signed capacity `+0x10`, signed count `+0x14` |
| Modifier | pointer array; vtable `base+0x1ccf4f8`, type DWORD `0x165`, size `0x28` |
| Selected modifier fields | definition `+0x10`, expiry date `+0x18`, multiplier `+0x1c`, opinion milli `+0x20`, raw flags `+0x24/+0x25/+0x26` |

`0x28ca50` is **not a read-only getter**: an absent slot can grow the outer
container through `0x28dc90`. This observer never calls it. A slot beyond the
materialized count returns `unsupported_unmaterialized_container`, not absence.
It also never calls the lazy CB getter `0x1f9210`, any modifier helper or virtual
method. The manager's dynamic vtable is not classified; the known owner/array
links are the explicitly checked manager identity contract. Unknown modifier
classes are inventoried by header only and prevent an absence/effect conclusion.

The modifier serializer's exact token names are recorded in `report.json`:
`modifier`, `date`, `current_opinion`, `expiry_date` (BYTE flag `+0x26`, despite
the name), `delayed_decay` and `multiplier`. This is not yet a save parser: the
parent saved diplomacy container's role and completeness rules are not closed.

## Observation and comparison contract

The reader has a 64 KiB single read, 1 MiB total read and 8,192 read-call limit.
Country lookup is bounded by the actual database count and 4,096 absolute limit.
Only the selected actor slot is read from the outer array. Each selected inner
container has a 256-pointer limit; duplicate objects or duplicate selected
definitions are rejected. Unknown objects are not followed past their header.
String32 uses bounded length/capacity, inline/heap selection and required NUL.

Each of two independent passes resolves roots, date, FRA/player and both full
country handles afresh. Known reset/load flags must be clear. The same identity
is reread at each pass end; complete typed snapshots must agree. Selected native
instruction bytes are checked before and after both passes. Imported reports
revalidate **both** complete passes with strict integer/boolean/string types;
stored state is recomputed, not trusted. Two equal Python bool/int/float values
cannot substitute for one another. Missing fields are not treated as null.

The explicit future process entry holds one QUERY_INFORMATION | VM_READ handle,
checks PID and full `GetProcessTimes` creation before and after, checks exit time
zero, exact process EXE path, full disk EXE SHA and loaded PE timestamp/size.
It requires the supplied canonical 16-character hexadecimal creation value.
Every failure closes the handle. It never opens write/operation/thread rights.
The loaded whole image is not hashed; selected code pins do not prove all code
or all possible reset paths.

`compare` requires the same process, module, roots, full identities and game date,
unchanged runtime definition/owner bindings, and ordered observation intervals.
The first supported transition is:

1. Before: a fully read, recognized container has no exact `insulted` definition.
2. After: exactly one recognized modifier has that definition, value `-50000`,
   multiplier `1`, flags `0/0/0`, and expiry later than the observation date.
3. Target trust decreases from a positive prior value to `max(0, old-5)`.

The result is `observed_selected_transition`. It never proves request causality,
AI acceptance, CB changes, whole-world invariance, strict SP, an atomic snapshot,
world epoch, execution capability or persistence. Existing-modifier refresh and
stacking are unsupported. The exact calendar expiry calculation is not emulated;
the comparison's future-expiry condition is explicitly narrower than proving
the full native 120-month calculation. Missing/unsupported/unstable data or an
unmatched transition means unknown, never diplomatic rejection.

## Offline author validation

Run these commands from the repository root:

```text
python -B work/candidates/ordinary-insult-observer-1375/trace.py --check
python -B -m unittest discover -s work/candidates/ordinary-insult-observer-1375 -p test_*.py -v
python -B work/candidates/ordinary-insult-observer-1375/validate.py
```

Tests use sparse byte maps and mocked held handles only. They cover all four
targets, full handles, direction, ownership links, actual count limits, unknown
classes with unmapped tails, duplicate pointers/definitions, missing cache,
code pins, bounded inline/heap strings, two-pass instability, imported type
aliases, trust clamp, matching modifier defaults, dates, creation and closing
the mocked handle. `preparation-history.json` preserves the first 26-test run's
single error: a synthetic unknown vtable was accidentally unaligned; the test
fixture was corrected, with no relaxation of the pointer guard.

Later root-authorized read-only commands (not executed during authoring):

```text
python -B work/candidates/ordinary-insult-observer-1375/observer.py sample --pid PID --creation 16_LOWER_HEX --target POR --exe EXACT_EU4_EXE --output NEW_BEFORE.json
python -B work/candidates/ordinary-insult-observer-1375/observer.py compare --before NEW_BEFORE.json --after NEW_AFTER.json --output NEW_COMPARISON.json
```

All output files use exclusive creation. No CLI operation sends an insult or
changes the game. This candidate requires independent review before actual
read-only use; it does not authorize any native submit.
