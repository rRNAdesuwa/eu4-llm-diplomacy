# 1.37.5 联姻、附庸的正常 AI 回复与只读观察

本报告只分析本机 `eu4.exe`，没有读取运行进程、调用原生方法、创建请求文件、控速或保存。适用 SHA256 为 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。所有地址均为 RVA；`runtime_verified=false`。

机器证据为 `work/reports/native-pair-replies-1375.json`，SHA256 `da3faa061af3d9ee8a3003412151594c6305b765afd8d739b4cb4a4759f63510`。生成器 `work/trace_pair_replies.py` 记录 45 个指定入口的有界控制流，并机械计算消息 vtable、固定消息类型分发表、动作虚槽和 server 虚槽。每入口最多 16 KiB / 4,000 条指令；不自动跟随调用；内存保护 768 MiB。

```powershell
python work/trace_pair_replies.py --deps-dir "$env:TEMP\eu4-native-analysis-deps"
```

## AI 回复不在这条路径中等待下一天

`4e7c50` 是外交 command 的执行方法。它先调用派生动作的合法性 `+0x80`，在 `4e8054` 结算初始 action；只有 `action+0x34==0` 且 `+0xd0` 表示需要回复，才进入下列分流。

| 条件 | 本入口的行为 |
|---|---|
| `game+0x1d48..+0x1d50` 控制数组非空，target slot 的 DWORD 为 0，且 `2cd570(target)` 为真 | 当场 clone、调用 `+0xb8` 判断 AI 接受，写 reply state、构造 command，再排队提交 |
| 控制数组为空，或 target slot 的 DWORD 非 0 | 尝试加入 recipient 的待回复队列 |
| 控制数组非空且 target slot 为 0，但 `2cd570` 为假 | 本入口不生成回复，也不转入人工队列 |

第一条分支 `4e819b→4e81c1→4e81d0→4e81e7→4e81ed` 没有日期、到达时间或暂停状态的判断。它属于初始外交命令执行的同步工作，不是等待日/月 AI 更新后才评分。但评分后产生的是**另一条排队命令**，所以静态证据不能保证同一帧接受生效，也不能独立证明暂停时命令泵的调度。已经暂停时，应先等待正常帧并观察结果，不必为了这段 AI 评分主动推进一个月。

回复命令的 gate `4e8630` 在 state 非 0 时跳过初始外交冷却比较（`4e8646/4e864a`），但仍调用派生合法性。执行入口也再次校验。因此“评分接受”与“接受效果已应用”是两个阶段：局势变化可能使回复执行不再合法。用户新请求必须保持 state 0，不能填 state 2、force 或作弊字段代替正常回复。

## 原生 AI 开关与评分

`2cd570` 要求 `country+0x3d0` 非空，再调用 `b52e0`。后者逐项要求：

1. 该对象 `+0x80` 的 BYTE 非 0；
2. 使用对象 `+0x20` 的国家 handle 查 country array；
3. 所查国家 `+0x2458` 对象的 BYTE `+0x18` 为 0；
4. `game+0x74d0` 的 BYTE 非 0。

这些是可复核的读取路径；本报告没有给尚未独立证实的字段起更强的业务名称，也不写入这些字段。`target != current_player` 不能替代上述控制映射与谓词。

两种动作的 `+0xb8=4ea1e0` 都调用 `+0x120`，按有符号整数 **score >= 1** 接受。联姻的评分是 `4f0bf0`；附庸 `51fab0` 委托 `38e6e0`。评分函数同时有可选的 `game+0x23a1` / 当前玩家特殊分支，返回 99999；正常实验不得依赖或启用它。

两种动作的 `+0xf0` 均为恒 false 的 `8f450`，所以正常路径进入上述评分，并不选择通用执行器中的无条件接受分支。联姻 `+0xd0` 返回 value，附庸返回 `state==0 && value`；正常取消模式无需 AI 同意。

联姻评分中可定位的原因标签包括 opinion、attitude、文化组、宗教、宗教学派、相邻国家、统治者特质、外交声誉、边界距离。附庸评分还包括核心省份、已有附属国、交战、臣属身份、贸易城市、无省份、已有联姻、经济/军事实力、政府等级、教宗/皇帝/选帝侯/自由市/HRE 和信任。报告保留这些具体标签与函数指令，但没有把它们拼成未经验证的独立评分公式。通用合法性预览通过不代表 AI 愿意接受。

## 待决队列与 ID 的边界

