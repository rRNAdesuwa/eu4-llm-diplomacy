# 1.37.5 和平请求的 owned 对象生命周期

已闭合 `requestpeace → 内嵌 CPeaceOffer → 条款对象和辅助容器` 的静态构造、复制与析构路径，并恢复 GUI 的两种谈判方向。没有访问游戏进程、调用原生方法、构建 DLL 或修改 v11；`runtime_verified=false`、`execution_verified=false`。

本报告只适用于游戏 SHA256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。旧 `work/peace-offer-layout.md` 是 1.37.4，本文未复用其 RVA。

机器报告：`work/reports/native-owned-peace-1375.json`，SHA256 `f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d`。生成器固定既有 native inventory 与字段报告的完整 SHA，并直接验证磁盘 PE。

## 外层请求和嵌入对象

| 项目 | 1.37.5 证据 |
| --- | --- |
| requestpeace | token `293c`，vtable `1c7b840`，大小 `210` |
| 外层构造 | `598af0(this, actor, target, demand, offer_ptr, date)`；外层内存由调用者提供 |
| 外层 clone | `59ba40` 分配 `210`，然后 `975f40(dst+48, src+48)` |
| 外层 deleting destructor | `598b60` 先清理 `+48`，删除标志 bit0 非零才释放外层 `210` |
| CPeaceOffer | 嵌入外层 `+48`，大小 `1c0`，vtable `1c578b8` |
| 默认 / 参数构造 | `2c6890` / `975d40` |
| copy / assignment | `975f40(dst, src)` / `976120(已构造dst, src)` |
| cleanup / standalone deleting destructor | `9761c0` / `2c6980` |

表中数值均为十六进制。`598af0` 设置完整 actor/original/recipient handle、日期、envoy=-1、state=0、value=1、ID=0；另外设置 `diplomats+40=1`、`demand+41`、`force+208=0`。这些派生字段由解析/序列化 token 分别确认。存在 `force` 字段不意味着应该公开或绕过合法性、AI 接受。

通用 factory 的 `35d3aa` 分支先分配外层，再默认构造临时 CPeaceOffer、复制到外层，最后清理临时对象。默认 CPeaceOffer 也会分配哈希哨兵和桶数组，**不等于全零内存**。copy 会重新分配容器、克隆 component、重建索引并修正 `owner+e8=this`。不能把两者替换成 memcpy；不能对内嵌 `+48` 单独调用带释放标志的 deleting destructor。

## CPeaceOffer 布局与所有权

| 偏移 | 含义 | 所有权 |
| --- | --- | --- |
| `10 / 18 / 20` | giver / taker 完整国家 handle / is_demand byte | 值 |
| `28 / 40` | war_givers / war_takers，各三个指针的 vector | 拥有缓冲区；元素是 8 字节国家 handle |
| `58 / 70` | 实际 givers / takers，同上 | 同上 |
| `88` | 全部 component 指针 vector | **拥有缓冲区及每个 component** |
| `a0 / b8` | 尚未命名的辅助 vector | 仅确认释放缓冲区，不再次析构元素 |
| `d0` | 40 个 type 桶，每桶一个 component 指针 vector | 拥有两层缓冲区；指针是 `+88` 对象的别名 |
| `e8` | 辅助状态的 owner 回指 | copy 结束必须指向目标自身 |
| `f0 / f4` | 两个辅助 DWORD | 游戏语义尚未命名 |
| `f8` | 带 `30` 大小链节点的 hash | 节点还拥有 `68` 大小记录的 vector |
| `138 / 178` | 两个带 `40` 大小节点的复合 hash | 各有独立哨兵、桶数组与链节点 |
| `1b8 / 1b9` | 辅助状态初始化候选标志 / apply_penalties | byte；前者语义名称仍保留为候选 |

`giver/taker/is_demand/givers/takers/war_givers/war_takers/apply_penalties` 均来自本版本精确 token descriptor 和 `981690` 序列化写入，不再把国家 handle 误称为短字符串。`144150` 只复制四个 vector 的 8 字节值；不会复制国家对象。

## Component 克隆及索引

`976430` 遍历源 `+88`，调用 `9a1040` 为每个 component 创建独立对象，再追加到目标 `+88`。`9a1040` 根据虚槽 `+78` 返回描述符的首 DWORD，在 `9a1d9c` 的 40 项 switch 表中分派；大于 39 返回空。

生成器逐项解码全部 40 个复制 case，与既有 40 个 factory 的 vtable 对账，并确认每个 case 只有一次分配调用及字段复制。大小只有 `30/38/40/48`；对应四个 deleting destructor 为 `179550/1795c0/1795f0/99af60`，均仅恢复基类 vtable 并按删除标志释放对象本身，没有递归释放派生字段。字段中出现的世界/定义引用不因此成为可由 caller 提供的任意指针。

