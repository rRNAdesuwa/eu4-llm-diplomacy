# Fixed five-spy initial/final census helper

One explicit invocation reads all five families, sequentially through one held
PID/creation-verified query/VM_READ handle. It calls the sealed dense full R2
observer's capture, preserving every complete original report. No DLL, native
function, sender, loader, console, request publisher, or game write is used.

Actor/target are fixed FRA/ENG; date is exactly 56456976 (1444.11.11).
Each family is bracketed by the selected frozen v17 pause predicate narrowed
to manual pause=1. Those pause/root/date observations must match across the
group and the full observer identities. The original observer's paused_verified
false is preserved; the outer pause observations are separate finite reads,
not permission for native execution. Group atomicity, lifetime, same-address
ABA, cache freshness, strict SP and complete world epoch remain unproved.

The entire five-family group shares 16 MiB / 8192 calls / 64 KiB single-read
bounds. PE guard reads are included in the final underlying byte limit. Output
is a CREATE_NEW/fsync JSON file capped at 8 MiB with all original reports. A
failure never overwrites an output or automatically retries sampling. There
is no intermediate-effect mode, dynamic family/target parameter or comparison
that promotes state equality into no-side-effects, causal, cost, or production
claims. Unknown dense arithmetic and unknown selected modifier semantics stay
in the original reports.

Future root-authorized usage (not run during candidate authoring):

```powershell
python -B work/candidates/v18-spy-group-census-1375/census.py --pid PID --creation HEX16 --phase initial --output NEW.json
```

Use `--phase final` once after all three no-send stages. This label only states
the caller's boundary choice; it does not assert that stages ran or completed.
The helper reads no stage log and offers no native readiness or effect result.

Offline checks:

```powershell
python -B work/candidates/v18-spy-group-census-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-group-census-1375 -p test_*.py -v
```
