# 机器可读的外交能力分层

研究 CLI 提供完全离线的 JSON 能力说明，不要求 PID，不打开游戏、不启动服务、不创建 API 数据库或请求文件：

```text
python tools/request_diplomacy_lab.py capabilities
python tools/request_diplomacy_lab.py capabilities --research-only
python tools/request_diplomacy_lab.py capabilities --action improve_relations
python tools/request_diplomacy_lab.py capabilities --action control.speed
python tools/request_diplomacy_lab_v7.py capabilities --action royal_marriage
```

默认列出当前动作目录中的全部 274 项。`--research-only` 返回与研究入口有关的37个目录条目及单独的速度控制；`laboratory_protocol_action_ids` 精确列出36个协议ID。两种计数不能相加：`request_trade_power` 导航到目录 `transfer_trade_power`，`cancel_independence_support` 导航到两种按角色区分的目录取消动作，并不证明两种角色都通过实际测试。`--action` 支持目录ID或这两个明确研究别名；别名返回相关现有目录条目，目录总数仍274。能力查询不接受 `--pid/--creation`，当前会话状态应使用独立的 `status` 命令。输出 `schema_version=1`、`kind=diplomacy_research_capabilities`，并列出目录与历史证据索引 SHA。

静态摘要分别计数 `ordinary_static_mapped_actions`（普通动作）、`subject_static_mapped_actions`（属国 singleton 互动）、`special_static_mapped_actions`（独立特殊命令）和 `peace_static_mapped_actions`（和平组件映射），`static_mapped_actions` 为去重并集。当前为 167 + 41 + 9 + 53 = 270，另有 4 项尚无映射。53 项和平动作对应 40 个不同原生组件，包含公共动作别名和脚本定义，不能当作 53 个不同 native 类。属国、特殊命令和和平的映射不会仅凭静态映射成为 pair 研究入口。新模式报告中的 4 个旧间谍取消名称仅有 UI / 静态证据，不能加入实际效果统计。`catalog_review` 绑定本次目录 SHA、模式报告和补贴参数单位核对报告（`duration_years`，仍为 partial），静态映射仍不证明执行。

## 四个独立层次

| JSON 字段 | 含义 | 不能推出的结论 |
|---|---|---|
| `static.mapped` | 当前构建有对应的静态 native 映射 | 不能推出合法、会发送或有实际效果 |
| `laboratory.entrypoint_available` | 有受限研究入口，版本范围见 `profiles` | 不能推出当前世界可调用或所有国家组合可用 |
| `observed_effects.experiments` | 经明确审查、绑定文件字节的历史实验 | 不能推广到其他动作、方向、国家或并发请求 |
| `production.status` | 当前正式 API 的执行状态 | 研究成功不自动注册生产后端 |

36 个版本化 pair 协议入口关联的目录条目的 `laboratory.status` 为 `gated_entrypoint`，模式为 `legality_only/submit`。输出明确 actor/target 范围、只允许 FRA 提交以及版本、进程创建时间、世界、线程、阶段证据、暂停、序号、TTL、未知所有权等运行门槛。它始终返回 `runtime_ready=null`、`live_process_inspected=false`，不会把离线信息伪装成实时可调用性。

`laboratory.profiles` 分别描述 v6 / EU4LAB/1、v7、v8、v9、v10、v12 / EU4LAB/2。v6 固定 TAG 为 FRA、ENG、POR；后续版本增加 NAV、FOI。各 profile 历史阶段证据独立校验：v6–v9 是五家族、20 pair cases；v10 是12家族、48 pair cases；v12是20家族、72 preview及72 command cases，国家组合均为 FRA→ENG/POR，不能据此声称所有新增国家组合都通过同样测试。原十项的单值 `laboratory.protocol/parameters/historical_preflight_evidence_available` 继续表示 v6，`protocol_field_scope=original_v6_entrypoint`；新增 14 项仅绑定 v10，标为 `v10_entrypoint`。新版消费者应使用 `profiles`。

