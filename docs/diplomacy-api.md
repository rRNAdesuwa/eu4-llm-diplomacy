# 外交对外接口

此接口把外交动作目录、参数验证、版本检查、请求幂等和审计统一到一个 JSON 协议。**动作出现在目录中不表示已完成原生逆向或可以执行。** 本机 EU4 1.37.5 的 SHA-256 为 `9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A`；仓库旧实验基于另一份 1.37.4 可执行文件。当前正式 HTTP/CLI 没有注册执行后端，生产 EU4PAIR/1 握手和原生消费者尚未部署。离线文件后端草案及独立 EU4LAB 研究接口不会改变这点：本页正式接口的提交明确返回 `unsupported`，不会产生游戏请求文件、注入 DLL、修改进程或改变存档。

已有 v9 `declare_war` / `whitepeace` / `gold` 的历史验证仍保留在目录的 `execution` 字段中。普通改善关系不能用旧桥接的 `add_opinion` 替代；王室联姻、保独、附庸、间谍网等动作也不能仅凭目录条目声称可执行。

截至本次审查，目录为 274 项、270 项静态映射；[研究能力索引](diplomacy-research-capabilities.md) 有36个版本化研究协议入口（关联37个目录条目）和二十八种固定历史状态效果，正式可执行动作仍为 0。v14已停止43步会话新增八项方向效果：禁运/撤销、固定补贴/取消、取消舰船停泊权、两种军事通行取消方向、解散同盟；授予舰船停泊权已提交但效果仍为 unknown。独立持久性审核另有9个选定状态，其中7个有序列化与重载一致证据，2个仅有带类型检查的重载缺席观察；不能把实验摘要的 save_reload_verified=false 改成统一true。v12原六项效果和20/72/72无发送预检保留，各版本历史证据不授权当前会话。研究 HTTP 使用独立 `/research/vN` 路由、显式进程绑定和永久序号账本，不等同于本页 `/v1`；历史效果也不证明精确请求因果、AI接受、严格单人来源或世界代次。

## 使用

Python 3.10+，仅使用标准库。从仓库根目录运行；`local.env` 的 `EU4_GAME_ROOT` 用于只读版本识别，也可明确传入 `--game-exe`。

```powershell
python tools/diplomacy.py capabilities
python tools/diplomacy.py describe whitepeace
python tools/serve_diplomacy.py
```

服务默认绑定 `127.0.0.1:8765`。CLI 不带 `--url` 时直接访问本地接口和 SQLite 队列；带 `--url` 时访问 HTTP 服务：

```powershell
python tools/diplomacy.py --url http://127.0.0.1:8765 capabilities
python tools/diplomacy.py --url http://127.0.0.1:8765 describe whitepeace
```

先查看 `describe` 中的 `parameters`，再准备 JSON 文件。例如，历史固定英法白和平的请求：

```json
{"request_id":"peace-demo-001","action":"whitepeace","parameters":{"actor":"FRA","target":"ENG"}}
```

```powershell
python tools/diplomacy.py preview request.json
python tools/diplomacy.py submit request.json
python tools/diplomacy.py status peace-demo-001
python tools/diplomacy.py audit peace-demo-001
python tools/diplomacy.py reconcile peace-demo-001
```

`preview` 是参数和能力预览，返回 `preview_kind=contract_only`、`game_legality_checked=false`。它没有读取游戏外交条件、计算接受概率或验证空闲外交官。`execution_allowed=false` 时，查看 `blockers` 中的具体原因。未完整确定参数的动作也会被阻止提交。

CLI 的 `preview/submit` 文件参数可使用 `-` 从 stdin 读取；`--queue-db` 可选择独立实验数据库。失败/拒绝/不支持的提交以非零状态退出。CLI 和 HTTP 不自动调用旧请求工具。

## HTTP 路由

