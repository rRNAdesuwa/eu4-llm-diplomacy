# EU4 1.37.5 双国外交邮箱协议与离线后端

本文定义下一版原生邮箱契约，以及已实现的 [Python 文件后端](../bridge/native_pair_backend.py)。文件后端仅经合成邮箱测试，未注册到 HTTP/CLI，未向游戏写入请求。当前执行白名单为空；v5 研究 DLL 没有本协议握手、可靠世代与邮箱消费者，不能据研究成功自动开放 API。已有 hook 的进程不得热替换 DLL。

后续 EU4LAB/1、EU4LAB/2 研究版本及 localhost `/research/vN` 服务是另一个协议，不能当成本草案 EU4PAIR/1 的已部署消费者。截至当前，v5–v10 有十四种经固定证据审核的历史状态效果；v11 在首个无发送阶段失败冻结，v12已有固定20/72/72无发送预检历史，仍无新增效果或生产就绪证明。它们均未注册生产后端，正式白名单和可执行动作数仍为 0。最新版本及保存/重载边界见 [研究能力说明](diplomacy-research-capabilities.md)，下面 v5 的原始验收记录保留其当时范围。

## 1. 当前证据与开放门槛

固定游戏 SHA-256：`9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A`。

2026-10-08 本地验收的 v5 DLL SHA-256 为 `03274A2E576F09D35B2FD0055B2EA234681F9C93C4AA227FC142B689D9CAC2F9`。PID 46972、线程 69052 完成五类动作生命周期、20 次原生合法性预览和 20 次 command 无发送生命周期。之后单独触发固定 FRA→ENG 改善关系研究：原生 submit 返回 true，container 被消费，exception=0；空前态变为双向关系 `1c81658`、envoy 0 状态 2、mission token `2ddb` 的完整关联图。随后另存并重载验收通过。证据见：

- [三阶段无发送日志快照](../work/runtime/native1375-v5/no-send-phases-46972.jsonl)
- [command 生命周期验收](../work/runtime/native1375-v5/command-verification-46972.json)
- [前后运行时效果](../work/runtime/pair-effects-comparison-v5-46972.json)
- [保存验收](../work/runtime/native1375-v5/saved-effect-verification-46972.json)
- [重载验收](../work/runtime/native1375-v5/reload-verification-45564.json)
- [基线存档证据](../work/runtime/diplomacy-baseline-save.json)
- [现有后端接口](../bridge/diplomacy_api.py)

保存文件 SHA 为 `7BFABE371E68AE502B806F9B80375FC8A4DAC638AD116D2506966FEF69633C5F`。此次重载产生新 PID 45564、新进程创建时间，完整 mission/envoy 图仍符合固定实验；该新进程没有 v5 hook。**一次重载走了进程重启，不证明所有加载路径都重启，也不建立同进程 world-generation 检测。** 报告明确 `generic_api_execution_verified=false`、`request_causality_verified=false`；这是固定隔离研究元组的保存/重载证据，不是任意并发 API 请求的归因证明。正式发送白名单仍为空，十个公开动作仍为 unsupported。

旧 v4 的 7 allowed / 13 rejected 只回答合法性，不能替代 AI 接受、实际投递或效果。v5 的真实发送和重载应按上面证据单独记录，不能继续描述为“从未真实发送”。

开放一个条目的顺序为：静态映射 → 动作生命周期 → 原生合法性 → command 的无发送生命周期/所有权验证 → 一个明确授权的真实发送实验 → 关联效果验证 → 保存和重载验证。证据必须区分这些层次。前一层成功不能自动生成后一层认证。

## 2. 十个公开动作与受限参数

客户端只提供现有 API 的三个字段：

```json
{"request_id":"pair-example-001","action":"improve_relations","parameters":{"actor":"FRA","target":"ENG"}}
```

本例只是结构示例，不能创建请求文件来试运行。`parameters` 只允许 `actor`、`target`；TAG 是三个 ASCII 大写字母或数字，且两者不同。request_id 沿用现有规则：1–64 个 ASCII 字母、数字、点、下划线或连字符，首字符为字母或数字。请求不接受指针、RVA、token ID、对象布局、原生 handle、日期、外交官编号、强制接受、跳过冷却或脚本文本。