所有研究 CLI 共享 `discovery_source=v5_v6_v7_v8_v9_v10_v12_v14_reviewed_history_with_v12_no_send_preflight`，不再各自硬编码过时的历史范围。v11和v13仍属于 `runtime_unreviewed_versions`，其独立 HTTP 适配器的 36 项白名单属于受限研究候选接口，候选构建不会自动成为运行证据。HTTP 按自身固定白名单过滤历史行：v9 仍为十项，v10 为 24 项；v11不会继承v12的阶段证明，所有新入口也不继承其他动作的效果。`historical_preflights` 按HTTP自身准确purpose筛选，因此只有v12服务会返回本次v12阶段记录；`history_actions` 按协议ID及明确的 `catalog_bindings` 筛选目录行，避免漏掉贸易权别名，也不重复创建动作。`research_references` 提供夹具窗口审查和两份严格单人静态研究的导航、哈希状态；这些条目的 `production_ready=false`、`live_readiness=null`，不会提升原生消费者权限。

所有目录动作的 `production.status=unsupported`、`ready=false`、`backend_registered=false`。生产 HTTP `/v1/capabilities` 和 `tools/diplomacy.py capabilities` 保持原有目录和版本/后端门控语义；`/v1/preview` 仍是参数契约检查。新研究说明不会更改这些接口，不会注册 `NativePairBackend` 或填充白名单。

v11 的候选代码已进行一次实际无发送自检，结果为失败：PID40176 / creation `01dd5692d472900c`，前 14 个 lifecycle 家族完成，第 15 个 `form_coalition` 的 factory 默认字段合同失败，整阶段没有通过。preview/command 未开始，外交和 fixture 请求均为 0，session 冻结；该版本不晋级为成功运行 profile。这里的“14 个 lifecycle 家族”与历史外交效果计数含义不同，不能相加。失败日志本身没有直接读出 state34；默认应为 2、旧检查期望 0 是静态解释，不能写成已在失败进程直接采样的值。

v12已有一次实际20/72/72无发送预检通过，其冻结证据独立于之前39项离线测试；研究合同仍为36 ID。`v12_candidate.runtime_verified=false`、`v12_live_readiness=null`；它不从共享的历史索引继承当前会话权限；默认候选标志不否认独立固定记录中已审核的六项效果。共享 `runtime_unreviewed_versions` 中的 v11 表示没有成功纳入历史证据，并不表示该版本从未运行，也不是全部未构建候选的发现列表。v12 coalition 初始化已有独立正常 AI 构造→wrapper/clone→拥有所有权的队列静态证据，支持准确 token `2de0` 使用 state2，其余19族保持0；factory/clone 默认状态检查本身并不提供这个证明。来源 `work/reports/native-coalition-queue-1375.json` / SHA256 `b36c788c3eeb589abaa208df83cb3f97bf3697023188149588b41bb60dde5b65`。该报告不识别人类 GUI 点击回调，不证明最终 dispatch 或运行效果，不增加历史效果或生产权限。

## v12 固定无发送预检

`historical_preflights[version=v12].historical_preflight_passed=true` 只在全部37个新增引用字节匹配时成立。记录绑定PID17676 / creation `01dd56989186135c`、world `0x1fb2c9cf0d0`、线程48456、raw56456976；DLL SHA `465A20166E1DD04EA7360F6EA83ED02E3AFEE59A26048B1651EE6862F118CEBD`，manifest SHA `652fb6901a43d3918397209a165c2ccd3adb5fd64dbe8b8757391f24d1797914`。固定摘要为 `work/runtime/native1375-v12/preflight-summary-17676.json`，SHA `3a95e5a85403c944ddb633baecba8e2c347e84d53602d26c7cf27f569a6b8f18`。

六文件镜像 `preflight-only-17676` 的日志184298字节，SHA `d324fb4e14f96f5a34c79c16ad7739c3c405fb2c9f62e0e9d8ef90269ed3d45d`。15份原输入、manifest、实际磁盘DLL、14个源及五个候选fixture文件均绑定；三次 `verify_phase` 离线重算与已存报告全文相同。快照只确认指定字段相同，末帧暂停且seq0；请求、外交提交和fixture提交均为0。后续live日志、fixture及pair操作不在本记录内，不自动晋级证据。

记录本身及完整37项文件描述符另有独立review pin `ef2f802621e164db05a74a377378d7f47876f65f0f2b65222414510ae3fcc4b1`，按 `canonical({record, artifacts})` 的UTF-8字节计算；它包括scope、完整引用集合和每个path/size/hash/read_mode。删除引用、改PID/creation/prefix hash或把引用换成另一份有效文件均会拒绝索引，不能通过只验证剩余文件继续声明通过。实际文件缺失/变更则保留原记录并将当前可确认的通过标志置false。

