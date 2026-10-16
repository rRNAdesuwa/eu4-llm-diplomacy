# 1.37.5 TAG 外交接口动作清单

本表由 `python -B tools/build_tag_command_reference.py` 从当前已编译注册表生成。`--check` 只核对文件。动作均只接收 `request_id/action/actor/target`，发起国可为 AI。

本轮八类目录共 147 项：120 个绑定、27 个排除项。宣战、议和不在范围内。绑定表示代码通路已编译，不表示游戏接受或效果已通过。

构建：`bridge/native/tag_diplomacy_1375_v31/build-7/build/build.json`。
Manifest SHA-256：`d4b3069cfac70cf9ff8e1270733ad64592c3d545a6d005fd0ed8b26c6070728a`。
注册表 SHA-256：`dfcd2cf16b7a6198dd9fc6ea619a0bad54ee58750a70a676f866be827c3771fb`。

| 类别 | 绑定数 | 排除数 |
| --- | ---: | ---: |
| 盟约 | 17 | 0 |
| 影响 | 43 | 3 |
| 关系 | 5 | 1 |
| 王室 | 9 | 0 |
| 秘密行动 | 18 | 9 |
| 经济行动 | 12 | 11 |
| 通行权 | 8 | 0 |
| 人情 | 8 | 3 |

实际测试状态取自 `work/runtime/tag31-integration-final-20261013.json`，只表示这一轮已授权拉通批次的发送情况，不覆盖历史效果记录。
证据 SHA-256：`704e9106db4eaf8ffd2a5eb9e23055862a7529130ebed3c54bd49cf82c2936ee`。

合计41次派发、77次条件/预检拒绝、2项未知；完整效果验收未通过。具体存档变化及未通过项见[拉通记录](tag-command-integration-1375.md)。

本轮只沿已审计的未领取请求继续；已进入、被拒、已提交或未知的请求均未重发。表中状态属于同一次最终拉通的各段合并结果。后续开发测试只允许完整审计证明未发送、清理闭合的正常拒绝动作使用新ID；历史成功、已派发及未知动作仍封禁，不重新运行全量批次。

原生条件仍由工厂、full+88、command gate 及发送前检查裁定；测试 Mod 的脚本条件放开不能保证绕过硬编码条件。精确脚本条款和局部原生检查线索见[条件查询](tag-command-conditions-1375.md)，可用CLI `conditions --action <action>`或HTTP `GET /native/v1/conditions/{action}`读取。百科直读仍失败，搜索缓存中的旧版说明仅作核对线索。

