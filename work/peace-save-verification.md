# 英法白和平存档窄范围验证

检查对象：`EU4_USER_DATA\save games\英格兰1445_06_16.eu4`

文件独立检查时间：2026-10-04。存档是 ZIP，包含 `gamestate`、`meta`、`ai` 三个条目；未修改存档内容。

## 可确认的文件证据

- `meta` 的日期为 `1445.6.16`，玩家为 `ENG`，`not_observer=yes`，版本为 `1.37.4.0`。
- `countries.ENG` 有 `human=yes`、`was_player=yes`；`countries.FRA` 没有这两个字段，并有初始化完成的 `ai` 块（`personality="ai_balanced"`）。因此该快照能确认英格兰是玩家国家、法国由原生 AI 控制。
- 当前 `active_war` 仍有 8 个文本块，其中英法战争块仍存在，但其 `history` 在 `1445.6.16` 记录了 `rem_attacker="FRA"`、`rem_defender="ENG"`，以及法国一方盟友和英格兰一方盟友的 `rem_*`；该块的 `outcome=1`。
- 与此前 `llm_peace_after_reject.eu4`（`1445.5.6`）及 `英格兰1445_04_24.eu4`（`1445.4.24`）相比，英法战争块此前没有这些 `rem_*` 记录，也没有 `outcome` 字段。这支持战争在新快照中已经结算。
- `countries.ENG` 对 `FRA` 的关系记录为 `last_war=1445.6.16`、`truce=yes`；`countries.FRA` 对 `ENG` 也记录相同的 `last_war` 与 `truce=yes`。两国各自还有 `last_war_ended=1445.6.16`。

## 用户操作与文件证据的边界

用户报告原生和平接受后战争正常结束，游戏显示停战期至 1450 年 7 月，并且保存后重新载入没有异常。文件独立检查确认了结算日期、双方停战标志和身份，但该版本的关系块没有单独保存一个 `truce_until` 字段，因此“1450 年 7 月”的具体终止日期来自游戏界面报告，不能仅由本存档文本独立重建。

`active_war` 容器在这个即时保存快照中尚未从文本中消失；能确认的是其中所有参战方已在历史记录中移除且存在 `outcome=1`。因此不把“整个 `active_war` 块已删除”作为已证实事实，建议后续推进一段时间后再保存一次，检查引擎是否清理该历史块。

存档 SHA-256：`3354B5520934587156ACEDBA1F4C2E9820B0D6C7BF994608E9C43BEAECF5C3BC`