通过72个合法性预检case表示完成受审原生检查，不是72个case都获准，也不是AI接受。36个协议ID可能关联37个目录条目，角色别名仅导航；NAV/FOI虽为协议允许TAG，并非本次ENG/POR阶段矩阵的目标。任一文件缺失、改变或追加会将本记录的当前可确认 `historical_preflight_passed` 降为false，保留 `recorded_historical_preflight_passed=true` 表示原审查记录。候选默认 `runtime_verified=false`、`live_readiness=null` 不变。历史效果计数由独立的效果审查提供；本预检本身不增加效果，生产0以及strict-SP/world-epoch/request因果均不因此改变。

## v12 已停止会话的六项效果

正式摘要 `work/runtime/native1375-v12/experiment-summary-17676.json` 的SHA为 `637f7b7ebccf31c11e51b13562ac90b908e5c25c2252c36cc76cd9e106475372`。它经独立离线审查与`--check`通过，绑定PID17676的精确持有句柄正常退出、完整停止日志、203项输入、97个session文件、全部28个序号、六次pair提交和选定效果。最终暂停raw56457552（1444.12.5）。固定日志1774777字节，SHA `2e4ddef6c8ae1cdc95c52504da737f50c1ec409d31999131c1ba655008c57e10`；不再以增长日志冒充完整终止证据。

| 序号 / 协议动作 | 固定选定效果 | 保存 / 冷重载 |
|---|---|---|
| 3 / `request_trade_power` | 新增POR→FRA普通贸易份额500 | 选定active状态一致，PID7852 |
| 10 / `cancel_trade_power_transfer` | 上述active关系移除 | 选定absent状态一致，PID9948 |
| 13 / `steer_trade` | 新增POR→FRA引导贸易 | 选定active状态一致，PID52308 |
| 16 / `send_gift` | 同日FRA −25000、POR +25000 milli，选定favors不变 | 未声明赠款持久性 |
| 19 / `cancel_steer_trade` | 已存在的引导贸易关系移除 | 选定absent状态一致，PID13252 |
| 22 / `warn` | 新增FRA→POR警告 | 选定active状态一致，PID13252 |

五项关系使用四份按完整SHA核对的存档和四个不同PID/creation的冷重载。取消证明包含提交前active状态，不从一次缺失读取推断撤销成功。保存/重载只确认指定序列化关系、完整国家handle、方向/日期/类型等字段一致；`exact_loaded_file_path_verified=false`，不声称引擎当前路径或整个世界一致。赠款即使存在后续经济读值，也不据此扩大同日差额的结论。未发送的侮辱、被拒绝的包围网/独立支持/人情，以及fixture和速度请求均不增加效果数。

这六项将固定历史状态效果从14增至20，生产仍为0。原36-ID合同、37目录绑定、独立20/72/72无发送预检不变。所有六项共用231个whole-file依赖：203原输入与原37项预检证据去重，再加入正式摘要、case manifest及相关检查源码。`canonical({observations, artifacts})` 独立review pin为 `a282f0d319ed0e689c1f6eb282940836b6f1621204ad4654aec0fa5cd13f2fa0`；删除依赖、改变scope/顺序/声明或赠款数值都会拒绝索引。真实文件缺失/变化则撤回这六项当前claims，保留recorded_claims；仅缺终止或重载证据不会撤销独立无发送预检。

`historical_effect_reviews` 单独返回固定会话的可核实六项效果及五项关系持久性计数；它不是当前会话ready。严格单人来源、可靠world epoch、AI接受、精确request-ID因果、完整世界不变仍均为false。v13首次阶段发布在创建intent后的重新检查处拒绝，没有原生阶段调用，不能晋级；后续共享HTTP discovery别名修正也已改变其support源hash，因此当前代码不能再声称通过冻结v13的`verify_build`，旧manifest没有重写。

## v5 至 v10 指定实验的历史证据

证据索引固定为 [diplomacy_research_evidence.json](../bridge/diplomacy_research_evidence.json)。本次审查包含 v5 固定改善关系实验、v6 PID 45564 / creation `01dd566ec369e4b7` 至 sequence 65 的收尾记录、v7 PID 57404 / creation `01dd567ca147b6f1` 至 sequence 10 的指定实验，以及 v8 PID 39216 / creation `01dd5681d5d0e053` 至 sequence 6 的收尾记录。v7 正向状态另有新进程 PID 33256 的保存/重载一致性检查。v8 的补充重载使用 PID 20276 / creation `01dd568c4bc812d0`；v9 使用 PID 60888 / creation `01dd56890aab4cd6` 至 sequence 7 的已停止日志，并核对新进程 PID 54232 / creation `01dd568b5be898da` 的重载结果。v10 PID 46408 / creation `01dd568ed7034bcb` 在 seq12 后冻结终止，仅接受四项 positive 效果，不包含保存/重载。

