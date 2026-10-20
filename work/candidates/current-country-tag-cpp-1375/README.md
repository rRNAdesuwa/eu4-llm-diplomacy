# Private C++ country resolver

This is a portable C++17 implementation of the independently reviewed Python `current-country-tag-resolver-1375`. It accepts one to sixteen distinct ASCII TAG strings and an internal read port/module base. It returns private bindings with the observed full QWORD handle, lookup slot and object address. Addresses and handles are not public request parameters.

It verifies the same selected instruction bytes, ordinary current-player selector0, signed database capacity/count and date, known reset/load fields, a complete country pointer table, country type header before derived reads, unique addresses/handles/TAGs, exact reserved slot0, and current-player full identity. Two complete passes must agree, including in-pass table/root rereads. Read budgets are shared: 20,000 calls, 512 KiB total and 32 KiB per read. Failed reads never imply a country is absent.

Unlike the Python file format, this private C++ result retains exact pointer arrays and typed rows directly; it does not serialize/revalidate a caller-supplied record or compute an array hash. Equality never relies on struct padding. The same generation/type filters are research profile limits, not a theorem about all engine handle types. High generation bytes are retained. Selector7 remains unsupported.

No OS reader, native call, process attestation, DLL, sender, execution backend, lifetime lock, clock guard or world epoch is implemented here. Read callbacks can race. Equal observations do not exclude same-value ABA; the positive synthetic ABA control makes this explicit. Future NativeGuard integration must apply its own final current-identity/clock barrier after this resolver returns. This component alone authorizes no engine work.

Tests use only an in-memory synthetic read port. Compilation is limited to a spawned analysis job, 768 MiB per process and 55 seconds; all descendants are collected. Sealed Python inputs and formal API files are never edited.
