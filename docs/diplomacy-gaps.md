# 完整外交接口缺口与研究顺序

更新日期：2026-10-08。对象为本机 EU4 1.37.5、[可重建目录](../bridge/diplomacy_catalog.json)、[外交静态报告](../work/reports/native-diplomacy-1.37.5.json)、[属国交互报告](../work/reports/native-subject-interactions-1375.json)、[特殊命令](native-subject-special-paths-1375.md)和[和平组件](native-peace-catalog-1375.md)。正式外部 API 的已验证执行数仍为 **0**。独立研究实验的各次发送、效果、回复、保存和重载证据由[研究能力清单](diplomacy-research-capabilities.md)单独记录，不能合并为通用执行后端已完成；生命周期和无发送预览不计作执行完成。

## 数量应如何解释

| 范围 | 公开 ID | 有静态原生映射 | 无映射 | `game_key=null` | `partial` 参数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 外交窗口 | 171 | 170 | 1 | 1 | 16 |
| 属国交互 | 44 | 44 | 0 | 0 | 6 |
| 政府机制交互 | 3 | 3 | 0 | 0 | 3 |
| 和平组件 | 54 | 53 | 1 | 1 | 54 |
| 旧版固定实验入口 | 2 | 0 | 2 | 0 | 0 |
| 合计 | 274 | 270 | 4 | 2 | 79 |

274 个 ID 没有重复键。它们并不代表 274 个独立原生类：167 个普通外交静态映射由 **87 个专用 family、40 个共用 `scriptable_diplomatic_action` 的脚本动作、原有 5 个撤销变体和本轮 35 个模式条目**组成，合计使用 88 个 family。45 个公开 ID 现在包含具体模式分支证据，其中蔑视侮辱由派生 index 选择而非 value。4 个旧间谍取消只是原生 UI false 名称分支，实际效果未证。原生报告中的 55 个 64 字节对象也不能直接视为“只填两个国家即可调用”；公共基类还有日期、外交官、模式与内部状态字段。

另有 41 个属国交互单例注册，使用独立 `subject` command，字段为 `native_subject_mapping`；9 个特殊入口使用 7 类独立 0x60 主命令，字段为 `native_special_mapping`，替换宿敌另有条件性的 0x68 命令。幕府 3 项保留 `subject.*` ID，但已更正为 actor 的政府机制，不能接收单一 target。53 个和平 ID 通过 `native_peace_mapping` 对应独立和平工厂的 40 个组件类：33 个同名标识、7 个显示方法别名、13 个脚本定义；一个旧 ID 是兼容别名。四类静态映射共 270 项，都需独立验证生命周期、参数、执行和效果。

79 项 `partial` 之外的 195 项 `specified` 仅表示当前公开请求形状已列出，**没有表示原生参数已验证**。特别是双 TAG 请求可能还依赖战争、外交官任务、第三国、请求响应或脚本定义的身份。

本轮目录 SHA-256 为 `96B312E2304B7B39D4A8F267D63CAD6ACF36E4B68311E7D79836194016AFAB8A`；[39 项静态分类报告](native-diplomacy-modes-1375.md) SHA 为 `1C0FA12B630A134036C32CAF826750CE82608C44FAB80108E6CFD2B738D06676`。它引用固定的旧目录清单，清单不会随着新映射改写，避免目录/报告摘要循环。和平补充报告仍为 `EA894744006119693B3568C08A94D30CB4929ABC2AC792A616C25466C7D608AA`，其字段报告 SHA 为 `CFABB4622B7C82F9E2476A82352F91FA5D0F8BA0F8150E75AAC47FB4AEADDC96`。

## 重复、别名和疑似旧功能

