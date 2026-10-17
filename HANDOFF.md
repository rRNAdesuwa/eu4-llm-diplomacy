# EU4 LLM 外交桥接交接

## 当前运行：R47A/B 金币与四省组合议和已接受并重载（2026-10-17）

R47A 在独立战争场景中通过统一接口执行一次组合议和：法国（FRA）向英国（ENG）提供 1.0 金币和省份 4388、4111、4112、4389。请求 `r47a_offer_eng_money_four_provinces_001` 的主动作是 `cede_province`，方向为 `offer`，金额条款排在省份条款之前。英国原生 AI 返回 state2/accepted，英法战争结束；法国支付 `1000` raw，原生把这笔金额分配给 ENG `661`、SWE `23`、UTR `316`，四个省份的 owner/controller 均从 FRA 转为 ENG。

[A 运行报告](work/runtime/diplomacy-query-20261017-r47-peace-a-combined/mixed-execution-001/report.json)的17项检查全部通过。报告同时记录一次请求发布、一次消费和一次业务投递。单次 QUERY7 返回的英国原生接受度评价为 `+12`；同一原提议和动作副本包含84个候选条款，选中5项，其中包括默认金币条款。公开 `effects`、私有支付观测和四省后果均完成核对。

A 保存的结果为 `llm_diplomacy_peace_money_provinces_accepted_20261017_r47a.eu4`，SHA-256 为 `23e4cd9279760a45224ce154c190d58471762c3fba03a8522d63aae3b3d23049`，大小 42,879,084 字节，日期为 1455.5.12。[保存观察报告](work/runtime/diplomacy-query-20261017-r47-peace-a-combined/save-observer-report-1792171939451380400.json)记录了该文件；原有三份自动存档已恢复。

R47B 在新进程中载入同一保存结果。安装目录为 [R47B mixed reload](work/runtime/diplomacy-query-20261017-r47-peace-b-mixed-reload)，PID `3656`、session `3656-1dd5d945c71fc76`，DLL SHA-256 为 `4f9da57bf5c9dcc57d8ce5ae2ec6b4fe346a04e887be8f468439047588bce91e`，构建包含 63 份源码。[B 重载报告](work/runtime/diplomacy-query-20261017-r47-peace-b-mixed-reload/mixed-reload-001/report.json)的 10 项检查全部通过；10 个国家国库和 4 个省份的保存后状态均与 A 的私有执行后观测相符。B 当前保持 POR 玩家、暂停状态，FRA 与 ENG 已和平。A 与 R46G 均已通过明确重启结束。

R47证明了金额支付与多省份转移可以在同一议和请求中共同完成，两种后果均已保存并重载。Python全套380项和原生后果计算24项通过。下一阶段继续扩展其余常用议和条款、外交剩余阶段、公平信息、常驻LLM和长期循环。详细过程见[R47人类说明](docs/history/R47金币与省份组合议和.md)，流程复盘见[复盘第35节](docs/外交开发推进复盘.md)。

R47最终检查点为[002归档](work/runtime/r47-peace-combined-checkpoint-20261017-002/archive-manifest.json)，336文件、6,947,793字节，manifest SHA `419e0afedd76ddfed81045b80cde1e442974c4d5ac507393716098f41c5bfb23`。[状态文件](work/runtime/r47-progress.json)记录15项已核对哈希的证据，63份native源码与B构建相符。001归档保留修订前文档；002已把接受度评价12与独立聚合分值46的名称分开，实际运行证据一致。全部root和子代理工具会话均已结束，B游戏保留暂停。本段索引在归档后追加。

下一条款优先战争赔款：已有[type7及无省份条款合同](work/runtime/peace-no-province-terms-contract-20261017-001/report.md)，继续研究原生选择与结算。B为和平结果；下一次英法议和从独立战争基线 `llm_diplomacy_peace_concession_ready_20261016_r46b.eu4` 启动新进程。不得重发R47A已完成请求。完整goal保持active。

## 历史运行：R46G 四省让步接受与结果重载（2026-10-17）

当前安装为 [R46G](work/runtime/diplomacy-query-20261017-r46-peace-g-province-reload/installation.json)，PID `6656`、session `6656-1dd5d8e337e34e3`，DLL SHA `ef2d09f9135b06b7a05a52e4ac64339813b6ac1d0b946210ee5c887b3657f732`，63份源码。葡萄牙（POR）玩家、法国（FRA）控制国，暂停1455.5.12/raw `56548944`；英法战争结束。A/B/C/D/E/F均已通过明确重启结束，各进程只安装一次。

F 唯一请求 `r46f_offer_eng_four_provinces_001` 通过统一接口提供4388、4111、4112、4389给英国。英国原生AI实际state2/accepted，四省owner/controller均FRA→ENG，公开 `terms_verified=true`，18项运行检查通过。结果存档 `llm_diplomacy_peace_four_provinces_accepted_20261017_r46f.eu4` SHA `a45999dbad1ba1456e9a185ce808567333d27458f025bd023cf15dc46c66c18b`，42,878,702字节；[流式保存对照](work/runtime/r46-province-save-pair-20261017-001/report.md)独立确认四省归属。G原生探针、私有执行后观测及存档中的四省和10国国库均匹配，[重载派生报告](work/runtime/diplomacy-query-20261017-r46-peace-g-province-reload/four-provinces-reload-001/four-provinces-reload-002-correction.json)10项通过。001的唯一失败是比较器取错runtime层级，使用原快照离线修正，没有重跑游戏或存档扫描。三份原自动存档均已恢复。

本轮增加让步方向QUERY7、金币/省份双方语义、原生33省候选查询、实际后果 `effects` 及重载后果读取。修复整临时对象raw memcmp误报、白和平侧别解析、候选空请求、把copied参数误当方向、授权账本收付款国硬编码等问题。E唯一请求已消费但未业务投递，保留失败报告及wire统计纠正；不得重发E/F编号。原生账本422项通过，Python整合与真实事件夹具见本轮报告。详细说明见 [R46](docs/history/R46让步方向与条款后果.md)。

继续金币实际接受与支付、其余常用议和条款，以及19项外交其他阶段、统一整合、公平信息、常驻LLM和长期循环。完整goal active。G是和平结果；下一笔英法议和需重新载入战争基线 `llm_diplomacy_peace_concession_ready_20261016_r46b.eu4`（SHA `634fdcc2c046e6a0860494bfbeba0b93a4333d43ca50ef7ad506c4c95a437772`），在独立新进程安装同一不可变构建。

R46 已归档为 [332文件检查点](work/runtime/r46-peace-concession-checkpoint-20261017-001/archive-manifest.json)，6,854,438字节，manifest SHA `e62ec2c3694fc591764140d96f332d50fead6bb574463fedacbccfeeea1f0325`。状态文件 [r46-progress.json](work/runtime/r46-progress.json)的39项证据引用均核对哈希，当前63份native源码与G构建一致。最终Python全套372项通过，原生账本422项、后果计算18项通过。全部root与子代理工具会话已结束；G游戏保留暂停。此索引在归档后追加。

## 历史运行：R45G 主动议和拒绝、外交官分配修正及重载（2026-10-16）

当前安装 [R45G](work/runtime/diplomacy-query-20261016-r45-peace-g-money-reload/installation.json)：PID `45272`、session `45272-1dd5d728104a377`，DLL SHA `31eaee779c162e50c73dff051a20ec53cfbdebc1aafa13cc824650a6edeb5f9b`，61 份源码。POR 玩家、FRA 控制国，暂停于 1455.1.5/raw `56545896`，英法战争继续。G 载入 F 的金钱提议被拒绝结果；[实际重载报告](work/runtime/diplomacy-query-20261016-r45-peace-g-money-reload/money-rejected-reload-validation-001/report.json)9 项通过。A/C/D/E/F 均已通过明确重启结束；B 因外部启动错误框无响应而结束，未安装 DLL。

法国已合法发送白和平、索取10金币和索取曼恩177三种提议，英国原生 AI 均明确拒绝，各17项运行检查通过。F 新构建修复了初次 Peace handler 把原生外交官分配误判为参数篡改的问题：核验同一已消费请求、原生调用位置和外交官记录后，只允许 envoy 从未分配变为原生编号；完整双方、日期、方向和条款继续比较。F 正常请求的 state0 handler 已实际转发一次，随后英国 state1 正常拒绝；无授权 handler 负例20项通过，原生调用0，业务状态不变。不得重发 A/D/E/F 业务请求或 F 的已消费测试包。

F 保存 `llm_diplomacy_peace_money_rejected_20261016_r45f.eu4`，SHA `92dc5d57c2a293261381e1a776e9a4af44f77511e9f8b932a3b8695025e99478`、43,084,825 字节。白和平拒绝已在 C 重载核验；C 的状态检查器错误通过原快照离线修正，没有重跑游戏。D/E 存档对照显示双方国库、曼恩归属不变，英法继续交战。三个原自动存档均已恢复。Python全套341项、随后新增流式存档3项定向测试通过，native账本399项通过。运行过程、处理器修正和下一步见 [R45 人类说明](docs/history/R45主动议和与NPC拒绝.md)。

下一步完成对方实际接受的提议、金钱分配与扣款、省份所有者/控制者读取及结算，再逐项扩展其余常用议和条款。完整19项外交各阶段、19项议和、公平信息、常驻LLM和长期循环仍为原目标，goal active。当前结果证明 NPC 的真实拒绝路径；实际接受和条款结算继续开发。

R45 已归档为 [322文件检查点](work/runtime/r45-peace-outbound-envoy-checkpoint-20261016-001/archive-manifest.json)，6,587,187字节，manifest SHA `d6a12595d6402bd865e74c8cf2ec614f22caec39f4d6cf3d7af0a4a97c311183`。状态文件[r45-progress.json](work/runtime/r45-progress.json)的32项证据引用均已核对哈希，61份原生源码与G构建一致。G还完成了四个省份的有界字段读取，三个不同所有者/控制者样本确认本版本`+0x468=owner`、`+0x470=controller`。新增存档/省份读取的6项定向测试通过。root和子代理工具会话均已结束，G保留暂停运行；本索引在归档后追加。

## 历史运行：R44E 外来白和平接受、拒绝及两分支重载（2026-10-16）

当前安装 [R44E](work/runtime/diplomacy-query-20261016-r44-peace-e-accepted-reload/installation.json)：PID `40804`、session `40804-1dd5d64a6b9aec2`，DLL SHA `31e6f65296f8df687428a744103bb55724fac15279edc04baab2541d10d9a583`。61 份源码均与当前 native 工作树相符。POR 玩家，FRA 控制国，暂停 1454.12.2/raw `56545080`；当前 FRA/ENG 已和平，原生 pending 队列为空。A 只编译；B 构建后安装一次；C/D/E 复制同一不可变构建，各在独立新进程安装一次。R43C、B/C/D 已通过明确重启结束。

`peace_offer` 已接通公开入站目录、规则查询、明确 accept/reject 和结果读取。B/D 分别从同一 R43C 待回应存档启动，恢复原生 token199、83 个完整条款对象，再各发送一次回应。B 请求 `r44b_reject_eng_peace_003` 实际 rejected，pending 移除、战争继续；D 请求 `r44d_accept_eng_peace_001` 实际 accepted，pending 移除、战争结束、white terms_verified=true。两次运行各20项通过，处理器实际返回、完整条款授权和 native membership 均有独立日志。B 的前两次预检查没有提交业务；不得重发第三次拒绝或 D 接受请求。

拒绝结果 `llm_diplomacy_peace_rejected_eng_20261016_r44b.eu4`，SHA `59eb153e52ed137b42bf899639b699ca419f88b8184b875af82962b32a477a0c`，42,772,961 字节；[C 重载](work/runtime/diplomacy-query-20261016-r44-peace-c-rejected-reload/rejected-reload-validation-001/report.json)8项通过。接受结果 `llm_diplomacy_peace_accepted_eng_20261016_r44d.eu4`，SHA `c842f297da435e8f7405a053f8f0c3115baed7cfc29f32d8d88340cbf607f30f`，42,779,195 字节；[E 重载](work/runtime/diplomacy-query-20261016-r44-peace-e-accepted-reload/accepted-reload-validation-001/report.json)8项通过。两次保存均恢复三份旧自动存档；原始 R43C 待回应存档保留。

已修复非零 pending token 的响应授权和 native_current_war 布尔字段误读。Python全套332项、修复后定向137项、实际双分支夹具Peace定向58项，账本384项与wire/formatter均通过。新脚本 `work/run_peace_inbound_response.py` 与 `work/validate_peace_inbound_reload.py` 可分别运行一次回应和只读重载验收。人类说明：[R44](docs/history/R44外来议和查询与明确回应.md)，状态：[r44-progress.json](work/runtime/r44-progress.json)。全部 root 工具句柄已终态；没有整机 RAM 轮询或大型反汇编全读。

R44 已归档为 [311 文件检查点](work/runtime/r44-peace-inbound-response-checkpoint-20261016-001/archive-manifest.json)，6,372,050 字节，manifest SHA `375acf90cac423213e3ee8230e83c199d5137961544ca69cd7f7ec6b03d6d21a`。源码、三个真实事件夹具、运行/重载操作器和状态已复制；A/B/C/D/E 构建、实际运行、保存和静态分析保留外部哈希引用。原生账本384项及wire/formatter的可审查编译/运行日志另存于 [native验证报告](work/runtime/r44-native-unit-validation-20261016-001/report.json)。此索引在归档后追加。

下一步重新载入独立战争实验存档，按原生外交官与冷却条件验收 FRA 主动发送、NPC 正常接受/拒绝，再继续其余常用条款及完整费用、参数和后果。当前 E 是和平结果，不能直接当作出站战争上下文。完整19项常用外交、19项议和、其他阶段、公平信息、常驻LLM和长期循环保持原范围，goal active。

## 历史运行：R43C 议和执行适配与外来提议保留（2026-10-16）

当前安装 [R43C](work/runtime/diplomacy-query-20261016-r43-peace-c-wrapper-and-inbound/installation.json)：PID `44892`、session `44892-1dd5d581078a642`、DLL SHA `f48944ee37bf0ef27e0c95bb9be3338946fb1726aecca928551452c2832ee4c4`，60 份源码输入。玩家为葡萄牙，桥接控制法国。游戏已从 R37B 宣战存档推进一天，暂停在 1454.12.2/raw `56545080`。A 仅编译，B/C 各在独立新进程安装一次；B、R42E 已通过明确重启结束。

白和平、金钱和割省的公开发送适配已经连接 `EU4PEACE_EXEC1`、最新 inspect、原生消费、完整条款账本、传输和结果读取。R43B 三类请求各 22 项检查通过：有效请求被消费后，DLL 因原生 common gate 不允许而返回未提交；公开 inspect/execute/result 也分别正确报告授权可用与游戏规则不可用。当前法国无空闲外交官，对英冷却要到 1455.1.2。尚需实际验收合法发送、NPC 接受/拒绝和条款后果。

接收后的实际调度已经闭合：`14ca770` 取得接收列表 → wrapper `+40/4e8660` 最终检查 → 原生回调 `14ce910` → wrapper `+48/4e7c80`。新增只读运行锚点为 caller `14ca7ad`。C 的查询实际调用最终检查，三类和约均返回 wrapper gate=false，身份和完整载荷前后比较通过。公开消费者曾误把完整的否定结果当作格式错误，已用三条实际事件修复并回放；一次公开复验24项通过，原失败 C/public-wrapper-rule-query-001 保留，纠正记录在 C/public-wrapper-rule-query-recheck-001。没有重发业务请求或重启DLL。

C 已正常传输英国→法国的白和平实验提议，原生 pending 0→1，proposal `1`、native token `199`、envoy `2`，完整载荷含 83 个条款对象，选中 1 项。推进一天后，同一提议在每日 caller `b22a3` 产生 hold_count=1，native queue 和完整载荷匹配，法国原生 AI 选择被跳过。初次 state0 handler 被闸门阻止后，generic 仍成功建队；不要简单放开该 handler，598f00 的部分 state0 路径能直接结算和约。公开 Peace pending 和 LLM accept/reject 适配继续接通。

已保存 `llm_diplomacy_peace_pending_eng_20261016_r43c.eu4`，SHA `71381146f68b526471a5eeae1342acee4b6412d30c45c4a133bec3299427c824`，42,787,118 字节、1454.12.2、POR。三份原自动存档已恢复。下一阶段从该存档重载，继续同一份提议的明确回应，不重新发送夹具。不得重发本进程的 ENG→FRA 提议、R37 宣战或 B 的已发布请求。

人类说明见 [R43](docs/history/R43议和执行接口与入站提议保留.md)，三类原生拒绝、入站和一天观察的路径均在那里列出。Python全套328项、账本381项及严格wire检查通过，状态索引 [r43-progress.json](work/runtime/r43-progress.json)。完整 19 项议和、常用外交其他阶段、公平信息、常驻 LLM 和长期循环继续保持原范围；goal active。本轮没有整机内存轮询或巨型反汇编全读。

R43 已归档为 [302 文件检查点](work/runtime/r43-peace-execution-pending-checkpoint-20261016-001/archive-manifest.json)，6,219,945 字节，manifest SHA `7e0bc46274b107e43ed7652af6ac9350177957d2b4dec65c496527aac71eb689`。源码、真实消费者夹具、操作器和状态已复制；A/B/C 不可变构建、实际运行、保存和逆向证据按哈希引用。此索引在归档后追加。

## 历史运行：R42E 完整议和载荷与两个入口拦截已通过（2026-10-16）

当前安装 [R42E](work/runtime/diplomacy-query-20261016-r42-peace-e-clone-and-handler-tests/installation.json)：PID `19188`、session `19188-1dd5d4c1483cd8b`、DLL SHA `3dcdb3e07e534380af1fb078b7419ef2735fd410fcd6bc83b9d2d05b3b0f17e5`，56 源码输入且与当前工作树匹配。POR 玩家、FRA 控制国，暂停 1454.12.1/raw56545056，仍载入 R37B 命名宣战存档。R41E、R42B、R42D 已通过明确重启结束；A 只构建，C 编译失败，B/D/E 各在独立新进程安装一次。不得重发 R37 业务请求或任何已经发布的测试包。

新增 `PeacePayloadRef` 与 `PeaceActionPayload`：110656 字节完整逻辑和约在 DLL 堆中封存，每条生命周期/协议/ledger 记录只携带 8 字节引用及三个动作标志。Native source/动作/wrapper 全字段和选中索引比较、Peace ledger initiate 家族、复制/传输与动作读取 hook 均已接入。环形队列出队释放引用。账本 369 检查、引用 19 检查、独立 wire 测试通过；Python 320 项通过。`bridge/peace_execution.py` 和新 wire 已定义，公开执行适配尚未连接，查询 `authority_bound=false` 继续保持。

[E 六项入口验收](docs/history/R42议和载荷授权与入口拦截.md)：白和平、10 金币、177 曼恩分别经过 generic entry 与 Peace action+48 handler，六次各 20 项通过，均为 `UNAUTHORIZED_FRA_PEACE_OFFER`，handler 原生调用数 0，战争/外交官/日期一致。各包 native_validity=true/common=false/send=true，因此合法正常发送仍需独立验收。B 的省份查询回归 23 项通过，B/D 的历史入口报告也保留。

[E 传输报告](work/runtime/diplomacy-query-20261016-r42-peace-e-clone-and-handler-tests/peace-authority-test-9f6424fc0514451ea9b75ad4cd02a321/report.json)保留 failed：serialization/load full87 payload/header 相等；已实际观察 `native_alliance_wrapper_clone`、caller15801e2、source/target完整，尚无 generic/handler entry。B/D 漏 Peace 的日志 filter，E 已修；不能再把没有协议日志写成没有 clone。D ring只读快照 head=tail=15/cancelled0/pending0 是时刻状态，不能推断接受或丢弃。旧 worker slot 公式已按真实指令纠正为 `ring+0x180+0x28*((3*head)&7)`，不要使用旧 0x78 公式；本轮未遍历槽位。

下一步定位 receiver 克隆后的调度调用者，把新请求结构接入完整授权发送与结果；先完成 FRA 入站 Peace pending 保留和明确 accept/reject，再推进完整日期循环。当前入站 adapter 使用明确拒绝处理，尚未实现原生 pending 保留，不能称作已完成接收方决策隔离。需要补 native +b8(mode0) 实际判断与 mode1 因素预览对照；mode0 会读取 action208 并可直接返回1000，不能直接用mode1 raw>=1冒充NPC预测。19项和平、常用外交其他阶段、公平信息、常驻LLM和长期循环全部保留。状态索引 [r42-progress.json](work/runtime/r42-progress.json)，人类说明 [R42](docs/history/R42议和载荷授权与入口拦截.md)。没有整机 RAM 轮询、议和业务提交、日期推进或新结果存档。

R42阶段已归档：[292文件检查点](work/runtime/r42-peace-authority-checkpoint-20261016-001/archive-manifest.json)，6,005,353字节，manifest SHA `203691dd37372fdaaef56e32545e53ad24cf3d60c069ca2338f581116f291643`。源码、操作器、人类说明和机器状态已复制；构建、实际运行报告与逆向证据按哈希引用。此索引在归档后追加。完整goal保持active。

## 历史运行：R41E 单/双省份选择及完整接受因素已通过运行验证（2026-10-16）

当前安装 [R41E](work/runtime/diplomacy-query-20261016-r41-peace-e-persistent-provinces/installation.json)：PID `30988`、session `30988-1dd5d41376255c3`、DLL SHA `81e42dad409ccc614f051b45e861d738bd60deee5f7099d6bd5659b727bd4ac2`，51源码。POR玩家、FRA查询，暂停1454.12.1/raw56545056；仍载入R37B命名宣战存档，SHA `083fd5fc0e98312fdc810c7dbd93be54b538ba17a1aca57bd3ed0fab2f7b00f2`。C已明确重启结束。A/D只构建未安装，B/C/E各只在自己的新进程安装一次。不得重发R37业务请求。

[E实际批次](work/runtime/diplomacy-query-20261016-r41-peace-e-persistent-provinces/peace-province-offer-queries-29ad0808325b491c852025f274a9e686/report.json)5次查询、23/23检查通过：41候选名称和FRA受益国；单省份177曼恩实际选中177，原生聚合分值8；双省份请求177/87、实际按候选顺序返回87/177，分值20；两者请求匹配及source/action copy均true。缺失2147483647无选择/无评价，空IDs本地拒绝。87条完整字段、typed selected-index、source/copy/after相等；原生selected数分别2/3（包含默认Gold0）。四快照/暂停/日期保持，无业务提交、推进或新存档。

