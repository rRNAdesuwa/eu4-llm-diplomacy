# 1.37.5 原生外交研究实验

这些实验用于补齐原生调用证据。v4 仅构造、预览并释放临时对象，不发送外交 command。v5 已完成三个无发送阶段，并实际发起一次固定的 FRA→ENG 改善关系；前后只读观察、保存和重载均验证了关系与外交官任务。外部 API 的执行适配器目前仍未开启。

## v5 已运行：命令生命周期与一次固定发送

独立源码 `work/native/research-pipeline-1375.cpp`，构建脚本 `work/native/build-pipeline-1375.cmd`，输出 `work/runtime/native1375-v5/eu4_pair_pipeline_1375.dll`。本次 `/W4 /WX` 编译通过，DLL SHA-256 为 `03274A2E576F09D35B2FD0055B2EA234681F9C93C4AA227FC142B689D9CAC2F9`；六份源码哈希记录在同目录 `build.json`，源码副本保存在 `sources/`。用户完整重启并载入暂停基线后，PID **46972**、窗口／帧线程 **69052** 安装成功，DLL 基址 `0x7fff469d0000`，BridgeStart 返回 0。此进程随后随读档结束；**源代码、构建产物和记录作为该次证据保留，下一版使用新文件和目录。**

五类 factory/clone/destroy、20 组 preview 和 20 组 command 构造／独立 clone／gate／析构全部实际完成，无异常。两个门槛矩阵均为 7 允许／13 拒绝，前后有限外交字段相同。发送前保存不可变日志 `no-send-phases-46972.jsonl`（SHA-256 `ecb518def4608c5503cc8f2b822996c32272ebcfa775ed2a0b54800ae661d030`），`command-verification-46972.json` 为 passed。该验证只针对无发送阶段。

随后唯一固定提交在同一线程发生：context submit 返回 true、caller command 容器被清空、异常码 0。此前原件已析构，移交后实验侧没有再次析构 command／clone。`pair-submit-improve.attempt.json` 保留一次性声明，不能删除后再试。

只读前态 `work/runtime/pair-effects-presubmit-v5-46972.json` 中双方改善索引为空、三个 FRA 外交官均无任务；后态 `pair-effects-postsubmit-v5-46972.json` 中双方索引指向同一活跃关系 `0x1e7912739b0`，vtable RVA **0x1c81658**，actor/target 完整句柄匹配，关系链接 mission `0x1e8a8ea48a0`。该 mission token **0x2ddb**、envoy ID **0**，entry 状态为 **2**，其余两名外交官仍空闲。前后日期均为 1444.11.11。`pair-effects-comparison-v5-46972.json` 报告 `observed_effect=true`；这是受控实验的新增对象图证据，不是任意并发请求的独立因果证明，也不是其他外交动作的执行认证。

用户另存 `llm_diplomacy_1375_after_improve.eu4`（34,776,584 字节，SHA `7BFABE371E68AE502B806F9B80375FC8A4DAC638AD116D2506966FEF69633C5F`），序列化记录新增 `improve_relation={first=FRA second=ENG start_date=1444.11.11 envoy=0}`，FRA envoy 0 增加 `action=2`，ENG 对 FRA 新增 2.000 的 improved_relation 好感。这个 action 值是本次观测，不能外推通用存档枚举。`saved-effect-verification-46972.json` 验证新增保存记录。用户随后通过菜单载入该文件，实际产生新 PID **45564**；`pair-effects-reloaded-45564.json` 中独立解析的新指针仍组成相同身份／token／envoy 的完整活跃图，`reload-verification-45564.json` 为 passed。此路径通过新进程身份作废旧 DLL；它不能证明每一种可能的读档路径都重启。

v5 保留独立 selftest、preview 两阶段，再依次要求以下单独 marker。每阶段仅一次；同进程前置阶段必须全通过，线程、世界／数据库／国家数组／玩家／日期保持一致。这个暂停实验的指针与日期检查不能替代正式后端的存档加载代际检测。

| 阶段 | 文件名 | 精确 ASCII 内容 | 原生调用范围 |
| --- | --- | --- | --- |
| 命令构造 | `pair-command.request` | `PAIR_COMMAND_1375\n` | 20 组工厂、初始化、wrapper、clone、gate、command 析构和原件析构；不发送 |
| 固定真实发起 | `pair-submit-improve.request` | `PAIR_SUBMIT_IMPROVE_FRA_ENG_1375_ONCE\n` | 仅 FRA→ENG、正向 `improve_relation` 一次 |