| 条目 | 现有证据与处理 |
| --- | --- |
| `offer_vassalization/cancel_vassalization`、联姻/解除、保独/撤销、改善关系/停止、间谍网/停止 | 5 组有同 family、相反 `value` 的静态证据。保留不同公开 ID；不重复实现独立工厂。联姻取消原脚本 key 是 `break_marriage`，不能仅按相同 `game_key` 统计别名。 |
| `cancel_vassalization` 与 `break_vassalization` | 英文标题都可能是 “Break Vassalization”，方向不同。后者存在原生 false 名称分支，但合法性明确拒绝 actor 是 recipient 附庸，不能建立可用映射。前者保留宗主解除的已有证据；后者不借同名分支或脚本效果冒充完成。 |
| `break_alliance` 与 `dissolve_alliance` | 前者要求目标与第三国断盟，后者解除自己的联盟。`rights_of_man_l_english.yml` 的 `BREAKALLIANCE_DESC/REQDES1` 是第三国语义证据。两者不得合并；旧模组锁前者不能证明锁住后者。 |
| `form_coalition` 与 `join_coalition` | 同一 true 模式读取 target+0x1920：已有包围网选择 JOIN，否则选择 FORM。新增 state_selected_alias_of，必须核对当前状态，不当作无条件别名或第二类对象。 |
| `knowledge_sharing` 与 `subject.knowledge_sharing`；`take_on_debt` 与 `subject.takeondebt` | 同游戏 key、不同窗口/权限来源。属国侧已找到独立单例注册与 subject command；不能以外交 family 的调用证据代替属国命令的验证。 |
| `whitepeace/offer_peace`、`gold/peace.po_gold` | 2 个固定旧版实验入口与通用请求有意并存。前者只允许 FRA→ENG，不能计作本版本额外完成项，也不能当成通用和约参数模板。 |
| `peace.po_change_culture` 与 `peace.po_change_culture_same_culture_group` | 同英文标题，安装脚本是两个独立条款；保留 key，比较条款条件/费用而非按名称去重。 |
| `peace.full_annexation` 与省份条款集合 | 完全吞并可能是 UI 快捷组合或和约判定结果，尚无独立条款对象证据。保持候选；先验证是否展开为 `po_demand_provinces` 的集合。 |
| `peace.po_humiliate` 与 `peace.show_strength` | 组件自己的显示虚方法直接引用 PEACE_SHOW_STRENGTH，故两个 ID 都是“展现力量”，后者标记 alias_of 保留兼容。真正的羞辱宿敌组件 po_humiliate_rival 引用 PEACE_HUMILIATE，不能根据 token 字面混淆。 |
| `subject.allow_settlement_growth/block_settlement_growth` | 源文件声明两个即时交互；是否共享底层状态切换 command 尚未证明。公开 ID 暂保留两个。 |
| 停止伪造宣称、停止制造贸易争端、停止散布不满、停止煽动独立 | 原生名称虚方法确有 value=false→CANCEL 分支，标记 native_ui_cancel_mode_effect_unverified。多个效果函数未见相应 value 分支，尚不能证明存在持续任务或取消既有效果。行政渗透另有 false 描述证据，但也没有实际取消验收。 |

一共存在 39 组重复的非空 `game_key`，均为有意保留的模式、跨窗口条目、兼容别名或固定旧入口；相同英文名共有 7 组。它们是审查线索，不能作为自动合并规则。带拼写问题的安装脚本 key，例如 `demand_sacirifces`、`release_pronia`、`*_influece`，也不能擅自改成无法解析的新游戏 key。

## 静态未映射的 4 项

固定旧基线的 39 个外交 ID 已全部分类，新增 35 个普通模式和 3 个独立 command；只有 break_vassalization 未映射。完整新分类及指令在独立机器报告中；它没有把 UI 模式证明提升为实际效果。当前全目录未映射项如下。

| 范围 | ID |
| --- | --- |
| 附庸主动脱离 | `break_vassalization`：存在同名模式分支，却被已证的 false 合法性拒绝该方向。需追实际 UI 可达条件，不换成宗主解除或宣战。 |
| 和平 UI | `peace.full_annexation`：尚无独立组件证据，需验证是否为省份条款组合及吞并结果判定。 |
| 旧版固定实验 | `whitepeace`、`gold`：保留 1.37.4 固定合同，不能套用本版本 requestpeace/peace.po_gold 静态类后宣称验收。 |

支持独立的请求/提供由 actor 依赖身份选择，不是简单交换 TAG；贸易联盟逐出/退出共用 invite_to_trade_league false，依首位成员身份区分。佣兵撤回/取消依现有租出/租入合同方向区分；朝贡还比较 original 字段，不能盲目将 original 替换为 actor。select_rival 的 replace 分支要求第三个国家身份，create_vassal 要解析无省份国家且可能再发切换玩家命令。这些前提保存为 mode_constraints 或独立 command 证据，仍未形成安全执行合同。

