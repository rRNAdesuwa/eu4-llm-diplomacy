# v9 同进程自动宣战与授权议和

2026-10-05。当前 v9 已完成同一游戏进程内的固定宣战→实验战争分→授权白和平验收，v7 DLL 与入口保留。新 DLL：`eu4_bridge_automated_diplomacy_v9.dll`，SHA256 `1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3`。严格 `-Wall -Wextra -Werror` 编译通过，19 项 bridge 测试通过；运行证据见本文“运行验收”和 `runtime/v9-cycle-validation.json`。

## 合并方案

`authorized-probe-v9.cpp` 基于 v7，保留和平锁、克隆/析构/序列授权传播与原生议和发送；加入 v8 的空闲外交官、FRA→ENG 冷却只读发送前检查。新增 `automated-war.inc` 在同一帧 hook 中消费固定宣战请求，调用原生 run evaluator 执行固定模板。不模拟键盘，不创建外部执行线程调用游戏逻辑。

原生 run 命令注册名称 RVA `0x1d3204c`、注册项 `0x1fc2528`、evaluator 槽 `0x1fc2558` → 函数 `0xe4f040`。此函数检查输入是一个32字节 string 组成的 vector，读取参数 +0x18 capacity，SSO capacity<16 时直接使用字符缓冲。返回对象为1字节成功标记+7字节对齐+32字节原生 string，共40字节；结果 string 由原生 `0x95660` 析构。调用前核对注册槽，参数固定短文件名 `llm_auto.txt`，没有任意命令执行接口。其内部解析脚本并在 `0xe4f449` 调用 effect +0x78，与手工 run 的入口相同。

脚本由正式 compiler 生成，固定 `war_auto_01`、FRA→ENG/cb_core/177；锁、AI、CB、停战、联盟、目标和结果检查均保留。构建时生成头文件，安装前写到配置的用户目录；DLL 调用前逐字节核对文件内容等于编译进 DLL 的模板。DLL 邻接的 `automatic-war-script.path` 仅为本机 UTF16LE 路径配置，已 Git 忽略。

和平自检改为等待确认英法交战后只执行一次。只读判据是 FRA +0x1548 的16字节国家/战争关联数组，数量 +0x1554，首字段国家槽46；已在 v7 手工宣战后的进程只读核对数组包含 ENG 槽46及共同战争对象。这样和平状态安装不会提前耗尽自检机会。未移除原生自检、有效性、preview、费用或外交官门槛。

## 请求入口

### 控制台命令如何自动执行

自动化直接调用游戏内部的控制台命令处理函数（evaluator）。DLL 不打开控制台窗口，也不模拟键盘输入；这些函数是控制台解析命令后实际执行逻辑的入口。命令名称、注册槽和函数地址通过本版本可执行文件的静态逆向定位，调用参数和返回对象布局核对后，再用运行日志与游戏状态变化验收。

| 固定调用 | 注册槽 RVA | 处理函数 RVA | 用途 |
| --- | --- | --- | --- |
| `run llm_auto.txt` | `0x1fc2558` | `0xe4f040` | 执行正式 compiler 生成的固定宣战脚本 |
| `tag FRA` / `tag POR` | `0x1fc5d98` | `0xe6a020` | 实验时临时切换玩家并恢复 |
| `winwars` | `0x1fc45d8` | `0xe61580` | 设置实验战争分条件 |

完整执行链是：Python 写固定请求文件 → DLL 在游戏主线程的帧回调中读取并删除请求 → 核对请求、注册槽及脚本内容 → 构造原生参数 → 调用 evaluator → 读取成功标记并析构返回字符串 → 核对实际游戏状态。主要实现位于 `native/automated-war.inc` 的 `fixed_console_call`、`consume_fixed_request` 和 `automated_war_tick`；帧回调入口位于 `native/authorized-probe-v9.cpp`。

参数使用24字节的原生 vector 布局，元素为32字节原生 string；当前固定参数均可放入16字节内联字符缓冲，capacity=15，避免自行分配游戏字符串堆内存。`winwars` 使用空参数 vector。返回对象为40字节，成功标记之后是原生 string，读取后调用游戏自己的字符串析构函数释放。上述 RVA 都以当前进程的游戏模块基址为起点，只适用于已核对哈希的 EU4 1.37.4 可执行文件。

