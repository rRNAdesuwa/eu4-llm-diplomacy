# 1.37.5 来源捕获接入：最小下一版计划

本目录是可审阅计划，没有新 hook、trampoline、DLL、游戏读取或编译。沿用 exact EXE SHA `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`；22 个冻结输入见 `pins.json`，35 个原生点位及 70 个既有指令引用见 `plan.json`。没有新增反汇编，也没有改旧候选、宿主、manifest 或运行记录。

**下一版最小交付应是捕获器，不是生产单机判据。** 第一步只证明一个配置复制实例的入口与正常返回可以完整记录；随后逐项补齐来源、撤销和原始字段生产。`strict_single_player_verified`、`world_epoch_coverage_verified`、`engine_lifetime_synchronized`、`production_ready` 保持 false。即使来源 trace 完整，也不能授权原生外交。

## 已有成果与准确边界

`origin-native-capture-1375-v2` 已有 256 槽、32 层、固定容量捕获核心；其独立合成验证记录为 3690 checks / 0 failures。旧 README/review 中“尚未编译”描述的是当时源审阶段；后来的独立 validation 和 external review 记录了编译/测试。本计划不改写旧时间线，也没有重跑合成可执行文件。

核心只管理诊断数据：单次 CAS、连续 ticket、不跨洞读取、50ms 被轮询缺口超时、先撤销后写日志、终态不可恢复；它并不保存真实寄存器、读取对象、安装跳板或认证线程来源。Reservation 没有 owning Ring 身份，跨实例使用不属于合法调用合同。新接入层应私有封装单个 Capture，不能把 token、site 或地址作为外部参数。

现有离线 reducer 已修复跨 update 借构造、跨 constructor 借 copy、未闭合 EOF、身份 bool/float 别名等问题。但它接受的是合成事件，不是可信原生记录。目前没有 raw-record exporter、进程 envelope、startup mutation classifier、原始字段生产者或可执行 hook。

## 第一个试点：配置复制入口和原调用者的返回点

选择 `80b4c0` 配置复制，而不是一次安装全部 35 个点位。已知直接调用为 `803d27: call 80b4c0`，正常返回地址 `803d2c`。配置目标/来源为 server `+1708` 和 frontend `+400`；必须绑定具体 server-constructor span，不能用相邻日志推断。这个唯一已验证直接 caller 并不证明不存在间接调用。

| 位置 | 已有证据 | 下一步必须补齐 |
| --- | --- | --- |
| `80b4c0` 入口 | pdata `[80b4c0,80b544)`，xdata `1e6033c`；保存 RCX/RDX、原 RSP 和 `[RSP]` | 逐指令重定位、完整 xdata/handler 解释；不能把 32-byte pin 当覆盖长度 |
| `803d27` CALL | `e894770000`；RCX 从 `server+1708`，RDX 来自同次 ctor 参数 | 给出调用前后寄存器与栈不变量，并核任何可能进入覆盖区的控制流 |
| `803d2c` continuation | `90` 后是 `803d2d: mov [rsi+19f8],0` | 这里是 caller 内部代码，不是另一个函数入口；新日志不得破坏 RAX/RSI/flags 或写入顺序；所需搬移长度仍为 null |
| enclosing `803270` | pdata `[803270,80b41f)`，xdata `1e5fef0` | 解析其 handler/scope 数据；此前报告 `complete_function_claimed=false`，不能因单个 RET 已见就宣称所有异常出口闭合 |

待评估的实现路线是 **callee 入口 + 精确 caller continuation**，原 CALL/原返回身份保持不变。入口先保存机器状态，记录真实 current thread、原始 RCX/RDX/RSP/return VA；正常 continuation 仅消费匹配 site/thread/span/parent 的栈顶 token，并核 caller RSP 等于 callee 原入口 RSP+8。没有匹配 token 或出现异常/跨线程/重入/丢失即终止捕获。此处只定义所需合同，没有批准覆盖字节、机器码或返回跳板。