保留选择的流程来自原生和约生成器98bf50：selected位→97a4e0前置依赖重算→按类型桶追加→条款+118原生重算→97a4e0后置依赖重算；type3桶3和descriptor返回身份已验证。[合同与REA证据](work/runtime/peace-province-persistent-selection-root-20261016-r41-001/report.md)。C的99d220临时试算与993520回滚结论继续保留，不再作为选择入口。

E原生日志中两份省份和约均preview=-100、9项因素完整、aggregate8/20。公共API初漏evaluation required ACK，导致已存在评价被剥离；Python已修复，无需重启DLL。[一次公共接口复验](work/runtime/diplomacy-query-20261016-r41-peace-e-persistent-provinces/province-public-evaluation-fbb0eed702cb4a85b1c2a82ba848c857/report.json)9/9通过，双省份公开返回-100、9因素和aggregate20，其中DIPLO_WAR_UNOCCUPIED_FORTS文本明确未占领与曼恩陆路相连的要塞。原E报告保持不变。

下一步把完整和平payload与动作身份接入ledger/复制/协议/传输/执行授权，分别隔离FRA发起和回应，再推进外交官冷却，运行实际议和、原生响应、后果、保存重载及其余19项条款。当前统一peace执行仍unimplemented，native_payload.authority_bound=false。保持暂停。整合后的Python全套312项、实际省份夹具/ACK定向9项、原生JSON三场景通过。人类说明见[议和接口](docs/议和接口与运行验收.md)及[R41过程](docs/history/R41省份查询与临时选择问题.md)。完整goal active。

R41阶段已归档：[278文件检查点](work/runtime/r41-province-query-checkpoint-20261016-001/archive-manifest.json)，5,844,333字节，manifest SHA `69f99325dc7a84772235c4c9281d2aac614145cc5f024e129762ad99fadb3f86`。源码、真实夹具和操作器已复制；A/B/C/D/E构建与原始/纠正运行证据按哈希引用。机器状态见work/runtime/r41-progress.json。此索引在归档后追加。root与三个worker的工具会话均已终态，无整机RAM轮询。

## 历史运行：R41C 已查询41个省份候选，已证实旧入口只做临时试算（2026-10-16）

当前安装 [R41C](work/runtime/diplomacy-query-20261016-r41-peace-c-province-json/installation.json)：PID `41488`、session `41488-1dd5d38938c676e`、DLL SHA `f5be048193d2ab47b2a8032eca2e6161e5103816b232696c92511467b409fb1b`，51源码。POR葡萄牙玩家、FRA法国查询国，暂停1454.12.1/raw56545056，仍载入R37B真实宣战结果存档。R40B、R41B已明确重启结束。R37业务请求 `r37b_declare_eng_core177_001` 不得重发；R41没有议和提交、日期推进或新存档。

[C实际批次](work/runtime/diplomacy-query-20261016-r41-peace-c-province-json/peace-province-offer-queries-a4d42b6e6c78411fa130e781a9fb4471/report.json)完成5次查询：战争发现、41省份候选、单省份177曼恩、双省份177/87加莱、缺失候选2147483647。四个province事件均为合法JSON，候选名称和FRA受益国可读；完整87条候选payload在source/copy/after一致。单省份/双省份虽然返回delta8/20，实际selected均为空、parameters_matched=false，因此原报告仍为failed。枚举/缺失请求也验证了空选择复制相等，copy证明与请求匹配分别返回。

已确证 `+0x120→99d220` 在返回前经 `993520` 恢复选中位和派生状态；该入口是临时分值试算，不是持久选择。见[修正合同](work/runtime/peace-province-query-contract-20261016-r41-selector-correction/report.md)。下一步研究真实UI点击选择流程，确认其保留选择与重算步骤后，再合并当前helper错误原因修复构建；工作树helper已有改动，不能声称它与C不可变DLL完全一致。省份候选逐条可选谓词仍未独立恢复；整份和约三gate和具体外交官/冷却原因已导出。

R41B曾因JSON数组缺两个闭合方括号导致consumer超时，原日志与报告保持不变；[离线纠正](work/runtime/diplomacy-query-20261016-r41-peace-b-provinces/peace-province-offer-queries-ae6babaa0ec8441991a94e1207b4c63d/province-query-reconciliation.json)只在派生文件补括号，确认同样41候选。C的操作器还误从公共投影读取私有evaluation，已改为按原生事件验证；这项消费端修正不会改变真正的持久选择失败。

人类说明见[R41省份查询与临时选择问题](docs/history/R41省份查询与临时选择问题.md)。Python全套310项通过；C四条实际事件回放8项通过；实际JSON生成/解析三场景通过。完整goal继续active，统一议和执行、19条款最终验收和其余整合仍需开发。

## 历史运行：R40B 已导出战争成员并完整比较议和字段（2026-10-16）

当前安装 [R40B](work/runtime/diplomacy-query-20261016-r40-peace-b-payload/installation.json)：PID `46780`、session `46780-1dd5d2adc49edf3`、DLL SHA `f3a6e301a9b8925f6d037566bed3590e591db2cb0420615de5bd09ac3c89e4d6`，49源码。POR玩家、FRA查询国，暂停1454.12.1/raw56545056，载入R37B真实宣战结果存档SHA `083fd5fc0e98312fdc810c7dbd93be54b538ba17a1aca57bd3ed0fab2f7b00f2`。R39E已随本次明确重启结束。R37业务请求 `r37b_declare_eng_core177_001` 不得重发；R40只有3次只读查询，没有议和业务提交、日期推进或新结果保存。

实际批次：[R40B原始运行](work/runtime/diplomacy-query-20261016-r40-peace-b-payload/peace-payload-context-43dd516df4d74cd5ac8f1249c4e5d3c2/report.json)。战争发现、选中白和平、选中10金币。新 `native_war_context` 通过97bba0取得实际战争，绑定选中registry reference，导出side_a六国FRA/AMG/AUV/BOU/FOI/ORL、side_b四国ENG/TYR/SWE/UTR；两侧与独立存档成员集合一致。角色/领袖继续unknown，不能把中性side编号当全局攻防ABI。

新 `peace-payload.h` 与 `peace-native-payload.inc` 按981500/980fe0真实序列化字段捕获：双方、4个国家句柄序列、方向、1b9、条款共享字段、额外国家句柄/关联对象编号/flag40、Gold金额、两类实际定义名称，以及typed selected-index。40项factory完整白名单均有静态合同；本场景实际出现19类、87项，source/copy/after均完整、无unsupported、owner正确、source_copy_equal与serialized_fields_unchanged均true。原始条款值及vtable只在private JSONL，公开只返回完整性/数量/相等结果。`authority_bound=false`，尚未加入ledger、transport及executor。

原生白和平默认选中Gold0（bucket0/index0）；money把同一条款改为Gold10000。原运行脚本误要求white selected_count0，并用公共结果中没有的私有query_id关联日志，导致原报告3项consumer检查失败。[离线纠正报告](work/runtime/diplomacy-query-20261016-r40-peace-b-payload/peace-payload-context-43dd516df4d74cd5ac8f1249c4e5d3c2/reconciliation-001.json)已用同批日志重算，24/24检查通过，原报告SHA `6485b4ea4e138519ef8f3a309a2a6f2c7dad6c4469d45f071f2c862fd9a87c02`保持不变。没有重发查询或重启游戏。

静态与字段合同见 [R40载荷合同](work/runtime/peace-payload-contract-20261016-r40-001/report.md)、[40项工厂](work/runtime/peace-province-selection-20261016-r40-001/factory-types.json)、[序列化字段](work/runtime/peace-term-serialization-20261016-r40-001/report.md)。R38要求比较未初始化tail及所有派生缓存的旧计划已由实际协议合同修正；下一步以完整语义值绑定授权，另核验外层动作、派生结构与真实传输身份。

省份研究纠正：1314be0→a688b0返回的是战争上下文，算法与97bba0相同，不应继续当省份候选。真正遗漏类型来自factory bucket3，vtable1cd4ad8/type2d25；serializer9a37d0=shared+extra30 uint64+nested(term38+20)u32+flag40。其+120→99d220为选择切换，+118→9a8420为重算/格式化。后续[type3字段绑定](work/runtime/peace-province-selection-20261016-r40-001/type3-field-binding.md)已通过reader9a36a0及formatter9aa3d0证明term38为原生province record，record+20为ID；B实际有41个该类型候选，extra30均为FRA句柄，source/action共164行一致。下一轮可基于原生候选提供province_id查询与选择；调用前按原生UI完整确认RDX上下文及R8B模式，勿直接写selected位。

Python整合全套302项通过；纯C++字段模型28项通过。完整goal保持active：常用外交19/19实际路径仍需完成最终阶段，19项和平的授权/执行/响应/后果/保存重载、其余阶段、公平信息、模型和长期循环均保留。人类说明与复盘已更新。当前进程只安装这一次DLL，后续新DLL必须明确新进程。

## 历史运行：R39E 已查询指定金币与完整接受因素标识（2026-10-16）

当前安装 [E](work/runtime/diplomacy-query-20261016-r39-peace-e-factor-ids/installation.json)：PID `8496`、session `8496-1dd5d1acc58e1ae`、DLL SHA `224142e7ca8d0e4f412b5ec9ec45be4e7f32cfc2e2e9e9180b2a13557f6f878f`，46源码。POR玩家、FRA查询国，暂停1454.12.1/raw56545056，仍载入R37B真实宣战结果存档SHA `083fd5fc0e98312fdc810c7dbd93be54b538ba17a1aca57bd3ed0fab2f7b00f2`。R37业务请求 `r37b_declare_eng_core177_001` 不得重发。R39只有查询，没有议和业务提交、日期推进或新结果保存。

[D金额矩阵](work/runtime/diplomacy-query-20261016-r39-peace-d-money/peace-money-offer-queries-b127fe75dd8b4aeba2f4869e75bca720/report.json)6查询/16检查通过：10/20金币及重复10金币均source/action回读10000/20000，当前原生currency ceiling865000即865金币；865.1超限，不调用setter，actual terms=[]，score不可用。within preview−100、聚合分数1、8因素；白和平preview−45、聚合0、5因素。Q5方向demand、payer ENG、claimant FRA；0.1金币精度、1000raw/ducat。GoldLimit输入100000是原生分数预算，不是金币硬上限。D DLL SHA `e583f145afbba934150287bf5def619ca802cb021fc1e4671191d411b385006b`，已停止。

[E重点验收](work/runtime/diplomacy-query-20261016-r39-peace-e-factor-ids/peace-factor-identifiers-88ab57c241964331b1e288ecb67c2963/report.json)3查询/14检查通过：白和平5项、金钱条款8项全部取得稳定key、中文名称、原生值/flag、strict row/text绑定；native_evaluation.factors_complete及acceptance.details_complete均true，外层acceptance.complete仍false（单位/预测阈值未完成）。实际五项caller位于370be0，已加入DIPLO_WAR_REBELS、DIPLO_HOLD_CAPITAL、DIPLO_WAR_TIME_PASSED、DIPLO_MILITARY_STRENGTH、DIPLO_WAR_FORCE_BALANCE。其他3项为DIPLO_WAR_INCONCLUSIVE(-1000)、DIPLO_PEACEOFFER_VALUE(-1)、DIPLO_HIGH_DEMANDS(-2)。8项和−1048，原生总值−100，分别返回，不自行求和替代总值。

R38附录中记录的函数名不准确；实际复用的是 `alliance_query_reason_provenance()`，事件 `native_alliance_reason_provenance`。D/E已输出真实caller并完成私有记录与public index对应；无需新增1c21e0 hook。只用一个实际命中函数370be0的REA查询补齐五key，证据见[标识合同](work/runtime/peace-real-factor-identifiers-20261016-r39-001/report.md)。E没有混装/重复注入。全Python298项通过；E真实夹具及列表定义定向22项通过。[目录实时读取](work/runtime/diplomacy-query-20261016-r39-peace-e-factor-ids/peace-catalog-live-5e19c8a10f5447d9bee975f7aac525e3/report.json)6项检查通过，19项和平目录正确声明white/money selected能力及嵌套参数形状，execute仍unimplemented。

R39源码与证据索引已归档：[259文件检查点](work/runtime/r39-query-implementation-checkpoint-20261016-001/archive-manifest.json)，5,338,098字节，manifest SHA `92645f907d0048e325fafe178efaeb87f7d4d0c210801fc419a74dde643c315c`。包含当前源码、金额/因素操作器和3个新fixture，D/E不可变构建引用及运行报告。机器状态见work/runtime/r39-progress.json。本归档索引在归档后追加。

下一步继续省份/其他条款的原生选择与完整CPeaceOffer payload授权，补战争角色/领袖/完整费用及实际发送/响应/后果/保存重载，再整合其余阶段、公平信息、常驻模型和长期循环。当前统一peace execute仍未实现；保持游戏暂停，先完成Peace权限隔离再推进冷却。人类说明见[议和接口](docs/议和接口与运行验收.md)。省份研究见work/runtime/peace-term-query-contract-20261016-r39-001/report.md；97d350用0x2940的国家候选不是已经证实的割地入口，勿手写province偏移。完整goal active，常用外交19/19实际路径不等于最终验收完成。

省份静态补充：[RTTI结果](work/runtime/peace-term-query-contract-20261016-r39-001/rtti-vtable-static.md)及[34个候选标签方法表](work/runtime/peace-term-query-contract-20261016-r39-001/f8-vtable-label-map.md)。34表无可关联RTTI，30个唯一+f8方法有界读取；已确认ENFORCED_VASSALAGE、PEACEOFFER_GOLD_DESC、PEACEOFFER_RELEASE、PEACEOFFER_TRANSFER等国家条款标签，未取得省份条款种子。这个范围内的阴性结果不能写成游戏没有省份候选；9927a0仍属于已知vassalization候选上下文，不作为已证实的省份入口。下一轮应区分省份容器/UI路径与该组国家条款，也可沿已证明的共同条款选择入口研究，避免继续在vassal cost上搜索province ID。此补充及索引在归档后追加。

本阶段root与三个worker的全部工具会话均已终态，无整机RAM轮询；当前保留E游戏暂停现场。

## 历史运行：R38C 已查询原生和平提议条件与接受因素（2026-10-16）

当前安装 [R38C](work/runtime/diplomacy-query-20261016-r38-peace-c-evaluation/installation.json)：PID `39144`、session `39144-1dd5d12b54fe9ee`、DLL SHA `b7ad2bedecf0cea8c2667c9feca12016f154cf0d7c44b660e36d974986640166`，45源码。POR玩家、FRA查询国，暂停1454.12.1/raw56545056，载入R37B实际宣战存档。R37业务请求不得重发。R38没有议和提交、日期推进或保存。

[C评价查询](work/runtime/diplomacy-query-20261016-r38-peace-c-evaluation/peace-empty-offer-queries-702e835781914f85b16c1418728828a8/report.json)7查询、15检查通过：ENG preview=-45，978ed0聚合分数=0，两次一致；五项实际因素为国内起义+1、控制首都伦敦−5、战争持续时间−45、军事实力+5、盟友相对实力−1。五项严格row/value/text绑定true，但ID全null；20个新增固定Peace key没有覆盖这组动态因素，下一步追其来源，不靠中文硬映射。TYR native_validity=false故evaluation.called=false/native_total=null。292项全Python在C接入后通过，实际fixture随后定向回放。

[A战争发现](work/runtime/diplomacy-query-20261016-r38-peace-a-contexts/peace-context-queries-bba5359590284c6faa5b27f491059816/report.json)6查询/12检查通过；[B选中空和平提议](work/runtime/diplomacy-query-20261016-r38-peace-b-empty-offer/peace-empty-offer-queries-7858c1ccb0b74bee9ece936723d609a4/report.json)7查询，其中3次构造/三gate查询，14检查通过。FRAENG validity=true/common=false/send=true，原生中文无外交官且冷却至1455.1.2；FRATYR validity=false/common=false/send=true，附庸或联合统治国家不可议和。ENGFRA按信息范围拒绝，没有放宽政策。四组参与国复制和原生析构已验证，完整terms payload权限尚未接入。

统一接口支持19项议和的战争发现，以及白和平的 `{peace_context:{war_id,terms:[]}}` 选中只读查询。战争编号是私有reference登记得到的会话级公开ID；角色/领袖仍未知，不外推为执行身份。人类说明见[议和接口](docs/议和接口与运行验收.md)。C已包含preview/因素和聚合分数查询，B不可变DLL只包含构造和三gate。全goal active，常用外交19/19实际路径与议和完整验收分开记录。金币set/get/limit ABI与direction1索取示例已有静态及历史运行证据，尚未接入当前统一参数接口。继续保持暂停，待Peace权限隔离后再推进至外交官冷却结束。

本轮已完成[构造取证](work/runtime/peace-offer-creation-20261016-r38-001/report.md)、[方法表](work/runtime/peace-action-methods-20261016-r38-001/report.md)、[评价/金币合同](work/runtime/peace-term-query-contract-20261016-r38-001/report.md)及[完整payload接入计划](work/runtime/peace-authority-integration-plan-20261016-r38-001/report.md)。root和三个worker的工具会话均已终态。禁止整机RAM轮询，禁止大型反汇编全读；新增DLL必须新进程。

下一步按[动态因素附录的根复核](work/runtime/peace-term-query-contract-20261016-r38-001/dynamic-factor-next-step.md)执行：先把当前已有ReasonMetadataRecord的caller/构造数值私有记录输出（复用alliance_query_reason_metadata_detail），由bind_rows关联到真实五行，再查询实际caller所在函数。worker新查1c1cf0包装器和1c23a0标签拼接；其候选向量尚未证明对应这五行，1c120f固定−1000也与真实值不符，不先加新的1c21e0 hook。可把私有caller导出与GoldSet/Get/Limit的明确数量查询合并下一D构建，避免每个字段重启一次。

R38查询源码已归档：[252文件检查点](work/runtime/r38-query-implementation-checkpoint-20261016-001/archive-manifest.json)，5,173,304字节，manifest SHA `7c63d877c86ca55c6e6e16cd32a29a50f60ddb1efd4a65e2eb97af96d71f51be`。包括当前源码、7个和平fixture、A/B/C不可变构建及运行报告索引。本文的归档索引和动态因素根复核在归档后追加。最新和平定向16项通过；全Python292项是在C接入整合点运行，随后数值/标志独立核验改动由真实fixture定向覆盖。

## 历史运行：R37C 已重载真实宣战结果（2026-10-16）

当前安装 [R37C](work/runtime/diplomacy-query-20261016-r37-war-c-reload/installation.json)：PID `10060`，session `10060-1dd5d06166db88a`，DLL SHA `e857d611ac21946520f676d272f79d04880d16ad042f8c8456c24ce3a67deb25`，42份源码，复制B不可变构建。POR玩家、FRA接口行动国，暂停1454.12.1/raw56545056。FRA与ENG正在战争中。原业务请求 **r37b_declare_eng_core177_001只发送一次，不得重发**。

B实际执行FRA→ENG、cb_core、省份177、受益国FRA、call_allies=[]，双向交战false→true，完整owned payload/三容器在授权、复制、协议、传输和执行入口间比较。未授权transport及direct入口均实际拦截。direct原报告因把调用返回标志当transport acceptance而failed，追加只读reconciliation后通过。B原execution artifact e11f9c37a95d4f96a9520f202bd9b1d8因receipt双重投影被误记invalidated，再遇after目录未建；代码已修复，原报告保留。[严格回收](work/runtime/diplomacy-query-20261016-r37-war-b-execution/declare-war-reconciliation-readback-applied.json)恢复同请求executed/submitted=true，未重发。

[只读执行恢复](work/runtime/diplomacy-query-20261016-r37-war-b-execution/declare-war-resume-7fcea360f5224bd8a75e577de01859c5/report.json)通过；同目录source-validation-001.json独立来源验证通过，包括真实generic diplomatic_command_observed与consume的wrapper/action/header/seq绑定。旧family-rich entry logger没有War白名单，generic entry logger已记录该命令，不补造旧事件。

存档 `llm_diplomacy_war_eng_core177_20261016_r37b.eu4` SHA `083fd5fc0e98312fdc810c7dbd93be54b538ba17a1aca57bd3ed0fab2f7b00f2`；原三份autosave已恢复。[存档对照002](work/runtime/r37-declarewar-save-pair-20261016-002/report.json)证实新增一场FRA/ENG战争、take_core/cb_core/province177，FRA稳定度1.000→1.000、威望−21.933→−21.933。C重载原报告仅使用不存在的loaded_dll_sha256字段误判，[只读纠正](work/runtime/diplomacy-query-20261016-r37-war-c-reload/declare-war-reload-faae28402fe24dcea02d44e20a70b54a/reload-reconciliation-001.json)19/19通过；无需再次重载。

常用外交实际执行路径**19/19**，完整goal保持active。下一阶段为19项常用议和；非空call_allies、公开战争标识、完整费用、阶段覆盖、保存外来提议恢复、公平信息及模型长期循环均继续。原生war关联值是私有opaque引用，未映射整数ID；帧内war_id/stability字段以null+verified=false公开，存档稳定度证据独立列出。最新全Python277项/6.664秒通过；ledger338、wire210、payload31项pure fixtures通过。机器状态见work/runtime/r37-progress.json，无整机RAM轮询。


R37阶段已归档：[237文件检查点](work/runtime/r37-implementation-checkpoint-20261016-001/archive-manifest.json)，4,988,316字节，manifest SHA `5cec6036a88f2a5f5d26e460b907e0e5ff2380a41de1bb0c24f2c9573d4779e3`。检查点保留A/B/C构建引用和执行、来源、保存、重载报告索引；本索引在归档完成后追加。

议和下一步盘点已完成：[R38集成盘点](work/runtime/peace-integration-inventory-20261016-r38-001/report.md)。已有White Peace和34.400金币的固定v7实验；当前统一接口19项peace只有目录/参数合同，原生执行未接入。最接近普通UI的已知链为页面回调130f080→分配210字节action/598b20→内嵌CPeaceOffer深复制975db0→通用wrapper4e9960/dispatcher14ca110；action vtable1c7b840，handler598f00→CPeaceOffer::Execute9765a0。应先从原生和平页面创建的完整offer做只读查询，保留war/direction/leader/双方role/完整terms；先空白和平，再金币和单省份。不得把目录参数或旧固定脚本当通用原生条款实现。当前C保持暂停，未发送任何R38议和请求。root及三个worker工具会话均已终态，未留分析进程。

