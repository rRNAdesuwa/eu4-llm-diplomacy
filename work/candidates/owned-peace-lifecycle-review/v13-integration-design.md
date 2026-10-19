# v13 独立 owned peace 无发送阶段接入设计

状态：**设计文档，未创建 v13 源、宿主、构建目录、DLL 或加载器**。现有 v12 全部保持冻结。本目录的默认生命周期候选也尚未接入任何宿主。

## 已有编译证据

候选源码/静态布局 review SHA256：`d54536724c804f436aef58b59722cb768bc6c40e77787d676837b871faa97fec`。新增验证文件不改变这个准备期快照。

- 实际共享 checker：[验证 JSON](validation-results/20261007T205931Z-0bd138f75a5e42628fef83fcb0d03ada/validation.json)，SHA256 `6833295d82c5d892a84fba1d5f33a914b252daa3d7c09361c49e3a04931b3201`，41 项检查、0 失败。
- 实际生命周期 CPP：[object 编译验证 JSON](validation-results/lifecycle-object-20261007T210445Z-66896e43a4734f6bb87a39305726fa15/validation.json)，SHA256 `bc005b3b25cef090fafe88d9cb03f1797e427a7b7f8b74a1dd641d96d3b8a10e`，MSVC `/c /std:c++17 /EHsc /W4 /WX` 退出 0，无诊断。实际模块 object SHA256 `2d09568c02ef6e092cd02674a834f531305495ff28ca453e29b8b72483a8941b`。

第二项确实编译了 `peace-owned-lifecycle-1375.cpp`，不是拿 checker 编译替代。没有 DLL 链接或原生运行证据。编译不能证明 ABI 正确、堆完整、析构无泄漏或外交可发送。

## 明确的阶段顺序

建议只在 root 完成独占审查、另行批准 materialize 后，以新的源和私有会话目录接入：

1. 安装 frame hook，完成既有 session/process/build/world 绑定，等待健康帧。
2. 显式触发原有 **20 family lifecycle**，仍按原有矩阵和计数验收；不混成 21 类。
3. 20 类全部通过且之后至少有一帧健康记录，才允许另一个显式、一次性的 **owned peace default lifecycle** marker。
4. owned peace 通过、完整 wrapper 结果已持久化且之后出现健康帧，才允许继续原有 72 preview 与 72 command 无发送阶段。
5. 若这份 v13 最终仍包含既有研究 mailbox，所有门槛都必须包含 owned peace 已通过。初轮只安排第 3 阶段；不因此自动生成任何外交请求。

每帧至多执行一个阶段或已有 mailbox 操作。阶段未请求就保持等待，不能自动创建 marker、自动补跑或把上个进程结果继承为通过。原有三阶段的 caller/返回记录与计数保持独立，旧 v12 verifier 不静默接收 v13。

## 新阶段身份与单次 claim

建议新 marker 名 `owned-peace-lifecycle.request`，固定精确 ASCII 内容 `OWNED_PEACE_LIFECYCLE_1375_V13\n`；它只在新 v13 私有 session 目录内有效，不接受任何国家、条款、地址或参数。协议名称在 materialize 审查时再最终固定，此文档不是已发布协议。

建议永久 claim 名 `phase-owned-peace-lifecycle.claim`。沿用已审过的有界 marker 消费和持久化规则：

- host 先检查精确 PID/创建 FILETIME、DLL/源 manifest、新 session 身份、暂停状态、窗口/游戏线程，以及 base20 已通过和后续健康帧。
- 使用 CREATE_NEW claim，在任何 native 分配或析构之前写全并 flush。claim 绑定 session、阶段、PID/创建时间、线程、manifest、当前完整玩家/世界观测信息；这些观测信息不是可靠 epoch 的替代。
- 从同一 request handle 精确核对内容后移除 request；claim 永久保留。重复、已有 claim、坏内容或消费失败按失败冻结处理。
- 标记 `owned_peace_tested=true` 必须发生在调用 core 之前；不能在失败后重新 armed。core 内部 `run_once` 也保留不可复位的独立一次性门槛。

原有请求 sequence 不应被这个固定 phase 借用或复位；它有独立 phase claim。不得为了重跑删除 claim、清掉 core 的 attempted，或热卸载已装 hook 的 DLL。

## 宿主与 core ABI

