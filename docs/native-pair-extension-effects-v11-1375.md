# v11 候选的只读观察与离线比较

工具：`work/probe_pair_extension_v11_1375.py`，独立 profile `1375_pair_extension_observation_v11_1`。只支持固定 FRA→ENG/POR/NAV/FOI。没有修改 v10、原生源码、DLL 或外交目录；本次只运行伪内存测试，没有访问游戏进程。

静态增量生成器：`python -B work/trace_pair_extension_effects_v11.py --check`。报告 `work/reports/native-pair-extension-effects-v11-1375.json` SHA256 为 `aa93b84c2ae1af3652134b49c80453aabfb4a51006e4ec20b9c6c7196eb1888a`。它固定父报告 SHA `ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344` 和 exact 1.37.5 PE SHA；新增 4 个函数，解码 469 字节，运行状态仍 false。

## 可观察项

| family | 读取/校验 | 比较能报告什么 |
| --- | --- | --- |
| warningaction | 双方 `1b8/1c4` 索引、vt `1c7fca0`、actor/target 完整 handle、marker、removed、start | 新增 FRA→目标的警告；反向警告单独报告，**不支持 cancel 比较** |
| form_coalition | FRA `18f8` 完整目标 handle；目标 `1910/1918/1920` 有界双向链表 | 目标绑定和成员节点都新增/移除，才报告 selected membership 改变 |
| support_independence_action | 双方 `170/17c`、vt `1c80570`、完整国家对 | selected pair 支持条约新增/移除；报告对象 field order，**不从顺序推断支持方权限** |
| transfer_trade_power | 默认 FRA receiver `248/254`、目标 supplier `230/23c`；vt `1c571f0`；方向、`+40` 比例、`+44` 标志 | 普通零标志条约新增/移除；可要求精确比例 |
| steer_trade | 默认 FRA beneficiary `278/284`、目标 `260/26c`；vt `1c7d498`；方向、`+40` 标志 | 普通零标志条约新增/移除 |
| giftaction | 两国 treasury `+bb0` 和双向关系 favors `+20` | 相同 raw date、显式预期金额、精确相反国库变化且人情不变；**不是单边余额推断** |
| trade_favors_for_gold | 同上；扣人情位置必须是目标针对 FRA 的 record | 相同日期、显式预期金币/人情成本、目标付款/FRA收款、人情正确方向扣减完全一致 |
| insultaction（普通 -1） | 不读取尚未闭合的 modifier/CB 布局 | `unsupported`，且 sample 分支不打开进程 |

所有数值偏移为十六进制。贸易提供 `--trade-direction target_to_actor`（默认）或 `actor_to_target`，两者使用相反的实物索引并核验相应对象顺序。前后报告 flow 必须相同。FRA 发起的正向原生操作只对应 `target_to_actor`；反向状态可采样、可核验取消，但拒绝作为 FRA 同 family 的正向效果。非贸易行为拒绝此选项。特殊标志为 1、比例不在保守普通范围 1..1000 时只报告特殊状态，不能通过普通效果比较。

支持独立的对象保存最初 proposal actor/target 顺序。已审效果允许独立国提供支持，也允许依附国请求支持，因此将存在条约解释为“FRA 一定是支持者”会产生错误。这个工具只核对所选国家对的条约；未来发送 host 仍需独立验证当前 overlord、dependency definition、发起权限和合法性。

## 新静态字段依据

`a6a150` 明确以 root `1b8/count1c4` 检查警告，再比较关系 `+18` 和 counterpart。观察器使用完整 handle、已知 relation vt 和 marker `0x165`，比原生 getter 的 slot 比较更严格。

`df1a0` 是包围网列表移除 helper：当 list `+14`（country `1924`）非零，仅把 node `+18` 标为 1，不摘链也不减 count。因此 count 包括待移除节点。观察器遍历这些节点的有界链接，但不解析 marked 节点的国家；有效成员另须有完整 country identity 与同一目标的 `18f8`。循环、重复有效成员、prev/next/tail/count 不符、选中国家和列表互相矛盾均返回 unknown。

`3383b0` 有 `ChangeTreasury` 原生诊断名，在 `338419/33841f` 对国家 DWORD `+bb0` 加算并写回，随后限制在 ±1,000,000,000 native 单位。赠款 `money` 的 `×1000` 参数经 AddExpense 取负及 AddIncome，直接到此 helper，故读取单位是千分之一金币。