| 动作与固定组合 | 记录 | 观察结论 |
|---|---|---|
| 改善关系 FRA→ENG | v5 固定实验 | 新增完整关系/mission/envoy 图，已核对保存和重载 |
| 建间谍网 FRA→POR | v6 seq 2 | submit 返回且新增间谍任务图；未做此动作的保存/重载验收 |
| 停止间谍网 FRA→POR | v6 seq 4 | submit 返回且选定关系/任务消失；未证明普遍取消语义 |
| 停止改善关系 FRA→ENG | v6 seq 6 | submit 返回且选定关系/任务消失；不能据此认证新的正向改善请求 |
| 保独及撤销 FRA→POR | v6 seq 23 / 65 | 分别观察到保独关系新增和移除 |
| 联姻 FRA→ENG/POR | v6 seq 26 / 45 | submit 返回，分别出现相关 `ROYMARREJECT` 通知；没有把发送成功当作联姻生效 |
| 提议附庸 FRA→ENG | v6 seq 25 | 原生合法性 false、reason 17、没有进入提交；这不是 AI 拒绝回信 |
| 联姻 FRA→NAV | v7 seq 3 | 新增双向关系并出现相关 `ROYMARACCEPT` 通知；选定关系通过保存/新进程重载一致性检查 |
| 提议附庸 FRA→NAV | v7 seq 6 | 新增 dependency，原生类型名为 `vassal`，出现相关 `VASALLACCEPT`；选定关系通过保存/新进程重载一致性检查 |
| 取消附庸 FRA→NAV | v7 seq 8 | 仅合法性检查，reason 17、没有发送；不能继承正向附庸效果证明 |
| 解除联姻 FRA→NAV | v7 seq 10 | submit 返回并观察到选定联姻关系移除；未验收此取消动作的保存/重载 |
| 解除联姻 FRA→NAV | v8 seq 4 / 5 | seq4 合法性允许、seq5 唯一 pair 提交，独立观测移除且保存结果一致；补充报告核对新进程重载后婚姻仍不存在 |
| 取消附庸 FRA→NAV | v9 seq 2 / 3 | seq2 合法性允许、seq3 唯一 pair 提交；附庸关系消失、NAV 独立且产生双向停战，保存和新进程重载的选定状态一致 |
| 同盟 FRA→POR | v10 seq 2 / 3 | 合法性允许、HTTP 单次提交及重复 POST 只读 replay，独立观察同盟新增；未保存/重载 |
| 请求军事通行 FRA→POR | v10 seq 5 / 6 | 合法性允许、提交消费归属明确，独立观察对应通行对象新增；未保存/重载 |
| 给予军事通行 FRA→POR | v10 seq 8 / 9 | seq8 仅合法性，旧 compare 为 unknown；seq9 提交后的另一组观测才证明所选对象新增；未保存/重载 |
| 请求驻港权 FRA→POR | v10 seq 11 / 12 | 合法性允许、提交消费归属明确，独立观察所选驻港对象新增；未保存/重载 |
| 速度控制 | v6 seq 7 / 8 / 21 | 已测试速度 0、5，观察到日期推进及有界租约后暂停；不是外交动作 |

这批v5–v10实验有十四种外交动作的特定历史状态变化，分别为先前十种与 v10 新增四种 positive；这不等于 v10 计划中的 14 项正反实验全部完成。v7 的取消附庸合法性拒绝记录保留；v9 的正向验收使用独立夹具与证据，不从早期记录推导发送成功。`reply_acceptance_correlated` 和 `reply_rejection_correlated` 表示按国家组合、类型、日期和新消息节点关联的通知，仍不是精确 request-ID 归因；所有实验 `request_causality_verified=false`、`ai_acceptance_verified=false`。正反模式分别陈述，证据不会互相继承。