| 方法 | 路径 | 内容 |
| --- | --- | --- |
| GET | `/v1/capabilities` | 全部目录条目、当前构建、逐动作执行门槛 |
| GET | `/v1/actions/{action_id}` | 单动作参数、证据、历史实现状态和当前门槛 |
| POST | `/v1/preview` | 验证请求和执行门槛；不入队、不执行 |
| POST | `/v1/requests` | 幂等提交；不支持也持久记录原因 |
| GET | `/v1/requests/{request_id}` | 请求与最新可核实状态 |
| GET | `/v1/requests/{request_id}/events` | 该请求的持久审计事件 |
| POST | `/v1/requests/{request_id}/reconcile` | 显式只读对账，只接受空 JSON 对象 `{}`，不重新发送 |

请求只能含 `request_id`、`action`、`parameters`。请求 ID 为 1–64 个 ASCII 字母、数字、点、下划线、连字符，首字符必须为字母或数字。未知字段和动作、错误类型、重复 JSON 键、非有限数值、违反枚举/范围/常量的参数均拒绝。JSON Schema 验证器对未知关键词拒绝处理，不会默默跳过约束。请求正文最多 64 KiB，必须为 UTF-8 `application/json`，不支持 chunked 编码。

错误响应通常为 `{"error":{"code":"...","message":"..."}}`。HTTP 状态：参数错误 `422`，未知动作/请求 `404`，同 ID 不同内容 `409`，不支持执行 `501`，投递结果不确定 `502`。`501/502` 的响应包含持久请求记录及原因。只有真正得到适配器队列回执才返回 `202`；`202` 不表示游戏效果已发生。

## 幂等、队列与证据

数据库默认位于忽略版本控制的 `work/runtime/diplomacy-api.sqlite3`，SQLite WAL + FULL 同步。请求正文使用规范 JSON 的 SHA-256，数据库唯一键防止同进程、跨服务实例和重启后的重复投递。相同 ID/相同内容返回旧结果；相同 ID/不同内容拒绝。重复提交不重新检查并自动执行历史被拒绝的请求。修改环境后需要一个有意创建的新 ID。

状态含义：

| 状态 | 已知事实 |
| --- | --- |
| `unsupported` | 当前构建、参数证据或适配器不满足执行门槛；没有调用执行器 |
| `dispatching` | 已持久登记，尚无持久适配器回执；也可能在投递期间崩溃 |
| `queued` | 执行适配器确认排队；游戏效果未确认 |
| `dispatched` | 执行适配器确认投递；游戏效果未确认 |
| `applied` | 适配器返回具有证据的游戏效果确认 |
| `rejected` / `failed` | 适配器返回具有证据的拒绝或失败 |
| `dispatch_unknown` | 调用异常或回执不足；可能已经投递，禁止自动重试 |

`game_effects_verified=true` 只对应 `applied`。观察失败保留已知状态并返回 `observation_error`，不会把无法读取状态写成执行成功或失败。客户端重试应复用同一 ID；进程崩溃留下 `dispatching` 时先对账，不能用新 ID 绕过不确定投递。该版本不提供自动重放、取消原生请求或队列清空接口。

API 在调用 backend.submit 前持久记录原始构建和 backend 身份并建立 `execution_holds`。尚无可信回执的 dispatching 或未知投递会冻结该 backend，冻结状态跨重启保留，新请求 ID 不能绕过。已认证的原生未知观察使用 `reason_code=native_dispatch_unknown`、`automatic_retry=false`，分别记录发送结果未知或对象所有权未知。

`reconcile` 只让原适配器读取账本、发布回执和证据，再同步本地 API 记录；它不会发布邮箱文件或调用原生命令。请求必须已存在，终态不可更改，客户端不能通过 HTTP 提交自己的 ack。适配器缺失时返回 `reconciliation_unavailable`，证据无效时返回 `reconciliation_refused` 并审计，当前状态不变。只有发送前持久绑定的 process/session/build/request 身份全部一致，且发送结果及所有权已知，才可恢复状态并解除 hold。旧记录缺少这份身份时不能用当前进程信息补造。

审计事件记录受控请求及检查结果，不导出整个存档、秘密情报或进程内存。数据库不是防篡改日志，应按普通本地实验文件管理。