真实发起先以 `CREATE_NEW` 写入并落盘 `pair-submit-improve.attempt.json`。已有、部分写入或结果不明的 claim 均保留，不自动删除或重试；加载器也拒绝遗留 marker／claim。日志写入／flush 失败、世界或线程检查失败都会禁止进入提交。提交前确认局部所有权并销毁原件，然后经钉扎的单人 context `0x14ca210(context, command**)` 转交 command；进入此调用后绝不由实验侧再析构 command／clone，即使返回假或异常。回执只说明投递是否得到确认，`applied_verified` 仍为 false。

必须在发送前保存固定日志快照，并运行 `tools/verify_diplomacy_command.py` 等离线验收器。三个无发送验收器都拒绝含实际发送事件的完整后续日志，且不会声称整个 v5 DLL 没有发送能力。效果规范见 `docs/native-pair-effects-1375.md`。基线文件明确序列化 `multi_player=no`；这与用户加载基线确认构成本次单机实验的前提，server/transport 虚表本身没有证明排除多人主机。世界锁不是存档加载代际检测，claim 也只约束同一输出目录，不能冒充跨版本的全局幂等。

```powershell
work/native/build-pipeline-1375.cmd
python -B work/native/inject_pipeline_1375.py --pid <新枚举的游戏PID> --ack-test-save
```

## v4 历史运行状态

**此前成功实验是 v4，PID 39708，窗口/帧线程 63336；该进程已由用户正常退出。** DLL 位于 `work/runtime/native1375-v4/`，SHA-256 `9993CC214C88B0C8E9A32222B75804920E7BDF252C9519BD93FBB65080517714`。安装了真实帧 hook 的模块不能用失败模块清理工具卸载或热替换。

五类 factory → clone → 删除析构均实际通过：附庸、联姻、改善关系、保独、间谍网。对象字段、线程、两份对象的析构和零异常均有日志。`lifecycle-verification-39708.json` 为 `passed`，但 `verification_scope=lifecycle_only`、`execution_verified=false`。前后有限只读字段（玩家/日期/FRA→ENG 冷却/FRA 外交官）相同，不是全世界状态无变化的证明。

随后 20 组无发送原生合法性预览全部正常完成：五类 × 正向/取消 × FRA→ENG/POR。7 组允许、13 组拒绝；每组均正确初始化/析构且无异常。

| 正向动作 | FRA→ENG | FRA→POR |
| --- | --- | --- |
| 附庸 | 拒绝 | 拒绝 |
| 联姻 | 允许 | 允许 |
| 改善关系 | 允许 | 允许 |
| 保独 | 拒绝 | 允许 |
| 间谍网 | 允许 | 允许 |

对应 10 组取消预览都拒绝。这里只是 1444.11.11 基线的原生可用性结果；没有发送请求，没有对方 AI 接受率或效果结算。日志汇总字段 `accepted` 在这个研究模块里仅计数 `allowed=true`，不能解释为对方接受。

## 安装问题及已确认的原因

用户已通过游戏菜单保存独立非铁人存档 `llm_diplomacy_1375_baseline.eu4`，2026-10-07 22:28:15（JST），34,742,723 字节。测试 Mod 仍停用。

首次研究 DLL SHA-256 为 `0D6CA7F88AD5A46541A1A043B7F4AAE59D445BBEA369AE5478D25FC017EECBF9`，目录 `work/runtime/native1375/`。对当时 PID 71428 的加载返回 `BridgeStart=21`：线程收集或冻结检查拒绝，尚未写入帧 hook。DLL 留在进程中，未执行 factory、clone、合法性或发送调用。游戏仍有响应，之后的只读国家结构核验正常；不能据此断言全部游戏状态未改变。

当次没有细分失败阶段日志，故不能确定是线程退出、新线程、权限、指令地址还是其他检查失败。随后只读枚举得到 Native 147 个线程、ToolHelp 146 个线程，说明存在变化，但不能倒推第一次失败的确切原因。记录位于 `work/runtime/thread-enumeration-readonly-71428.json`。加载器禁止在该进程中再加载研究 DLL；需要完整退出游戏，重新启动并载入基线存档。

