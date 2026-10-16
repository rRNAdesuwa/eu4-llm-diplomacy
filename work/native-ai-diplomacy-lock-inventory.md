# 法国原生 AI 外交锁盘点（EU4 1.37.4）

审计范围：本仓库 `llm_bridge` 生成/源文件、已部署的
`EU4_USER_DATA\mod\llm_bridge`，以及
`EU4_GAME_ROOT` 的脚本、defines 和相关原生接口说明。
本报告只做静态盘点，没有联网，也没有改动原生 probe 或游戏安装。

## 结论先行

当前 `llm_diplomacy_locked` 是一个国家 flag，**实际只阻止法国作为行动者走旧外交动作 `declarewar` 和 `break_alliance` 的正常动作入口**。它没有覆盖法国的其他外交动作、原生 `requestpeace`、原生 AI 主动议和/接受，也没有覆盖事件或脚本 effect 直接发起/结束战争的路径。军事和经济 AI 没有被该模组代码改写；当前锁属于很窄的外交动作门禁，不能称为“法国外交全禁”。

## 锁标志、生成脚本和已部署文件

| 位置 | 关键字段/行为 |
|---|---|
| `work/install.py:14-29` | 从原版 `common/diplomatic_actions/00_diplomatic_actions.txt` 读取文本，只对 `('declarewar', 'break_alliance')` 各插入同一个 `condition`。安装器没有修改 `common/new_diplomatic_actions`、和平条款或 defines。 |
| `mod/llm_bridge/common/diplomatic_actions/00_diplomatic_actions.txt:91-96` | `declarewar` 条件：`potential = { has_country_flag = llm_diplomacy_locked }`，但 `allow = { NOT = { has_country_flag = llm_diplomacy_locked } }`，所以带 flag 时该动作无效。 |
| 同文件 `:771-776` | `break_alliance` 使用同一 `potential/allow` 门禁。 |
| `bridge/compiler.py:18-20,152-161` | 外部白名单只有 `snapshot`、`lock_diplomacy`、`unlock_diplomacy`、`improve_relations`；锁/解锁只设置或清除 `llm_diplomacy_locked`，没有逐动作的额外覆盖。 |
| `EU4_USER_DATA\llm_bootstrap.txt:1` | `FRA = { set_country_flag = llm_bridge_enabled set_country_flag = llm_diplomacy_locked ... }`，启动时直接给法国加锁。 |
| 同目录 `llm_stop.txt:1` | 清除 `llm_bridge_enabled` 和 `llm_diplomacy_locked`。 |

已部署模组的 descriptor 是 `EU4_USER_DATA\mod\llm_bridge.mod`，声明 `supported_version="1.37.4"`；`dlc_load.json` 已启用 `mod/llm_bridge.mod`。部署目录共 9 个脚本/本地化文件；repo 与部署副本的 6 个关键脚本（外交动作、new actions、peace treaty、scripted effect、on_actions、事件）SHA-256 均一致。对部署目录搜索 `llm_diplomacy_locked` 只有两处 action 条件和一处快照日志（`common/scripted_effects/llm_bridge.txt:14-15`），没有和平、new action 或 defines 条件。

`common/on_actions/00_on_actions.txt:2046-2049` 只把 `llm_bridge.1` 加到月度脉冲；`events/llm_bridge.txt:9-10` 限制为 `tag = FRA ai = yes has_country_flag = llm_bridge_enabled`，事件只调用快照日志效果。没有军队、预算、建造、收入、外交 AI 权重等修改，因此在静态范围内保留军事和经济 AI。

## 覆盖矩阵

