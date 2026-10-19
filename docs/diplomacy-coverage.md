# 外交行为目录与验证边界

此文档由 `tools/build_diplomacy_catalog.py` 生成。目录供外部 API 枚举、参数校验和查询证据；目录收录不表示已实现原生执行。

扫描版本：`EU4 v1.37.5.0 Inca (491d)`。执行文件 SHA-256：`9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A`。
共 274 个公开行为标识；本次扫描版本原生执行已验收数量为 **0**。1.37.4 的历史验证不能移用于 1.37.5。

## 可复现生成

```powershell
python tools/build_diplomacy_catalog.py
python tools/build_diplomacy_catalog.py --check
python -B -m unittest bridge.tests.test_diplomacy_catalog -v
```

省略 `--game-root` 时按 `local.env` 的 `EU4_GAME_ROOT` 读取。只读扫描安装目录；写入仓库 JSON 和本文档。源文件按文件保存 SHA-256、大小，证据按相对路径和行号保存；不复制完整游戏源码。

扫描器处理注释、引号、嵌套大括号、顶层定义和 `copy_from`。外交脚本头部的原生动作注释、实际覆盖块、static_actions、脚本新动作分别计数并合并；属国交互从 default 标记段提取并解析各属国类型继承；和平条款从脚本定义和 CB/war goal 的选项集合提取。明确 `always = no` 的隐藏条款/示例不计入普通 UI 行为，仍记录在 exclusions。

若默认 `work/reports/native-diplomacy-1.37.5.json` 存在，扫描器合并原生静态报告；可用 `--native-report` 指定其他报告。`--no-native-report --no-subject-report --no-special-report --no-peace-report` 关闭四类原生映射，仅扫描文本；政府机制作用范围仍按实际源脚本修正。合并前强制报告 binary.sha256 与当前 EXE 完全一致，不匹配直接报错。目录保留各 vtable 变体、token/getter 和 factory 引用；这只属于静态证据，不开启执行。

## 目录协议

`bridge/diplomacy_catalog.json` 顶层为 `schema_version / game_build / sources / coverage / actions`。`actions` 是数组；每项包含 `action_id`、中文名称、类别、`surface`、`game_key`、`parameters`、`parameter_status`、`evidence` 和 `execution`。

`parameters` 是 JSON Schema 子集，`actor/target` 为三字符国家 TAG。它描述外部请求，不等于引擎参数布局。`partial` 表示尚缺参数或对象身份绑定；即使 `specified` 也必须经过原生能力门槛。所有和平组件仍为 partial，待统一定义战争、谈判方和 giver/taker 的身份绑定。只有中文/英文文本的 UI 候选保留 `game_key=null`，不能按名字直接跳入任意引擎地址。

`surface=diplomacy` 是外交窗口行为；`subject_interaction` 为属国交互；`government_interaction` 为政府机制交互；`peace_term` 为和约组件；`legacy_request` 为历史固定实验。幕府三项保留 `subject.*` 旧 ID，但只接收 actor，不接受 target，作用于脚本筛选出的全部大名。`break_alliance` 是大国要求第三国断盟，`dissolve_alliance` 才是解除本国联盟，不能混用。
原文语义证据在 `localisation/rights_of_man_l_english.yml` 的 `BREAKALLIANCE_DESC/REQDES1`，明确包含 THE(M)/WITH 第三国关系。因此历史模组锁 `break_alliance` 不能直接证明已阻止受控国自己解除联盟。
开始/停止、提议/撤销可能共用原生 token，通过 value 或其他模式字段区分。公开 API 为它们保留不同 action_id；没有单独取消 token 不等于引擎不支持取消。有直接分支证据时将 value 和证据放入 native_mapping.variants；国家方向仍不明的分支保留在 unresolved_native_variants，不猜测对应的公共动作。

`execution.status=unimplemented` 必须拒绝提交。`legacy_build_verified` 仅表示受约束的历史证据；需再次匹配执行文件哈希、固定参数、安装状态及前置检查，不能因为枚举成功就返回游戏动作成功。宣战、白和平、金币历史证据的层级也不同。

## 扫描计数

| 来源 | 数量 |
| --- | ---: |
| actions_total | 274 |
| actions_with_any_static_native_mapping | 270 |
| actions_with_static_native_mapping | 167 |
| actions_with_static_peace_mapping | 53 |
| actions_with_static_special_mapping | 9 |
| actions_without_static_native_mapping | 4 |
| documented_native_action_occurrences | 66 |
| government_interactions_corrected_from_subject_properties | 3 |
| localized_peace_variants | 8 |
| localized_ui_variants | 50 |
| native_script_override_blocks | 23 |
| native_token_names | 88 |
| native_ui_cancel_modes_without_effect_proof | 4 |
| native_vtable_variants | 88 |
| peace_compatibility_aliases | 1 |
| peace_component_classes | 40 |
| peace_option_references | 505 |
| public_actions_with_native_mode_evidence | 45 |
| remaining_mode_actions_mapped | 38 |
| scripted_diplomatic_action_blocks | 40 |
| scripted_peace_treaty_blocks | 13 |
| special_primary_command_classes | 7 |
| static_action_registrations | 45 |
| subject_actions_with_static_registration | 41 |
| subject_interaction_properties | 44 |
| subject_types | 27 |

