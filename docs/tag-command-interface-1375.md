# 指定 TAG 的注入命令接口（1.37.5）

目标是让外部调用者指定发起国、目标国和外交动作，注入模块在游戏主线程执行。发起国可以是 AI 国家。玩家国家不切换，原生 AI 的军事与经济系统继续运行。测试 Mod 只提供测试条件。

2026-10-12 已接通实际通路：CLI／HTTP → 持久请求文件 → 注入宿主 → TAG 解析 → 原生动作工厂 → 合法性检查 → 命令封装 → 游戏发送队列。旧 `/v3/requests` 仍是返回501的合同草案，与本接口分开。

## 命令

```json
{
  "request_id": "my-diplomacy-command-1",
  "actor": "POR",
  "target": "BRI",
  "action": "offer_fleet_basing_rights"
}
```

`actor`、`target` 均为调用者提供的三个大写 ASCII 字符／数字。运行时解析完整国家句柄，不接受内存地址。没有 FRA 固定发起方，也没有“发起国必须是当前玩家”的限制。同一进程创建时间和已加载 session 内，相同 request_id 和内容重复提交只查状态；改变内容会被拒绝。幂等键不会自动跨新进程去重，因此重启后的测试必须先审计历史批次。动作参数超出此宿主已实现合同会被拒绝。

## CLI

```powershell
python -B tools/tag_command.py capabilities
python -B tools/tag_command.py search --query knowledge_sharing
python -B tools/tag_command.py lookup --action ask_for_march
python -B tools/tag_command.py conditions --action offer_vassalization
python -B tools/tag_command.py load --pid <PID> --creation <16位进程创建时间十六进制>
python -B tools/tag_command.py submit --session-file <load生成的session文件> --request-id my-diplomacy-command-1 --actor POR --target BRI --action offer_fleet_basing_rights
python -B tools/tag_command.py status --session-file <session文件> --request-id my-diplomacy-command-1
```

`batch --commands <JSON文件>` 接收命令数组，一次发布整批；每个动作在独立主线程回调执行。开发测试应加 `--test-only`，规则见下方。普通接口调用保留正常动作可用性。未知结果不自动重发。V31 每次进程最多128条命令，V30仍为64条。V31整批共用的绝对期限默认按每条10秒加30秒计算，至少60秒、最多30分钟；每次原生操作前仍核对该期限。加载后的自动暂停不足以发布，必须确认引擎的手动暂停标志。

`--test-only` 始终拒绝历史38项成功动作，禁止复用最终拉通的原120个request_id，并禁止重测已派发、未知或尚未审计闭合的同一动作。换TAG、request_id、构建或session不能绕过这些规则。只有完整文件审计证明此前为正常合法性拒绝、所有权和清理闭合、没有发送或dispatch_intent，才允许使用新request_id做条件修复后的定向测试。原75项full+88干净拒绝中扣除18项历史成功，留下57个修复候选；另2项贸易联盟的稀疏lease拒绝暂不满足证明要求。候选清单不代表当前可用，也不是可发布命令。

`bridge/tag_test_history_1375.json` 保留原拉通关闭台账；`bridge/tag_test_policy.py` 在 `work/runtime/tag-command-development-history-1375` 为新开发尝试创建持久预留，跨session核对原manifest、DLL、请求和完整审计。待领取、已领取、派发及证据不全的预留阻止该动作再次测试。锁残留不会自动清除，测试不会污染普通调用的幂等范围。拒绝或派发均不自动增加历史效果成功数量。

CLI 可用 `--ttl-ms` 指定整批期限，仍受当前宿主上限约束。`capabilities` 返回 `command_fields`、`bindings`、`categories`、`batch_expiry`、手动暂停要求和幂等作用范围；HTTP 使用同一默认批次期限。

加载目标为已另存的可丢弃、非铁人、暂停战役，精确绑定PID和创建时间。宿主加载一次，不热卸载。当前默认 V31 build-7，构建命令为 `python -B tools/build_tag_diplomacy_v31.py --attempt <新目录名>`；不同构建通过 `--manifest` 指定。

## HTTP

设置 `EU4_DIPLOMACY_TOKEN`（16..256个ASCII字符）后运行：

```powershell
python -B tools/tag_command.py serve --session-file <session文件> --port 8774
```

