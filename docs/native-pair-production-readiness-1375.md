# 1.37.5 十个核心动作的生产接入准备审查

2026-10-12 更新：本文的FRA／当前玩家限制仅描述旧固定实验，不是产品要求。用户要求外部命令干预指定AI国家；新[指定TAG注入命令接口](tag-command-interface-1375.md)已支持独立actor/target解析，并取得POR→BRI、玩家仍FRA的原生队列发送证据。以下旧正式API及生产审查结论不代表新实验接口仍无发送能力，也不构成限制AI国家发起的理由。

结论：目前可以复用十个受限研究入口的构造、合法性、主线程守卫和部分效果证据，不能注册生产发送后端。机器记录为 `work/reports/native-pair-production-readiness-1375.json`，所有结论均限定于其中绑定的文件 SHA；本次没有访问游戏进程、创建 mailbox 或发布请求。

审查截面为 v6 seq 65、v7 seq 10，以及 v7 正向联姻/附庸在 PID 33256 的保存重载一致性报告。十个 ID 都有研究入口；九个有指定实验的状态变化，`cancel_vassalization` 只有合法性拒绝，没有取消成功证据。已有固定结果不能证明严格单人或同进程世界代次。

## 当前 Python 接口实际提供什么

| 接口 | 已实现语义 | 生产接入不得隐含的行为 |
|---|---|---|
| `GET /v1/capabilities`、`describe` | 目录、构建、adapter/hold 门控 | 静态映射不是可执行，读到 DLL 文件不是已接入 |
| `POST /v1/preview` | `contract_only` 参数检查，`game_legality_checked=false` | 不能悄悄变成原生合法性调用 |
| `POST /v1/requests` | request_id 持久幂等、冲突拒绝、先保存 dispatch identity/hold 再调用 adapter | HTTP 202 或 queued 不能当作外交生效 |
| `GET /v1/requests/{id}` | 读取并核对既有结果；可信 adapter 可刷新本地状态 | 不发布、不重试、不创建新原生对象 |
| `POST /v1/requests/{id}/reconcile` | 仅接收 `{}`，按原始 binding 做可信只读对账 | 客户端不能提供“成功”证据或解除未知发送 hold |
| `NativePairBackend` | 合成文件协议、独占发布、永久 ledger、事件链、只读观察/对账 | 当前 EU4LAB 研究 DLL 并不消费 EU4PAIR/1 |

HTTP 服务和本地 CLI 均直接构造无 backend 的 `DiplomacyAPI`。目录中的十个动作仍为 unimplemented，且没有本构建执行白名单。因此即使传入合成就绪 backend，真实目录的提交仍被拒绝。正式启用时必须同时审查动态绑定策略和目录执行注记，不能仅加一个 import 或把十个动作整体改成 runtime_verified。

## 明确的阻断项及最小验收

| 条件 | 当前可复用证据 | 仍缺的实现和验收 |
|---|---|---|
| 同一世界代次 | 加载入口 `74b8a0` 在解析前经 `5cf740` 清理、重置世界；多次实验重载换了进程 | 所有同进程加载、失败加载、开局、菜单、重同步和模式转换必须在旧世界被改变前撤销 session。原子 epoch 递增和路径覆盖需要独立验证 |
| 严格单人 | 原生 `6eaa10` 分类器及 `multi_player` 序列化语义已解；研究档序列化为单人 | 分类 false、单个玩家、transport/server vtable、启动参数均不能排除可加入的 MP host。需证明 offline-origin 初始化和全部模式转换失效路径 |
| 暂停 | 研究 pause manager、手动标志和原生分类候选；固定实验暂停执行 | 生产暂停语义需要独立验收，不能复制 pause_candidate。新 consumer 必须在认领、构造和原生调用前主线程复核；外部心跳不能排除间隙变化 |
| 生产 consumer | 研究宿主的主线程回调、精确 ASCII 解析、持久 claim、TTL、单次序号、日志失败停止 | 新原生宿主实际实现 EU4PAIR/1、私有目录/同句柄读取/持久 claim、event hash 链、store/session/nonce 绑定；不能重命名 EU4LAB 文件充当消费 |
| 即时国家与资源绑定 | 完整 handle/slot、当前日期、取消 spy 的唯一 mission/entry ID、其他取消方向/类型约束已有代码 | 每个请求在消费线程重新解析，公开请求只收 TAG。执行前资源再次校验；不能缓存预览中的外交官 ID 或固定 envoy 0 |
| 原生所有权 | 五类 lifecycle、二十种 command 生命周期；固定 submit 返回且 caller 容器被清空 | 新 consumer 必须保持同一移交表，并做日志失败/SEH/未知返回/崩溃窗口验收；调用进入后不得凭 bool 或旧指针补析构 |
| 精确请求与效果归属 | 本地 request/sequence 和日志强绑定；固定关系图及相关接受/拒绝通知 | 普通关系观察和通知都没有原生精确 request-ID。需要同一 generation 内的 command 执行/响应关联或更窄的已证明归因方案，才可将该请求升级 applied |
| 每动作、方向和环境白名单 | 固定改善已保存重载；NAV 正向联姻/附庸在测试夹具下保存重载一致 | 取消附庸仍未生效；其他多项未分别保存重载。测试夹具条件必须进绑定，不能推广为普通条件或其他 actor/target |