v7 的 NAV 实验使用固定测试夹具 profile `3a7f514eadacee07494fef32e8ebca62d1020c6936c9877490ddba0bd59223c1`，改变了外交官数、外交声誉和关系条件。其接受结果不能推广到普通游戏条件。正向联姻及附庸的 `saved_state_verified/reload_verified=true` 限于 `saved_reload_state_consistent`：保留存档 SHA `F6A56C25FD366522C5F625BAFF086B33F02473EDCD34AAE3E3C2984D30436FB8`、序列化关系及新进程中指定关系的完整国家 handle、起始日期和附庸类型一致。`exact_loaded_file_path_verified=false`、`whole_world_unchanged_verified=false`；没有从引擎读取当前所加载文件的完整路径，也没有认证整个世界状态。

v8 使用 profile `68f5c90d63343fd2db64ccd64bd232877409dc43302bf5d40c854c30c84ae918`，seq1 关闭夹具、seq2 速度推进、seq3 开启夹具、seq4 查询、seq5 解除联姻提交、seq6 速度推进后暂停。保存 SHA 为 `0000E4218F266CA3F29E2A3695FA16F4A8F405B91168C2C15F9E14070DC49571`；原收尾记录维持 `saved_state_verified=true`、`reload_verified=false`，新增的独立补充记录在核对新进程身份、婚姻不存在及保留的附庸身份后报告 `saved_reload_state_consistent=true`。原摘要文件未被重写。夹具关闭后的存档无相应 modifier，但外交官池仍观察到 103 个对象，不能宣称缩回 3 个。窗口关闭的人机操作观察与只读状态审查另列来源，不冒充自动像素验证。该补充只增加同一动作的持久性证据，不新增外交动作数。

v9 使用 profile `f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507`，夹具先建立无同盟、无停战的 FRA→NAV 附庸关系，再执行唯一一次取消附庸提交。完整已停止日志、永久 claim、阶段与监督记录、双遍只读关系和夹具观察、保存提取及新进程重载全部绑定。保存 SHA 为 `A0FD329156118EE8284FE214223609FB73F3EAF55C4C6B81278D4171EE4D9F39`，保存/重载选定状态是 dependency 不存在、NAV 无 overlord、双向停战存在。最终暂停日期 raw `56457192`（1444.11.20）；seq7 的首次租约暂停检查点 raw `56457168` 不等于最终保存日期。没有认证严格单人来源、可靠世界代次、当前引擎实际载入路径、整世界一致性或精确 request-ID 因果关系。

v10 固定审核报告为 `work/runtime/native1375-v10/experiment-summary-46408.json`，由 `work/verify_v10_experiment_1375.py` 离线重算。完整日志已停止，健康前缀单独通过 12/48/48 阶段和 seq1–12 的原生所有权验证；末条冻结、seq13 遗留 request/host-intent、无 claim/dispatch 记录及监督器报告的精确进程终止单独核对。末次健康日期 raw `56457144`。冻结原因字符串为 `request_invalid_expired_or_already_claimed`，具体 TTL/文件共享/已有 claim 原因没有得到证明。该已停止会话不可恢复就绪，四项效果均 `saved_state_verified=false`、`reload_verified=false`；其余新家族及所有新取消入口不继承正向效果。HTTP 同盟实验的首次发布与重复请求只读 replay 已绑定同一永久 intent 和 native 结果。

## 哈希、缺失证据和后续扩展

每个实验绑定 PID/creation、DLL SHA、固定国家组合、序号和证据引用。报告文件按完整字节 SHA 校验，持续增长的原生日志按截止指定完成事件的固定字节前缀校验。追加后续日志不会改变已审历史，也不会自动增加能力。每个文件读取有界，路径必须在仓库内，禁止链接与路径跳转。

本轮索引包括876个文件引用、36条历史效果/控制实验、1条独立v12预检及1组独立v14持久性审核，累计校验24,263,680字节。读取上限是1024个文件、每个 8 MiB、总计 32 MiB，索引上限512 KiB。v7 关系/通知比较同时绑定其 before/after 原始输入；保存/重载结论还绑定检查器源码、统一验收报告及各输入文件。v8 绑定摘要的 14 个输入文件、检查器、manifest、实际 DLL、session，以及 seq6 租约完成后第一个暂停健康帧为止的原始日志前缀。v8 补充重载单独绑定其 10 个输入和检查器；v9 绑定收尾检查器的全部 54 个输入、实际 DLL、检查器源码与最终报告，并校验已停止日志完整字节。v10 绑定 68 个输入、固定检查器、独立观察器源码与布局报告；旧 unknown 比较也保留在输入中。v6 收尾摘要和最终状态报告分别校验，各自抓取时刻不同的全日志 SHA 不被当成同一字节快照。

