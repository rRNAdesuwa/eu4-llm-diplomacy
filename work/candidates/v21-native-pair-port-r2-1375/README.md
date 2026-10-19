# Private native pair port R2

This new revision addresses the independent F1 finding against the immutable
original adapter. Marriage String32 heap storage (capacity >= 16) is refused
before its pointer is read and before deleting destructors are entered. All
issued live objects are retained and quarantined. A readable/writable private
allocation, including one disjoint from known objects, does not prove ownership
by the game's allocator. No heap buffer is guessed, copied, reset or freed.
Only the known capacity-15 inline representation is supported. Valid heap
strings are conservatively unsupported pending an allocator ownership design.

The portable core is an exact copy of sealed R3. Its declaration is byte-identical
to R2; the adapter header points to that canonical R2 header to compose with the
five-family cancellation reader without physically duplicate pragma-once files.
The compiled engine implementation is R3: the native spy setter's ID survives
and the legacy binder confirms equality without a write.

The original adapter, R3 component, their tests, failures, and review seals remain
unchanged. Preimages here preserve copied files before local modifications.
Original author fake tests run with the heap-success expectation replaced by
quarantine; the R3 37-group integration suite is reused with only its include
path changed. Eight additional groups reproduce known aliases and unknown heap
ownership, with no fake deleting destructor entry; legal inline cleanup remains.

The real Win32 platform is compiled only as a separate object, never linked or
executed by these tests. No DLL, process reader, sender or external API backend
is built. OS identity, strict single-player state, world epoch, allocation
lifetime, receiver behavior and production readiness are not established by
these fake tests. No new disassembly or PE reads are needed for this revision.
