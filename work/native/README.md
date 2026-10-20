# EU4 1.37.4 原生桥接：当前运行说明

> 本文件下文是 1.37.4 历史说明。当前本机为 1.37.5，先读根目录 `HANDOFF.md` 和 `docs/native-research-1375.md`，不要运行旧地址／旧 DLL。1.37.5 v5 的固定改善关系已经完成保存重载实验；完整外交执行尚未完成。用户已要求后续自动完成测试，旧文中要求其手动控制台／重启的流程不再适用于当前任务。

更新：2026-10-05。先读项目根目录 HANDOFF.md；本文件只给出当前原生模式与操作入口。
旧说明已保存为 README-history-2026-10-05.md，仅作历史追溯，其中“尚未实测”等结论不代表现状。

**最新实验入口为 v9 自动宣战与授权议和。** 使用 `build-automated-diplomacy.ps1` 构建、`start-automated-diplomacy.ps1 -SavedTestGame` 安装。安装要求新进程、玩家 `POR` 和固定实验基线；之后从项目根目录运行 `python tools/run_diplomacy_cycle.py --pid <PID> --test-winwars`，串联固定 `FRA→ENG` 宣战与白和平。游戏需保持前台帧，外交官返回需推进日期。PID 32336 已完成同进程验收，无需重装当前 DLL。详见[运行记录](../automated-diplomacy-v9.md)。下方权限隔离模式保留为历史操作参考。

## 当前能力

- 原生白和平：对玩家和原生 AI 国家均有结算成功证据；AI 白和平保存已核验。
- 原生金钱：构造、费用与玩家接受已验证；AI 接收方结算未验收。原生割地尚未实现。
- v9 当前提供固定 FRA→ENG 宣战、实验战争分和授权白和平；v7 金币赔款保存/重载结果继续保留。
- 当前不是完整外交 API，也没有真实模型接入。
- 旧 `-Sender` 仍由 `SEND_DISABLED` 禁用。

## 当前推荐实验模式：AutomatedDiplomacy v9

在项目根目录执行：

```powershell
.\work\native\start-automated-diplomacy.ps1 -SavedTestGame
$GamePid = (Get-Process -Name eu4).Id
python -B .\tools\run_diplomacy_cycle.py --pid $GamePid --test-winwars
```

该流程在同一进程中完成固定 FRA→ENG 宣战、实验战争分和授权白和平。游戏需要保持前台帧；外交官和关系冷却通过推进日期满足。宣战、和平和金币请求也可由 `tools\request_diplomacy.py` 单独创建。详细步骤和日志解释见 `docs\人工实验与日志读取流程.md`。

## 历史模式：PeaceAuthorityLock

DLL：eu4_bridge_peace_lock_v1.dll。
SHA-256：230A6A81153D1CE6D2B94113126A87E7AA1421A245437C38465889C9C545105F。

它在 generic command 执行入口识别已验证的和平 action 类，匹配当前完整 FRA 句柄后阻止所有涉及法国的和平请求/响应。其他国家之间的和平及非和平命令透传。该版也阻止玩家/LLM 和平，桥接发送编译禁用。

已运行验收：3 次 native_peace_authority_blocked，包括 ENG→FRA 和 FRA→POR；用户推进超过一月仍交战，军队正常行动。经济未做独立压力验收。

边界：其他外交未全部锁；事件脚本直接结算不在该锁范围；法国数据库身份读取失败时会透传。必须核对运行预检，不能据此宣称法国外交永久被完全接管。

## 操作

在项目根目录执行。助手负责脚本，用户手动载入/暂停/控制台/推进；不使用 UI 自动化。

```powershell
# 换 DLL 必须新进程；保留原启动参数。
.\work\native\restart-game.ps1 -SavedTestGame
# 用户载入交战基线并暂停后：
.\work\native\start-probe.ps1 -SavedTestGame -PeaceAuthorityLock
```

启动时会清理过期请求，不会自动发起外交。预期 probe.jsonl 有 peace_authority_lock_installed、持续帧日志，以及发生和平尝试时的 native_peace_authority_blocked。通用 hook_installed 行可能仍写 observe，以专用事件判断权限锁是否激活。

DLL 没有热卸载/替换。加载失败也不要同进程重试；退出并重启、不要安装 DLL，即恢复无原生 hook。run llm_stop.txt 只清理模组标记，不能卸载 DLL。载入存档不会卸载 DLL。

当前锁的编译命令：

```powershell
.\work\native\build.ps1 -OutputName eu4_bridge_peace_lock_v1.dll -TracePeaceResponses -TraceCommandExecution -PeaceAuthorityLock
```

修改和重编后须重新审查并同步加载器哈希。当前源码已演进，历史 DLL 不保证能从当前源码重建相同哈希；不要只取消加载器检查。

## 历史实验入口

这些是复现实验用模式，不是应当随时运行的生产接口。当前优先验收权限隔离，不继续条款测试。

| 开关 | 用途与边界 |
| --- | --- |
| -RepairedSender | 固定 FRA→玩家 ENG 白和平；修复完整战争上下文 |
| -GoldSender | 固定 FRA→玩家 ENG 一档原生赔款 |
| -AIRecipient | 固定 FRA→AI ENG，要求玩家 POR；只看入队不证明执行 |
| -AIResponseTrace | 观察和平 action 响应入口；状态语义需与实际结果对照 |
| -AIDispatchTrace | 记录发送前原生有效性；不证明排队后执行 |
| -AIExecutionTrace | 观察 generic command 执行入口，已用于 AI 白和平成功实验 |
| -PeaceAuthorityLock | 当前和平隔离版，禁用发送；其他外交未锁 |

whitepeace.request / gold-peace.request 曾供发送版使用；gold-roundtrip.request 仅构造检查。文件存在、消费、构造成功、入队、执行、接受、保存、重载是不同证据阶段。

## 内部代码与证据

- probe.cpp、frame_stub.S：帧线程业务与原生槽观察/拦截。
- inject_probe.py：版本、路径、架构、导出和已加载模块检查；DllMain 不安装 hook。
- ../probe_native_state.py：只读身份/句柄/日期证据。
- ../inspect_peace_save.py、../verify_whitepeace_save.py：只读保存结果核验。
- ../runtime/native-ai-whitepeace-saved-validation.json：AI 白和平保存验收。
- ../runtime/native-peace-lock-validation.json：和平锁验收。
- ../native-peace-authority-hook-audit.md：拦截与泛化边界。

全部 RVA 仅适配已经核对哈希的本机 EU4 1.37.4，必须加实际模块基址。PID 需重新枚举，不沿用旧进程号。

开始内部分析前读 ../AGENTS.md。禁止全量 Get-Content 大型反汇编或遗留后台扫描；2026-10-05 已发生双 pwsh 近 20 GB 内存事故。先查文件大小，按函数范围反汇编，流式搜索，跟踪和收尾工具 session。
