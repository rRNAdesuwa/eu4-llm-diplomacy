# 1.37.5 TAG 外交最终拉通记录（2026-10-13）

120个绑定的同一次拉通已结束，完整运行验收尚未通过。41项完成原生派发，77项被原生条件或预检拒绝，2项保持未知。没有待发送项，任何已进入请求均未重发。逐项发送结果见[动作清单](tag-command-actions-1375.md)，调用方式见[接口文档](tag-command-interface-1375.md)。

## 执行及证据

| 片段 | 构建 / PID | 派发 | 拒绝 | 未知 | 该片段后未进入余项 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | build-5 / 33824 | 6 | 4 | 1 | 109 |
| 2 | build-6 / 20496 | 19 | 48 | 1 | 41 |
| 3 | build-7 / 47740 | 16 | 25 | 0 | 0 |
| 合计 | 同一次拉通 | 41 | 77 | 2 | 0 |

每个后续片段从上个片段保存后的战役继续，只发布经文件审查证明完全未领取的请求，保留原request_id。三个片段合计581次原生调用，日志中无SEH异常；12次派发的actor不是玩家，玩家始终FRA。77项拒绝中75项为 `full88_normal_false`，2项为贸易联盟关系预检拒绝，不将其当作发送成功。

合并证据：`work/runtime/tag31-integration-final-20261013.json`，SHA-256 `704e9106db4eaf8ffd2a5eb9e23055862a7529130ebed3c54bd49cf82c2936ee`。三个原始报告及审计文件保持不变。此次拉通不改变历史成功台账的定义，也没有开发复测历史成功动作。

最后存档为 `llm_diplomacy_1375_tag31_final.eu4`，42,742,328字节，SHA-256 `7bf6d888747d178d9f545fc7278cbf7342be28ea84a0f4e7a4ecd82fde83ae07`。原基线及两段中间存档均保留。前后均为1445.2.16，没有推进日期。代理自行处理了启动、载入、Steam提示、Mod成就提示和保存；20496与47740均通过菜单退出，held精确进程观察的退出码为0。33824退出确认期间消失，未取得退出码，原因不明。

## 统一存档观测

整批结束后才进行末态核对。有界解析31个相关国家的选定字段和全局外交记录；忽略字节位置及原始拼写的差异，保留重复修正和关系记录。主要差异为15条全局记录新增、15条移除，原始证据为 `work/runtime/tag31-effects-diff-20261013.json`。另从相同两个存档提取FRA、POR的宿敌和包围网字段，见 `work/runtime/tag31-effects-rivals-coalition-diff-20261013.json`。这些操作只读磁盘文件，不打开游戏或重发命令。

以下是实际记录的变化，不是完整因果证明。后续选定状态的冷重载比较已完成，范围及差异见末节，不能扩大为全部效果验收。

| 动作或组合 | 存档证据 | 限制 |
| --- | --- | --- |
| 保独 FRA→SAV；撤销保独 FRA→SCO | 新增FRA/SAV guarantee，移除FRA/SCO guarantee | 选定关系变化 |
| 提供军通 FRA→BRI | 新增military_access，first=BRI、second=FRA | 不据此验证取消分支 |
| 败坏官员、破坏征兵、破坏声誉、诽谤商人、煽动不满 | POR/NAV/SCO/BRI/SAV分别新增对应国家修正 | 五项修正均有新增记录 |
| 制造贸易冲突；制造传播信仰借口 | 新增FRA→ENG cb_trade_conflict、FRA→BUR cb_spread_the_true_faith | 只制造CB，未宣战 |
| 解除联姻 LIT→BLO | 移除BLO/LIT royal_marriage | 选定关系变化 |
| 取消提供独立支持 FRA→HOL；取消请求的独立支持 SWE→ENG | 移除FRA/HOL、ENG/SWE support_independence | 两个方向的既有关系均移除 |
| 取消附庸 POL→MAZ；取消朝贡 DAN→LAU | 移除相应dependency，MAZ/LAU不再记录原overlord | 选定关系变化 |
| 异教联姻 POR→NAV | 新增POR/NAV royal_marriage | 与其他后续属国动作共用国家 |
| 请求保护国 BRI→POR | 新增POR/BRI trade_protectorate | 证明AI发起国关系发生变化 |
| 建立索尤加尔 FRA→AUV；建立欧洲殖民地 FRA→FOI；转换整合联统 DAN→SWE | 新dependency类型分别为soyurghal_subject_type、european_colony、integrated_personal_union | 原属国类型被替换 |
| 提拔封邑继承人 FRA→BOU | BOU的旧heir消失，FRA新heir为相同ID1539 | 选定继承人记录变化 |
| 释放纳瓦特尔朝贡国 DAN→DTT | 原DAN/DTT tributary_state记录消失 | 基线类型是普通朝贡；不能算验证纳瓦特尔类型全部语义 |
| 加入包围网 POR→SAV | POR新增coalition_target=SAV及coalition_date | 原FRA已在该包围网中 |
| 选择宿敌 FRA→BUR | FRA新增rival={country=BUR,date=1445.2.16} | 选定宿敌变化 |

