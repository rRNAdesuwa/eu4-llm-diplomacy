# EU4 1.37.5 外交测试夹具与事件 ABI

这份证据支持通过已安装测试 Mod 和固定原生事件回调，研究额外外交官及外交接受条件；没有调用游戏、写进程、修改已冻结的 v6，或把测试结果当作正式外交 API 的覆盖证明。机器码证据只适用于 SHA256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。

重现报告：

```powershell
python work/trace_test_fixture.py --deps-dir "$env:TEMP/eu4-native-analysis-deps" --user-data "${USERPROFILE}/Documents/Paradox Interactive/Europa Universalis IV"
```

输出为 `work/reports/native-test-fixture-1375.json`。29 个明确入口共反汇编 24,145 字节，每入口窗口最多 16 KiB / 4,000 条指令，内存限额 768 MiB；不跟随所有调用，也不反汇编整个定义加载器。报告记录配置/脚本原文及 SHA，安装状态只表示生成报告时的磁盘配置，不能证明某个游戏进程已经加载它们。

## 冷却 0 的实际边界

原版 `NDiplomacy.DIPLOMAT_COOLDOWN_TIME = 1` 注释单位为月。测试 Mod 将它设为 0。定义加载器的 41 字节窗口 `49a00b..49a034` 把名称 `DIPLOMAT_COOLDOWN_TIME` 与全局 DWORD `233e064` 交给 Lua 整数读取函数 `14a7650`。这些证据确认配置绑定，不能据此把该全局当作可直接写入的测试接口。

`35a830` 复制当前 rawdate、读取全局月份、调用 `14c8030`，然后写入 actor 的关系数组 `country+1510` 中 `targetSlot*48+30` 阈值。`14c8030` 的开头明确在月份为 0 时直接返回。初始外交 command 的门槛 `4e8630` 仍要求当前 rawdate **严格大于** 阈值。因此：

- 0 月可以减少以后新产生的等待；不能保证暂停同日连续发起。
- 载入 Mod 不会由这条路径追溯清除存档中已有阈值。
- 验收应分别只读记录 `233e064` 和关系阈值，并通过已审核的有限控速推进正常日期；不写日期、阈值或命令 state 来跳过检查。

安装并启用 Mod 后需要重新启动。仅复制 Lua 文件、生成 on/off 脚本或现有 PID 继续运行，都不是配置生效证据。

2026-10-13补充：最终TAG拉通后，unlock测试Mod新增有符号月份-1候选，借用原生日期加法把未来新阈值写到过去，保留全部原生检查。`work/runtime/tag31-cooldown-static-20261013.json` 记录公共full检查、阈值写入、负月份分支及三族+100槽。已安装但未重启/发送，不能算同日冷却实测通过；旧存档阈值保持。上面的0配置描述属于此前实际测试版本。

## 外交官数量及稳定身份

测试 modifier `llm_diplomacy_test_pool = { diplomats = 100 }` 是有限额外数量。它通过标准 `add_country_modifier` / `remove_country_modifier` 脚本效果启用/停用，不是手工改外交官内存。原版 event modifiers 也使用 `diplomats`；报告保留 token `2746`、两个 modifier 效果 token `2732/2792` 和检查 token `2a2d`。

国家构造路径 `2cb753..2cb818` 创建 token `2746`、type 3 的外交官 manager，放在 `country+1480` 指针向量的第 4 项。构造 `6fec50` 确认：

| 对象字段 | 静态证据 |
|---|---|
| manager vtable | `1cac380` |
| manager `+10` DWORD | `diplomats` token |
| manager `+14` BYTE | 类型 3 |
| manager `+16` QWORD | 未对齐的完整 country handle |
| manager `+20/+28/+30` | entry 指针向量 begin/end/capacity |
| entry `+10` QWORD | mission |
| entry `+18` BYTE | 状态 |
| entry `+44` DWORD | 当前外交官 ID |

`UpdateEnvoyCount` 的调试名称直接出现在 `2e1670`。它取得国家聚合 modifier 的索引 `0x22`，由 dense 值 `+114` 或 sparse `{index,value}` 数组读取，经过全局 `2358080` 对象 `+d00` 的可选 modifier hook，再将 signed fixed-point 数值除以 1000，调用 `6ff110` 调整外交官总量。不能只读取一个聚合数值就把它称为当前可用数量：缓存读取 `93d750` 带线程/有效性检查和诊断分支，也不适合外部读取器调用。

`6ff110` 增删外交官后会重写所有 entry 的 ID，调用 `24ff20` 重新关联 mission，并更新间谍 task 的 envoy ID `+2c`。因此启用或停用夹具后，必须重新解析整个 manager / entry / mission 图，不能缓存旧指针或 ID。停用额外数量可能移除正在执行任务的超额外交官，应放在测试收尾。数量增长、state 0 数量和具体 mission 身份是不同观察项；后续外交操作仍使用原生合法性和可用外交官检查。

## 固定事件回调

原生注册项的名称地址 `1cc1f50` 为 `event`，回调槽 `1fc3638` 为 `e5bb30`。签名为：

```cpp
Result40* __fastcall event_callback(Result40* output,
                                   const Vector24<String32>* arguments);
```