| 公开 action_id | DLL 内部 family | 内部 value | 方向约束 |
| --- | --- | --- | --- |
| `offer_vassalization` | `vassalaction` | true | actor 发起收 target 为附庸的提议 |
| `cancel_vassalization` | `vassalaction` | false | actor 作为宗主取消对 target 的附庸关系；不能反转为附庸自行独立 |
| `royal_marriage` | `royal_marriage` | true | actor 发起联姻 |
| `break_marriage` | `royal_marriage` | false | actor 解除与 target 的联姻 |
| `improve_relations` | `improve_relation` | true | actor 派外交官改善与 target 的关系 |
| `stop_improving_relations` | `improve_relation` | false | actor 停止对应任务 |
| `guarantee` | `guaranteeaction` | true | actor 保障 target 独立 |
| `revoke_guarantee` | `guaranteeaction` | false | actor 撤销对 target 的保独 |
| `build_spy_network` | `spy_network` | true | actor 对 target 建立间谍网 |
| `stop_building_spy_network` | `spy_network` | false | actor 停止对应间谍任务 |

映射以 [动作目录](../bridge/diplomacy_catalog.json) 中当前 SHA 绑定的 `native_mapping.variants` 为静态来源。表中的 false 方向已有静态证据，但不代表取消动作已经真实执行过。正反模式分别认证，不能因为一个模式通过而开放另一模式。内部 family/value 由 DLL 固定映射，不从客户端传入。

首个实验只允许一个精确 `(action_id, actor, target)` 元组，并限制一个未完成请求。之后逐条扩展白名单，不能把 FRA→ENG 的证据推广为任意国家组合。白名单还绑定游戏 SHA、DLL SHA、协议版本、实验/验证清单 SHA、动作效果验证器版本、允许的世界状态前提。它由审核后的配置产生，不由日志中出现一次 `allowed=true` 自动产生。

## 3. 进程、世界与双向握手

已实现 `bridge/native_pair_backend.py`，后端名 `native_pair_1375_v1`。以下是正式启用条件；现有研究 DLL 没有这些生产握手功能。

适配器在 `capability()` 中只读检查以下条件，任一不满足返回 `ready=false` 和具体原因：

1. 磁盘游戏 SHA 与当前进程映像路径、PE 时间戳/SizeOfImage 匹配。PID 必须连同进程创建 FILETIME 核对，禁止仅按 PID 识别。
2. 已加载 DLL 的绝对路径、模块身份和磁盘 SHA 与实验 manifest 一致；source SHA、manifest SHA 与审核版本一致。DLL 自报 SHA 不能取代宿主对已加载模块的独立核对。
3. DLL 的 session 握手完整、帧心跳新鲜、主线程绑定未变、world_ready、paused、动作生命周期和 command 无发送检查均通过；独立只读 verifier 也必须明确核验 paused=true。
4. 此动作/方向/国家元组位于实际发送且效果/重载验收通过的白名单中。当前此清单为空。
5. 唯一持久账本与 session 中的 `store_id` 相符；没有未对账的未知发送、所有权故障或人工加载/重载事件。

握手采用两个独立 128-bit 随机数：DLL 每次成功初始化生成 `native_session_id`，宿主每次连接生成 `host_nonce`。不能使用 PID、时间戳或日志行号替代随机 session。握手响应回显两个值，并包含：

| 字段 | 含义 |
| --- | --- |
| `protocol` | 固定 `EU4PAIR/1` |
| `store_id` | 唯一持久账本建立时生成并保留的 UUID |
| `pid`, `process_creation_filetime` | 进程身份，FILETIME 使用 16 位十六进制文本 |
| `native_session_id`, `host_nonce` | 本次双向握手随机数，各 32 位小写十六进制 |
| `world_generation` | 已验证的加载事件产生的递增世代号，不能用 game 指针或日期替代 |
| `game_sha256`, `dll_sha256`, `experiment_sha256` | 版本与审核实验身份 |
| `window_thread`, `frame_sequence`, `uptime_ms` | 已绑定主线程、单调帧序号、`GetTickCount64` 时间 |
| `world_ready`, `thread_changed`, `send_enabled` | 严格布尔字段 |
| `lifecycle_passed`, `command_no_send_passed` | 当前 session 中通过的检查 |
| `world_generation_verified`, `single_player_verified` | 已独立验证的加载世代机制与单机会话识别 |
| `paused` | 经过生产语义核验的严格 true，不能采用研究 pause_candidate |
| `whitelist_sha256` | 双方采用同一精确执行白名单 |

