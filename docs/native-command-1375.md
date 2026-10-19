# EU4 1.37.5 外交通用命令链静态审计

本页与 `work/reports/native-command-1.37.5.json` 仅适用于 SHA256
`9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A`。
地址均为 RVA，运行时需加真实模块基址。以下结论来自本机 EXE 有界反汇编，尚无新桥接发送或状态结算实测。

## 动作、命令和所有权

1. `action.vtable+0x40` 的公共实现 `0x4e9930` 接收 `RCX=action`、`RDX=command输出指针容器`。
2. 它调用 `action.vtable+0xb0` 克隆动作；克隆 `+0x2c` 写为当前游戏日期，分配 `0x58` 字节 command，令 `command+0x50` 持有克隆。
3. command 虚表为 `0x1c814b0`，类型标识写 `0x2934`；构造结果写入输出容器，函数返回该容器地址。
4. `0xbfe50` 接收 command 指针容器，从游戏对象的 server `+0x1e00` 经 `vtable+0x80` 取得发送上下文，再调用 `0x14ca210`。原容器先清零再转交，说明这里有明确所有权转移，不能发送后无条件再次析构 command。
5. command 析构 `0x4e7470` 先检查所持 action 的 `vtable+0xa8`；非特殊共享对象才调用 action deleting destructor，然后销毁字符串并按 flags 决定释放 `0x58` 字节。不得给未知 factory 返回的共享哨兵套用普通释放逻辑。

这些是静态 ABI 证据，不是可在任意外部线程调用的授权。工厂、克隆、检查和投递必须在已核验的游戏线程上下文执行，且各类额外参数、DLC条件与响应生命周期须另外验证。

## 可用性检查与冷却

command `vtable+0x40 = 0x4e8630`：

- 对初始动作状态 `action+0x34 == 0`，并在 `action.vtable+0x100` 返回真时检查关系冷却。
- 以 `original` 国家 `action+0x18` 定位国家对象；其 `+0x1510` 是关系数组，目标国家 slot 对应的记录宽 `0x48`，记录 `+0x30` 是冷却截止原始日期。
- 正常路径要求 `game+0x1dd0 > cooldown_until`，是严格大于，不是大于等于。
- 随后还检查其他费用和 action 的 `vtable+0x80`；通过冷却不等于动作合法。

执行函数 `0x4e7c50` 在首次有效性检查后，对部分动作调用 `0x35a830` 写关系冷却，然后才检查空闲外交官。故外交官不足仍可能留下冷却；不得盲目重试。

`0x35a830` 从全局 `0x233e064` 读取月份参数，调用日期加法 `0x14c8030`，把结果写回上述关系记录。与原版 `NDiplomacy.DIPLOMAT_COOLDOWN_TIME = 1` 的配置一致；配置为 0 的同日重复提交仍需实测，不应绕过原生检查。

## 执行与响应

command `vtable+0x48 = 0x4e7c50`：

- 先调用 action `+0x80` 原生有效性检查。
- 通过国家 `+0x1480 -> +0x18` 的外交官管理器检查可用资源，不能仅依赖外部预检。
- 调用 `0x4ea820` 处理动作效果／通知／外交官任务。
- 对需要回应的动作克隆对象，根据原生判断设置响应状态，并再次经 action `+0x40` 包装与 `0xbfe50` 投递，或放入目标国待处理消息队列。

因此不能直接调用效果函数并称作“向 AI 发起原生外交”。通用 wrapper、原生判定、外交官资源、投递、对方响应和最终游戏效果需要连起来验收。当前静态阶段没有证明每个动作的状态编号语义均一致，也没有完成外交权限独占拦截。

## 当前构建全局对象

| 项目 | RVA / 偏移 | 证据 |
| --- | --- | --- |
| 国家数据库全局指针 | `0x233d8d0` | 当前 command gate/execute 的 RIP 相对引用 |
| 游戏对象全局指针 | `0x233fe78` | command wrapper 与发送函数 RIP 相对引用 |
| 国家数组 | database `+0x118` | gate/execute 按 handle slot 读取 |
| 当前原始日期 | game `+0x1dd0` | wrapper 写 clone 日期、gate 比较 |
| 关系数组及冷却 | country `+0x1510`, slot `*0x48 +0x30` | gate 与 `0x35a830` 写入一致 |

这些全局地址相对旧构建发生了变化，部分虚表地址恰巧相同不能当成版本兼容证据。旧 1.37.4 DLL 不能用于当前 EXE。

复现：

```powershell
python -B work/discover_diplomacy.py --exe "$env:EU4_GAME_ROOT/eu4.exe" --deps-dir "$env:TEMP/eu4-native-analysis-deps" --rva 0x4e9930 --rva 0x4e7c50 --rva 0x4e8630 --rva 0x4e7470 --output work/runtime/common-diplomacy-command.json
python -B work/discover_diplomacy.py --exe "$env:EU4_GAME_ROOT/eu4.exe" --deps-dir "$env:TEMP/eu4-native-analysis-deps" --rva 0x35a830 --rva 0x4ea820 --rva 0xbfe50 --rva 0x4e8520 --output work/runtime/common-diplomacy-dispatch.json
```

需要 Capstone 5；可以使用自己的依赖目录。只解码 `.pdata` 指定的有限函数范围，函数后的 jump table 不应作为指令解释。