## 历史运行：R36E 宣战参数查询和费用预览已接通（2026-10-16）

当前安装为 [R36E](work/runtime/diplomacy-query-20261016-r36-war-e-selected-context/installation.json)，PID `9628`、session `9628-1dd5cfa62d4cf6c`、DLL SHA `997315c3919edf5985b5af7faf1354cdb87d677972e6f561ca54802772277d7f`，38份源码。葡萄牙POR玩家，法兰西FRA接口行动国，暂停1454.12.1/raw56545056。载入的仍是R35I取消伦斯特结果存档，SHA `6adfdce8dd608eb65b054dada26804dac0f184f07a14428e6eef9b15d0f4b0d9`。本阶段只有查询，没有宣战、日期推进或保存；common实际执行仍18/19，全goal active，19项议和与最终整合均保留。

原生实际结果：A五目标默认规则查询9项检查通过；C五目标候选查询11项通过，ENG有8条cb_core+4条cb_conquest，BUR7条cb_conquest，PRO/ORL/POR为0。C report：[40627...](work/runtime/diplomacy-query-20261016-r36-war-c-candidates-fixed/declare-war-queries-40627a42dc8d4a03b421eddc2171bfc4/report.json)。CB key来自候选metadata+18字符串；已证实vtable1d20290的candidate+18为省份ID，+38为受益国家上下文。`ee3550`把候选本体存入UI row+58，`ee7100` clone候选本体；旧报告“clone(candidate+58)”归属错误，实际19个candidate+58均0，修正合同见work/runtime/declarewar-candidate-identifiers-20261016-r36-001/report.md。

统一接口支持 QUERY1 空参数枚举和 QUERY3 显式参数 `{casus_belli:'cb_core',war_goal:{province_id:177,beneficiary:'FRA'},call_allies:[]}`。原生每次重新枚举并唯一匹配，再用d9a960复制候选并交临时action+48，正常析构；没有跨查询使用候选索引。显式no-CB键为 `no_casus_belli`，province=-1。非空call_allies仍待接入。E原四查询已原生完成，费用预览 core177=0稳定度损失；无CB=2000raw/2稳定度，WAREX2000，AE主量20000/附加17640，原生中文说明+2厌战、171国0~17AE。费用整体partial，不能当实际扣费。

E原report因公共reader把候选全集误当选中候选而失败，文件保留：[d348...](work/runtime/diplomacy-query-20261016-r36-war-e-selected-context/declare-war-parameter-queries-d3482330d770494bb3c8f8850bb1e1bd/report.json)。修正后[原事件回放](work/runtime/r36-war-e-selected-context-readback-20261016-001/report.json)通过；随后同一活进程[两次真实统一API调用](work/runtime/diplomacy-query-20261016-r36-war-e-selected-context/live-api-selected-query-0840c41dca4849df9af54db6620914b5/report.json)7项检查全部通过：core177 available且成本0，不存在省份unavailable且不套用默认费用。后者是actual live API证据；回放报告的fixture-ready不是原进程身份。

B候选清理曾崩溃，已用有界dump模块表/寄存器定位：错误vtable+a0读取到文本0x6c006100690074后call；原UI实际直接1739420(begin)。C按原指令修复后通过。[B故障分析](work/runtime/diplomacy-query-20261016-r36-war-b-candidates/failure-analysis.md)保留。C编译监督脚本遇到进程在poll/children之间退出的竞争，DLL与37源码副本经hash确认后直接使用，没有重编译；脚本已捕获NoSuchProcess正常终态。D为仅编译未安装的费用中间构建；worker的declarewar-selection-r37-build3也是未安装构建，不代表R37运行。实际当前为上述E。

下一步核心：完整payload授权/生命周期/协议/transport/generic entry和原生战争结果。已有 `work/native/declarewar-payload.h` 保存owned clone的全部复制字段与三个有界8字节元素容器，纯fixture31项通过，尚未接入ledger。owned逻辑字段为+08dword/+10qword/+18dword/+1cqword/+28/+30/+38/+40/+48/+50/+58qword，排除padding；d9a960只复制这些字段、没有内部重新分配。三容器为+50/58/60、+68/70/78、+80/88/90的begin/end/cap，业务含义仍须结合盟友选择确认。正常发送 `edf8b0 → wrapper4e9960 → dispatcher14ca110` 与已验收家族共用，但不能仅加War枚举而忽略owned/容器。War clone50b920、serializer50ba50、reader50bc40、handler5012c0；现阶段query=true/submission=false。

R36查询实现已归档：[224文件检查点](work/runtime/r36-query-implementation-checkpoint-20261016-001/archive-manifest.json)，4,723,004字节，manifest SHA `532a8e10cb799bf02aa3432539611ccf0a1bf0401775f1c59925a508ce4e2a8f`。检查点包括当时源码、文档和A/B/C/E不可变构建引用；本索引在归档后追加。

人类文档：[宣战接口与运行验收](docs/宣战接口与运行验收.md)。最新全Python268项/5.869秒通过，复盘追加§24；没有整机RAM轮询。root和子代理shell工具均已终态，后续启动或调用前以当前installation/活进程为准。

## 历史运行：R35J 已重载取消附庸结果（2026-10-16）

本轮属于实际进展：E 明确拒绝萨伏依提议；F 从 E 保存的未回应队列恢复该提议、跨一天保持并明确接受；G/H 分别重载接受/拒绝结果通过。I 推进到1454.12.1后原生取消规则通过，法兰西一次取消伦斯特附庸，威望3067→-21933（减少25）；J新进程重载关系不存在、威望与外交官任务/日期一致。常用外交实际执行路径18/19，下一项宣战；19项议和、其他家族保存提议恢复和统一长期整合继续，全goal active。

当前 [J 安装](work/runtime/diplomacy-query-20261016-r35-vassal-j-cancelled-reload/installation.json)属于 PID `26736`、session `26736-1dd5cee546b0b53`，暂停1454.12.1/raw56545056、POR玩家。复制F不可变 DLL及35源码，SHA `8ad9865fb3de6f1eebca5615f0c6c323623227bbd257ca3451ed8c98e104ac7c`。载入 `llm_diplomacy_vassal_lei_cancelled_20261016_r35i.eu4`，SHA `6adfdce8dd608eb65b054dada26804dac0f184f07a14428e6eef9b15d0f4b0d9`。首次J查询超时但进程/帧仍运行，原生结果随后到达；第二次只读重载校验[e2b584...](work/runtime/diplomacy-query-20261016-r35-vassal-j-cancelled-reload/vassalization-reload-e2b58419ab5740dc9177c1e70a1540e3/report.json)通过，没有重新取消。

五个业务请求各一次：`r35b_offer_pro_001`、`r35c_offer_lei_001`、`r35e_reject_vassal_sav_001`、`r35f_accept_saved_vassal_sav_001`、`r35i_cancel_lei_001`，不得重发。I可取消的基线已另存 `llm_diplomacy_vassal_lei_cancel_available_20261016_r35i.eu4`，SHA `10f4ce6857421e2b74c3c04698062d9d26d01f1a7cd3069cd1ceb489699e13ac`，避免重复推进五年。原始三份轮转自动存档在各保存和长推进结束后均已恢复。

E拒绝来源37项、F恢复接受来源49项及G/H/J保存重载均通过。F恢复事件保留原token59、date28/date2c56500920、envoy2，原生队列1，来源明确saved_native_pending。恢复逻辑实现五家族，真实恢复目前只验证Vassalization，不外推到另四家族。I的未授权Offer/Cancel transport/direct四条入口均拦截；Cancel transport原report因错误要求query.submitted字段false失败，root已追加query-contract-reconciliation-001.json，未重发测试包。I取消来源40/40、四条权限来源独立检查均通过，Offer B/C来源回归各40/40。R35已归档：[204文件检查点](work/runtime/r35-implementation-checkpoint-20261016-001/archive-manifest.json)，4,430,521字节，manifest SHA `56f7fb0b667f8f8df22f8d7f334553276e08f9c05409f4bcc26068d3a880f20e`。Python unittest252项通过；无整机RAM轮询。

宣战研究：`work/runtime/declarewar-identification-20261016-002/report.md`定位 selector293b→f0ab40→ee4060 DeclareWarDialog，dialog+1c0持有action，ee75f0生成宣战确认。root发现报告误把ee9740的ScornfulInsult按钮当War：538730是已实测Insult validity，ee9740出现scornful_back。该错误已修正，见work/runtime/declarewar-dispatch-20261016-001。动作合同见work/runtime/declarewar-action-contract-20261016-001：selector293b、factory35a8b0、creator5004b0、size98、vtable1c80d90；+80 legality508de0、+88 common50a0d0、+90 send509e60、clone50b920、serializer50ba50、reader50bc40。War自己的+48对象和三组动态容器仍需CB/目标/盟友语义。**下一原生查询优先edf8b0**：已经确认War窗口ee75f0在无需稳定度确认时直接调用edf8b0；它比对话框完成后的通用0xb回调更接近业务提交链。0xb目前只证明UI回调分派，可能是关闭/刷新，应作为待验证推断，不再无界追UI链。所有worker均已结束并收集工具终态。

人类说明见[附庸接口](docs/附庸接口与运行验收.md)，机器状态见[r35-progress.json](work/runtime/r35-progress.json)。root当前没有活动shell工具session；子代理如有REA工具须各自收集终态。以下为各独立进程历史记录，旧“当前”只描述相应阶段。

## 历史运行快照：R35D 已重载普通附庸，正推进停战到期场景（2026-10-16）

当前安装 [R35D](work/runtime/diplomacy-query-20261016-r35-vassal-d-active-reload/installation.json)，PID `16380`、session `16380-1dd5ce421c03fcd`，DLL SHA `ef8d54dc0b86a92cc64b21b8ac48ee0a07521ba20681b442f767078437528b2b`。D 复制 C 的32份源码和不可变 DLL，一进程只安装一次。

实际请求各一次：B `r35b_offer_pro_001` 原生 rejected，原报告因错误要求外交官快照不变而失败，[只读回收通过](work/runtime/diplomacy-query-20261016-r35-vassal-b/vassalization-resume-c83f2ec716f64cf3b4d63ae3d5969a90/report.json)；C `r35c_offer_lei_001` 原生 accepted，FRA→LEI false→true、type vassal。C 保存 SHA `c9b7eb4d27257f66a9238485166346eda8ae81f470b0b887b2e374010298ea87`，日期1449.11.17/raw56500920，D [重载](work/runtime/diplomacy-query-20261016-r35-vassal-d-active-reload/vassalization-reload-82c9a446e4ef4594913f3bc50e2452c6/report.json)通过；外交官数量/任务/出发与归途日期也实际匹配。common实际执行路径17/19，剩宣战、取消附庸；入站附庸、19议和及整合继续，全goal active。

D推进9天至raw56501136，2名外交官已归国，但Cancel原生返回“受和约保障的附属关系不能被取消”。[存档读取](work/runtime/diplomacy-query-20261016-r35-vassal-d-active-reload/lei-protection-save-001.json)记录1449.11.17为truce起点，shipped defines.lua TRUCE_YEARS=5。当前root exec session **6899** 正执行 advance-context-15cafe7180a9434ea761ca47d8c694a3，目标raw56544744（预计1454.11.18）。前一 advance418f...第8段已经完成但心跳滞后一天，已通过只读resume d024...确认且未重发；新脚本仅在完成后等最多3秒健康日期同步，2项定向测试通过。继续先poll同一live handle；不要重发控制或业务请求。

长推进自动存档恢复待办：[preservation记录](work/runtime/diplomacy-query-20261016-r35-vassal-d-active-reload/long-advance-autosaves-preservation.json)指向 C/save-backup 中三份已验证原始轮转存档。推进结束后恢复这三份，其他存档保持原状。不要用新生成的自动存档覆盖原备份。D成熟场景先另存，避免后续重复等待5年。

根代码树已经准备入站实验fixture（未集成main/build），仅为独立实验将FRA20省发展降到60并给SAV联盟/关系，实际提议仍要原生UI/规则/传输，LLM明确接受/拒绝；不可把fixture当业务执行。下一步先完成D取消/威望/保存重载，再对独立分支验收入站。DeclareWar既有证据清单在work/runtime/declarewar-integration-inventory-20261016-001；目前没有通用UI selector已证实。人类说明见[附庸接口](docs/附庸接口与运行验收.md)。全Python253 tests/96subtests通过；后加心跳故障2项通过；无整机RAM轮询。

## 历史运行快照：R35A 附庸十项查询通过（2026-10-16）

当前安装为 [R35A](work/runtime/diplomacy-query-20261016-r35-vassal-a/installation.json)，PID `43844`、session `43844-1dd5cdf617855a2`，DLL SHA-256 `1af63afba507a19803daec09a1ec5ad9afe2a2861d83c72ecdb9a87386a7565f`。从 R34F 宿敌组合存档启动，POR 玩家、暂停、1449.11.17/raw `56500920`。本进程只安装一次；A 开放 Vassal 查询，执行能力仍为 false。

[十项真实查询](work/runtime/diplomacy-query-20261016-r35-vassal-a/vassalization-queries-08b4e54e917040af8bddeaa95f6513f1/report.json)已通过。ORL/AMG 是 FRA 的 appanage，原生取消动作当前隐藏且禁止；PRO/SAV/POR 与 FRA 无附属关系。Offer 诊断导出结盟、至少+190关系和目标和平条件，POR 另有发展度上限。关系状态独立于动作合法性；这批合法性均为 unavailable，尚未取得可用目标接受度。人类说明见[附庸接口](docs/附庸接口与运行验收.md)。常用外交实际执行仍为16/19；全goal保持active。

工作树正在接入下一构建：Vassalization family8 的授权执行、Cancel关系/威望后果、外来提议与每日AI选择保持，以及固定 TEST_ONLY 结盟/关系场景。工作树代码尚未加载到A；不可对A推进日期来声称外来Vassal已受控。root负责native/main/执行整合与实际运行，royal_api负责Python执行与结果，royal_wire负责固定场景准备，royal_lifecycle负责单次执行操作器。已执行Rival请求不得重发。启动helper已经终态，查询操作器已终态，当前没有待消费业务请求。

## 历史运行快照：R34G 宿敌两项已保存并重载（2026-10-16）

当前安装为 [R34G](work/runtime/diplomacy-query-20261016-r34-rival-g-reload/installation.json)，PID `32616`、session `32616-1dd5cd6b1a62182`，DLL SHA-256 `c84b03ad3194fc1418977f5c6c98a0b4bf837964fbb918481e317d76b3d22e19`。POR（葡萄牙）玩家，FRA（法兰西）接口行动国，暂停在 1449.11.17/raw `56500920`。G 复制 F 的不可变 DLL 与 29 份源码，没有重新编译或重复注入。

F 的两个业务请求各执行一次：`r34f_remove_cas_001` 移除 CAS，宿敌数 3→2、外交点 581→480、cost101；`r34f_set_bur_001` 设置 BUR，数量 2→3、外交点保持480、cost0。Remove 曾被 Python 错误字段名误记为 invalidated；已通过严格唯一回执+实际事件回收为 executed，原失败和审计证据都保留，未重发。当前 CAS absent、BUR active；ENG/ARA 原宿敌保留。

组合存档 `llm_diplomacy_rivals_cas_removed_bur_set_20261016_r34f.eu4` SHA-256 `2c91fca284f985dc88adcb4e88511e242904ddc5e94626a255cd624707294c2d`，日期1449.11.17，40,720,906字节。[G重载报告](work/runtime/diplomacy-query-20261016-r34-rival-g-reload/rival-reload-480ee65102ab4d449176e0382b7f08a8/report.json)全部通过；[G公共投影检查](work/runtime/diplomacy-query-20261016-r34-rival-g-reload/public-projection-validation-001/report.json)确认执行支持/授权与游戏合法性分离，Remove费用amount101、unit外交点、scale1。完整路径和各报告见[宿敌说明](docs/宿敌接口与运行验收.md)。common 实际路径更新为16，剩余宣战、提议附庸、取消附庸及19议和；全goal保持active。

D 已自然推进至宿敌保留期结束并保存成熟上下文，F 已从该命名存档启动；长推进前的三份自动存档已从D原备份恢复。F保存组合结果也恢复了三份自动存档。日期推进脚本现在能只读回收 reached=false 的明确终态；save helper已修复轮转期间FileNotFoundError和稳定窗口；startup dialog探针只访问已知UI对象图，私有堆扫描已关闭，G安装实际使用已验证的server UI route。

R34 已归档：[181文件检查点](work/runtime/r34-implementation-checkpoint-20261016-002/archive-manifest.json)，3,969,733字节，manifest SHA-256 `664feff6298ea559937c2d7301bd58d83cfce581becb081f3e2d49be5cbceb51`。归档保存当时源码、文档和运行状态；本归档索引和下段Vassal交接在归档完成后补入。全Python回归243 tests / 96 subtests通过，两个F来源链各62/62通过。所有root及子代理工具session均已收集终态，当前没有待消费控制或业务请求。全goal保持active。

下一家族Vassal的[静态报告](work/runtime/vassal-identification-20261016-001/report.md)已完成：Offer/Cancel共用selector `0x2940`、40hex字节动作、vptr RVA `0x1c7fd20`，+38非零/零切换模式；handler `0x51d840`、legality `0x51f050`、clone `0x51fa30`、score `0x51fae0`，公共wrapper/serializer/clone日期变换与既有外交动作一致。普通factory为 `0x35d240`，UI creator/visibility仍须结合已知调用合同确认；Cancel菜单会随关系类型选择CANCELVASSAL/BREAKVASSAL。+18由通用构造与UI填充，业务语义未单独确认，不能凭静态占位值构造业务请求。下一步先接入Vassal实际查询，读取当前关系、合法性和接受因素，再完成Offer/Cancel授权执行、响应和保存重载。非FRA原生外交选择、军事与经济AI继续保留。任何操作前重新读取installation；禁止重发两个已执行Rival请求。

## R34D 历史阶段： 宿敌查询、授权拦截与非 FRA 转发观察（2026-10-16）

本阶段已归档 [R34 源码检查点](work/runtime/r34-implementation-checkpoint-20261016-001/archive-manifest.json)：166 个文件、3,616,331 字节，manifest SHA-256 `22681ab686344a4b6cb55f559b47420288bcbcd43da644a648dcb317461ca378`。归档保存当时的代码与文档；本段归档索引在归档完成后补入。全部工具与子代理会话已收尾，当前安装没有待消费请求。全 goal 保持 active。

R34D 在和平上下文中完成了宿敌查询和 FRA 授权负例验收。新进程安装记录为 [installation.json](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/installation.json)，PID `45680`、session `45680-1dd5ccbe10d5b6e`，DLL SHA-256 `6816c581d45fa89b7db6225ede5a7cb67cc047383d280931697a8881f1678fc8`。载入的存档是 `llm_ai_whitepeace_accepted.eu4`，SHA-256 为 `e0f6be661621272102dd02576ae29a20011f78b076e40d17d769fbc1378de8f0`。POR（葡萄牙）是玩家，FRA（法兰西）是查询与授权控制国；查询和授权测试边界保持暂停，日期为 1445.6.9/raw `56462016`。

R34D 的 [八项查询报告](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/rival-queries-84f4d795e9224165a591235b860d5229/report.json)同时调用 `set_rival` 与 `remove_rival`，并分别读取宿敌成员关系和原生命令条件。FRA 当时处于和平状态，`diplomatic_power_raw=143`、`rival_count=3`、`max_rivals=3`。ENG（英格兰）和 CAS（卡斯蒂利亚）是当前宿敌；ENG 的 Remove 诊断指出保留至 1449.11.11，CAS 的 Remove 诊断指出保留至 1449.11.16。BUR（勃艮第）和 SAV（萨伏依）当前不是宿敌，但两者的 Remove 原生条件函数都返回 `true`；独立的成员关系读取仍返回 `rival_active=false`。Remove 查询导出的外交点费用原始值为 `101`，可负担性为 `true`，费用单位和完整附加费用仍按原生字段保留为未完全解释。查询结果把候选资格、成员关系和命令条件分开记录，避免用任一布尔值替代另外两项。

[R34D 授权负例报告](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/rival-authority-test-53d055de8a5c407a98e5270e8c1a4dd8/report.json)发布一次精确的 `RIVAL_GUARD_TEST1` 请求，覆盖 `set_rival`、`replace_rival`、`remove_rival` 三种原生处理器的 direct 和 vtable 路径。六个入口都记录 `allowed=false`、`reason=FRA_SUBMISSION_UNAUTHORIZED`、`canonical=true`、`shape=true`；原生测试的 `before` 与 `after` 相同，宿敌状态、数量、上限、外交点和战争状态没有变化。该报告还确认没有业务执行事件或外交业务提交。

随后进行的 [35 天生命周期观察](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/lifecycle-observation-5ca7f6c019324be3b636e832acbe55a5/observation-report.json)把进程推进到 1445.7.14/raw `56462856`，并恢复暂停。观察到五条非 FRA 的原生命令转发：`ENG→CAS`、`TAH→AGG`、`ENG→DAN`、`MUL→SRH`、`KSH→MUL`；五条记录均为 `set_rival`、`allowed=true`、`canonical=true`、`shape=true`。这项观察证明 Rival 处理器会把非 FRA 来源交还原生处理路径。随后对旧存档和新存档做了[流式 NPC 后果对照](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/npc-rival-save-effects-20261016-001/report.md)，并保存[结构化证据](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/npc-rival-save-effects-20261016-001/evidence.json)：五个 actor 的 `rival.country` 均新增对应目标，ENG 新增 CAS/DAN，TAH 新增 AGG，MUL 新增 SRH，KSH 新增 MUL；FRA 的直接宿敌仍为 ENG、ARA、CAS，成员和日期没有变化。这证明非 FRA 转发已经产生了原生 NPC 宿敌成员变化，但不把结果归入 FRA 授权执行。观察阶段保存了 [存档观察报告](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/save-observer-report-1792086435528801700.json)及存档 `llm_diplomacy_rival_authority_observed_20261016_r34d.eu4`，SHA-256 为 `092af9ef02b8d2fede03d3155fee3b8746a26273c2b189d70eba8bf47b35d5fe`；该存档尚未完成新进程重载验收。

