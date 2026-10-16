# Private V24 native pair transfer adapter

New namespace preserves all frozen R2 source bytes. Own ledger only, true gate,
original already deleted, command owns clone. Before adapter submission local
ownership is relinquished; no object reads/cleanup even on refusal or exception.
New SubmissionGuard requires two matching contexts, then world/typed owned
command+clone/context and LAST monotonic/original TTL. Platform pins exact submit
and transport bytes and invokes only 14ca210(context,command**). No receiver drain.
Native platform is compiled but NOT linked to the offline synthetic test EXE.
Private callbacks still need an actual initialized Host and fresh process.
No strict SP/epoch/lifetime/receiver causality/effect proof or production backend.

R2 fixes the transport vtable +0x30 slot address. The instance +0x30 is data; the synthetic fixture now deliberately sets it to zero/arbitrary data, and rejects a bad/missing vtable slot even when instance data resembles the function.