宿主挑战文件和 DLL 响应须使用本 session 目录、固定文件名、排他创建及完整记录校验。响应只有在 host_nonce、native_session_id、进程创建时间、实验清单全部一致后才有效。同一 session 的 nonce、身份和原生事件链不可重置；宿主恢复必须读取持久 nonce，重新协商身份需要新 session 且不能迁移旧请求。心跳的 uptime 与宿主读取的 `GetTickCount64` 比较，默认 2 秒过期；每次 submit 和原生消费时都重新检查。UTC 时间用于审计，不能作为单调截止时间。只有 native 自己的 `heartbeat.record` 可以在身份不变、帧序号不回退的条件下原子更新；请求、claim、握手不得覆盖。

加载存档、退回菜单、重开游戏或世代无法确认时立即撤销握手。尚未消费的旧请求也不能转交新世界。**当前还没有经过验证的 world-generation/load 检测；game 指针、玩家 handle 和日期相同不能排除重载。完成该检测前，正式 `ExecutionBackend` 必须保持不就绪。** 下一次单次受控发送实验可以单独验证这项前提，但不能通过用户填写一个 world_id 将其当作运行时证明。

邮箱位于固定的本地 NTFS 目录，仅当前 Windows 用户和必要系统主体可访问；不接受请求指定的目录、网络路径或 reparse point。哈希用于完整性校验，随机数用于关联 session，两者都不能防御已控制同一用户身份的进程。此协议是本地实验边界，不是对同用户恶意软件的认证边界。

## 4. 邮箱布局和确定性编码

建议固定根目录为 `work/runtime/pair-adapter/`，在目录中保存一个长期账本和每次启动独立目录：

```text
pair-adapter/
  ledger.sqlite3                 # 永久请求 ID 与事件账本，禁止按进程清空
  store.json                     # store_id 与账本身份
  experiment.json                # 由宿主参数固定 SHA 的审核证据清单
  whitelist.json                 # 固定 SHA 的精确动作/方向/国家白名单
  sessions/<native_session_id>/
    handshake.request
    handshake.response
    heartbeat.record
    inbox/<sequence>.request
    claimed/<sequence>.request
    native-events.jsonl
    effects/<sequence>.json      # 固定路径；必须经过独立效果验证器
```

文件名由适配器分配的十进制 `sequence` 生成，不把 request_id 拼成路径。单 session 的 sequence 严格递增；最多一个未完成请求。握手与请求最大 4096 字节；单事件最大 16384 字节；完整事件链上限 2 MiB、4096 条；manifest 和单效果报告上限 65536 字节。达到边界需有计划地终结 session，不能截断旧链继续发送。ASCII 请求不允许 BOM、CR、NUL、重复字段、额外字段、超长十进制值或前导加号。尾部必须恰好一个 LF。整数范围为 1..2^63-1，PID/window_thread 额外限制 uint32。

为避免在 DLL 内引入完整 JSON 接口，请求使用以下**固定顺序** ASCII 行编码。尖括号是文档占位符，不是可提交值：

```text
EU4PAIR/1
operation=submit
store_id=<uuid>
native_session_id=<32-hex>
host_nonce=<32-hex>
pid=<uint32>
process_creation_filetime=<16-hex>
world_generation=<uint64>
game_sha256=<64-lower-hex>
dll_sha256=<64-lower-hex>
sequence=<uint64>
request_id=<public-request-id>
request_sha256=<64-lower-hex>
action=<one-of-ten-action-ids>
actor=<TAG>
target=<TAG>
deadline_uptime_ms=<uint64>
experiment_sha256=<64-lower-hex>
whitelist_sha256=<64-lower-hex>
record_sha256=<64-lower-hex>
```

`request_sha256` 使用现有 API 的 `canonical(request)` UTF-8 字节 SHA-256。因为此协议的三个请求字段只接受 ASCII，原生端可按固定键序构造相同字节：`{"action":"…","parameters":{"actor":"…","target":"…"},"request_id":"…"}`。`record_sha256` 覆盖从 `EU4PAIR/1\n` 到 `whitelist_sha256=…\n` 的原始字节，不含自身一行。请求截止时间默认发布后 5 秒；过期只能拒绝，不能延长后再次发送同一请求。

