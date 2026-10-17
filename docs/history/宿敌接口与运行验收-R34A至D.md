# 宿敌接口与运行验收

更新日期：2026-10-16。本文面向需要读取或调用 EU4 外交接口的人类开发者和 AI 调用者，说明 R34D 已交付的宿敌（Rival）查询、FRA 授权负例和非 FRA 转发观察，也保留 R34A/R34B 的历史证据与字段定义。

## R34D 当前查询与授权边界

R34D 在 `llm_ai_whitepeace_accepted.eu4` 的和平上下文中运行。POR（葡萄牙）是玩家，FRA（法兰西）是桥接控制国，游戏在查询和授权测试期间保持暂停，边界日期为 1445.6.9/raw `56462016`。安装进程是 PID `45680`、session `45680-1dd5ccbe10d5b6e`，DLL SHA-256 为 `6816c581d45fa89b7db6225ede5a7cb67cc047383d280931697a8881f1678fc8`；载入存档 SHA-256 为 `e0f6be661621272102dd02576ae29a20011f78b076e40d17d769fbc1378de8f0`。

操作器对 BUR（勃艮第）、ENG（英格兰）、CAS（卡斯蒂利亚）和 SAV（萨伏依）分别查询 `set_rival` 与 `remove_rival`。结果如下：

| 目标 | `rival_active` | `set_rival` 原生条件 | `remove_rival` 原生条件 | 诊断或费用 |
| --- | ---: | ---: | ---: | --- |
| BUR 勃艮第 | `false` | `false` | `true` | Remove 原始外交点费用 `101`；成员关系读取仍为非成员 |
| ENG 英格兰 | `true` | `false` | `false` | Remove 保留至 1449.11.11 |
| CAS 卡斯蒂利亚 | `true` | `false` | `false` | Remove 保留至 1449.11.16 |
| SAV 萨伏依 | `false` | `false` | `true` | Remove 原始外交点费用 `101`；候选资格为 `false` |

FRA 的 `diplomatic_power_raw=143`、`rival_count=3`、`max_rivals=3`，并且 `at_war=false`。八项查询均确认目标存在、成员关系可读、原生条件函数确实被调用；`relationship_state.rival_active` 与 `native_command_validity` 各自描述不同对象。Remove 的 `diplomatic_power_cost_raw=101` 和 `affordable=true` 已导出，费用单位、附加费用以及完整执行前规则仍由 `full_rules_complete=false` 明确标记为尚待补齐。Rival 是 FRA 持有的单方关系，因此 `acceptance.applicability=not_applicable`。

[R34D 八项查询报告](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/rival-queries-84f4d795e9224165a591235b860d5229/report.json)通过新进程、POR 玩家槽位、暂停日期、四份快照、native event slice、DLL/build/session 绑定和无副作用检查。查询没有发布外交业务请求，也没有把原生对象指针或句柄放入公开结果。

下面的命令查询当前 D 进程的 1445.7.14 状态；上表保存的是推进日期之前的 1445.6.9 结果。`--recipient` 和 `--expected-rival` 都可以重复：

```powershell
python work/run_rival_queries.py `
  --installation work/runtime/diplomacy-query-20261016-r34-rival-d-peace/installation.json `
  --expected-date-raw 56462856 --require-ui-candidates `
  --recipient BUR --recipient ENG --recipient CAS --recipient SAV `
  --expected-rival BUR=absent --expected-rival ENG=active `
  --expected-rival CAS=active --expected-rival SAV=absent
