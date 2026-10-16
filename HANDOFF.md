## 2026-10-16 当前研究检查点：已暂停，整理上传

先读[本次研究进展](docs/research-20261016.md)和[机器摘要](docs/research-20261016/summary.json)。本快照基于上游6092de98，保留原1.37.4历史。1.37.5当前为120绑定、原批次41派发/77拒绝/2未知、48选定效果信号/44历史持久化/42修复候选，完整效果与war/peace执行器尚未完成。

[工具目录v8](docs/runtime-capability-map-1375-v8.json)7入口已有受限验收；最新只证明和平空目标队列与支持继承人双向missing-key，阳性body仍未实机验证。R86/R87完整raw审及root接受已完成；R89仅SOURCE-READY，无actual授权或采集。lookup当前已验v6（60/94/346），v7（61/95）只方案。原始合同的历史pending标签保留，以较新独审和root文件确定接受状态。

源码来源与文档路径替换见[来源表](docs/research-20261016/source-provenance.json)。完整宿主图、进程capture、大型分析、个人配置和构建记录保留本地，缺失依赖必须拒绝，不能重建pin绕过。上传时只做文件验证，没有复跑旧测试、查询或游戏操作。用户要求暂停后续逆向；任何历史成功/派发/未知及未闭合拥有权动作禁止重发。以下是上游历史记录，不是当前进程授权。

# EU4 LLM 外交桥接交接

**窗口模式后台测试增量（2026-10-07）：当前 PID31872 / control v3 / POR / 1445.2.5 / 暂停。** 用户关闭游戏后，助手重启并载入 `llm_control_por_recall_after_20261007.eu4`，自动确认成就提示。配置 fullScreen=no、borderless=no；约5秒测试中前台PID一直为3652，游戏帧3302→3940，后台暂停请求消费成功，日期不变。证据 `work/runtime/windowed-background-control.json` 和 `windowed-before/after.json`。可先在聊天前台继续操作，不需默认每步请求切回游戏；最小化与长时间后台闭环未验收。该进程没有召回模块，不重复注入。

**最新运行状态（2026-10-07 外交官召回）：PID 48184 / control_recall_v5 / POR / 1445.2.5 / 暂停。** 用户布置 POR 外交官0在FRA改善关系，1/2分别4天、8天返回。本轮先原生 autosave 保存现场再重启，安装独立 v5，成功执行 POR 外交官0的原生取消命令：active 2→1，12天返回；日期未推进，另外两名记录完全未变。前后存档的 action 分别 `[2,1,1]`→`[1,1,1]`。召回与保存已验收，12天后空闲及结果重载尚未验收。无待处理请求，不再给本进程重复排召回（一次成功限制），不热替换DLL。v5 SHA256 `E29E17CB419176573C4AE1E7C087D3A38E6261A75705EA028C8A619EF7B2DB39`。证据 `work/runtime/por-recall-v5-validation.json`、`por-recall-save-comparison.json`，详情见 `work/game-control-experiment.md` 最新节。

2026-10-07 游戏控制实验：载入→推进 35 天→原生 autosave→改名→新进程重载的五个步骤已通过，POR / 1445.2.5 / 暂停 / 英法战争关联一致，原有三份自动存档恢复且哈希一致。证据 `work/runtime/control-save-validation.json`（reloaded=true）。当前 PID 30196 / control v3，已暂停。首次推进在载入转换期被暂停状态覆盖，补发后成功；外部编排新增 120 帧等待尚待整轮复跑，不能称为单次无人值守闭环。`savegame` 返回成功却无文件，改用 autosave。v2 曾因过早暂停空指针闪退，v3 就绪检查已实测避免该崩溃。v9 未改动。已继续定位运行中载入链，并严格编译固定 FRA 外交官0原生召回候选 v4，未安装/验收。详见 `work/game-control-experiment.md`。不得继续使用 control v2，不同进程模式不可混装。