服务仅监听127.0.0.1，请求带 `Authorization: Bearer <token>`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/native/v1/capabilities` | 当前实际动作绑定 |
| GET | `/native/v1/actions?q=knowledge_sharing` | 只读搜索120绑定及27排除标签 |
| GET | `/native/v1/actions/{action}` | 绑定、原生入口与逆向证据 |
| GET | `/native/v1/conditions/{action}` | 只读条件资料，不访问游戏 |
| POST | `/native/v1/commands` | 提交单条上述JSON命令 |
| POST | `/native/v1/batches` | 提交命令数组 |
| GET | `/native/v1/commands/{request_id}` | 查询持久回执 |

202表示已发布，不表示AI接受。状态为 `published`、`claimed`、`dispatched`、`native_rejected`、`not_dispatched`、`publication_unknown` 或 `unknown_no_retry`。`dispatched` 必须有原生正常返回、true值、被消费的命令指针槽及对应TAG绑定回执；它仍不证明外交关系已生效。

发布开始预留或写入持久意图后发生错误，接口返回结构化 `PublicationUnknownError`：HTTP409，CLI输出JSON并以2退出。结果含每条request_id、sequence和 `publication_stage`，保留发布锁与已有意图，`automatic_retry=false`。这些阶段描述文件发布进度，不能推断原生结果；不得从部分失败自动重发整批。开始持久写入前的普通输入/文件错误仍返回原422/404。

## 条件查询

`search` 和 `lookup` 提供147个标签的只读查找；后者区分编译profile与静态目录映射，返回原生RVA和按动作关联的逆向证据。排除项可查询但仍不可提交，CLI无需session。搜索支持分页、类别及bound/excluded过滤，详见[外交行动API查找](tag-action-lookup-1375.md)。

`conditions --action <action>` 不需要session。HTTP条件路由仍使用上述Bearer认证。返回原版脚本和配置中测试Mod的精确条件条款、来源散列及公共原生检查说明；51个普通外交族的local-check索引提供调用和本地化键线索，两个独立宿敌命令单独标注。原版与Mod条款分开，资料散列不匹配时拒绝返回。

这是静态资料查询，`evaluated_in_game=false`、`complete_legality_documented=false`。本地化键可能描述成功、取消或占位文本；引用不能证明实际失败分支。公共full+88还可能在进入local+80前拒绝。查询不能替代当前TAG的实时合法性判断，详见[条件资料与证据边界](tag-command-conditions-1375.md)。

## 当前覆盖与实际证据

当前 V31 宿主有120个仅需 `actor`、`target` 的动作绑定，覆盖盟约、影响、关系、王室、秘密行动、经济、通行权及人情。包括118个普通外交动作（51个原生族、其中39个加载中的脚本定义）和2个独立宿敌命令。机器可读清单为 `bridge/tag_actions_1375_v31.json`，`capabilities` 返回当前宿主实际清单。宣战、议和、省份和复杂参数不在本轮范围。目录中的274项不是本接口的可执行数量。

类别数量依次为盟约17、影响43、关系5、王室9、秘密行动18、经济12、通行权8、人情8。各模式、脚本定义和本轮实际状态见[动作清单](tag-command-actions-1375.md)，由当前编译注册表生成并核对八类目录的147个标签均已列为绑定或排除项。

另有27个目录标签未暴露：省份、第三国、数量／期限、舰队、叛军和侮辱定义选择等参数动作被延期；部分旧取消标签没有核实的原生取消语义，`break_vassalization` 也没有有效原生方向，均不会伪造为可执行入口。完整清单及原因由 `capabilities.excluded` 返回。

同一次最终拉通的120条请求已在三个进程片段中全部记账：41次原生派发、77次条件或预检拒绝、2项未知且禁止重试，没有未进入请求。581次原生调用未记录到SEH异常；其中12次派发的actor为非玩家国家，玩家始终FRA。证据为 `work/runtime/tag31-integration-final-20261013.json`；逐项状态见动作清单。批次完成不表示120项通过，77项拒绝也不能证明各动作发送分支可用。

两项未知分别是旧60秒期限到期的 `ask_military_access` POR→BRI，以及适配器错误拒绝工厂状态的 `abandon_union` BUR→BRB。后者的工厂在+0x34写入2，原适配器期待0；build-7已修正工厂、初始化和clone检查，并补充负向离线检查。该请求没有重发，修正后的发送效果仍未验证。静态证据为 `work/runtime/tag31-abandon-union-state-20261013.json`。

整批完成后保存了 `llm_diplomacy_1375_tag31_final.eu4`，并统一比较31个国家的选定存档字段。可看到保独、军通、五种间谍修正、解除联姻及属国关系等变化；也发现待玩家处理的独立支持提议、无法区分各自效果的开始/停止组合、与预期不一致的部分属国类型。后续冷重载选定状态比较已完成：31国关系/外交官、全局外交记录保持，仅DAN属国计数及其索引发生变化，不推断额外外交效果。详见[拉通结果及未通过项](tag-command-integration-1375.md)。存档差异和选定状态持久化均不等于全部AI接受或120项效果通过。

新DLL已在进程37816／创建时间 `01dd5a40957e7dea` 单次加载成功。请求 `tag30-por-bri-fleet-1` 指定 **POR → BRI** 提供驻港权，玩家仍为 **FRA**。记录确认 `actor_is_human_player=false`、full+88检查true、命令gate true、发送正常true且slot被消费，所有已移交对象退出本地所有权记录。没有调用控制台或切换玩家国家。

这是非玩家国家原生发送的实际证据。BRI接受／关系生效尚未核验，不新增历史效果成功数量。无重新发送。证据位于 `work/runtime/tagcommand30-nonplayer-dispatch-37816.json`。

当前build-7离线验证：C++128组协议、10组Guard模拟内存检查、53组原生扩展合同检查；另有直接编译Guard源的9个到期边界场景。先前相关Python检查88项通过，覆盖传输、HTTP、注册表、暂停、历史审计、续测合并、持久开发测试策略、部分发布失败、条件查询、有界存档解析和7项测试Mod检查。它们不调用实际游戏外交动作。build-7的44个来源pin不含Python backend/service；本次Python改动没有更改DLL或要求重编原生模块。

后续36项定向检查通过，含4项新增索引检查，与前88项重叠；已涵盖92个不同检查，条件资料和动作参考生成器 `--check` 通过。

拉通后测试Mod把普通冷却从0改为-1月份，以处理严格 `current_date > deadline` 的同日边界；既有截止日期不会自动清除。另已定位 `on_dependency_gained` 调用 `convert_special_subject_to_vassal`：发起国缺少特殊政府能力时，会把eyalet、pronoia或文化势力范围属国转为vassal。Mod只把该helper外层limit设为 `always = no`，保留其余helper及原动作on_accept。修正已备份安装。

新进程61988已进入最终存档地图1445.2.16、FRA、手动暂停，39个脚本definition均找到，Mod文件与manifest一致并启用末位，实时普通冷却值为−1。日志仍有其他字体/事件告警，选定unlock/helper/action相关行为空。未加载TAG外交DLL、未发送新请求。冷重载的选定状态已核对，证据 `work/runtime/tag31-cold-reload-20261013.json`；同日冷却和特殊属国修正效果仍未验证。详见拉通记录。

## 历史审计和中断批次

`status` 仍要求当前构建全部源码散列一致。源码更新后可用文件专用的 `audit` 查看旧构建回执：

```powershell
python -B tools/tag_command.py --manifest <旧build.json> audit --session-file <旧session文件> --request-id <原request_id>
```

该入口只核对记录中的manifest、DLL、请求意图、报文和日志，不加载模块、不打开进程、不验证当前源码可执行性。返回 `evidence_only=true` 和 `source_pins_verified=false`；旧构建不会因此获准加载或发送。

`tools/plan_tag_command_continuation.py` 要求完整且终止的日志、既有整批证据和原命令列表一致，才生成待审查的余项文件。只有完全没有日志条目、没有claim文件且原发布报文完好的请求可入选。已领取、条件拒绝、已提交、冻结或未知的请求全部排除；截断日志、残留发布锁、回执变化均拒绝规划。它不自动恢复或发送。

本轮曾分别生成109条和41条未领取余项，均已按审查文件发布一次并完成记账。每次先保存已派发状态，新进程加载该保存状态，保留原request_id；没有回到原基线重发已进入请求。`work/merge_tag31_integration.py` 校验哈希、请求分区和连续片段后合并，不加载游戏，不自动恢复。现在没有可继续发布的余项，原始批次及两个余项文件均不得再次发送。

V29五项人情批次未发送，旧信任字段合同把+40/+44的含义写反，禁止加载该旧批次。新宿主保留原生工厂生成的人情成本与信任增量，并核验clone一致，尚不宣称信任动作的实际效果通过。

完整外交覆盖、各动作的AI接受／实际效果、全部参数族以及对原生AI外交决策的完整接管仍待完成。当前构建为实验接口。