[七家族十四项查询回归](work/runtime/diplomacy-query-20261016-r34-rival-d-peace/family-query-regression-e42fa13fca5e42c692e268daa2546a46/report.json)在同一安装中通过，查询没有增加 common14。桥接回归当前记录为 233 tests / 96 subtests；R34D 的真实费用测试已纳入统计。R34D 已经能稳定读取和平状态中的 Rival 成员、原生命令条件、费用原始值和诊断文本，也能拦截 FRA 未授权入口并保持其他国家的 Rival 命令转发。Rival 的授权业务提交、真实关系变化、保存后新进程重载，以及 `full_rules_complete` 所代表的完整费用与执行前规则验收仍属于下一阶段。下一步是为满足国家命令、传输协议、授权和保留期限的场景建立独立正向执行测试；这项工作不增加 common14，直到真实业务结果完成。

R34C 的安装失败原因和 D 的对照修复记录在 [failure-analysis.md](work/runtime/diplomacy-query-20261016-r34-rival-c-peace/failure-analysis.md)：C 把 32 字节数组按指针传给模板读取，D 改为数组引用后在新进程通过八项查询和授权负例。该文件还记录了启动确认探测的优化方向；它不会改变本轮已经取得的 Rival 结果。

## R34B 历史阶段：宿敌候选查询（2026-10-16）

R34B 在新进程中补齐了宿敌候选资格查询。安装记录为 [installation.json](work/runtime/diplomacy-query-20261016-r34-rival-b/installation.json)，PID `17152`、session `17152-1dd5cc7d790cfab`，DLL SHA-256 `0ad940a20adee1bd600960eac492baa4585a840ccca0116243829c70ca8254be`。POR（葡萄牙）仍是玩家，游戏保持暂停，查询日期为 raw `56465136`。

R34B 没有发布执行请求、推进日期、保存游戏或重新安装 DLL。第一组查询报告 [c5765830](work/runtime/diplomacy-query-20261016-r34-rival-b/rival-queries-c5765830ea7b4459b39bb79e78e3229e/report.json) 覆盖 BUR（勃艮第）、ENG（英格兰）、HAB（奥地利）和 CAS（卡斯蒂利亚）：四个目标均存在，候选资格均为 `true`；BUR 与 ENG 的宿敌成员状态为 `true`，HAB 与 CAS 为 `false`。第二组报告 [8316ea](work/runtime/diplomacy-query-20261016-r34-rival-b/rival-queries-8316ea7151874f31992d4ccf3f188e22/report.json) 覆盖 SAV（萨伏依）、GEN（热那亚）和 LAN（佛罗伦萨）：三个目标均存在，候选资格均为 `false`，宿敌成员状态均为 `false`。

两组报告都记录 `ui_war_allowed=false`、`native_command_validity=false`，而 `full_rules_complete=false` 表示完整费用与执行前规则验收仍待补齐；候选资格、原生命令条件和宿敌成员状态是三个分开的字段，不能互相替代。两组查询的 POR、暂停、日期、四份快照、native event slice、DLL/build/session 绑定和无副作用检查均通过，common14 仍为十四条已实际执行路径。候选查询已经在运行时通过正反目标对照，但宿敌 Set/Replace/Remove 的完整执行、费用、保存后果和新进程业务重载仍未开始。

为准备后续和平场景，另有[旧存档流式基线报告](work/runtime/r34-rival-peace-baseline-20261016-004/report.md)：`llm_authorized_whitepeace_v7.eu4` 在 1445.8.3 捕获到 FRA（法兰西）参与的现役战争，不适合作为和平基线；`llm_ai_whitepeace_accepted.eu4` 在 1445.6.9 未捕获 FRA 现役战争，且 `last_war_ended=1445.6.3`，可作为和平上下文候选。两个旧存档只用于准备上下文，不属于 R34B 接口完成证据。[外交点结构取证](work/runtime/r34-rival-power-structure-20261016-001/report.md)确认 FRA 国家块存在 `powers={0 0 0}` 的无名三元向量，但分量顺序和外交点语义尚未验证；费用与变化对照仍以新进程公开的 `diplomatic_power_raw` 为准。

## R34A 历史阶段：宿敌查询（2026-10-16）

R33 普通侮辱与轻蔑侮辱已经完成真实执行、效果核对、保存重载和阶段归档；当前阶段转为 R34A 宿敌查询。R34A 的实测安装记录为 [installation.json](work/runtime/diplomacy-query-20261016-r34-rival-a/installation.json)，PID `44680`、session `44680-1dd5cc4715ab2b2`，DLL SHA-256 `a329187c84796273c394f814cf8ace43c420b8d9afe98b8a7c252d4b2817a2aa`。该记录显示 POR（葡萄牙）是玩家，游戏处于暂停状态，日期为 1445.10.17/raw `56465136`。

本阶段为只读查询。公开动作沿用目录中的 `set_rival` 和 `remove_rival`，由 FRA（法兰西）在 `initiate` 阶段查询目标国家；查询不会提交外交请求、推进日期、保存游戏或安装 DLL。原生宿敌列表显示，FRA 当前有三个宿敌：ENG（英格兰，1444.11.11 起）、ARA（阿拉贡，1444.11.11 起）和 BUR（勃艮第，1444.11.15 起）。[流式存档基线](work/runtime/r34-rival-save-baseline-20261016-001/report.md)和[识别报告](work/runtime/rival-identification-20261016-root-review-001.md)保存了这三个成员及其起始日期。

[R34A 六项查询报告](work/runtime/diplomacy-query-20261016-r34-rival-a/rival-queries-e2be4ced4a634febbebbc63c5cd121f7/report.json)对 BUR、ENG、HAB（奥地利）分别执行 `set_rival` 和 `remove_rival` 查询。BUR 与 ENG 的 `rival_active=true`，HAB 的 `rival_active=false`；六条 native `native_rival_inspection` 事件均与 action、recipient、日期和 session 相符。当前 FRA 的 `rival_count=3`、`max_rivals=3`、`diplomatic_power_raw=162`、`at_war=true`。六项查询的原生动作条件均返回 false，公共结果因此把当前动作合法性标为 `unavailable`；这项结果描述当前战争、名额和关系状态下的动作检查，不改变独立读取的宿敌成员状态。Remove 事件的原生诊断已由 `eu4_escape` 解码为“不能在战争期间移除宿敌”，公开 `queries.json` 的 `native_diagnostic.text` 保留了这一可读原因。

本阶段的检查已经通过：新进程 ready、POR 玩家槽位、暂停日期、四份边界快照、`native_rival_query` 能力、DLL/build/session 一致性、六条 native 事件、关系状态、资源整数和公开结果指针隔离均已核对。宿敌没有对方接受度，因此 `acceptance.applicability=not_applicable`；候选列表与完整 UI 规则尚未接入，`candidate_eligibility_available=false`、`full_rules_complete=false`，这两个字段明确表示查询范围，不代表查询失败。[七家族十四项查询回归](work/runtime/diplomacy-query-20261016-r34-rival-a/family-query-regression-a80b3fa3e1914451bb5096754525de0b/report.json)同时通过，且没有发布执行请求。

R34A 尚未开放宿敌执行、保存结果或新进程业务重载。下一步需要接入 `possible_rival_entry` 候选路径、完整 UI 合法性和费用规则，区分 Set、Replace、Remove 的构造与提交语义，再为 FRA 建立授权执行和结果查询。常用外交的已实际执行路径仍为 **14 项**；R34A 的宿敌查询不增加这个计数。R34 的详细调用方式和字段解释见[宿敌接口与运行验收](docs/宿敌接口与运行验收.md)，阶段状态见 [r34-progress.json](work/runtime/r34-progress.json)。


## R33 已结束：普通侮辱与轻蔑侮辱

当前安装是 [R33C](work/runtime/diplomacy-query-20261015-r33-insult-c-reload/installation.json)，PID **38380**、session **38380-1dd5cbbec883c84**、DLL SHA `34236f3553285411013e98eff742e2d03a820c14f777b7fa67fe7779199194ea`，POR玩家、暂停、1445.10.17/raw56465136。A/B进程已结束，C复用B的不可变构建；每个进程只安装一次。root 安装65840/89326等工具session均已收集终态。未做整机RAM检查。

Insult family7、selector2947、VT1c7f6b0、对象72字节。普通+40=-1，轻蔑+40为合法候选数组索引。候选库859910返回dataset，+48指针数组/+54数量；858fc0复用原生候选条件；859430生成实际本地化文本。clone538e50完整复制+40并将date28复制到date2c，serializer539270保存+40。新增insult-query.inc及两个公开动作、query2/execution v2参数传输；授权精确匹配参数，NPC单方侮辱不进入LLM待处理队列。

[A首批真实查询](work/runtime/diplomacy-query-20261015-r33-insult-a/insult-queries-48be048004ed4e8ba20334a7c3f6ecf0/report.json)暴露API漏列Insult完整规则分类，已经修复并保存真实fixture。SAV common gate禁止，ENG原生诊断“我国处于战争状态”；B中BUR/GEN选定候选0查询通过。轻蔑空参数只发现候选，选择具体ID后才检查完整合法性。B查询已导出原生轻蔑威望费用5000。

已提交两个唯一业务请求：普通 `r33b_insult_bur_001`（FRA→BUR，1445.10.6）和轻蔑 `r33b_scornful_gen_001`（FRA→GEN，候选0，1445.10.11）。普通原生修正0→-50000、威望8086不变；轻蔑0→-100000、威望8086→3086。普通提交后API类方法误用self，原报告7d79751失败；只读resume9f01cf通过，**绝不重发**。旧execute_call_count=0不能否定原生submitted；操作器现在在调用前记录，并从native/journal判断提交。轻蔑51f99b首次执行报告通过。direct普通/transport轻蔑无授权负例均被UNAUTHORIZED_FRA_INSULT拦截。

组合存档 `llm_diplomacy_insults_bur_gen_20261015_r33b.eu4` SHA `bbc1fa731e5e8bf9fe129fee00c968625733c0d15860487d8693f5765eb5a23d`，1445.10.11。C新进程两份重载报告e3f843/4540e2均通过，GEN同时匹配B结束时控制/外交官/意见与威望语义。独立流式存档确认BUR insulted=-50.000、GEN scornfully_insulted=-100.000、FRA prestige8.086→3.086，比例1000。推进5+1天后外交官id3空闲、可用1，侮辱修正仍存在；已保存 `llm_diplomacy_insults_returned_20261015_r33c.eu4` SHA `470d9546c4183ce481d0e0d02f843c7c11749f5b3bc475b89cd636742acfa825`，可作下一家族基线。C七家族十四项查询回归4eccec通过，另有两国侮辱查询d04f80通过。

root拥有native、HANDOFF、主文档、进度与归档；royal_api已完成API/catalog/tests、source validator及费用投影；royal_wire已完成operator/reload/savepair与两组独立存档；royal_lifecycle已结束Rival有界识别，全部工具session终态。普通generic-resume-005/轻蔑scorn-004各36项正向及11项负例来源通过；实际generic入口通过指针和协议头与完整payload记录关联，报告列明入口未直接导出的字段。统一costs.items现在输出普通0、轻蔑5威望，raw/scale1000均保留；C费用实际查询b67a90通过。全桥接 **219 tests / 71 subtests**、API定向10、ledger285/wire165通过，git diff --check通过（仅原有LF/CRLF提示）。使用方法和证据见[侮辱说明](docs/侮辱接口与运行验收.md)。

R33主路径已归档：[153文件检查点](work/runtime/r33-implementation-checkpoint-20261016-001/archive-manifest.json)，3,326,108字节，manifest SHA `516b7c9d8d229a77a5ea41c8585cbe23960ed2e142c0fc4391ab9fb83754f435`。下一步R34 Rival：[识别报告](work/runtime/rival-identification-20261015-001/report.md)定位Set为2aaad0/table1c55180/RIVAL_SET，Remove为2aca90/table1c54ab0/RIVAL_REMOVED，共用2ab8b0有两个分支。**Set/Remove都OR入关系行+46 bit20，所以该位不能作为宿敌是否存在的查询依据**；需另找宿敌列表或原生成员判断，见[root整合说明](work/runtime/rival-identification-20261016-root-review-001.md)。2948/2949已排除（Gift/Claim）。尚缺原生命令参数/构造或序列化、UI合法性与费用/资源契约，不能直接套用普通Insult工厂。优先按命令表引用和UI调用者继续有界查询。其余五项常用动作、十九项议和、已保存pending与长期统一运行均保留。

机器状态见 [r33-progress.json](work/runtime/r33-progress.json)，参数ABI见[最新报告](work/runtime/insult-parameters-20261015-001/report.md)。原goal保持active，R32运行阶段已经归档，后续所有常用外交／十九项议和要求继续有效。

## r32 历史阶段：请求与取消军事通行权

原 goal 保持 active。上轮临时答复了 POR/PRO 国家角色问题；本轮继续实际运行，接受卡斯蒂利亚自然提议、保存组合结果并在新进程重载。当前安装是 [R32E](work/runtime/diplomacy-query-20261015-r32-military-access-e-reason-branches/installation.json)，PID **15020**、session **15020-1dd5cac68ec6f5b**，DLL SHA `581918df50f4d616e3b2ad60f2c7d6412980fb22ecf1bd1718fff192b9109195`。玩家 POR（葡萄牙），暂停，1445.10.6/raw56464872。所有 root 工具 session 已收集。R31D 和 R32A/B/C/D 已结束；每个进程只安装一次。

Ask/Cancel 的 selector 为2943，虚表为1c7fb70。actor 是请求通行国，recipient 是授予国；actor 持有的 relations[recipient] 表示 actor 在 recipient 境内的通行权。Offer2944是独立动作。四个统一工具、示例及运行报告见[军事通行权说明](docs/军事通行权接口与运行验收.md)，机器进度见[r32-progress.json](work/runtime/r32-progress.json)。

已执行五个唯一业务请求：A中勃艮第原生AI拒绝法兰西，萨伏依原生AI接受法兰西；B中法兰西明确拒绝萨伏依反向请求，原有法兰西→萨伏依权限保留；C中法兰西取消萨伏依授予的通行权，随后接受卡斯蒂利亚自然提出的请求。C的[取消报告](work/runtime/diplomacy-query-20261015-r32-military-access-c-direction-reload/military-access-execution-75dce8c414b04a20a4a833c2bf67c0cd/report.json)和[自然提议接受报告](work/runtime/diplomacy-query-20261015-r32-military-access-c-direction-reload/inbound-response-462a74fd7d134c578e83b2fd056ecf6a/report.json)均通过。两种出站分支分别通过50项正向、16项负例来源检查；B入站拒绝通过47项独立来源检查。

C的GEN测试提议在10月2、3、4日实际命中每日选择hold。10月6日接受前复查返回PENDING_NOT_ACTIVE，唯一请求 r32c_accept_gen_access_001 为invalidated、submitted=false，没有重发；队列移除的具体原因待查。相同观察中，卡斯蒂利亚于10月4日自然向法兰西请求通行，10月5、6日均被hold，10月6日由接口以 r32c_accept_cas_access_001 明确接受，state2/variant1、关系false→true、pending_removed=true。证据见[五天观察](work/runtime/diplomacy-query-20261015-r32-military-access-c-direction-reload/lifecycle-observation-e8af4ca6ea7b49dfbd749c42f14653b0/observation-report.json)。

C保存为 `llm_diplomacy_access_sav_cancelled_cas_accepted_20261015_r32c.eu4`，SHA `b0e316d1df7e7bce853226e3638c5e85164eba34d0ab35f281bd97672c4d1ca2`，38,692,966字节。D已载入该存档，使用与C相同的不可变DLL；[七家族十四项实际查询](work/runtime/diplomacy-query-20261015-r32-military-access-d-final-reload/family-query-regression-46846f0912c34518b27706501c3a464e/report.json)通过。[D组合重载](work/runtime/diplomacy-query-20261015-r32-military-access-d-final-reload/military-access-directions-reload-b7cff90f3e44482aa508b856459d332f/report.json)13项通过，四方向分别为无、无、有、无，外交官语义已记录且FRA可用1、id3空闲。

当前分工：root拥有native与metadata表、HANDOFF/总文档/进度和归档；royal_api拥有API/catalog/tests、出站来源validator和流式存档parser；royal_wire拥有wire/formatter、操作器、入站来源validator及军事通行权说明，正在完成D组合方向验收；royal_lifecycle只读识别后续侮辱动作，不再修改metadata。E在既有row ctor捕获中按thisrow相对偏移读取原生文本开关与宗主分支单字节，已实际命中BUR标准和HOL宗主两种因素ID。独立26项fixture通过；E四国8查询和七家族14查询通过，未新增业务提交。API已修复真实inactive事件投影，全桥接209 tests/71 subtests通过；C自然来源46项、可复现GEN/CAS综合22项独立验证均通过；E条件化因素独立报告确认21行及标准4行／宗主2行分支均通过，前缀与原始事件slice已固定。Royal默认fixture来源37项回归通过。R32已完成[138文件检查点](work/runtime/r32-implementation-checkpoint-20261015-001/archive-manifest.json)，3,050,539字节，manifest SHA `b0bc667d3ae23ed365188d86bae4c1ec308629a10383d50005bb1817df3cc100`。下一步继续识别普通／轻蔑侮辱的原生入口。

R31检查点：[122文件](work/runtime/r31-implementation-checkpoint-20261015-001/archive-manifest.json)，2,698,439字节，manifest SHA `fa25b0e074bd3ca7a3cff734b16855f0bc9b0d0fceb7c4148a80b91bae4cd66e`。原goal的其余七项常用外交、十九项议和、已保存pending重新登记及长期循环继续在范围内。

## 下一阶段 r33：普通／轻蔑侮辱已定位核心入口

[最新静态报告](work/runtime/insult-integration-20261015-001/report.md)补充了旧识别报告的unknown：selector2947、72字节对象、VT1c7f6b0，parameter+40为signed int32，工厂默认-1普通，非负进入轻蔑文本分支；handler537920、validity80=538730、display88=538a00、description70=538ab0、cloneb0=538e50、dtor129500、diplomat100=true。539570及53a630系列已证明为Gift，不能混入侮辱。下一步查clone/serializer参数保留与scornful候选/DLC/威望规则，然后实现四工具与实际执行。当前仍是R32E安装，尚未发送侮辱。

royal_api/royal_wire已完成并无遗留session。royal_lifecycle未按要求及时返回交接，root已中断该agent并接管；最新CLI539570记录exit0/completed，REA MCP open=false，缓存cache.lock不存在，任务路径匹配的分析进程无。不要重新跑此前已完成函数查询或全量分析；既有证据在insult-identification-20261015-001。root工具session全收集。

## r31 历史运行层：支持独立双向分支已运行验收（2026-10-15）

当前为 [R31D安装](work/runtime/diplomacy-query-20261015-r31-support-d-accepted-reload/installation.json)，PID **22984**、session **22984-1dd5c9901da1376**、DLL SHA `533cb43065e20f66934baef962e504d6d8d7c7309797ad5078b79a4aff04b2da`。POR玩家、暂停、1445.8.21/raw56463768；法兰西支持挪威，瑞典和荷兰支持关系不存在。外交官id3空闲，可用数1；原有Improve AMG/PAP、Spy BUR任务继续活动。A/B/C已结束，各进程只安装一次，所有root工具session已收集。

Support已接入生命周期、0x40正常工厂、查询、传输、family5授权、原生NPC回应、FRA pending队列及每日选择hold、入站响应和四工具合同。新增 `support_independence`（需回应）与 `revoke_support_independence`（单方）。后者为27字符，wire/native结果容量已扩为28；4组C++ fixture通过，ledger250、execution wire128；bridge全套191项和真实事件修正后的Support定向9项通过。已实际完成出站接受／拒绝、撤销、入站跨日接受／拒绝与保存重载。[面向人类的接口说明](docs/支持独立接口与运行验收.md)。

[五目标查询](work/runtime/diplomacy-query-20261015-r31-support-a/support-independence-queries-9bf1deccef644b96a056d65c8c6c257a/report.json)已通过：HOL合法、预测拒绝−921；NOR合法、预测拒绝−999；SWE合法、预测接受49；FOI为己方附庸禁止支持，SAV双方均独立禁止支持。初次查询ef92报告因API只允许Alliance/Royal接受评分而失败；修正后原生评分正常返回，原失败保留。[原生ABI与方向报告](work/runtime/support-independence-integration-20261015-001/report.md)纠正旧报告：FRA→HOL为提供支持，HOL→FRA为请求支持，两种情况下支持方均为FRA。+120=50f160、3a8270返回有符号总值与48字节原因行；+c8是AI优先级，未混作接受总值。

A已完成[无授权直接入口拦截](work/runtime/diplomacy-query-20261015-r31-support-a/authority-test-25a6694c06dd42ec89d70626a7997f5a/report.json)，唯一请求 `r31a_support_hol_001` 被荷兰原生 AI 拒绝。API 与操作器最初误读 mock 的 `mode` 字段，已按实际 DLL 的 `native_variant` 修正；[原请求只读恢复](work/runtime/diplomacy-query-20261015-r31-support-a/support-independence-resume-0b32873770c74c849a23df8103246b24/report.json)通过，没有重发。[HOL独立来源验证](work/runtime/diplomacy-query-20261015-r31-support-a/support-independence-source-validation-ac9719ae2d824f19aec3566ddd1ca418/validation.json)和[SWE接受来源验证](work/runtime/diplomacy-query-20261015-r31-support-a/support-independence-source-validation-40206a439f1440f6b76026d986e8ac32/validation.json)均通过。

已保存HOL拒绝状态为 `llm_diplomacy_support_hol_rejected_20261015_r31a.eu4`，SHA `ae4c3727d5af5be7a88d67c7e5855626231feadf20ca3d4eb2a31074cd53a232`，38,137,692字节，6月5日。[保存报告](work/runtime/diplomacy-query-20261015-r31-support-a/save-observer-report-1792061345819430700.json)已成功并恢复三份原autosave。