更新：2026-10-05。本文件是当前状态入口；`VALIDATION.md` 保存时间顺序的实验记录。旧报告中的推断可能已被后续实验推翻，不以旧标题判断当前能力。

**最新状态：v9 同进程自动宣战→授权白和平已验收。** 固定 DLL SHA256 `1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3`，当前 PID32336/玩家POR。DLL帧线程自动执行正式compiler的FRA→ENG/cb_core/177脚本，ACK applied，快照ai/war/locked均1；自动实验tag FRA→winwars→tag POR后玩家恢复。宣战耗尽空闲外交官，用户推进约一个月后自动提交白和平，授权2执行状态0→2，最终只读英法战争数组均为空。宣战议和之间没有重启。单入口 `tools/run_diplomacy_cycle.py --pid <PID> --test-winwars` 串联并等待门槛；动作入口 `tools/request_diplomacy.py`。详见 `work/automated-diplomacy-v9.md` 和 `work/runtime/v9-cycle-validation.json`。自然战争分接受、保存重载、玩家FRA仍未验收；外部模型服务尚未接入。当前保留v9，不要同进程热替换。

**历史状态：v7 授权赔款已通过原生 AI 接受、金币结算、保存和重载验收。** 英国扣款34.400，法国及五盟友合计入账34.400，双向休战、战争结束、领土不变。结果重载为PID25340，用户确认仍和平；证据见 `work/native-authorized-gold-test.md` 和 `work/runtime/authorized-v7-gold-save-comparison.json`。下方旧进程模式及时间顺序记录为历史。

## 目标和可行性结论

目标：单机玩家与外部 LLM 交流；LLM 决定法国等受控国家的外交和战略，原生 AI 保留军事、经济操作。LLM 应能向玩家及原生 AI 国家发起原生议和，最终取得受控国外交的唯一权限。当前不开发游戏内聊天框。

已经证明本机版本(1.37.4)存在可用的内部控制路径：脚本状态导出、有限动作、原生和平构造/费用/投递/结算，以及原生和平权限拦截均有实测。无需以联机接口作为这些操作的前提。

这还不是完整、稳定的 LLM 对手。部分剩余工作是工程整合，完整外交覆盖、其他条款和信息可见性仍需技术验证。没有公共 SDK、完整游戏源码或跨版本兼容承诺。

## 已验证能力和证据

| 项目 | 实验结论 | 主要证据 |
| --- | --- | --- |
| 脚本快照、有限动作 | 本国状态导出、桥接标记、法国带锁宣战实测；不等于全部外交 API | `VALIDATION.md`、`bridge/README.md` |
| 原生 AI 作战 | 用户确认法国和盟友正常作战；和平锁试验中军队仍正常行动 | `VALIDATION.md`、`work/runtime/native-peace-lock-validation.json` |
| v9 自动宣战与授权白和平 | 玩家 POR；同一进程固定 FRA→ENG `cb_core` 宣战，实验战争分后授权白和平，英法战争数组清空 | `work/runtime/v9-cycle-validation.json`、`work/runtime/v9-cycle-native.jsonl` |
| 对玩家原生白和 | 修复战争参与国初始化后，接受正常结束战争；该次白和曾重载验证 | `VALIDATION.md`、`work/offer-initializer-audit.md` |
| 对原生 AI 白和平 | 玩家 POR、法国/英国非玩家；FRA→ENG 命令进入执行器，状态 0→2，战争结束 | `work/runtime/native-ai-whitepeace-acceptance-evidence.json` |
| 上述白和平保存结果 | 1445.6.9 保存；英法活跃战争 1→0、双向停战；2472 个有主省份所有者无变化 | `work/runtime/native-ai-whitepeace-saved-validation.json` |
| 原生赔款构造/费用 | setter/getter 一致：34400 内部金额，预计 34.4 金币，原生费用 1 战争分 | `work/runtime/native-ai-gold-roundtrip-interference.json` |
| 对玩家国家要求赔款结算 | 玩家接受后战争结束、国库整数显示 45→11；精确扣款和赔款后存档重载未验证 | `VALIDATION.md`、`work/native-gold-setter-audit.md` |
| 法国原生AI议和权限拦截 | 拦截 ENG→FRA 一次、FRA→POR 两次；推进超过一月仍交战、军队正常 | `work/runtime/native-peace-lock-validation.json`、`work/runtime/native-peace-lock-after.json` |