## 参数审计

已有来源证据支持的修正：

- `transfer_trade_power` 增加必填 `trade_power_percent`，公开候选范围为整数 0..100，并从 `specified` 改为 `partial`。`interface/countrydiplomacyview.gui:6972` 的 `TransferTradePowerDialog` 包含 `trade_power_slider`（控件名在 7077 行，min/max/step 为 0/100/1）；这证明需要数值选择，不能证明引擎实际允许全部滑块范围。目录保存该控件证据。原生 `amount` 的定点数转换、百分比单位及额外 flag 仍需绑定。
- `subject.fortify_march` 增加必填 `province_id`，维持 `partial`。`localisation/common_sense_l_english.yml:842` 的 `FORTIFY_MARCH_EFFECT` 与 1349 行 `fortify_march_desc2` 明确引用选定省份；堡垒级别、费用和目标省份句柄尚未绑定。
- `peace.give_up_claims` 改用暂定 `claims_against` 国家 TAG，拒绝旧 province_ids 数组：组件有一个 taker 国家句柄，原生 tooltip 明确是放弃某国境内全部宣称。国家方向到原生字段的绑定仍未验证。
- 特殊命令明确军事方针 `no_focus=0/aggressive=1/supportive=2/passive=3/defensive=4/siege=5`，贡品 `none=0/cash=1/adm=2/dip=3/mil=4/manpower=5`；列表显示顺序不能当作编码。释放殖民领的 play_as_released=true 需要后续独立 set_controller，不能当作同一命令的布尔字段，也没有原子性证明。

当前所有非和平 `partial`：

| ID | 尚需补全的合同 |
| --- | --- |
| `declare_war` | 无 CB 情况、战争目标是否可空、参战者/共同交战者/召盟选项及 CB 实例绑定；不能要求所有战争都有目标省份，也不能把旧 FRA→ENG 样例泛化。 |
| `offer_peace` | 当前只有 `war_id/offer_mode`，没有 `terms` 组合或 giver/taker/谈判方身份；尚不能描述一份通用和约。 |
| `offer_condottieri` | 部队稳定 ID、租金单位、可出租兵力、合同标志与召回方向。 |
| `sell_ships` | 舰队/舰船选择、拆分规则、价格单位和接收后的对象身份。 |
| `support_rebels` | 叛军派系实时标识、资助金额/期限由谁选择及到期/取消语义。 |
| `transfer_trade_power` | 百分比到引擎数值的转换、有效范围、方向和额外模式位。 |
| `select_rival` | 新选/替换槽位、已满槽位行为、替换成本与事件路径。 |
| `scornful_insult` | 侮辱类型/文本选择与普通 `insultaction` 的关系。 |
| `create_vassal` | 被释放国家、释放省份集合和国家尚不存在时的标识；通用 target TAG 不能自动证明能绑定活国家句柄。 |
| `remove_rival` | 现有宿敌关系、成本和控制者权限；独立命令 gate 不能替代完整 UI 约束。 |
| 四个 `cancel_*` 旧间谍 UI 模式 | 伪造宣称/制造贸易争端/散布不满/煽动独立的 false 名称已证，但实际取消效果未证。 |
| `break_vassalization` | 目标方向遭已证原生合法性拒绝；没有被证明可调用的替代路径。 |
| `confirm_tribute_action` | 原生待响应贡品请求身份、接受/拒绝方向和具体贡品内容。 |
| `subject.customize_subject` | 名称/颜色/旗帜等 UI 字段及其实际可修改范围。 |
| `subject.fortify_march` | 省份、堡垒升级目标、成本和有效性。 |
| `subject.grant_core_claim` | 省份之外的核心/宣称模式、适用属国类型与获得方。 |
| `subject.start_colonial_war` | 敌国、CB、战争目标和殖民国参战身份。 |
| `subject.upgrade_subject_type` | 新属国类型、所需选项、费用及既有依赖关系迁移。 |
| `subject.release_colony` | 释放和切换玩家是两次命令，需分别核验结果、部分完成和身份重绑定。 |
| `subject.expel_ronin / subject.sankin_kotai / subject.sword_hunt` | actor 政府机制及交互定义 ID 的实时解析、脚本实际筛选对象和权限；参数仅 actor，禁止 target。 |