原生命令返回成功只是第一层证据。宣战还要求脚本 ACK applied、AI/锁快照以及实时英法战争关联确认；实验 tag 操作还要求恢复原玩家完整句柄。议和走既有的原生授权外交发送路径，不调用控制台和平命令；完成判据为授权执行状态0→2以及双方战争关联清空。

游戏暂停时仍能产生帧，因此可以执行上述调用；本机验收要求游戏在前台产生帧。推进日期是另一件事，外交官返回和日期冷却仍需要实际游戏时间，当前由玩家操作。现有接口仅允许固定命令和参数，普通宣战不会执行 tag 或 winwars；`test_winwars` 单独请求且每进程只执行一次，不能证明自然战局的议和接受率。外部 LLM 服务尚未接入，当前由 Python 请求入口驱动。

构建 `native/build-automated-diplomacy.ps1`，安装 `native/start-automated-diplomacy.ps1 -SavedTestGame`，要求玩家POR与固定游戏/DLL哈希，安装不生成请求。换 DLL 需新进程；随后宣战和议和均在该进程中进行。

`python tools/request_diplomacy.py declare_war --pid <当前PID>` 写 `declare-war.request`，固定内容 `FRA ENG cb_core 177 war_auto_01`。帧线程核对、消费并删除后执行；进程内只允许一次宣战调用。ACK 和完整快照来自同一正式脚本，native log 另有 automatic_war_begin / automatic_console_result / automatic_war_runtime_confirmed。

`tools/request_diplomacy.py whitepeace|gold` 复用既有 guarded queue 工具；检查外交官与冷却及自检后写原生议和请求。DLL 中仍有自己的实时门槛，游戏线程会再次核对运行状态。

`test_winwars` 是明确的实验准备请求，单独 token 与文件，普通宣战请求不会执行它。帧线程调用固定原生 tag FRA → winwars → tag POR，核对 player 完整句柄恢复。注册槽分别为 `0x1fc5d98`→`0xe6a020`、`0x1fc45d8`→`0xe61580`，调用 ABI 与 run 相同。该实验提高战争分，不证明自然战局下 AI 会接受议和。任何恢复失败均不能继续发送，必须检查当前玩家。

## 运行验收

已在 `llm_war_v7_before.eu4`（1445.1.1/POR，英法无战争/停战，锁开启）完成运行验收。安装 v9、自动宣战、实验战争分准备、原生授权白和平与战争结束均使用 **PID 32336**；宣战与议和之间没有重启或重新注入。

原生 run 返回成功，ACK `war_auto_01 applied`，快照 ai/war/locked 均为1；只读战争数组确认英法共享战争对象。授权自检随后通过。自动 tag FRA、winwars、tag POR 均成功，完整玩家句柄恢复。宣战消耗了法国最后一名空闲外交官，初次白和平预检明确停止且未写请求；用户推进约一个月后外交官返回，预检通过。白和平 native preview=100、valid=true，授权2在克隆和传输中保留，执行状态0→2。最终只读检查英法两个战争关联数组均为空，玩家槽189/POR，日期 raw=56459208。

证据：`runtime/v9-cycle-validation.json`、`runtime/v9-cycle-native.jsonl`、`runtime/v9-war-pair-before-peace.json`、`runtime/automatic-cycle-settlement.json`。本轮没有保存重载或双向停战存档核验；使用了人工战争分条件，不证明自然战局接受率。玩家法国场景仍未支持，固定实验要求玩家POR、法国AI。

## 单入口串联

安装后运行 `python tools/run_diplomacy_cycle.py --pid <当前PID> --test-winwars`，顺序等待宣战确认、自检、独立实验战争分准备、外交官/冷却门槛、白和平接受，并只读确认战争结束。默认超时900秒；日志已经确认的阶段会跳过，可在同PID恢复。超时保留已排队请求，不取消也不重复发送。游戏需要前台帧；外交官返回需要玩家推进日期。`--test-winwars` 是显式实验选项，不能当作正常LLM外交策略。

该入口整合执行链，尚未接入外部模型服务。普通动作继续使用 `tools/request_diplomacy.py`，不会自动设置战争分；更换 DLL 时使用新游戏进程。