167 个公开条目带静态映射，其中 40 个脚本定义共用 `scriptable_diplomatic_action` 家族。原生 token 名称为 88 个；公开条目数不能当作独立原生类的数量。

静态原生对账新增：`confirm_tribute_action`、`convert_tributary_to_vassal`、`invite_to_hre`。
`scriptable_diplomatic_action` 归为脚本动作共用原生家族，不作为任意脚本执行接口暴露。未按 token 或已有模式证据映射的脚本动作：无；不能由同类名称推断对象布局或取消模式。

`cancel_vassalization` 已静态确认是 `vassalaction` 的 value=false 模式，用于宗主国解除附庸关系；合法性分支拒绝 actor 是 recipient 附庸的方向。因此不能把同一映射用于 `break_vassalization`（附庸主动解除关系），后者继续未映射。该结论仍不是运行验收。

另有 41 个属国交互已定位静态 token、单例注册和共用 subject command；保存在 `native_subject_mapping`，与普通外交工厂分开。合计 270 个公开 ID 有静态原生映射，执行支持仍为 0。
属国交互剩余未映射：无（仅静态对应完成）。字段参数、生命周期和运行结果仍需逐项验收。

属国/政府特殊路径报告映射 6 个旧公开 ID、4 个独立 0x60 主命令类，证据保存在 `native_special_mapping`。其 report SHA-256 `EEF6C7369E37A339975D5234C62B069CDD4864B697D0897304316C5C2D09AD3D`、游戏 SHA-256 和幕府脚本 SHA-256 均须匹配；可通过 `--special-report` 指定同一份审查报告，或 `--no-special-report` 不合并这份特殊路径报告。
军役 focus 枚举编码为 `no_focus=0, aggressive=1, supportive=2, passive=3, defensive=4, siege=5`；贡品为 `none=0, cash=1, adm=2, dip=3, mil=4, manpower=5`。字符串 schema 列表顺序不能直接当作原生编码，适配器须读取独立的 enum_mappings。
`subject.release_colony.play_as_released=true` 表示释放后再独立提交 set_controller；它不是释放命令内的布尔字段，没有原子性或玩家身份重绑定验证，因此参数状态保持 partial。
`subject.expel_ronin / subject.sankin_kotai / subject.sword_hunt` 已按 `17_shogunate.txt` 修正为 actor 的政府机制，命令没有单一 target。其 parent/index 为当前定义数字 ID，尚需按机制名/交互名有界解析；不接受用户数字 ID。旧属国属性留在 legacy_subject_types_enabled_by_source，不能据此把它们重新当作逐个附庸操作。
详见 [特殊路径分析](native-subject-special-paths-1375.md)。

独立 `native_peace_mapping` 覆盖 53 个公开和平 ID、40 个原生组件类，其中 13 个脚本条款共用专属和平定义注册表。`peace.show_strength` 为 `peace.po_humiliate` 的兼容别名，两者名称均修正为“展现力量”；不能把别名或脚本定义个数当成独立原生类数。
新增 `peace.po_enforce_military_access / peace.po_transfer_vassals / peace.revoke_reform`。扫描器补读 attacker_disabled_po/defender_disabled_po；禁用集合只证明选项标识存在，不证明可执行。军事通行和撤销帝国改革另有原生显示方法直接引用本地化的证据。
和平组件工厂为 0x99ff90，与普通外交工厂分开；base_fields/fields 保存序列化类型、偏移和指令证据。giver+0x22 为未对齐完整国家句柄，和 offer_giver+0x10 不同。province_id、region、脚本 type 的实例字段存对象/定义指针，不能直接写公开整数或字符串。war/offer/角色方向与所有权仍未闭合，所有条款保持 partial、execution unimplemented。
`peace.give_up_claims` 的旧 province_ids 数组没有依据，改为暂定 claims_against TAG（放弃该国境内全部宣称）；其 native taker 方向仍待绑定。唯一未映射的和平候选为 `peace.full_annexation`，不推断其复合实现。
和平补充报告 SHA-256 `EA894744006119693B3568C08A94D30CB4929ABC2AC792A616C25466C7D608AA` 与字段报告全 SHA、安装源文件全 SHA 均须匹配。用 `python work/trace_peace_catalog.py --check` 复核独立证据，详见 [和平静态目录分析](native-peace-catalog-1375.md)。

