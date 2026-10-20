# EU4 1.37.4 原生线程探针

本目录是内部接口研究代码，不是完整外交插件。默认 `observe` 模式不发送提议、不改变玩家国家、不修改存档或磁盘中的游戏 exe。安装时会修改当前进程的帧函数入口；游戏退出后该修改消失。不要卸载已安装的 DLL，恢复方式是正常退出并重启游戏。

仅适用于已核对 SHA-256 的本机 EU4 1.37.4。任何内部函数调用和 hook 都可能导致测试进程崩溃，因此首次运行前需另存测试局。加载器要求显式 `--ack-test-save`，不自动运行。

**当前发送禁用（2026-10-04）：旧 sender DLL 收到、拒绝测试通过，但点击接受会崩溃，不能使用。** `SEND_DISABLED` 阻止加载发送版；源码也直接拒绝使用未初始化战争上下文的条约。下文第三版说明为历史流程，不是当前可用接口。

本地 minidump 确认：访问异常 C0000005，RVA 0x108d670 执行 `mov rcx,[rax]` 时 RAX=0；对应 CPeaceOffer+0x40 参与国数组首地址。条约虚表和双方句柄正确，但四组参与国数组全为空。默认构造、深复制、投递通过，不能证明条约语义完整。正在查找原生战争上下文初始化入口；不能只补几个句柄后继续发送。证据：`work/runtime/native-crash-analysis.json` 与 `native-crash-fault-disassembly.txt`。

已准备 `eu4_bridge_warcontext.dll`：`start-probe.ps1 -SavedTestGame -WarContext` 加载，默认只观察。`action-roundtrip.request` 改用完整原生构造 RVA 0x975bb0，校验四组参与国数组和句柄，再测试动作深复制及销毁。该版入口硬拒绝所有发送，不能用于接受测试。完整审计见 `work/offer-initializer-audit.md`；尚未游戏内运行。它需要一个没有旧桥接 DLL 的新游戏进程。

warcontext 版完整构造、复制和销毁已实测通过，数组人数2/6/2/6；原生页面对照发现英方 ENG/POR、法方 FRA/AMG/AUV/BOU/FOI/ORL，两种方向列表对调。修复发送测试版为 `eu4_bridge_sender_repaired.dll`，构建命令 `build.ps1 -OutputName eu4_bridge_sender_repaired.dll -EnablePeaceSend`，加载命令 `start-probe.ps1 -SavedTestGame -RepairedSender`。新增双方字段、列表领头国家及命令副本数组独立分配与内容一致性检查，默认只观察，仍必须显式 whitepeace.request 才投递。新 DLL 需新游戏进程，接受结算尚未验证；旧 `-Sender` 仍禁止使用。

修复版接受结算已实测通过：用户接受 FRA→ENG 原生白和平后战争正常结束，停战期至1450年7月，帧回调继续且无崩溃。当前仍只有固定双方白和平；尚未验证原生 AI 接收方或带条款提议。请不要把旧 sender DLL 恢复启用。

## 原生赔款测试版（尚未实测）

当前有效测试版为 eu4_bridge_gold_v2.dll，启动参数仍为 -GoldSender。首版已实测被校验拦截，原因是混淆金额和战争分数单位；未调用金额setter、未投递。v2按原生加号流程把1000分数内部步进换算为金额，再读取上限、裁剪和取整后调用原生setter。条款金额与读回值一致、费用汇总为一档才继续；它们不是同一个单位。v2尚未运行。以下首版“1000为金额输入”的表述应以本段为准。

`start-probe.ps1 -SavedTestGame -GoldSender` 安装 eu4_bridge_gold.dll，默认只观察。gold-roundtrip.request 测试完整战争条约构造、原生金额上限/写入/读回、汇总与副本一致性，然后销毁，不投递。gold-peace.request 通过同一流程投递固定 FRA→ENG 一档要求赔款。金额输入1000为原生内部步进，不是1000金币；实际金币由引擎计算，以玩家通知及结算变化验收。源码不直接写+0xf0。原生费用记录为native_cost_raw，单位仍需页面对照。

新 DLL 安装必须用没有旧桥接DLL的新进程；随后不发送测试与发送可在同一进程完成。需要载入英法仍交战的测试存档，不在已和平的新存档上重新宣战。发送前仍需核对外交冷却。所有请求在首次安装时清除，不自动触发。

赔款v2已实测：原生一档换算金额34400、上限860000、条款setter/getter一致、费用汇总1000、费用函数返回1。带条款提议成功投递、由玩家接受，战争结束，国库整数显示45→11，帧回调继续。精确34.4扣款和保存重载尚未独立验证；不是完整原生AI外交接口。首版赔款的单位错误及未写入停止记录保留于VALIDATION.md。

用户随后保存、重载并推进两周未报告异常，帧日志继续。精确金币变动由存档审计另外核对。

## 原生AI接收方测试（尚未实测）

