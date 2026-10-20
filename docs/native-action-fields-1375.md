# EU4 1.37.5 外交派生参数静态证据

本报告覆盖已有清单的 88 个原生外交类，包括五个核心类之外的 83 类；检查了全部不同的序列化/字段解析入口。33 个类的分配尺寸大于基础对象 `0x40`。新报告包含 63 条动作级派生 token 映射、贡品与和平请求的嵌套对象、40 个和约组件工厂分支，以及战争目标对象的一组具体字段。

这是**静态字段证据**，不是完整、可直接执行的外交 API schema。所有 `runtime_verified` 均为 `false`；本工作没有访问游戏进程，没有更改当前研究 DLL，也没有改变目录或接口的执行状态。

报告：[`work/reports/native-action-fields-1375.json`](../work/reports/native-action-fields-1375.json)。可重复工具：[`work/map_diplomacy_fields.py`](../work/map_diplomacy_fields.py)。原始动作清单 [`native-diplomacy-1.37.5.json`](../work/reports/native-diplomacy-1.37.5.json) 保持不变。

## 构建与可复现性

- 本机 `eu4.exe` SHA256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。
- 输入原生清单 SHA256：`c64df6e043c9e7a498a25082e0e768902764e4a271ab3579f0eaddb2f1391633`。
- 报告 SHA256：`cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96`。
- 工具只读磁盘 PE，按指定函数建立有界可达指令图；每个入口限制 16 KiB 地址窗口、4,000 条指令，单进程 768 MiB 内存保护。本次包含 141 个入口、23,144 字节指令（共享路径可能重复计数），峰值提交内存约 88 MiB。
- 普通遍历不会猜测间接分支。和平工厂的 40 项跳转表、战争目标 token 表是单独读取并验证的有界数据。

在仓库根目录运行：

```powershell
python work/map_diplomacy_fields.py --exe ..\eu4.exe --deps-dir "$env:TEMP\eu4-native-analysis-deps"
python -m py_compile work/map_diplomacy_fields.py
```

只查看某一入口：

```powershell
python work/map_diplomacy_fields.py --deps-dir "$env:TEMP\eu4-native-analysis-deps" --print-rva 0x5476e0
```

工具中的 token 注释明确标为候选；任意立即数都可能碰巧等于 token。最终 `derived_fields` 使用经过人工检查的比较、控制流、目标字段地址与序列化证据，没有把所有立即数自动解释为字段。

## 可消费的报告结构

`actions[]` 按原生名称列出 vtable、分配尺寸、parser/serializer RVA、`derived_fields`、尚未对应序列化字段的 clone 访问候选及已知模式证据。每个字段提供 `token_name`、`token_id`、descriptor RVA、`object_offset`、`width_bytes`、存储表示、解析证据指令 RVA。`functions["0x..."]` 保留对应机器字节、反汇编和分支边，可以复核链条。

`embedded_objects[]` 是贡品与和平请求内部对象。`peace_components[]` 是 40 个独立和约组件，含实际工厂 case、跳转表项、分配候选尺寸、vtable 和 token getter。`peace_component_base_fields` 是这些组件的公共字段。`war_goal_object` 是宣战指向的战争目标对象，当前明确检查了 `take_colony` 的 vtable 示例；未声称每个战争目标子类的完整布局一致。

字段宽度指进程对象中的存储宽度，**不是网络协议或存档占用字节数**。向量的 24 字节是 begin/end/capacity 三个指针；嵌套对象也不能按同等长度的外部数组写入。全部 `public_parameter_schema_complete` 保持 `false`。

## 数值、国家、省份的必要区分

`0x170f620` 解析十进制固定点：`0x170f670` 与 `0x170f6f7` 将整数部分乘 `1000`，结果写入 4 字节有符号整数；最多合入三位小数。`0x246bc0` 序列化时反向分解整数与小数。这确认了内部 `raw = decimal × 1000`，但不证明对应 UI 的百分比含义、范围或日期单位。

