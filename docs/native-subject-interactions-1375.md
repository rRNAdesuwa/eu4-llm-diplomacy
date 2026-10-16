# 属国交互原生注册与命令（EU4 1.37.5）

对象是 SHA-256 `9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A` 的本机程序。离线报告 [native-subject-interactions-1375.json](../work/reports/native-subject-interactions-1375.json) 由 [trace_subject_interactions.py](../work/trace_subject_interactions.py) 重建：41 项注册、96 个有界入口、10,642 字节代码。没有调用游戏，也没有增加已验证执行能力。

## 注册与所有权

`0x81c20..0x83841` 的 41 个静态初始化函数将 token 与 16 字节单例绑定。每个单例 `+0` 是虚表、`+8` 是 token。生成器同时核对初始化立即数、单例静态数据、虚表、token descriptor 和显示名称入口，避免仅凭本地化猜测映射。

`0xaf41b0(token)` 从全局哈希表取单例：桶数 `0x1fd522c`，桶指针 `0x1fd5230`；节点 `{singleton,next}`，比较 `singleton+8`。没有匹配时返回空。这些是程序静态注册的借用对象，不能作为普通外交对象分配、克隆或释放，也不能将交互 token 交给外交工厂 `0x35d210`。

现有 47 个 `subject.*` 公共 ID 中，41 个已在目录的 `native_subject_mapping` 中绑定。其余 6 项为 `expel_ronin`、`sankin_kotai`、`sword_hunt`、`release_colony`、`set_military_focus`、`set_tribute`；前 3 项有属国类型源文件属性，后 3 项是 GUI 候选。未找到注册不等于证明功能不存在。

## 共用 subject command

命令 token 为 `0x31d8`（subject），对象大小 `0xa0`，虚表 `0x1c3a650`。构造器 `0xaf3860(storage, singleton, overlord_handle, subject_handle)` 创建独立命令并借用单例，随后调用 `0xaf4030` 从当前属国标志推导 cancel 状态。

`0xaf37c0` 是空句柄、空单例的默认构造器；不能直接替代上述带身份的构造器进行提交。

| 字段 | 偏移/大小 | 序列化含义 |
| --- | --- | --- |
| overlord | `+0x50 / 8` | 完整国家句柄 |
| subject | `+0x58 / 8` | 完整国家句柄 |
| third_party | `+0x60 / 8` | 第三国句柄，默认无国家 |
| index | `+0x68 / 4` | 动作相关的整数，默认 -1 |
| token 15 | `+0x70 / 32` | 动作相关 EngineString32，名称未确认 |
| cancel | `+0x90 / 1` | 构造时读取的当前持续交互状态 |
| interaction | `+0x98 / 8` | 借用单例；序列化其 token，反序列化经注册表恢复 |

序列化/解析分别为 `0xaf3bc0 / 0xaf3cd0`。克隆入口 `0xaf3b70` 分配 `0xa0` 并调用 `0xa7070` 复制构造；析构入口 `0xa7180`，成员析构 `0xa7040`。这些布局有静态证据，生命周期尚未做原生运行验收。

合法性入口 `0xaf3e20` 先检查单例 `+0x30`，再调用 `0xaf3e70`。后者核对当前宗主身份、属国类型是否允许交互；仅对单例 `+0x38` 返回非零持续状态 flag 的交互比较 cancel 快照，最后调用单例 `+0x28` 的动作专用检查。真正执行 `0xaf3af0` 将命令交给单例虚表 `+0x8`。

`cancel` 不能作为任意布尔选项绕过这些状态检查；`index`、字符串和第三国也不能用通用默认值替代逐项参数绑定。例如授予省份和升级属国类型显然需要不同的输入解释。目前目录仍保留原参数完成度，所有属国动作执行状态均为 `unimplemented`。

## 重建

```powershell
python -B work/trace_subject_interactions.py --exe ../eu4.exe --deps-dir "$env:TEMP/eu4-native-analysis-deps" --output work/reports/native-subject-interactions-1375.json
python -B tools/build_diplomacy_catalog.py
```

生成器核对完整程序哈希，以 512 字节/150 指令为每项注册上限；其他指定入口使用 16 KiB/4,000 指令上限，不递归反汇编被调用函数。报告仅保存必要代码证据，不复制完整游戏资源。