6月10日唯一请求 `r31a_support_swe_001` 被瑞典原生 AI 接受，[执行报告](work/runtime/diplomacy-query-20261015-r31-support-a/support-independence-execution-bd1cff0d09fe4ed3aa60e02496279465/report.json)通过，支持关系 false→true。活动存档 `llm_diplomacy_support_swe_active_20261015_r31a.eu4` SHA `1cb3405c475ef8d28b20e124a49af59a2f341f7c08648a349a1e564f6beeaa9b`；[B新进程重载](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/support-independence-reload-e98f54ba138e4c0ea58fe1c328910101/report.json)通过。B的[五目标查询](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/support-independence-queries-6bd1ab381e894ed8b8a6c6c5be0a8204/report.json)确认瑞典存在、荷兰不存在，荷兰/挪威13项接受因素均有已核验原生标识。静态绑定见[原因报告](work/runtime/support-independence-reason-metadata-20261015-001/report.md)。

B推进35天后，原生规则允许撤销。[无授权正常传输](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/authority-test-a1955b7c1e324ae198888332bebe4816/report.json)被拦截；唯一授权请求 `r31b_revoke_support_swe_001` [实际撤销](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/support-independence-execution-faec6a52fd5746bf9602d3a8ffcd5eb4/report.json)，关系 true→false。随后固定测试源送入 HOL→FRA 请求支持提议，[准备报告](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/support-inbound-preparation-8854de697d6b4471aa71857b762f63ac/report.json)确认两个回应选项可用；[跨一天](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/lifecycle-observation-6d2c2f98db9d44d99fd3bfd188974a6a/observation-report.json)后，FRA request `r31b_reject_hol_support_001` [明确拒绝](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/inbound-response-8b5c28a11bf34f03a9cfed44e064cd1e/report.json)，原生 state1、pending_removed=true、关系仍不存在。保存 `llm_diplomacy_support_swe_revoked_hol_rejected_20261015_r31b.eu4`，SHA `e933b6949c682afd10f12dce188e8f029c6a303fa1cf934dcecfb53e0164feb2`，日期7月16日。

C重载确认瑞典撤销与荷兰拒绝持久化，随后改用未往返过的挪威请求法兰西支持，避免等待荷兰同一配对的原生冷却。C的[挪威入站接受](work/runtime/diplomacy-query-20261015-r31-support-c-revoked-reload/inbound-response-60e7289a54894f328764dcd375d50d3b/report.json)与[D新进程活动关系重载](work/runtime/diplomacy-query-20261015-r31-support-d-accepted-reload/support-independence-reload-a95b4157b1634ad694878a2321daac8e/report.json)通过。接受存档 `llm_diplomacy_support_nor_accepted_20261015_r31c.eu4` SHA `ab8fe08d2dfdcec56908e720a0cacc10c3eec5b9598aab64a526958d628c5ef1`。

独立验证已通过：[撤销来源](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/support-independence-source-validation-8a2ee3221a2f4eb6ab031e8c74130ff5/validation.json)、[HOL拒绝及跨日hold44项](work/runtime/diplomacy-query-20261015-r31-support-b-active-reload/support-inbound-source-validation-b-007/validation.json)、[NOR接受及跨日hold44项](work/runtime/diplomacy-query-20261015-r31-support-c-revoked-reload/support-inbound-source-validation-c-003/validation.json)。两次hold均为同一proposal/token，未出现自动响应或未授权回应。[五份存档流式取证](work/runtime/r31-support-save-effects-20261015-001/report.json)确认持续关系与外交官记录分开，并记录拒绝−25、撤销−50的原生关系修正。[六家族12项实际查询回归](work/runtime/diplomacy-query-20261015-r31-support-d-accepted-reload/family-query-regression-68de3c73440642ae9ed42068f6c855d6/report.json)通过。

D再推进35天后，外交官归来，三国支持关系保持预期；[归来后查询](work/runtime/diplomacy-query-20261015-r31-support-d-accepted-reload/support-independence-queries-afc570ab58d1495483ef3b2d26dab34f/report.json)通过。下一轮基线已保存 `llm_diplomacy_support_returned_20261015_r31d.eu4`，SHA `902f7e6d7fe5eb8d3e2330237f81fb122163f3701fb8a8b790ad802691256db5`，日期8月21日。

下一步实施请求／取消军事通行权：[方向与ABI](work/runtime/military-access-integration-20261015-001/report.md)已完成，Ask/Cancel使用selector2943、VT1c7fb70、actor持有的relations[recipient]；Offer2944为另一个family。原goal保持active，其余常用外交、19项议和条款和Royal已保存pending重新登记继续保留。当前三个子代理任务均已完成；归档记录见r31-progress.json。

## r30 历史运行层：保证与撤销保证独立已运行（2026-10-15）

`proclaim_guarantee` 与 `revoke_guarantee` 已接入四工具，实际完成 FRA→SAV 的建立、活动关系新进程重载、原生冷却等待、撤销、撤销结果新进程重载和外交官归来。两个动作都是单方操作，`phase=initiate`、`parameters={}`、接受度 `not_applicable`。[使用方法与证据](docs/保证独立接口与运行验收.md)。

当前 C 安装为 [installation.json](work/runtime/diplomacy-query-20261015-r30-guarantee-c-revoked-reload/installation.json)，PID **36276**，session `36276-1dd5c896226227f`，DLL SHA `5d013ebcbc8279f09a08bb06ff2619fa09e7cfab7864c5f9d92b66ab24c77328`。当前 POR 玩家、暂停、1445.6.5/raw56461920；FRA→SAV 保证不存在，外交官id3为空闲，可用数1。旧有Improve AMG/PAP、Spy BUR三项任务继续活动。POR是玩家葡萄牙，FRA是接口控制法兰西，PRO是NPC普罗旺斯，SAV是NPC萨伏依。

A [查询](work/runtime/diplomacy-query-20261015-r30-guarantee-a/guarantee-queries-7cacb0e7cd4349218a6e6815a0dd8292/report.json)、[无授权直接入口](work/runtime/diplomacy-query-20261015-r30-guarantee-a/authority-test-20526baaaa3444e6ba6876525832a40f/report.json)、[授权建立](work/runtime/diplomacy-query-20261015-r30-guarantee-a/guarantee-execution-1ed6a6745d6b4f8e91aec6beaedc2be8/report.json)均通过。B [活动重载](work/runtime/diplomacy-query-20261015-r30-guarantee-b-active-reload/guarantee-reload-b3bc6c753de74a69b1c7911f5b9cef81/report.json)、[无授权普通投递](work/runtime/diplomacy-query-20261015-r30-guarantee-b-active-reload/authority-test-c04f0dfb631c4111b3b3e44d61a4b781/report.json)、[授权撤销](work/runtime/diplomacy-query-20261015-r30-guarantee-b-active-reload/guarantee-execution-25a7b1fe1d7640a2be536ef2604c70a0/report.json)均通过。C [撤销结果重载](work/runtime/diplomacy-query-20261015-r30-guarantee-c-revoked-reload/guarantee-reload-5ff15f17b5cd429f95770b94e8175a05/report.json)和[归来后查询](work/runtime/diplomacy-query-20261015-r30-guarantee-c-revoked-reload/guarantee-queries-1493e083df94408c9fcd87495d5a79d0/report.json)均通过。两个实际请求分别确认幂等与SQLite重开。

真实规则限制：A建立于4月21日，B推进5天后外交官已空闲，但[原生诊断](work/runtime/diplomacy-query-20261015-r30-guarantee-b-active-reload/revoke-wait-query.json)要求5月22日后才可再次派遣；首次撤销负例在发包前停止，原报告4d88保留。继续推进35天到5月31日后撤销成功。C再推进5天至6月5日，外交官归来。关系状态由独立 `relationship_state.guarantee_active` 表示，不通过外交官是否工作推断。

三份命名存档：active `llm_diplomacy_guarantee_sav_active_20261015_r30a.eu4` SHA `2e24a87847ddc8222c907045e3264c02471db14e6c5fc59a6b80c6894e080666`；revoked `llm_diplomacy_guarantee_sav_revoked_20261015_r30b.eu4` SHA `b46d3f3f2ed2e97f7abce033d6cf88862c0ec9ed17f63d7373f560b23ddcaec7`；returned `llm_diplomacy_guarantee_sav_returned_20261015_r30c.eu4` SHA `05e2d01ec24523e8e1b3e9808d2e4475b5b66461b500fc8f6d007b9a7562bb34`。下一轮可从returned继续，原始R3保留。

实现复用已证明共性的0x40对象工厂、生命周期、传输、授权及通用执行入口；Guarantee独立family/selector/vtable/clone与mode，+100要求外交官，+90只是提示。查询与提交ACK独立，结果为 `native_diplomacy_relation_execution_result`，mode1/0且state0，前后保证关系必须实际改变。Ledger226项、wire114项、bridge183项通过；Improve/Spy四项共享原生查询回归已通过（原始公有字段误读报告保留，只读修正）。本阶段没有新增入口补丁或整机内存检查。

[建立来源](work/runtime/guarantee-source-validation-r30a-independent-20261015-005/validation.json)与[撤销来源](work/runtime/guarantee-source-validation-r30b-independent-20261015-003/validation.json)各39正向／11未授权检查通过。[流式存档对照](work/runtime/r30-guarantee-save-effects-20261015-007/report.json)取得实际 `diplomacy.guarantee` 的0→1→0变化，active的start_date为4月21日、takes_diplo_slot=yes；撤销后FRA→SAV出现truce=yes和last_war=5月31日。外交官guaranteeaction构造记录独立保存，不能当作保证关系。期间Spy值191→91仅记录观察，不归因为撤销。

本阶段实现归档：[r30 checkpoint](work/runtime/r30-implementation-checkpoint-20261015-001/archive-manifest.json)。大日志、DLL和存档通过哈希引用保留，不重复复制。

下一步完成支持独立的实际上下文切换与响应，并继续请求／取消军事通行权。[军事通行权静态识别](work/runtime/military-access-identification-20261015-001/report.md)已完成：Ask/Cancel selector2943、VT1c7fb70、0x40对象、mode1/0，handler523e90、validity525530、clone525da0、d0=51fac0；Offer selector2944/VT1c7f580另族。实施前还需核准Ask的UI关系行方向、原生接受评分及FRA入站pending控制，不能直接套用单方Guarantee。Royal保存pending重新登记、其余常用外交动作、19项议和条款和整体集成均仍在原goal范围内，goal继续active。

## r29 历史运行层：间谍网开始、停止与持久化已验收（2026-10-15）

`build_spy_network` 与 `stop_building_spy_network` 已接入四个统一工具，并完成 FRA→SAV 的实际建立、活动任务新进程重载、自然持续35天、停止、返程重载与归来。两个动作都是单方任务，`initiate`、`{}`、接受度 `not_applicable`。使用说明见[间谍网接口与运行验收](docs/间谍网接口与运行验收.md)。

当前 C 安装：[installation.json](work/runtime/diplomacy-query-20261015-r29-spy-c-returning-reload/installation.json)，PID **17680**，session `17680-1dd5c8185927090`，DLL SHA `47596fa65569aded1c2e2d0699d3d12ffb2183082803d38de2291c7c25d06fbf`。当前为 POR 玩家、暂停、1445.4.21/raw56460840；FRA→SAV Spy任务已停止，外交官id3为空闲，可用数1。POR=葡萄牙玩家，FRA=接口控制法国，PRO=NPC普罗旺斯，SAV=NPC萨伏依。

实际证据：A [六项查询](work/runtime/diplomacy-query-20261015-r29-spy-a/spy-network-queries-1af202daaa1240819535424876e0c9b4/report.json)与[授权开始](work/runtime/diplomacy-query-20261015-r29-spy-a/spy-network-execution-18bc19afd0ff4da486a1cf793fbcd202/report.json)通过；B [活动重载](work/runtime/diplomacy-query-20261015-r29-spy-b-active-reload/spy-network-reload-baa1ec86b6d9432d995cc3c9ddc106b9/report.json)、[35天](work/runtime/diplomacy-query-20261015-r29-spy-b-active-reload/lifecycle-observation-3ac3444dab664426b5a76099f824db3a/observation-report.json)、[授权停止](work/runtime/diplomacy-query-20261015-r29-spy-b-active-reload/spy-network-execution-eace0b6b95a54d30acba48c1ac5afcbb/report.json)通过；C [返程重载](work/runtime/diplomacy-query-20261015-r29-spy-c-returning-reload/spy-network-reload-3433e29708f4402ea4f28a618508e83b/report.json)和[5天归来](work/runtime/diplomacy-query-20261015-r29-spy-c-returning-reload/lifecycle-observation-b8d01c6891b44444bdd1dfe6d4c06466/observation-report.json)通过。每次提交均核对同ID幂等和SQLite重开；[Start](work/runtime/diplomacy-query-20261015-r29-spy-a/spy-network-source-validation-b786e04f58444cccbfe67e35a0d1db03/validation.json)与[Stop来源](work/runtime/diplomacy-query-20261015-r29-spy-b-active-reload/spy-network-source-validation-beba84f837814a38b6f8676fff3ef68c/validation.json)分别通过独立核验。

A 的[Start direct未授权包](work/runtime/diplomacy-query-20261015-r29-spy-a/authority-test-31924836a2cf4c8e8f63f841148a6304/report.json)与B的[Stop transport未授权包](work/runtime/diplomacy-query-20261015-r29-spy-b-active-reload/authority-test-15a2816beee849fd8c4fe7734cc47b6f/report.json)都在执行入口拦截，外交官完整语义不变。两例是人为合法原生包，分别覆盖模式和入口；原生AI自发选择证据与此分开记录。

[流式三存档对照](work/runtime/r29-spy-save-effects-20261015-002/report.md)确认：开始后 `is_building_spy_network=yes`；35天后出现原始整数 `spy_network=191` 和 `our_spy_network="SAV"`；停止后数值保留，活动标记消失，外交官2→1。5天后外交官1→0、可用数0→1。active SHA `86e30195b6af3cd43bb48b792647dd3b0f7474187310f4953316d70ae90839c1`；35days `a53a4f161af19eb631c6644d0fa0dd8b54394a98d378bf0a54abc1559a7b8e37`；returning `2069c63b184eeec41f7f0fc8de469343ddf8fe57f75b4634d6852eb40bfabe9c`；returned `53a7a593ad150b41e1d9f80d4d2877b3cfe88b76c362bcc76d704d1c22c8986d`。四份命名存档独立保存；最后一份可作下一轮实验场景。

实现采用共享UI工厂和原生任务分配/清理：Spy +108=true，由generic executor分配外交官并在授权入口后将action envoyID -1→3；Stop的原生mode setter恢复id3。shared helper保留Improve默认行为，family与授权独立。`stop_building_spy_network`实际为25字符，wire及结果缓冲容量26含NUL，实际Stop日志完整。C++ ledger202项/wire100项通过，bridge179项和56个子测试通过。原生未新增补丁位置，复用r28已验收的generic入口与unwind。

下一步优先保证/撤销保证独立。[Guarantee与Support静态识别](work/runtime/guarantee-support-identification-20261015-001/report.md)已证明二者不同：Guarantee selector2941/vtable1c7fe50为单方关系；Support selector2f2e/vtable1c805f0有state1拒绝/state2接受。不得按同一家族批量套用。尚未接入二者实际query/execute；Royal pending重登记、其余常用动作及19项议和条款仍继续推进，全goal保持active。

本阶段检查点：`work/runtime/r29-implementation-checkpoint-20261015-001`；native生产源码/DLL在A/B/C不可变构建目录，接口、测试、操作器、验证器和文档另行归档。

## r28 历史运行层： 改善关系任务、停止与返程已验收（2026-10-15）

已接通 `improve_relations` 和 `stop_improving_relations` 的四工具接口，实际完成 FRA→SAV 的派遣、持续 35 天、停止、返程和保存重载。查询另覆盖 PRO/ENG。两个动作均为单方任务，阶段 `initiate`、参数 `{}`、接受度 `not_applicable`。[使用方法与实际结果](docs/改善关系接口与运行验收.md)。

当前安装为 [work/runtime/diplomacy-query-20261015-r28-improve-e2-authority/installation.json](work/runtime/diplomacy-query-20261015-r28-improve-e2-authority/installation.json)：PID `27404`、session `27404-1dd5c7b000ebd2b`、DLL SHA-256 `2487a5d9c9e89c85006996f262768b1a3c2227b6f05fde66ff27612da4a12050`。本安装载入返程已结束的存档后，先完成两个未授权测试，再通过授权请求重新开始 FRA→SAV 任务；当前为 POR、暂停、1445.4.21/raw `56460840`，FRA→SAV 任务活动。POR 是玩家葡萄牙；PRO 是 NPC 普罗旺斯；FRA 是接口控制的法国；SAV 是 NPC 萨伏依。

| 能力 | 实际结果与独立证据 |
| --- | --- |
| 原生查询 | [R28a 六组查询](work/runtime/diplomacy-query-20261015-r28-improve-a/improve-relations-queries-095be3fff8b3422e9a20335ec86ed65c/report.json)：原生可见性、合法性、可读诊断与外交官数量均有记录 |
| 开始任务 | [R28b 执行](work/runtime/diplomacy-query-20261015-r28-improve-b/improve-relations-execution-a960cdb03c8b4405a4ba275dadad4580/report.json) 返回 executed，任务 false→true，type11739，外交官可用数1→0；[26项来源验证](work/runtime/diplomacy-query-20261015-r28-improve-b/improve-relations-source-validation-eb0bdfaeca2e47e5bba0f2a7fb84a1db/report.md)通过 |
| 活动任务重载 | [C 新进程重载](work/runtime/diplomacy-query-20261015-r28-improve-c-active-reload/improve-relations-reload-25ca854b6dc844088c3a9562621ca2d8/report.json)通过，任务和外交官语义与B执行后一致 |
| 持续效果 | [存档字段对照](work/runtime/r28-improve-save-effects-20261015-001/report.md)：35天后 improved_relation 的存档值 FRA→SAV 3.500→7.000、SAV→FRA 7.000→14.000，停止时保留 |
| 停止任务 | 原生结果 executed、task true→false、state0/mode0；[同请求只读修正验收](work/runtime/diplomacy-query-20261015-r28-improve-c-active-reload/improve-relations-resume-140842721add4c728f9591084f99b639/report.json)和[36项来源验证](work/runtime/diplomacy-query-20261015-r28-improve-c-active-reload/improve-relations-source-validation-fad014c24c0c4f6b8adcea99f8f3a603/report.md)通过 |
| 返程持久化与结束 | [D 新进程重载](work/runtime/diplomacy-query-20261015-r28-improve-d-returning-reload/improve-relations-reload-16cd915066284f27a35941993e7467e6/report.json)恢复返程值1；[再推进5天](work/runtime/diplomacy-query-20261015-r28-improve-d-returning-reload/lifecycle-observation-ac5e3ab826cc4db29a6b1cf50467697a/observation-report.json)后归为空闲值0，可用外交官0→1 |
| 权限隔离 | E2 游戏内 [direct entry](work/runtime/diplomacy-query-20261015-r28-improve-e2-authority/authority-test-ce144ee555704f3e8727d1f34ca804f1/report.json)与[正常transport](work/runtime/diplomacy-query-20261015-r28-improve-e2-authority/authority-test-9cd6bb988a68492293afcecedd08930f/report.json)均拦截无授权包，任务/外交官不变；随后[授权开始](work/runtime/diplomacy-query-20261015-r28-improve-e2-authority/improve-relations-execution-816e4c64974944068d80202b470bc696/report.json)成功 |

原生 AI 直接调用 generic executor 的静态来源证明旧虚表拦截存在覆盖缺口；现在函数入口和虚表调用共用一次授权检查，获准后原方法执行一次。两次游戏内负例是人为构造的合法原生包。独立 fixture、目标 PE 18字节 prologue、原生 unwind 和完整执行来源均有报告。本轮 bridge 回归为 172 passed、47 subtests passed。

保存证据：活动存档 SHA `c99737d693cda74106bba56cfa0c89977b6e152f81f890bc94fa062e0ba44ad4`；35天后 `ae5b1b8398ede8809feb04614c280c87b49c8b25885bd95a91718fd6ab11f163`；返程中 `5a5533e8405cb1b61d9a15da69926786b9559f1205fb7e8e4ce648cf6f56abf6`；返程结束 `4cf6fdd3e1c7ba20939de1c0ead574c4fa9342a5baa391edb48c00143fb7bf82`。原始R3独立保留。

下一家族为建立/停止建立间谍网：[静态识别](work/runtime/spy-network-identification-20261015-001/report.md)已确认 selector13176/0x3378、专用clone、native stop ID回填与原生规则；尚未接入该家族的查询和执行。Royal已保存pending的重新登记、其他常用动作与19项议和条款继续按原goal推进，整体goal保持active。

本轮验收脚本修正见复盘：任务证据字典与布尔值误比、返程值1误作工作状态、停止后强求Start立即可用，以及新日期第二心跳尚未出现的即时health误报。原始失败报告保留，停止操作没有重发。首次E构建的旧变量名编译失败保留在独立目录；E2编译和安装成功。

本阶段代码与文档检查点：`work/runtime/r28-implementation-checkpoint-20261015-001`。原生源码/DLL通过B/E2不可变构建清单引用；统一接口、测试、操作器和文档另行归档。

## r27 历史快照：N/O 自然提议拒绝已验收（2026-10-15）

当前 O 安装快照记录在 `work/runtime/diplomacy-query-20261015-r27-royal-native-reject-o-reload/installation.json`：PID **31104**、session `31104-1dd5c6ef5543982`、DLL SHA-256 `73175c293c4b1d606651665a8bb65a2a7f190f49b38b0b328258f562f420908b`。PID 和 session 只属于该 installation；后续操作必须重新读取 installation.json。玩家是 POR，受控决策国是 FRA，PRO、SAV、LIT 是其他国家。

L 和 M 各自让 PRO→FRA 的自然联姻提议保持三天，没有原生自动回应。L 的迟到响应报告显示 `PENDING_NOT_ACTIVE`、`proposal_status=invalidated`、`submitted=false`；该报告没有确认 pending 被移除的具体原生原因，不能称为自然过期已确认。N 运行则在 raw date `56459904` 发现 PRO 自然提议，在 `56459928` 保持一天后由 FRA 通过 request `r27n_reject_pro_001` 明确拒绝，原生 `state1`、`pending_removed=true`、`royal_marriage_after=false`，6 项响应检查全部通过。N004 生命周期报告对同一自然来源链通过 33/33 项检查：hold 期间没有 state 1/2 command entry 或未授权 FRA response。[N004 报告](work/runtime/diplomacy-query-20261015-r27-royal-daily-n/royal-pending-lifecycle-validation-004/report.md)

