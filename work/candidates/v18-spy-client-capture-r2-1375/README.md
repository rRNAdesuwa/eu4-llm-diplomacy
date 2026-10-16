# Private R2 reader client wrapper

This is a Python-only research client revision. The original client, loader,
wire codec, DLL and build manifest remain unchanged. It is not a new DLL build,
an installed client, or a production API. No actual session is read and no game
stage is published during candidate validation.

The original client's exact verified bytes are compiled with their original
`__file__`. Fixed private import aliases route `real_capture` to the sealed R2
reader; `build_manifest`, `wire`, and `loader` keep their original source and
identity. Both publication gates and the status gate therefore use R2. Private
imports do not change `sys.path` or replace `sys.modules`, and the CLI accepts no
validator/dependency callback. R2's source identity is recorded separately from
the unchanged original DLL manifest. The old manifest is never relabelled as
containing this wrapper or the R2 reader.

Source checks run before delegating the unchanged CLI. The source chain is a
local research provenance check, not authentication against a user who can
replace all files. Standard Python import/runtime integrity is a prerequisite.
The private frozen loader remains importable for its query-only process guard
and CREATE_NEW helper; this wrapper never calls loader.main or its injection
path. The original loader's three query helper imports preserve their own
existing origin verification.

Only `status` and explicit `stage lifecycle|family_preview|owned_command` are
available, with the original required `--build`, `--pid`, `--creation`, and
`--session`. There is no loop, automatic progression or retry. A stage requires
fresh owner health, strict next sequence, the exact held live process identity,
and durable permanent publisher intent before rechecking R2. Any failure after
intent leaves that intent in place. A failed/unknown rename is never retried or
overwritten; temporary files and intent remain evidence. Normal publication is
still native-result-unknown, not a stage completion or an effect.

R2 additionally rejects result=0 installation receipts with empty collected
thread sets or nonzero error/failure_thread/rip. Terminated threads may leave
suspended < collected. This restriction applies at all three client read sites.
No guards, freshness limits, native protocol, or ownership contracts are relaxed.

Offline checks:

```powershell
python -B work/candidates/v18-spy-client-capture-r2-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-client-capture-r2-1375 -p test_*.py -v
```

Tests use synthetic raw/outer logs, temporary directories, a fake process guard
and clock. They retain real R2 file/log validation and CREATE_NEW/fsync/rename
operations on test files. No actual process, game, DLL mapping, loader call,
native function or existing session is accessed. A future live invocation is
separate root-authorized work after independent review.
