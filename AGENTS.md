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

### 关于subagent
仅限Astra,Sol和Terra模型使用subagent：你可调用 5.6 Luna-Max。你负责核心推理、决策和最终整合；对于耗时、重复、机械、可并行或可独立验证的工作，主动委派给 Luna-Max，必要时并行调用多个实例。不要过度思考是否委派：简单任务自己顺手做了，明显的脏活累活直接派出去，并快速检查其结果后继续工作。假如遇到情形：必须需要等subagent返回结果才能继续。那就等着，什么也不做，不用自己跟subagent并行去做。不用和subagent在同一件事上重复劳动，除非怀疑subagent出错。

子代理曾两次 pwsh 全量读取约 350 MB 反汇编，各提交约 9–10 GB 内存，导致换页风暴，系统几乎卡死。应提醒subagent注意。