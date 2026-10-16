# Private V24 pair send core

Twelve typed start/stop modes in six families. Copied R3 lifecycle algorithm,
with the existing no-send entry kept and tested. New single-use SendCore keeps
the independently cloned command after deleting the original. A durable intent
precedes a fresh fields/cancellation/world/LAST original TTL guard. Private
TransferPort is not implemented by this candidate and exposes no addresses.
Only normal true plus consumed slot is called Dispatched; effects, reception,
strict SP and epoch remain unproved. Every uncertain entry freezes and forbids
all local reads, cleanup, retry and rearm. Old sources/seals are untouched.
Offline tests use the old synthetic engine, never the game. No DLL or API backend.