recipient country 的字段：head `+0x18d8`、tail `+0x18e0`、DWORD count `+0x18e8`、迭代 BYTE `+0x18ec`。节点大小 `0x20`：action `+0`、previous `+8`、next `+0x10`、deleted BYTE `+0x18`。

人工/待处理分支在 `4e82a4` 申请请求 ID，写入 action DWORD `+0x3c`；`+0x2c` 写当前 rawdate。一个合法、未删除且 state 0 的匹配节点可以报告 `pending_observed`。应同时记录 action vtable/token、完整 actor/originalActor/target handle、value、envoy ID、两个日期字段和请求 ID。

直接 AI 分支在申请此 ID 之前已经返回，因而 AI 回复的 `+0x3c` 可以仍为 0。不能把“缺少非零 ID”或“不在人工待决队列”视为 AI 没有处理。

`360970` 根据 ID 清理队列，**先析构 action**；若迭代标志非 0，只把 node deleted 置 1，action 指针仍可能留着。因此已删除节点绝不能再解引用 action。`3607c0` 还会清理不合法或已不再待决的动作，`3608d0` 能清空整条队列，均不证明拒绝。

另有 `2ee280` 的有界清理路径：`game+0x7484!=0` 且控制映射 slot 为 0 时，比较当前 rawdate 是否**严格大于** `action+0x2c + 72`。`cf4e0` 明确计算 `3 × 24`，即三个原生日期单位的天数；超出时直接析构并移除队列节点，没有写 state 1，也没有发拒绝通知。本报告未证明该大函数的完整调度频率，不能把此路径当作所有人工请求统一超时规则。

## 接受、拒绝通知提供另一条只读证据

联姻 effect `4ed640` 在 `4edb77/4edb7a` 区分 state 2；`4ee7e4` 区分 state 1。附庸 `51d810` 对应 `51dce2/51dce5` 与 `51e195`，并检查 value。它们构造以下确切消息 key：

| 类型 | 原发起国视角 | 收件国视角 | 第三国视角 |
|---|---|---|---|
| 联姻接受 | `ROYMARACCEPT` | `ROYMARWEACCEPT` | `ROYMARACCEPTOTHER` |
| 联姻拒绝 | `ROYMARREJECT` | `ROYMARWEREJECT` | `ROYMARREJECTOTHER` |
| 附庸接受 | `VASALLACCEPT` | `VASALLWEACCEPT` | `VASALLACCEPTOTHER` |
| 附庸拒绝 | `VASALLREJECT` | `VASALLWEREJECT` | `VASALLREJECTOTHER` |

原发起国视角的判断比较 action originalActor `+0x18` 与当前观察国家。以拒绝为例，联姻在 `4ee8ad` 选 key，`4ee902` 构造消息，`4ee90d` 分派；附庸对应 `51e25f/51e2ab/51e2b6`。这比“关系没有生成”提供了明确的拒绝分支证据。

构造 `8d4660` 与移动 `1af350` 确认消息字段：

| 对象 | 字段 | 宽度 |
|---|---|---|
| message | `+0x08` 类型定义指针 | QWORD |
| message | `+0x28` actor 完整 handle | QWORD |
| message | `+0x30` target 完整 handle | QWORD |
| message | `+0x88` rawdate | DWORD |
| definition | `+0x38` 消息 key | EngineString32 |

普通消息的 vtable RVA 为 `0x1c426e0`，带回调的历史消息派生类为 `0x1cc1ca0`，由报告中三处 RIP 相对 LEA 独立计算。字符串仍按内联容量 `<16`、否则首 QWORD 指针的有界 String32 规则读取，检查 length/capacity/NUL，不调用名称解析方法。

## 最近 200 条消息历史的读取路径

在已核对 `game+0x1e00` server vtable `0x1cb8460` 的条件下，虚槽 `+0x228` 指向 `80e670`：它要求 `server+0x1178` 非空，然后从 `server+0x12d0` 取 history manager，调用 `1241af0` 添加消息。观察器可以沿字段直接读取，**不调用虚方法**。

| history manager 字段 | 含义 |
|---|---|
| `+0x10` QWORD | head |
| `+0x18` QWORD | tail |
| `+0x20` DWORD | count |
| `+0x24` BYTE | 正在迭代/延迟移除的标志 |