## 盟约

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `form_coalition` | `form_coalition` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `support_independence` | `support_independence_action` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `ask_support_independence` | `support_independence_action` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `cancel_offered_independence_support` | `support_independence_action` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `cancel_requested_independence_support` | `support_independence_action` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `dissolve_alliance` | `allianceaction` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `invite_to_federation` | `invite_to_federation` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `invite_to_trade_league` | `invite_to_trade_league` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `join_coalition` | `form_coalition` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `kick_from_federation` | `invite_to_federation` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `kick_from_trade_league` | `invite_to_trade_league` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`lease_precondition_rejected` |
| `leave_coalition` | `form_coalition` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `leave_federation` | `request_to_join_federation` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `leave_trade_league` | `invite_to_trade_league` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`lease_precondition_rejected` |
| `offer_alliance` | `allianceaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `request_to_join_federation` | `request_to_join_federation` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `request_to_join_trade_league` | `request_to_join_trade_league` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |

## 影响

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `offer_vassalization` | `vassalaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_vassalization` | `vassalaction` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `guarantee` | `guaranteeaction` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `revoke_guarantee` | `guaranteeaction` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `annex_vassal` | `annexationaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `ask_for_march` | `ask_for_march` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `ask_to_be_tributary` | `ask_for_tributary_state_action` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `call_eyalet_into_wars` | `scriptable_diplomatic_action` | `call_eyalet_into_wars` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `call_trade_protectorate_into_wars` | `scriptable_diplomatic_action` | `call_trade_protectorate_into_wars` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_annexation` | `annexationaction` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_tributary` | `tributary_state_action` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `convert_to_core_personal_union` | `scriptable_diplomatic_action` | `convert_to_core_personal_union` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `convert_tributary_to_vassal` | `convert_tributary_to_vassal` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `create_european_colony` | `scriptable_diplomatic_action` | `create_european_colony` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `create_pronoia` | `scriptable_diplomatic_action` | `create_pronoia` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `create_soyurghal` | `scriptable_diplomatic_action` | `create_soyurghal` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `demand_sacrifices` | `scriptable_diplomatic_action` | `demand_sacrifices` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `designate_march` | `designate_march` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `dissolve_protectorate` | `scriptable_diplomatic_action` | `dissolve_protectorate` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `elevate_influenced_country_to_vassal` | `scriptable_diplomatic_action` | `elevate_influenced_country_to_vassal` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `establish_tributary` | `tributary_state_action` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `grant_autonomy_to_core_eyalet` | `scriptable_diplomatic_action` | `grant_autonomy_to_core_eyalet` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `grant_war_rights` | `scriptable_diplomatic_action` | `grant_war_rights` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `incorporate_vassal` | `scriptable_diplomatic_action` | `incorporate_vassal` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `invite_into_cultural_sphere_of_influence` | `scriptable_diplomatic_action` | `invite_into_cultural_sphere_of_influence` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `invite_to_zoroastrian_community` | `scriptable_diplomatic_action` | `invite_to_zoroastrian_community` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `join_cultural_sphere_of_influence` | `scriptable_diplomatic_action` | `join_cultural_sphere_of_influence` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `leave_the_cultural_sphere_of_influece` | `scriptable_diplomatic_action` | `leave_the_cultural_sphere_of_influece` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `make_pronoia_inheritable` | `scriptable_diplomatic_action` | `make_pronoia_inheritable` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `mam_sponsor_hajj` | `scriptable_diplomatic_action` | `mam_sponsor_hajj` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `offer_protectorate` | `scriptable_diplomatic_action` | `offer_protectorate` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `promote_appanage_heir` | `scriptable_diplomatic_action` | `promote_appanage_heir` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `promote_primary_culture` | `scriptable_diplomatic_action` | `promote_primary_culture` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `promote_vassal_to_eyalet` | `scriptable_diplomatic_action` | `promote_vassal_to_eyalet` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `reign_in_eyalet` | `scriptable_diplomatic_action` | `reign_in_eyalet` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `release_nahuatl_tributary` | `scriptable_diplomatic_action` | `release_nahuatl_tributary` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `release_pronia` | `scriptable_diplomatic_action` | `release_pronia` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `release_soyurghal` | `scriptable_diplomatic_action` | `release_soyurghal` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `remove_them_from_cultural_sphere_of_influece` | `scriptable_diplomatic_action` | `remove_them_from_cultural_sphere_of_influece` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `request_protectorate` | `scriptable_diplomatic_action` | `request_protectorate` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `revoke_march` | `designate_march` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `revoke_war_rights` | `scriptable_diplomatic_action` | `revoke_war_rights` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `warn` | `warningaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |

## 关系

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `improve_relations` | `improve_relation` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `stop_improving_relations` | `improve_relation` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `insult` | `insultaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `select_rival` | `add_rival` | `独立命令` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `remove_rival` | `remove_rival` | `独立命令` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |

## 王室

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `royal_marriage` | `royal_marriage` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `break_marriage` | `royal_marriage` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `abandon_union` | `abandon_union` | `true` | 冻结，禁止重发：`synthetic_exception_no_guessed_cleanup` |
| `cancel_integration` | `integrationaction` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `claim_throne` | `claimaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `heathen_royal_marriage` | `scriptable_diplomatic_action` | `heathen_royal_marriage` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `integrate_union` | `integrationaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `stop_supporting_heir` | `support_heir` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `support_heir` | `support_heir` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |

## 秘密行动

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `build_spy_network` | `spy_network` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `stop_building_spy_network` | `spy_network` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `agitate_for_liberty` | `agitate_for_liberty` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_infiltration` | `infiltrate_administration` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `corrupt_officials` | `corrupt_officials` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `counterespionage` | `counterespionage` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `fabricate_ottoman_invasion_cb` | `scriptable_diplomatic_action` | `fabricate_ottoman_invasion_cb` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `fabricate_spread_the_true_faith_cb` | `scriptable_diplomatic_action` | `fabricate_spread_the_true_faith_cb` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `fabricate_tributary_cb` | `scriptable_diplomatic_action` | `fabricate_tributary_cb` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `infiltrate_administration` | `infiltrate_administration` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `justify_trade_conflict` | `justify_trade_conflict` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `sabotage_recruitment` | `sabotage_recruitment` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `sabotage_reputation` | `sabotage_reputation` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `send_royal_ambassador` | `scriptable_diplomatic_action` | `send_royal_ambassador` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `slander_merchants` | `slander_merchants` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `sow_discontent` | `sow_discontent` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `steal_modern_ideas` | `scriptable_diplomatic_action` | `steal_modern_ideas` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `stop_counterespionage` | `counterespionage` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |

## 经济行动

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `ask_knowledge_sharing` | `ask_knowledge_sharing` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_steer_trade` | `steer_trade` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_subsidies` | `warsubsidy` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_trade_power_transfer` | `transfer_trade_power` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `embargo` | `embargoaction` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `knowledge_sharing` | `knowledge_sharing` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `mam_export_grain` | `scriptable_diplomatic_action` | `mam_export_grain` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `request_access_to_modern_ideas` | `scriptable_diplomatic_action` | `request_access_to_modern_ideas` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `revoke_embargo` | `embargoaction` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `sell_indulgence` | `scriptable_diplomatic_action` | `sell_indulgence` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `share_modern_ideas` | `scriptable_diplomatic_action` | `share_modern_ideas` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `steer_trade` | `steer_trade` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |

## 通行权

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `offer_fleet_basing_rights` | `offer_fleet_access` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `ask_fleet_basing_rights` | `fleet_access` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `ask_military_access` | `milaccess` | `true` | 冻结，禁止重发：`guard_before_initialize` |
| `cancel_fleet_basing_rights` | `fleet_access` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `cancel_military_access` | `milaccess` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `offer_military_access` | `offermilaccess` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `revoke_fleet_basing_rights` | `offer_fleet_access` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `revoke_military_access` | `offermilaccess` | `false` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |

## 人情

| action | 原生族 | 模式/定义 | 本轮状态 |
| --- | --- | --- | --- |
| `curry_favors` | `curry_favors` | `true` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `stop_currying_favors` | `curry_favors` | `false` | 已提交，接受/效果见独立观测：`normal_dispatch_slot_consumed` |
| `trade_favors_for_gold` | `trade_favors_for_gold` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `trade_favors_for_men` | `trade_favors_for_men` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `trade_favors_for_sailors` | `trade_favors_for_sailors` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `trade_favors_for_trust` | `trade_favors_for_trust` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `trade_favors_for_war_prep` | `trade_favors_for_war_prep` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |
| `trade_favors_for_heir` | `trade_favors_for_heir` | `true` | 游戏条件/预检拒绝，原请求禁止重发：`full88_normal_false` |

## 排除项

以下标签不出现在接口 actions 中；提交会在发布前被拒绝。

| action | 类别 | 原因 |
| --- | --- | --- |
| `break_alliance_favor` | 人情 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `break_vassalization` | 影响 | 已检查的原生分支拒绝该发起方向，替代通路未证实 |
| `cancel_agitate_for_liberty` | 秘密行动 | 只有旧取消文案，尚未证实可取消的任务和效果 |
| `cancel_condottieri` | 经济行动 | 需要绑定已有单位、叛军派系或省份对象 |
| `cancel_fabricate_claim` | 秘密行动 | 只有旧取消文案，尚未证实可取消的任务和效果 |
| `cancel_justify_trade_conflict` | 秘密行动 | 只有旧取消文案，尚未证实可取消的任务和效果 |
| `cancel_sow_discontent` | 秘密行动 | 只有旧取消文案，尚未证实可取消的任务和效果 |
| `charter_company` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `confirm_tribute_action` | 影响 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `create_vassal` | 影响 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `fabricate_claim` | 秘密行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `fabricate_state_claim` | 秘密行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `give_subsidies` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `offer_condottieri` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `offer_loan` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `reduce_relations_favor` | 人情 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `request_maps` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `return_core_favor` | 人情 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `revoke_condottieri` | 经济行动 | 需要绑定已有单位、叛军派系或省份对象 |
| `scornful_insult` | 关系 | 需要选择侮辱定义 |
| `sell_province` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `sell_ships` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `send_gift` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `steal_maps` | 秘密行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `stop_supporting_rebels` | 秘密行动 | 需要绑定已有单位、叛军派系或省份对象 |
| `support_rebels` | 秘密行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |
| `transfer_trade_power` | 经济行动 | 需要省份、第三国、数量等额外参数，按本轮范围延期 |

关于同名取消分支、附庸主动解除方向的证据，见 [原生模式分类](native-diplomacy-modes-1375.md) 和 [取消动作合同](native-pair-cancel-1375.md)。