## 原生适配器接入条件

`bridge.diplomacy_api.ExecutionBackend` 是供实现者使用的 Python 协议；现有 HTTP/CLI 启动入口不注册任何原生执行适配器。测试中的 `RecordingBackend` 只验证基础设施，不是游戏后端。

适配器需要实现 `name`、只读 `capability(action, build, parameters)`、`submit(request, build)`、`status(request, receipt)`。接口只有在目录参数为 `specified`、动作实现状态已验证、当前可执行文件 SHA-256 在该动作的 `supported_builds`、后端名称匹配且实时检查 `ready=true` 时才调用 `submit`。

适配器必须在实际写入的边界重新核验**当前进程**的可执行文件/模块/协议、生命周期和前置条件；只读磁盘文件哈希不是进程身份。需要完成的原生工作包括正确命令构造、状态校验、外交官/费用/耗时/冷却、原生 AI 接受或拒绝、授权隔离、游戏结果和保存重载证据，不能只把目录状态改为已验证。不得从 HTTP 接受原始 RVA、vtable、指针、脚本或内存写入。

`submit` 返回 `{status: queued|dispatched, external_id: "...", evidence: [...]}`。`status` 返回受支持状态及证据；`applied` 额外要求 `game_effects_verified:true`。队列消费、执行入口或实验日志行本身不足以满足该语义。

支持新恢复协议的适配器在 `capability()` 返回 `dispatch_identity`，并可实现 `ReconciliationBackend.reconcile(request, prior_record)`。完整的身份字段、回执、证据约束、10 个动作 ID 和原生邮箱设计见 [1.37.5 双国适配协议](native-pair-adapter-1375.md)。这些检查不会使静态动作自动可执行；当前仍没有注册 native backend。带身份的适配器，其 submit/status/reconcile 证据均必须绑定同一个原始进程和 session。

## 访问边界与测试

默认只允许 loopback Host，拒绝浏览器 `Origin`，不开放 CORS。可用环境变量 `EU4_DIPLOMACY_TOKEN` 设置 bearer token。绑定非 loopback 地址同时要求 `--allow-remote` 和至少 32 字符的 token；内置服务没有 TLS，应只在受控网络或具 TLS 的反向代理之后使用。不要把 token 写进命令行或版本库。

```powershell
python -m unittest bridge.tests.test_diplomacy_api -v
python -m unittest bridge.tests.test_diplomacy_reconciliation -v
```

测试涵盖版本拒绝、未实现动作拒绝、输入边界、持久幂等、并发重复请求、投递异常、效果证据门槛及真实本机 HTTP 往返。它们不会注入或启动游戏，也不构成各项原生外交行为的验收。

## 1.37.5 只读结构探针

`work/probe_diplomacy_current.py` 是独立的诊断工具，与执行 API 分开；运行它不会把动作改为可执行。它只接受当前已审计的 1.37.5 SHA-256，并校验进程路径以及加载模块或 minidump 模块的 PE 时间戳和 `SizeOfImage`。minidump 未包含完整镜像，不能计算转储中模块的完整哈希；报告明确记录这一限制。

```powershell
python work/probe_diplomacy_current.py --pid <当前PID> --output work/runtime/diplomacy-current-live.json
python work/probe_diplomacy_current.py --dump <minidump.dmp路径> --output work/runtime/diplomacy-current-dump.json
python -m unittest bridge.tests.test_diplomacy_current_probe -v
```

`--pid` 和 `--dump` 互斥；`--exe` 可覆盖 `local.env` 中的游戏路径，`--actor/--target` 默认 `FRA/ENG`。默认检查前 256 个国家槽；`--slots` 最高 4096，不推断整个国家数组的长度。只有对象完整 handle 与槽位一致，国家 TAG 合法，玩家完整 handle 匹配，才解释对应外交状态。外交官向量最多 256 项。每次显式读取最多 1 MiB，总显式读取预算 16 MiB，不扫描 heap、不暂停进程、不调用原生函数、不注入或写内存。

