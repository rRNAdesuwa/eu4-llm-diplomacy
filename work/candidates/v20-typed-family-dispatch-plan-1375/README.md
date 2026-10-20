# V20 有类型的分族调度方案（仅设计）

本候选把已有证据整理成私有 ABI registry 和下一步实现合同。没有 C++ profile、sender、DLL、hook、loader、publisher 或公共 backend 实现；没有读取游戏进程、调用引擎、重新解码、编译或修改旧版本。`native_ready / production_ready / runtime_verified` 均为 false。旧实验的 selected-state correlation 不升级为请求因果、自然 AI 接受、严格单人或世界代次证明。

输入是 38 个精确文件快照，共约 20.3 MB。单件实际读取上限 4 MiB、累计 32 MiB，顺序读取；不扫描旧大反汇编，也不运行旧报告生成器或导入正式 API。`input-pins.json` 中正式 API 文件仅用于本次差异审计，**不能成为新 runtime 永久依赖的可变正式模块**。未来 profile 应固化最小版本化定义和原生 pins。

## 覆盖数字及 37 个绑定的实际含义

当前目录 274 项，270 项有至少一种静态映射。`V12_ACTIONS` 的 36 个研究协议 ID 对应 20 个原生 family；`V12_CATALOG_BINDINGS` 映射到 37 个 catalog ID。两处名称关系必须显式保留：

* `request_trade_power` → catalog `transfer_trade_power`，不是额外 family。
* 一个 `cancel_independence_support` → `cancel_offered_independence_support` 与 `cancel_requested_independence_support`。这是描述层的两个角色绑定，不是两次独立运行验收；禁止把 37 写成 37 个已可调用方向。

正式 V2 typed enrichment 是另外的 15 项；已封 `TenFamiliesDraft/2` 是另外的 10 项。它们与 36 项研究表有重叠，不能求和当成已执行动作。独立 `break_alliance_favor` 又有自己的三国静态合同。`plan.json` 给出精确 36→37 映射，以及剩余 237 个没有这套 laboratory binding 的 catalog ID；这些并不因有字符串/虚表映射就获得新调用链。

## 可以复用什么

V19 可复用的是**受所有权约束的控制流程**：固定工厂与默认字段核验 → 仅初始化本方新建原件 → 本族完整 `+88(action,NULL,false)` → `4e9930(action,&empty_slot)` 生成独立 clone / `0x58` command → command `+40=4e8630` → 正常析构独立原件 → 永久 intent → 重新核完整根/身份/command → 紧邻调用的最后 guard → `14ca210(context,command**)`。原件、clone、command 是三个不同对象，不能 memcmp padding 或重复包装继承旧 cleanup 状态。

一旦进入 `14ca210`，本方永久放弃 command/clone 权属；正常 AL true 且容器为 NULL 仅是 dispatched。false、SEH、缺返回、非空容器、日志/guard 异常必须保存当前项并冻结，不读已交出的对象、不猜析构、不补发、不 drain queue。正常返回的已知清理可以越 TTL，新的工作不可以。正常返回不是接受回复，更不是效果证明。

该 sender 的 context/readiness、transport ABI 已有有限静态 pins；**不是每一种 command 都已验证能经这个发送器运行**。`14ca2d0(context,command*)` 是另一个 ABI，不能换名字当成相同容器交付。server/context 相等、暂停或两遍一致也不建立严格 SP / epoch / engine lifetime lock。

V19 当前实现固定 FRA→ENG、五 family、同一锁定日期。泛化目标、跨日批次及更多 family 需要新版本的 Host/profile 合同，不能仅替换数组或让客户端给 `ready=true`。继续复用已审实际 preflight receipt 机制：每族工厂/clone/default/析构、完整预览、owned-command gate 的真实记录和以后独立 owner health；mock 或旧版本日志不能代替新 DLL/同会话的履历。

## 原生 family 的具体边界

`abi-registry.json/research_families` 是精简 20 family 表：每项保存固定 token、size、vtable、clone、destructor、setter、local/full 槽、协议正反模式以及例外。来自冻结 v17 C++ 表与已封静态 inventory 的逐项对账，不是允许外部任意 token 的 dispatcher。