固定的 39 个外交待分类 ID 已逐项审查，新增 38 项静态对应：35 个既有外交 family 模式，3 个独立 command。模式报告 SHA-256 `1C0FA12B630A134036C32CAF826750CE82608C44FAB80108E6CFD2B738D06676`，其报告、固定历史清单、来源报告和安装文本全 SHA 都须匹配；不依赖正在生成的目录，避免摘要循环。复现 `python work/trace_diplomacy_modes.py --check`；可显式 `--no-modes-report` 省略该增量。
`dissolve_alliance` 对应本国 allianceaction false，不能和要求第三国断盟的 break_alliance 混用。军通请求方取消使用 milaccess false，给予方撤回使用 offermilaccess false。支持独立、贸易联盟、包围网、佣兵和朝贡还依赖当前国家角色/关系的具体分支；mode_constraints 保存这些前提。
四个旧间谍取消 ID 只确认原生 false 名称分支，标记 native_ui_cancel_mode_effect_unverified、effect_semantics_verified=false、参数 partial；它们是否可达、是否真的撤销任务或效果仍未证明。蔑视侮辱用 index+0x40 的非负值选择，不是 value=false，定义选择仍待绑定。
select_rival/remove_rival/create_vassal 分别保存独立命令证据。选宿敌的替换分支另用 0x68 replace_rival_command 和第三国字段；释放附庸目标必须绑定无省份国家，play_as_released 另发 set_controller，不能当作原子布尔字段。
`native_special_mapping` 现合计 9 个公开 ID、7 个主命令类；替换宿敌属于额外条件命令。break_vassalization 的同名 UI 分支因合法性拒绝主体方向继续未映射。详见 [剩余外交静态分类](native-diplomacy-modes-1375.md)。

全部四类静态映射合计 270 个公开 ID；剩余 4 个在 `coverage.unmapped_action_ids`。运行执行支持仍为 0。

`give_subsidies.duration_months` 已纠正为 `duration_years`，旧字段拒绝，不做隐式转换。action+0x44 原生单位为年；UI 的 10–400、步长 10 是界面域，尚非完整引擎合法域证明。参数仍 partial、执行仍未实现。
单位证据完整报告 SHA-256 `0C1731B0B29B296DA73DC406FB31544ADA59C17C275D17D623677B16998698BD`，详见 [v10 扩展静态分析](native-pair-extension-v10-1375.md)。本次没有将七类静态构造依据提升成运行支持。

## 未完成与遗漏边界

- 所有新行为仍待逆向构造器、析构/克隆/序列化、字段、原生合法性检查、游戏线程调用、响应、结算和保存重载。没有把 set_relation 或脚本效果伪装为正常改善关系，也没有把直接创建属国伪装为附庸外交提议。
- GUI 使用动态动作列表；目录不是从截图或 GUI 控件数量推断完整性。头部文档和本地化可能保留旧功能，需运行时验证实际可见性。
- 本次仅扫描安装目录原版数据；未合并启用 MOD 的覆盖、DLC 许可、存档条件。属国类型 source-enabled 标记只反映脚本继承，不能当作实时可执行性。
- 外交请求的接受/拒绝、撤回提议、被动 AI 回应、冷却/成本预览、全部 AI 外交权限隔离仍未完成。事件、决议、任务等可间接改变外交状态，不等同于外交窗口动作。
- 和平条款需要组合成原生和约；单个条款的参数目录不是完整和约构造器。割地、战争赔款等尚无本版本结算证据。
- 纯硬编码且没有这些文本引用的动作仍可能遗漏。`complete_native_coverage` 固定为 false；新增版本先运行扫描并审查差异，不能自动提升原生支持状态。

## 行为清单

以下仅展示首条证据；JSON 保存其他证据、参数和属国适用类型。