```

### R34D 的未授权入口和非 FRA 转发

[R34D 授权负例报告](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/rival-authority-test-53d055de8a5c407a98e5270e8c1a4dd8/report.json)只发布一次 `RIVAL_GUARD_TEST1` 请求，覆盖 `set_rival`、`replace_rival`、`remove_rival` 的 direct 和 vtable 入口。六条原生命令记录均为 `allowed=false`、`reason=FRA_SUBMISSION_UNAUTHORIZED`、`canonical=true`、`shape=true`；原生测试的 before/after 状态相同，且没有业务执行事件。

随后 35 天的 [生命周期观察](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/lifecycle-observation-5ca7f6c019324be3b636e832acbe55a5/observation-report.json)到达 1445.7.14/raw `56462856` 并再次暂停。观察到 `ENG→CAS`、`TAH→AGG`、`ENG→DAN`、`MUL→SRH`、`KSH→MUL` 五条非 FRA `set_rival` 命令；五条命令均为 `allowed=true`、`canonical=true`、`shape=true`。随后[流式存档后果报告](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/npc-rival-save-effects-20261016-001/report.md)及[结构化证据](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/npc-rival-save-effects-20261016-001/evidence.json)确认五个 actor 的 `rival.country` 都新增了对应目标：ENG 新增 CAS/DAN，TAH 新增 AGG，MUL 新增 SRH，KSH 新增 MUL；FRA 的直接宿敌仍为 ENG、ARA、CAS，成员和日期没有变化。这说明非 FRA 来源继续沿用原生处理路径并产生了 NPC 宿敌成员变化；观察本身没有提交 FRA Rival 业务动作。

观察阶段生成了 [存档观察报告](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/save-observer-report-1792086435528801700.json)，保存的 `llm_diplomacy_rival_authority_observed_20261016_r34d.eu4` SHA-256 为 `092af9ef02b8d2fede03d3155fee3b8746a26273c2b189d70eba8bf47b35d5fe`。该存档仍需在新进程中完成 Rival 查询重载验收。

[R34D 七家族十四项回归](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/family-query-regression-e42fa13fca5e42c692e268daa2546a46/report.json)通过；common14 仍为十四项真实执行路径。下一项运行工作是准备一个同时满足国家命令、传输协议、授权和保留期限的正向场景，接通 Rival 业务提交、结果事件和保存重载；完成这些环节前，Rival 查询能力不增加 common14。

## R34B 历史候选查询

R34B 在新进程 PID `17152`、session `17152-1dd5cc7d790cfab` 中运行，POR（葡萄牙）是玩家，FRA（法兰西）是查询 actor，游戏保持暂停，raw 日期为 `56465136`。查询结果分为两组：

| 目标 | 国家全名 | 目标存在 | `candidate_eligible` | `rival_active` |
| --- | --- | ---: | ---: | ---: |
| BUR | 勃艮第 | `true` | `true` | `true` |
| ENG | 英格兰 | `true` | `true` | `true` |
| HAB | 奥地利 | `true` | `true` | `false` |
| CAS | 卡斯蒂利亚 | `true` | `true` | `false` |
| SAV | 萨伏依 | `true` | `false` | `false` |
| GEN | 热那亚 | `true` | `false` | `false` |
| LAN | 佛罗伦萨 | `true` | `false` | `false` |

所有 R34B 查询还返回 `ui_war_allowed=false`、`native_command_validity=false` 和 `full_rules_complete=false`。其中候选资格回答“目标是否进入候选路径”，宿敌成员状态回答“目标是否已经在 FRA 的宿敌列表”，原生命令条件回答“当前 Set/Remove 条件是否通过”；三者不能互相替代。`full_rules_complete=false` 表示完整费用与执行前规则验收仍待补齐，不能把候选资格当作完整合法性证明。

[R34B 正向候选报告](../work/runtime/diplomacy-query-20261016-r34-rival-b/rival-queries-c5765830ea7b4459b39bb79e78e3229e/report.json)和[R34B 反向候选报告](../work/runtime/diplomacy-query-20261016-r34-rival-b/rival-queries-8316ea7151874f31992d4ccf3f188e22/report.json)均通过新进程、暂停日期、四份快照、native event slice、DLL/build/session 绑定和无副作用检查。两组查询沿用 B 进程已经安装的 DLL，读取前后的日期和外交状态相同。

R34B 的批量候选查询命令如下：

```powershell
python work/run_rival_queries.py `
  --installation work/runtime/diplomacy-query-20261016-r34-rival-b/installation.json `
  --expected-date-raw 56465136 `
  --recipient BUR --recipient ENG --recipient HAB --recipient CAS `
  --recipient SAV --recipient GEN --recipient LAN `
  --expected-rival BUR=active --expected-rival ENG=active `
  --expected-rival HAB=absent --expected-rival CAS=absent `
  --expected-rival SAV=absent --expected-rival GEN=absent --expected-rival LAN=absent
```

