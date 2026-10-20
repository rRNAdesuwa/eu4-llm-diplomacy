# V22 private no-send batch client

This client is restricted to the separately sealed V22 no-send DLL, one fresh
process creation and one client-owned session. It publishes six positive pair
requests once. It has no sender, retry, unload, pointer or envoy input. The formal
API remains validation-only. This client does not attest strict single-player,
world epochs, allocator ownership, receive completion or diplomatic effects.

Run only with Python `-I -B` after externally checking the sealed client hash and
source index. Loading is explicitly restricted to the disposable baseline. A
permanent loader intent, bootstrap and batch publisher intent prevent reuse.
The publisher validates readiness before publication, then publishes all six
requests without observing individual action results. The final inspector checks
the complete bounded audit, permanent canonical claim/request bytes, call pairs,
object counts and known cleanup. A frozen or incomplete audit is never success.

Tests use only analysis-owned synthetic files and the pure C++ wire codec. No
game process, DLL load or native game call is part of offline validation. The
exact prior loader graph is captured and verified before its definitions are
evaluated. Only the explicitly invoked `load` command may use its injector.

The native guard may refuse a request before a call, and conservative marriage
heap-string rejection may freeze the research session. All permanent files and
private native ledgers must be preserved. Changes require a new sealed candidate
and fresh process. The older V17/V18/V19 sessions must never be rearmed.
