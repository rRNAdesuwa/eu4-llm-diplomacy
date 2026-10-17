# R45 主动议和与 NPC 拒绝

更新：2026-10-16。

当前运行快照为G：已载入修正后金钱拒绝存档，暂停于1455.1.5，英法仍交战。后续会话应从最新安装记录取得进程身份。

R45 首次通过统一接口合法发送法国（FRA）的主动议和请求，并在同一战争场景中取得白和平和索要金币两种请求的真实 NPC 拒绝。葡萄牙（POR）是游戏玩家，法国（FRA）由桥接接口控制，英国（ENG）由游戏原生 AI 控制。每次业务请求只发送一次；接口先查询当前战争和议和条款，再由原生规则决定是否投递以及英国是否接受。

本轮完成了完整参数提交、原生明确拒绝、拒绝结果保存和新进程恢复，并修复了原生分配外交官时的授权误拦。下一步取得实际接受结果，验收金币扣款、割省结算并扩展其他议和条款。

## 白和平：法国请求，英国拒绝

白和平请求使用 action_id=white_peace，参数为当前 FRA→ENG 战争、direction=demand、terms=[]。运行前的公开检查确认了战争双方、完整白和平载荷、原生合法性、通用动作条件、发送条件和执行授权。请求 r45a_fra_eng_white_002 只执行一次，A 阶段报告中的 17 项检查全部通过。

原生结果为 state=1、outcome=rejected。原生结果同时确认：

- war_before=true，war_after=true，英法战争继续；
- response_verified=true，request_binding_verified=true；
- execution_verified=false，terms_verified=false；
- submission receipt 的 submitted=true，transport_verified=true。

这里的 submitted=true 表示请求已通过传输并到达原生执行入口；英国随后选择拒绝，所以它不表示白和平已经生效。terms_verified=false 表示这次拒绝没有发生和约条款结算。

[白和平实际运行报告](../../work/runtime/diplomacy-query-20261016-r45-peace-a-outbound-war/public-outbound-white-002/report.json)保存了请求参数、原生 submission、原生拒绝响应和运行前后战争快照。该请求的日期原始值为 56545896，战争公开编号为 war_d43abc22498bb812_00000001。

## 拒绝结果保存与新进程重载

A 阶段保存了拒绝后的存档：

- 文件名：llm_diplomacy_peace_outbound_rejected_20261016_r45a.eu4；
- 文件 SHA-256：93ce805c48b72b2b828d251448203a4a4bb74fda82b2de1431dfe0e863301dab；
- 保存报告：[save-observer-report-1792153431809681700.json](../../work/runtime/diplomacy-query-20261016-r45-peace-a-outbound-war/save-observer-report-1792153431809681700.json)。

C 阶段把这份拒绝结果载入新进程，重新读取战争、外交官、日期和存档身份。第一次重载报告中 9 项检查有 8 项游戏实际状态核对通过；唯一失败项 source_unknown_preserved 是检查器把已经由原生明确判定为 rejected 的结果错误地当作 unknown。生命周期修正报告只修正了这个检查器判断，沿用了第一次重载的游戏快照和原始证据，没有重新发送请求。修正后的 9 项检查全部通过。

- [C 第一次重载报告](../../work/runtime/diplomacy-query-20261016-r45-peace-c-outbound-rejected-reload/outbound-rejected-reload-validation-001/report.json)
- [C 修正后的重载报告](../../work/runtime/diplomacy-query-20261016-r45-peace-c-outbound-rejected-reload/outbound-rejected-reload-validation-002/report.json)

重载结果仍为英法交战，拒绝后的保存状态与 A 阶段的原生 outcome 一致。这个结果证明拒绝状态、战争状态和保存对象可以在新进程中恢复；它没有证明接受结果或其他和约条款已经持久化。

## 索要金币：完整参数提交后仍被原生拒绝

D 阶段在同一战争类型中提交 demand_ducats 请求，请求编号为 r45d_fra_eng_money_001，金额为 10.0 金币，对应原生 amount_raw=10000。运行前检查确认金额条款复制到完整议和载荷，执行入口收到同一请求参数；17 项运行检查全部通过。

英国仍返回 native_state=1、outcome=rejected，war_before=true、war_after=true，terms_verified=false。因为对方拒绝，英国没有支付金币，法国也没有获得金币。该阶段只证明金额条款可以进入原生执行流程并得到明确拒绝，不代表金币结算已经完成。