v9 自动白和平实验使用 `winwars` 作为实验战争分夹具，不能代表自然战局下的接受率。v7 白和平和金币赔款的保存重载证据继续保留；v9 保存重载尚未纳入本轮验收。

## 还没有完成的部分

1. **完整外交权限隔离。** 脚本 `llm_diplomacy_locked` 只限制普通 `declarewar` 和 `break_alliance`。原生锁只识别和平 action 类，未覆盖联盟、婚姻、保证等其他外交。事件/脚本直接结算也不是该锁的覆盖范围。
2. **授权通道工程化。** v9 已在原生和平锁保持安装时完成同进程授权白和平，v7 金币赔款路径已有独立保存重载证据。多人、跨版本、其他外交动作及长期运行未验收。
3. **其他条款。** 本轮一次性金币赔款34.4已核对实际结算；持续战争赔款和割地未实现/验收。历史割地是原生竞争和约，不能视为桥接成功。
4. **命令稳定性。** v9 已把空闲外交官和 FRA→ENG 关系冷却纳入运行前检查，并完成一次同进程验收；其他状态和长期运行仍需继续测试。
5. **信息边界。** 本国导出有限；视野内外国信息过滤、战争迷雾、秘密信息不泄露尚未验证。不得直接把完整存档或全部内存交给模型当作公平情报。
6. **模型与外部交流。** 当前实验由 Codex 人工决定请求，没有接通真实常驻 LLM 适配器、自动战略循环或外部聊天产品。没有 API 凭据；Codex/其他 harness 的正式适配未验证。
7. **工程指标。** 长时间运行、多国家、版本适配、失败恢复、操作频率、token 消耗和延迟都没有完整实测。64 项一次性观察队列不适合长期服务。

## 当前进程内模式：AutomatedDiplomacy v9

当前 DLL 为 `eu4_bridge_automated_diplomacy_v9.dll`，SHA-256：

```text
1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3
```

- `work/native/start-automated-diplomacy.ps1 -SavedTestGame` 安装 v9 并检查玩家 `POR`、`FRA`、`ENG` 的原生身份。
- `tools/run_diplomacy_cycle.py --pid <PID> --test-winwars` 串联固定 `FRA→ENG/cb_core/177` 宣战、实验战争分、外交官/关系冷却等待和授权白和平。
- `work/runtime/v9-cycle-validation.json` 记录同进程验收；`both_pair_at_peace=true`、`player_slot=189` 表示英法战争结束且玩家恢复为葡萄牙。
- `tools/request_diplomacy.py` 可单独创建 `declare_war`、`whitepeace`、`gold` 请求。当前没有真实 LLM 服务。

## 历史 v7 进程内模式

最后验收的是 `eu4_bridge_peace_lock_v1.dll`，启动开关 `-PeaceAuthorityLock`。其 SHA-256：

```text
230A6A81153D1CE6D2B94113126A87E7AA1421A245437C38465889C9C545105F
```

