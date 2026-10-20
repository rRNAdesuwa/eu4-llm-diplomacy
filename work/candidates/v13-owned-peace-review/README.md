# Isolated v13 owned-peace stage candidate

This directory is a review artifact. It does not modify v12, materialize a v13
runtime, build a DLL, open the game process, or invoke a native game function.
Root alone may materialize the reviewed sources and perform a single formal
DLL build after separately reviewing the v13 Python host and manifest recorder.

`python -B work/candidates/v13-owned-peace-review/prepare.py --check` verifies
42 pinned inputs and reproduces the 20-file native source set, its detailed
diff and machine-readable host contract. `prepare.py` without `--check` updates
only this isolated directory. It never copies into `work/native` or runtime.

`python -B work/candidates/v13-owned-peace-review/verify_candidate.py` uses an
exclusive output directory and MSVC C++17 /W4 /WX /EHsc. It compiles the actual
generated host and unchanged owned-peace core to objects; it separately runs
the pure state/marker helpers included by that same host. It does not link the
host or core. The old 41 default-layout checker tests are not repeated because
those four reviewed source files are copied without changes.

The native stage order is ordinary lifecycle (20), owned-peace default lifecycle
(1), preview (72), command (72), then the existing 36-ID research mailbox. Every
transition requires a later durably logged healthy frame. Each stage still has
an explicit marker and permanent claim. The new exact ASCII marker is:

```text
OWNED_PEACE_LIFECYCLE/1
purpose=restricted_pair_lab_1375_v13
pid={decimal_pid}
creation={16_lowercase_hex_FILETIME}
```

It ends with a newline. Filename: `owned-peace-lifecycle.request`; permanent
claim: `phase-owned-peace-lifecycle.claim`, both in the already private,
PID/creation-bound session directory. The existing audited same-handle consumer
validates all bytes, persists the CREATE_NEW claim before deleting the request,
and never retries an ambiguous post-claim outcome. The new stage never accepts
pointer, RVA, war, term, offer, target, or filename parameters.

`owned_peace_core_record` adds PID/creation/thread binding around the unchanged
core's step logs. Core return, `owned_peace_selftest_complete` (wrapper result),
and the following `research_frame` are different evidence. The core's final
return log occurs before its `passed` member is assigned; the wrapper validates
the returned Result. A durable wrapper alone does not open the next phase.
New frame booleans are `owned_peace_tested` and `owned_peace_passed`.

The wrapper supplies a boolean WriteFile+FlushFileBuffers logger and a fresh
paused-world/thread/process-creation guard before each native call. During this
single stage the date must remain unchanged. Original/clone layout, distinct
owned allocations, survivor reinspection and pin checks remain in the unchanged
reviewed core. Any failure or SEH permanently freezes the session; unknown
ownership is not speculatively cleaned or retried.

This verifies no runtime behavior yet. The factory's internal default temporary
is already cleaned when it returns; only original and clone are simultaneously
observable. Destructor return is not proof of released heap memory. Parameterized
offers, war identity, negotiation direction, real peace terms, wrapper ownership,
submission and effects require separate fixtures and verification. Root/player/
date invariants are not a complete world epoch or multiplayer-origin proof.

The DLL would retain the existing research sender. Only the new owned-peace
module is no-send, with no command wrapper or submit call. This adds no peace
API action and no production backend. All runtime/execution verification flags
remain false until separately supported by appropriate evidence.