不能简单将 CALL 改为一个“调用原函数的包装器”，然后继续把 callee 实际 return VA 报成 `803d2c`：包装器会改变栈与返回地址，必须另建并审阅不同的事件合同。也不建议直接替换 `[RSP]` 捕获返回；其异常展开、尾调用及返回保护尚未证明。首个试点即使成功，也只能输出原始片段，不能伪造缺失的 frontend/update 父 span 来让 reducer 通过。

## 完整来源链仍需要的点位

| Scope | 参数和顺序绑定 | 当前状态 |
| --- | --- | --- |
| Play `1120dd0` | RCX 是 callback；frontend 是 `[callback+30]`，要求同实例 mode0/config(1,0) | callback 读取与全部返回/异常路径未实现 |
| fallback `113b350` / context ctor `14c8940` | ctor type 来自原 R9D；要求同 Play 的 fallback 子实例；返回 context vt `1d8c900`、type2/flags(0,1)、transport vt `1d96178`、反链一致 | 只支持 type2 候选；Steam type1 SP 属未支持路径，不能称多人 |
| context install `811ab0` | 保存 frontend/holder/owning input，返回后核 input consumed 和 holder+370 | `811b11` 是间接尾跳，`811b19` 才是普通 RET；仅挂 RET 会遗漏 |
| update `10da520` / server ctor `803270` | caller `10daead` / return `10daeb2`；原 R9=holder，原 callee RSP+28 是第5参 frontend+400 | 原始栈参数必须在 recorder prolog 前取值；同一 update 只能使用自己的 constructor |
| config copy `80b4c0` | return `803d2c`，destination=server+1708，source=frontend+400 | 精确绑定本次 ctor；不得复用前次 copy 标志 |
| holder publication `14c2530` | caller `10daede`；清 input `14c2559`，发布 holder+70 `14c2563`，旧 server 可能在 `14c2573` 析构 | 同 update、同新 server；input consumed 不是单看 RAX |
| opaque dispatch `14ca360` | 进入后禁止完成快照；内部通知可能早于 transition helper | 不能把每次命中叫迁移；异常、外线程、未闭合 scope 必须拒绝 |
| frame `10a6ec0` | 全部相关 scope 已正常退出后再核 roots / config / players / epoch | frame 含虚调用，不能当引擎生命周期锁 |

初始 Play 的 clear/init/install 与后续替换在原生上共用入口。已有 Capture 的 `invalidate` 永远先增加 epoch 并撤销；离线 reducer 对 invalidate 则丢弃 candidate。二者不能仅改事件名直接接在一起。下一份协议必须明确：原始撤销永不删除；旧 witness 在 Play 前已经失效；只有被同一可信 startup span 证明的预期初始化才可作为新候选的一部分。未知分支、非预期对象或外线程一律拒绝。packed epoch 与 reducer generation 的映射须独立测试，不能把 `word>>1` 或日志序号自动当二者等价。

## 必需撤销集合及覆盖限制

所有 28 个命名 revoker 都在 `plan.json`，与 9 个 origin scopes 重叠 2 个，共 35 个点位。计划没有把它们简化成一个“最小完整切集”。主要组为：

- 应用/世界：`1fefa0 / 210000 / 74b8a0 / 5cf740 / 749020 / 74bf70 / 74dd50 / 74a260 / 74c080`。
- 国家存储：`2812a0 / 2830a0 / 286250 / 2e1a30`；共享索引 `8f4f0 / 8f4c0` 仅比较已保存的 `database+110` 身份，不能先解引用再判归属。
- 上下文：`811ab0 / 14c9930 / 14c97e0 / 14cd8b0 / 14cd4d0 / 14c88f0 / 14c99c0`。
- transport：`1574fb0 / 157c620 / 1577280`；server 拥有式发布/析构：`14c2530 / 80b420 / 80b570`。

失效 hook 先原子撤销，再尝试诊断；日志满或 consumer 停止不能恢复旧见证。外线程只访问原子/环，不访问 owner 的 span 栈。不在析构入口等待正在运行的引擎调用，也不把适配器 mutex 说成引擎锁。