N 保存 `llm_diplomacy_royal_native_rejected_20261015_r27n.eu4` 的 SHA-256 为 `e8242d4e5ad9eb927ee839e6f49988b31ef1c1f0bb42c20330f76eab32edd449`，日期为 `1445.3.14`。O 新进程重载通过全部 23 项检查：PRO/SAV 均不存在，四组快照、外交官、POR、暂停、raw date `56459928`、源 R3 和新存档哈希均匹配。

当前调用者结论是：每日回应实际来自 `0xb22b9`；只有 Royal、`d0`、caller `0xb22a3` 且完整 FRA pending/node proof 成立时，gate 才返回 0 跳过 daily AI，其他 caller 保持原样。J 的 `4e81b8` 候选未命中；J007 负例在 pending 期间实际检出 3 次 state 1/2 command entry 和 3 次未授权 FRA response，继续保留为 gate 失败证据。[J007 报告](work/runtime/diplomacy-query-20261015-r27-royal-pending-j/royal-pending-lifecycle-validation-007/report.md)。已保存但尚未回应的 pending 仍需新进程重新登记；`royal_wire` 正在修正真实 pending validator schema，针对 L/M/O 的独立来源链报告仍未返回。N004 已为 N 的自然来源链通过 33/33 项生命周期检查。

E/F/G/H 的 SAV accept/reject 和保存重载仍是已完成结果。当前 Python API、测试/fixture、相关操作器、验证器和文档检查点为 `work/runtime/r27-implementation-checkpoint-20261015-002`；该检查点只引用 L/O manifest，不复制 native 源码和大型运行日志。全外交 goal 仍未完成。

## r25d历史王室联姻查询（2026-10-15）

当前PID **12932**、session `12932-1dd5c105af2b43c`，只安装一次，安装记录 `work/runtime/diplomacy-query-20261015-r25-royal-d/installation.json`；DLL SHA `51620e39986e907d2c436f74a8ee36b3f063ee4541f30977952a93859ce98406`。POR、暂停、date56459880，原始R3。[r25d报告](work/runtime/diplomacy-query-20261015-r25-royal-d/royal-marriage-queries-7011638465244738b2c9582292e54651/report.json)15项全部通过，SAV/LIT全部实际因素的稳定原生ID、值、Ctor到最终行绑定均verified。SAV总值62预测接受；LIT−30预测拒绝。

共和国例外已实际验收：本机 `LAN=countries/Florence.txt`，R3为republic/signoria_reform；FRA→LAN原生合法、总值47、预测接受。GEN原生政府拒绝；MOR仍在当前解析范围外返回unknown。来源见[政府及标签报告](work/runtime/royal-marriage-governments-20261015-001/report.json)。不要把TUS（Tuscany/oligarchy_reform）与LAN混称。查询脚本支持repeatable `--recipient`，自动保留SAV/GEN正反例，避免每次重跑所有国家。

Royal协议进一步确定：[clone/serialize/load/handler](work/runtime/royal-marriage-identification-20261015-001/query-methods-20261015-002/report.md)证明前缀9个字段共用流标签，Royal类型尾码19e、额外flag60入流；string40不入流，clone将string40与flag60重置，handler直接访问state34/variant38而不访问40/60。下一实现应限定普通UI默认flag60=false，完整记录Royal family与flag，不能把Alliance许可误用于Royal。普通+40 wrapper4e9960先调用+b0 clone，再将clone.date2c设当前游戏日期；UI工厂默认date28为旧初始化值，执行时的date28/期限合同还需与现有ledger检查一起确认。Royal权限、授权执行、原生回应和保存重载尚未实现。

所有本轮root shell sessions均已收齐；子代理三项只读取证及文档归整已完成，未遗留分析进程。下面r25c/PID22208记录为已结束的首次查询实验。

当前PID **22208**、session `22208-1dd5c0c6d9b2360`，安装记录 `work/runtime/diplomacy-query-20261015-r25-royal-c/installation.json`，已安装一次。DLL SHA `7ff260cdc94f3c2ace0ac822c949185151464291988860485b3e73db363e4953`；POR、暂停、date56459880（1445.3.12），原始R3独立实验。r24e/PID17508已正常重启关闭，下面r24内容是已经完成的检查点。

[r25查询报告](work/runtime/diplomacy-query-20261015-r25-royal-c/royal-marriage-queries-2ed042ec7dd444d9a8f219b8008b3278/report.json)13项全部通过，FRA对SAV/LIT/GEN/TUS/TUN/PRO/ENG共14组Offer/Break查询均归档。SAV联姻合法、native_would_accept=true、total62，五因素值4/40/5/5/8及中文文本已读；LIT合法而预测拒绝−30，ENG合法而预测拒绝−1102。GEN原生政府拒绝文本、PRO已联姻禁止重复Offer、无联姻的Break不可用，PRO现有联姻可Break；TUN因当前查询范围得到unknown。TUS不可用的具体场景/政府正在流式核对，不能称Signoria例外已验收。查询前后外交官任务、联盟状态、日期和暂停相同。

新ACK仅增加 `native_royal_marriage_query:true`，Python精确顶层literal true才允许Royal initiate查询，未开放Royal执行。Query复用UI creator `0x35a8b0`→factory `0x35d240`/selector28df/case35d29d，原生heap0x68、vtable1c80ab0，创建期间初始化+40string/+60bool及端点，+e0=4e9a00选择Offer1/Break0；析构4ed5e0 flags1销毁字符串并释放heap。Royal方法 +80=4ef3e0、+88=4ef7e0、+90=4e9b40、+120=4f0c20，+40=4e9960/+b8=4ea210共用。UI selection case35ac11用relation owner+68/+74的16字节联姻列表。参考[方法分析](work/runtime/royal-marriage-identification-20261015-001/query-methods-20261015-001/report.md)及同001目录的factory/vtable/helper投影。

王室查询9项定向测试、旧外交54项均通过。下一步：依据本轮实际Ctor caller映射因素稳定标识，核对存续Signoria共和国场景，解码clone4f0800/serialize4f08b0/load4f0900及执行4ed670的额外字段，再扩展授权与执行。r25a/b未安装，构建时能力字符串匹配选错出现两次assert；r25c已正确将cap加入observer ACK。不要把r25a/b当运行版本。

保存优化已通过8项定向测试并实际成功：[r24e保存报告](work/runtime/alliance-query-20261015-r24e-results-reload/save-observer-report-1792001747786246900.json)只备份/恢复3份autosave，其他69份记录元数据；命名目标 `llm_diplomacy_save_rotation_20261015_r24e.eu4` SHA `2a8280d847636011b0cd7a576de0506fc25d5352753a53106d9351fe6aeabbd9`。r24源码与脚本快照见 `work/runtime/r24-implementation-checkpoint-20261015-001/manifest.json`。根代理所有shell sessions已收齐；三项只读独立取证仍在子代理执行，完成前不要称全部分析会话已结束。

## 最新检查点：r24断盟交付及结盟回归（2026-10-15）

当前实验为 `work/runtime/alliance-query-20261015-r24e-results-reload/installation.json`，PID **17508**、session `17508-1dd5c06e40e4b77`，只安装一次。DLL SHA256 `49e8381850dd13c90591ee3142b553bd7d0df6ecf5445fb2cc3e98255223f23a`，安装选择 `eu4_escape` 文本解码。玩家POR、暂停、raw date56460720（1445.4.16），已完成[新构建结果重载](work/runtime/alliance-query-20261015-r24e-results-reload/reload-validation-c4fedb28997f4247aeb2bc526df0eeff/report.json)。SAV联盟存在、LIT联盟不存在、PRO原联盟保留，外交官记录、原始r3和命名存档哈希均与对应保存前证据一致。不要重复安装或热换DLL。

r24已新增 `submit_dissolve_alliance`、原生断盟投递、`executed` 结果和SQLite旧表约束迁移。实际FRA→PRO联盟从存在变为不存在；无联盟的FRA→SAV请求在提交前失效，重复编号返回已有执行结果。[断盟执行](work/runtime/alliance-query-20261015-r24-dissolve-a/dissolve-execution-5db2994d34db45f69b8b6a808378a1ac/report.json)10项通过，[原生来源](work/runtime/alliance-query-20261015-r24-dissolve-a/dissolve-execution-5db2994d34db45f69b8b6a808378a1ac/native-source-chain-validation-001.json)48项通过，[断盟重载](work/runtime/alliance-query-20261015-r24-dissolve-reload/reload-validation-798ab399b77f4db0972d4bc535cb0816/report.json)通过。[存档变化](work/runtime/r24-dissolve-save-pair-20261015/report.md)含PRO对FRA的break_alliance −50、双方truce=yes；停战期限未单独映射。断盟存档 `llm_diplomacy_dissolved_pro_20261015_r24.eu4` SHA `7dd89542fe1a89d98a33e27249b13f2d356541afc368b0dcd10ce89d3a81f9ed`。

r24b重新执行断盟通过，并完成[未授权断盟](work/runtime/alliance-query-20261015-r24b-authority/authority-test-bbbbab2610c843388f1430454be374dc/authority-source-validation-001.json)；r24c完成[未授权结盟](work/runtime/alliance-query-20261015-r24c-offer-authority/authority-test-187b15159f6e4903af72bec485144e35/authority-source-validation-001.json)，两组独立来源检查各63项通过。合法的实验命令未建立授权种子，经过原生传输、读取、复制后在普通执行入口被拒绝，关系及外交官不变。这是普通命令授权拦截取证；原生AI自发选择的样例仍需独立观察。[断盟外交官归途](work/runtime/alliance-query-20261015-r24b-authority/lifecycle-observation-61d86dff7ec04da09f704524a91cca2b/dissolve-envoy-validation-001.json)确认新增外交官从执行后active1/可用0返回active0/可用1，另三名任务完全相同。

r24c结盟回归发现真实关联错误：原生SAV接受并结盟，但NPC回应的日志phase被改为accept，Python仍按原始initiate请求匹配。r24d修正 `execution_binding_phase`，让外部结果沿用请求phase，原生选择由native_state/outcome描述。新构建的[SAV接受](work/runtime/alliance-query-20261015-r24d-response-phase/alliance-execution-95bf43c4f0be4a2b9c1ad592c86da120/report.json)及[LIT拒绝](work/runtime/alliance-query-20261015-r24d-response-phase/alliance-execution-9f774cbbfe7148a5b5bdb786b61bf0f0/report.json)均passed，SQLite重开一致。命名存档 `llm_diplomacy_alliance_results_20261015_r24d.eu4` SHA `cd65de2a2d4d5359deecce280b1c2641e2a163a80f6bbeceb5ff4ec7a345fd8f`，三旧autosave恢复；r24e直接复用构建后重载通过。

就绪脚本已应用到断盟、结盟、入站、因素和重载/日期推进实验。最小化游戏会停帧，脚本在需要时恢复同session、同PID、精确标题的唯一窗口，不激活前台；只在开始和结束读取完整health，中间用有界心跳尾部轮询。取消逐步整机内存检查和编译器内存轮询；编译监督仅保留超时和自己子进程的清理。分析仍遵守大文件流式读取和REA进程既定上限。

下一实施点：提议撤销、完整主动断盟来源分类、王室联姻家族。七个直接helper caller已做[追加分类](work/runtime/alliance-dissolve-callers-20261015/remaining-callers-20261015-001/upstream-analysis-001.md)：两个RIVAL_SET伴随关系清理、ChangeTags路径应保留；country update与effect路径的选择语义仍需查明，不能全局拒绝helper。王室联姻正在按需识别具体ctor/vtable/selector及规则入口。全goal仍active，常用操作和议和条款尚需逐项开发。

以下r23及更早记录保留各实验当时的状态；其中“当前PID”“尚未实现”均对应各段注明的历史版本。

**用户当前约束（2026-10-14）：** 用户明确要求“不要再每步都检查内存”，并确认最近卡顿是其他软件bug，更早卡顿是代理违规读取。已撤去EU4/Ghidra/编译的整机内存启动门槛、编译器整机内存轮询，删除新增resource_guard及其门槛测试。下面早期资源记录仅为历史，4096/2048 MiB不再是启动或继续工作的条件。仍遵守大文件有界读取、分析进程既定上限和会话清理；不要把这些规则扩成每步整机检查。按功能需要继续编译、脚本加载和运行验收。

**当前运行成果（2026-10-15，r23）：** 因素标识及入站接受/拒绝已实际运行。r23c DLL SHA256 `61e0b62ede5d8b1fe8565685e78a6de17ca2b0d45391aa216afefe5fd50a805e`，两组SAV/LIT六项因素均返回verified的稳定标识和原生值，见[因素报告](work/runtime/alliance-query-20261014-r23c-reason-binding/reason-metadata-validation-07b144940f8040b0b55eefbf6639ea00/report.json)。构造来源表已覆盖实际caller及DIPLO_BORDER_DISTANCE；最终行比较排除未初始化padding，仍要求顺序、值、flag、字符串存储、size/cap和完整文本一致。

法兰西对实际SAV入站提议的accept（r23b）得到state2、alliance true、pending removed；reject（r23c）得到state1、alliance false、pending removed；SQLite重开一致。两份[accept来源链](work/runtime/alliance-query-20261014-r23b-reason-meta-f17c8d6b/inbound-response-467ed587f3184e2686acd6d1f66a4f4c/native-source-chain-validation-001.json)、[reject来源链](work/runtime/alliance-query-20261014-r23c-reason-binding/inbound-response-bb79c6eae6e14da197846900b9e837e2/native-source-chain-validation-001.json)独立验证transport/load/clone/entry及完整payload/header。r23b原总体report因64KiB日志尾部遗漏heartbeat后的selector暂时unready保留failed；selector-recheck已visible/available，Python现保留64KiB快路径并在必要时扩展至1MiB尾部，新增3测试通过。

接受存档 `llm_diplomacy_inbound_accepted_20261014_r23b.eu4` SHA `ae75fd27141d32a1ea7f606309cd5724c41a142b7d9debbcbcf194f9ae5aafaa`；拒绝存档 `llm_diplomacy_inbound_rejected_20261014_r23c.eu4` SHA `8aa734933558a0dd8582ebda251a735d98094e4587ee0a2258947133af4ab371`。两者均原生保存并恢复三份旧autosave，[接受重载](work/runtime/alliance-query-20261014-r23d-accepted-reload/reload-validation-bc997a0d648044339860c67f69a4518f/report.json)、[拒绝重载](work/runtime/alliance-query-20261014-r23e-rejected-reload/reload-validation-1d71e565c87743a1b4f60e32f6196de9/report.json)全部检查通过。重载直接复用经SHA校验的r23c构建，无重复编译。当前PID **20084**、session `20084-1dd5bf5b1f3e967`、r23e installation已安装一次；POR/paused/date56459880/health ready，不重复注入。已收齐89678、23783、62465、68354、52890、89840、58703等本轮shell sessions；没有未收尾shell会话。

启动错误 `DLL autoupdate failed / DLL autoupdate WAIT_TIMEOUT` 曾阻挡PID21652初始化。已通过脚本精确确认唯一错误按钮并继续启动；starter现每5秒至多检查一次该严格匹配的错误框，成功后停止扫描，9项启动测试通过。保存首次我误用raw日期参数，后改help明确1445.3.12格式；独立backup目录支持同session再次保存，6项保存测试通过。早期r23因Ctor序言RSI误写RBP安装返回28且全回滚，r23b修正后安装成功；上述失败证据保留。下一阶段推进联盟撤销和断盟的授权执行及直接调用来源分类，再按全goal扩展，goal仍active。

**断盟下一阶段已取得的具体依据：** [七个直接caller投影](work/runtime/alliance-dissolve-callers-20261015/alliance-dissolve-callers-20261015.json)及[两函数级投影](work/runtime/alliance-dissolve-callers-20261015/function-level-projection-20261015.md)已归档，未修改断盟执行代码。根代理确认 `0x766cc8` 属于 `0x763ba0` 的ChangeTags关系/pending/联盟清理，应保留原生执行；`0x2d618b` 属于 `0x2d2ff0`，以param_3=0x2cf7分派操作，selector名称仍需映射。禁止以共同helper `0x3d2350` 全局拒绝FRA相关调用。两次REA缓存查询已收尾；第二份13MB evidence采用流式投影，未全量解析。

正常断盟命令的实施点：ledger已支持 `Phase::dissolve` 和 `variant38=0/state34=0`；现有query以50f780构造owned action后将variant38设0，复用原生visibility/common/+80/+90。当前[下一阶段真实基线](work/runtime/alliance-query-20261014-r23e-rejected-reload/dissolve-next-baseline/inspection.json)确认FRA→PRO为visible/available、原生要求外交官、FRA空闲1名。执行wire仍固定offer_alliance且action_id buffer15，Dissolve标识需18字节；submission formatter仍硬编码offer，sender phase仍固定initiate，结果仅处理accept/reject。下一实现需一起调整wire/action buffers、preflight variant与selector、Phase::dissolve种子、普通命令入口授权、单方后果和统一结果状态；为单方执行成功定义明确结果，不能伪装成对方接受。随后新构建/新进程完成实际断盟及保存重载，继续研究提议撤销和已识别direct来源。

**r22已编译快照（2026-10-14）：** `work/runtime/alliance-query-20261014-r22-inbound-e-d954825a` 的DLL SHA256为 `7cc0dcbb2bb59f7f7e0e32a584facb931dc53a1d66129102a00d3839c5c8dcc4`。已修安装版本、提交收据、查询事件绑定、pending删除误判和目录支持状态；formatter五项、pending七项、wire及当时53项Python检查通过。响应复用+80、+100恒真、+f8恒假，+b8的NPC意愿不作为LLM前提，清理继续由原生链处理。见[r22报告](work/runtime/alliance-r22-review-d954825a/report.json)。最新源码和安装进度使用上方r23成果，旧c/d/e证据保留。入站运行脚本为 `work/run_alliance_inbound_response.py`；accept、reject及保存重载仍按全goal推进。

**早期资源复测记录（2026-10-14 20:31，策略已撤销）：** 测量记录见[复测报告](work/runtime/computer-lag-20261014-2031/report.json)。新增门槛及4项门槛测试已按用户要求删除，不再阻塞开发；原始记录保留，不作为当前启动指令。

**早期资源自查记录（2026-10-14 19:44）：** 当时关闭了自己启动的实验PID6248并释放不用的kernel，未发现重复350 MB读取。测量见[原始记录](work/runtime/computer-lag-20261014-1944/report.json)。用户后续明确本次是其他软件bug；根代理此前的整机余量归因与启动门槛已撤回。违规全量读取是更早的另一事件，继续遵守 `work/AGENTS.md` 的读取约束。

**资源自查前的运行成果：** r21-inbound-d DLL `25e88ae754006dabf3d1f96e315016f48c627142de4489deaf149bbcfb01d846` 已在新进程只安装一次，原生 `CALL` 分支将合法的 TEST_ONLY SAV→FRA 提议送入 FRA 原生 pending 队列、state0；统一目录已返回入站提议和决策国 FRA。[入站报告](work/runtime/alliance-query-20261014-r21-inbound-d/inbound-validation-73983eca90ba4e4bb851f7db9dcbd864/report.json)八项检查全部通过。该可重现实验因资源自查已关闭，未保存这条测试提议；源 r3 和已验收 r20h 命名存档继续保留。r22源码与响应规则的最新状态见顶部e编译记录，旧c快照和曾恒false的完整性门不再作为当前源码依据。新增 `alliance-reason-metadata.inc` 捕获层已通过小fixture，五项localization key有静态映射；`alliance-query.inc`的宏守卫接入尚未整合安装。

**当前阅读入口（2026-10-15）：** [外交系统说明](docs/外交系统说明.md)说明查询、接受度明细、实际执行结果和调用方法；[外交开发推进复盘](docs/外交开发推进复盘.md)评估检查价值及可压缩的流程。开发 goal active，联盟出站样例已完成原生接受、拒绝、保存和新进程重载。当前PID20084/r23e已完成拒绝存档重载核对，POR、暂停、date56459880、health ready；下方r20h-reload、r19及更早信息属于归档实验。

**已结束的运行检查点（2026-10-14，r20h-reload）：** PID `67700`，session `67700-1dd5bcab6cef7e5`，DLL SHA256 `902b7f0c53c3431cf8ca4f520026611dbd6e3b6d9927420c14b52669d21e6e55`，只安装一次。已从独立命名存档 `llm_diplomacy_alliance_results_20261014_r20h.eu4` 重载，POR、paused、raw date `56460720`（1445.4.16）、health ready。[重载报告](work/runtime/alliance-query-20261014-r20h-reload/reload-validation-001/report.json)全部检查通过：FRA–SAV 联盟保留、FRA–LIT 未结盟、外交官任务和归途字段与保存前一致，源 r3 和新存档哈希均未改变。

**本轮实际业务结果（r20h）：** DLL SHA256 `7e601b47de965e8be07fbb82d3a46ec71fd0a5eabfc22846ced5f7c6caea6a07`；统一接口请求 `r20h_sav_002` 在 raw date `56459880` 获萨伏依原生 AI 接受，`state=2`、联盟已建立；自然推进35天后，外交官返回可用，请求 `r20h_lit_001` 获立陶宛原生 AI 拒绝，`state=1`、未建立联盟。两次结果均通过 SQLite 关闭重开核对。报告分别位于 [SAV 接受](work/runtime/alliance-query-20261014-r20h/alliance-execution-b57156adb9374dc7ac974f1cc88b3fa7/report.json)、[LIT 拒绝](work/runtime/alliance-query-20261014-r20h/alliance-execution-9de8b66f9ca2499cbe422dab4bf81361/report.json)；[独立来源验收](work/runtime/alliance-query-20261014-r20h/execution-source-validation-001/transport-validation.md)通过两次发起及两次回应共4条完整 transport→load→clone→entry 链。