| 法国 AI 路径 | 当前覆盖 | 证据和边界 |
|---|---:|---|
| 普通外交界面的宣战（`declarewar`） | 有，限正常 action 入口 | `00_diplomatic_actions.txt:91-96`。只检查行动者 ROOT 的法国 flag；事件/脚本直接宣战不是这段条件。 |
| 普通外交界面的断盟（`break_alliance`） | 有，限正常 action 入口 | `:771-776`。不能据此覆盖所有 effect 调用。 |
| 其他旧外交动作：结婚、联盟、保证、威胁、军事/舰队通行、赠礼、侮辱、间谍、贸易、附庸/吞并/整合、干涉战争等 | 无 | 原版旧动作文件列出动作清单 `common/diplomatic_actions/00_diplomatic_actions.txt:21-86`，锁条件只插在上表两个 block。 |
| `common/new_diplomatic_actions` 中的原生/自定义动作 | 无统一锁 | 该文件另有 `static_actions` 注册表；当前模组 `01_llm_bridge.txt` 只定义两个测试动作，未引用 `llm_diplomacy_locked`。 |
| 原生 `requestpeace`/和平窗口主动提议 | 无 | `common/new_diplomatic_actions/00_diplomatic_actions.txt:3-6` 仅将 `requestpeace` 注册为 static action；旧外交动作文件也只在注释清单列出 `requestpeace`（`:21-24`），没有可插入的脚本 block。 |
| 原生 AI 主动求和、对提议接受/拒绝 | 无 | 和平 AI 计算由引擎及 `PEACE_*`/`PEACE_TERMS_*` 参数驱动；当前 flag 没有响应/提议队列条件。 |
| 事件或脚本 effect 直接宣战/断盟 | 无保证 | 原版存在 `declare_war`/`declare_war_with_cb` 直接调用，如 `events/disaster_ming_crisis.txt:229-237`、`:263-271`；也有 `break_alliance` effect，如 `events/FlavorFRA.txt:2224-2228`、`common/government_reforms/02_government_reforms_republics.txt:617-720`。这些不是 `declarewar` action block 本身。 |
| 直接 `white_peace = TAG` 结算 | 无锁 | 原版事件和和平条款效果直接使用 `white_peace`，如 `events/flavorBYZ.txt:3020-3023`、`common/peace_treaties/00_establish_trade_protectorate.txt:31-40`；它是立即结算 effect，不是提议/接受阶段。 |
| 军事、经济 AI | 保留 | 模组只有外交条件、外交测试动作、日志/变量导出和月度快照；没有改 `NAI` 预算或军事行为字段。 |

“有”仅表示带 flag 时对应脚本 action 的 `allow` 会失败；不表示所有战争或事件来源都被拦截。

## 和平与自定义外交动作的实际能力

原版 `common/new_diplomatic_actions/00_diplomatic_actions.txt` 的模板（`:62-175`）明确提供：

- `require_acceptance`：是否给接收方拒绝选项；
- `is_visible`、`is_allowed`：自定义动作的显示和可用条件；
- `on_accept`、`on_decline`：接受/拒绝后的脚本 effect；
- `ai_acceptance`：接收方 AI 的接受评分；
- `ai_will_do`：发起方 AI 是否想提出该自定义动作。

同一模板第 62 行写明“AI will currently never send them”。因此 `ai_will_do = { always = no }` 只是 AI 发起意愿/选择层，不能当成对玩家或原生 hardcoded AI 的绝对禁止；真正的自定义动作门禁是 `is_visible`/`is_allowed`，而它们只作用于该动作。

当前 `mod/llm_bridge/common/new_diplomatic_actions/01_llm_bridge.txt`：

- `llm_submit_white_peace`（`:2-21`）限定 `tag = ENG ai = no`，要求 ENG 与 FRA 交战且法国是 AI；`require_acceptance = no`，`on_accept` 只给法国设置 `llm_peace_pending_eng` 并写日志（`:16-19`）。它不调用 `requestpeace`、不创建原生和平弹窗，也不给法国接收方一个接受/拒绝机会。
- `llm_accept_white_peace`（`:25-62`）同样限定玩家 ENG；`on_accept` 在 `FROM = FRA` scope 中直接执行 `white_peace = ENG`（`:45-50`），再以 `NOT = { war_with = ENG }` 验证并清理标志（`:51-58`）。这是一条玩家点击后立即结束战争的脚本 effect，不是法国 AI 的原生接受响应。
- 两个动作都写 `ai_will_do = { always = no }`（`:21`、`:62`）。这避免当前自定义动作由 AI 主动选择，但不改变原生 `requestpeace`、原生和平评分或其他外交动作。

原版 `common/peace_treaties/00_peace_treaties.txt` 的脚本和平条款接口支持：
`category`、`power_projection`、`power_cost_base`、`prestige_base`、`ae_base`、`warscore_cost`、`warscore_cap`、`requires_demand_independence`、`is_make_subject`、`requires_is_allowed`、`is_visible`、`is_allowed`、`effect`、`ai_weight`（`:18-60`）。文件同时明确限制：不能把谈判双方换成第三国，也不支持直接设定省份或第三方目标（`:5-7`）。