详见 [世界代次静态研究](native-world-lifecycle-1375.md)、[取消构造](native-pair-cancel-1375.md) 的事实和边界。`game` 指针、玩家 handle、日期、`+7480/+7485` 布尔值都不能充当 world generation：同地址同日期重载及一次置位再清零会逃过采样。加载失败也必须撤销，不能仅在加载完成时递增。

## 可实施的窄范围绑定

第一版只接受：固定 EXE SHA、新生产 DLL SHA、一个持久 store、一条 native session、一个已证明 epoch、严格单人、当前玩家为 FRA、暂停、同一主线程、同一时刻一个未完成请求，以及逐项批准的 action/actor/target。NAV 正向实验需要明确测试夹具 profile；默认生产环境不得把夹具视为已经启用，也不得自动调用 fixture_on。fixture、速度控制和脚本输入不属于生产外交协议。

不要把世界代次缺口改写成 `one_shot`、只看指针、给 session 换名或让客户端填写 UUID。它们均不能阻止请求被投递到 ABA 重用的世界。最小可靠方案仍是新宿主在所有可能破坏世界的入口之前撤销授权：

1. 进入经证明的加载/重置/模式转换路径时，先将 `session_valid=false`，原子递增 epoch；不接受新认领，不消费旧序号，不自动重新握手。
2. 已过 dispatch_intent 的记录维持 unknown；未过该界且能证明没有调用和已安全清理时，可明确记录 rejected_before_dispatch。不能删文件后声称未执行。
3. 只在新世界完成、线程稳定、严格单人和暂停证明全部重新建立后，由可信宿主创建新的 native nonce/session 并完成 challenge。旧世界对象和缓存 ID 永远不进入新绑定。
4. 独立只读 verifier 必须核验实际映像、已加载 DLL、epoch、模式和暂停；不得直接复述 JSON 心跳。校验代码本身绑定静态报告和模块版本，失败只会降低 readiness。

建议将下一版经过审查的配置扩展成 `scoped_binding_v2`，而不是修改当前白名单填 true：

```text
binding_profile_id
game_sha256, dll_sha256, native_consumer_protocol
world_generation_method, single_player_method, pause_method
player_actor_only=true, max_inflight=1
environment_profile_sha256 (ordinary 或精确 fixture profile，不能为通配符)
tuples[{action,actor,target,verifier_id,evidence_manifest_sha256,
        resource_binding_method,dispatch_verified,effects_verified,reload_verified}]
```

这是未来配置设计，当前 `_configuration()` 会因 exact keys 拒绝它。实施时应增加明确 schema 版本、迁移/兼容拒绝测试、绑定文件 SHA 和原生握手字段；没有新的审核清单就继续 unsupported。API 的持久 `dispatch_identity` 可复用现有 `store_id/session_id/pid/creation/world_generation/game/dll/experiment/whitelist`，新增环境与方法承诺通过固定 experiment SHA 绑定。一个新进程或新 DLL 的证据不能冒充旧 session 的恢复身份。

## 外交官和取消的消费时规则

公开参数仍只接受 actor/target TAG，不接收 pointer、RVA、完整内部 handle、envoy ID 或原生回复 state。国家完整 handle、slot 和对象必须在消费回调里从当前数据库解析；FRA 之外的 actor 暂不开放提交。

- 普通正向动作初始 envoy 保持 `-1`，让已验证的原生 command 资源路径选择。预览时看到一个空闲外交官不等于预约成功。调用前再次检查原生 gate，并在真正执行阶段记录资源结果。
- 停止间谍网必须唯一绑定现有 active entry、mission、task、完整 actor/target 和 entry ID；setter 后、clone 后及提交前再次核对。不能只按 slot 取首个任务，也不能把上次请求的 ID 带入本次。
- 停止改善关系通过对应关系析构召回 mission；不额外调用一次召回，也不要求立即空闲。停止间谍任务不能要求已积累网络值归零。
- 撤销保独必须核对保证方向；取消附庸必须核对宗主方向和 `vassal/client_vassal` 定义。取消并不普遍免外交官或冷却；联姻、保独、附庸的取消仍经过相应公共资源路径。

