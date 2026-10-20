# 剩余属国特殊命令与未映射动作盘点（1.37.5）

静态研究仅分析磁盘上的确切版本 PE、游戏脚本及既有报告。随后将 6 项证据整合到目录和目录生成器；没有打开游戏进程，没有执行命令，也没有改动冻结的 v6。所有新增证据的 `runtime_verified`、`execution_verified` 都是 `false`。

生成器为 `work/trace_subject_special_paths.py`，机器报告为 `work/reports/native-subject-special-paths-1375.json`。游戏 SHA256 固定为 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`；报告还记录整合前目录最小基线、既有派生字段报告与幕府脚本的独立摘要。审查报告 SHA256 为 `eef6c7369e37a339975d5234c62b069cdd4864b697d0897304316c5c2d09ad3d`，目录生成器同时钉扎报告全部字节、游戏与源脚本。

## 整合前 98 项的构成

| 来源 | 数量 | 本轮结果 |
|---|---:|---|
| 外交本地化/变体候选 | 39 | 保留未决，不能按名称相似自动映射撤销或双向行为 |
| 历史请求 | 2 | 原历史版本协议不能证明本机执行支持 |
| 和平条款 | 51 | 30 个确切源名称对应已有组件；13 个脚本条款；8 个本地化候选 |
| 属国交互 | 6 | 找到 4 个特殊命令类；其中 3 条实际为幕府政府机制 |

报告 `inventory.rows` 保存整合前全部 98 个稳定 ID、源键、来源行号、参数状态及逐项对应，避免手工列表漏项。该历史基线在 `work/reports/subject-special-inventory-baseline-1375.json`，记录原目录摘要，不随目录整合自动改写，以避免 catalog→report→catalog 摘要循环。生成器默认读此基线；显式传入 `--catalog` 可产生新的独立研究盘点，须重新审查摘要后才允许合并。

**仅完成本文 6 项特殊路径整合时，历史目录为 271 个 ID、179 个静态映射、92 个未映射。** `native_special_mapping` 新增 6 项、4 个主命令类。后续[和平专项报告](native-peace-catalog-1375.md)补充独立和平映射与三个漏项后，目录已变为 274 个 ID、232 个静态映射、42 个未映射，正式执行支持仍为 0。当前集合以目录 `coverage.unmapped_action_ids` 和[覆盖文档](diplomacy-coverage.md)为准；下文和平盘点和机器报告保留专项研究开始前的历史基线。

## 6 个属国目录项的特殊路径

| 目录 ID | 原生命令 token | vtable RVA | UI 构造入口 | 载荷 |
|---|---|---|---|---|
| `subject.release_colony` | `release_colony` / `0x2f39` | `0x1c56090` | `0xf669e0` | `+0x50` 殖民国完整句柄，`+0x58` 宗主完整句柄 |
| `subject.set_military_focus` | `set_subject_military_focus` / `0x3017` | `0x1c54678` | `0xf59b70` | `+0x50` 属国完整句柄，`+0x58` DWORD 枚举 |
| `subject.set_tribute` | `set_tribute_type` / `0x35c0` | `0x1c53090` | `0xf59d00` | `+0x50` 属国完整句柄，`+0x58` BYTE 枚举 |
| `subject.expel_ronin` | `government_interaction_command` / `0x36fd` | `0x1c53288` | `0x13b3ca0` | `+0x50` actor，`+0x58` 机制 ID，`+0x5c` 交互 ID |
| `subject.sankin_kotai` | 同上 | 同上 | 同上 | 同上，机制/交互需按名称解析当局定义 |
| `subject.sword_hunt` | 同上 | 同上 | 同上 | 同上 |

4 类均由 UI 分配 **0x60 字节独立命令**。它们不属于此前 41 个 singleton 借用指针 `+0x98` 的 0xa0 属国命令，也不属于普通外交 action 工厂。报告逐类核验 token getter、全部虚表指针可执行性，并保存 serializer、parser、gate、execute、clone 与 UI 构造的有界反汇编。常见命令基类的构造、传输所有权和派生生命周期仍须分别验收；已有五核心验证不能迁移为这些类的通过证据。

### 军役与贡品：枚举顺序已由 GUI 初始化链证明

军役选择值为 `0=no_focus, 1=aggressive, 2=supportive, 3=passive, 4=defensive, 5=siege`。注意目录 JSON 的字符串枚举顺序不是序列化编码；把其中 `supportive` 的列表位置直接写入原生对象会错误设置为 `aggressive`。

贡品选择值为 `0=none, 1=cash, 2=adm, 3=dip, 4=mil, 5=manpower`。两个 UI handler 将按钮名称数组索引写入命令。生成器从 CRT 单字符串初始化、String32 数组复制和按钮处理链抽取值，而非硬写 GUI 排列猜测。

军役 parser `0x2b29b0` 解析 `subject_country` / `subject_focus`；execute `0x2b28c0` 写目标国家 `+0x2864`。其 gate 仅检查国家存在/类型及 unsigned 值不超过 5，**不能当作调用者有宗主权限的证明**。

贡品 parser `0x2beed0` 解析 `subject_country` / `tribute_type`；execute `0x2be340` 先写目标国家 `+0x28a6`，后有时间与消息更新。gate `0x2bf050` 进一步检查属国类型及非零贡品数量。此命令与外交类 `confirm_tribute_action` 分开，不能复用其对象布局。

### 释放殖民地：play-as 是第二条命令

`0x2a1c90` 将 `from` 解析至 `+0x50`，`to` 至 `+0x58`；gate `0x2a2910` 从前者取得 dependency definition 并检查 `+0x142` 殖民属国标志。UI 向前者填当前殖民国，后者填宗主。实际 effect `0x2a1ef0` 处理关系、独立状态与消息。

`0xf66b8d` 已提交释放命令后，`0xf66b90` 才检查“扮演被释放国家”复选框。选择时再分配命令、调用 `0x277310` 并在 `0xf66c53` 独立提交：第二条 token 为 `set_controller` / `0x29d6`，有目标国家、控制者 ID 和三个 byte flags。**`play_as_released` 不是释放命令内的一位布尔字段。** 未证明这两步原子性、失败回滚或切换玩家后的宿主继续授权；新适配器应先仅实现不切玩家的释放，复合操作另行设计。

### 幕府三项：修正作用范围后再整合

`common/government_mechanics/17_shogunate.txt` 将 `expel_ronin`、`sankin_kotai`、`sword_hunt` 明确定义在 `shogunate_mechanic.interactions` 中。各自效果包含 `every_subject_country`，筛选 `is_subject_of_type = daimyo_vassal`。这是 actor 的政府机制交互，会影响符合条件的全部大名；不存在指定一个 target 的载荷。

UI `0x13b3ca0` 从机制和交互定义对象的 `+0x8` 读取数字 ID。命令 serializer `0x2bfae0` 将三字段命名为 `country`、`parent`、`index`。这些 ID 必须从当前有效定义按名称解析；不能写入源键 token、字符串地址或用户任意数字。

gate `0x2bfd80` 从 actor `+0x1420` 的机制容器 `+0x20..+0x28` 查找机制 ID，再从机制定义 `+0xe0` 指针数组 / `+0xec` DWORD 数量查找交互 ID，最后调用 `0x7b6ab0` 检查脚本触发、成本和冷却。execute `0x2bfa70` 找到机制后进入 `0x7bc160`，更新成本/冷却，再对交互定义 `+0x170` 的 effect 对象调用虚槽 `+0x78`。

整合保留三个稳定 ID，但将其来源和请求作用范围修正为政府机制、只接 actor；API 参数校验明确拒绝额外 target。参数仍为 partial，因为当前定义 ID 解析和原生参数绑定未实现。旧属国属性放入 `legacy_subject_types_enabled_by_source`，不再作为逐个目标的适用类型。没有把数字 ID 解析或执行标为实现。

## 和平条款的精确缺口

既有 `native-action-fields-1375.json` 恢复 40 个和平组件类。在目录 51 个和平条款中，30 项 `game_key` 与组件名称逐字相等。机器报告提供这些项的原工厂 case、分支、虚表、parser 和派生字段引用，但没有新增 callable mapping。和平组件须装入拥有嵌套容器的和约对象，不能作为普通国家对 action 直接发送。

13 个未同名匹配项确实来自 `common/peace_treaties` 脚本：`demand_sacirifces`（原拼写）、`force_peasant_republic`、`make_nahuatl_tributary`、`po_annex_tribe`、`po_change_culture`、`po_change_culture_same_culture_group`、`po_claim_elector_role`、`po_claim_norwegian_throne`、`po_establish_eyalet`、`po_extinguish_the_revolution`、`po_raid_churches`、`po_reintegrate_into_hre`、`spread_dynasty`。后续和平专项已证明专属脚本注册表和静态定义绑定，保存于 `native_peace_mapping`；对象所有权和运行绑定仍待验证。不能仅因存在同名普通外交 family 就借用其布局。

8 个仅本地化候选为 `concede_colonial_region`、`end_rivalry`、`enforce_fleet_basing_rights`、`full_annexation`、`give_up_claims`、`pillage_capital`、`show_strength`、`war_reparations`。其中若干与原生 `po_*` 名称相似，需 UI 构造或明确字符串引用才能确认别名。尤其“完全吞并”和“展现力量”可能是已有条款组合或特定模式，本轮不推断独立组件。

历史反向对账发现 10 个组件名没有目录的确切源键对应：`po_concede_colonial_region`、`po_end_rivalry`、`po_enforce_fleet_basing_rights`、`po_enforce_military_access`、`po_give_up_claim`、`po_pillage_capital_state`、`po_transfer_vassals`、`po_war_reparations`、`revoke_reform`、`scriptable_diplomatic_action`。后续专项通过组件显示方法和脚本注册表解决这些对应，其中军通、转移属国、撤销改革新增真实公开 ID；历史“271 项”以及现在的“274 项”都不能解释为完整外交入口的完备性证明。

## 可执行的下一研究次序

1. 6 项静态特殊路径已整合、3 项幕府作用范围已修正；执行继续禁用。下一步为军役/贡品实现固定枚举、有界目标解析与独立宗主权限核验，再分别验收生命周期及只读效果。
2. 释放殖民地先限制不切换玩家，核验双方完整句柄、真实 dependency 方向和殖民类型；研究一次性命令及解除关系结果。play-as 另作会改变宿主 player identity 的复合操作。
3. 为幕府机制定义建立按名称解析的有界只读观察器，验证 ID 与脚本定义对应；触发/冷却可借已找到的原生 gate，执行仍需独立 ABI 和所有权验证。
4. 和平先选择最小、可明确核验的单组件和约，恢复双方与战争上下文、demand 方向、容器构造/销毁/clone 和实际接受结果，再推进 30 个已有同名组件。
5. 沿 scriptable 和平组件补齐 13 个脚本定义绑定；同时处理 8 个候选别名及反向发现的原生组件缺项。剩余 39 个外交变体逐项证明 value/角色/取消前置，不能批量字符串去前缀映射。

## 复现与边界

在仓库根目录执行（依赖目录是现有离线 Capstone 安装）：

```powershell
python work/trace_subject_special_paths.py --deps-dir "$env:TEMP/eu4-native-analysis-deps"
python work/trace_subject_special_paths.py --deps-dir "$env:TEMP/eu4-native-analysis-deps" --check
```

固定 45 个有界入口，共解码 14,416 字节。每入口至多 16 KiB / 3,000 条指令，全部解码总量上限 128 KiB，单个附加输入文件上限 4 MiB，并调用 768 MiB 内存保护。跟随局部分支，不递归跟随调用；记录未跟随边。没有将未走到的路径、原生 gate 或静态指针解释为运行时安全、授权或游戏行为成功。