发布过程为：在同目录排他创建临时文件 → 完整写入 → flush 并核对成功 → 同卷原子重命名为最终名且**禁止覆盖**。消费者只看最终名，不读临时文件。遇到已有最终名，必须核对 ledger 和全文哈希，不能替换。原子重命名不构成“游戏恰好执行一次”的保证；断电/磁盘故障造成的账本、文件不一致一律进入对账状态，不推测安全重发。

DLL 在正常帧上最多消费一个请求，执行前重新检查所有版本/session/world/主线程/有效期/白名单/TAG 条件。TAG 到 country 的解析完全在 DLL 内完成，使用有界国家数组，核对完整 handle、slot 和低三字节 TAG；命令执行前再次核对身份。仅核对语法不代表国家存在。

DLL 先将请求移到 `claimed/`，再持久记录 `claimed`；在任何可能向游戏交付的调用前，写入并确认 durable `dispatch_intent` 事件。写入或 flush 失败则不得进入该调用。日志/文件 I/O 必须位于普通回调阶段，不能位于暂停其他线程的 patch 阶段。磁盘 I/O 的耗时没有硬实时保证，不允许在游戏线程等待宿主 ack、重试 I/O 或循环轮询到成功。

原生事件使用 UTF-8 单行 JSON，仅允许第 9 节固定字段和事件专属 `data` 对象；重复键/非有限数/不完整行均拒绝。每条包含 `protocol`、完整 store/process/session/world/manifest 身份、`sequence`、`request_id`、`request_sha256`、动作/TAG、单调 `event_sequence`、`uptime_ms`、UTC 时间、`event`、`data`、`previous_event_sha256`、`event_sha256`。哈希针对去掉 `event_sha256` 后按现有 canonical 规则编码的对象。没有客户端指定的文件路径；私有诊断也不能变成可重新提交的 handle。

事件按 `received → claimed → legality_result → dispatch_intent → dispatch_returned → effect_observed` 发展；可以在交付前产生 `rejected_before_dispatch`，在交付后产生明确的 `ai_rejected`，在已收到请求后的故障点产生 `session_fault`。`dispatch_intent` 只表示跨越调用边界的意图，不能声称原生调用已完成。`allowed=false` 或未知预调用所有权后不得产生 dispatch_intent。旧 v4/v5 研究事件缺少这些绑定字段，不能伪装为本协议 ack。

## 5. 持久幂等与异常所有权

“全局 request_id”指同一适配安装的唯一持久账本，跨 DLL、PID、session、存档世代仍不重复。不宣称覆盖另一台机器或人为替换整套账本后的世界。实现采用实例 RLock、SQLite BEGIN IMMEDIATE 与数据库唯一键串行化多个宿主的保留意图；不把单进程锁当成跨进程保证。此后端账本采用 DELETE journal / synchronous=EXTRA，避免只读 status 创建 WAL 共享文件；API 自己的 WAL 账本保持原样。`store_id` 缺失、更换或账本损坏时不允许静默建立新账本继续发送。不能仅凭文件内的 store_id 检测人为回滚的整套旧快照，部署不得自动回滚或重建账本。

API 的现有 `requests.request_id PRIMARY KEY` 和 payload digest 已能拒绝不同内容重复 ID。它还会永久保留 `unsupported` 的 ID；动作将来开放后也不能把同一 ID 重新发送。适配器再记录 session/sequence/请求原文/哈希/发布阶段/原生事件链，不建立一个与 API 无关联的“每次启动清空”缓存。

| 故障窗口 | 恢复行为 |
| --- | --- |
| API 只写了 `dispatching`，宿主未获得可验证回执 | 只读对账；不能再次调用 backend.submit |
| 请求文件发布后，宿主尚未保存 queued receipt | 通过持久 request_id/digest/session 对账原文件和事件；不能再发布另一份 |
| DLL claimed 后尚未有 dispatch_intent | 保持不重发；只有已证实未越过边界的显式拒绝事件才能终结为 rejected |
| durable dispatch_intent 后，进程退出、超时、SEH 或返回结果丢失 | `dispatch_unknown`，禁止自动重试或改 ID 绕过 |
| 原生调用正常返回，但尚无关联效果 | dispatched/pending，返回不是 applied |
| 后续载入另一存档或新进程 | 旧请求仅能对账，不迁移到新 session 重新执行 |

