# EU4 1.37.5 统一外交操作接口

全部行动使用 `{request_id, action, parameters}`，沿用当前 cold product 的同一个 owner、请求队列和证据台账。

| 操作 | HTTP 路径 | 输入/输出 |
|---|---|---|
| 全部行动 | GET `/v1/actions` | 原生路由、参数、条件、候选与效果合同 |
| 单行动 | GET `/v1/actions/offer_loan` | 对应行动合同 |
| 参数查询 | POST `/v1/diplomacy/query` | `{request}` → 标准化请求与合同 |
| 原生预览 | POST `/v1/diplomacy/preview` | `{request,ttl_ms,allow_writes:true}` → 队列结果，再读取 status |
| 效果基线 | POST `/v1/prepare` | `{request}` |
| 执行 | POST `/v1/production/requests` | `{request,ttl_ms,allow_writes:true}` |
| 状态 | GET `/v1/requests/ID` | 当前派发/原生状态 |
| 响应 | GET `/v1/requests/ID/response` | generated_decisions、pending、reply、generated_send、effect、证据路径 |
| 效果 | GET `/v1/requests/ID/effects` | 所选字段的 before/after 与进展 |
| 合并结果 | GET `/v1/requests/ID/outcome` | 同一请求的响应与效果证据 |

参数查询是纯源码/codec 校验；当前世界条件由原生执行门控处理。`native_preview=true` 的行动仅当**当前加载 build 的 `build.json` 声明 `no_send=true`** 时使用 send=0 预览；build 未接通 send=0（如 build15 `no_send=false`）时工具在发布前拒绝并保持 owner 可用。特殊 typed 路由返回 false。预览与正式执行使用不同 request_id，效果基线使用正式执行 ID。

目录直接来自 UnifiedDiplomacyAPI，覆盖普通经济/贸易/外交/间谍行动、当前战争、属国/殖民国、幕府、租兵、卖船、支持叛军、朝贡回复和总督选择。参数字段按各自 codec 提供，支持叛军和停止支持等不同载荷分别列出；effect_profile 从现有效果定义读取，包含所需状态和原生回执字段。

例如贷款参数查询：

```json
{"request":{"request_id":"loan-query-001","action":"offer_loan","parameters":{"actor":"FRA","target":"SAV","amount":100,"interest_percent":"2.000","duration_months":12}}}
```

查询返回的 `conditions` 用于选择真实测试对象；`candidates` 对应 `/v1/candidates` 的查询种类。省份、舰队、叛军派系和战争都从当前游戏候选取值。教廷行动使用实际 Curia controller，属国交互使用当前类型能力和真实依附关系。

响应中的 AI 决定、回复传递、执行和效果分别保留。人类朝贡回复通过 `confirm_tribute_action` 的 `accept` 参数执行；总督选择通过 `event.choose_governor_option`。吞并/合并等持续行动在 effects/outcome 中读取进展。

本轮静态接入和后续测试清单见 `work/reports/diplomacy-unified-20261028/HANDOFF-DEEPSEEK.md`。