| 动作 | 已确认的派生字段（相对动作起点） | 表示 |
|---|---|---|
| `giftaction` | `money +0x40` | 4B 固定点 ×1000 |
| `warsubsidy` | `amount +0x40`; `duration +0x44` | 固定点；4B 整数，时间单位待证 |
| `offerloan` | `amount +0x40`; `interest +0x44`; `duration +0x48` | 金额为原始整数；利息固定点；期限整数 |
| `sellprov`, `charter_company` | `amount +0x40`; `province +0x44` | 两者均为 4B 整数 |
| `transfer_trade_power` | `amount +0x40` | 固定点；UI 百分比到此字段的换算仍需调用者证据 |
| `trade_favors_for_trust` | `favors +0x40`; `trust_value +0x44` | 固定点；4B 整数 |
| `condottieri_action` | `cost +0x40`; `unit +0x48`; `subunit_limit +0x5c` | 固定点；16B 引用包装；4B 整数 |
| `sell_ships_action` | `amount +0x40`; `unit +0x48` | 原始整数；16B 引用包装 |
| `break_alliance`, `break_alliance_favor`, `reduce_relations_favor` | `third_party +0x40` | 完整 8B 国家句柄 |
| `return_core_favor` | `province +0x40`; `tag +0x44` | 4B 省份编号；未对齐的 8B 国家句柄 |
| `threaten_war` | `province +0x40`; `taker +0x44` | 4B 省份编号；未对齐的 8B 国家句柄 |
| `enforce_peace`, `intervene_in_war` | 同名 token 位于 `+0x40` | 国家句柄，不能命名为数字 war ID |
| `claim_states`, `fabricate_claim` | `province +0x40` | 8B **省份对象指针**；解析编号后查 DB |
| `demand_unlawful_territory_action` | `province_id +0x40` | 4B 整数 |
| `sharemap`, `stealmap` | `region +0x40` | 4B 整数，枚举和界限待证 |
| `support_rebels` | `rebel +0x40` | 接收国叛军派系指针，通过两 DWORD 身份查找 |
| `insultaction` | `index +0x40` | 4B 整数，索引语义/范围待证 |
| `appoint_cardinal` | `curia_treasury +0x40` | 1B bool |
| `invite_to_federation` | `name +0x40` | 32B 引擎字符串 |
| `tributary_state_action` | `reason +0x40` | 4B 枚举，取值未确认 |
| `royal_marriage` | `force +0x60` | 1B 内部标志，不应自动作为普通公开参数 |

单位引用解析器 `0xcd990` 在 `0xcd9f7` 写入 16 字节：空的缓存指针与 8 字节对象身份。它既不是裸单位指针，也不是单位编号。`condottieri_action` 的序列化函数还会刷新自身 `+0x48` 缓存；不能把序列化函数当作绝对只读的任意线程检查。

叛军解析器 `0x584420` 从目标国 `+0xe68..+0xe70` 列表查找对象，比较派系 `+0x10/+0x14` 两个 DWORD，成功才将指针存入动作 `+0x40`。这不足以直接接受一个 rebel type 字符串。

## 参战与宣战

`callaction` 有第三国 `versus +0x40`、`replace +0x49`、`call_ally_type +0x4c` 和国家句柄向量 `specific_enemies +0x58`。`call_ally_type` 的枚举值仍未确认。

以下字段内部值与序列化 bool **反向**：`defensive_war_with +0x48`、`autojoin +0x50`、`full_ally +0x51`、`union +0x52`、`promised_land +0x53`、`ignore +0x56`。例如序列化 `0x543a70` 比较 `+0x48` 后 `sete`，解析对应分支也取反。把外部 true 直接写入 1 会改变含义。

`declarewar` 的 `stability +0x40`、`succession +0x41`、`colonialwar +0x42` 是普通 bool；`attacker +0x50`、`promised_land +0x68`、`full_ally +0x80` 都是国家句柄向量。`attacker_call_all` token 被解析器接受，但检查路径只验证 yes/no，没有找到对应写入；不能给它发明字段。

`declarewar +0x48` 是通过 `0xd9b740` token→枚举和 `0xd9b080` 工厂创建的多态战争目标指针，不能写 CB 字符串。已确认 11 个原生目标 token：`take_colony`、`take_core`、`take_border`、`take_province`、`take_capital`、`defend_capital`、`defend_country`、`naval_superiority`、`superiority`、`take_region`、`blockade_ports`。

战争目标 parser `0xd9c0d0` 的具体字段如下，偏移相对战争目标对象：

| token | 偏移 | 表示 |
|---|---:|---|
| `type` | `0x10` | 战争目标定义指针，由名字查询 |
| `province` | `0x18` | 4B 省份编号 |
| `tag` | `0x1c` | 8B 国家句柄 |
| `region` | `0x28` | 区域定义指针，由名字查询 |
| `continent` | `0x30` | 大洲定义指针，由名字查询 |
| `subjects` | `0x38` | 单个国家句柄；复数 token 不代表向量或附庸类型 |
| `casus_belli` | `0x40` | CB 定义指针；registry `0x1f9210` / lookup `0x1fa0a0` |
| `rebel_faction` | `0x50` | 16B 对象身份引用包装 |

## 贡品、附庸与和平组件