后续执行实验可参考[和平基线准备报告](../work/runtime/r34-rival-peace-baseline-20261016-004/report.md)：`llm_authorized_whitepeace_v7.eu4` 仍有 FRA 现役战争，不适合作为和平基线；`llm_ai_whitepeace_accepted.eu4` 没有捕获 FRA 现役战争，且 `last_war_ended=1445.6.3` 早于存档日期 `1445.6.9`，可作为候选上下文。旧存档只用于准备上下文，不替代 R34B 运行证据。

## 1. 国家角色和当前结果

实验存档中的玩家是 POR（葡萄牙）。统一桥接接口控制 FRA（法兰西），由 FRA 查询或发起外交动作。本文中的 ENG 是英格兰，ARA 是阿拉贡，BUR 是勃艮第，HAB 是奥地利。

FRA 当前的三个宿敌来自流式存档成员列表：ENG（1444.11.11 起）、ARA（1444.11.11 起）和 BUR（1444.11.15 起）。R34A 用 BUR、ENG 和 HAB 做了三组对照，每个目标各查询 `set_rival` 与 `remove_rival`，共六项查询：

| 目标 | 国家 | `rival_active` | `rival_since_date_raw` | 查询结果 |
| --- | --- | ---: | ---: | --- |
| BUR | 勃艮第 | `true` | `56457072` | 成员状态可读，Set/Remove 当前原生条件均为 `false` |
| ENG | 英格兰 | `true` | `56456976` | 成员状态可读，Set/Remove 当前原生条件均为 `false` |
| HAB | 奥地利 | `false` | `-1` | 非成员状态可读，Set/Remove 当前原生条件均为 `false` |

查询边界的游戏日期为 1445.10.17/raw `56465136`。FRA 的 `rival_count=3`、`max_rivals=3`、`diplomatic_power_raw=162`、`at_war=true`。这些字段描述原生动作条件看到的当前环境；`relationship_state.rival_active` 单独描述目标是否已经在 FRA 的宿敌列表中。例如，BUR 和 ENG 已经是宿敌，但本次 `remove_rival` 条件仍返回 false。读取成员关系和判断当前动作是否可用是两个独立步骤。

R34A 查询属于只读路径。查询过程保存四份边界快照，读取当前会话，发送 Query1 检查请求，再按 session、动作、目标和 raw 日期复制 native 事件。查询没有提交外交业务请求，也没有推进日期、保存游戏或安装 DLL。R34A 的六条 native 事件全部与公共查询结果对应。

## 2. 统一接口

宿敌动作沿用外交目录的两个动作 ID：

| 动作 ID | 作用 | 阶段 | 参数 | 接受度 |
| --- | --- | --- | --- | --- |
| `set_rival` | 查询或将目标登记为 FRA 的宿敌候选 | `initiate` | `{}` | `not_applicable` |
| `remove_rival` | 查询或移除 FRA 的宿敌关系候选 | `initiate` | `{}` | `not_applicable` |

当前阶段已经接入 `inspect_diplomatic_action` 查询。查询调用明确写出 actor、recipient、phase 和 parameters：

```python
set_result = api.inspect_diplomatic_action(
    "set_rival", "FRA", "BUR", phase="initiate", parameters={}
)
remove_result = api.inspect_diplomatic_action(
    "remove_rival", "FRA", "BUR", phase="initiate", parameters={}
)
```