所有 54 个和平 ID 维持 `partial`：共同缺口是战争/谈判上下文、条款给付方与受益方、原生对象所有权和组合约束。53 个静态映射暴露序列化字段，不能直接当作公开参数 setter。giver+0x22 未对齐且不同于 offer_giver；province_id/region/type 的实例字段实际保存对象或定义指针。条款无额外选项并不意味着可以独立发出外交消息。

仍标 `specified`、但应优先复核的字段包括：`call_to_arms.promise_land` 的反向布尔存储；`enforce_peace/intervene_in_war` 的战争与阵营；`fabricate_state_claim.area_id` 与原生省份/地区选择；赠款/贷款/补贴/价格的单位和边界；`return_core_favor` 的核心受益国；`subject.force_isolation.direction` 是否真由用户选择；军事方针/贡品的调用者权限和句柄绑定。上述条目在证据补齐前仍不可提交，不能因为 `specified` 就采用默认原生字段值。

## 可执行的研究优先级

下面每一行先产出可复现静态证据和字段合同，再走“对象生命周期 → 无发送合法性 → 有请求身份的提交 → 原生接受/拒绝 → 状态核对/保存重载”。任一阶段缺失均不能把整个动作标为 execution verified。五核心研究实验按具体请求单独记录，不在下表合并计为通用动作完成量。