当前测试条款 `mod/llm_bridge/common/peace_treaties/01_llm_bridge.txt:3-32` (`llm_test_pay_10`) 只在 ENG/FRA 原生和平界面可见（`:10-15`），检查支付方国库（`:16`），在**结算时**转移 10 金币并写 flag/日志（`:17-28`），`ai_weight` 仅导出 `ai_value = 10`（`:30-32`）。这里没有 `llm_diplomacy_locked`，也没有发送、接受、拒绝或待处理提议入口。`requires_is_allowed = no` 表示条款不由 CB 明确允许时仍可出现并产生外交点数代价；它不是锁。

## 原生脚本/defines 能做什么

1. `common/diplomatic_actions/00_diplomatic_actions.txt:1-16` 的旧动作格式支持每个 action 多个 `condition`，每个 condition 有 `tooltip`、`potential`、`allow`，并支持一个 `effect`。当前锁正是利用这个脚本门禁。
2. `common/new_diplomatic_actions/00_diplomatic_actions.txt:3-60` 的 `static_actions` 注册了 `requestpeace`、`break_alliance` 等原生动作及图标/alert 索引；`requestpeace` 的核心行为没有在可编辑脚本 block 中暴露。不能仅通过给旧文件加 condition 来拦截它。
3. `common/on_actions/00_on_actions.txt:182-190` 只有 `on_peace_actor`/`on_peace_recipient` 结果回调（recipient 默认为空），不是提议发送或 AI 接受接口。
4. `white_peace` 是可由事件/条款 effect 调用的直接结算效果；静态搜索的调用包括 `events/flavorBYZ.txt:3021,3074`、`events/flavorGOT.txt:573`、`events/flavorSON.txt:431,568`、`events/flavorSWI.txt:995`、`events/FlavorTUR.txt:6141` 及 `common/peace_treaties/00_establish_trade_protectorate.txt:34`。直接调用会跳过原生提议队列和接收方 AI 判断，不能作为“原生主动议和”实现。
5. `common/defines.lua` 没有 `llm_diplomacy_locked` 或按国家关闭全部外交的字段。可见的是全局评分/门槛：例如 `NAI` 下 `DIPLOMATIC_ACTION_BREAK_ALLIANCE_BASE_FACTOR`（`:1666`）、各类外交动作评分（`:1667-1677`）、`DIPLOMATIC_ACTION_PROPOSE_SCORE`/`DIPLOMATIC_ACTION_BREAK_SCORE`（`:1914-1918`），以及和平 AI 的 `PEACE_BASE_RELUCTANCE`、战争方向、战争疲劳、力量、时间、停滞、绝望等（`:1780-1828`）和各和平条款权重（`:1830-1912`）。这些是全局权重/接受倾向，不是法国专属的绝对 veto；调低权重也不能保证零动作。

## 缺口和对“禁止法国外交”的含义

- 要达到“法国仍由原生 AI 作战/理财，但其外交主动权交给外部 LLM”的强度，至少还要覆盖所有原生外交 action 的行动者选择，以及 `requestpeace`/原生和平发送和响应路径。当前 flag 没有这些入口。
- `requestpeace` 是 static/hardcoded action，和平条款脚本只定义条款可见性、费用、效果和 AI 条款权重；公开脚本没有“发送原生和平提议”“接受/拒绝原生提议”的 effect。要保留原生和平评分和接收逻辑，需要运行时/native 层在 action 选择或投递前拦截，或另行实现明确的自定义协议；直接 `white_peace` 只是强制结算。
- 事件和其他脚本 effect 可直接调用 `declare_war[_with_cb]`、`break_alliance` 或 `white_peace`，所以把两个 `condition` 当作全局绝对禁令会过度声称覆盖范围。是否某条具体 effect 在运行时还经过同一硬编码检查，应由原生 probe 单独验证；本报告不替代该验证。
- `ai_will_do = { always = no }` 的正确解读是“该自定义 action 的 AI 发起评分为零/模板声明当前 AI 不会发送”，不是法国原生外交全禁，也不会改变原生和平 AI 的主动提议/接受算法。