`evidence_status=reviewed_bytes_match` 表示本机文件与审查索引的字节一致；不是重新运行游戏，也不是对每个历史判断再次独立证明。证据缺失或变化时返回 `unavailable_or_changed`，生效的 `claims` 全部为 false，`findings` 为空；原有声明留在 `recorded_claims/recorded_findings` 供审查。缺证不等于游戏中没有该效果。运行日志与部分报告属于本机研究产物，其他克隆若没有这些文件，会明确返回缺证状态。

后续验收需人工审查新的固定实验并更新索引与其 SHA；不能扫描到 `submit_returned=true` 就自动扩展 `observed_effects`，更不能自动开放正式执行。摘要中的静态映射和目录数量从当前目录计算，不使用历史文档中的固定计数。


## v14 停止会话：八项效果与一项 unknown

`directional-finalized-summary-r3-18356.json`（SHA `19f9203fe5eed194c02d8bead92a7503bf296f7f28db3baa50b2882ddfc7d967`）由 root 对固定43步 case 实际执行 r3 审查后生成；266项输入、完整停止日志及20/1/72/72四阶段均通过。独立 r3 源码复审为 `9a3c1f54…f4133`。本轮能力更新校验已冻结字节，没有重跑游戏或生成新的实验摘要。

| 序号 | 接口 | 此方向的结论 |
|---|---|---|
| 3 / 7 | embargo / revoke_embargo | FRA→POR 禁运新增及撤销 |
| 10 / 40 | give_subsidies / cancel_subsidies | FRA付款、POR收款，固定每月1.000/10年；新增及取消 |
| 13 | offer_fleet_basing_rights | 原生提交返回正常，但选定关系未新增，效果unknown |
| 19 | cancel_fleet_basing_rights | FRA为权利持有者、POR为授予者，原active关系移除 |
| 31 | revoke_military_access | POR为权利持有者、FRA为授予者，原active关系移除 |
| 37 | cancel_military_access | FRA为权利持有者、POR为授予者，原active关系移除 |
| 43 | dissolve_alliance | FRA/POR原同盟关系移除 |

这八项将历史效果由20增至28。372个完整依赖共同绑定独立 pin `dc9b75959265c3fbaf4d48e346fa130ccc28563afa489d4aaa201b2a2559156c`；它覆盖所有九条记录、完整依赖描述符、实际停止输入、四阶段、manifest/DLL与源码。缺文件会撤回这组当前claims；修改scope、顺序、依赖或把unknown改成效果会拒绝索引。root对葡萄牙否决授予停泊权的UI观察保留为非原生注记，不能变成AI接受/拒绝的原生证明，不能授权重发或撤销不存在的关系。尚未验收的 `revoke_fleet_basing_rights` 也不借用其他方向效果。

独立 `historical_persistence_reviews` 绑定 `directional-persistence-summary-r2-18356.json`（SHA `efd863a3252812ee6481f98f3bfc695a23128a2f3a07c70c459cc216fc2bf5b4`）及66项依赖，pin为 `5fb2a2c92845ff24215865acad1e9d9a9f8c5979ffc52607cf8b1c3efbc94771`。九个状态来自positive/final两份存档和PID35552/59012的独立冷重载；七个有完整选定序列化关系与带类型检查的重载一致性，fleet/embargo的两个缺席结果仅为typed reload，序列化布局仍unsupported。观察器action名称标识检查的关系方向；positive档中用取消方向检查器看到active，并不表示当时已执行取消。

这组独立持久性明细由完整离线能力结果提供。已冻结的研究HTTP只转发其原合同中的summary、history_actions和匹配版本的预检；本轮没有修改共享HTTP支持文件，也没有给旧HTTP增加持久性接口。

持久性结果独立返回，v14各外交实验的 saved_state_verified/reload_verified 仍false，原实验摘要的 save_reload_verified=false 保留。两份大型存档的SHA保留在独立审查中；能力发现只校验有界审查报告和提取结果，不再次读取或解析36MiB存档。缺持久性依赖只撤回该组结果，不抹掉已审外交效果；缺效果摘要也不冒充撤销已审独立持久性记录。精确加载路径、请求因果、整世界不变、结算、自然AI接受、严格SP、world epoch与production均false，live readiness仍null。