DLL 对同 session 的 request_id/sequence/哈希再次出现时只重放已有结果，不重入构造或交付。重复 ID 但不同内容是冲突，session 进入拒绝状态。宿主重启后需读取完整的 bounded、连续事件链；若链存在空洞、截断、重复序号或身份不符，冻结发送。

不能承诺跨游戏进程和文件系统的原子 exactly-once。可实现的目标是“已持久认领的请求最多尝试一次，未知结果不重发”。宁可丢失一次执行机会，也不能用重试猜测之前未发生。

动作对象、command 对象及 clone 的所有权必须有单独验证过的交接表。每个原生调用前后分别记录 `caller_owned / engine_owned / ownership_unknown`，其中 `engine_owned` 必须来自已验证的具体交接语义，不能只看返回 bool。若 SEH、无效对象、异常返回或无法确定是否转移所有权：停止后续原生调用，禁用该 session；不重复析构、不尝试换一个指针、不重新 clone、不自动发送。Python 不能通过“清理临时文件”解除这个状态。

## 6. API 状态与可证明的效果

| 对外状态 | 必须具备的证据 | 明确不代表什么 |
| --- | --- | --- |
| `unsupported` | 版本、白名单、握手或实现门槛未满足 | 不代表游戏规则拒绝 |
| `queued` | 持久 ledger 记录及同 session 的完整邮箱发布凭据 | 不代表 DLL 已消费 |
| `dispatched` | 相同请求的原生交付调用已确认完成，具有验证过的返回/交接语义 | 不代表 AI 接受或效果发生 |
| `applied` | 独立效果验证器确认目标状态变化，并关联本请求 | 不代表任务已积累全部关系值/间谍网，也不自动代表已保存重载 |
| `rejected` | 明确的消费前拒绝，或已验证并关联的原生/AI 拒绝事件 | 不能用超时或效果暂未出现代替 |
| `failed` | 已知终结故障且能够排除未知交付/未知所有权 | 不是未知情况的兜底 |
| `dispatch_unknown` | 已可能越过交付边界而不能确定结果，或所有权未知 | 禁止重发；人工重新建 ID 也不能消除风险 |

合法性结果单独使用 `native_legality_checked`、`allowed`、`checked_frame`、`checked_world_generation`；AI 接受使用 `ai_acceptance_observed`；保存重载使用 `reload_verified`。这些字段不能互相替代。预览通过后游戏状态还可能变化，所以正式交付前必须重新检查，不能把预览当成预约。

效果验证器需要逐动作实现：

| 动作组 | 需要观察的目标变化 |
| --- | --- |
| 接受附庸 / 取消附庸 | 指定方向的 dependency/subject_type 与国家 subject 信息从已记录前态变为目标状态；其他宗主/其他属国不计入 |
| 联姻 / 解除联姻 | 指定双方的 royal_marriage 关系建立或移除；发出提议本身不计成功 |
| 保独 / 撤销保独 | first=actor、second=target 的 guarantee 建立或移除，方向相反不计入 |
| 改善关系开始 / 停止 | 明确映射至该 target 的外交官任务建立/终止；关系数值增长或外交官 state=0 单独不够 |
| 间谍网开始 / 停止 | 明确映射至该 target 的间谍任务建立/终止；已有网络值或外交官数量单独不够 |

基线证明 `diplomats/envoy` 中有 name/type/id。v5 固定改善实验进一步实测了全局 `improve_relation={first=FRA second=ENG ... envoy=0}` 和同外交官新增序列化 `action=2`，运行时通过完整关系/mission/envoy 图核验，随后重载通过。`type=3` 本身不是改善任务标记；`action=2` 也不能据单次实验泛化为所有动作枚举。其余动作的任务/关系映射仍需相应证据。

验证器保留前后 SHA、process/session/world、请求 digest、帧/日期、目标字段和原生关联事件。只看到存档里已有关系，或看到另一个玩家/AI 同时造成的变化，不能自动标 applied。无法可靠关联时保持 dispatched，并报告 `effect_observed_uncorrelated`。单次隔离实验可以记录受控条件作为研究证据，不能直接推广为任意并发游戏中的因果证明。

## 7. 与现有 ExecutionBackend 的接入及必须补齐的接口

当前接口为 `capability(action, build, parameters)`、`submit(request, build)`、`status(request, receipt)`，已有 API 会在目录标记和构建支持均通过后才查询 backend。接入时保持这两层检查：目录按动作提供已审核执行支持，backend 再检查具体 session、国家组合和实时前提。不得为了试接线把所有条目改成 `runtime_verified`。

