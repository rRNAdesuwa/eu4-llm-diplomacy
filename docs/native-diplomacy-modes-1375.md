# 剩余 39 个外交 ID 的静态分类

本报告来自固定的 274/232 目录基线，只读精确 SHA EXE、既有原生报告及解包一致的安装资料；不访问游戏进程。复现：`python work/trace_diplomacy_modes.py --check`。

游戏 SHA-256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。固定清单 SHA-256：`ce846a61dd9801ca8da797accbee102832a48406b3981078c002d1fa8c63f988`。固定清单不会随目录增加映射而改写，避免摘要循环。

35 个 ID 找到普通外交类的具体模式分支，3 个是独立 command，1 个有同名原生 UI 分支却被合法性明确拒绝该方向。全部 execution_verified/runtime_verified/ownership_verified=false；所有权、原生实际效果、响应和存档重载都需分别证明。

## 模式不是新的工厂类

联盟解除使用 allianceaction false，和大国的 break_alliance 第三国要求不同。请求军通/自己取消使用 milaccess，主动给予/撤回使用 offermilaccess；舰队停泊对应两套同方向类。证据是各类自身的 action+0x38 分支和文案，不是共享 value setter。

支持独立的请求/提供由发起国是否符合原生依赖条件选择，value 再选择开始/撤销。联盟、朝贡、佣兵与贸易关系也有依当前状态区分方向的分支，不能只填 false 就把所有公开操作互换。蔑视侮辱由 signed index+0x40>=0 选择，不是 value=false；选项定义解析仍未完成。加入包围网是 form_coalition 的 true 模式在目标已有包围网时的名称分支，保留独立 ID 兼容。

## 不能当作已完成取消的四个分支

伪造宣称、煽动独立、散布不满、制造贸易争端确有 value=false→CANCEL_* 的原生名称虚方法。已保留其效果和合法性函数作审查材料，但这不能证明当前版本存在相应运行任务，也没有证明 false 会撤销既有效果。它们归类 native_ui_cancel_mode_effect_unverified，参数保持 partial，禁止把正向即时效果当作取消执行。

break_vassalization 更直接存在冲突：vassalaction 的 false 名称有 BREAKVASSAL，但合法性拒绝 actor.overlord==recipient。该 ID 继续未映射，不能借用宗主解除的 cancel_vassalization，也不能悄悄替换成宣战或 free_vassal 脚本效果。

## 独立命令

select_rival 的空槽选择为 add_rival 0x60；替换已有槽位为 replace_rival_command 0x68，具有第三个国家字段。remove_rival 是另一 0x60 类，共享 parser 不代表共享 token/效果。三者都使用独立 command 布局，不能投进普通外交工厂。

create_vassal 对应 createvassal 0x60 命令，释放目标是当前没有省份的国家对象，和外交附庸提议、同名脚本效果均不同。play_as_released 复选框会在释放提交之后另行构造 set_controller；没有原子性，也没有玩家身份变更后的安全续接。

| ID | 分类 | 原生家族/命令 |
| --- | --- | --- |
| `ask_support_independence` | `native_pair_state_selected_mode` | `support_independence_action` |
| `break_vassalization` | `native_ui_label_direction_rejected` | `vassalaction` |
| `cancel_agitate_for_liberty` | `native_ui_cancel_mode_effect_unverified` | `agitate_for_liberty` |
| `cancel_annexation` | `native_pair_boolean_mode` | `annexationaction` |
| `cancel_condottieri` | `native_pair_state_selected_mode` | `condottieri_action` |
| `cancel_fabricate_claim` | `native_ui_cancel_mode_effect_unverified` | `fabricate_claim` |
| `cancel_fleet_basing_rights` | `native_pair_boolean_mode` | `fleet_access` |
| `cancel_infiltration` | `native_pair_boolean_mode` | `infiltrate_administration` |
| `cancel_integration` | `native_pair_boolean_mode` | `integrationaction` |
| `cancel_justify_trade_conflict` | `native_ui_cancel_mode_effect_unverified` | `justify_trade_conflict` |
| `cancel_military_access` | `native_pair_boolean_mode` | `milaccess` |
| `cancel_offered_independence_support` | `native_pair_state_selected_mode` | `support_independence_action` |
| `cancel_requested_independence_support` | `native_pair_state_selected_mode` | `support_independence_action` |
| `cancel_sow_discontent` | `native_ui_cancel_mode_effect_unverified` | `sow_discontent` |
| `cancel_steer_trade` | `native_pair_state_selected_mode` | `steer_trade` |
| `cancel_subsidies` | `native_pair_boolean_mode` | `warsubsidy` |
| `cancel_trade_power_transfer` | `native_pair_boolean_mode` | `transfer_trade_power` |
| `cancel_tributary` | `native_pair_state_selected_mode` | `tributary_state_action` |
| `create_vassal` | `independent_native_command` | `createvassal` |
| `dissolve_alliance` | `native_pair_boolean_mode` | `allianceaction` |
| `join_coalition` | `native_pair_state_selected_alias` | `form_coalition` |
| `kick_from_federation` | `native_pair_boolean_mode` | `invite_to_federation` |
| `kick_from_trade_league` | `native_pair_state_selected_mode` | `invite_to_trade_league` |
| `leave_coalition` | `native_pair_boolean_mode` | `form_coalition` |
| `leave_federation` | `native_pair_boolean_mode` | `request_to_join_federation` |
| `leave_trade_league` | `native_pair_state_selected_mode` | `invite_to_trade_league` |
| `lift_excommunication` | `native_pair_boolean_mode` | `excommunicate_action` |
| `remove_rival` | `independent_native_command` | `remove_rival` |
| `revoke_condottieri` | `native_pair_state_selected_mode` | `condottieri_action` |
| `revoke_embargo` | `native_pair_boolean_mode` | `embargoaction` |
| `revoke_fleet_basing_rights` | `native_pair_boolean_mode` | `offer_fleet_access` |
| `revoke_march` | `native_pair_boolean_mode` | `designate_march` |
| `revoke_military_access` | `native_pair_boolean_mode` | `offermilaccess` |
| `scornful_insult` | `native_pair_derived_field_variant` | `insultaction` |
| `select_rival` | `independent_native_command` | `add_rival` |
| `stop_counterespionage` | `native_pair_boolean_mode` | `counterespionage` |
| `stop_currying_favors` | `native_pair_boolean_mode` | `curry_favors` |
| `stop_supporting_heir` | `native_pair_boolean_mode` | `support_heir` |
| `stop_supporting_rebels` | `native_pair_boolean_mode` | `support_rebels` |

精确 token、虚表、源文件哈希、模式指令、字符串引用、状态谓词和待验证项均保存在机器报告。RVA 只作为离线证据；接口不接受 raw pointer/RVA/脚本。