新进程载入英法仍交战的测试存档，暂停，控制台执行 `tag POR`，令玩家控制葡萄牙、英格兰交还原生AI。使用 `start-probe.ps1 -SavedTestGame -AIRecipient` 安装 eu4_bridge_ai_response.dll。默认只观察；仍使用 whitepeace.request/gold-peace.request 显式发起固定FRA→ENG提议。

该版发送前强制核对玩家POR完整句柄，且玩家不等于FRA/ENG。不会替接收国执行接受或调用强制white_peace效果。首次测试先验证双方AI身份及有效战争、月度冷却，再投递一次。原生预览与投递结果分别记录，实际响应仍需独立验收。不在当前已和平的存档上重新开战。

## 响应记录版（尚未实测）

首次AI接收方提议已发送但战争继续，before/after存档没有明确响应结果。新启动参数 `-AIResponseTrace` 选择 eu4_bridge_ai_response_trace.dll，保留相同发送流程，并在和平动作虚表+0x48增加观察桩。观察桩不写动作、不改原方法参数或返回值，仅保存双方与原始状态后转发；最多64项缓冲由帧线程输出 native_peace_response_entry。它属于进程内hook实验，不是无侵入读取。

需重启并载入llm_ai_peace_before（1445.5.23、玩家POR），安装后先检查response_trace_installed与帧稳定，再显式发送一次白和平。不要只因战争仍在就记录已拒绝，也不要把preview分数当响应。状态含义与完整响应路径尚需实测。实际战争、停战与条款后果仍是接受结算验收项。

## 编译

在项目根目录运行 `work/native/build.ps1`。输出 `eu4_bridge_probe.dll`。本机工具链为 Strawberry 的 x86_64 MinGW GCC；没有游戏业务公共 API 或调试符号。

## 首次实测：只观察

在游戏中另存测试局、关闭控制台并暂停。运行加载器 `inject_probe.py --pid <EU4 PID> --dll <绝对 DLL 路径> --ack-test-save`。加载器验证游戏路径、SHA-256、DLL架构及导出；通过显式 BridgeStart 导出安装 hook。DLL 的 DllMain 不安装 hook。

预期 `probe.jsonl` 出现 `hook_installed`，随后每秒一条 `frame`，其中 `country_valid=true`、`player=ENG`、`thread_changed=false`。帧数随时间上升且线程号保持一致。暂停时也应继续触发；此项尚待实测，不能仅凭入口名字确认游戏线程身份。

先观察至少10秒；没有日志或游戏无响应时不重复加载。`BridgeStart` 非零退出码需根据加载器输出与日志诊断。若 DLL 已加载但安装失败，本次进程也不支持重复尝试；重启测试游戏后再检查。

## 第二阶段：空条约构造/析构

只有线程探针实测通过后，在 DLL 同目录创建空文件 `roundtrip.request`。帧回调在达到100次、国家句柄有效且未检测到线程切换时，消费请求，调用原生默认条约构造函数 RVA 0x2c68c0，校验 vtable 与 owner 回指针，再调用原生非删除析构函数 RVA 0x976030。

预期依次出现 `roundtrip_begin`、`roundtrip_ok`。这是一次明确的原生内存分配/释放测试，尚未运行，不是议和发送。若仅有 begin，则不能视为成功；若 owner 校验失败，需要停止后续构造研究并检查布局。

## 当前边界

- 汇编入口保存 flags、7个易失通用寄存器及 XMM0–5，并提供 Windows x64 调用栈对齐/影子空间与桩的展开元数据；其余非易失寄存器由 C++ ABI 保持。只复制已核对的20字节完整指令，无 RIP 相对指令。
- 安装前收集线程句柄，暂停现有其他线程，检查它们不在将改写的20字节入口内，再复查签名和写入跳转；所有已暂停线程均恢复。不能保证安装时不会新建线程，仍属于实验性 hook。
- 原函数原有异常展开元数据没有为动态 trampoline 单独注册；不把此探针当成成熟可发布 hook 框架。
- 尚未提供 DLL 卸载、原生费用函数、外交发送或模型调用。第二版的外交动作构造/销毁仍待实测；不要将找到的投递地址视作稳定接口。

## 已实测与生命周期第二版

第一版在用户暂停的测试局实测成功：线程16424持续触发，玩家ENG句柄有效，没有线程切换；随后一次roundtrip.request得到roundtrip_begin→roundtrip_ok，帧回调继续且游戏进程保持响应。

新增第二版eu4_bridge_lifecycle.dll，编译命令为 `build.ps1 -OutputName eu4_bridge_lifecycle.dll`，启动命令为 `start-probe.ps1 -SavedTestGame -Lifecycle`。首次安装必须先退出旧测试游戏并重新加载；加载器拒绝同一进程已有任何eu4_bridge_* DLL。不支持热更新。

第二版默认仍只观察；额外记录帧入口this指针及候选投递器链。创建action-roundtrip.request时才构造全新的空条约，填入FRA→ENG双方句柄，调用原生外交动作构造、命令包装和相应析构。它不调用投递器、不评估接受意愿、不改变玩家国家。预期action_roundtrip_begin→action_roundtrip_ok且send=false。本阶段尚待实测。

