# v19 restricted Host R2: two terminal-boundary repairs

This is a new, isolated source/object/mock candidate. It does not build a DLL,
install a hook, inspect EU4, publish a request, or call an engine function.
The sealed predecessor remains unchanged. `predecessor-README.md` records its
full interface and limits; `interface.json`, public C++ headers, private wire,
journal, preflight Controller, native environment, Core and all versioned
preimages are byte-identical. `host-r2.diff` is the entire native behavior delta.

The predecessor's independent review is pinned with its original counterexample
source and output. Its two reported behaviors were observed using the actual
sealed C++ Controller and an isolated mock resolver, not a Python approximation:

1. A false `begin_frame` callback on sequence 4 returned false without freezing.
   Restoring that callback allowed the same request to claim and submit in mock.
2. Preflight clock observations did not update the outer Host clock. A final
   preflight observation of 10000 followed by sequence 4 at 9999 was accepted.

R2 routes every owner-frame initialization through the same private wrapper.
A false return or terminal state during that callback locks the Host. A later
successful callback, an empty frame, or the same packet cannot recover it.
The shared `clock_cb` now records every actual observed clock across all three
preflight stages and sequence 4. A lower value locks failure `clock`; the
callback returns the actual value and never clamps, substitutes or invents a
timestamp. The send barrier uses that same callback and rechecks terminal state
before any subsequent claim or native operation. Equal readings remain valid.
Existing SEH, reentry, unique-claim, ownership, TTL and no-retry rules remain.

Only `host.cpp` changes native behavior. The original `test_host.cpp` is copied
unchanged and included by `test_host_r2.cpp`; the mock build changes only its
test entry filename. New tests use the real Controller paths for all 17
preflight/batch/item/health callback boundaries, unrecoverable false returns,
preflight-to-sequence-4 rollback, postclaim and later-health rollback, and valid
equal/advanced clocks. The object-only NativeEnvironment is compiled but is not
linked into or initialized by the mock executable. Temporary mock journal files
are retained. Runtime/strict-SP/epoch/effect/production flags stay false.

```powershell
python -B work/candidates/v19-spy-restricted-host-r2-1375/prepare.py --check
python -B work/candidates/v19-spy-restricted-host-r2-1375/validate.py --output work/candidates/v19-spy-restricted-host-r2-1375/validation-new
```

The output directory must not exist. Validation has a 55-second child timeout
and collects only its own compiler/mock process tree. No old source or artifact
is replaced. `derive.py` is the recorded CreateNew source derivation, not an
installation or mutable rearm command.