建议的未来方法职责：

- `capability()`：只读核对上述身份、白名单、账本锁与心跳。没有具体 parameters 时仅报告动作是否存在至少一个合格元组，并附精确约束；不能声称任意国家可用。
- `submit()`：重新核对同一证据，事务性保留发布序号和意图，再发布一个请求；返回 `queued`、稳定 `external_id=store_id/native_session_id/sequence` 及真实发布凭据。不能从研究日志合成 receipt。
- `status()`：只读核对原生事件链和独立效果报告。它不能负责重新创建请求、延长期限、重新握手后补发或自动修理未知所有权。

以下两个恢复缺口已经作为纯离线基础设施补齐；本次文件后端复用这些接口，仍不改变当前所有动作的 unsupported 状态：

1. `status()` 接受严格绑定证据的 `dispatch_unknown`：`reason_code=native_dispatch_unknown`、`automatic_retry=false`、明确区分 `dispatch_outcome_unknown` 和 `ownership_unknown`。它在 SQLite `execution_holds` 中持久冻结此 backend，后续换 request_id 也会被拒绝。缺失或矛盾的证据只产生 observation_error，不改变已知状态。
2. 显式 `DiplomacyAPI.reconcile(request_id)` 调用可选 `ReconciliationBackend.reconcile(request, prior_record)`，只恢复已有 dispatching/queued/dispatched/dispatch_unknown。HTTP 为 `POST /v1/requests/{id}/reconcile`，只接受 `{}`；CLI 为 `python tools/diplomacy.py reconcile <id>`。不接受客户端提供原生证据，不调用 submit，也不创建未知请求。终态不改变。对账失败记录 `reconciliation_refused`。

支持恢复的 adapter 必须在 `capability()` 返回 `dispatch_identity`，字段恰好为 `store_id, session_id, pid, process_creation_filetime, world_generation, game_sha256, dll_sha256, experiment_sha256, whitelist_sha256`。API 在任何 submit 调用之前持久保存这份身份与原始 build/request SHA，并建立 dispatching hold。此内部字段的 `session_id` 对应线上 `native_session_id`，四个构建/配置 SHA 使用大写规范文本。旧记录若缺少预投递身份，不能拿今天的进程或目录补造它来完成对账。

receipt、native status observation、reconcile observation 均须带 `binding`：上述九个身份字段，加 `request_id, request_sha256, backend, external_id, sequence`，不接受额外字段。请求 SHA 沿用现有 API 的小写 digest。binding 必须与原始身份、原始 receipt 完全一致。恢复证据为非空对象数组，每项至少含 `kind, reference, sha256`；真实文件/原生日志真实性由可信 adapter 验证，API 检查字段和哈希格式不能代替原生证明。

非 unknown 的恢复还必须有 `dispatch_outcome_known=true`、`ownership_known=true`；applied 额外要求 `game_effects_verified=true`。在缺少原始 receipt 的 dispatching/unknown 恢复到 queued/dispatched/applied 时，必须返回具有同一 binding 的原始发布 receipt。unknown/dispatched 不能退回 queued；已有 receipt 不可替换。API 使用预期旧状态的条件更新，拒绝用滞后恢复覆盖并发终态。只有显式可信恢复才解除未知发送 hold；如果还有其他未知请求，backend 继续冻结。

现有 `POST /v1/preview` 始终是 `contract_only`，而 ExecutionBackend 没有 native-preview 方法。不要暗中让该端点开始调用原生代码。未来可增加明确标识的研究 CLI/独立原生 preview 操作，使用同样的 session 绑定、有限任务预算和单独审计；其 `allowed` 不能更新执行白名单。inbox 本版只接受 `operation=submit`；握手/心跳各有固定文件与 operation，不能将它们放进 inbox 触发原生行为。

文件后端现已实现 capability、submit、只读 status/reconcile；测试仅在 TEMP 的独立私有目录建立合成文件，不连接游戏。构造函数不执行 I/O；只有显式 `initialize_mailbox(new_path)` 会建立新账本，已有目录一律拒绝。正式 HTTP/CLI 没有 import/注册该后端，默认白名单为空。新的可信只读 live_identity_probe 和逐动作 effect_verifier 尚未接入；缺少其中任一项不可能 ready。不得把合成测试中的回调或 manifest 用于实际部署。