| 顺序 | 范围与对象 | 下一个可执行研究任务 | 通过门槛 |
| --- | --- | --- | --- |
| P0 | 通用传输、响应与身份 | 将 command 状态、原始 actor/recipient、活国家完整句柄、外交官和关系冷却绑定到请求 ID；区分“合法”“已提交”“待回复”“拒绝”“已结算”。补异步接受/拒绝与取消待发送提议入口。 | 同一请求不可重复扣成本；失败不伪报成功；接收方/请求身份不因 TAG 切换或旧句柄复用而串线。 |
| P1-1 | 联盟：`allianceaction`，解除本国联盟 | false→BREAKALLIANCENEWDESC 已直接绑定，下一步追实际效果及接受路径、外交关系槽位和对象所有权。不要走第三国 break_alliance。 | 形成有向 offer/accept/decline/dissolve 矩阵，正反关系双方一致，撤销后持久化；拒绝与已有联盟场景不产生新关系。 |
| P1-2 | 军事/舰队通行：`milaccess/offermilaccess/fleet_access/offer_fleet_access` | 四种 false 方向已各自绑定类内描述分支，下一步核对构造、当前关系身份、合法性与实际移除；区分有条件通行与直接协议。 | 8 个公开 ID 各有明确 grantor/grantee 语义和合法性原因；取消不会误撤反方向通行，关系快照与原生界面相符。 |
| P1-3 | 支持独立：`support_independence_action` 和 3 个角色模式 | 请求/提供由 actor 的宗主与 dependency definition+0x11a 选择，value 控制正反模式；据此建立有界身份绑定，再核两方关系与独立战争触发。 | 正向、请求、撤销两个方向均有独立证据；独立战争触发时支持关系的参战效果得到核对。 |
| P1-4 | 宣战和参战：`declarewar/callaction/enforce_peace/intervene_in_war/unconditional_surrender` | 按派生 parser 字段逐项绑定 CB、war goal、参战国、原生战争标识和布尔选项；补无 CB/无省份目标的合同分支，隔离旧固定实验。 | 能描述至少无 CB、收复核心及多方参战三种不同请求；错战争/错阵营明确拒绝；每方战争列表、费用、休战破坏影响和保存重载一致。 |
| P1-5 | 和约：`requestpeace` 与 54 个公开条款 ID | 独立工厂 0x99ff90、40 个组件和脚本定义注册已静态对应；下一步定位 owned offer 的构造/销毁、战争/谈判方绑定，从空条款白和和金币开始。核 giver/offer_giver/offer_taker/taker，再加入割地/返还核心/释放。完全吞并保持未决。 | 条款 getter/setter、成本和接受判断一致；被拒绝不结算，接受后战争结束/休战/金币/省份/依赖关系均准确；多边分账与保存重载通过。 |
| P1-6 | 附庸主动独立、吞并/整合/卫戍国/朝贡 | BREAKVASSAL 的同名 false 分支被合法性拒绝，需追真正 UI 可达条件；与独立战争和 peace.po_independence 区分。其余四类撤销模式已绑定，下一步核 current relation、original 和派生对象及实际效果。 | 宗主取消、附庸脱离、战争争取独立、释放新附庸成为四条独立合同；不得将 vassal false 直接用于全部场景。 |
| P2-1 | 间谍行动 | 依次核对 `fabricate_claim/claim_states`、`counterespionage`、`support_rebels`、`stealmap`，再处理 sabotage/corrupt/slander/infiltrate/sow/agitate/justify；以网点消耗、目标对象和外交官占用判别持续任务/瞬时效果。 | 每项记录解锁条件、网点/金币成本、有效对象、持续期和效果；旧取消标题被确认为可达分支或被正式降为历史候选。 |
| P2-2 | 数值经济与第三国 | 先 gift/subsidy/loan/trade power，再 sell province/ships/condottieri；第三国 `break_alliance/break_alliance_favor/reduce_relations_favor` 查第三国完整句柄，`return_core_favor` 查受益国与省份。 | 数值单位逐字段定义，舍入/溢出/最小最大值可测试；第三国不能等于错误一方；拒绝、到期、撤销和资金/关系变化符合原生结算。 |
| P2-3 | 属国交互 44 项及政府机制 3 项 | 静态已有 41 单例/common0xa0 路径和 6 个特殊入口/4 主命令。下一步验证 borrowed singleton 与 command 所有权、派生字段和调用者权限；先六个持续开关，再省份/军事方针/贡品/自定义。幕府走 actor 政府机制定义，不逐个 target。 | 逐类型原生合法性与实际效果一致；修改对象确为 actor 的适用属国，连续切换不重复收费；释放切换玩家按两次提交处理，读回与重载通过。 |
| P3 | 40 个脚本外交动作及组织/教廷/HRE 余项 | 绑定 `scriptable_diplomatic_action` 的实际定义对象、脚本 scope 与原生 acceptance；逐个评估 DLC/改革/任务触发，追剩余组织加入/退出/逐出方向。 | 只允许已枚举且有源哈希的脚本定义，不接受任意脚本输入；每项可见性、成本和结果有独立证据。 |

属国持续开关当前为 `subsidize_armies/scutage/embargo_rivals/support_loyalists/send_officers/divert_trade`。不把它们与即时的允许/禁止殖民地发展按钮混为一类。[派生字段报告](native-action-fields-1375.md)已给出普通外交和 40 个和平组件的 parser/serializer token→offset→类型证据，接下来应逐项绑定公开合同与运行对象；clone 读取宽度只证明存储形状，不能独立证明字段含义。

## 完整性仍需单独验收

目录扫描目前限定安装本体脚本、所选本地化和 GUI。解包的 64 个 ZIP、启用 Mod 的最终覆盖顺序、DLC 许可、存档条件还没有合并成有效配置；[解包工具](../tools/unpack_game.py)只解决来源归档。不能把压缩包全部覆盖到一个目录后声称得到真实加载配置。

完整目标还要求原生 AI 外交权限隔离、输入事件/决议造成的外交变化边界、外国信息可见性过滤、长期运行和异常恢复。这些不会因为 274 个 API 名称而自然完成。API 能枚举/校验请求、对象可创建、预览合法、正式结算成功应分别统计。

重建与回归命令：

```powershell
python -B tools/build_diplomacy_catalog.py
python -B tools/build_diplomacy_catalog.py --check
python -B work/trace_diplomacy_modes.py --check
python -B -m unittest bridge.tests.test_diplomacy_catalog -v
```

本轮新增参数回归同时验证：不会把无关同名 slider 当成证据；比例和省份选择不会被请求形状丢失；二者继续 `partial/unimplemented`，没有从 GUI 或本地化提升为原生映射。