| 分组 | 可建立的新私有 profile | 必须保留的例外与下一缺口 |
|---|---|---|
| 附庸、改善、保独、间谍网 | 已有 `0x40` owned-action 实现可移植到新 profile；正反 ID 分开 | 取消附庸只允许当前 vassal/client_vassal，不覆盖 appanage/union；保独核正确方向；改善撤销保持 envoy=-1；间谍撤销必须即时解析唯一 mission/task/entry 的 int32 envoy 并再核，不能公开传 envoy |
| 联姻 | 单独 `0x68` profile | EngineString32 `+40` 和 force byte `+60`；原件预览后可有 bounded 文本，clone 重建空串且 force=false；专用析构，不能套 `0x40` 或复制/释放字符串 |
| 同盟、军事/舰队通行、禁运 | 已有固定 pair 实现及方向观察来源 | ask 的 actor 为权利持有者，offer 的 actor 为授予者；cancel 与 revoke 使用不同索引方向；dispatch 不产生可撤销关系的保证；无现存匹配对象不能造取消成功 |
| 补贴、贸易权、礼物、普通侮辱 | 新 profile 先保持旧固定值 | 补贴 `1000 milli/月, 10 年`，贸易 `500 milli/flag0`，礼物 `25000 milli`，侮辱 index=-1；开放金额/期限/特殊侮辱需要另版 schema、单位与范围，不可直接复用用户任意整数 |
| 包围网、支持独立、警告、导向贸易 | 已有特殊 state/graph 检查可移植 | 包围网初始化 state=2 有正常 AI 专门证据，其他 family 不能跟随；支持独立必须是第三方宗主的有效属国，FRA 自己的 NAV 不能满足；警告没有此版 undo；贸易取消需唯一方向 |
| 五间谍 | 直接参考 V19 精确五 profile 与各族正常 caller | 正向 true/state0/envoy=-1；完整 `+88` 必须保留能力/费用/脚本检查，false 不是撤销；不把单次 mock 或 no-send 验证解释成外部发送服务 |
| 拉拢人情正反 | 可新建 `0x40 / 0x3acc` profile | 已有完整预览/clone/析构证据；两模式 envoy=-1，stop 需要当前 outgoing relation/mission 图；不因为 GUI visibility 未解释就伪造 DLC 许可 |
| 军役 + 三属国开关 | **独立 already-command profile**，不是 pair profile | 军役 `0x60`，开关 `0xa0 + borrowed singleton`；`+60` clone 需要被 callee 消耗的临时 EngineString32，不能 NULL/一参数；新 authority reader、constructor/clone/command gate/析构预检及交付链分别审查 |

特别是旧 v17 `execute()` 实际调用 `kPreview=4e9d00`，**没有逐 family 调用完整 `+88`**。表中的 full 槽是已封静态映射；除另有正常 caller 补证的 family，不能称完整正常调用参数/作用域已闭合。优先检查已有 inventory/caller 报告，缺者仅补具体 caller slice，而不是重扫全程序。新 profile 在生命周期后单列完整预览阶段，允许合法 false 并正常清理；该阶段可能有 TLS/lazy cache/脚本副作用，不叫只读。

军役选择 public enum `no_focus/aggressive/supportive/passive/defensive/siege`；私有值是 0..5，0 不是取消。其 gate 不核宗主授权；还要核双向 dependency、完整 current player、definition 的 `uses_military_focus` 与 `can_set_mil_focus`、当前 enum entitlement。三个开关用 `enabled` 严格 bool 表示期望状态；当前已等于期望时 `already_desired` 无原生调用，不能制造 flip。构造时的 cancel 字节是当前状态快照，前置状态变化后拒绝，不重新构造重试。单例只借用，不得析构；三个效果也可能有额外关系或 modifier 副作用。

## 参数族的最小新增工作

`abi-registry.json/supplemental_groups` 保存 10 项草案的原始公开 schema、具体私有 extras 与其静态证据指针，再加八个补充分组。所有 native 描述只属 registry，不接受进公共请求。

* **可实施受限 owned profile 的静态基础较齐**：curry、人情换金币/人力/水手/备战、claim_throne；各自正常 full+88 与 owned queue 已闭合。人情族正常 AI 只写 source primary date，secondary 仍可为工厂值；clone 两日期取 primary，wrapper 再写当前 secondary，不能为方便套 V19 原件两日期相等的检查。
* **需要 resolver，不再需要泛泛找参数**：sell_province 使用整数金币 `price_integer` 和省份 ID；enforce_peace 是 `opposing_country` 的完整句柄而非 war ID；reduce 是 `third_country`，新 GUI 已补齐选中 full handle→action+40→owned wrapper→14ca210；trust 从认证进程内 `233db7c/233db80` 两 signed DWORD 取一步默认，cost×1000、amount 为整数，不能写死10/5。未来 TAG/province resolver 仍未实现运行认证。
* **仍需具体 caller/选择或 lifetime 闭合**：threaten_war 的正常发送分支仅明确 local+80，没有证明调用 full+88；受让国限 actor，+44 是未对齐 QWORD。`break_alliance_favor` 已有三国普通 AI/full+88/queue，但大工厂 token 分派需单独固定；它不同于普通断盟。steal_maps 要有界 loaded region membership/type/name；support_rebels 要完整 target faction 双 DWORD 身份→唯一 borrowed pointer 与跨消费存活，并补 selected owning caller，false 暂不支持；stock steal_modern_ideas 是具体俄罗斯 modernization 脚本，不是通用偷科技，lazy definition registry 不能当 RO resolver。
* **省份/战争另组**：enforce/threaten 拒绝可能引发参战/宣战；full/local 预览本身会构造 CB/临时对象。不能和普通和平批次混跑，也不能把 rejected 当作无变化。省份所有者、战争图、三国关系与回复观察都需单独有限 profile。