`confirm_tribute_action +0x40` 是 32B 嵌入对象，其 vtable 为 `0x1c7b340`。嵌套 parser `0xb1d8a0` 将 `subject` 写到内部 `+0x10`（8B 国家句柄）、`type` 写到内部 `+0x18`（1B 枚举）、`amount` 写到内部 `+0x1c`（4B 固定点）。`type` 的合法取值未得到确认；不得将它直接当作外交附庸类型。

普通 `vassalaction` 没有新的派生序列化字段。基础 `type +0x34` 的逐动作含义仍需验证。`tributary_state_action.reason`、贡品 `type`、和平组件 `po_become_vassal` 是不同机制，不能合并成一个未经证实的 subject_type 参数。

`requestpeace`：`diplomats +0x40`、`demand +0x41`、`force +0x208` 为 bool；`terms +0x48` 是嵌入的和平提议对象。其 parser `0x981170` 包含 giver/taker、双方参与国向量、`is_demand`、`apply_penalties`，并将具体和平组件放入自身 `+0x88` 向量。组件有内部索引分组；构造字段正确不代表索引、所有权和合法组合已正确。

和平工厂 `0x99ff90` 通过 `0x9a0f98` 的 40 项跳转表构造组件。每个分支均通过其 vtable `+0xa0` 的整数 getter 与 token 描述符对齐。涵盖 `po_gold`、割地/归还核心/撤销核心、成为或转移附庸、成为贡朝、废除条约、放弃宣称、战争赔款、贸易转移、羞辱、宗教/政府变更、帝国/天命/革命、殖民区域，以及脚本组件。完整 40 项在 `peace_components[]`，没有据此创建新的外交 API 动作。

关键组件字段（偏移相对各组件）：

| 组件 family | 派生字段 |
|---|---|
| `po_gold` | `value +0x30`，4B 固定点 |
| 附庸/贡朝/释放或转移附庸/废除条约/结束宿敌等 11 类共用 parser `0x99e590` | `taker +0x30`，8B 国家句柄 |
| `po_demand_provinces` | `taker +0x30` 句柄；`province_id +0x38` 省份对象指针；`tribal +0x40` bool |
| `po_revoke_cores`, `po_return_cores` | `taker +0x30` 句柄；`province_id +0x38` 省份对象指针 |
| `po_concede_colonial_region` | `region +0x30` 殖民区域定义指针，由字符串解析 |
| 和平 `scriptable_diplomatic_action` | `type +0x30` 脚本和平定义指针 |

公共和平组件 parser `0x99b400` 有 `offer_giver +0x10`、`offer_taker +0x18`、`is_selected +0x20`、**未对齐的 `giver +0x22`**。这里的 giver 不等于 offer_giver，不应因名字相似而复用一个偏移。

## 脚本动作与剩余缺口

顶层 `scriptable_diplomatic_action` 的 `action_type` token `0x3668` 通过 registry `0x5b6b80` 按名字查定义，结果在 `0xac66f8` 写入动作 `+0x40`。serializer 从 definition `+0x10` 读取名字。原生 factory 第二参数需要这份定义指针；传字符串地址、token 整数或缺失查询 sentinel 都不成立。和平脚本组件用的是另一套 registry、`type` token 和组件 `+0x30` 字段。

以下仍明确未完成：

- 55 个 `0x40` 类不能全部认定为无参数；基础 `type/id/value` 及不同调用现场仍可能携带模式。
- 联盟、军事通行、海军基地、支持独立等动作的取消/请求方向，不能仅由共有 `value` 字节推断。本报告不扩大此前五类的已知模式映射。
- `invite_to_trade_league +0x40` 在 clone 中置零，但未找到派生序列化 token；`transfer_trade_power +0x44`、`callaction +0x54/+0x55`、佣兵额外标志、联姻字符串缓存等同样没有被包装成公开参数。
- 每个整数/枚举的合法范围、时间单位、UI 换算、各参与国角色、当前对象身份与生命周期、组件分组维护、合法性/AI 接受/执行效果均需后续专门证据。
- 此次 clone 读写摘要不是全面数据流分析；`unmapped_clone_*` 的空列表不代表没有未映射字段。报告保留所有入口字节用于后续复核。

下一步最容易形成可验证适配层的是：固定点/整数转换和国家、省份身份解析，随后为纯标量经济动作提供构造—预览—析构测试；单位引用、国家向量、战争目标与和平组件需要各自的构造/复制/销毁和主线程流程验证。目录字段的 `partial` 或运行门禁不能因为此静态报告而提升。

附带确认当前 server context getter `0x811aa0` 只有三条指令：读取 `server+0x330`，再读取该对象 `+0x370`，返回。它只为根任务的只读链条核验提供静态偏移，本报告没有调用该 getter。