- 在 generic command 执行入口核对 command vtable，再识别已经验证的和平 action vtable。
- 用数据库中当前完整 FRA 句柄匹配双方，阻止所有涉及法国的和平请求与响应，不猜状态编号的决策主体。
- 其他国家之间的和平和非和平命令原样转发；原生军事经济 AI 没有被整体禁用，但经济未做独立压力验收。
- 已识别的被锁动作不会因日志字段读取失败或日志队列满而放行。
- 如果法国数据库对象身份读取失败，当前实现会透传；此时不能声称隔离有效。需运行预检与后续健康检查。
- 这是进程内 hook，退出游戏即消失；载入存档不等于卸载 DLL。
- 激活依据是 `peace_authority_lock_installed`。通用 `hook_installed` 行仍可能标注 `observe`，不能单凭它判断业务模式。

当前未验收完整外交隔离，不要将其他未知 action 按和平布局直接封锁。

## 环境与文件

```text
项目：当前仓库根目录
游戏：通过 local.env 的 EU4_GAME_ROOT 指定
用户数据：通过 local.env 的 EU4_USER_DATA 指定
Python：通过 local.env 的 EU4_PYTHON 指定
编译器：通过 local.env 的 EU4_CXX 指定
工具：通过 local.env 的 EU4_OBJDUMP 指定
```

首次运行前复制 `local.env.example` 为 `local.env`，只在本地填写路径；`local.env` 已被 Git 忽略，不应发布。

Windows x64、EU4 1.37.4；游戏 exe SHA-256：

```text
B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77
```

原生代码在 `work/native/probe.cpp`、`frame_stub.S`；构建/加载入口为 `build.ps1`、`start-probe.ps1`、`inject_probe.py`。自动重启为 `restart-game.ps1`。旧 `-Sender` 因曾接受崩溃由 `SEND_DISABLED` 禁用，不要移除保护标记。

DLL 的原生地址全部是 build-specific RVA，必须用当前进程模块基址计算。不要记住 PID 或绝对内存地址；重新枚举进程。自动启动返回的 PID 也可能不是最终游戏进程。

## 安全复现和平隔离

在项目根目录运行。只使用已另存的实验战役，保留正常存档。

1. 有旧 DLL 时，由助手执行自动重启；保持原启动参数，不批量结束同名进程：

   ```powershell
   .\work\native\restart-game.ps1 -SavedTestGame
   ```

2. 用户手动载入交战基线 `llm_ai_peace_before.eu4`，保持暂停；先核对当前 player、双方对象及战争。文件名曾被覆盖，不能认定永远是 1445.5.23；最近使用的基线为 1445.5.30。
3. 由助手执行当前和平锁安装：

   ```powershell
   .\work\native\start-probe.ps1 -SavedTestGame -PeaceAuthorityLock
   ```

4. 检查 `work/native/probe.jsonl` 的 `peace_authority_lock_installed` 与持续帧日志；`country_valid=true`、`thread_changed=false`，另用只读探针验证 FRA 完整句柄。
5. 安装后，用户保持暂停执行 `tag FRA`、`winwars`、`tag POR`，然后推进一个月以上。这是触发原生议和意图的试验，不是自然战争策略评估。
6. 预期：出现 `native_peace_authority_blocked`，战争继续，军事操作正常。不能只凭没有议和就判定发生了拦截。

当前锁的重建命令：

```powershell
.\work\native\build.ps1 -OutputName eu4_bridge_peace_lock_v1.dll -TracePeaceResponses -TraceCommandExecution -PeaceAuthorityLock
```

重建改动后必须重新审查并同步加载器哈希，不能随意取消哈希校验。当前源码已演进；历史发送 DLL 不保证能由当前源码重建出同一哈希，不要重编后继续套用旧验收结论。

同一游戏进程不支持替换/卸载/重复安装 DLL；加载失败也不要同进程反复尝试。换版本需要重启，但同一 DLL 的多次实验不要求每次重启。模组脚本的重载限制与 DLL 限制分开判断。

## 请求、验证与停止

