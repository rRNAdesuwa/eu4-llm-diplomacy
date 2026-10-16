# v10 七类外交关系效果的只读核验

本轮闭合了显式同盟、军事通行、舰队停泊的持久关系方向、虚表和双边索引；禁运、补贴沿用已钉扎的扩展报告。新增工具仅采样选定状态和比较保存的报告，没有调用游戏方法、注册生产后端或声称完成实际外交验收。

适用 EXE SHA-256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。
基础扩展报告 SHA-256：`0c1731b0b29b296da73dc406fb31544ada59c17c275d17d623677b16998698bd`。
本轮 `work/reports/native-pair-extension-effects-v10-1375.json` SHA-256：`b6f4b69db38f5e3eae0c3cebf1fa5298701b86a98e8299d6f0e9759b84861f62`。

生成器 `work/trace_pair_extension_effects_v10.py --check` 核验精确 EXE、父报告完整摘要、指令锚点、关系虚槽及 token。23 个辅助函数共 8,366 字节，另取 124 字节已定位 UI 指令片段；每函数最多 16 KiB / 4,000 指令，总辅助解码上限 64 KiB，内存保护 768 MiB。无递归整程序扫描或进程访问。报告全部 `runtime_verified=false`、`execution_verified=false`。

## 对象和方向

表中索引偏移相对于 country `+1510` 的 pair record 所引用的 root。索引为 DWORD count 和 16 字节 `{slot, padding, object}` 项；不是 pair record 内直接放置的外交状态位。

| 原生 family | FRA 索引 pointer/count | target 索引 pointer/count | 关系虚表 RVA | 对象 +10 / +18 |
| --- | --- | --- | --- | --- |
| allianceaction | 80 / 8c | 80 / 8c | 1c7a740 | 两盟友，顺序可交换 |
| milaccess | b0 / bc | c8 / d4 | 1cdde60 | FRA 使用权持有国 / target 授予国 |
| offermilaccess | c8 / d4 | b0 / bc | 1cdde60 | target 使用权持有国 / FRA 授予国 |
| fleet_access | e0 / ec | f8 / 104 | 1cddee0 | FRA 停泊权持有国 / target 港口国 |
| offer_fleet_access | f8 / 104 | e0 / ec | 1cddee0 | target 停泊权持有国 / FRA 港口国 |
| warsubsidy | 110 / 11c | 110 / 11c | 1c815d8 | FRA 付款国 / target 收款国 |
| embargoaction | actor pair record +46 & 02 | 仅另行观察反方向 | 无独立关系对象 | FRA 发起 / target 被禁运 |

六种有对象的 family 均对应 0x48 字节持久关系。观察器核对虚表、`+8=0x165`、完整国家句柄、`+20` 起始日期、`+28=0`，并要求双方索引指向同一对象。通行额外 `+40` 是 `enforce_peace` BYTE，不是“条件通行”标志；构造默认 0，token 为 `2dda`，序列化/解析方法 `a70410/a703c0`。值 1 单列为 `enforce_peace_relation`，不能作为普通外交请求的新增/取消效果。

请求与授予是不同动作类：`milaccess/offermilaccess` 分别在 `5243d9/5352ca` 选择不同对象角色；停泊对应 `52db58/531f66`。它们都在 action `state==2 && value==true` 的效果分支构造关系。这能证明静态接受后的写入路径，不能让只读关系出现被表述为某次请求得到 AI 接受。

军事关系 `a70270` 注册、`a70310` 清双索引并标 removed；停泊关系为 `a70760/a70840`。同盟 `a5d1b0` 注册双边、`a5d790` 解除并写 removed。补贴两方向都使用 `a697a0`，取消 `a62f80` 清双方后标 removed。取消可能伴随休战、费用等其他效果，工具不判断世界是否回到原状。

## 显式协议不等于条件通行

