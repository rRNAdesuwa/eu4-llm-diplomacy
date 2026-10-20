# 原生 AI 议和：对象来源授权实验（2026-10-05）

本实验保留涉及法国的原生和平锁，只允许桥接构造的请求及其原生 clone/协议重构后代。**v7 白和平及后续金币赔款34.4均已通过原生 AI 接受、结果保存和重载验收；赔款实际扣款和阵营合计入账均为34.400。** 赔款最新状态见 `native-authorized-gold-test.md`；本文各旧版本与旧进程状态为历史。

可复验的前置条件：已保存的单机交战基线、玩家 POR、安装/无提交自检通过、重载后重新完成 `tag FRA → winwars → tag POR`、法国至少一名空闲外交官、FRA→ENG 关系冷却通过。使用 `queue_guarded_whitepeace.py --pid <PID>` 排队，DLL 再检查实时上下文和 preview≥100。游戏必须产生前台帧；**无需推进游戏日期即可处理本次白和平**。发送入口或 `submitted=true` 单独不能作为生效证明。

## 独立资产

- `native/authorized-probe.cpp`：以当前 `probe.cpp` 为基础的独立研究源码。未替换旧和平锁源码或 DLL。
- `native/build-authorized-peace.ps1`：构建授权实验 DLL。
- `native/start-authorized-peace.ps1 -SavedTestGame`：检查固定 DLL 哈希、唯一游戏进程、当前 POR 玩家及 FRA/ENG 完整句柄，再安装。失败不得同进程重试。
- `native/eu4_bridge_authorized_peace_v1.dll` SHA-256：`EBED86F52CD05C52DFA21E6ACFA7CF26AF52ABCFAAD4EA00E89643DC029CD225`。
- `native/restart-game.ps1 -SavedTestGame -SaveName llm_ai_peace_before.eu4`：保留普通启动参数，删除旧 continue/continuelastsave 选项，再追加指定存档。仅支持 ASCII 简单文件名。必须核对实际载入状态。

## 原生依据与权限规则

本机固定 exe 哈希及 RVA 规则沿用 HANDOFF.md。

`peace vtable 0x1c7b840 +0xb0` 指向 `0x59ba70`，签名为 `void* clone(void*)`；它分配 0x210 字节并深复制和平 offer。generic wrapper `0x4e9960` 通过此槽复制输入 action；generic executor `0x4e81c5`、`0x4e824f` 也通过此槽生成响应对象。响应进入 wrapper 时再次复制，因此授权需逐级传播。

`peace vtable +0` 指向 `0x598b90`，签名为 `void* destructor(void*, unsigned flags)`。generic command 析构 `0x4e74a0` 通过此槽销毁所持 action（除原生持有状态分支）；在实际释放前清除对象授权，避免同地址重用继承权限。源码直接析构的本地自检 action 则显式撤销。

桥接仅在完成身份、条款、深复制、原生有效性预检后，为待提交的准确 action 地址登记递增授权 ID。全局 clone 槽 hook 只有在源对象已登记时才传播 ID；128 槽 sidecar 满时拒绝新增，失去来源的副本仍被法国和平锁阻止。没有用国家、日期或金额作为授权键，也不修改引擎对象中的授权字段。

新增 clone/析构槽与原有执行槽、帧 hook 在其他线程暂停时安装；安装失败回滚，不热卸载。只覆盖已验证的和平 action 类，其他外交仍未隔离。

## 验收顺序

1. 核对加载基线：存档 meta 为 1445.5.30、player POR，FRA/ENG 活跃战争一场。基线语义报告为 `runtime/authorized-peace-baseline-20261005.json`。
2. 安装后不自动发送。首个有效帧上下文达到 100 帧时，执行无提交自检：登记本地 action、通过原生 wrapper 复制、检查授权继承，再通过原生 command 析构检查授权撤销。必须出现 `authorization_selftest_passed` 才允许发送。
3. 用户保持暂停，按需要执行 `tag FRA`、`winwars`、`tag POR`。战分触发仅供本实验；不能用它替代权限隔离。
4. 助手创建 `native/whitepeace.request`。检查 seed、`authorization_native_clone`、`llm_authorized_peace_execute_entry` 的同一授权 ID，并检查未授权原生提议仍出现 `native_peace_authority_blocked`。
5. 用户推进日期，观察 AI 原生接受/拒绝。执行入口状态不是结算证明；应另存独立结果，验证战争、双向休战和领土不变，再用指定存档启动重载。
6. 白和平新组合通过后，从原始交战基线重复赔款。金额须核对原生 getter、实际金库、保存和重载；不能把 offer 汇总分值当金币。