- 发送版曾使用 `whitepeace.request`、`gold-peace.request`；构造检查使用 `gold-roundtrip.request` 等。安装会清除过期请求；仅创建文件不等于已经消费或发送。
- 当前和平隔离版禁用发送，不得继续条款测试。助手负责安装和请求文件，用户不必手动执行 PowerShell。
- 后台游戏帧可能停止。需要用户返回游戏使帧运行，不要把“返回窗口”误写成“必须推进日期”。暂停时能否处理某条完整链路要以日志判断。
- 证据分层：生成请求 → 消费 → 构造有效 → 入队 → 执行入口 → 原生响应 → 战争/条款结果 → 保存 → 重载。不能跳层命名为成功。
- `state_raw=2` 与本次和平成功关联；`state_raw=1` 分支不进入和平执行函数。不要把编号推广到其他外交类。
- 原生金钱条款使用 setter/getter；`offer+0xf0` 是汇总战争分单位，不能直接当金币金额写入。
- 停止原生 hook：退出并重启游戏，不安装 DLL。`run llm_stop.txt` 仅清理模组标记，不卸载原生 DLL。不要调用 FreeLibrary 尝试热卸载。

## 后续优先顺序

1. 保留已验证和平锁；建立其他外交 action 的 vtable、国家字段、生命周期及权限主体清单，逐类扩大隔离。generic wrapper 的公共前缀证据不足以证明所有动作布局相同，也尚未排除军事经济共用该 wrapper。
2. 做明确 LLM 授权通道，验证原生 AI 不会借用授权，外来提议可供 LLM 决定；不能根据相同日期/金额猜测请求来源。
3. 在权限隔离有效时，先复验原生 AI 白和平，再做赔款原生结算/存档/重载，最后割地等条款。
4. 完善公平状态导出和日志协议，再接模型/harness、外部聊天与战略循环，最后测多国家、频率、token 和延迟。

## 阅读索引与交接资产

- 进度和证据：`PLAN.md`、`VALIDATION.md`、`work/runtime/native-peace-lock-validation.json`、`work/runtime/native-ai-whitepeace-saved-validation.json`。
- 权限边界：`work/native-ai-diplomacy-lock-inventory.md`、`work/native-peace-authority-hook-audit.md`。
- 原生结构/通道：`work/offer-initializer-audit.md`、`work/native-gold-setter-audit.md`、`work/native-response-state-branch-audit.md`、`work/native-peace-dispatch-gate-audit.md`、`work/native-peace-queue-audit.md`。
- 把这些报告与代码交给新对话；不依赖旧子代理的聊天记忆。细节有冲突时先核对证据日期，再看本文件状态，未解决矛盾不能自行补成成功。
- 换电脑还需同版本游戏、工具链、已部署 `llm_bridge` 模组与两份实验存档：交战基线 `llm_ai_peace_before.eu4`、和平结果 `llm_ai_whitepeace_accepted.eu4`。它们在项目外的用户数据目录，单独交接并核验内容，不覆盖原件。

## 用户操作偏好与资源事故

不使用电脑/UI 自动化；用户负责载入、暂停、控制台和推进。助手自动重启游戏、安装 DLL、检查日志/存档和生成请求。已授权常规实验操作，不需重复询问每个可逆步骤。

用户允许委派机械/独立工作，但必须限制资源和收尾。2026-10-05 两个子代理遗留的 `pwsh` 全量读取约 350 MB 反汇编，各提交约 9–10 GB 内存，导致换页风暴；已终止，游戏正常。不要重开这些命令。

开始任何内部分析前读 `work/AGENTS.md`：先查大小，超过 10 MB 使用 `rg` 或流式 Python，只反汇编必要函数范围；分析进程提交内存不得超过 1 GB。代理结束前收集或停止其工具 session，不留后台扫描。


## 新对话启动文本

可将以下文字作为新对话的第一条消息，工作目录仍指向本项目：