节点大小 `0x28`，字段为 message `+0`、共享所有权控制对象 `+8`、previous `+0x10`、next `+0x18`、removed BYTE `+0x20`。`1241af0` 通过共享所有权保留消息，并在正常插入后把历史限制为 200 条。观察器不能改引用计数，也不能释放任何对象；已移除节点应跳过消息解引用。

消息历史有过滤条件。`8c07b0` 会检查特殊观察模式、server、handler `+0x48`、game `+0x74e0` 以及消息设置；只有设置 `+0x11` 为真才走历史插入。弹窗与自动暂停使用另一些设置字段。因而通知可能被关闭，旧节点也会被 200 条上限淘汰；缺失不是拒绝或接受的证据。

这条消息结构没有已确认的原生外交请求 ID。新出现且 key、完整国家对、日期窗口匹配的消息可报告 `reply_notification_observed`，标注 `correlation=pair_type_date_new_node`。不能声称它具有逐请求 ID 的严格归因，也不能用已有的同日历史消息验收新的实验请求。

## 下一步可编码的验收

1. 在暂停、同一已绑定会话中，发送前记录关系索引、待决队列和消息历史基线；检查链长、前后指针、count、完整 handle、类型与 removed 标志。若不能在同一稳定帧读取，要求重复快照一致；不一致保留 unknown。
2. 发起正常 state 0 的联姻或附庸，先继续观察暂停帧。初始预览通过只说明合法性，transport 确认只说明已分派。
3. 匹配待决节点记录为 pending；新增拒绝 key 记录为回复通知已观察，并附上匹配层级。没有匹配事件时保留 unknown，不从空队列或外交官返程倒推。
4. 新增接受通知仍需与关系状态核对：联姻为双侧婚姻索引同一活跃对象；附庸还需 dependency 类型、宗主/附庸方向及 target.overlord 字段一致。保留发送前不存在、发送后出现的证据。
5. 若之后需要推进时间，只使用另行审核的有界测试控速；本静态报告不授权或实现控速、强制 AI 回复、改 message settings 或新的 hook。

## 只读研究探针

`work/probe_diplomacy_replies_1375.py` 已实现上述消息历史观察，固定 FRA→ENG/POR，打开进程仅使用 `QUERY_INFORMATION | VM_READ`。采样先核对实际进程路径、完整 exe SHA、PID 创建时间、完整国家 handle、server vtable 和历史转发函数前缀，再做两次完整且一致的快照。每轮严格限制总节点 512（含 removed）、活动消息 200、消息 key 96 字节；removed 节点绝不解引用 payload，未知消息 vtable 只记录身份。

显式采样与离线比较命令：

```text
python work/probe_diplomacy_replies_1375.py sample --pid <PID> --target both --output work/runtime/reply-before.json
python work/probe_diplomacy_replies_1375.py sample --pid <PID> --target both --output work/runtime/reply-after.json
python work/probe_diplomacy_replies_1375.py compare --before work/runtime/reply-before.json --after work/runtime/reply-after.json --action royal_marriage --output work/runtime/reply-comparison.json
```

输出文件必须不存在；不会覆盖已有证据。比较器重新验证原始快照，不直接相信保存的状态摘要。只有在同一进程创建身份、同一完整国家身份和历史根，日期单调且采样时间不重叠时，才比较新增消息。匹配还要求 node、message、shared owner 三个地址均未出现在基线，消息日期位于前后窗口。结果是 `accepted_correlated` / `rejected_correlated`，`applied_verified` 和 `request_id_causality_verified` 始终为 false。无新通知、复用的地址或不一致快照均保留 unknown；双 pass 不能排除 ABA 指针复用和同进程读档。

2026-10-08 的一次明确授权基线保存于 `work/runtime/reply-baseline-45564.json`，SHA256 `68a7ad74c936b784474d0ab11db6813a3814fc0e5df4bef61c14a02766858b12`。PID 45564、创建 FILETIME 134358597615871159、rawdate 56457744，两轮一致，200 个活动消息，已知消息 vtable 全部匹配，所选国家对的回复 key 匹配数为 0；读取总量 23818 字节。此结果验证了该次历史遍历，不证明发生过接受或拒绝，也不提升全部协商动作的运行验证状态。

`python -m unittest bridge.tests.test_diplomacy_replies_probe -v` 的 17 项纯 mock 测试覆盖全部 12 个 key × 两个目标、边界 512 removed 节点、超限与坏链、未知 vtable、字符串边界、双 pass 差异、身份变化、时间窗口以及离线证据篡改。测试本身不读取游戏进程。