## 当前状态与限制

编译已通过（-Wall -Wextra -Werror）。2026-10-05 已按指定存档参数重启；最初只读探针显示 player=---，尚待地图加载确认。用户已确认启动弹窗并进入暂停地图；只读探针确认 player POR、current_raw_date=56461776。新版已安装成功（BridgeStart=0），无请求发送，等待前台帧完成自检，无新的议和成功结论。

旧和平锁运行日志已保存为 `runtime/peace-lock-before-authorized-20261005.jsonl`。不恢复旧 Sender，不修改基线存档，不使用 UI 自动化。

授权不跨 DLL 重启或对象序列化；若引擎存在未经过已验证 clone/析构槽的复制或释放路径，需要补充证据和 hook。64 槽执行日志与 64 槽复制日志满后不再记录；权限判断继续工作，但日志缺失不能作为未发生动作的证据。当前锁身份读取失败时仍沿用旧版透传边界，不能宣称完整外交排他权限。

## v1 实测失败与 v2 修正

v1 无提交 clone/析构自检通过，但第一个实际请求预览值 -26，随后虽 submitted=true，执行端事件为 native_peace_authority_blocked、authorization=0。未执行 winwars 的条件错误与 transport 来源丢失同时存在；不能解释成 AI 拒绝。完整日志见 runtime/authorized-peace-v1-transport-failure-20261005.jsonl。

transport `0x1580270` 先在 command+0x48 写来源编号，再从 transport+0x128 原子计数器分配 command+0x4c 序列号，随后通过 command vtable+0x08 → +0x10 序列化。serializer `0x4e8470` 调 base serializer `0x14c6190`，后者写来源编号（token 0xc7）、flags（0xcc）、序列号（0xdb）；base parser `0x14c62c0` 分别恢复 +0x48/+0x4a/+0x4c。说明 clone sidecar 不覆盖这个重构边界。

v2 源码为 native/authorized-probe-v2.cpp；DLL 为 eu4_bridge_authorized_peace_v2.dll，SHA-256 为 28E6BD4B9EFE12480746E7824EC4671070E44F08EFFCB3DB434D79CAA8F4C1A7。当前 build/start-authorized-peace.ps1 已指向 v2。v1 保留供失败复现，不再使用。

v2 在已验证 generic command 序列化槽登记已授权 action 对应的原生（来源编号、序列号）组合。执行端只有准确匹配登记的组合才能一次性消费并恢复 action 授权，后续仍沿原生 clone 传播。未修改协议数据，没有以相同条款/日期猜来源。只接受 flags=0 的已验证路径；128 项满、重放或来源不明时不放行。日志 authorization_transport_identity phase=1 是登记、2 是消费成功，3/4 是登记或恢复失败。仍需运行证明收发两端身份匹配；编译通过不能代替权限组合验收。

用户已在暂停状态执行 tag FRA、winwars、tag POR，并另存当前战役。游戏实际生成文件名 ` llm_authorized_winwars_baseline.eu.eu4`；助手验证 meta POR、1445.7.2、FRA/ENG 战争一场后，保留原件并复制为 ASCII 规范名 llm_authorized_winwars_baseline.eu4，供启动参数使用。已以该存档重启，尚待弹窗确认、v2 安装和实验。

## winwars 后的 v2 结果与 v3 诊断