报告区分原始日期、外交官 `+0x18` 状态字节以及指定关系的冷却阈值；`state_zero_count` 表示静态空闲分支对应的零状态项数，不代表某外交行为一定合法。冷却只报告 `current_raw_date > threshold_raw` 比较，不把它当成全部前置条件。活进程报告会再次核对全局指针、玩家和日期，但仍明确 `atomic=false`。

2026-10-07 的一次暂停地图只读观察记录于 `work/runtime/diplomacy-current-live-71428.json`：玩家 `FRA`，slot 122；前 256 槽中 255 个国家身份一致；FRA 外交官 3 项状态为零；FRA→ENG 原始冷却阈值为 43808760，当前原始日期 56456976。显式内存读取请求合计 4623 字节，包含重复检查，不是进程占用内存或唯一读取字节数。PID、地址和日期只是该次观察，后续必须重新枚举并验证。

指定崩溃转储的结果记录于 `work/runtime/diplomacy-current-dump-20261007.json`：异常指令属于 `plugins/plugin64.dll +0x348a4`，不是外交 DLL 的指令；这只确定异常指令所属模块，不能据此断定崩溃根因。该 dump 捕获了数据库和游戏全局指针，但没有捕获国家数组、日期和玩家字段所在的 heap 页，因此报告 `partial_capture`，没有将缺页当成零值或已验证的外交状态。旧工具中的 offer 对象猜测没有移植到新探针。

探针的 10 项合成内存/minidump 测试覆盖身份不符、版本与模块签名不符、向量/槽位上限、缺页、异常归属和截断文件；这些测试及一次实时观察不等于任何外交动作的构造、投递、结算或保存重载验收。


## 可选 Contract/2：只生成请求草稿

显式 `/v2` 与 `--api-version 2` 提供全部 274 项的描述、结构校验和请求草稿。V1 的三个字段、原参数、SQLite 幂等和审计行为不变。V2 不使用 V1 submit、后端、数据库、进程或研究邮箱；它永远不会发送外交动作。

| 方法 | 路由 | 返回 |
| --- | --- | --- |
| GET | `/v2/actions` | 274 项目录和不可执行状态 |
| GET | `/v2/actions/{action_id}` | 参数、旧参数、15 类静态 binding 描述和未决项 |
| POST | `/v2/validate` | 规范 JSON、摘要和结构校验；不是游戏合法性 |
| POST | `/v2/requests` | HTTP 501，保留可用草稿正文、规范 parameters 和 unsupported 原因 |

V2 的请求有且只有四个字段：

```json
{"protocol":"EU4DIPLOMACY-CONTRACT/2","request_id":"maps-draft-1","action":"steal_maps","parameters":{"actor":"FRA","target":"ENG","region_index":0}}
```

仅两项参数迁移：`steal_maps.region_id` 字符串改为 `region_index` 整数 0…2147483647；`support_rebels.rebel_faction_id` 字符串改为 `faction_identity:{low:uint32,high:uint32}`。其余 272 项原参数保持不变。两词身份不是派系指针，也不证明对象存在或寿命。V1 继续接受两个旧参数，V2 不做隐式转换。描述中的 `legacy_parameters` 可直接查看旧形状。

```python
from bridge.diplomacy_api import DiplomacyAPI

v2 = DiplomacyAPI.contract(version=2)  # 不构造 V1，不打开 SQLite
description = v2.describe("subject.scutage")
draft = v2.request({
    "protocol": "EU4DIPLOMACY-CONTRACT/2", "request_id": "scutage-draft-1",
    "action": "subject.scutage", "parameters": {"actor": "FRA", "target": "NAV", "enabled": True}
})
assert draft["status"] == "unsupported" and draft["draft_only"] is True
assert draft["idempotency_scope"] == "not_reserved_contract_only"
```

```powershell
python tools/diplomacy.py --api-version 2 describe steal_maps
python tools/diplomacy.py --api-version 2 validate request-v2.json
python tools/diplomacy.py --api-version 2 request request-v2.json
python tools/serve_diplomacy.py --contract-only
python tools/diplomacy.py --api-version 2 --url http://127.0.0.1:8765 request request-v2.json
```