`set_rival` 和 `remove_rival` 的查询结果属于 `family="rival"`。FRA 是单方关系的拥有者，BUR、ENG、HAB 等目标国家不会返回一项需要对方选择的接受度分数。因此结果中的 `acceptance` 明确写为：

```json
{
  "applicability": "not_applicable",
  "prediction_available": false,
  "complete": true
}
```

当前公开结果的日期位于 `session.date_raw`。native 事件自身还保存 `date_raw`，操作器会分别核对这两个层次：公共结果确认接口使用的会话日期，native event slice 确认原生事件发生在相同日期和 session。公共结果也不会导出 native 指针、对象地址或句柄。

## 3. 重要输出字段

| 字段 | 读取对象 | 解释 |
| --- | --- | --- |
| `family`、`action_id`、`actor`、`recipient`、`phase` | 公共查询结果 | 确认结果属于 Rival family，并确认动作、国家和阶段没有串用 |
| `session.status`、`session.date_raw` | 当前游戏会话 | `status="ready"` 表示会话健康；`date_raw` 是公共日期来源 |
| `relationship_state.rival_active` | FRA 的宿敌列表 | `true` 表示目标已登记为宿敌，`false` 表示当前列表没有目标 |
| `relationship_state.rival_since_date_raw` | 宿敌列表节点 | 目标成为宿敌的原生日期；非成员以 `-1` 表示 |
| `rival_count`、`max_rivals` | FRA 国家对象和原生上限 | 当前成员数量及可容纳的最大宿敌数量 |
| `native_command_validity_called` | 原生 Set/Remove 函数 | `true` 表示本次查询确实调用了对应原生条件函数 |
| `native_command_validity` | 原生 Set/Remove 函数返回值 | 表示当前环境下对应动作条件是否通过 |
| `diplomatic_power_raw`、`at_war` | 原生条件检查读取值 | 外交点原始整数和 FRA 当前战争状态 |
| `legality.status`、`legality.reasons` | 公共规则投影 | 说明当前动作条件结果；R34A 仍保留原生规则覆盖范围 |
| `candidate_eligibility_available` | UI 候选查询 | R34A 为 `false`，候选列表尚未接入公共结果 |
| `full_rules_complete` | UI 规则覆盖 | R34A 为 `false`，表示完整 UI 条件仍待补齐 |
| `submitted` | 查询结果 | R34A 为 `false`，表示查询没有创建业务提交 |

本次 FRA 的 `at_war=true`，Remove native event 还保存了非空诊断十六进制字符串。静态规则报告确认 Remove 函数能够处理战争、宿敌保留期限和外交点数条件；`eu4_escape` 已将该诊断解码为“不能在战争期间移除宿敌”，公开 `queries.json` 的 `native_diagnostic.text` 保留这一可读原因。

## 4. 批量只读查询

操作器 `work/run_rival_queries.py` 支持多个目标。`--recipient` 可以重复，`--expected-rival` 用于声明每个目标的关系状态预期：

```powershell
python work/run_rival_queries.py `
  --installation work/runtime/diplomacy-query-20261016-r34-rival-a/installation.json `
  --expected-date-raw 56465136 `
  --recipient BUR --recipient ENG --recipient HAB `
  --expected-rival BUR=active `
  --expected-rival ENG=active `
  --expected-rival HAB=absent
```

操作器会在安装目录旁创建新的 artifact，并写入：

- `probes/`：查询前的四份边界快照；
- `queries/<TAG>.json`：该目标的 `set_rival` 与 `remove_rival` 公共结果；
- `queries.json`：本次目标集合的聚合结果；
- `native-events-slice.jsonl`：从本次查询起点复制的 bounded native 事件；
- `report.json`：检查、来源、DLL、session 和结果摘要。

操作器将成员状态检查、原生动作条件检查和完整 UI 规则覆盖分别记录。`full_rules_complete=false` 不会使关系状态查询失效，也不会被解释成已经完成完整合法性判断。R34A 的查询报告通过后，操作器仍保持 `execute_call_count=0`、`business_submission=false`、`advance_requested=false`、`save_requested=false` 和 `installation_requested=false`。