在同一 v2 进程重新执行 tag FRA → winwars → tag POR 后，白和平 preview=100、flag_208=1、native_valid=true。请求 authorization=3，发送端协议 key=0x2e811a7 已登记，但执行端仍 authorization=0，被锁阻止。因此战分条件已确认，当前阻塞点是来源恢复，不能称为 AI 拒绝或白和平失败策略。完整日志：runtime/authorized-peace-v2-winwars-gate-failure-20261005.jsonl。

当前研究源码/构建/加载入口已切到 authorized-probe-v3.cpp / eu4_bridge_authorized_peace_v3.dll；SHA-256 D43311ED6301FBB37D24E5C6AF5DE9859F3B8196D3695D341C2822BBBA9996C9。v3 增加执行端 protocol_key/protocol_flags 日志与 phase=5 收包观察，并以来源编号+原子序列号组合做准确匹配（flags 作为诊断字段，不作为来源身份）。原生法国和平锁保持启用。

v3 已以规范基线重启并安装成功；尚待用户在此次重载后重新执行 winwars，未排队发送。务必将“重载后用户完成 winwars”作为实验前置步骤，不能假设保存重载保留其效果。当前没有新的和平结算成功证据。

## v3 收发身份差异与 v4 单机限定修正

v3 在 winwars 条件下 preview=100，发送 key=0x100b0f（序列号 16），执行 key=0x10ffff（序列号仍为 16，来源变为 0xffff），flags=0。请求仍被锁，见 runtime/authorized-peace-v3-origin-sentinel-failure-20261005.jsonl。

只读核对发现原生 world server 的 dispatcher getter 为 0x811ad0：读取 server+0x330 的 context，再返回 context+0x370。UI 与 world server 路由实际指向同一 dispatcher、transport 和 transport+0x128 计数器；计数器 next_sequence=17，与刚发送的 16 对应。证据 runtime/singleplayer-transport-counter-proof.json。

v4 仅用于当前已另存的单机实验：启动及每次恢复均检查 UI/world 路由仍共用同一已验证计数器。来源完全匹配可消费；执行端来源为已观察到的 0xffff 时，要求序列号对应唯一已授权发送登记（有歧义则拒绝）。序列号来自同一原生原子分配器，不使用和平国家/日期/金额作为授权键。消费一次即移除，随后仍以准确对象来源沿 clone 传递。此规则尚不能推广到多人或多 transport 场景。

当前 build/start-authorized-peace.ps1 已切到 authorized-probe-v4.cpp / eu4_bridge_authorized_peace_v4.dll，SHA-256 0EFAC80B963D2D3E67B22A264737AC30C82B03425423F7CC5FA51C101727EB70。额外加入 preview<100 自动停止、不投递的实验门槛，防止漏做 winwars 时发送。旧版本与失败日志均保留。v4 已编译并重启基线，尚待地图确认、安装和运行验收。

## v4 安装回滚与 v5 诊断

v4 BridgeStart 返回 18，日志显示 shared_counter_verified 后 hook_not_installed、hooks_rolled_back=true；未发起请求，不能声称 v4 来源恢复已实测。失败进程未重试或热卸载。日志保留为 runtime/authorized-peace-v4-install-rollback-20261005.jsonl。

v5 沿用 v4 权限与 preview 门槛，新增安装阶段、线程枚举/暂停计数、Win32 error 与冲突 RIP 日志，用于区分暂停检查与各 hook 安装阶段失败。当前 build/start 入口指向 authorized-probe-v5.cpp / eu4_bridge_authorized_peace_v5.dll，SHA-256 5A285F642F8D69259BA166C804E0DF6897A31B0BD16F5DB2C6837AB040C37C02。已编译并重启，等待暂停地图确认后安装；安装确认成功后才请求用户重做本轮 winwars，随后创建发送请求。

## v5：授权入口通过，结算仍未验收

v5 安装成功，自检通过；用户本轮完成 winwars 后 preview=100、native_valid=true。发送登记序列号 16；执行端来源 0xffff 时唯一匹配恢复 authorization=2，并记录 llm_authorized_peace_execute_entry state_raw=0。证明授权请求到达原生执行器，不等于提议已生效。

