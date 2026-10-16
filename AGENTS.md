# EU4 diplomacy research workflow

- Read the latest section at the top of `HANDOFF.md` and `README(agent).md`
  before continuing. Historical sections do not override the latest state.
- For native reverse engineering, use the installed REA skill at
  `${USERPROFILE}/.agents/skills/reverse-engineer-anything/SKILL.md` and
  `docs/rea-workflow-1375.md`. Local REA source is `${USERPROFILE}/rea`.
  `python tools/rea.py ...` reuses the Codex REA registration for CLI access.
- REA evidence, ordinary disassembly, static inference, and observed runtime
  effects must remain distinct. Keep binary SHA-256, RVA/VA distinction,
  bounded address ranges, and unresolved conditions with each finding.
- Follow `work/AGENTS.md` resource limits. No whole-file disassembly scans.
- Keep the existing no-repeat policy: historical successful actions, dispatched
  or unknown actions, original final-pass request IDs, and unclosed ownership
  cannot be retried. Static findings do not authorize a fresh dispatch. New
  corrective tests require the complete audit and `--test-only` policy described
  in the current handoff. Do not repeat the original 120-action batch.
