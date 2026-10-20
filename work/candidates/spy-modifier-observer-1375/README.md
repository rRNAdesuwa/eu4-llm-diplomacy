# 五类间谍修正的只读观察候选

这是精确 EU4 1.37.5 EXE 的静态研究与稀疏内存模拟候选。没有读取游戏、调用游戏函数、构建或加载 DLL，也没有更改现有宿主。当前 `runtime_verified`、`native_call_authorized`、`production_ready` 恒为 false。

优先用途是下一轮 **corrupt_officials 正向动作** 的独立前后观察。其余四族复用已分别核对的容器布局，但各自绑定名称、注册槽、能力字节及费用/持续时间 globals。不能把 `value=false` 当作取消；入口明确拒绝 false、整数 1 或任意额外动作。

| 家族 | 注册槽 | 定义名称 | actor 能力偏移 | 持续时间单位 |
|---|---:|---|---:|---|
| corrupt_officials | 0x160 | corrupt_officials | 0x86 | 天 |
| sabotage_reputation | 0x150 | reputation_sabotaged | 0x80 | 天 |
| sow_discontent | 0x140 | discontent_sowed | 0x83 | 天 |
| slander_merchants | 0x170 | merchants_slandered | 0x81 | 月乘 30 天 |
| sabotage_recruitment | 0x180 | recruitment_sabotaged | 0x82 | 月乘 30 天 |

`trace.py` 只新增解码 11 个指定函数、共 12,573 字节，单函数窗口不超过 8 KiB，总预算 16 KiB。原 spy 报告的六个函数按 JSON pointer 引用并逐指令核对磁盘字节，不重新扫描其 52 个 CFG。`report.json` 保存原始字节、有限边、PE/字符串/引用来源。探索中间文件单独保留，不属于运行合同。

## 定义解析

`8ed850` 把五个精确名称传入 `8f42b0`，后者调用 `8eef60`，将返回指针写入缓存槽并把槽后 BYTE 标为 1。关键区别是：**查询失败也会写入共享空定义**。`8f58f0` 起初令这些槽共同指向 global `2458c68`；`8eef60` 失败仍返回它。

候选只读 global `242bd08` 已存在的注册表，不调用可能初始化它的 `8ecec0`。必须同时观察：缓存 flag=1、指针不同于默认 sentinel、definition 的 vtable 位于当前精确模块只读段、`virtual+90` 地址等于已钉扎的常量 true 叶函数 `8f440`，以及 `definition+158` 的精确名称。默认对象 vtable `1c48378` 的该槽是 `8f450`，返回 false。

名称布局由 `8ef020..8ef03a` 的真实查表比较证明：String32，QWORD length 在 +10、capacity 在 +18；capacity<16 走 SSO，否则间接字符指针。读长 1..128，capacity<=4096，ASCII 标识符、精确 length/NUL。只读方案不调用 virtual90，也不声称已识别所有可能的具体派生类；其他虚槽实现保留 unsupported。

## 修正容器与结果边界

target country `+1f0/+1f8/+200` 是 head/tail/DWORD count。最多 256 个 0x20 节点；逐个核对前后链、首尾、真实 count、去重及 BYTE+18=0。非零标记语义未完整闭合，所以拒绝整份样本，不借此推断已删除。未知 object vtable 只记录对象地址和虚表，绝不读取派生字段；存在未知对象时不能声称完整的 selected absence。

已知 object 的 vtable 为 `1ce8040`、DWORD+8 为 `165`、构造分配 0x50；读取 definition+30、associated+38、expiry+44。只有所选定义且 associated=null 才属于本候选关联。expiry 原始值仍保留；过期对象不等于列表中不存在。`active_by_expiry_comparison` 仅是 `expiry >= sampled_date` 的字段比较，不是对实际逐日清理时机的证明。

`compare_snapshots` 严格检查所有嵌套键/类型（bool 和 float 不能冒充 int），要求相同家族、国家、完整句柄、进程外的 world roots、同一天、定义、能力及费用输入。新节点和新对象地址都必须不在 before 列表中，且 expiry 精确等于 `date + live_duration * day_multiplier * 24`。输出只称同日 selected correlation；对象没有记录发起国家，因此没有 request ID 因果、AI 回复、脚本纯净性或 applied 结论。刷新/叠加不在接受范围。这个导入比较器也不认证文件来源；未来验收仍须绑定采集器、进程 envelope 和原始记录哈希。

