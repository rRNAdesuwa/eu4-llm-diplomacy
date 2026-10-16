# EU4 1.37.5 offline API lookup v5

59 retained research endpoints,74 directly guarded JSON sources. The original
v4 58 records and59 source pins are preserved. The only new entry is993570;
R71/R73 are later conditional inherited-fragment context, not standalone APIs.
NULL993658, unknowncallees/finalD/units/recipients/effects/lifetime stay unknown.

This version uses a NEW16583B Python queryengine identity. The sole engine
change is source-count ceiling64→96;4MiB perfile/32MiB total guards and parser
semantics are unchanged. Frozen d423engine/v1-v4 files are untouched. Source
hardening and engine delta await a nonauthor review. Every authority staysfalse.

File-only commands: check; catalog; lookup0x993570; search993643. Exit0 means
local evidence query succeeded, never nativeAPI readiness. No process access,
game call, request, installer, listener, publication or package is included.
--base remains conditional user-supplied arithmetic, not module authentication.

engine-delta.json,lineage-proof.json andreference-verification.json preserve
the narrow delta and allflat provenance. First newguardfixtures distinguish
real boundedfakefile reads from synthetic aggregate returnedbytes; receipts
and allstdout/stderr are retained. Oldtests/CLI suites are not repeated.