第二版实测更新：action_roundtrip_begin→action_roundtrip_ok，游戏继续响应。帧入口this并非原生发送所使用的UI根对象，+0x330链不可用，已明确排除。只读扫描议和窗口重新验证原生投递链，并在模块RVA0x2349550找到唯一相同UI根指针。下一版读取该全局，再验证transport虚表+0x30等于本机RVA0x1580270。

## 第三版：固定白和平发送测试

eu4_bridge_sender.dll已编译，启动参数 `start-probe.ps1 -SavedTestGame -Sender`，仍需先退出旧进程再加载测试存档。默认只观察，启动清理所有过期请求；不会自动发送。

加载后创建whitepeace.request，才在已经验证的帧线程上尝试固定FRA→ENG白和平。发送前核对两国句柄、玩家为ENG、投递器指针链及末级方法、原生发送日期保护。构造原生空条约及动作，按原生按钮流程获取线程局部理由缓冲区、重置并保证40项容量，调用预览RVA0x59bf10；按原页面规则在返回值>=1时设置动作内部+0x208标志，再包装并调用RVA0x14ca110。该标志和预览返回值的业务含义尚未完全恢复，不将其称为接受结果。它不切换玩家、不调用white_peace effect或CPeaceOffer::Execute，也不硬编码接受意愿。

预期whitepeace_begin→whitepeace_submitted；submitted仅表示投递器返回true，不等于合法性验证、收到、接受或结算。需要用户观察法国的原生和平通知，并在必要时推进游戏日期。若whitepeace_rejected或whitepeace_not_submitted，不自动重试。当前尚未在游戏中发送测试，AI身份与交战状态仍需结合既有测试存档和原生后续校验确认。

## AI发送有效性诊断版（dispatch_v1）
启动：start-probe.ps1 -SavedTestGame -AIDispatchTrace。需新游戏进程，默认观察、不自动发送。保留响应记录功能；收到whitepeace.request后，在排队前对独立clone调用原生vtable+80方法（RVA59b480），参数与执行器一致：clone/null/0。记录peace_dispatch_preflight，包括native_valid、state_before/after、flag208；返回假、身份不符或状态异常则停止投递，正常销毁未提交对象，不强制返回真。此预检不是排队后执行器的返回记录，条件在执行前可能变化；即使通过也不证明已实际发送或接受。
SHA256=0c031d88df66c87defd9a534928441e3ff49c4bbf88bdd7bb56525ef7081d70c。

## 自动重启游戏
restart-game.ps1 -SavedTestGame：核对唯一EU4进程、完整exe路径和测试版本哈希，保存并复用原启动参数与游戏工作目录；优先关闭游戏窗口，8秒未退出才结束已验证的指定进程，然后正常显示游戏窗口。不会删除存档、重写模组配置或自动发送。当前未保存的测试进度会随重启丢失；仅用于已另存基线的实验。记录work/runtime/game-launch.json便于游戏已退出后重新启动。载入测试存档后由Codex执行诊断DLL安装，不再要求用户手动启动PowerShell。

## 命令执行入口观察版（execution_v1）
启动-AIExecutionTrace。复用单一只读tail-forward观察桩，将槽位改为command vtable1c814b0+48（原方法4e7c80）。本版不安装action响应槽hook；不是同时观察两个入口。记录native_peace_command_execute_entry并保留发送前有效性诊断。回调先验证command，再读取command+50持有的action，原始command参数保持用于尾跳。入口事件只证明执行器进入，不代表校验或结算成功。SHA256=92a44abbf4ea0f6b95050377ca25d610ee793add45c846f33e7d222ba23fbb05。默认观察、清除过期请求，不自动发送。

## 法国原生和平隔离版（peace_lock_v1）
启动-PeaceAuthorityLock，DLL eu4_bridge_peace_lock_v1.dll，SHA230a6a81153d1ce6d2b94113126a87e7aa1421a245437c38465889c9c545105f。在command执行槽4e7c80之前，只有owned action vptr符合已验证和平类1c7b840，且actor或recipient等于当前完整法国句柄时阻止执行。同时阻止请求与全部响应，不猜状态主体，也暂时包括玩家/LLM和平；本版桥接发送编译禁用。其他国家之间的和平及非和平命令原样转发。军事经济AI没有禁用。尚未覆盖其他外交动作、事件脚本直接white_peace/战争结束effects，不能称为全外交锁。
阻止路径恢复寄存器/flags/原始栈后返回，command仍由原调用方释放，hook不自行销毁。记录native_peace_authority_blocked；64项队列饱和后仍继续锁，只有逐条日志停止。既有现成模组仅锁普通declarewar/break_alliance，详见work/native-ai-diplomacy-lock-inventory.md。
这是一版过程内隔离实验，当前不得作为长期AI代理运行：其他外交锁、授权LLM来源及持续日志尚待完成。安装会清除旧请求，不会触发旧赔款试验。
