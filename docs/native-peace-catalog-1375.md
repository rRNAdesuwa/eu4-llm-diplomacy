# 1.37.5 和平条款静态目录闭合

本报告只读解析精确 SHA 的 EXE、字段报告和已解包游戏源文件，没有打开游戏进程。可复现：`python work/trace_peace_catalog.py --check`；省略路径按 local.env 读取。

游戏 SHA-256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。字段报告 SHA-256：`cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96`。
报告自身 SHA 随目录合并时钉扎在 build_diplomacy_catalog.py；修改证据后必须重新审查。

独立的和平组件工厂为 `0x99ff90`，包含 40 个 case。不要调用普通外交工厂 `0x35d210` 来构造它们。组件必须装入具备正确战争、谈判方和所有权的和约；这里没有实现发送接口。

## 名称与扫描修正

7 个原本只有本地化的旧 ID 由各组件 vtable+0x100 的直接字符串引用闭合。保留旧 ID：`peace.show_strength` 是 `peace.po_humiliate` 的兼容别名，两者均为展现力量；真正的羞辱宿敌组件是 `po_humiliate_rival`。公共 ID 个数不等于独立组件个数。

补充 `peace.po_transfer_vassals`：源文件已有 7 个 attacker_disabled_po 引用，旧扫描器漏读这个容器。禁用集合只证明标识存在，不能作为可执行条件。`peace.po_enforce_military_access` 与 `peace.revoke_reform` 由原生显示方法和本地化共同证明；后者是和约要求撤销帝国改革，与皇帝自愿撤销操作区分。

| 公开 ID | 和平组件 | 原生显示 key | +0x100 方法 |
| --- | --- | --- | --- |
| `peace.give_up_claims` | `po_give_up_claim` | `PEACE_GIVE_UP_CLAIMS` | `0x9b5db0` |
| `peace.war_reparations` | `po_war_reparations` | `WAR_REPARATIONS` | `0x9b66d0` |
| `peace.enforce_fleet_basing_rights` | `po_enforce_fleet_basing_rights` | `ENFORCED_FLEET_BASING_RIGHTS` | `0x9c0440` |
| `peace.concede_colonial_region` | `po_concede_colonial_region` | `PEACE_CONCEDE_COLONIAL_REGION` | `0x9c8180` |
| `peace.end_rivalry` | `po_end_rivalry` | `PEACE_END_RIVALRY` | `0x9ca180` |
| `peace.pillage_capital` | `po_pillage_capital_state` | `PEACE_PILLAGE_CAPITAL_STATE` | `0x9b19f0` |
| `peace.show_strength` | `po_humiliate` | `PEACE_SHOW_STRENGTH` | `0x9bc880` |
| `peace.po_enforce_military_access` | `po_enforce_military_access` | `ENFORED_MILITARY_ACCESS` | `0x9bfef0` |
| `peace.po_transfer_vassals` | `po_transfer_vassals` | `PEACEOFFER_TRANSFER_TXT` | `0x9cd690` |
| `peace.revoke_reform` | `revoke_reform` | `DEMAND_REVOKE_REFORM` | `0x9bdc20` |
| `peace.po_humiliate_rival` | `po_humiliate_rival` | `PEACE_HUMILIATE` | `0x9bc2a0` |

## 脚本和平专属路径

可见脚本定义 13 个。`/peace_treaties` → loader `0x9d2c90` → registry `0x242bd80` → `0x9d33d0` 按根名称注册定义；descriptor case=39/+8 定义指针 → 和平工厂 case39 的 component+0x30。parser `0xac9a30` 的 type 查同一 registry，serializer `0xac9be0` 使用 definition+0x10 名称。这个共享 token 虽也叫 scriptable_diplomatic_action，却具有独立 vtable、字段、工厂和定义注册表。

解包审计覆盖 18 个 CB/war-goal/peace 源文件，匹配安装目录；这些目录的归档新增文件为 0。整个游戏的 MOD/DLC 覆盖和活动载入顺序仍未解析。明确 is_visible always=no 的定义保留为排除项。

## 字段与未知项

基础字段分别为 offer_giver+0x10、offer_taker+0x18、is_selected+0x20、**未对齐 giver+0x22**。不能把 giver 与 offer_giver 合并，不能假定 actor/target 就是其顺序。割地/撤销核心/归还核心的 province_id 实际存省份对象指针；殖民地区存定义指针，脚本和平 type 也存定义指针，外部整数或字符串不能直接写入。金币 value 为 4 字节有符号定点 ×1000，公开金额上下限/步进尚待原生校验。

`peace.give_up_claims` 的额外国家字段和文案明确是放弃某国境内全部宣称，旧 province_ids 数组没有证据，改为暂定 claims_against TAG。所有条款 parameter_status 继续 partial，public_parameter_binding_verified=false；没有将序列化字段当成完成的请求适配器。

- Owned peace-offer construction, war and current negotiator identity, component ownership and disposal are unverified.
- Native giver/offer_giver/offer_taker/taker roles have not been bound to public actor/target fields.
- Full annexation is not mapped to an independent factory class; no composite implementation is inferred.
- No legality, acceptance, application, persistence or runtime visibility is established by this report.

全部 runtime_verified/execution_verified=false。保存重载、AI 接受、和平结算和完整外交覆盖均未因此完成。