人情换金币 `4f4927..4f4976` 取目标国、actor slot、`country+1510` records，并经 `c9cc0` 计算 `records+slot*0x48`；`a658d0` 在 feature 条件通过时从 DWORD `record+20` 扣减，限制到 0..100000。cost 表达式把人情数乘 1000，所以字段单位是千分之一人情。两遍采样不能代替该 feature gate 或接受状态；未出现扣减时不会判为通过。

## 命令

以下为供宿主后续显式运行的模板；本次未执行 sample。

```powershell
python -B work/probe_pair_extension_v11_1375.py sample --pid $targetPid --target NAV --action warningaction --output work/runtime/v11-warning-before.json
python -B work/probe_pair_extension_v11_1375.py sample --pid $targetPid --target NAV --action transfer_trade_power --trade-direction target_to_actor --output work/runtime/v11-trade-before.json
```

每次效果操作前后分别另存两份报告，再离线比较。输出使用新文件，已有文件拒绝覆盖。

```powershell
python -B work/probe_pair_extension_v11_1375.py compare --before work/runtime/v11-warning-before.json --after work/runtime/v11-warning-after.json --direction positive --output work/runtime/v11-warning-compare.json
python -B work/probe_pair_extension_v11_1375.py compare --before work/runtime/v11-trade-before.json --after work/runtime/v11-trade-after.json --direction positive --expected-fraction-milli 500 --output work/runtime/v11-trade-compare.json
python -B work/probe_pair_extension_v11_1375.py compare --before work/runtime/v11-gift-before.json --after work/runtime/v11-gift-after.json --direction positive --expected-amount-milli 25000 --output work/runtime/v11-gift-compare.json
python -B work/probe_pair_extension_v11_1375.py compare --before work/runtime/v11-favors-before.json --after work/runtime/v11-favors-after.json --direction positive --expected-amount-milli 30000 --expected-favors-milli 10000 --output work/runtime/v11-favors-compare.json
```

经济命令中的 25 金、30 金和 10 人情只是单位示例，不是硬编码 native 金额或当前游戏观察。`trade_favors_for_gold` 的金额由 native helper 计算；外部预期值必须独立确定，不能用后报告差额反填再声称匹配了请求参数。取消用 `--direction cancel`；警告、赠款、人情换金币和侮辱没有在本工具中提供伪造的撤销语义。

## 有界原生候选建议（尚未构建）

下一份研究宿主可以只允许这八个既有 token，actor/target 仍限已验证完整身份。建议首批只研究警告 true、普通侮辱 true 且 index 固定 -1、包围网 true/false、支持独立 true/false、贸易权 true/false 且比例固定 500 / flag0、转移贸易 true/false、赠款 true 且金额固定 25000、人情换金币 true 且不接受 caller 金额。不要把所有 family 自动扩成正反两项。

每类先做 factory/clone/preview/command 阶段。贸易取消绑定具体对象、full handles、start、方向和普通标志；包围网取消必须绑定现有目标且列表匹配；支持独立取消另核当前依附权限。侮辱虽可做生命周期研究，但在 modifier/CB 观察器补齐前，不应将真实提交列为效果闭合。人情换金币的经济期望金额/成本需要独立前置来源；不能把 core 已有原生返回值或此工具的余额差额当作 AI 回复。

## 验证与限制

`python -B -m unittest bridge.tests.test_pair_extension_v11_probe`：17 项通过，覆盖五类关系与四目标、贸易方向和比例、反向贸易正向比较拒绝、普通/特殊标志、包围网 deferred removal 和双向链表损坏、full-handle generation、错误 vt/marker/removed、读取预算、两遍波动、经济单位/方向/日期、unsupported 不开进程，以及离线 CLI 拒绝覆盖。生成器 `--check` 字节一致；独立逐项核对新增及引用锚的 162 条指令字节与 exact PE 相同。

sample 沿用已审 full EXE SHA、PID/进程创建时间、loaded PE identity、只读权限和总/单次读取预算。每次完整采样前后检查 roots、player 和 pair，连续两次完整结果必须一致。列表最多 1024 节点，关系索引最多 4096 条。compare 重新验证原始两遍与 stored state，核对 profile/evidence hash、同进程、完整 handle、roots、时间顺序和非倒退日期；经济额外要求相同 raw date。

这不是原子快照或可靠 world epoch。`observed_effect=true` 只表示所选状态转变或精确预期经济差额；请求因果、AI 接受、生产执行、全世界不变全部保持 false。absence/unknown/unsupported 不代表拒绝。未进行游戏实测，也未借用 v10 历史结果。