> 请先读取 HANDOFF.md 和 work/AGENTS.md，再按 HANDOFF 顶部的 v9 状态和证据索引工作。当前入口是 AutomatedDiplomacy v9：玩家 POR，同一进程完成固定 FRA→ENG 宣战、实验战争分和授权白和平；继续验证自然战争分、保存重载、玩家 FRA 及更多外交动作。不要同进程热替换 DLL，不全量读取大型反汇编，不遗留后台进程。不使用 UI 自动化，重启和 DLL 安装由助手完成，载入/控制台/推进由我完成。

## 2026-10-05 授权议和实验增量（未验收）

后续对话已用指定存档参数启动 `llm_ai_peace_before.eu4`。弹出模组成就提示，用户确认后进入暂停地图；只读身份/日期与 POR、1445.5.30 基线一致。`restart-game.ps1` 新增 `-SaveName`，见 `work/save-load-launch-reference.md`。

独立实验源码 `work/native/authorized-probe.cpp`、构建 `build-authorized-peace.ps1`、加载 `start-authorized-peace.ps1`，未替换已验收的旧和平锁。新 DLL 以准确对象地址登记授权，沿已验证 native clone 槽传播，在析构槽撤销；保留未授权法国和平拦截。安装成功，但尚待无提交自检及新组合白和平/赔款验收。详细状态以 `work/native-authorized-peace-experiment.md` 为准，不能把编译/安装成功视为议和成功。

### 授权实验后续失败定位

v1/v2 的授权组合均未验收：v1 经 transport 后对象地址授权丢失；v2 登记协议身份后执行端仍未恢复来源。同一 v2 进程重新 winwars 后 preview=100，但请求仍被锁挡住，不能解释成 AI 拒绝。当前 build/start-authorized-peace.ps1 指向 v3 诊断版，旧已验证和平锁未替换。v3 已安装，未发请求；后续先确认此次重载后 tag FRA → winwars → tag POR，再发送，检查收发 protocol_key/protocol_flags。详见 work/native-authorized-peace-experiment.md 和 runtime/authorized-peace-validation-20261005.json。

### 当前实际运行状态：v5 授权入口通过，结算未通过

当前 start-authorized-peace.ps1/build-authorized-peace.ps1 对应 v5，SHA-256 5A285F642F8D69259BA166C804E0DF6897A31B0BD16F5DB2C6837AB040C37C02。v4 曾安装回滚；v5 安装成功。UI/world dispatcher 的同一 transport 原子序列计数器已只读核对，收到来源 0xffff 时以唯一原生序列号恢复授权，仅用于此次单机实验。winwars 后 preview=100，请求 state 0 到达执行器；其他原生 FRA 议和继续被拦截。用户推进后仍交战、暂无同授权 ID 的 state 1/2，FRA last_sent 未更新；不能宣称和平成功或 AI 已拒绝。证据见 work/runtime/authorized-peace-validation-20261005.json。

已准备接收字段诊断候选 v6，但没有安装或切换加载入口。它增加接收端参与方/owner 原始布局日志，不强制引擎接受；专用构建 build-received-offer-probe.ps1。下一轮应先比较反序列化后的字段，避免继续无证据推进日期。后台停止帧回调会拖住请求消费，但本轮已在前台消费且原生 AI 有新提议，因此后台不是唯一解释。


## 2026-10-05：v7 原生有效性诊断已编译，等待地图

本轮继续自主排查：v5 的只读 AI 队列为空，FRA/ENG 外交消息中未找到双方和平；不等于证明请求从未入队。证据 work/runtime/authorized-v5-pending-queues.json，工具 work/probe_pending_peace.py。v5 完整日志归档为 work/runtime/authorized-peace-v5-executor-entry-no-settlement-20261005.jsonl。

v7 在 v6 字段诊断基础上观察 peace vtable+0x80：原参数调用原生 0x59b480 一次，保留真实返回值，无附加引擎调用。安装/回滚与 clone/dtor 同一事务；自检 preflight 检查改为新槽身份。-Wall -Wextra -Werror 构建通过，SHA256 F989A4DE0BA60C1285907752179DD9626AEA2611ED1A1A42771410BF0952FAD3。独立入口 native/build-validity-observer.ps1、native/start-validity-observer.ps1；普通入口仍为 v5。