`DIPIRO_CONDITIONAL_ACCESS` 的界面代码在 `f09178` 调用 `a69030`，后者转到规则计算 `28b220`。该计算在 `b0/bc` 显式协议检查之外，存在同国、其他关系和宗主等分支；没有找到显式关系对象不等于没有移动权限。

本观察器只核对指定显式索引及匹配关系，既不调用这个规则函数，也不尝试复刻全部条件通行规则。synthetic 测试在其他关系索引存在时仍保持“没有选定的显式协议”，不推断拒绝或禁止通行。

## 使用方式

工具：`work/probe_pair_extension_v10_1375.py`。独立 profile 为 `1375_pair_extension_observation_v10_1`；actor 固定 FRA，target 仅 ENG/POR/NAV/FOI。不会自动采样。以下命令供主任务在已授权实验中使用，本轮没有执行 sample：

```powershell
python -B work/probe_pair_extension_v10_1375.py sample --pid <PID> --target NAV --action allianceaction --output work/runtime/v10-alliance-before.json
python -B work/probe_pair_extension_v10_1375.py sample --pid <PID> --target NAV --action allianceaction --output work/runtime/v10-alliance-after.json
python -B work/probe_pair_extension_v10_1375.py compare --before work/runtime/v10-alliance-before.json --after work/runtime/v10-alliance-after.json --direction positive --output work/runtime/v10-alliance-comparison.json
```

取消仍采样同一 family，比较用 `--direction cancel`。例如请求方取消军通用 `milaccess`，授予方撤回军通用 `offermilaccess`；不能替换为另一个 family 的 before/after 报告。`--action` 接受上表七个原生 family 名称。

补贴可额外核对固定实验的精确金额和期限：

```powershell
python -B work/probe_pair_extension_v10_1375.py compare --before work/runtime/v10-subsidy-before.json --after work/runtime/v10-subsidy-after.json --direction positive --expected-monthly-milli 1000 --expected-duration-years 10 --output work/runtime/v10-subsidy-comparison.json
```

`monthly_milli=1000` 表示每月 1 金；期限为年。到期公式仅报告 `start + years*0x2238`，不保证后续世界事件不会提前取消。若不提供这两个可选参数，比较只报告读到的数值，不声称与任何请求参数相符。

sample 验证磁盘完整 EXE SHA、加载模块 PE 身份、PID 与进程创建 FILETIME；只打开 `QUERY_INFORMATION | VM_READ`。选定结构被完整读取两次，内部前后身份也一致才返回 `consistent_bounded_observation`。索引最多 4,096 项，总读量和单次读量沿用原 core probe 预算。所有输出独占创建，旧证据不会覆盖。

compare 再验证原始两次采样、profile、证据摘要、进程与完整国家身份、时间顺序及日期不倒退。只有 absent→active 或 active→absent 才标 `observed_effect=true`；同盟允许关系对象两国顺序互换，反向补贴单列 `reverse_relation`。变化、缺页、错误类型/句柄、索引矛盾、重复项、超限都保持 unknown。不存在状态不推断拒绝。

这不是原子快照；两个采样之间的瞬态、ABA 复用、同地址重载可能逃逸。`observed_effect` 从不提升 `execution_verified`、`ai_acceptance_verified`、`request_causality_verified` 或 `whole_world_unchanged_verified`。

## 验证与目录修正

`python -B -m unittest bridge.tests.test_pair_extension_v10_probe bridge.tests.test_diplomacy_extension_parameters`：18 项离线测试，通过稀疏伪内存验证七 family × 四目标的添加/移除、ask/offer 分离、反向补贴、对称同盟、enforce_peace、禁运掩码、双索引/完整身份错误、读预算、两次采样变化和离线比较不打开进程。

目录仅迁移 `give_subsidies.duration_months` 为 `duration_years`，旧字段拒绝且不隐式换算，附新扩展报告全 SHA。参数保持 partial，执行保持未实现；274 项/270 静态映射的计数不变。