## 费用与能力

actor+2440 已存在指针上的 BYTE 是 full preview 的一个能力条件。null 输出 unknown，0 保留 0；二者都不等于完整原生合法性结果。不能只调用旧通用 preview/command gate 来代替该族 `virtual+88`。

基础费用从该族 getter 对应 global 读取。actor+1510 关系数组按 target 的真实 slot×0x48 定位，核对 +8 owner 完整句柄、+10 counterpart 完整句柄；+18 signed WORD 是 0..10000 的网络百分之一点单位。目标 `+18f0` 高字节非零意味着原生可能重定向到宗主，本版拒绝此目标，绝不假借另一条关系记录。

`4ea610` 的最终费用不是基础常数：它调用 `93d750(actor+28c0)`，读取 id `261` 的 modifier，再可能经过 global `2358080` 所指对象 `+e4a0` 的 virtual8。getter 可进入线程/延迟诊断路径，不能调用。静态可重建的窄分支要求 actor+28c8 DWORD !=1、aggregate actor+28d0 的 dense BYTE=0、最多 4096 个唯一 id/value 8B 条目、转换根存在且转换对象=null。此时费用候选为 `base_milli*(1000+modifier)/1000` 的已限制非负整数分支。输出明确是 static candidate。

state=1、dense 存储、缺少转换根、非空动态转换对象、越界数值都保留 unknown；dense 数据不被索引，动态对象不被解引用。此方案不重建 TLS，不调用 lazy getter，不声称 aggregate 具有有效引擎锁或 lifetime。即便静态计算分支可读，合法性、脚本条件和所有其他 world effects 仍不成立。

## 采样边界与后续路径

- `capture(read_only_reader, module_base, family=..., target=...)` 只使用 reader.read；默认 FRA→ENG，目标仅 ENG/POR/NAV/FOI 的固定完整句柄。
- 两次完整样本包含 roots、player、country slots/full handles、已知 reset/load 排除标志、定义、能力、费用、列表。每遍末尾重读 roots，前后钉扎少量布局相关代码。两遍不一致即拒绝，不输出 absence。
- `sample_process(...)` 是**未来显式调用**的入口，无 CLI。本轮仅用 mock 替换。它复用 legacy 的 QUERY_INFORMATION|VM_READ、精确路径/完整磁盘 EXE SHA/PE signature、模块核验；持有同一 handle 前后核 PID/GetProcessTimes creation/未退出，并在 finally 关闭。未完整哈希内存映像。
- 总读预算 16 MiB、单次 64 KiB、最多 8192 reads（两遍共用）；节点 256、字符串 128、country count 4096、sparse modifier count 4096。窗口由外部宿主另行确认；不假造 paused。

下一次动态前置应先由 root 审查并单独授权固定新进程的 RO 样本，确认 definition cache/name/true90、独立目标关系方向、capability 和成本窄分支均可解释。若实际 definition subtype 或 aggregate 分支不支持，应另做有限静态研究，不能通过虚函数来“补读”。然后才讨论独立新版本原生生命周期、该族 full preview 与单次正向试验；本观察器不会授予这些权限。

暂停、同一地址、相同日期、两遍一致均不证明 strict SP、可靠 world epoch、引擎线程同步、ABA 不存在或对象 lifetime。不能以网络扣费、修正新出现、命令消费或接口返回值单独宣布完整动作 applied。

## 离线重放

```powershell
${USERPROFILE}\AppData\Local\Programs\Python\Python312\python.exe -B work/candidates/spy-modifier-observer-1375/trace.py --check
${USERPROFILE}\AppData\Local\Programs\Python\Python312\python.exe -B -m unittest discover -s work/candidates/spy-modifier-observer-1375 -p test_observer.py -v
${USERPROFILE}\AppData\Local\Programs\Python\Python312\python.exe -B work/candidates/spy-modifier-observer-1375/prepare.py --check
```

31 个 test methods，另有全部 snapshot 整数字段的 bool/float 遍历反例；未来 wrapper 只以 mock 检查成功、身份变化、拒绝前不 open、finally close。真实 Windows/游戏采样未执行。