已重启独立基线 llm_authorized_winwars_baseline.eu4，当前 PID 48092；尚未安装 v7，等待启动提示关闭及暂停地图。安装成功、自检通过后，必须重新确认 tag FRA → winwars → tag POR，之后才能创建 whitepeace.request。不要以 entry、preview 或编译通过作为有效投递/AI 接受/结算证明。详见 work/native-authorized-peace-experiment.md 最新节。


### v7 后续关键发现

接收有效性实测 true，参与方 2/6/2/6/句柄/owner 正常；初始法国三名外交官全忙（存档 diplomats action=2），0x4e7e09 无空闲时提前退出。用户已召回一名。第二笔已序列化但没有进入执行器；缓冲未满。发现 command vtable+0x40（0x4e8660）还有 FRA→ENG 关系冷却，0x35a860 在外交官检查前设置该冷却。当前 threshold=56463312、current=56463336，已清除。已排队第三笔，等待前台帧及 3 天观察。当前 PID 48092/v7，不需重启或重复 winwars。全部证据和不确定性见 work/native-authorized-peace-experiment.md 最新节；不要声称 AI 拒绝或结算成功。


当前等待点：第三笔 whitepeace.request 仍在 native/ 目录，v7 最后 frame=10486；只有返回游戏才能消费。已向用户请求前台暂停约 10 秒，然后推进 3 天再暂停；尚无回复。当前 v7 实验继续，未关闭或再次重启游戏。v8 只编译未安装，SHA256 63A1DEECD867E258930A4A8D35ACCFBBA4D0C258D6466A6A07118829D5EB1186：在 DLL 源发送端加入空闲外交官和关系冷却的只读前置检查；独立 build-guarded-sender.ps1，下一轮才考虑安装。队列工具已加入这两项检查。


## 最新最终状态（2026-10-05）：授权 v7 白和平已保存/重载验收

authorization=4 同源请求 state0 → 原生响应 state2，preview100、原生有效性 true、完整参与方/owner 正常；游戏日期不变的暂停帧中完成白和平。存档1445.8.3 POR：双向休战、八国全部当天退出战争、八国领土不变。保存文件实际为前导空格+双扩展名，已保留并复制为 llm_authorized_whitepeace_v7.eu4。结果重载成功，用户确认推进几日无异常。

检查脚本 inspect_peace_save.py 已修正：当前战争只看 attackers/defenders，不以历史 participant/persistent 阵营判定；暂停结算保留历史数据，原误判交战1场现正确为0。回归检查通过。详细证据见 work/runtime/authorized-v7-whitepeace-save-validation.json 与 work/runtime/authorized-v7-paused-whitepeace-proof.json。

**当前游戏 PID 5428，运行已验证的 eu4_bridge_peace_lock_v1.dll（发送禁用），无排队请求；不是 v7。** v7 成功日志 work/runtime/authorized-peace-v7-paused-whitepeace-20261005.jsonl 已归档。普通授权 build/start 入口已更新为已验收 v7 与固定哈希 F989A4DE0BA60C1285907752179DD9626AEA2611ED1A1A42771410BF0952FAD3；下轮要 fresh process，禁止热替换/同进程重复注入。

成功前置条件除每次重载后 winwars 外，还有空闲外交官和 FRA→ENG 关系冷却。第一笔无外交官提前退出仍可写关系冷却；第二笔因冷却在命令门槛被阻止。使用 work/queue_guarded_whitepeace.py 做只读前置核对；前台帧必须产生，暂停无需推进日期。v8 已把门槛加入 DLL 发送端并严格编译，但未运行验收；赔款仍未验收。详见 work/native-authorized-peace-experiment.md 最终节。