后续 ENG→FRA 及 FRA→ENG 的未授权原生请求继续被拦截，证明原生和平锁仍起作用。用户推进日期后仍交战；截至只读快照，current_raw_date=56464104，比基线 56462568 多 64 个游戏日，FRA last_sent 原始值仍为 56460528；暂无同授权 ID 的 state 1/2 日志。需进一步核对接收端 action 原生有效性、反序列化的战争参与方和实际方法分支，不能称为 AI 已拒绝。

后台现象已观察到：帧日志暂停时请求文件保持未消费，返回游戏才处理。本轮请求已消费且进入执行器，随后日期和原生 AI 提议均有进展，因此不能单凭后台现象解释本轮没有结算。

## 接收端字段诊断候选 v6（未安装）

已准备并编译 authorized-probe-v6.cpp / eu4_bridge_authorized_peace_v6.dll，SHA-256 AC66C3BCD6415908A3BD7CEAAE966056C18C64495CAA357C7F6F054945F3D664。独立构建入口为 build-received-offer-probe.ps1；当前 start-authorized-peace.ps1 与普通构建入口仍对应正在运行的 v5。

v6 仅增加已授权接收对象的四组战争参与方计数、完整国家句柄验证、offer owner 自引用及 action+0x28 原始值日志，不增加原生引擎调用或强制接受。接收端出现 state 0 而没有结算，需先与发送前的 2/6/2/6 参与方及原生 owner 布局比较。+0x28 字段语义仍需核对，不应只凭日志字段名推断为创建日期。v6 尚未运行验收，当前游戏进程及 v5 锁保持原状。

## v5 队列复核与 v7 原生有效性观察（进行中）

只读工具 `probe_pending_peace.py` 复用原探针的 exe 哈希、进程路径及 QUERY_INFORMATION | VM_READ 校验。固定检查 FRA、ENG 和当前玩家；AI 链表最多 128 节点，外交消息向量最多 256 项，不调用引擎方法，不扫描整个堆。布局来自 generic executor 0x4e7c80 与消息构造 0x4e7580，字段业务语义尚未全部确立。

PID 47868 的快照 `runtime/authorized-v5-pending-queues.json` 中 FRA/ENG 的 country+0x18e8 为 0，+0x18d8 链表为空；外交记录没有 FRA↔ENG 的 type 0x293c 消息。法国最后发送日期仍为 56460528。它只能说明当前快照未发现待处理提议，不能证明请求从未入队。初次快照还读取了 WUR（工具后来改为当前 player_slot），不影响 FRA/ENG 的证据。

原生 type getter 0x59ba60 恒返回 0x293c；generic executor 首先以原参数调用 peace vtable+0x80（0x59b480）。该检查返回 false 时走 0x4e83a0 旁路，不更新 last_sent。发送前检查成功并不保证反序列化后检查成功，因此必须观察接收端实际调用的返回值，不能再把入口日志当作投递成功。

v7：`native/authorized-probe-v7.cpp`、`build-validity-observer.ps1`、`start-validity-observer.ps1`；DLL SHA-256 `F989A4DE0BA60C1285907752179DD9626AEA2611ED1A1A42771410BF0952FAD3`。保留 v6 字段诊断，并在同一个 lifecycle 安装/回滚事务中观察 +0x80 槽。观察函数使用原参数调用 0x59b480 **一次**，原样返回 bool，不添加验证调用或强制结果；只记录准确 sidecar 授权对象，64 项固定缓冲由帧线程写日志。新增事件 `authorized_native_validity_result` 包含实际返回值及调用前后状态。编译 -Wall -Wextra -Werror 通过，尚未运行验收。普通 build/start 入口继续保留 v5，v7 使用独立入口。

v5 完整日志已归档为 `runtime/authorized-peace-v5-executor-entry-no-settlement-20261005.jsonl`。游戏已用独立存档 `llm_authorized_winwars_baseline.eu4` 重启为 PID 48092；初次探针显示 world 尚未初始化，等待用户关闭启动提示并进入暂停地图。安装确认成功后，本轮仍必须重新执行 tag FRA → winwars → tag POR，再允许发送；保存重载不能代替该前置条件。