## 尚未通过的部分

- `ask_support_independence` SWE→FRA 已派发，FRA存档中的外交队列新增对应提议；玩家尚未接受，不算独立支持关系已成立。
- 改善关系/停止改善、间谍网/停止间谍网、拉拢人情/停止拉拢、反间谍/停止反间谍在同一批次内成对执行。最终状态无法分别验证各次持续任务。改善关系可看到新增+50关系修正，但不补发以取得中间快照。
- `create_pronoia`、`make_pronoia_inheritable`、`promote_vassal_to_eyalet` 虽有派发，最终AMG、ORL的dependency类型为vassal，不能认定目标特殊属国类型通过。`join_cultural_sphere_of_influence` 最终NAV也为vassal，完整语义未验证。
- `call_eyalet_into_wars`、`grant_war_rights`、`cancel_infiltration` 尚无足够的选定字段证据，保留为派发已证、完整效果未证。停止类动作同理。
- `remove_rival` FRA→ENG 已派发，但基线FRA的宿敌字段中没有ENG；这条请求不能验证移除既有宿敌的效果。
- 75项full+88拒绝仅证明原生检查正常返回false，尚未逐一定位全部条件；不得把测试Mod视为已绕过所有硬编码条件。两项贸易联盟取消动作缺少先决联盟关系，也未进入发送。
- 27个目录排除项继续按各自原因保留；其中22项需要额外参数，4项旧取消标签语义未证，1项附庸主动解除方向未证。宣战、议和仍延期。

## 两项未知及修正

`ask_military_access` POR→BRI在旧整批60秒期限到期时已进入工厂，发送未调用，按unknown_no_retry处理；build-6起整批期限随条数调整。`abandon_union` BUR→BRB在工厂正常返回后被适配器Fields检查隔离，未进入初始化或发送。这不是捕获到的游戏异常：原生exception=0，适配器误把该族+0x34初值当成0，实际工厂写2。

build-7修正工厂、初始化和发送clone的状态合同，仍保持隔离和未知禁止重试。静态证据 `work/runtime/tag31-abandon-union-state-20261013.json` 定位工厂35f620的写2指令。修正后的53组扩展合同检查通过，包括初值0必须隔离的负向用例；没有再次测试abandon_union，因此修正后的真实发送路径仍未通过运行验收。

当前build-7构建通过128组协议、10组Guard、53组原生扩展合同检查。先前88项相关Python检查通过，包含部分发布失败、持久开发测试策略、条件查询和7项测试Mod检查；没有调用游戏外交动作。DLL和原生来源未改，44个来源pin不含Python backend/service。原始120条及两个余项文件不可再次发布；以下修正不改写原结果，也不会开始第二次全量120条拉通。

后续36项定向检查通过（3.580s），含4项新增索引检查，与前88项重叠；已涵盖92个不同相关检查。条件资料和动作参考生成器 `--check` 通过。索引原文件SHA-256 `f0253495ce7a440f05840ff6d6a7993ad0e4d1cca90f9cb68fc99dcdcd1d92f9`。

## 拉通后的拒绝分析与开发测试规则修正

此前把全部120个动作永久禁止开发测试的规则过宽。用户禁止复测成功动作，并未禁止修复条件后测试证据完整的失败动作。现在 `--test-only` 始终排除历史38项成功动作、原120个request_id及已派发/未知/未闭合尝试的同一动作。只有完整文件审计证明正常拒绝、没有发送、所有权和清理闭合，才允许新request_id。75项full+88干净拒绝减去18项历史成功，得到57个条件修复候选；2项稀疏lease拒绝暂不入选。`work/runtime/tag31-corrective-candidates-20261013.json` 仅为资料，不是发布命令，也不证明这些动作当前可用。

新 `bridge/tag_test_policy.py` 在跨session持久目录预留每个开发尝试，核对旧manifest/DLL、请求意图、原审计前缀、完整调用配对及拒绝清理结果；待领取、派发、未知或缺失证据均阻止再测。不自动清除残留锁。普通API调用不受开发台账限制，历史38项成功数量不变。本轮尚未发送新的外交请求。

公开的 `conditions --action <action>` 和 `GET /native/v1/conditions/{action}` 提供原版/测试Mod条件与来源散列；51族local+80索引含15,341条解码指令、1,600个直接调用和228个不同本地化键。索引没有递归解码调用，scriptable族还保留一个外部尾跳转；这些只是条件线索，不是完整谓词或实际失败分支。公共full+88可能先行拒绝，不能从本地化引用归因75项拒绝。详见[条件资料](tag-command-conditions-1375.md)。

四族窄分析见 `work/runtime/tag31-native-rejection-leaf-20261013.json`：FRA→SAV盟约的既有包围网目标和−10000好感度是确定的存档阻碍；附庸、联姻和信任尚有未采样的原生能力或参数。信任读的是NAV→FRA方向的人情，不能拿反向FRA→NAV值解释拒绝。原full false没有记录具体失败分支，不能把这些线索说成全部拒绝原因。

