# 原生 AI 白和平结算存档检查

本次只读检查了：

- `llm_ai_peace_before.eu4`
- `葡萄牙1445_05_30.eu4`
- `llm_ai_peace_before_Backup.eu4`

解析范围为 `meta`、英法关系、英法战争、停战字段和 2472 个省份的当前 `owner`。

结论是：**本轮白和平结算尚未保存到这些文件中。** 三个存档都仍包含 1 个英法活跃战争，参战结构为法国及其 6 个盟友对英格兰和葡萄牙；英法双方关系块都没有 `truce` 字段。三个文件的日期分别为 1445.5.30、1445.5.30 和 1445.5.23，当前玩家均为 POR。

`llm_ai_peace_before.eu4` 与 `葡萄牙1445_05_30.eu4` 的 SHA-256 完全相同，说明这两个文件是同一存档内容的不同文件名。它们与 `llm_ai_peace_before_Backup.eu4` 的 2472 个省份所有者也完全一致，未发现领土变化。

法国的 `last_sent_peace_offer_date` 在三个目标存档中都是 `1445.4.8`，没有记录本轮执行后的发送日期。请求中的运行时日志（FRA→ENG 从 state 0 到 2、`preview=100`、费用为 0）只能说明进程内执行结果，不能替代结算后的存档证据。

因此，用户报告的“两国已和平”可能是当前尚未保存的内存状态；需要在和平成立后另存一个新文件，再检查是否出现英法停战字段、战争记录结束或参战方移除。当前检查不把“没有领土变化”误判为“没有结算”，也不把这些旧存档中的活跃战争误判为本轮 AI 明确拒绝。

详细机器可读结果见 [`native-ai-whitepeace-settlement-save-check.json`](runtime/native-ai-whitepeace-settlement-save-check.json)。