[原生保存报告](work/runtime/alliance-query-20261014-r20h/save-observer-report-1791975293447965700.json)证明保存文件实际存在，SHA256 `c040551925f6f66360c66476d5ebebe4c156017a0784cba529bbdff866433f60`，三份原 autosave 已恢复。执行接口目前支持 FRA→SAV/LIT 的 Offer/initiate、空参数；未授权 FRA state0 Offer 在执行入口被拦截，实际原生 AI 选择拦截用例仍待取证。后续首先完成入站 FRA 提议及 LLM 接受/拒绝，再完成撤销、断盟和其他常用外交/议和操作。入站静态线索在 `work/runtime/alliance-inbound-plan-20261014/`，必须复核报告中 roster 条件及 bool 决策分支，不把布尔结果当作“暂不决定”。

**最新运行检查点（2026-10-14，r19）：** 新进程 PID `31504`，session `31504-1dd5bbddc38e34f`，DLL SHA256 `f5b48d422311add3b7e48807aa899d8c160c4c2d549271cb51c7acec6cc7c2e2`。原生脚本确认 r3 载入提示并完成一次安装；法兰西→萨伏依的实际查询返回 visible/available、六项接受因素、总值64及原生愿意接受判断。新增 transport 和包装读取观察点实际取得两条“发送原对象→重建包装→接收复制→执行入口”的对象关联；[独立验收报告](work/runtime/alliance-query-20261014-r19/lifecycle-observation-cc9c84d97c4d414192552215662090de/transport-validation-001.md)核对完整 header、九项 payload、peer/ring/owner、对象地址及严格 callback 顺序，两条均通过。35天目标观察结束在 raw date `56460720`，POR、paused、health ready。当前进程不重复注入。

本轮桥接新增原生提交适配：能力声明、最新查询、独占 execution wire、真实收据校验和请求持久化；另修复 `record_result` 的未定义变量，验证 accepted/rejected 写入并重新打开 SQLite。原生执行 wire 解析器已有独立测试。r19 继续作为观察构建，下一步把授权 ledger 接入已取得证据的来源转换，再实现实际 sender 和回应记录。新的 native source chain 是原生请求来源证据，联盟业务交付仍按实际桥接提交、回应、关系和保存重载验收。

**逆向模块入口（2026-10-14）：** [联盟外交逆向梳理](docs/联盟外交逆向梳理.md)与[reverse_engineering](reverse_engineering/README.md)集中维护查询、包装/投递、接收重建、执行/响应、断盟旁路、生命周期和业务持久化缺口。`python -m reverse_engineering` 提供地址查询与证据/EXE 校验；本轮没有新的 EU4 运行实验或 DLL 变更，r17c 仍为下述归档运行层。REA 分析尝试及资源/覆盖限制另记索引 `analysis_runs`，不作为业务验收。

**REA 诊断与旧有界入口：** 原版 REA 6.4.0 在全 EXE 默认分析完成后才启动 bridge，EU4 首次查询因此超时。项目先建立有界路线，现用 `python -m reverse_engineering.rea fn.receive.reconstruct --seeded` 明确选择：按精确 EXE 哈希和 PE unwind 范围进行受限分析。receive 当时在 38.14 秒内取得反编译、112 条汇编和成功 Evidence；该路线全局 caller / 类型覆盖不完整。详见[故障诊断](docs/REA故障诊断与按需分析.md)。新汇编还明确 receive `+0x118` 是队列结构指针候选，source wrapper 经 `0x1581120` 的出参取得；旧合同的简写已在逆向文档和索引中修正。

**完整库已完成并可复用（2026-10-14）：** Ghidra 默认全程序静态分析耗时 3426.28 秒，保存 65,423 个函数、6,662,700 条指令，峰值 814.9 MiB，进程已清理。`work/runtime/ghidra-full/latest.json` 已发布完成库；上述 `reverse_engineering.rea` 命令现在默认复用该库。receive / wrapper clone 缓存查询分别 30.80 / 26.41 秒，profile 相同，数据库 SHA 前后不变；没有再次全量分析。`--seeded` 才选择旧的临时有界流程。见[完整分析与缓存查询](docs/Ghidra完整分析与缓存查询.md)。原版 MCP、DLL 和游戏运行验收未变，类型、间接调用和授权业务缺口仍需分别研究。

**当前检查点（2026-10-13，r17c）：** 新进程 PID`60892` / session`60892-1dd5b1d26b30a9b` / 创建时间`134363744652429979`，DLL SHA256`e4c14dadfcfe13f967e3d6ca220b0a81e27680af15cad221f1055cd3c8256c87`，仅一次安装。`work/runtime/validation-alliance-20261013T141723Z-2c9ee9dfd801/validation-report.json`八组查询与九项guard passed；`work/runtime/alliance-query-20261013-r17c/lifecycle-observation-3bcb20be51e14aaea3fcebba71df6c17/observation-report.json`证明35天到raw date56460720、POR、恢复暂停、health ready。该目录`live-state-integrity.json`重核源r3哈希未变，没有待消费查询/日期请求。r17编译失败保留；r17b只编译/审核未安装；r17c已运行，不能在该进程重注入。

r17c观察675条wrapper field begin和20条Alliance wrapper clone；两条CAS→POR请求以clone返回的同一wrapper/action地址与完整payload进入执行入口。clone返回origin65535/sequence0；静态接收函数`0x15800c0..0x158026e`在`0x15801e8`复制source sequence到target，入口实际恢复41/747。见`protocol-continuity-core.json`及`work/runtime/alliance-static-20261013/incoming-receive-contract-20261013-r17c.md`。发送关联仍是完整header/payload候选，尚无桥接业务发送或独立transport receipt；origin名称/身份命名空间未知，65535绝非授权通配符。

`r17c-protocol-validation-002.json/md`独立核对source/DLL/schema hash、ACK和session，无drop；20 clone、2条局部链、全阶段链0，6项tests通过。001遗漏command wrapper地址关联条件，已修正并保留历史。查询报告基线为raw date56459880；当前56460720不能继承旧状态预测。`semantic-source/source-manifest.json`归档13份语义、编排、验收和授权底座源码。

新`work/native/alliance-authority-ledger.h`尚未编入r17c或启用：分离outgoing/incoming/target代际、完整payload/phase/header/epoch/期限、单次claim、移交后source detach、显式revoke及target dtor撤销；独立`authority-ledger-fixture/review-003/verification.json`163项检查通过。64个终态tombstone为实验容量限制，生产来源proof和长期回收未实现。下一步优先恢复接收owner/namespace、selector0x240和controlled recipient route，再实际接入权限与sender；断盟七caller来源仍unknown，不全局拦截共同helper。

新双槽观察安装拥有局部及外层回滚；六个asm桩用单次固定栈分配和对应SEH记录，按Win64调用ABI保存参数/返回路径，条件flags为volatile，DF不改。`patch-fixture/verification.json`独立证明direct/wrapper reader整数与浮点参数/返回、真实RtlVirtualUnwind四位置、10轮并发patch/rollback恢复；它不计作EU4业务验收。受控国隔离、授权发送、实际accept/reject、外交官分配/归途、业务后果保存重载仍未完成，goal active。

**历史检查点（2026-10-13，r16c）：** 新进程 PID`6588` / session`6588-1dd5b13bad331e2`，DLL SHA256`18b9eabcd2cc5b320a6f5ded542b8b55e2e0d6ddda984550d8045e33022da201`。证据根目录`work/runtime/alliance-query-20261013-r16c`；`validation-alliance-20261013T130913Z-20b28ee1ea2d/validation-report.json`记录8组查询和9项native guard，查询与只读快照通过，所有执行结果均`submitted=false`，`invalidated`是未实现执行适配的桥接状态，不是游戏或AI拒绝。`lifecycle-observation-7546f9ab0f3c476caf3c40e10e230ca1/observation-report.json`证明自然推进35天到raw date`56460720`、POR、恢复暂停、health ready；源r3存档SHA256`d5da2f4bf818a481fe1493341c4cfd09cb5bcc5d621dd826ebc9051cd3565d5f`已由`live-state-integrity-1791899390100389400.json`重核且未变。

r16c字段读取验证记录198条field read、22组，实际字段为`0x3ec`（`variant38`，不是`0xec3`）；2条局部field→clone→entry链中第二条的`date2c`发生变化，不能据此推断协议身份或提交。2条direct-break均返回caller RVA`0x2aab24`、native flag`1`；决策国和caller source仍unknown。权限隔离、正常原生构造/投递、AI选择、实际accept/reject、业务后果及保存重载仍未完成，goal active。r16/r16b从未安装；当前运行证据只属于r16c身份。

`patch-fixture/verification.json`是独立Windows fixture进程验证：10轮、15次尝试、整数/浮点返回值和observer计数无错误、bytes restored、pending为0、线程全部join、非法signature未发布；它不接触EU4，不能计作游戏运行验收。静态alternate/wrapper报告继续保留unknown边界，见`work/runtime/alliance-static-20261013/alternate-alliance-handler-20261013-r16.md`与`wrapper-deserialize-20261013.md`。

**历史检查点（2026-10-13，r14查询与被动生命周期实验）：** `work/runtime/alliance-query-20261013-r14/installation.json` 绑定 PID `54108`、session `54108-1dd5b08cf5dc180`、创建时间 `134363657287876992`，DLL SHA256 `3ec91d49481530c15e5d37e41b443510105cb58910d106eb555e93176c82378f`。这些身份不能跨实验使用。新进程从独立r3存档启动，一次安装成功；r13编译失败及r13b基础钩子安装回滚的证据分别保留，没有在旧进程重注入。

`validation-alliance-20261013T115040Z-5bc2df60602a/validation-report.json` 为passed：8组真实查询含 FRA→SAV 原生当前接受检查=true（总值64）、FRA→LIT=false（总值-26），两者均visible/available；预测分别为accept/reject，`prediction_basis=native_current_acceptance_check`、`actual_response_verified=false`。其余6组保持r12规则结果，玩家POR和单方Dissolve没有AI预测。八组实际读取FRA空闲外交官1名、原生要求外交官=true；分配和归途未验证。九项wire guard、只读前后资源和状态比较通过。77项bridge tests及5项验收脚本测试通过。执行adapter和权限隔离仍关闭，不能把预测算作实际响应。

新被动钩子观察原生clone、wrapper、析构前快照及payload serialization_begin，保留原函数参数与返回；序列化开始可以记录原生分配的完整origin/sequence/flags，但不等于入队、服务器接受或外交业务成功。`lifecycle-observation-fe4904491c214e23a42aefc3a5b69305/observation-report.json` 证明自然推进35天到raw date `56460720`、POR、恢复暂停、health ready。此步骤没有桥接外交请求或权限拦截；生命周期关联正独立验证。当前日期与查询报告基线`56459880`不同，下次使用前重新读取。联盟真实授权提交、实际接受/拒绝、后果、保存和新进程重载尚未验收，goal active。

**历史检查点（2026-10-13，r12联盟查询验收）：** r12 使用独立安装记录 `work/runtime/alliance-query-20261013-r12/installation.json` 和 `build-manifest.json`，身份为 PID `58260` / session `58260-1dd5b002515dbe9`，DLL SHA256 为 `e767d6ad30ec1b3e1c19a3df18d8246781420eade3bef582e450baefdd35456f`；这些身份只适用于该实验，后续运行前必须由根代理重新核对。报告基线和结束快照均为 POR、raw date `56459880`、paused=1，preflight health 为 ready。完整报告为 `work/runtime/alliance-query-20261013-r12/validation-alliance-20261013T105346Z-73e73a09cc94/validation-report.json`，`status=passed`。

`semantic-results.json` 记录39项目录和7个原生 UI selector inspect：FRA→SAV/ENG/POR/PRO 的 Offer，以及 FRA→SAV/SCO/PRO 的 Dissolve。原生 selector、button `+0x90` 和 specific validity `+0x80` 的发起层覆盖为 `complete=true`；Offer FRA→SAV 为 visible/available，native_total=64，六项中文名称和原生值 `[-25,20,7,4,50,8]` 可读；ENG 为 visible/unavailable，POR 为 visible/available 但没有原生 AI 接受预测；Offer PRO 为 hidden/unavailable；Dissolve SAV/SCO 为 hidden/unavailable，Dissolve PRO 为 visible/available。Offer 的原生项目标识、文本编码核验、单位/尺度、理由列完整性、费用/参数成本和最终响应仍未知；Dissolve 是单方动作，acceptance 为完整的 `not_applicable`。静态与实际调用链详见 [`gui-alliance-rule-coverage-20261013.md`](work/runtime/alliance-static-20261013/gui-alliance-rule-coverage-20261013.md)。这些结果只适用于 r12 绑定身份和当前场景。

代码侧73项 bridge tests 已通过；r12 `validation-report.json` 另证明九个固定 wire guard 全部匹配预期错误码且 `submitted=false`，四个只读探针前后稳定摘要相等。四个统一 API 的目录、查询、结果持久化和请求幂等/冲突检查通过；`execute_diplomatic_action` 仍因 adapter 未实现而返回 `invalidated`/`submitted=false`，`get_diplomatic_result` 的 business outcome 保持 unknown，这不是游戏或 AI 拒绝。报告中的 `native_token_generated=true` 只表示负向查询 guard 已产生 token，不表示业务外交提交；observer 的 authority 为 false、所有命令仍透传，`native_execution_enabled=false`。只读 transport-owner 证据 [`transport-owner-live.json`](work/runtime/alliance-query-20261013-r12/transport-owner-live.json) 已核对 server getter `0x811ad0`、UI/world dispatcher 一致、transport `+0x30=0x1580270` 和 counter 可读，但 `alliance_sender_runtime_verified=false`、`authorization_lifecycle_runtime_verified=false`，不能把它当作联盟投递或授权完成。查询请求已采用原子 hardlink 发布以修复 partial-file reader race。权限隔离、正常原生构造/投递、真实接受/拒绝、撤销、后果和保存重载业务证据仍未完成，goal active。

**历史检查点（2026-10-13，r10查询运行）：** 独立r10已在新进程载入 `llm_diplomacy_observer_returned_20261013_r3.eu4`，POR / raw date 56459880 / paused=1 / 帧持续增长，当前无需手动恢复窗口。当前身份 `59036-1dd5af393abfe07` 仅适用于本实验，使用前重查；DLL SHA256 `37cbb23fddc1a747b59a67522dcf3c54b9082e8e77706108b23421d659a77fa9`，安装记录在 `work/runtime/alliance-query-20261013-r10/installation.json`。FRA→SAV查询common/specific/initiation均true，总值64，六行数值为[-25,20,7,4,50,8]；原生行字符串size=0，名称/标识未恢复，明细仍不完整。中文诊断为补丁编码，不是UTF8，暂不输出乱码；后续恢复明细参数与编码。校正接口结果在 `value-only-query-output.jsonl`（早期first-query-output中的空名称/details_available=true已被修正，保留为历史）。r9结束于安装层、无帧无查询；不再使用其旧PID或待消费确认请求。完整合法性仍unknown，授权隔离及业务提交未开启，goal active。

**开发增量（2026-10-13，r12）：** 已完整读取 `work/临时prompt/外交系统开发goal.md` 并继续实际开发，goal仍为active。四个统一语义API（`list_diplomatic_actions`、`inspect_diplomatic_action`、`execute_diplomatic_action`、`get_diplomatic_result`）覆盖39项目录；r12 已恢复联盟原生 UI selector 和发起层规则覆盖，7项 Offer/Cancel 查询通过，完整发起层为 `complete=true`。接受度仍按动作区分：Offer 的明细标识/尺度/最终预测待恢复，Dissolve 正确返回完整 `not_applicable`。执行 adapter、权限隔离、业务提交、实际 accept/reject 与后果尚未完成；SQLite claim 与实际 native 提交分开，不能把 claim 当作 `submitted`。

**本轮运行证据校正（2026-10-13）：** `work/runtime/alliance-observer-20261013-r3/save-observer-report-1791874981964909800.json` 记录的 `session.pid=14556` 仅是该归档实验的旧身份，不能当作当前进程；同一报告证明 autosave 有效（POR、1445.3.12、哈希及恢复文件均有记录）。`work/runtime/alliance-observer-20261013-r5/save-reload-validation.json` 的保存哈希、新进程、日期/玩家/暂停、外交官和联盟持久字段检查均为 true，但 `alliance_business_acceptance_verified=false`，所以保存/重载结果不等于联盟业务验收。`work/runtime/alliance-query-20261013-r7/native-inspection-ai-candidates.json` 只证明候选查询得到部分 common gate/native validity 与原生总值（包括64、5、27）/reason_count（可见项为6），预测响应仍 unknown、明细和尺度未验证、visibility unknown。r9 虽已有构建产物，截至本记录未安装；PID 52544 只是待复核的临时记录。

**历史检查点（2026-10-13 16:50 后，r9安装）：** r9 已安装到经创建时间、exe/DLL 哈希重新核对的 PID 52544，身份为 `52544-1dd5aeb2cc2ff22`；前段“未安装”记录已被此检查点更新。DLL SHA256 为 `7241612810cc0fc564aaaced5f5a1dca15decbb3bff43ea8eb51f64ef97628a9`。当前游戏窗口最小化，没有帧回调，载入确认请求尚未消费；因此安装成功不等于载入/查询运行验收。已请求用户恢复窗口，无须点击游戏按钮；不得重复注入。定位器改为已知 UI 根优先、限时续扫，独立预算耗尽保留游标。r10 的接受原因文本/数值复制代码已严格编译，SHA256 为 `37cbb23fddc1a747b59a67522dcf3c54b9082e8e77706108b23421d659a77fa9`，尚未安装或运行；新构建必须使用新进程。

**联盟线索与边界：** `work/runtime/alliance-static-20261013/alliance-static-audit.md` 记录 Offer/Cancel 的共享对象、variant、构造与规则候选。`response-chain-native-summary-20261013.md` 进一步证实 UI 暂写状态1/2→clone/wrapper→owner transport 链；`reason-layout-static-summary.md` 证实48字节接受原因行的有符号数值、字符串和布尔字段。`decision-semantics-branch-map-20261013.md` 以原生分支及消息文本确认 Offer 状态2接受、1拒绝、recipient作响应选择；这是静态语义，尚未验证当前请求的实际响应或后果。`authority-entry-coverage.md` 确认 `0x3d2350` helper 直接调用断盟业务方法，故仅拦通用命令入口不足。格式化名称不能当成已核验原生标识；观察模块全部透传，不承担 FRA 权限隔离。

**系统开发安排（2026-10-13）：** 已建立[外交能力矩阵](docs/外交能力矩阵.md)和[外交接口开发方案](docs/外交接口开发方案.md)，统一记录接口、原生规则复用、权限主体、授权执行和持久化证据。后续先完成当前动作的规则覆盖与公共实验复核，再以联盟完成查询、隔离、授权执行、双方响应及实际后果的完整示例。旧文件中的优先顺序保留为历史，以新方案的当前开发顺序为准。

**规则复用要求：** 优先调用游戏原本的动作选择、合法性、条款/费用、接受和执行复检方法。来源授权不能绕过游戏规则。保证独立与支持独立分别登记；政体和属国限制由引擎评估，不能按概括规则重写。本机共和制改革文件存在 `royal_marriage = yes` 的例外。现有固定宣战脚本尚未证明与普通宣战全规则等价；和平有效性调用也不能证明所有条款条件都已覆盖。本轮只核对源码、既有证据与原版脚本，没有新运行验收或修改 DLL。

**窗口模式后台测试增量（2026-10-07）：当前 PID31872 / control v3 / POR / 1445.2.5 / 暂停。** 用户关闭游戏后，助手重启并载入 `llm_control_por_recall_after_20261007.eu4`，自动确认成就提示。配置 fullScreen=no、borderless=no；约5秒测试中前台PID一直为3652，游戏帧3302→3940，后台暂停请求消费成功，日期不变。证据 `work/runtime/windowed-background-control.json` 和 `windowed-before/after.json`。可先在聊天前台继续操作，不需默认每步请求切回游戏；最小化与长时间后台闭环未验收。该进程没有召回模块，不重复注入。

**历史运行状态（2026-10-07 外交官召回）：PID 48184 / control_recall_v5 / POR / 1445.2.5 / 暂停。** 用户布置 POR 外交官0在FRA改善关系，1/2分别4天、8天返回。本轮先原生 autosave 保存现场再重启，安装独立 v5，成功执行 POR 外交官0的原生取消命令：active 2→1，12天返回；日期未推进，另外两名记录完全未变。前后存档的 action 分别 `[2,1,1]`→`[1,1,1]`。召回与保存已验收，12天后空闲及结果重载尚未验收。无待处理请求，不再给本进程重复排召回（一次成功限制），不热替换DLL。v5 SHA256 `E29E17CB419176573C4AE1E7C087D3A38E6261A75705EA028C8A619EF7B2DB39`。证据 `work/runtime/por-recall-v5-validation.json`、`por-recall-save-comparison.json`，详情见 `work/game-control-experiment.md` 最新节。

2026-10-07 游戏控制实验：载入→推进 35 天→原生 autosave→改名→新进程重载的五个步骤已通过，POR / 1445.2.5 / 暂停 / 英法战争关联一致，原有三份自动存档恢复且哈希一致。证据 `work/runtime/control-save-validation.json`（reloaded=true）。当前 PID 30196 / control v3，已暂停。首次推进在载入转换期被暂停状态覆盖，补发后成功；外部编排新增 120 帧等待尚待整轮复跑，不能称为单次无人值守闭环。`savegame` 返回成功却无文件，改用 autosave。v2 曾因过早暂停空指针闪退，v3 就绪检查已实测避免该崩溃。v9 未改动。已继续定位运行中载入链，并严格编译固定 FRA 外交官0原生召回候选 v4，未安装/验收。详见 `work/game-control-experiment.md`。不得继续使用 control v2，不同进程模式不可混装。

更新：2026-10-05。本文件是当前状态入口；`VALIDATION.md` 保存时间顺序的实验记录。旧报告中的推断可能已被后续实验推翻，不以旧标题判断当前能力。

**历史状态：v9 同进程自动宣战→授权白和平已验收。** 固定 DLL SHA256 `1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3`，当时 PID32336/玩家POR。DLL帧线程自动执行正式compiler的FRA→ENG/cb_core/177脚本，ACK applied，快照ai/war/locked均1；自动实验tag FRA→winwars→tag POR后玩家恢复。宣战耗尽空闲外交官，用户推进约一个月后自动提交白和平，授权2执行状态0→2，最终只读英法战争数组均为空。宣战议和之间没有重启。单入口 `tools/run_diplomacy_cycle.py --pid <PID> --test-winwars` 串联并等待门槛；动作入口 `tools/request_diplomacy.py`。详见 `work/automated-diplomacy-v9.md` 和 `work/runtime/v9-cycle-validation.json`。自然战争分接受、保存重载、玩家FRA仍未验收；外部模型服务尚未接入。当前保留v9，不要同进程热替换。

