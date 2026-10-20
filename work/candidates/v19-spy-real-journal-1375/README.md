# V19 private journal validator — pure candidate

This candidate validates supplied native-format files, not their authenticity
against a party able to replace the files. It never accesses a process, loads a
DLL, publishes a request, reserves an ID, or registers an execution backend.

`reader.validate_stream(raw, outer, identity, claims, complete=False)` accepts
complete byte strings and a fixed claim map (`1`…`4`, `4.item-1`…`4.item-5`). It
checks every JSON row, exact types, duplicate keys, all selected identity fields,
world/date/full handles, owner thread/frame, exact outer byte range and segment
SHA, ordered permanent claims, and installer successful-result diagnostics.
Maximum raw input is 1 MiB / 512 rows; outer input 2 MiB / 1024 rows; each line is
at most 8192 bytes and each fixed request/claim at most 1024 bytes.

`files.inspect_files(session, identity, complete=False)` only reads the explicit
fixed filenames under `spy19-PID-CREATION-SESSION`. Every request equals its
retained claim; item claims match the exact fixed family and batch expiry.
No link/reparse or multi-link regular file is accepted. Claims are reread and
their existence rechecked after the log read. This is not atomic across files.

`reader.coherent(read_pair, ...)` makes at most three full reads, with no sleeps,
no truncation, and no native-operation retry. Rereading is possible only for an
otherwise validated, complete preflight health tail / request-zero owner begin.
Both complete prior byte strings must remain prefixes. New claims, core calls,
faults, arbitrary outer events, malformed JSON, and semantic failures do not
qualify. In-progress native work without its Result is rejected, not hidden.
Send-phase tails are deliberately not reread by this minimal version.

The preflight reducer is an isolated versioned copy of the previously reviewed
pure protocol/model/projection/trace. Only the purpose becomes v19, local source
pins/import paths change, and an explicitly non-ready partial result view is
added. Every actual core/result row is still consumed; no synthetic health is
created. Three durable stage Results and separately later real health are
required before `next_sequence == 4`. A just-returned stage is not ready.

The new `Interval` reducer does not feed fabricated event times to sealed R2
SendModel. Normal Core `step_return` proves entered and returned, with the
intent-to-return observation interval. `entry_uptime` stays null. The pinned
Core's before-work barrier supports expiry semantics; the journal does not
measure an entry timestamp. A return or cleanup after expiry can be valid;
new work/claims cannot begin after expiry. Only true submit return plus consumed
NULL slot can become `dispatched`, which is not an AI/effect/settlement result.
All full Item fields, IDs, object flags, action fields, Result outcomes and
ownership flags remain checked. Typed terminal Result retains its current item
and freezes; no destructor, retry, or guessed cleanup is authorized. Missing
Result or missing outer correspondence is rejected. The extra `final_health`
owner call and outer `completed_send_batch` footer are required for complete.

Private output includes `status`, `next_sequence`, `preflight_ready`,
`authenticated_stages`, `completed_items`, `completed_outcomes`, last owner
uptime/thread/frame, selected roots, exact input hashes, and interval records.
All of `source_bound_origin_verified`, `build_loader_verified`,
`runtime_authorized`, effect/SP/epoch/production verification remain false.
**A future separately reviewed wrapper must bind the final v19 build manifest,
loader, bootstrap source chain and exact process identity before using this
parser as one publisher gate. Such a wrapper is not implemented here.** The
root bootstrap draft is not pinned as a completed or approved native build.

Current Host serializer contract is R2 (review `b3553d5c…3fcbd`). Its predecessor
is retained only as source ancestry and C++ mock capture provenance. The old
mock projector's reusable `Projection` class is not invoked: only pure typed
helper functions are reused. Its early-failure object-reuse finding is neither
fixed nor relied upon here; its seal remains unchanged.

Tests explicitly derive **synthetic** native-format rows from isolated C++ mock
captures, replacing mock flags only within fixture construction. These are not
actual Host receipts. Four normal captured Core paths (all dispatched, preview
false, gate false, mixed) pass, along with full Host/outer partial boundaries.
Adversarial tests rehash outer segments after changing semantic fields, so SHA
mismatch alone is not the intended rejection. No actual session was read.

Offline commands from repository root:

```powershell
python -B work/candidates/v19-spy-real-journal-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v19-spy-real-journal-1375 -p test_*.py -v
```

Development history: first test invocation failed because an integer sequence
was compared with canonical string claim-map keys; this implementation bug was
fixed before sealing. An additional test initially expected the wrong mixed
mock outcome vector; the actual captured vector is `[2,3,5,2,3]`, and only the
test expectation changed. Neither failed attempt is reported as passing. No
compilation or native/mock executable was run by this candidate.
