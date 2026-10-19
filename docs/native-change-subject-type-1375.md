# `change_subject_type` 的磁盘静态证据（1.37.5）

结论：stock 脚本证明了在附属国自身 country scope 中使用
`change_subject_type = { subject_type = crown_colony }` 的语法；本次同时闭合了
token、工厂、对象字段和虚函数执行槽。但这份精确版本 PE 的对应执行函数只有
scope / DLC 条件诊断，尚未找到真正修改 dependency 的路径。因此不能承诺
`appanage → vassal` 可执行，也不能承诺保留原始 start date 或双方休战。当前不据此
增加 FOI 转型夹具，不修改已冻结的 v8。

范围仅为磁盘静态分析。没有读写游戏进程、调用原生函数或修改模组。没有尝试绕过
DLC 判断，也没有把加载插件或其他未分析的运行时行为当作证据。

## 版本与复现

- EXE SHA256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。
- 工具：`work/trace_change_subject_type.py`。
- 报告：`work/reports/native-change-subject-type-1375.json`。
- 报告 SHA256：`bd55249e8b280369fd36627e7de3b74c0072025506f21ea26deedefa4012d58f`。
- 9 个有界小函数及 17 个精确代码块，共 2,311 字节指令。未反汇编整个大工厂。

在仓库根目录运行：

```powershell
$env:PYTHONPATH="$env:TEMP\eu4-native-analysis-deps;work"
python work/trace_change_subject_type.py --check
```

`--check` 重建证据并逐字节比较已有 JSON；源码和报告中的
`runtime_verified` 都为 `false`。

## 已闭合部分

stock `events/ColonialNation.txt:4655` 的 `colonial_nation.185` 是 country event。
trigger 要求 `has_dlc = "Leviathan"` 和 `is_subject_of_type = private_enterprise`；
其 option 在 `4679` 行直接使用上面的 effect。effect 位于当前附属国 scope，未通过
`overlord` 切换作用域。这只是 `private_enterprise → crown_colony` 的脚本用法证据；
普通 `vassal`、`appanage` 定义存在不等于任意类型组合都可转换。

| 项目 | 精确静态证据 |
|---|---|
| effect token | `change_subject_type = 0x3bc6`，descriptor `0x22c4680` |
| 参数 token | `subject_type = 0x352a`，descriptor `0x21e1088` |
| 通用 effect 工厂 | `0x5dec50`，最终 switch 为 byte table `0x5e6314` + DWORD table `0x5e62a0` |
| 该 case | token index `0x84`，映射 index `14`，case `0x5e3d04` |
| 对象 | 分配 `0x58` 字节，ctor `0x5de6c0`，vtable `0x1c9e978` |
| 参数解析 | slot `+0x20 = 0xdda5d0`，`subject_type` 通过 `0x170b790` 写入 String32 `+0x38` |
| String32 布局 | 对象 `+0x48` 为 length，`+0x50` 为 capacity；构造时分别为 0 和 15 |
| append / parse | `0x5e4312` 加入容器 `+0x10`，`0x5e4322` 调用对象 slot `+0x18` |
| 工厂收尾 | `0x5ef140` 只有 `mov [rcx+0x28],edx; ret`，保存 token，未替换对象 |
| 通用执行 | `0x5ed800` 遍历子 effect，`0x5ed851` 调用子对象 slot `+0x78` |
| 该对象执行槽 | `+0x78 = 0xdda140`；`+0x98` 已在此 vtable 边界外，不得当作该对象方法 |

`set_country_subject_type (0x3bb3)` 和 `upgrade_subject_type (0x3bb9)` 在这个
工厂都进入 default / scripted-effect fallback `0x5e4b04`，没有进入上述 case。
不能按名字相似就认为它们是可调用替代入口。stock subject definitions 中的
`upgrade_subject_type = yes/no` 还是定义属性。

## 为何停止扩展这个 effect

完整有界解码 `0xdda140` 后，入口按 scope `+0x4b` 选择 country handle `+0x44`
或 `+0x2c`，再校验 handle 高字节。无效 scope 路径记录
`Scope.GetCountryTag().IsValid()` 诊断。

有效 country 路径跳至 `0xdda471`，取得来源位置后，在 `0xdda515` 引用字符串
`Script should DLC check Mandate of Heaven OR Art of War OR Leviathan.`，由
`0xdda520` 写诊断后返回。其 source path 指向 `effects\dependencyeffects.cpp`
第 `0x9f` 行。该函数没有读取已解析的 `subject_type +0x38`，没有查找 dependency
定义，也没有修改 dependency 类型、开始日期或休战。

另外核对了构造时的 effect 注册表 `0x233fe48` 和启动初始化循环：
`0x205d6a` 调用每个 effect 的 slot `+0x50`，而本对象该槽为 `0x8f440 (ret)`。
这一初始化路径不能补上真实类型转换逻辑。此结果仅针对已追踪的磁盘路径；不能据此
断言所有正常 DLC / 运行时分派都不存在，但不能将未知分派当成已实现能力。

| 待回答的问题 | 当前结论 |
|---|---|
| `appanage → vassal` 是否受支持 | 未证实 |
| 是否复用原 dependency 对象 | 未证实 |
| dependency start date 是否保留 | 未证实 |
| bilateral truce 是否保留或新增 | 未证实 |
| 能否据此绕过正常取消附庸的休战条件 | 不能作此结论 |

下一步改研究 stock `create_vassal` / `vassalize` 的独立执行路径；即使找到能够建立
普通 vassal 的脚本，也仍须单独核对其休战写入、国家作用域与真实验收，不能套用
正常外交提议被接受时的行为。