## 5. 历史 R34A 验收结果

[R34A 宿敌查询报告](../work/runtime/diplomacy-query-20261016-r34-rival-a/rival-queries-e2be4ced4a634febbebbc63c5cd121f7/report.json)通过以下检查：

- POR 玩家、游戏暂停、日期 raw `56465136` 和新进程健康状态；
- 安装声明、build manifest、载入 DLL 和查询 session 的 SHA-256 绑定；
- BUR、ENG、HAB 六项 set/remove 查询与预期成员状态；
- 六条 native `native_rival_inspection` 事件各出现一次，动作、目标、日期和 session 相符；
- `rival_count`、`max_rivals`、`diplomatic_power_raw` 为整数，`at_war` 为布尔值；
- 接受度明确为 `not_applicable`，公开结果不包含指针类字段；
- 查询没有执行、推进、保存或安装动作。

[七家族十四项查询回归](../work/runtime/diplomacy-query-20261016-r34-rival-a/family-query-regression-a80b3fa3e1914451bb5096754525de0b/report.json)在同一 POR、暂停、日期和 DLL 环境中通过。该回归确认本次 Rival 查询接入没有改变既有七个外交家族的查询结果。

## 6. 历史 R34A 边界和后续验收

R34A 交付的是关系状态与原生动作条件的只读查询。宿敌执行尚未接入，因此 `execute_diplomatic_action` 目前不能用来创建 `set_rival` 或 `remove_rival` 的业务请求；R34A 也没有保存宿敌执行结果或进行宿敌重载验收。

下一阶段按以下顺序推进：

1. 接入 `possible_rival_entry` 候选列表和四参数候选谓词，导出目标资格与完整 UI 规则。
2. 分别核对 Set、Replace、Remove 的构造、复制、序列化和提交参数；Replace 使用的旧宿敌句柄不能被隐藏在 Set 的空参数合同中。
3. 为 FRA 建立授权执行、native result、关系后果和资源变化的统一接口。
4. 保存成功结果，在新进程中重新查询宿敌成员和动作条件，并运行有区分力的未授权入口测试。

R34A 的查询能力没有增加常用外交的已实际执行计数。当前 common14 仍表示十四项常用外交已经完成真实执行路径；宣战、设置／移除宿敌、提议／取消附庸仍待完成，十九项议和和统一长期运行也继续按项目目标推进。

## 7. 证据索引

- [R34D 八项查询结果](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/rival-queries-84f4d795e9224165a591235b860d5229/report.json)
- [R34D FRA 授权负例](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/rival-authority-test-53d055de8a5c407a98e5270e8c1a4dd8/report.json)
- [R34D 七家族十四项回归](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/family-query-regression-e42fa13fca5e42c692e268daa2546a46/report.json)
- [R34D 生命周期观察](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/lifecycle-observation-5ca7f6c019324be3b636e832acbe55a5/observation-report.json)
- [R34D NPC 宿敌存档后果](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/npc-rival-save-effects-20261016-001/report.md)
- [R34D 存档观察](../work/runtime/diplomacy-query-20261016-r34-rival-d-peace/save-observer-report-1792086435528801700.json)
- [R34A 查询结果](../work/runtime/diplomacy-query-20261016-r34-rival-a/rival-queries-e2be4ced4a634febbebbc63c5cd121f7/report.json)
- [七家族十四项回归](../work/runtime/diplomacy-query-20261016-r34-rival-a/family-query-regression-a80b3fa3e1914451bb5096754525de0b/report.json)
- [R34 原生宿敌规则](../work/runtime/rival-rules-20261016-001/report.md)
- [R34 流式存档基线](../work/runtime/r34-rival-save-baseline-20261016-001/report.md)
- [R34 宿敌识别复核](../work/runtime/rival-identification-20261016-root-review-001.md)
- [R34A 阶段状态](../work/runtime/r34-progress.json)