v7 后续：PID 48092 已安装成功（BridgeStart=0），无提交授权自检通过；用户已确认本轮 tag FRA → winwars → tag POR 完成。单次 whitepeace.request 已排队，当前等待前台帧消费，尚未取得原生有效性结果。详见 runtime/authorized-v7-progress.json。


## v7：接收字段/有效性正常，定位到外交官门槛

v7 authorization=2 实测：preview=100，接收协议身份恢复成功；authorized_native_validity_result.result=true、state_before=state_after=0；参与方 2/6/2/6、完整句柄和 offer owner 均通过。暂停快照 runtime/authorized-v7-paused-after-submit-queues.json：FRA/ENG AI 队列仍空，FRA last_sent 未更新。不能称为 AI 拒绝。

generic executor 的 0x4e7d89 起读取 actor country+0x1480 → +0x18 → vector +0x20/+0x28，统计每个 envoy+0x18==0 的条目；0x4e7e09 在计数为零时直接跳至 0x4e8440，绕过消息构造 0x4e7580 和 last_sent 更新。基线 FRA 的三个条目均为 2；对应保存的 diplomats 中 id 0/1/2 均 action=2（runtime/authorized-baseline-fra-envoys.json）。peace ctor 0x598b20 将 +0x40 置 1；+0x100 方法 0x59bef0 返回该字节，故普通请求进入上述外交官分支。当前最明确的可复验阻塞是无空闲外交官；需要释放一名后重试来验收因果，尚未宣称和平成功。

工具 probe_pending_peace.py 现输出 available_diplomat_count；queue_guarded_whitepeace.py --pid <PID> 在只读核对 POR、FRA 空闲外交官、发送日期及自检日志后，用独占文件创建排队一次。DLL 继续检查实时上下文、preview>=100 和原生有效性。这是前置条件快照，仍可能受 AI 重新派遣影响，不能作为投递/接受证明。当前用户正在召回外交官，游戏 PID 48092，v7 保持安装，不需重启或重复 winwars。


## 第二次重试：外交关系冷却在执行器之前阻止命令

召回外交官后确认 FRA 空闲数=1，第二笔请求 authorization=3、preview=100、preflight=true、serialized key=0xd02996，但没有原生执行入口或新的有效性调用。只读 sidecar：packet_count=7、response_count=4、gate_count=1，均未满；authorization=3 的登记仍待消费。消息当前也未找到。因此没有 AI 接受/拒绝证据。

新增静态证据：generic command vtable+0x40 为 0x4e8660。普通 state=0 且 peace+0x40!=0 时，它读取 actor+0x1510 的目标关系条目（每项 72 字节）+0x30，要求 current_raw_date > threshold，game+0x23a9 为旁路字节。本轮旁路为 0。generic executor 在 0x4e7d1c 调 0x35a860；该函数以 action+0x28 为日期，调用 0x14c7f30 加全局配置 0x233e044，再写该关系+0x30。这个写入发生在检查空闲外交官前。因此第一次没有空闲外交官的请求也可能写入关系冷却；不能只看 country+0x24a0。

只读证据 runtime/authorized-v7-relation-cooldown.json：FRA→ENG threshold=56463312、current=56463336、旁路=0，当前已通过。较早重试队列快照 current=56463120 尚在该阈值前，支持冷却导致第二次命令未进入执行器的解释；该命令的 +0x40 实际返回尚无 hook 证据，结论是静态控制流加只读状态的推断。

probe_pending_peace.py 与 queue_guarded_whitepeace.py 已加入关系冷却检查，保留 country last_sent、空闲外交官、自检/POR 检查和 DLL 的 preview/native-valid 门槛。新快照使用唯一文件名，避免未来重试覆盖取证。当前第三笔重试已同时通过空闲外交官和关系冷却检查并排队；仍无和平结算验收。


### v8 候选：把两项前置门槛放入 DLL 发送端（未安装）