D 阶段保存报告为 [save-observer-report-1792155632942986100.json](../../work/runtime/diplomacy-query-20261016-r45-peace-d-outbound-money/save-observer-report-1792155632942986100.json)。随后保存的业务结果存档 SHA-256 为 f58251c49883cbf57b5e4833e03bdb310936e3081fe986868a5f00b2a5e2cd41。金币实际结算仍需要对方接受的运行分支。

## 割省拒绝与 envoy 绑定修复：E/F 阶段

E 阶段提交了 `cede_province` 请求 r45e_fra_eng_province_001，参数为 FRA→ENG、`province_ids=[177]`、受益国 FRA。17 项运行检查全部通过；原生结果为 `native_state=1`、`outcome=rejected`，`war_before=true`、`war_after=true`，`response_verified=true`、`request_binding_verified=true`、`terms_verified=false`。这次拒绝没有改变战争、177 省份所有权或双方国库。

E 阶段保存报告为 [save-observer-report-1792156439078067900.json](../../work/runtime/diplomacy-query-20261016-r45-peace-e-handler-correlation/save-observer-report-1792156439078067900.json)，拒绝存档 SHA-256 为 `ff96ea7eea61a837157e5118ec1fabf3667396f94ea4be71e6cd69f6bf49e3c5`。有界存档对照 [r45e-province.json](../../work/runtime/peace-save-pair-20261016-001/r45e-province.json) 显示，FRA 与 ENG 的 `treasury` 均保持原值，177 省的 `owner=ENG`、`controller=ENG` 和 `previous_controller=REB` 均未变化；这些是保存前后序列化结果，不能单独归因于议和请求。

F 阶段使用加入 envoy 证明字段的新 DLL 再次提交 `demand_ducats` 请求 r45f_fra_eng_money_001。17 项运行检查全部通过；10.0 金币对应 `amount_raw=10000`，原生结果为 `native_state=1`、`outcome=rejected`，战争保持 `true→true`。F 阶段的 state0 handler 记录了 `response_scope_active=true`、`binding_consumed=true`、请求编号匹配、`native_envoy_verified=true`，当前 envoy 为 2，绑定载荷中的原始值为 `uint32(-1)`；root 同时核对了外交官管理器中的 ID、活动状态、双方、日期和 record，随后才调用完整 payload helper。helper 只对已证明的 `uint32(-1)→0..255` 情形归一化当前副本，双方、日期、方向和条款仍执行完整相等比较。

F 阶段的 NPC state1 handler 正常转发并产生 rejected 结果；同一 DLL 的无授权负例 [peace-authority-test-0536e8e1a5934f5885cf33e9d79e9928/report.json](../../work/runtime/diplomacy-query-20261016-r45-peace-f-native-envoy/peace-authority-test-0536e8e1a5934f5885cf33e9d79e9928/report.json) 20/20 检查通过。该负例没有 response scope、没有 consumed binding、`native_envoy_verified=false`、handler `allowed=false`，且战争、外交官、玩家和关系快照保持不变。这证明 envoy 归一化没有放开无授权的 FRA state0 入口。

F 阶段保存报告为 [save-observer-report-1792157108692696900.json](../../work/runtime/diplomacy-query-20261016-r45-peace-f-native-envoy/save-observer-report-1792157108692696900.json)，拒绝存档 SHA-256 为 `92dc5d57c2a293261381e1a776e9a4af44f77511e9f8b932a3b8695025e99478`。F 的 handler、提交回执和无授权负例来源核对见 [R45F handler source report](../../work/runtime/r45-peace-outbound-source-report-20261016-002/report.md)。

## R45 回归结果与当前状态

R45 合并节点运行了 341 项 Python 测试，结果为 `Ran 341 tests ... OK`；native authority ledger 编译并运行 399 项检查，结果为 `passed=true, failures=0`。F 阶段的 envoy 修复、正向拒绝和无授权负例已经独立核对，G 阶段随后完成了 F 金钱拒绝存档的重载。

G 阶段随后载入 F 保存的金钱拒绝存档，并在新进程中完成 9/9 项重载检查。报告 [money-rejected-reload-validation-001/report.json](../../work/runtime/diplomacy-query-20261016-r45-peace-g-money-reload/money-rejected-reload-validation-001/report.json) 确认当前日期原始值仍为 56545896、POR 仍暂停、英法战争仍在，重载使用的 DLL SHA-256 为 `31eaee779c162e50c73dff051a20ec53cfbdebc1aafa13cc824650a6edeb5f9b`。G 复用了 F 的拒绝存档 SHA-256 `92dc5d57c2a293261381e1a776e9a4af44f77511e9f8b932a3b8695025e99478`，没有重新发送金钱请求。