调用入口只有 `eu4_owned_peace_lifecycle_1375::run_once(const Host&)`。Host 传当前经验证的游戏线程、durable claim/full SHA/实验授权状态、bool logger 和 guard；参数不能来自公共任意 JSON。

guard 在 factory、clone、原件 dtor、克隆 dtor 之前各执行一次；logger 的 step-begin 必须全长写入并 flush 后才进入 guard。guard 至少重新核对：当前线程、同进程创建身份、会话未撤销、暂停、玩家完整句柄及已绑定世界/上下文、没有竞争操作或加载异常。可额外采用届时已独立验证的 epoch/source observer，但不能把目前的 roots/date 检查写成“已证明所有同进程重载安全”。

候选只调用固定 factory/虚克隆/虚析构，没有 parameterized war constructor、validity、preview、GUI、wrapper 或 submit。宿主不得在 wrapper 中追加这些调用。logger 应适配现有持久审计通道并准确返回 bool，不能把原来 void logger 的“调用过”当作 flush 成功。

## 日志与验收合同

建议 wrapper 记录新事件 `owned_peace_selftest_begin`、`owned_peace_selftest_complete`，不重用普通 `pair_selftest_complete`。每条绑定当前 session 的 PID/创建 FILETIME/线程和 phase；所有事件 `submitted=false`。新阶段期间 `send_enabled=false`。

现有 core 事件为 `owned_peace_lifecycle_step_begin` / `step_complete`，步骤固定 1→4，各仅出现一次，最后 `owned_peace_lifecycle_return(step=0)`。它们记录 uint 形式的 entered/returned 标志、mismatch masks、别名/存活核验结果、reason/exception；离线工具应严格接受 0 或 1，不能把其他整数转换成 bool。

wrapper 只有在返回 Result 同时满足以下条件时才能记录 passed=true：

- `reason=none`、`passed=true`、`audit_complete=true`、`freeze_session=false`、exception=0。
- factory、clone、原件 dtor、克隆 dtor 的 entered 与 returned 均为真。
- 原件与克隆 mismatch 均为 0；8 块分配逐项无重叠；clone 后原件不变；原件释放后 clone 仍完整且分配身份不变。
- wrapper 自己的新完成事件也写全并 flush，随后重新核验暂停会话状态。

Result 中 `retry_allowed` 与 `execution_verified` 必须始终为 false。core 最后一条日志不能证明该条自身已 flush；必须结合返回 Result、成功持久化的 wrapper complete 和**其后的健康帧**验收。

建议新增专用离线 verifier，使用日志固定字节快照、manifest、指定 PID/创建时间及前后只读报告，限定最新准确 session。它应拒绝缺失、重排、重复步骤、未知 stage、SEH、冻结、线程变化、任何 submit 事件或状态以及缺少最终健康帧。成功只给 `runtime_verified=owned_peace_default_lifecycle_only`，保持 `execution_verified=false`。前后选定 world/player/date/cooldown/envoy 观测相等也不能推断“全游戏状态无变化”或“所有内存无泄漏”。

建议健康帧新增独立 `owned_peace_tested` / `owned_peace_passed` 字段。base20/preview/command 的原字段不得被这个结果覆盖。

## 失败行为

任一 marker/claim/audit/guard/layout/alias 问题或 SEH 都撤销本研究 session，关闭 mailbox；禁止重试、猜测析构或 native 修复。core 的失败路径可能留下有限研究分配，不能声称释放完整。SEH 后 core 不调用 logger，host 应在调用返回后尽量持久记录 Result 并冻结；审计通道失败时也不能继续调用游戏。

出现未知所有权时，保留现有只读证据，结束进程的后续操作按独立受控退出流程处理。不能为“清理失败”对已装 hook 模块执行 FreeLibrary。

## 后续 materialize / 构建门槛

下一次真正生成 v13 前，root 需独占核对：隔离源 diff、candidate review/source/pins hash、object 编译证据、shared checker 41 项证据、host 日志/claim/guard适配、phase顺序、CLI/manifest/verifier的新版本隔离及离线状态机测试。随后才能批准一次正式 DLL 构建；此文档不授权自动构建。

第一次实验仅验默认空对象，不需要也不应该创建战争来使它“合法”。真实和平的战争 fixture、war identity/epoch、参与方方向、非空 terms 生命周期、完整命令移交、AI 回复、实际结算及保存重载属于后续独立任务。
