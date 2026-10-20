# v19 五间谍固定发送研究计划（仅静态合同及纯模型）

这不是发送器。此目录没有 C++、DLL、进程读取、加载器、请求文件发布器或实际日志验收器；`model.py` 的返回值只表示合成状态转换。v18 的原协议、三阶段 core、Host、DLL、reader 和 client 全部保持封版，**v18 仍只允许无发送测试**。本候选没有读取任何本次 v18 实际会话，不能假定它已经通过。运行、效果、生产能力始终为 false。

## 建议的最小新边界

新名称 v19；建议未来 DLL `eu4_spy_send_lab_1375_v19.dll`，私有协议 `EU4SPYSEND/1`、journal `EU4SPYSENDHOST/1`。不得将 v18 的 `send_supported=false` 原样事件改解释为允许发送，也不得热改已加载模块。必须新冷进程、新 session、新 EXE/DLL/manifest/导出钉扎、完整 held PID/创建时间、一次安装以及正常 owner hook；不得借旧 PID、旧阶段日志或仅相同世界地址重获权限。此处没有未来 DLL SHA 或导出 RVA，任何实际实现仍待独立审查和 root 授权构建。

在同一个未来 v19 会话完成三个显式无发送阶段（5 lifecycle / 5 full-family-preview / 5 owned-command），各有永久独占 claim、完整 core 返回、持久 Host wrapper 和更晚真实 owner-call 的健康帧。合法性 false 是完成检查的正常结果；它不授予发送。新的第四次显式请求仅有一个 `submit_fixed_spy5` 操作、sequence=4，内部按下表尝试一次。使用和前三阶段相同的暂停日期、线程、世界根、完整 FRA 玩家/actor 与 ENG target。fixture、speed、yesman、任意脚本、额外 TAG、金额和 raw 地址均不在协议中。

| 次序 | 家族 | token | action vtable | 完整预览 +88 | 效果 +48 |
|---|---|---|---|---|---|
| 1 | corrupt_officials | 337c | 1c7c4a8 | 582730 | 581ac0 |
| 2 | sabotage_reputation | 2ddd | 1c7cfd8 | 57e900 | 57ddc0 |
| 3 | sow_discontent | 2ddf | 1c7c9e8 | 585020 | 5844e0 |
| 4 | slander_merchants | 337b | 1c7c378 | 580260 | 57f6e0 |
| 5 | sabotage_recruitment | 33bf | 1c7c5d8 | 581450 | 5808d0 |

actor fullhandle 固定 `0100007a00415246`，target `0100002e00474e45`。先解析当前完整 country 身份、generation、lookup count 和 exact vtable，不能只接受 slot/TAG。每个 0x40 action 都由 `35d210(token,null)` 构造；不是栈字节伪造，也不接受用户参数覆盖构造器。正常 AI 证据支持 actor+10/original+18/target+20、当前日期+28/+2c、envoy+30=-1、state+34=0、value+38=1、flag39=0、id3c=0。五项 setter 是 `4e99d0(action,true)`；四项先前缺失的正常调用者已由后来的 sealed normal-callers 报告闭合，不再沿用旧报告的未完成标记。derived_fields 均为空，但 padding 不是合同。

## ABI、转移与真正消费

以下均为 Windows x64 静态签名；地址只在私有源码常量中使用：

