# Private pair guard R2 composition

This revision connects the sealed R3 portable core and the repaired native port
R2 declaration with the existing TAG resolver and five-family cancellation reader.
One original lease, owner thread, typed full handles, paused health, dates, roots,
reset/load and original <=60s expiry remain mandatory. StopSpyNetwork now binds
its exact typed graph twice at lease creation and rechecks it in the final
Authority callback before the fresh clock. No native-written envoy is changed.

NativeEnvironment is copied into this candidate, with source preimages and only
include relocation plus country header/marker checks before derived country
fields in sample(). Its health sampler still requires the historical FRA/ENG
slots to exist; this is a restricted test environment, not a general production
sampler. Strict single-player and world epoch are still not proven.

The guard tests inject fake callbacks. The environment binding is compiled but
not instantiated by those tests. A separate boundary executable calls the actual
sample() on analysis-owned VirtualAlloc memory, deliberately bypassing initialize;
an inaccessible derived field distinguishes type refusal from a failed read.
This is not game process memory, provenance or initialization attestation.

No sender, export, hook, request consumer, public backend or durable claim is
introduced. Actual Host composition and a fresh, source-bound DLL remain next.