第二版构建输出独立目录 `work/runtime/native1375-v2/`，保留第一次加载的文件。增加了逐阶段拒绝诊断，以及未开始修改代码时最多三次安装尝试。任何指令地址、线程集合或权限检查仍须通过。新版本的编译、加载和实验结果分别记录，不能仅凭构建文件存在宣称运行通过。

在新 PID 39708，v2 三次均拒绝于 stage 41：原生枚举出现初始 ToolHelp 枚举没有的线程 11932。v3 统一使用原生枚举后，三次均拒绝于 stage 36：对同线程 SuspendThread 返回错误 5。只读核对确认该线程已退出：退出码 0、非零退出 FILETIME `134358551247644201`、所属 PID 39708。它是仍被引用的已结束线程对象，不能被当作活线程暂停；不能把这一发现描述为游戏的反调试保护或权限限制。

v4 仅在退出码和非零退出时间双重确认后跳过已结束线程，对实际成功暂停的索引逐项恢复，仍拒绝未知运行线程、地址冲突和任何恢复失败。实测第一次尝试安装成功，`terminated_skipped=1`。

v2/v3 都在写入 hook 前被拒绝，所有恢复成功、原始前缀未变、没有实验记录或后台工作线程。经过分别固定 PID/模块路径/基址/哈希/全部三条失败日志的特例审查后，调用 FreeLibrary 返回 1，随后确认模块消失和原始前缀不变；报告分别保存在各自输出目录 `unload-audited-refusal-39708.json`。这是未安装模块的清理，**不能推广到已经安装 v4 hook 的模块**。通用加载器继续禁止替换已加载桥接。两个失败模块各留下一个日志句柄，游戏进程退出后由系统回收；后续使用不同目录。

## v4 构建和载入（历史已运行版本）

```powershell
work/native/build-lifecycle-1375.cmd
python -B work/native/inject_lifecycle_1375.py --pid <新枚举的游戏PID> --ack-test-save
```

加载器检查游戏完整哈希、进程路径、既有桥接模块、DLL 与源码的构建清单。旧 1.37.4 加载入口仍拒绝当前游戏。禁止修改或覆盖已加载 DLL、同进程热替换以及遗留 marker 后直接启动。

当前构建脚本默认输出 v4 目录。该文件已加载，继续开发应改用新的输出目录并在新的游戏进程中测试。

帧入口只使用本次 EXE 核对的 RVA `0x10a6ec0`。保存/恢复的寄存器、原始 20 字节序言和静态 MASM trampoline 均有对应 x64 unwind 元数据。安装前独立查出本进程唯一可见无主窗口的线程，之后每个回调均核对线程身份；任何不符都会禁止实验。安装时短暂暂停同进程线程，并检查指令指针没有落在覆盖区域。暂停区不调用 ToolHelp、日志或格式化代码。

## v4 两个单独触发的实验

安装成功不会自动调用游戏动作。`research-1375.jsonl` 必须先出现稳定的 `research_frame`：`world_ready=true`、`thread_changed=false`、累计至少 100 帧，并且线程与安装日志中的窗口线程一致。

1. 在 DLL 输出目录创建 `pair-selftest.request`，内容为精确 ASCII `PAIR_SELFTEST_1375\n`。帧线程只执行一次五类 factory → clone → 删除析构；对象保持工厂默认的无效国家句柄。逐项核对对象尺寸、虚表、字段和婚姻额外字符串。
2. 仅在生命周期全通过后，创建 `pair-preview.request`，内容为精确 ASCII `PAIR_PREVIEW_1375\n`。它单独验证五类正向/取消模式的原生合法性：临时动作填入核实的 FRA→ENG、FRA→POR 完整句柄，调用 `0x4e9d00(action, nullptr, false)`，随后析构。合法性返回 false 是正常拒绝结果；异常或生命周期错误才是实验失败。

marker 经逐字节检查后先删除再运行，单进程不重试原生实验。需要存档、外交官、同国冷却或日期变化的真实执行实验尚未在本模块实现。布尔合法性结果不包含 AI 接受概率或最终效果证明。

日志、DLL 清单、前后只读结构快照应一起保留。`tools/verify_diplomacy_lifecycle.py` 只验证五类生命周期及有限字段快照；它不把 preview、目录条目或编译成功计入外交执行验收。