1. `void* Factory(uint32 token, const void* definition=null)`。全字段/marker/vtable/固定默认值通过后，才认为返回原件独占可写。null/sentinel/错类、分配异常都停止，不猜内部是否已经分配。
2. `bool FullPreview(action, void* reason=null, bool skip=false)` 调家族 **+88**。不能只调用 generic `4e9d00` 或 +80；完整检查还有各自 capability byte。它可能初始化定义、TLS 或运行脚本，并非只读查询。
3. `void** Wrapper(action, void** out)` 地址 `4e9930`，out 初始 null。返回值必须等于输入 slot 地址；command 独立 size58/vt1c814b0/type2934，+50 是独立 clone；clone 与 source/command 均不别名。clone 的 +2c 被包装器重写为当前日期。原件仍由调用者拥有。`bool Gate(command)` 为 command+40=`4e8630`，也必须执行。
4. 未交接时 `DeletingDtor(command,1)` 地址 `4e7470` 负责其 clone；clone+a8=false。绝不能另析构 clone。原件独立 `129450(original,1)`。先正常析构原件、确认返回并清掉自己所有权，再保留仅 command 的唯一所有权。
5. 建议沿已研究 v17 的 `bool ContextSubmit(context, void** owned_slot)` 地址 **14ca210**。它在 `14ca22a/22d` 先取走并清 caller slot，再检查 transport/readiness，故 false 或异常不等于归还所有权。进入调用前即停止认为 command 为本方所有；进入后绝不读取/析构旧 command/clone，不自动重试。只有正常返回、AL=true、caller slot=null 同时成立才记 `dispatched`；其余都 `dispatch_unknown`，永久冻结。
6. **14ca2d0 的 ABI 不同**：`bool(context, void* command)`，直接收对象指针，没有 caller slot。普通 subject UI 使用它；不可向它传 `void**`，也不可拿其 early false 行为解释 14ca210。本候选不选择这条入口，亦不直接调用 world-submit bfe50 或原生 consumer。

context 的计划钉扎复用 v17：game+1e00→server vt1cb8460；server+330→holder+370→context；context+58→transport vt1d96178 / +30=1580370；context+55 或 +80d 非零。最终日志持久化后重新核所有链、完整 actor/target/player、日期和本次唯一线程，再紧邻调用核 guard。它只证明本次选定根一致，不证明 world epoch 或严格单机来源。

type2 transport `1580370(transport, owned_command)` 正常路径序列化/重建/入队，最终在 1580c4a..5a 删除原 command。`15801c0` 是 drain，不是 submit；不主动调用它推动“立即生效”。本轮新增有限解码闭合正常消费链：

- transport+48=`8b0e0` 返回 transport+c8；context `14ca870` 取队列，转入 context+140 指针向量并释放链节点。
- `14cab30` 再次调用 command+40；不通过不会走正常 execute 路径。通过后建立栈 callback，vt1d8c8b0、+8=command、外层 std-function 容器+38 指向该 callback。这里 rbp=rsp+100，故 `rbp-78` 是容器 `rsp50+38`，不可误读成对象自有 +38。
- `14d4e70→14d4e30→10a0f20` 调 callback+10=`14cea10`，最终尾跳 command+48=`4e7c50`。`14d4e30` 的递归计数来自原生 instrumentation，完整最大值与异常展开未证明；设计不直接调用它。
- 消费正常结束后 `14cb13b` 由引擎删除所消费的 command。此对象可能是传输重建后的副本，不是已删除的原 command，不能用地址相等连接两者。

`4e7c50` 重新检查 action+80(NULL,false)。五族 +100/+f8/+d0 为 false、+108 为 true：普通同国日期冷却/外交官派遣/等待 AI 回复分支不适用。**这不等于没有其它 gate 或发送后一定成功。** `4ea820` 在 actor/target 的 +1344/+26 条件允许时调用 action+48；五个效果函数写 target timed modifier 并调用脚本/重算路径，费用另由 relation WORD+18 与原生算法扣除。效果对象没有本次请求 ID/actor 归属。消费时余额或合法性可能变化；按初始余额预判五项全部会成功不可靠。

## 一次批次、所有权及日志合同

初始与最终各采一次已审五 spy full RO census；中途只做执行所必需的身份/guard/全合法性/对象合同检查、命令日志和健康检查，不逐项采效果。每个 family 占一个更晚的实际 owner frame，最多每帧一项；不能由工具递归/异线程或伪造 frame ID 驱动。暂停固定日期，不内置推进天数；给正常引擎队列处理机会，但更晚帧本身不证明队列已消费。