发布错误也已补齐：开始持久预留/意图写入后失败，HTTP409或CLI退出2返回 `publication_unknown` 及逐项 `publication_stage`，保留锁和意图、禁止自动重试。文件发布阶段不能代替原生执行结果。

## 拉通后的冷却 Mod 修正候选

拉通使用的是普通冷却配置0。重新核对已知严格日期边界后，确认公共full检查4e9d00也会调用35a7f0：在option=false且动作虚表+100为true时，当前日期不大于关系截止日期会拒绝。联姻、盟约和脚本外交三族的该槽均固定返回true。该检查存在于游戏代码，单纯把月份设0不会把同日阈值移到过去；这支持部分拒绝与同日冷却有关的解释，不能证明75项均因此拒绝。

35a830使用有符号月份加法14c8030写入截止日期，后者具有负月份跨年的分支。因此测试Mod现改为 `DIPLOMAT_COOLDOWN_TIME=-1`，让以后新写入的阈值落在过去；没有改原生检查、进程日期、内存阈值或普通动作效果。候选已生成、备份并安装。当前新进程仅在进行只读载入检查，未发送新请求；同日运行效果未验证，也不能清除旧存档阈值。当前仍不能宣称测试Mod使所有外交条件可用。

静态证据 `work/runtime/tag31-cooldown-static-20261013.json`；安装回执 `work/runtime/tag31-mod-negative-cooldown-install-20261013.json`，旧安装备份 `work/backup/diplomacy-unlock-20261013T001814418117Z`。此候选在上述拉通结束后产生，不属于120条拉通的运行证据。

## 特殊属国回退原因及 Mod 修正

解包脚本给出明确调用链：`common/on_actions/00_on_actions.txt:5410` 的 `on_dependency_gained` → `01_scripted_effects_for_on_actions.txt:4885` → `01_scripted_effects_for_diplomacy.txt:76` 的 `convert_special_subject_to_vassal`。overlord缺少 `has_eyalets`、`enables_pronoias` 或 `persian_influence_mechanic` 时，该helper分别把eyalet/core_eyalet、pronoia/hereditary_pronoia、文化势力范围属国改为vassal。之前只放开动作及潜在宗主条件，漏掉了这条获得属国后的回退。

该链与AMG、ORL、NAV的最终vassal及选定副作用一致，但未采集当时政府能力或逐调用分支，因此仍是对具体实例的有力解释，不能写成已跟踪确认。证据 `work/reports/tag31-subject-normalization-diagnosis-20261013.json` 区分已证脚本链和实例推断。

Mod已只禁用这个helper外层 `if.limit`（`always = no`），同文件其他helper和原外交动作on_accept保持原字节；未禁用宗教/政府变化或君主死亡等正常生命周期。安装回执 `work/runtime/tag31-special-subject-mod-install-20261013.json`，备份 `work/backup/diplomacy-unlock-20261013T042007570129Z`。7项Mod离线检查通过，包括其他helper和原效果保留。

PID61988／创建时间 `01dd5acc83b0078c` 已由代理关闭Mod成就提示并进入最终存档地图：1445.2.16、FRA、manual_pause1、ironman0、reset0/load0。39个请求脚本definition全部找到，总46项类型匹配；已安装全部Mod文件与repoManifest一致且启用末位，实时 `base+0x233e064` int为−1。证据 `work/runtime/tag31-health-61988.json`、`tag31-loaded-definitions-61988.json`、`tag31-mod-load-61988.json`。errorlog仍有其他字体/事件告警，选定unlock/helper/action相关行为空，不能称日志全clean。未加载TAG外交DLL或发送请求；配置及脚本载入不证明同日冷却或特殊属国修正效果。

原GitHub页面可读取；贴吧正文和中英文百科直连失败。搜索缓存取得中文百科的附庸、外交条件片段，其中包含旧版本标记，只作为交叉核对线索。未声称读完贴吧或核对完1.37.5全部百科条件。

## 冷重载的选定状态比较

61988冷载原final后，保持手动暂停自行另存；固定副本 `llm_diplomacy_1375_tag31_reload.eu4` 为42,742,220B，SHA-256 `40a53b45056db3aa5fdef7858e22829d7f5241471ea3324a35284258c94254a1`。证据 `work/runtime/tag31-cold-reload-20261013.json`。没有加载外交DLL、执行请求或重测成功动作。

31国同范围选定关系与外交官、全局外交记录完全保持。唯一选定字段差异为DAN num_of_subjects从3到2，num_of_subject_count_indexed移除11=1，4=1/24=1保持；仅描述重载计数变化，不据此断言额外外交效果。原档已有vassal类型也不会被新helper保护追溯修复。

旧组1/2提取不含rival/coalition字段，新提取多4个字段，首次比较因范围不一致拒绝。原新提取及失败证据均保留；之后仅在文件内投影去除额外字段并固定原提取散列，得到scoped结果再比较，没有重采存档或发送请求。结论仅为该范围的冷重载状态，不证明全部120项效果或精确请求因果。
