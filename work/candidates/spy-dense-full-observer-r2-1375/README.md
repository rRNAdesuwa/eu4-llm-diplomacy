# Spy dense full RO observer, revision 2

Separate candidate replacing the rejected first integration. The previous
observer and its independent rejection remain pinned and unchanged. This source
adds exact integer comparisons for every shared cost field that the dense
kernel actually observed: base, cache state, transform root, transform, and
aggregate address/dense/data/count when reached. Both full snapshots must bind.
Unobserved None fields in unsupported early branches are not observations.

The four original sparse-memory substitutions (data, count, transform root,
transform) must now fail. Stable unknown cache, root, transform, aggregate,
layout, vector and selected-record branches retain an unknown candidate without
inventing a dictionary or granting execution authority.

The shared reader has a 16 MiB / 8192 payload-call / 64 KiB single-read budget.
The held-process opener uses the prior reviewed exact EXE/path/PE/PID-creation
checks and closes its VM_READ handle on success and failure. PE guard bytes are
included in the final underlying byte budget. There is no CLI, file publisher,
engine getter, native call, game write, or production capability.

Equal snapshots and equal pointers do not exclude same-address value ABA,
cache staleness or object lifetime changes. The cost is only a static arithmetic
candidate. The original full observer still reports dense cost as unsupported;
its raw record is preserved. All execution/effect/production claims remain false.

Validation uses sparse raw memory and mocked OS handles only. No actual game
sampling is permitted before independent review of this new candidate.