`1574fb0` 整个已解码函数只有 12 字节、无 pdata；32-byte identity pin 跨过函数末尾。不能套用一个 14-byte 跳转覆盖模板。`14ca360` 通知重入、别名写/间接调用、759 个未经逐 CFG 证明的 database 初始化模式以及其他生命周期路径，仍是有限覆盖的明确遗漏。`19f1==0` 不是世代计数器；`6eaa10=false` 与地址未变也不能证明来源未改变。

## Windows ABI、unwind 与线程门槛

Windows x64 的四个整型寄存器参数、shadow space 和栈对齐只是基础 ABI。任意原生指令处插入 recorder 还需保护该点仍存活的 volatile、flags、返回值及向量/控制状态；不能因为 helper 是普通 C++ 函数就假定透明。先定义支持的 CPU/XSTATE 范围，再用隔离机器状态测试核保存与恢复。[官方调用约定](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170)

每个跳板的栈变化和非易失寄存器保存都需要相符的 unwind 描述；原函数 pdata 不会自动覆盖搬到其他地址的指令。下一步解析上述 xdata 的 chain/handler/scope，再设计不吞异常的 termination 路径：异常越过 active token 前永久撤销，原异常仍继续展开。动态函数表的注册/有效生命周期也是接入要求，本计划没有调用它。[官方 x64 异常展开](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170)、[动态函数表](https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable)

早启动安装必须属于新的受控进程边界，完整 PID+creation/fullSHA/runtime bytes 绑定。现有“已入地图后加载”方式无法补造首次 Play 历史。是否能在 sites 首次可达前完成安装、如何避开 loader lock、怎样证明线程 IP 不在 patch 区、怎样处理部分安装失败，均未实现。不要通过关闭系统缓解策略来获得成功；未来 adapter 应查询实际策略并对不支持组合拒绝。[缓解策略查询](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocessmitigationpolicy)

owner thread 必须来自可信进程/线程绑定，并与真实 Play、update、后续 frame 一致；不能仅取任意第一条日志的数字。当前静态 call 链没有证明所有销毁均在此线程。generation 双读和暂停只能检测部分变化，不能阻止其他线程在读取或引擎调用中释放对象。因此完整 trace 成立以后，生产执行仍要另做引擎生命周期同步证明。

## 字段生产与导出合同不能省略

已有 reducer 要求的 `players_complete`、`only_local_ids`、`pending_transition`、`double_snapshot_equal` 并非可由外部或宿主直接传 true 的证明。此前 snapshot 草案给出了 game+1e00、server+330→holder+370、context+54/+55、game+a50 及节点+18/+60 等候选；还需逐项闭合节点 owner、遍历终止、宽度/角色、完整玩家集合及 pending 的语义。当前 raw producer 不存在，不在本轮猜布局。

raw record header 无 PID/creation envelope，payload 用 present mask+整数槽，reducer 则要求严格 bool/list/int；exporter 要按 site/kind schema 转换，缺字段不能转 0、非0布尔不能强转真，module RVA 必须从同一已钉扎基址推导。ticket 连续、时钟不回退、epoch前后稳定、捕获终态、source envelope 和文件内容绑定，都应由独立消费者检查。诊断文件不是签名的引擎证据，不能作为外部接口的授权令牌。

## 可执行的闭合顺序

`plan.json` 的 C01–C09 给出交付物、门槛及未支持项。建议下一次仅授权 C01：复用既有 CFG，读取 `1e6033c / 1e5fef0` 的有限 unwind/handler 数据，补 `80b4c0` 入口与 `803d2c` continuation 候选覆盖区的精确控制流/重定位说明。单轮新增 decode 上限 8 KiB；不重扫大函数，更不写 hook。

C02–C03 才是独立 machine-state / unwind 合成 adapter；C04–C07 补 startup 分类、早启动时机、28 revoker 与字段生产；C08 才可形成新的 capture-only 宿主候选并另行审阅。C09 的引擎同步证明独立保留。每一步都要求新的源/hash、反例和明确失败边界；本目录没有授权编译、安装或实际游戏试验。