虚槽 `+78` 的 type getter 也逐一校验：类型 0–38 的描述符附加 QWORD 为零；类型 39 的附加 QWORD 从 component `+30` 复制定义指针。类型 39 的定义仍需要独立身份和生命周期约束，不能只看到 type=39 就接受任意指针。

只有 `component+20` 非零的对象被放入 `+d0` 分类索引。copy 保留它在源同类型桶中的序号；找不到则追加。未选中的 component 仍属于 `+88`，仍由其析构。索引元素不能再释放一次。

`976290` 先对 `+88` 每个非空指针调用虚析构槽 0，参数为 1；将 end 退回 begin，然后更换为 40 个空桶。`976120` 首先执行此清理，再把新参与国和条款分配给一个**已经构造**的目标。因此 assignment 不能代替未初始化内存的构造函数。

## 辅助 hash 和最终析构

`998290` 复制 `+f8` hash 的节点。节点键是 DWORD；`999850` 为其值分配 `68` 大小记录数组，`99a1d0` 逐字段复制。析构 `415e60 → 163c90` 先释放数组，再释放 `30` 大小链节点及哨兵。`68` 记录的游戏含义尚未命名；已审复制与释放路径没有逐元素析构。

`994280` 独立复制 `+138/+178` 两个 hash，`415e00` 释放其 `40` 大小链节点，桶数组另由 `c03b0` 释放。

`9761c0` 顺序为：删除 `+88` 的 component 对象；清理三个辅助 hash；清理 `+d0` 的所有桶及外层 vector；释放 `b8/a0/88/70/58/40/28` 缓冲区。索引清理只释放别名数组，不再删除 component。standalone `2c6980` 在 cleanup 后按标志释放 `1c0`；外层 requestpeace 只调用 cleanup 后释放自己的 `210`。

## GUI 如何选择谈判方向与战争

`13067b0` 把选定目标存入 GUI `+2c`，维护两份完整提案：

| GUI 提案 | 参数构造调用 | giver / taker |
| --- | --- | --- |
| `+48`，demand=true | `975d40(dst, player, target, 1)` | 目标给出，玩家取得 |
| `+208`，demand=false | `975d40(dst, target, player, 0)` | 玩家给出，目标取得 |

已有相同目标的缓存提案可能被直接深复制。GUI `+660` 选择两份提案之一。`130c280` 据此创建临时 requestpeace，但外层 actor/original 始终是当前玩家，recipient 始终是 GUI 目标；方向变化通过选择的内嵌提案和 demand byte 表达，不能只交换 actor/target。该函数执行 UI 评估后清理临时提案；本次没有把它误标为最终提交入口。

参数构造 `975d40` 会读取实时世界：`97bd30` 从 taker 的 giver 对应外交记录读取关系 root `+50`、DWORD count `+5c` 的 16 字节索引，返回当前两国的战争对象。`97bea0` 根据 taker 是否在 war `+48` 一侧，选择 war `+48/+78` 两方列表，填充 war_givers/war_takers，再按战争领导国、单独议和与属国关系派生实际 givers/takers。战争对象是借用的当前世界对象；没有恢复一个“写入 war 指针或任意 war ID”的公开构造参数。

随后 `978cd0` 初始化辅助状态，`97ed00` 生成大量当前可用候选条款。参数构造因此不是简单的“空白和平”初始化 API。`59b450` 也会独立查找当前 pair war，缺失则拒绝，再检查条款与普通外交合法性。

`59bb00` 是 requestpeace 虚槽 `+d0` 的回复谓词，检查 state 和外交记录；它不是 GUI 装配函数。

## 未决项与复现

- 尚未在当前版本实测 constructor/clone/destructor、部分分配失败的异常清理或最终 GUI 点击到 command/submit 的所有权交接。
- 尚未完整命名 `a0/b8` 辅助数组和 `68` 大小 hash 值记录；本报告不承诺可公开修改这些内部字段。
- 每种条款的合法性、战争分、AI 接受、最终战争效果仍须各自验证；本次所有权证据不提升执行状态。
- 使用当前 pair war 的原生构造需要可靠世界失效保护、完整战争身份复核及明确选择策略；相同国家 TAG 或地址并不能证明仍是同一局战争。

复现命令：

```powershell
python -B work/trace_owned_peace_1375.py --check
```

分析限定 50 个函数、40 个 clone switch case 和各自最多 12 条指令的 type getter；累计解码 32,108 字节，函数窗口最多 `6000`、每函数最多 5,000 条指令，总解码预算 128 KiB，内存保护阈值 768 MiB。没有递归遍历全部被调函数，也没有整库反汇编。