`String32` 为 16 字节内联区、QWORD length `+10`、QWORD capacity `+18`；容量小于 16 使用内联数据。`Vector24` 为 begin/end/capacity 三指针。`Result40` 的成功 BYTE 在 `+0`，拥有的 `String32` 在 `+8`，返回 RAX 等于 output。`e5c3a9..e5c3b8` 将本地结果字符串转移到 output；正常返回后只对 output.message 调用 `95660`，不能重复析构原生已转移的局部对象。

新核心固定两个参数 `{ "llmt.1", "FRA" }` 或 `{ "llmt.2", "FRA" }`。短别名 6 字节、FRA 3 字节，均为容量 15 的 SSO 字符串，不需要原生输入字符串分配，不对两个入参或向量调用原生析构。旧 `llm_diplomacy_test.1/.2` 长名仍可以作为 Mod 的兼容事件存在，但核心不接受它们或其他任意字符串。

第一参数通过 `6ee1d0` / `6f5500` 查找事件定义；缺失返回 null，回调拒绝。第二参数由 `e42b00(args,1)` 解析完整国家 handle；其失败路径会回退到当前/观察国家，因此核心在调用前独立核对玩家为完整 FRA handle `0100007a00415246`、slot 122 的国家对象身份也相同。它没有第三参数，不选择手动 option 分支。

两个参数的正常路径会执行 event definition `+180` 的 effect，再调用 `756f00` 登记正常事件并经 `10b9a50/6ecae0` 交给事件 UI。回调的 true 只说明该原生处理路径返回成功，不证明指定 modifier、外交官或关系效果已应用；hidden 事件的运行表现同样需要观察。

回调还会临时把全局 BYTE `1fd10c4` 置零，并在正常返回时恢复。异常可能跳过恢复。核心只读取前后值，异常时永久冻结，不擅自修复该字段、不销毁所有权不明的结果、不自动重试。

## v7 独立核心和宿主契约

新增 `work/native/test-fixture-v7-1375.h/.cpp`，接口为 `eu4_test_fixture_1375::invoke(Operation::enable/disable, Host)`。它包含独立 v7 的 controls 头，仅复用 `observe()` 进行只读暂停/世界检查。单文件 MSVC `/std:c++17 /O2 /W4 /WX /c` 已通过，独立审查也核对了四处函数前缀、注册指针和结果字符串所有权。编译或审查本身不是运行验证。

Host 必須在调用前持久化唯一 claim，并提供固定游戏线程、完整 exe SHA 验证、文件安装/启用发生在 PID 创建之前且现有文件 SHA 对应 manifest 的 `fixture_definition_files_verified` 证据。该名称特意不叫 loaded：宿主尚未独立证明引擎注册的是哪份定义。原生 callback 的名称查找能拒绝缺失定义，实际效果仍须后续只读验证。profile ID 为 `1375_test_fixture_v1`；定义 manifest SHA 进入 begin/complete 日志，并由宿主绑定请求 sequence 和 PID 创建身份。

核心只允许暂停中的 FRA、无已知加载/重置标志、原生 MP classifier 为 false，并要求外层宿主保留一次性单人测试会话约束。初次 native 调用前必须成功持久化 `test_fixture_begin`，随后再次检查世界/线程/guard；输出析构前后也检查 guard。过期请求不得首次进入，已经调用完成的结果清理则由宿主标记 operation_entered 后允许执行，不能误当作新的请求重试。

核心日志名称为 `test_fixture_begin` / `test_fixture_complete`，正常完成应同时满足 reason 0、callback 返回 true、SSO 入参未变化、结果已销毁、世界身份/日期未变化、临时 flag 已恢复、exception 0、freeze false。`fixture_effect_verified` 始终 false；`diplomacy_submitted=false` 指核心未调用 pair command 发送器，不能解释为事件没有改变外交关系。

目前 `llmt.1` 的已审脚本包含外交官 +100、外交声望 +100、FRA 与 NAV/FOI 的意见 modifier 以及 NAV 联盟创建，专门用于可丢弃测试存档；这些接受条件不代表常规 AI。`llmt.2` 移除 modifier / 意见，**没有撤销创建的 NAV 联盟**，因此 fixture_off 不是“恢复完整基线”。完整恢复应通过已保留的测试基线读档。

## `run` 路径为何保留为静态研究

`run` 注册槽 `1fc2558` 指向 `e4f1d0`，同样使用 Result40/Vector24 ABI，但严格要求一个参数。它只检查文件名包含 `.txt`，随后经 VFS existence 与读取路径构造解析器、effect 树，再对当前/观察国家执行。这个内部扩展名检查不是调用方的路径白名单。

存在检查 `19f6ea0→19fad70` 使用 `19fb410` 清理 VFS 路径，拒绝冒号、反斜杠以及 `.` / `..` 路径组件；Windows 绝对路径不适用。底层会遍历已挂载搜索路径，文件流 `1710440→1718300` 的 mode 0 走原生读取路径。用户目录已有 `llm_test_diplomats_on.txt/off.txt`，但本报告没有验证它们在运行时会解析到哪个 mount、是否会被其他 Mod 遮蔽。不能把磁盘同名文件 SHA 当作 VFS 最终解析来源的证明。

因此 v7 核心只实现已预期由开局资源加载器处理的两个固定事件，不开放 `run`、日期修改、任意 console/script 字符串、任意国家、yesman 或直接改国家字段。报告中其余入口均为证据，不是可执行接口。