已准备 native/authorized-probe-v8.cpp、native/build-guarded-sender.ps1；DLL SHA256 63A1DEECD867E258930A4A8D35ACCFBBA4D0C258D6466A6A07118829D5EB1186，-Wall -Wextra -Werror 构建通过。v8 在原 v7 发送函数构造提议之前，以有界只读方式核对 FRA 外交官列表、至少一名 +0x18==0 的外交官、FRA→ENG 的关系 +0x30 日期门槛及原生旁路字节；读取失败或门槛未通过时记录 peace_native_preconditions_stopped 并 return，不提交也不触发引擎冷却副作用。没有额外引擎调用，不清零冷却或修改外交官。当前 PID 48092 仍运行 v7，第三笔请求仍待前台帧消费；不为部署候选而重启当前实验。编译通过不能代替运行验收。


## 最终验收：v7 白和平成功，保存重载通过

第三笔 authorization=4：发送 preview=100；序列号 911 的请求和 912 的原生响应均恢复同一授权，clone 两级继续继承。日志先记录 state=0，再记录 state=2；两次原生有效性检查均 true，参与方/完整句柄/owner 均通过。发送、响应及结算快照的 current_raw_date 均为 56463336（1445.8.3），因此本次原生 AI 白和平在暂停帧中完成，不需要先推进日期。法国 last_sent 更新为 56463336，外交官 id=0 进入该和平消息的派遣/返回状态。未授权 ENG→FRA、FRA→POR 等和平仍被锁拦截。

证据：runtime/authorized-peace-v7-paused-whitepeace-20261005.jsonl、runtime/authorized-v7-paused-whitepeace-proof.json、runtime/authorized-v7-user-reports-whitepeace-state.json。

用户将结果保存为实际文件名 ` llm_authorized_whitepeace_v7.eu4.eu4`（前导空格、重复扩展名）；助手保留原件并复制为启动兼容的 `llm_authorized_whitepeace_v7.eu4`。保存结果 meta=1445.8.3/player POR。FRA→ENG 和 ENG→FRA 均 truce=yes、last_war=1445.8.3；同一战争当天八个参战国全部有 rem_attacker/rem_defender 记录。FRA/ENG/POR/AMG/AUV/BOU/FOI/ORL 的 owned_provinces 均与交战基线相同；额外检查 BUR 也未变化。原生提议 gold_cost_raw=0，不用跨月金库变化作为零付款证据。

修正 inspect_peace_save.py 的判定：不能从 participant 统计或 persistent_attackers/defenders 判断当前交战，它们在暂停结算后仍保留。find_eng_fra_active_wars 改用当前 attackers/defenders；当前侧名单为空、历史侧名单仍有国家的回归检查通过，基线当前交战数=1、结果=0。原始 active_war 对象/历史统计仍在文件中，不等于仍交战。完整验收 runtime/authorized-v7-whitepeace-save-validation.json。

结果已通过 `-continue=llm_authorized_whitepeace_v7.eu4` 重载，新 PID 5428。用户确认“正常载入，仍和平，推进几日无异常”。只读确认玩家 POR、FRA last_sent=56463336；重载后用户推进日期，所以不要求当前日期仍等于发送日期。为保留法国原生和平隔离，新进程安装了已验证的 eu4_bridge_peace_lock_v1.dll（BridgeStart=0），发送禁用，无排队请求。v7 当前不再注入该进程；其成功日志已完整归档。

普通 native/build-authorized-peace.ps1、native/start-authorized-peace.ps1 现指向已验收 v7 和固定哈希 F989A4DE0BA60C1285907752179DD9626AEA2611ED1A1A42771410BF0952FAD3。它们用于下一次独立交战实验，不能同进程替换当前旧锁。v8 的 DLL 内前置检查仅编译通过，仍是候选；赔款、多人传输、完整外交隔离均未验收。

注意：v7 的 peace_dispatch_preflight.method_rva 在 hook 安装后记录的是 DLL observer 地址减 exe base，不能解释为有效 exe RVA；原生有效性实现由安装槽身份与 wrapper 中固定原函数 0x59b480 确认。该诊断字段不用于权限或生效判断。