V2 CLI 仅支持 describe、validate、request，request 返回草稿并以退出码 2 表示不支持执行；不把 preview/submit/status/audit/reconcile 解释成 V2 别名。`--contract-only` 服务提供 V2/V3 草案路由，不建立 V1 数据库或探测 executable。默认旧服务仍可使用 V1，并同时提供草案路由；启动旧服务本身仍会初始化 V1 数据库。V2 没有 GET 请求状态或审计路由。

`request_id` 在 V2 **不预留**，同 ID 重复或不同内容只产生各自的 unsupported 草稿，不是持久幂等 ACK。`request_written=false`、`queued=false`、`native_called=false`，当前 `native_legality=null`、`native_binding_resolved=false`。desired-state 开关的 current/cancel 保持 null；不会假定 already_desired。不得用草稿摘要作为执行凭据。

V2 正文上限 16 KiB，保留严格 JSON 类型、重复键/未知字段拒绝、深度与节点预算；不接受 RVA、地址、backend、脚本、native state/value/envoy 或进程控制参数。静态证据逐文件有界校验，固定目录与 bindings 不从 HTTP 载入。目录与原生证据尚不完整时仍只提供结构信息，生产可执行动作保持 0。

## V3：十族受限静态参数来源

`DiplomacyAPI.contract(version=3)` 使用 `EU4DIPLOMACY-CONTRACT/3`，保留 V2 的 274 项目录与已有 typed 描述，并补充十族的受限静态参数来源。V1/V2 的协议、参数和请求处理保持原义。V3 仍无执行 adapter；每项 request 都返回 unsupported，HTTP 501、CLI 退出码 2，且不写数据库、不预留 request_id、不排队。

四项参数变化只在 V3 生效：sell_province 使用 `province_id` 和整数金币 `price_integer`（0..2147483）；enforce_peace 使用 `opposing_country` TAG，拒绝旧 war_id/defender；threaten_war 必须显式提供 `taker_country==actor`；trade_favors_for_trust 仅接受 actor/target，拒绝旧 favors 及任意 amount。V3 不舍入金币、静默丢旧字段或自动补 actor。所有十族要求双方 TAG 不同，opposing_country/third_country 也须在语法上不同于双方。

trust 的一原生步参数来源是 NDiplomacy 两个已加载 signed int32 define global，cost 以整数乘 1000，amount 保持整数 trust points；当前数值未知，不默填 10/5。reduce_relations_favor 继续接受 `third_country` TAG，未来必须通过已认证的 loaded country registry/private resolver 得到当前完整国家身份。本 API 没有实现这项 live 解析。静态来源闭合、文件哈希、global 观察或 extras 缓存都不证明运行权限、原生合法性或效果。

```json
{"protocol":"EU4DIPLOMACY-CONTRACT/3","request_id":"trust-draft-1","action":"trade_favors_for_trust","parameters":{"actor":"FRA","target":"ENG"}}
```

```powershell
python tools/diplomacy.py --api-version 3 describe trade_favors_for_trust
python tools/diplomacy.py --api-version 3 validate request-v3.json
python tools/diplomacy.py --api-version 3 request request-v3.json
python tools/serve_diplomacy.py --api-version 3
python tools/diplomacy.py --api-version 3 --url http://127.0.0.1:8765 request request-v3.json
```

V3 服务启动自动使用 contract-only，并限 loopback；不接受 executable、catalog、queue-db 或 remote binding 选项。路由为 GET `/v3/actions`、GET `/v3/actions/<action>`、POST `/v3/validate` 和 POST `/v3/requests`。沿用 16 KiB、严格 JSON 类型、重复/未知字段拒绝及 Host/Origin/Bearer 边界。V3 不提供 preview、submit、status、audit 或 reconcile 别名。十族公开 binding/symbolic 描述仅含公开 TAG/参数单位和静态来源名称；不暴露可执行地址、完整句柄或 native 控制输入。