| action_id | 中文名称 | 范围/类别 | 状态 | 首条证据 |
| --- | --- | --- | --- | --- |
| `abandon_union` | 放弃联合统治 | diplomacy/dynasty | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:72` |
| `agitate_for_liberty` | 煽动独立 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:63` |
| `annex_vassal` | 外交吞并附庸 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:27` |
| `appoint_cardinal` | 任命枢机主教 | diplomacy/papacy | unimplemented | `localisation/emperor_l_english.yml:406` |
| `ask_fleet_basing_rights` | 请求舰队停泊权 | diplomacy/access | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:34` |
| `ask_for_march` | 请求成为卫戍国 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:70` |
| `ask_knowledge_sharing` | 请求分享思潮 | diplomacy/economy | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:59` |
| `ask_military_access` | 请求军事通行权 | diplomacy/access | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:33` |
| `ask_support_independence` | 请求支持独立 | diplomacy/alliance | unimplemented | `localisation/text_l_english.yml:1118` |
| `ask_to_be_tributary` | 请求成为朝贡国 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:85` |
| `bestow_imperial_grace` | 赐予帝国恩惠 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:44` |
| `break_alliance` | 要求第三国断盟 | diplomacy/great_powers | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:83` |
| `break_alliance_favor` | 用人情要求断盟 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:52` |
| `break_marriage` | 解除王室联姻 | diplomacy/dynasty | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:68` |
| `break_vassalization` | 附庸国解除附庸关系 | diplomacy/influence | unimplemented | `localisation/text_l_english.yml:1172` |
| `build_spy_network` | 建立间谍网 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:78` |
| `call_crusade` | 号召十字军 | diplomacy/papacy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:52` |
| `call_eyalet_into_wars` | 召集埃亚莱特参战 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:634` |
| `call_to_arms` | 召集参战 | diplomacy/war | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:40` |
| `call_trade_protectorate_into_wars` | 召集贸易保护国参战 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1561` |
| `cancel_agitate_for_liberty` | 停止煽动独立 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:252` |
| `cancel_annexation` | 取消外交吞并 | diplomacy/influence | unimplemented | `localisation/diplomacy_l_english.yml:145` |
| `cancel_condottieri` | 解除租用的雇佣军团 | diplomacy/economy | unimplemented | `localisation/text_l_english.yml:2335` |
| `cancel_fabricate_claim` | 停止伪造宣称 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:322` |
| `cancel_fleet_basing_rights` | 取消请求的舰队停泊权 | diplomacy/access | unimplemented | `localisation/EU4_l_english.yml:2592` |
| `cancel_infiltration` | 取消行政渗透 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:211` |
| `cancel_integration` | 取消整合 | diplomacy/dynasty | unimplemented | `localisation/diplomacy_l_english.yml:163` |
| `cancel_justify_trade_conflict` | 停止制造贸易争端 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:324` |
| `cancel_military_access` | 取消请求的军事通行权 | diplomacy/access | unimplemented | `localisation/text_l_english.yml:1204` |
| `cancel_offered_independence_support` | 终止提供的独立支持 | diplomacy/alliance | unimplemented | `localisation/text_l_english.yml:1121` |
| `cancel_requested_independence_support` | 终止收到的独立支持 | diplomacy/alliance | unimplemented | `localisation/text_l_english.yml:1120` |
| `cancel_sow_discontent` | 停止散布不满 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:261` |
| `cancel_steer_trade` | 取消贸易引导 | diplomacy/economy | unimplemented | `localisation/rule_britannia_l_english.yml:365` |
| `cancel_subsidies` | 停止战争援助 | diplomacy/economy | unimplemented | `localisation/text_l_english.yml:2300` |
| `cancel_trade_power_transfer` | 取消贸易竞争力转移 | diplomacy/economy | unimplemented | `localisation/diplomacy_l_english.yml:208` |
| `cancel_tributary` | 解除朝贡关系 | diplomacy/influence | unimplemented | `localisation/mandate_of_heaven_l_english.yml:11` |
| `cancel_vassalization` | 宗主国解除附庸关系 | diplomacy/influence | unimplemented | `localisation/text_l_english.yml:1171` |
| `charter_company` | 购买贸易公司省份 | diplomacy/economy | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:49` |
| `claim_throne` | 宣称王位 | diplomacy/dynasty | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:39` |
| `confirm_tribute_action` | 确认或拒绝年度贡品 | diplomacy/influence | unimplemented | `work/reports/native-diplomacy-1.37.5.json:1` |
| `convert_to_core_personal_union` | 转为直属联合统治 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:5967` |
| `convert_tributary_to_vassal` | 将朝贡国转为附庸 | diplomacy/influence | unimplemented | `work/reports/native-diplomacy-1.37.5.json:1` |
| `corrupt_officials` | 腐化官员 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:228` |
| `counterespionage` | 反间谍 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:595` |
| `create_european_colony` | 设立欧洲殖民地 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:5654` |
| `create_pronoia` | 设立普罗尼亚 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:2697` |
| `create_soyurghal` | 设立索尤尔加尔封地 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:6011` |
| `create_vassal` | 释放新附庸 | diplomacy/influence | unimplemented | `localisation/text_l_english.yml:2500` |
| `curry_favors` | 积攒人情 | diplomacy/favors | unimplemented | `localisation/EU4_l_english.yml:4778` |
| `declare_reichskrieg` | 发动帝国战争 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:45` |
| `declare_war` | 宣战 | diplomacy/war | legacy_build_verified | `common/diplomatic_actions/00_diplomatic_actions.txt:22` |
| `demand_sacrifices` | 索要祭品 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:5696` |
| `demand_unlawful_territory` | 索要非法领土 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:51` |
| `designate_march` | 指定卫戍国 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:69` |
| `dissolve_alliance` | 解除本国联盟 | diplomacy/alliance | unimplemented | `localisation/text_l_english.yml:1129` |
| `dissolve_protectorate` | 解除保护国关系 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1154` |
| `elevate_influenced_country_to_vassal` | 将受影响国提升为附庸 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:3635` |
| `embargo` | 实施禁运 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:26` |
| `enforce_peace` | 强制和平 | diplomacy/war | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:54` |
| `enforce_religious_unity` | 要求宗教统一 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:46` |
| `establish_tributary` | 建立朝贡关系 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:84` |
| `excommunicate` | 绝罚统治者 | diplomacy/papacy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:53` |
| `fabricate_claim` | 伪造省份宣称 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:56` |
| `fabricate_ottoman_invasion_cb` | 伪造奥斯曼入侵理由 | diplomacy/covert | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:380` |
| `fabricate_spread_the_true_faith_cb` | 伪造传播正信战争理由 | diplomacy/covert | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:3827` |
| `fabricate_state_claim` | 伪造地区宣称 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:75` |
| `fabricate_tributary_cb` | 伪造朝贡战争理由 | diplomacy/covert | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:763` |
| `form_coalition` | 组建包围网 | diplomacy/alliance | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:64` |
| `give_subsidies` | 提供战争援助 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:42` |
| `grant_autonomy_to_core_eyalet` | 授予直属埃亚莱特自治 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1652` |
| `grant_electorate` | 授予选帝侯地位 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:47` |
| `grant_freecity` | 授予自由市地位 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:49` |
| `grant_war_rights` | 授予自主战争权 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1966` |
| `guarantee` | 保证独立 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:30` |
| `heathen_royal_marriage` | 异教王室联姻 | diplomacy/dynasty | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:5722` |
| `improve_relations` | 改善关系 | diplomacy/relations | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:55` |
| `incorporate_vassal` | 合并附庸 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:5343` |
| `infiltrate_administration` | 渗透行政系统 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:59` |
| `influence_nation` | 影响国家 | diplomacy/great_powers | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:74` |
| `insult` | 发送侮辱 | diplomacy/relations | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:37` |
| `integrate_union` | 整合联合统治国 | diplomacy/dynasty | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:28` |
| `intervene_in_war` | 介入战争 | diplomacy/war | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:82` |
| `invite_into_cultural_sphere_of_influence` | 邀请进入文化势力圈 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:2946` |
| `invite_to_federation` | 邀请加入联邦 | diplomacy/alliance | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:66` |
| `invite_to_hre` | 邀请加入神圣罗马帝国 | diplomacy/emperor | unimplemented | `work/reports/native-diplomacy-1.37.5.json:1` |
| `invite_to_trade_league` | 邀请加入贸易联盟 | diplomacy/alliance | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:79` |
| `invite_to_zoroastrian_community` | 邀请加入祆教共同体 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:4361` |
| `join_coalition` | 加入包围网 | diplomacy/alliance | unimplemented | `localisation/diplomacy_l_english.yml:270` |
| `join_cultural_sphere_of_influence` | 加入文化势力圈 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:3362` |
| `justify_trade_conflict` | 制造贸易争端 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:57` |
| `kick_from_federation` | 逐出联邦 | diplomacy/alliance | unimplemented | `localisation/nw_l_english.yml:130` |
| `kick_from_trade_league` | 逐出贸易联盟 | diplomacy/alliance | unimplemented | `localisation/mare_nostrum_l_english.yml:53` |
| `knowledge_sharing` | 分享思潮 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:86` |
| `leave_coalition` | 退出包围网 | diplomacy/alliance | unimplemented | `localisation/diplomacy_l_english.yml:831` |
| `leave_federation` | 退出联邦 | diplomacy/alliance | unimplemented | `localisation/nw_l_english.yml:128` |
| `leave_the_cultural_sphere_of_influece` | 退出文化势力圈 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:3259` |
| `leave_trade_league` | 退出贸易联盟 | diplomacy/alliance | unimplemented | `localisation/mare_nostrum_l_english.yml:55` |
| `lift_excommunication` | 解除绝罚 | diplomacy/papacy | unimplemented | `localisation/text_l_english.yml:5177` |
| `make_pronoia_inheritable` | 令普罗尼亚可继承 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:2889` |
| `mam_export_grain` | 出口粮食 | diplomacy/economy | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:4642` |
| `mam_sponsor_hajj` | 资助朝觐 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:4996` |
| `offer_alliance` | 提议结盟 | diplomacy/alliance | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:25` |
| `offer_condottieri` | 出租雇佣军团 | diplomacy/economy | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:42` |
| `offer_fleet_basing_rights` | 给予舰队停泊权 | diplomacy/access | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:35` |
| `offer_loan` | 提供贷款 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:41` |
| `offer_military_access` | 给予军事通行权 | diplomacy/access | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:36` |
| `offer_peace` | 提出和约 | diplomacy/war | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:23` |
| `offer_protectorate` | 提议保护国关系 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:877` |
| `offer_vassalization` | 提议附庸 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:29` |
| `promote_appanage_heir` | 提拔采邑继承人 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1824` |
| `promote_primary_culture` | 推广主流文化 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:4014` |
| `promote_vassal_to_eyalet` | 提升附庸为埃亚莱特 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1691` |
| `recruit_foreign_general` | 招募外国将军 | diplomacy/relation | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:5374` |
| `reduce_relations_favor` | 用人情要求降低关系 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:50` |
| `reign_in_eyalet` | 收紧埃亚莱特控制 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:507` |
| `release_nahuatl_tributary` | 解除纳瓦特尔朝贡国 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:6158` |
| `release_pronia` | 解除普罗尼亚 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:2835` |
| `release_soyurghal` | 解除索尤尔加尔封地 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:6107` |
| `remove_electorate` | 撤销选帝侯地位 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:48` |
| `remove_freecity` | 撤销自由市地位 | diplomacy/emperor | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:50` |
| `remove_rival` | 移除宿敌 | diplomacy/relations | unimplemented | `localisation/diplomacy_l_english.yml:167` |
| `remove_them_from_cultural_sphere_of_influece` | 逐出文化势力圈 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:3220` |
| `request_access_to_modern_ideas` | 请求现代理念 | diplomacy/economy | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:2147` |
| `request_maps` | 请求分享地图 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:81` |
| `request_protectorate` | 请求保护国关系 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1291` |
| `request_to_join_federation` | 请求加入联邦 | diplomacy/alliance | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:65` |
| `request_to_join_trade_league` | 请求加入贸易联盟 | diplomacy/alliance | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:80` |
| `return_core_favor` | 用人情要求返还核心 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:51` |
| `revoke_condottieri` | 召回出租的雇佣军团 | diplomacy/economy | unimplemented | `localisation/text_l_english.yml:2334` |
| `revoke_embargo` | 解除禁运 | diplomacy/economy | unimplemented | `localisation/text_l_english.yml:1149` |
| `revoke_fleet_basing_rights` | 收回给予的舰队停泊权 | diplomacy/access | unimplemented | `localisation/EU4_l_english.yml:2595` |
| `revoke_guarantee` | 撤销独立保证 | diplomacy/influence | unimplemented | `localisation/diplomacy_l_english.yml:753` |
| `revoke_march` | 撤销卫戍国地位 | diplomacy/influence | unimplemented | `localisation/text_l_english.yml:1146` |
| `revoke_military_access` | 收回给予的军事通行权 | diplomacy/access | unimplemented | `localisation/text_l_english.yml:1208` |
| `revoke_war_rights` | 撤销自主战争权 | diplomacy/influence | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:1995` |
| `royal_marriage` | 王室联姻 | diplomacy/dynasty | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:21` |
| `sabotage_recruitment` | 破坏征兵 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:221` |
| `sabotage_reputation` | 破坏外交声誉 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:60` |
| `scornful_insult` | 轻蔑侮辱 | diplomacy/relations | unimplemented | `localisation/dharma_l_english.yml:613` |
| `select_rival` | 设定宿敌 | diplomacy/relations | unimplemented | `localisation/EU4_l_english.yml:4605` |
| `sell_indulgence` | 出售赎罪券 | diplomacy/economy | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:209` |
| `sell_province` | 出售省份 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:43` |
| `sell_ships` | 出售舰船 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:71` |
| `send_gift` | 赠送礼物 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:38` |
| `send_royal_ambassador` | 派遣王室使节 | diplomacy/covert | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:4277` |
| `share_modern_ideas` | 分享现代理念 | diplomacy/economy | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:2448` |
| `slander_merchants` | 诽谤商人 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:233` |
| `sow_discontent` | 散布不满 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:62` |
| `steal_maps` | 窃取地图 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:77` |
| `steal_modern_ideas` | 窃取现代理念 | diplomacy/covert | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:2031` |
| `steer_trade` | 要求引导贸易 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:76` |
| `stop_building_spy_network` | 停止建立间谍网 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:587` |
| `stop_counterespionage` | 停止反间谍 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:598` |
| `stop_currying_favors` | 停止积攒人情 | diplomacy/favors | unimplemented | `localisation/EU4_l_english.yml:4780` |
| `stop_improving_relations` | 停止改善关系 | diplomacy/relations | unimplemented | `localisation/diplomacy_l_english.yml:192` |
| `stop_supporting_heir` | 停止支持继承人 | diplomacy/dynasty | unimplemented | `localisation/EU4_l_english.yml:4757` |
| `stop_supporting_rebels` | 停止支持叛军 | diplomacy/covert | unimplemented | `localisation/diplomacy_l_english.yml:244` |
| `support_heir` | 支持继承人 | diplomacy/dynasty | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:67` |
| `support_independence` | 支持独立 | diplomacy/alliance | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:24` |
| `support_rebels` | 支持叛军 | diplomacy/covert | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:61` |
| `take_on_debt` | 承担外国债务 | diplomacy/great_powers | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:73` |
| `threaten_war` | 威胁战争 | diplomacy/war | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:32` |
| `trade_favors_for_gold` | 用人情换取金钱 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:58` |
| `trade_favors_for_heir` | 用人情要求同王朝继承人 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:56` |
| `trade_favors_for_men` | 用人情换取人力 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:54` |
| `trade_favors_for_sailors` | 用人情换取水手 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:55` |
| `trade_favors_for_trust` | 用人情换取信任 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:53` |
| `trade_favors_for_war_prep` | 用人情要求备战 | diplomacy/favors | unimplemented | `common/new_diplomatic_actions/00_diplomatic_actions.txt:57` |
| `transfer_trade_power` | 要求转移贸易竞争力 | diplomacy/economy | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:58` |
| `unconditional_surrender` | 无条件投降 | diplomacy/war | unimplemented | `localisation/mare_nostrum_l_english.yml:90` |
| `warn` | 发出警告 | diplomacy/influence | unimplemented | `common/diplomatic_actions/00_diplomatic_actions.txt:31` |
| `subject.expel_ronin` | 驱逐浪人 | government_interaction/government_mechanics | unimplemented | `common/subject_types/00_subject_types.txt:200` |
| `subject.sankin_kotai` | 参勤交代 | government_interaction/government_mechanics | unimplemented | `common/subject_types/00_subject_types.txt:199` |
| `subject.sword_hunt` | 刀狩令 | government_interaction/government_mechanics | unimplemented | `common/subject_types/00_subject_types.txt:198` |
| `gold` | 固定实验：一次性金币赔款 | legacy_request/peace | legacy_build_verified | `HANDOFF.md:5` |
| `whitepeace` | 固定实验：白和平 | legacy_request/peace | legacy_build_verified | `HANDOFF.md:5` |
| `peace.concede_colonial_region` | 割让殖民地区 | peace_term/peace_terms | unimplemented | `localisation/text_l_english.yml:2538` |
| `peace.demand_sacirifces` | 要求祭品和约 | peace_term/peace_terms | unimplemented | `common/peace_treaties/01_demand_sacirifces.txt:1` |
| `peace.end_rivalry` | 结束宿敌关系 | peace_term/peace_terms | unimplemented | `localisation/text_l_english.yml:8104` |
| `peace.enforce_fleet_basing_rights` | 强制舰队停泊权 | peace_term/peace_terms | unimplemented | `localisation/core_l_english.yml:900` |
| `peace.force_peasant_republic` | 建立农民共和国 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_peasant_war.txt:3` |
| `peace.full_annexation` | 完全吞并 | peace_term/peace_terms | unimplemented | `localisation/text_l_english.yml:2542` |
| `peace.give_up_claims` | 放弃宣称 | peace_term/peace_terms | unimplemented | `localisation/text_l_english.yml:2543` |
| `peace.make_nahuatl_tributary` | 建立纳瓦特尔朝贡国 | peace_term/peace_terms | unimplemented | `common/peace_treaties/01_make_nahuatl_tributary.txt:1` |
| `peace.pillage_capital` | 劫掠首都 | peace_term/peace_terms | unimplemented | `localisation/tmm_l_english.yml:276` |
| `peace.po_annex_tribe` | 吞并部落 | peace_term/peace_terms | unimplemented | `common/peace_treaties/01_annex_tribe.txt:1` |
| `peace.po_annul_treaties` | 废除条约 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:214` |
| `peace.po_become_tributary_state` | 强制朝贡 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:1865` |
| `peace.po_become_vassal` | 强制附庸 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:208` |
| `peace.po_change_culture` | 强制改变主流文化 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_enforce_primary_culture.txt:3` |
| `peace.po_change_culture_same_culture_group` | 强制同文化组文化 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_enforce_primary_culture_same_culture_group.txt:1` |
| `peace.po_change_government` | 改变政体 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2029` |
| `peace.po_change_hre_religion` | 改变帝国官方宗教 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2310` |
| `peace.po_change_religion` | 强制改宗 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:665` |
| `peace.po_claim_elector_role` | 夺取选帝侯地位 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_claim_elector_role.txt:3` |
| `peace.po_claim_norwegian_throne` | 夺取挪威王位 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_claim_norwegian_throne.txt:3` |
| `peace.po_concede_defeat` | 承认战败 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:61` |
| `peace.po_demand_provinces` | 割让省份 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:73` |
| `peace.po_dismantle_revolution` | 粉碎革命 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:236` |
| `peace.po_enforce_military_access` | 强制军事通行权 | peace_term/peace_terms | unimplemented | `localisation/core_l_english.yml:899` |
| `peace.po_enforce_rebel_demands` | 执行叛军要求 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2276` |
| `peace.po_establish_eyalet` | 建立埃亚莱特 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_establish_eyalet.txt:3` |
| `peace.po_extinguish_the_revolution` | 扑灭革命 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_extinguish_the_revolution.txt:2` |
| `peace.po_force_migration` | 强制迁徙 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2627` |
| `peace.po_force_out_colonizers` | 驱逐殖民者 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2736` |
| `peace.po_form_personal_union` | 强制联合统治 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:578` |
| `peace.po_gold` | 一次性金币赔款 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:60` |
| `peace.po_guaranteed_join_empire` | 保证加入帝国 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2503` |
| `peace.po_humiliate` | 展现力量 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2146` |
| `peace.po_humiliate_rival` | 羞辱宿敌 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:515` |
| `peace.po_independence` | 承认独立 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:726` |
| `peace.po_join_empire` | 加入帝国 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2451` |
| `peace.po_raid_churches` | 劫掠教堂 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_raid_churches.txt:2` |
| `peace.po_reintegrate_into_hre` | 重新纳入帝国 | peace_term/peace_terms | unimplemented | `common/peace_treaties/00_reintegrate_into_hre.txt:3` |
| `peace.po_release_annexed` | 释放被吞并国家 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:212` |
| `peace.po_release_vassals` | 释放属国 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:211` |
| `peace.po_return_cores` | 返还核心 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:416` |
| `peace.po_revoke_cores` | 放弃核心 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:176` |
| `peace.po_revoke_elector` | 撤销选帝侯 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:89` |
| `peace.po_spread_revolution` | 传播革命 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:215` |
| `peace.po_steer_trade` | 引导贸易 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:63` |
| `peace.po_subjugate_tributary_state` | 臣服为朝贡国 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2426` |
| `peace.po_subjugate_vassal` | 臣服为附庸 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:384` |
| `peace.po_take_mandate` | 夺取天命 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:2390` |
| `peace.po_trade_power` | 转移贸易竞争力 | peace_term/peace_terms | unimplemented | `common/wargoal_types/00_wargoal_types.txt:62` |
| `peace.po_transfer_vassals` | 转移属国 | peace_term/peace_terms | unimplemented | `common/cb_types/00_cb_types.txt:222` |
| `peace.revoke_reform` | 要求撤销帝国改革 | peace_term/peace_terms | unimplemented | `localisation/text_l_english.yml:3352` |
| `peace.show_strength` | 展现力量 | peace_term/peace_terms | unimplemented | `localisation/core_l_english.yml:289` |
| `peace.spread_dynasty` | 传播王朝 | peace_term/peace_terms | unimplemented | `common/peace_treaties/02_spread_dynasty.txt:1` |
| `peace.war_reparations` | 战争赔款 | peace_term/peace_terms | unimplemented | `localisation/core_l_english.yml:901` |
| `subject.allow_settlement_growth` | 允许殖民地增长 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:188` |
| `subject.bestow_gifts` | 赏赐礼物 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:176` |
| `subject.block_settlement_growth` | 禁止殖民地增长 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:187` |
| `subject.change_colonial_type` | 变更殖民地类型 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:189` |
| `subject.conscript_general` | 征召属国将军 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:185` |
| `subject.contribute_to_capital` | 贡献首都发展度 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:182` |
| `subject.customize_subject` | 自定义属国 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:162` |
| `subject.decrease_tariffs` | 降低关税 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:174` |
| `subject.demand_additional_tribute` | 索要额外贡品 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:179` |
| `subject.demand_artifacts` | 索要珍宝 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:178` |
| `subject.divert_trade` | 转移属国贸易 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:157` |
| `subject.embargo_rivals` | 要求禁运宿敌 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:152` |
| `subject.enforce_culture` | 强制文化转变 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:165` |
| `subject.enforce_religion` | 强制改宗 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:161` |
| `subject.force_isolation` | 强制孤立政策 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:183` |
| `subject.force_seppuku` | 强制切腹 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:180` |
| `subject.fortify_march` | 强化卫戍国 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:167` |
| `subject.grant_administrative_autonomy` | 授予行政自治 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:193` |
| `subject.grant_core_claim` | 授予核心或宣称 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:170` |
| `subject.grant_province` | 授予省份 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:164` |
| `subject.increase_tariffs` | 提高关税 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:173` |
| `subject.knowledge_sharing` | 分享思潮 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:186` |
| `subject.placate_rulers` | 安抚当地统治者 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:159` |
| `subject.place_relative_on_throne` | 扶植亲属登基 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:160` |
| `subject.press_sailors` | 征用水手 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:181` |
| `subject.release_colony` | 释放殖民领 | subject_interaction/subjects | unimplemented | `interface/countrysubjectsview.gui:602` |
| `subject.replace_governor` | 更换总督 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:163` |
| `subject.request_extra_levies` | 征召额外征募兵 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:192` |
| `subject.return_land` | 归还领土 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:184` |
| `subject.sacrifice_heir` | 献祭继承人 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:172` |
| `subject.sacrifice_ruler` | 献祭统治者 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:171` |
| `subject.scutage` | 征收代役税 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:155` |
| `subject.seize_court_resources` | 收取宫廷资源 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:191` |
| `subject.seize_territory` | 夺取领土 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:168` |
| `subject.send_additional_troops` | 派遣额外部队 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:177` |
| `subject.send_officers` | 派遣军官 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:156` |
| `subject.set_military_focus` | 设置属国军事方针 | subject_interaction/subjects | unimplemented | `interface/countrysubjectsview.gui:740` |
| `subject.set_tribute` | 设置朝贡类型 | subject_interaction/subjects | unimplemented | `interface/countrysubjectsview.gui:1023` |
| `subject.siphon_income` | 抽取收入 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:166` |
| `subject.start_colonial_war` | 命令发动殖民战争 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:169` |
| `subject.subsidize_armies` | 补贴军队 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:154` |
| `subject.support_loyalists` | 支持忠诚派 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:153` |
| `subject.takeondebt` | 承担外国债务 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:175` |
| `subject.upgrade_subject_type` | 升级属国类型 | subject_interaction/subjects | unimplemented | `common/subject_types/00_subject_types.txt:190` |