Formal V2 当前的 sell price、enforce war_id/defender、threaten 缺 taker、trust favors 与 TenFamiliesDraft/2 有四项明确 schema 差异，见已封 `formal-api-diff.json`。新接口应选择新版本，不静默丢字段、补 actor、四舍五入或将 war_id 猜为国家。

## 从 37 个绑定到外部研究请求

最小路径不是再写 37 个假 endpoint。先保留正式 V2 describe/validate/request 的 unsupported 行为，在独立研究版本实现下面几个可审件：

1. 版本化私有 profile registry（固定 20 families/36 modes）及严格公共 schema。公共层只有 request_id、动作名、TAG、受限整数/enum；拒绝 ptr/RVA/token/state/envoy/force、任意 string sink 和客户端证明字段。
2. 有界私有 TAG→当前完整 generation handle resolver：读精确 DB 数组/count、country+20、current/effective player，唯一匹配且前后根/date/身份重核。在 owner 调用前重新绑定，不把进程启动时的 handle 缓存当永恒身份。省份、region、faction、singleton 仅按各族独立合同加入。
3. 新 Host 的真实逐族 preflight 与后来 health、取消关系/即时 envoy/权限和完整 +88 检查。当前五 TAG、同日期 V19 Host 不自动变成任意 TAG/跨日 Host。
4. 独立研究 HTTP/CLI→严格 codec→永久 intent/claim→owner consumer，按 process+creation+session+profile+canonical payload 固定幂等；同 request_id 不同 payload 冲突，unknown 永久冻结不补发。生产 backend 仍不注册。
5. 状态分别为 `validated_draft`、`legality_rejected`、`dispatched`、`dispatch_unknown`、`reply_observed`、`selected_state_observed`；不把这些压成 success。预检 false 是有价值结果，不授予 submit，也不假称动作功能已经完成。

严格 SP 来源和可靠 world epoch 是生产条件的独立缺口，不是本方案把静态动作称不可研究的理由；受限可丢弃研究仍需显式新版本、安全 guards 和独立审查，不能绕过现有冻结边界。

## 下一批顺序与观察

优先 A：核心五 pair + curry 的新 profile/no-send 验证；B：其余既有 pair 的方向和固定参数迁移；C：独立属国 command profile；D：参数化省份/战争/借用对象单独处理。`plan.json/batch_groups` 保存范围、前置和次序，**不是实际序号或当前目标许可**。

每个批次只做同一组 initial 和 final 聚合 census，内部逐请求仍核持久 claim、原生归属、异常、独立后来 health；拒绝跳过 submit、不消耗空序号，unknown 立即终止。同目标确需新日期时，只在单独已审新 Host/监督 lease 合同下推进，不把 v19 锁定同日修改为任意时钟。

正向后又取消会抹去中间状态；final census 只能说明选定最终状态及 dispatcher 的归属覆盖，不能证明所有正向曾生效。六种军役连跑最终只有最后值可观察。跨日经济变化、人情、费用不作逐项成本归因；若要独立效果验收，另立有限实验，不能违反本批 initial/final 约定。不得为了凑覆盖自动开启 acceptance override、强制 state2、重复自然 AI 拒绝或修改 fixture。

## 离线重放

```powershell
python -B work/candidates/v20-typed-family-dispatch-plan-1375/build_plan.py --check
python -B -m unittest discover -s work/candidates/v20-typed-family-dispatch-plan-1375 -p test_*.py -v
```

check 只重建文档对象并比较固定 bytes，输入前后 SHA 完整核验。未运行旧游戏相关脚本/预检/API。所有分析输出、首次 shell 搜索路径/编码小错误在作者工作记录说明；没有将失败检索当证据，也没有遗留 shell。此候选不是执行批准。
