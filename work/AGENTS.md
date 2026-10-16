# Native analysis resource limits

- Never load a large disassembly into a PowerShell array with `Get-Content`.
  Check file size first. For files above 10 MB, use `rg` or streaming Python
  with bounded context/output. Do not use `Select-String -InputObject` on a
  whole-file array or run simultaneous whole-file scans.
- Disassemble only the specific function or bounded address range needed.
  Do not repeat the 350 MB `runtime/offer-action-4e64.txt` whole-file scan.
- An agent must not leave running shell sessions behind when reporting done.
  Track each returned session ID; collect completion or stop the exact process.
- Stop analysis if an analysis process exceeds 1 GB committed memory. Inspect
  its exact command before terminating it; do not stop unrelated user processes.
- The 2026-10-05 incident involved two orphaned `pwsh` scans committing about
  9–10 GB each and inducing paging. They were stopped. Prefer bounded reads.