batch claim 与五个 item claim 使用 session 私有固定文件名/索引和 CREATE_NEW 全长写入+flush，永不删除或重复认领；任何 native allocation/preview/wrapper 之前必须已有该项 claim。收到错误请求不发布文件；认领后的到期/guard/audit/SEH 不补发。每项调用之前复核 `now < expires`；claim 限 `now < expires <= now+60000`，全局 uptime/frame 非递减。正常返回后的已知所有权清理可越过 TTL，世界/线程检查不豁免；下一项不得越期启动。

日志新 schema 必须记录固定 family/token/value/state/envoy、完整 stamp、batch/item ordinal、独占 claim 内容 SHA、source/original/clone 的私有对象序号、native call intent/entered/returned、allowed nullable、原件/命令清理、submit bool 与 slot-consumed nullable、异常、freeze，以及持久 logger 成功状态。intent 不能冒充 entered，callback 内事件不能冒充最终 Result；最终 Host wrapper 必须在 core 返回后持久化，随后较晚真实健康帧才可继续。审查器须解析所有 owner-call 行，未知/错误行不跳过；不得复制 v18 no-send 模型并删掉禁止发送断言。

只有 full preview false / command gate false 且所有已知对象正常清理，才是可继续下一项的已知合法性拒绝。其余未知对象布局/alias/异常、context 缺失、最后 guard 拒绝、logger 失败均停止该批并冻结；不猜清理，不重新构造。提交前 context 缺失而仍能证明 command 所有权时，未来实现可做一次已知 dtor 后冻结，本最小模型没有实现这条优化。五项尝试完成不等于五项已发送；摘要分别列 `full_preview_rejected` / `command_gate_rejected` / `dispatched` / `dispatch_unknown`，中断后未尝试项保持未尝试。

## 观察与未决条件

最终选择状态只在第五项已知结局及更晚健康帧之后采样。若批次冻结，可由独立只读诊断采样器另采 forensic 记录，不把它当正常批末通过。只报告五个 modifier 的类型、定义、expiry 以及网络余额/dense cost 快照；选定总余额变化不是单项因果，也不假设累计费用固定 78,750。UI 批次历史与 v17 其它动作历史不能替新 v19 请求提供 runtime 效果证据。没有 queue settlement/时限证明；如果末帧尚未出现 modifier，只能 unknown/未观察到，不能补发或强迫 drain。

开始任何实际研究前仍缺：v18 当前真实三阶段独立验收；新的 v19 全源/pins/导出/冷进程装载；sender mock 与真实 core 所有权测试；新增 native/Host/outer journal 的全流水线审查；v19 自身三个前置阶段；批次初始身份、定义、网络余额及允许使用的可丢弃测试存档授权。没有可靠 epoch、全路径加载锁、严格 SP 或完整 unwind 证明，均不能提升为 production。

## 文件范围和复现

`report.json` 重用旧 evidence 并逐条核对 exact EXE；新解码 2,718 B，8 个入口，每窗 8 KiB，总预算 48 KiB。四份 exploration 包含全部新增探索，无 whole-disassembly 或递归扩散。`contract.json` 是未来实施门槛，`model.py` 只是抽象状态模型，不读取真实日志或认证传入的 phase 布尔值。未来 actual reader 必须另实现，不得把模型当正式 verifier。

本候选只有标准库模型，不导入、不新建长期 hash gate 指向 `bridge/diplomacy_api.py`。旧 v18 元数据作为历史来源记录，不递归用其中旧 API pin 约束未来源。如果实现需要旧通用 validator，应把所需的已审核精确 preimage/窄定义复制到 versioned v19 私有目录并重新审查；不修改旧 pin，不把可变公开 API 变成研究 DLL 永久依赖。

```powershell
python -B work/candidates/v19-spy-send-plan-1375/prepare.py --check
python -B work/candidates/v19-spy-send-plan-1375/evidence.py --check
python -B -m unittest discover -s work/candidates/v19-spy-send-plan-1375 -p test_model.py -v
```

`validate.py` 仅将这些离线命令输出封存到新的 validation 目录；它不构建或调用游戏。