**历史状态：v7 授权赔款已通过原生 AI 接受、金币结算、保存和重载验收。** 英国扣款34.400，法国及五盟友合计入账34.400，双向休战、战争结束、领土不变。结果重载为PID25340，用户确认仍和平；证据见 `work/native-authorized-gold-test.md` 和 `work/runtime/authorized-v7-gold-save-comparison.json`。下方旧进程模式及时间顺序记录为历史。

## 目标和可行性结论

目标：单机玩家与外部 LLM 交流；LLM 决定法国等受控国家的外交和战略，原生 AI 保留军事、经济操作。LLM 应能向玩家及原生 AI 国家发起原生议和，最终取得受控国外交的唯一权限。当前不开发游戏内聊天框。

已经证明本机版本(1.37.4)存在可用的内部控制路径：脚本状态导出、有限动作、原生和平构造/费用/投递/结算，以及原生和平权限拦截均有实测。无需以联机接口作为这些操作的前提。

这还不是完整、稳定的 LLM 对手。部分剩余工作是工程整合，完整外交覆盖、其他条款和信息可见性仍需技术验证。没有公共 SDK、完整游戏源码或跨版本兼容承诺。

## 已验证能力和证据

| 项目 | 实验结论 | 主要证据 |
| --- | --- | --- |
| 脚本快照、有限动作 | 本国状态导出、桥接标记、法国带锁宣战实测；不等于全部外交 API | `VALIDATION.md`、`bridge/README.md` |
| 原生 AI 作战 | 用户确认法国和盟友正常作战；和平锁试验中军队仍正常行动 | `VALIDATION.md`、`work/runtime/native-peace-lock-validation.json` |
| v9 自动宣战与授权白和平 | 玩家 POR；同一进程固定 FRA→ENG `cb_core` 宣战，实验战争分后授权白和平，英法战争数组清空 | `work/runtime/v9-cycle-validation.json`、`work/runtime/v9-cycle-native.jsonl` |
| 对玩家原生白和 | 修复战争参与国初始化后，接受正常结束战争；该次白和曾重载验证 | `VALIDATION.md`、`work/offer-initializer-audit.md` |
| 对原生 AI 白和平 | 玩家 POR、法国/英国非玩家；FRA→ENG 命令进入执行器，状态 0→2，战争结束 | `work/runtime/native-ai-whitepeace-acceptance-evidence.json` |
| 上述白和平保存结果 | 1445.6.9 保存；英法活跃战争 1→0、双向停战；2472 个有主省份所有者无变化 | `work/runtime/native-ai-whitepeace-saved-validation.json` |
| 原生赔款构造/费用 | setter/getter 一致：34400 内部金额，预计 34.4 金币，原生费用 1 战争分 | `work/runtime/native-ai-gold-roundtrip-interference.json` |
| 对玩家国家要求赔款结算 | 玩家接受后战争结束、国库整数显示 45→11；精确扣款和赔款后存档重载未验证 | `VALIDATION.md`、`work/native-gold-setter-audit.md` |
| 法国原生AI议和权限拦截 | 拦截 ENG→FRA 一次、FRA→POR 两次；推进超过一月仍交战、军队正常 | `work/runtime/native-peace-lock-validation.json`、`work/runtime/native-peace-lock-after.json` |

v9 自动白和平实验使用 `winwars` 作为实验战争分夹具，不能代表自然战局下的接受率。v7 白和平和金币赔款的保存重载证据继续保留；v9 保存重载尚未纳入本轮验收。

## 还没有完成的部分

1. **完整外交权限隔离。** 脚本 `llm_diplomacy_locked` 只限制普通 `declarewar` 和 `break_alliance`。原生锁只识别和平 action 类，未覆盖联盟、婚姻、保证等其他外交。事件/脚本直接结算也不是该锁的覆盖范围。
2. **授权通道工程化。** v9 已在原生和平锁保持安装时完成同进程授权白和平，v7 金币赔款路径已有独立保存重载证据。多人、跨版本、其他外交动作及长期运行未验收。
3. **其他条款。** 本轮一次性金币赔款34.4已核对实际结算；持续战争赔款和割地未实现/验收。历史割地是原生竞争和约，不能视为桥接成功。
4. **命令稳定性。** v9 已把空闲外交官和 FRA→ENG 关系冷却纳入运行前检查，并完成一次同进程验收；其他状态和长期运行仍需继续测试。
5. **信息边界。** 本国导出有限；视野内外国信息过滤、战争迷雾、秘密信息不泄露尚未验证。不得直接把完整存档或全部内存交给模型当作公平情报。
6. **模型与外部交流。** 当前实验由 Codex 人工决定请求，没有接通真实常驻 LLM 适配器、自动战略循环或外部聊天产品。没有 API 凭据；Codex/其他 harness 的正式适配未验证。
7. **工程指标。** 长时间运行、多国家、版本适配、失败恢复、操作频率、token 消耗和延迟都没有完整实测。64 项一次性观察队列不适合长期服务。

## 当前进程内模式：AutomatedDiplomacy v9

当前 DLL 为 `eu4_bridge_automated_diplomacy_v9.dll`，SHA-256：

```text
1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3
```

- `work/native/start-automated-diplomacy.ps1 -SavedTestGame` 安装 v9 并检查玩家 `POR`、`FRA`、`ENG` 的原生身份。
- `tools/run_diplomacy_cycle.py --pid <PID> --test-winwars` 串联固定 `FRA→ENG/cb_core/177` 宣战、实验战争分、外交官/关系冷却等待和授权白和平。
- `work/runtime/v9-cycle-validation.json` 记录同进程验收；`both_pair_at_peace=true`、`player_slot=189` 表示英法战争结束且玩家恢复为葡萄牙。
- `tools/request_diplomacy.py` 可单独创建 `declare_war`、`whitepeace`、`gold` 请求。当前没有真实 LLM 服务。

## 历史 v7 进程内模式

最后验收的是 `eu4_bridge_peace_lock_v1.dll`，启动开关 `-PeaceAuthorityLock`。其 SHA-256：

```text
230A6A81153D1CE6D2B94113126A87E7AA1421A245437C38465889C9C545105F
```

- 在 generic command 执行入口核对 command vtable，再识别已经验证的和平 action vtable。
- 用数据库中当前完整 FRA 句柄匹配双方，阻止所有涉及法国的和平请求与响应，不猜状态编号的决策主体。
- 其他国家之间的和平和非和平命令原样转发；原生军事经济 AI 没有被整体禁用，但经济未做独立压力验收。
- 已识别的被锁动作不会因日志字段读取失败或日志队列满而放行。
- 如果法国数据库对象身份读取失败，当前实现会透传；此时不能声称隔离有效。需运行预检与后续健康检查。
- 这是进程内 hook，退出游戏即消失；载入存档不等于卸载 DLL。
- 激活依据是 `peace_authority_lock_installed`。通用 `hook_installed` 行仍可能标注 `observe`，不能单凭它判断业务模式。

当前未验收完整外交隔离，不要将其他未知 action 按和平布局直接封锁。

## 环境与文件

```text
项目：当前仓库根目录
游戏：通过 local.env 的 EU4_GAME_ROOT 指定
用户数据：通过 local.env 的 EU4_USER_DATA 指定
Python：通过 local.env 的 EU4_PYTHON 指定
编译器：通过 local.env 的 EU4_CXX 指定
工具：通过 local.env 的 EU4_OBJDUMP 指定
```

首次运行前复制 `local.env.example` 为 `local.env`，只在本地填写路径；`local.env` 已被 Git 忽略，不应发布。

Windows x64、EU4 1.37.4；游戏 exe SHA-256：

```text
B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77
```

原生代码在 `work/native/probe.cpp`、`frame_stub.S`；构建/加载入口为 `build.ps1`、`start-probe.ps1`、`inject_probe.py`。自动重启为 `restart-game.ps1`。旧 `-Sender` 因曾接受崩溃由 `SEND_DISABLED` 禁用，不要移除保护标记。

DLL 的原生地址全部是 build-specific RVA，必须用当前进程模块基址计算。不要记住 PID 或绝对内存地址；重新枚举进程。自动启动返回的 PID 也可能不是最终游戏进程。

## 安全复现和平隔离

在项目根目录运行。只使用已另存的实验战役，保留正常存档。

1. 有旧 DLL 时，由助手执行自动重启；保持原启动参数，不批量结束同名进程：

   ```powershell
   .\work\native\restart-game.ps1 -SavedTestGame
   ```

2. 用户手动载入交战基线 `llm_ai_peace_before.eu4`，保持暂停；先核对当前 player、双方对象及战争。文件名曾被覆盖，不能认定永远是 1445.5.23；最近使用的基线为 1445.5.30。
3. 由助手执行当前和平锁安装：

   ```powershell
   .\work\native\start-probe.ps1 -SavedTestGame -PeaceAuthorityLock
   ```

4. 检查 `work/native/probe.jsonl` 的 `peace_authority_lock_installed` 与持续帧日志；`country_valid=true`、`thread_changed=false`，另用只读探针验证 FRA 完整句柄。
5. 安装后，用户保持暂停执行 `tag FRA`、`winwars`、`tag POR`，然后推进一个月以上。这是触发原生议和意图的试验，不是自然战争策略评估。
6. 预期：出现 `native_peace_authority_blocked`，战争继续，军事操作正常。不能只凭没有议和就判定发生了拦截。

当前锁的重建命令：

```powershell
.\work\native\build.ps1 -OutputName eu4_bridge_peace_lock_v1.dll -TracePeaceResponses -TraceCommandExecution -PeaceAuthorityLock
```

重建改动后必须重新审查并同步加载器哈希，不能随意取消哈希校验。当前源码已演进；历史发送 DLL 不保证能由当前源码重建出同一哈希，不要重编后继续套用旧验收结论。

同一游戏进程不支持替换/卸载/重复安装 DLL；加载失败也不要同进程反复尝试。换版本需要重启，但同一 DLL 的多次实验不要求每次重启。模组脚本的重载限制与 DLL 限制分开判断。

## 请求、验证与停止

- 发送版曾使用 `whitepeace.request`、`gold-peace.request`；构造检查使用 `gold-roundtrip.request` 等。安装会清除过期请求；仅创建文件不等于已经消费或发送。
- 当前和平隔离版禁用发送，不得继续条款测试。助手负责安装和请求文件，用户不必手动执行 PowerShell。
- 后台游戏帧可能停止。需要用户返回游戏使帧运行，不要把“返回窗口”误写成“必须推进日期”。暂停时能否处理某条完整链路要以日志判断。
- 证据分层：生成请求 → 消费 → 构造有效 → 入队 → 执行入口 → 原生响应 → 战争/条款结果 → 保存 → 重载。不能跳层命名为成功。
- `state_raw=2` 与本次和平成功关联；`state_raw=1` 分支不进入和平执行函数。不要把编号推广到其他外交类。
- 原生金钱条款使用 setter/getter；`offer+0xf0` 是汇总战争分单位，不能直接当金币金额写入。
- 停止原生 hook：退出并重启游戏，不安装 DLL。`run llm_stop.txt` 仅清理模组标记，不卸载原生 DLL。不要调用 FreeLibrary 尝试热卸载。

## 后续优先顺序

1. 保留已验证和平锁；建立其他外交 action 的 vtable、国家字段、生命周期及权限主体清单，逐类扩大隔离。generic wrapper 的公共前缀证据不足以证明所有动作布局相同，也尚未排除军事经济共用该 wrapper。
2. 做明确 LLM 授权通道，验证原生 AI 不会借用授权，外来提议可供 LLM 决定；不能根据相同日期/金额猜测请求来源。
3. 在权限隔离有效时，先复验原生 AI 白和平，再做赔款原生结算/存档/重载，最后割地等条款。
4. 完善公平状态导出和日志协议，再接模型/harness、外部聊天与战略循环，最后测多国家、频率、token 和延迟。

## 阅读索引与交接资产

- 进度和证据：`PLAN.md`、`VALIDATION.md`、`work/runtime/native-peace-lock-validation.json`、`work/runtime/native-ai-whitepeace-saved-validation.json`。
- 权限边界：`work/native-ai-diplomacy-lock-inventory.md`、`work/native-peace-authority-hook-audit.md`。
- 原生结构/通道：`work/offer-initializer-audit.md`、`work/native-gold-setter-audit.md`、`work/native-response-state-branch-audit.md`、`work/native-peace-dispatch-gate-audit.md`、`work/native-peace-queue-audit.md`。
- 把这些报告与代码交给新对话；不依赖旧子代理的聊天记忆。细节有冲突时先核对证据日期，再看本文件状态，未解决矛盾不能自行补成成功。
- 换电脑还需同版本游戏、工具链、已部署 `llm_bridge` 模组与两份实验存档：交战基线 `llm_ai_peace_before.eu4`、和平结果 `llm_ai_whitepeace_accepted.eu4`。它们在项目外的用户数据目录，单独交接并核验内容，不覆盖原件。

## 用户操作偏好与资源事故

不使用电脑/UI 自动化；用户负责载入、暂停、控制台和推进。助手自动重启游戏、安装 DLL、检查日志/存档和生成请求。已授权常规实验操作，不需重复询问每个可逆步骤。

用户允许委派机械/独立工作，但必须限制资源和收尾。2026-10-05 两个子代理遗留的 `pwsh` 全量读取约 350 MB 反汇编，各提交约 9–10 GB 内存，导致换页风暴；已终止，游戏正常。不要重开这些命令。

开始任何内部分析前读 `work/AGENTS.md`：先查大小，超过 10 MB 使用 `rg` 或流式 Python，只反汇编必要函数范围；分析进程提交内存不得超过 1 GB。代理结束前收集或停止其工具 session，不留后台扫描。


## 新对话启动文本

可将以下文字作为新对话的第一条消息，工作目录仍指向本项目：

> 请先读取 HANDOFF.md 和 work/AGENTS.md，再按 HANDOFF 顶部的 v9 状态和证据索引工作。当前入口是 AutomatedDiplomacy v9：玩家 POR，同一进程完成固定 FRA→ENG 宣战、实验战争分和授权白和平；继续验证自然战争分、保存重载、玩家 FRA 及更多外交动作。不要同进程热替换 DLL，不全量读取大型反汇编，不遗留后台进程。不使用 UI 自动化，重启和 DLL 安装由助手完成，载入/控制台/推进由我完成。

## 2026-10-05 授权议和实验增量（未验收）

后续对话已用指定存档参数启动 `llm_ai_peace_before.eu4`。弹出模组成就提示，用户确认后进入暂停地图；只读身份/日期与 POR、1445.5.30 基线一致。`restart-game.ps1` 新增 `-SaveName`，见 `work/save-load-launch-reference.md`。

独立实验源码 `work/native/authorized-probe.cpp`、构建 `build-authorized-peace.ps1`、加载 `start-authorized-peace.ps1`，未替换已验收的旧和平锁。新 DLL 以准确对象地址登记授权，沿已验证 native clone 槽传播，在析构槽撤销；保留未授权法国和平拦截。安装成功，但尚待无提交自检及新组合白和平/赔款验收。详细状态以 `work/native-authorized-peace-experiment.md` 为准，不能把编译/安装成功视为议和成功。

### 授权实验后续失败定位

v1/v2 的授权组合均未验收：v1 经 transport 后对象地址授权丢失；v2 登记协议身份后执行端仍未恢复来源。同一 v2 进程重新 winwars 后 preview=100，但请求仍被锁挡住，不能解释成 AI 拒绝。当前 build/start-authorized-peace.ps1 指向 v3 诊断版，旧已验证和平锁未替换。v3 已安装，未发请求；后续先确认此次重载后 tag FRA → winwars → tag POR，再发送，检查收发 protocol_key/protocol_flags。详见 work/native-authorized-peace-experiment.md 和 runtime/authorized-peace-validation-20261005.json。

### 当前实际运行状态：v5 授权入口通过，结算未通过

当前 start-authorized-peace.ps1/build-authorized-peace.ps1 对应 v5，SHA-256 5A285F642F8D69259BA166C804E0DF6897A31B0BD16F5DB2C6837AB040C37C02。v4 曾安装回滚；v5 安装成功。UI/world dispatcher 的同一 transport 原子序列计数器已只读核对，收到来源 0xffff 时以唯一原生序列号恢复授权，仅用于此次单机实验。winwars 后 preview=100，请求 state 0 到达执行器；其他原生 FRA 议和继续被拦截。用户推进后仍交战、暂无同授权 ID 的 state 1/2，FRA last_sent 未更新；不能宣称和平成功或 AI 已拒绝。证据见 work/runtime/authorized-peace-validation-20261005.json。

已准备接收字段诊断候选 v6，但没有安装或切换加载入口。它增加接收端参与方/owner 原始布局日志，不强制引擎接受；专用构建 build-received-offer-probe.ps1。下一轮应先比较反序列化后的字段，避免继续无证据推进日期。后台停止帧回调会拖住请求消费，但本轮已在前台消费且原生 AI 有新提议，因此后台不是唯一解释。


## 2026-10-05：v7 原生有效性诊断已编译，等待地图

本轮继续自主排查：v5 的只读 AI 队列为空，FRA/ENG 外交消息中未找到双方和平；不等于证明请求从未入队。证据 work/runtime/authorized-v5-pending-queues.json，工具 work/probe_pending_peace.py。v5 完整日志归档为 work/runtime/authorized-peace-v5-executor-entry-no-settlement-20261005.jsonl。

v7 在 v6 字段诊断基础上观察 peace vtable+0x80：原参数调用原生 0x59b480 一次，保留真实返回值，无附加引擎调用。安装/回滚与 clone/dtor 同一事务；自检 preflight 检查改为新槽身份。-Wall -Wextra -Werror 构建通过，SHA256 F989A4DE0BA60C1285907752179DD9626AEA2611ED1A1A42771410BF0952FAD3。独立入口 native/build-validity-observer.ps1、native/start-validity-observer.ps1；普通入口仍为 v5。

已重启独立基线 llm_authorized_winwars_baseline.eu4，当前 PID 48092；尚未安装 v7，等待启动提示关闭及暂停地图。安装成功、自检通过后，必须重新确认 tag FRA → winwars → tag POR，之后才能创建 whitepeace.request。不要以 entry、preview 或编译通过作为有效投递/AI 接受/结算证明。详见 work/native-authorized-peace-experiment.md 最新节。


### v7 后续关键发现

接收有效性实测 true，参与方 2/6/2/6/句柄/owner 正常；初始法国三名外交官全忙（存档 diplomats action=2），0x4e7e09 无空闲时提前退出。用户已召回一名。第二笔已序列化但没有进入执行器；缓冲未满。发现 command vtable+0x40（0x4e8660）还有 FRA→ENG 关系冷却，0x35a860 在外交官检查前设置该冷却。当前 threshold=56463312、current=56463336，已清除。已排队第三笔，等待前台帧及 3 天观察。当前 PID 48092/v7，不需重启或重复 winwars。全部证据和不确定性见 work/native-authorized-peace-experiment.md 最新节；不要声称 AI 拒绝或结算成功。


当前等待点：第三笔 whitepeace.request 仍在 native/ 目录，v7 最后 frame=10486；只有返回游戏才能消费。已向用户请求前台暂停约 10 秒，然后推进 3 天再暂停；尚无回复。当前 v7 实验继续，未关闭或再次重启游戏。v8 只编译未安装，SHA256 63A1DEECD867E258930A4A8D35ACCFBBA4D0C258D6466A6A07118829D5EB1186：在 DLL 源发送端加入空闲外交官和关系冷却的只读前置检查；独立 build-guarded-sender.ps1，下一轮才考虑安装。队列工具已加入这两项检查。


## 最新最终状态（2026-10-05）：授权 v7 白和平已保存/重载验收

authorization=4 同源请求 state0 → 原生响应 state2，preview100、原生有效性 true、完整参与方/owner 正常；游戏日期不变的暂停帧中完成白和平。存档1445.8.3 POR：双向休战、八国全部当天退出战争、八国领土不变。保存文件实际为前导空格+双扩展名，已保留并复制为 llm_authorized_whitepeace_v7.eu4。结果重载成功，用户确认推进几日无异常。

检查脚本 inspect_peace_save.py 已修正：当前战争只看 attackers/defenders，不以历史 participant/persistent 阵营判定；暂停结算保留历史数据，原误判交战1场现正确为0。回归检查通过。详细证据见 work/runtime/authorized-v7-whitepeace-save-validation.json 与 work/runtime/authorized-v7-paused-whitepeace-proof.json。

**当前游戏 PID 5428，运行已验证的 eu4_bridge_peace_lock_v1.dll（发送禁用），无排队请求；不是 v7。** v7 成功日志 work/runtime/authorized-peace-v7-paused-whitepeace-20261005.jsonl 已归档。普通授权 build/start 入口已更新为已验收 v7 与固定哈希 F989A4DE0BA60C1285907752179DD9626AEA2611ED1A1A42771410BF0952FAD3；下轮要 fresh process，禁止热替换/同进程重复注入。

成功前置条件除每次重载后 winwars 外，还有空闲外交官和 FRA→ENG 关系冷却。第一笔无外交官提前退出仍可写关系冷却；第二笔因冷却在命令门槛被阻止。使用 work/queue_guarded_whitepeace.py 做只读前置核对；前台帧必须产生，暂停无需推进日期。v8 已把门槛加入 DLL 发送端并严格编译，但未运行验收；赔款仍未验收。详见 work/native-authorized-peace-experiment.md 最终节。


## R40归档索引（归档后追加）

源码与证据索引已归档为 [R40检查点](work/runtime/r40-query-implementation-checkpoint-20261016-001/archive-manifest.json)，268文件、5469130字节，manifest SHA `f5e6fb01996b54088f23fe2edd5a64aac6fc89fa77e400b35a92150f88af8da2`。包含49源码不可变B构建引用、3次查询与24项离线复核、真实事件夹具和字段模型。当前root及三个worker全部工具会话已结束，B仍暂停；机器状态为work/runtime/r40-progress.json，完整goal保持active。后续从type3候选选择和完整议和授权继续。
