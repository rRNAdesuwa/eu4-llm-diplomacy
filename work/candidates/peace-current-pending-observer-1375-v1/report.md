# Peace current pending candidate: first offline delivery

Implemented the approved current-only queue design as independent
`peace_current_pending.py` with check/catalog/status. Runtime remains blocked:
the canonical source manifest is draft, sealed=false and
runtime_capture_authorized=false. No source or production receipt is installed.
No real status invocation occurred.

The first new suite ran31 methods once:31 passed,0 failures,0 errors in0.147s.
It covered empty/present/multiple repeated ID0/rawstate, foreign-vt no64B reads,
tombstone-before-invalid-action, iteration, prev/tail/cycle/count, one-sided
actor binding, recipient/marker, short reads, two-pass/table changes, code
mismatch, budget limits, low pointers, source/production gates, failed close,
uncleared handle and strict success flags. These are fake/owned-file tests;
they do not prove real current-world compatibility or effect.

First file-only check and catalog both returned files_verified. The candidate
graph has32 explicit pins/3502427B, including the full design owner graph and
CLI itself. Frozen direct-v1 Libraries verified its own graph and delegated
old-host closure of215 local/11 selected external pins. Those source/sample
helpers were reused; old main/capture/registered argv/REA/Frida were not called.

All three operations ran in the reviewed Job helper with45s and768MiB limits.
The new fake-suite/check/catalog Jobs exited0, had active-process-final0, and
reported peak commit25112576/32460800/33202176B respectively. All source files
were unchanged across the first run. The receipt is
`offline-r1/receipt.json` (5631B,
SHA25662d2304667ef588c5b28d600ef02b08e85b8093fb166f9960e7cdacc8e49a0d5).
No old suite was rerun and no native scope was decoded.

The runtime entry adapter is a reviewed-source candidate change: it subclasses
the frozen RuntimeCapture and preserves initialization/exit behavior while
moving its8192B loaded PE read into the same shared4096/512KiB attempt ledger.
Structural reads use frozen AlignedPort; the exact pinned unaligned code slice
uses the same budget/canonical guard but bypasses only extra alignment.
Successful evidence needs normal context exit, cleared held.handle and final
source/disk guards. OS CloseHandle return remains explicitly unchecked.

Source-ready review must examine this new adapter and the complete fake-to-real
host flow; real world is still pending. Runtime receipt schema is documented in
README and requires exact CLI/source-graph subjects plus root production
approval. No profile/effect/native authority is promoted: stable15/98pins and
historical48/44/42 stay unchanged. No requests, saves, game accesses or real
process memory reads were performed in this implementation task.