## 8. 下一版实现的验收用例

先使用不接触游戏的 fake transport 测试协议与持久性，再在独立测试档中逐级实验。fake transport 必须标记为测试，不能输出游戏执行成功证据。

- 严格编码：截断、重复字段/键、未知动作、跨行 ID、pointer/RVA 参数、错误哈希、超长文件均拒绝，已有文件不覆盖。
- 身份：PID 重用、进程创建时间不同、旧 session/host_nonce、DLL/实验/白名单 hash 不符、过期心跳、加载世代变化均禁止消费。
- 幂等：两个 API 进程并发提交同 ID；同 ID 不同参数；发布后宿主崩溃；claim 后 DLL 退出；dispatch_intent 后无返回。每个场景均证明不会第二次交付。
- 账本：保留 unsupported 和未知请求跨重启；账本被删除、换路径、回滚或 store_id 不匹配时不自动重建并开放。
- 状态：queued 不等于消费，返回不等于 applied；合法性允许而 AI 拒绝、超时无结论、效果存在但不可关联、重载另一个世界分别验证。
- 所有权：在构造、clone、交接、返回和析构各阶段注入测试故障，确认只执行已证明安全的清理，未知时停止 session 且不重发。
- 真实实验：先 command 无发送自检，再只启用一个明确授权元组；保存基线、发布一次、核对关联原生事件和目标效果、另存并重载确认，最后才讨论该元组的执行认证。

通过这些条件后仍须为其他九个 ID 分别获取证据。当前 7 个合法性允许结果不会直接进入执行白名单。

## 9. 可实现的精确契约

实现中的 `WIRE_FIELDS`、`EVENT_KEYS`、`EVENT_DATA` 是机器字段清单，测试见 [test_native_pair_backend.py](../bridge/tests/test_native_pair_backend.py)。仅 host 配置与可信代码可以提供审核清单和验证回调；HTTP 请求不能填这些字段，也不能仅凭 JSON 中的 true 获得能力。

握手使用与 submit 相同的 `EU4PAIR/1\noperation=…\n` 首两行和末尾 `record_sha256`。中间字段顺序如下，所有 SHA、nonce、FILETIME 使用小写十六进制；UUID 使用标准小写连字符文本：

```text
BASE = store_id,native_session_id,host_nonce,pid,process_creation_filetime,
       world_generation,game_sha256,dll_sha256
MANIFEST = experiment_sha256,whitelist_sha256
HEALTH = window_thread,frame_sequence,uptime_ms,world_ready,thread_changed,
         send_enabled,lifecycle_passed,command_no_send_passed,
         world_generation_verified,single_player_verified,paused
handshake_request  = BASE + MANIFEST + challenge_uptime_ms
handshake_response = BASE + MANIFEST + HEALTH
heartbeat          = BASE + MANIFEST + HEALTH
```

这是字段清单表示法，不是线上逗号编码；线上仍是每行一个 `key=value`。布尔只允许 `true`、`false`。所有 HEALTH 布尔必须为 true，唯 `thread_changed` 必须 false。challenge ≤ response ≤ heartbeat uptime、frame 序号不回退且窗口线程一致。capability 同时调用宿主安装的独立 `live_identity_probe()`，返回 PID、创建 FILETIME、world_generation、window_thread、两个大写游戏/DLL SHA、observed_uptime_ms，以及 process_identity_verified、loaded_dll_identity_verified、world_generation_verified、single_player_verified、paused 五个严格 true；数据必须不超过 2 秒。该回调必须实际核验映像/已加载模块、世代、模式与暂停，不能把 heartbeat 原样回抄。

`paused` 是未部署的 EU4PAIR/1 草案新增必填字段，缺失、false、数字 1 或字符串 `"true"` 都不能开放投递。此更改不兼容更早的合成握手格式，也不意味着任何正在运行的研究 DLL 已兼容该生产协议。研究工具的 pause candidate 不是生产证明。Python 在投递前重复核对暂停仅缩短检查窗口；原生 consumer 在认领、构造、执行合法性检查和紧邻原生提交前仍必须在绑定主线程重新读取经验证的暂停语义。无法证明时在 dispatch_intent 前拒绝，不能靠两秒内的心跳推断执行时暂停。只读 status/reconcile 可在后来解除暂停后继续审查既有历史。