## 如何解释 R45 的原生日志

R45 的 handler 日志、submission 回执和 generic observation 记录写入了不同的日志路径。物理文件中的行号不能直接当作 native 调用顺序。

bridge_execution_execute 先捕获 generic command，并把记录放入观察队列。执行绑定消费成功后，桥接设置当前线程的 response scope，再调用原始 generic wrapper。原生 helper 0x4ea850 随后调用 Peace action 的 vtable +0x48 handler。handler 在 state0 场景写出拒绝记录；原始 wrapper 返回后，Peace submission 代码直接写出 submission receipt。generic observation 要等后续 frame tick 调用 observation_flush 才写入文件。

因此，line 209 的 state0 拒绝早于 line 211 的 submission receipt，具有源码上的调用顺序依据；line 212 虽然出现在文件中更晚，但它记录的是此前已经捕获、后来才刷新的 generic observation。R45 的物理行顺序不能说明 generic observation 在 handler 之后才发生。

[handler 顺序分析报告](../../work/runtime/r45-peace-handler-order-analysis-20261016-001/report.md)还指出，state0 handler 目前只记录了统一原因 UNAUTHORIZED_FRA_PEACE_OFFER，没有记录 response scope、binding slot、载荷比较结果和 handler 所在线程。现有证据可以证明 generic 入口和传输回执已经出现，同时证明 handler 没有继续转发；现有证据不能判断拒绝具体发生在 scope、binding 状态、载荷解析还是载荷相等性检查。后续 E 构建只增加这些私有请求、scope 和比较失败字段，用于区分原因，不会因为 submission receipt 存在就放宽权限。

## 本轮真正改变实现的检查

第一项是执行前公开检查。A-001 的原生合法性和三个动作条件已经为 true，但公开授权仍返回“执行适配器未实现”，脚本因此在发送前停止。这个检查发现的是公共能力投影错误，不能通过重跑游戏解决。修复授权投影后，A-002 才按完整白和平参数发送一次并得到 17/17 通过。

第二项是原生结果消费。A-002 的结果同时给出 native_state=1、outcome=rejected 和战争 true→true；消费端据此把请求标为 rejected，而不是等待 accepted 或把它写成 unknown。C-001 的重载检查曾把这个已知 rejected 结果误判为 unknown，C-002 只在既有报告上修正检查器语义，保留全部物理证据。

第三项是保存和重载。保存报告核对了存档路径、文件哈希和保存对象；C 阶段在新进程中再次核对战争仍在、拒绝结果对应的队列状态和运行身份。这个检查发现了持久化结果是否与原生拒绝一致，避免把当前进程内的结果误认为已保存。

第四项是日志顺序分析。handler 拒绝早于 Peace submission 回执，而 generic observation 属于延迟刷出的记录。分清这三种状态后，才能把“请求到达原生入口”和“handler 允许法国 state0 动作”分别判断；没有因此修改授权条件。

## 下一步

E/F 阶段已经把 handler 请求编号、response scope、binding 状态、envoy 证明和载荷比较结果接入真实日志；下一步是核对 F 金钱拒绝存档的 G 进程重载。当前仍需要完成：

- NPC 接受白和平后的战争结束、条款和保存重载；
- NPC 接受金币条款后的国库变化；
- 割省条款的实际选择、领土变化和保存重载；
- 其余 19 项常用议和动作及最终 LLM 循环。

R45 已经把主动议和的拒绝路径接到统一接口并完成真实回执与重载验证；这项结果不替代接受分支，也不替代金币和割省的后果验收。

## 金钱和省份后果的读取依据

原生金币执行函数已经对应到国家国库的增加和扣减，国库字段为国家对象的 `+0xbb0`，原始金额尺度为每金币1000。分配行直接决定哪个国家获得相应金额，付款国家由条款自身指定；分配权重的业务名称可以继续研究，现有调用关系已足以确定收付款对象。

省份读取改用有区分力的运行样本：263的所有者/控制者为SIL/HUN，349为TLC/TFL，350为MZB/TUN，177则均为ENG。同一暂停日期下，四个省份的原生ID和八个国家身份全部核对通过，确定本版本省份对象 `+0x468` 为所有者、`+0x470` 为控制者。后续结算结果可以直接比较这两个字段与保存文件。证据见[字段对照](../../work/runtime/peace-province-effects-probe-20261016-r45-003/report.md)。