`4e7c50` 的某些路径先写冷却、后检查外交官。这意味着“未观察到关系效果”不能反推完全无副作用，更不能转换成可自动重试的失败。资源不足应尽可能在原生提交前拒绝；一旦进入原生投递，状态证据必须按实际边界记录。

## 所有权与状态

复用现有 pair core 的原则：fresh factory 返回且布局确认后才归 caller；wrapper 的 command 拥有 clone；发送前安全清理由 command 析构同时销毁 clone，禁止另析构一次 clone。调用 context submit 之前永久记录 intent；进入调用后原容器可能转移给引擎，此后不再由桥接持有可释放对象。空指针/共享 sentinel 不证明 factory 内部完全没有分配，未知情况停止 session。

生产 event 链必须记录接收、永久认领、合法性、dispatch_intent、返回及错误。日志持久化失败会阻止下一次原生调用；若在调用后失败，只能 unknown，不补造成功。原生顺序号高水位还应拒绝 ledger 回滚、旧 claim、旧 nonce 和第二个 store 接管同一世界。API/传输的 SQLite 幂等与 holds 已实现，可复用，但不能替代原生唯一消费方。

| 状态 | 严格含义 |
|---|---|
| queued | 已持久发布可消费字节；未证明消费或调用 |
| dispatched | 有完整调用返回、容器移交及已知所有权；未证明接受或生效 |
| applied | 独立 verifier 对原始 binding 的请求效果建立充分证据 |
| rejected_before_dispatch | 明确未越过调用界，所有临时对象所有权已知且安全清理 |
| AI rejected | 有精确关联的原生拒绝证明；普通相关通知不够 |
| dispatch_unknown | 调用或所有权存在不确定；永久 hold，不自动重发 |

当前观察器的 `ROYMARACCEPT/REJECT`、`VASALLACCEPT` 是按国家、类型、日期和新消息对象关联，不应直接接到生产 `ai_rejected` 或 `effect_observed`。可先通过独立 observation 输出 `pair_state_observed/reply_correlated`，保持请求状态 dispatched。若缺少足以解除未完成请求的归因，第一版应继续阻塞新发送，而不是伪造终态。

一种待证明的归因设计是在绑定主线程执行入口观察原生 command：内部将当前被借用的 command 标识关联到持久 request SHA/sequence/epoch，在执行入口/返回记录动作和选定前后态；不得在所有权移交后从 Python 解引用旧地址。对于延迟回复，仍需另外证明 request/response ID 的创建和传播；不能靠同帧或“此时只有我的一个请求”排除 AI、事件及其他引擎来源。

## query、native preview 与现有 preview 分离

现有 `/v1/preview` 保持契约检查。若需要运行时 pair state 或原生合法性，增加单独、明确的异步 query 接口和独立消费操作，不能让 GET status 隐式构造动作或重发请求。建议 `POST /v1/queries` 接受固定 `pair_state` 或 `native_legality` 类型，返回 query_id；`GET /v1/queries/{id}` 仅读取结果。当前 HTTP router 与 EU4PAIR/1 submit grammar 均未实现这些操作。

pair_state 在绑定主线程做有界只读快照；native_legality 新建临时动作、wrapper、执行正常检查并安全清理，不调用 context submit。结果必须包含 exact build/session/epoch、frame、日期、TAG/完整身份的内部校验结论、暂停语义、查询类型、native_legality_checked/allowed；TTL 只表示新鲜度，不是资源保留。两者都不能扩展白名单，也不能使后续 submit 跳过全部检查。旧 epoch 的结果只能作为历史证据，不标为当前状态。

## 本轮可逆改进与验证

生产 Python 草案原先没有暂停字段，合成握手可在未提供任何暂停证据时 ready。本轮新增握手、heartbeat 和独立 live verifier 的必需 `paused=true`，拒绝缺失、false 和非布尔值；预约 ledger 后的再次检查若失去暂停，不发布请求，也不允许该 request_id 自动重试。既有 status/reconcile 仍可在以后解除暂停时只读查询。

此变化仅适用于未部署的 EU4PAIR/1 草案，不兼容旧合成握手格式，不声称任何 EU4LAB 研究 DLL 已支持它。37 项文件后端离线测试和 20 项 API 测试通过，包含暂停证据拒绝、投递前状态变化、不重发及真实目录仍 unsupported。正式 consumer、严格单人、全路径世界代次和 request effect verifier 仍未完成，生产白名单保持为空。