`experiment.json`、`whitelist.json` 使用 UTF-8 严格 JSON、exact keys，宿主初始化参数必须固定各文件原始字节 SHA。清单 schema 为：

```text
experiment = {schema_version:1, protocol:"EU4PAIR/1",
  purpose:"native_pair_mailbox_verified", game_sha256:<UPPER64>, dll_sha256:<UPPER64>,
  world_generation_method:"native_load_counter_v1", world_generation_verified:true,
  actions:[{action,actor,target,verifier_id,evidence_sha256:<lower64>,
            dispatch_verified:true,effects_verified:true,reload_verified:true}]}
whitelist = {schema_version:1, protocol:"EU4PAIR/1", game_sha256:<UPPER64>,
  dll_sha256:<UPPER64>, experiment_sha256:<lower64>,
  entries:[{action,actor,target,verifier_id,evidence_sha256:<lower64>}]}
```

数组各最多 64 条，动作/方向/国家不得重复，每条 whitelist 必须精确对应 experiment 中相同证据和 verifier_id。旧 v5 manifest 用途不同，不能兼容成正式清单。`native_load_counter_v1` 是未来经过验证的机制标识，不代表该机制已经实现；[世代/单机静态研究](native-world-lifecycle-1375.md) 仍有加载路径覆盖和模式证明缺口。

原生 JSONL 每条 exact keys 为 `BASE + MANIFEST + sequence,request_id,request_sha256,action,actor,target,protocol,event_sequence,uptime_ms,utc,event,data,previous_event_sha256,event_sha256`。BASE 和 MANIFEST 必须与原始请求逐字段相同；每个 event 都必须对应持久 host intent，不接受没有 ledger 记录的其他命令。event_sequence 从 1 连续递增，previous_event_sha256 首条为 64 个零，之后接上一条 hash。UTC 格式为 `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`。hash 使用 JSON 按键字典序、无空格、UTF-8 编码、去掉 event_sha256 的字节；data 内也排序。所有固定字符串均可用无转义 ASCII 生成，不能把日志自由文本放入该记录。

| event | data 精确字段 | 状态含义 |
| --- | --- | --- |
| received | `{}` | 接收，不证明交付 |
| claimed | `{}` | 已独占认领；缺少后续事件不重发 |
| legality_result | `allowed:bool` | 原生合法性；不是 AI 接受 |
| dispatch_intent | `ownership_known:true` | 已持久记录调用意图；结果未知 |
| dispatch_returned | `returned:bool,container_consumed:bool,exception:uint32,ownership_known:bool` | 只有 true/true/0/true 才为 dispatched；其他均 ownership_unknown |
| rejected_before_dispatch | `reason_code,dispatch_excluded:bool,ownership_known:bool` | 后两者 true 才能 rejected |
| ai_rejected | `reason_code,rejection_verified:bool,ownership_known:bool` | 在 dispatch_returned 后，后两者 true 才能 rejected |
| session_fault | `reason_code,dispatch_may_have_occurred:bool,ownership_known:bool` | 交付前且 false/true 可 failed；跨过 intent 后一律 unknown；所有 session_fault 禁止继续发送 |
| effect_observed | `effect_report_sha256:<lower64>` | 仅读固定 effects/sequence.json，独立 verifier 成功才 applied |

reason_code 使用 request_id 的 ASCII 语法，不能嵌入路径或自由消息。未知字段、错误顺序、不同身份、截断、重复、超限或无 ledger 意图，均停止解释为成功。原生还须在可能跨界的调用前 flush dispatch_intent；如果实际返回后来无法可靠持久记录，不能补造 completed 事件。

效果验证回调签名为 `effect_verifier(request, binding, report_bytes)`，返回相同 binding、严格 `game_effects_verified=true`、与该请求审核清单一致的 verifier_id。绑定与报告哈希只是必要条件；回调必须核验受控前后状态与请求归因。文件后端不会仅凭 native 的 effect_observed 自报将请求升级为 applied。

37 项离线测试通过：真实临时文件/SQLite/原子重命名/NTFS ACL、并发与崩溃窗口、持久 hold、只读对账、身份和暂停证据拒绝。运行 `python -B -m unittest bridge.tests.test_native_pair_backend -v` 可复验。它们是传输测试，不能写成原生行为通过。完整生产缺口及限定绑定设计见 [生产接入准备审查](native-pair-production-readiness-1375.md)。
