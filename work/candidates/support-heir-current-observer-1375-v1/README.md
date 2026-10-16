# 当前支持继承人任务候选

这是独立的 current pair 观察候选，只有 `check`、`catalog`、`status` 三个入口。草稿清单拒绝实际 status；须独立 source-ready、root 生产封存和生产清单审查后，才可另行授权查询。当前没有运行游戏查询，没有修改 stable15、候选18、原 native DLL 或冻结读取器。

返回 `selected_task_present`、`selected_task_absent` 或 `unknown`。exit0 只说明文件检查通过或当前选定状态获得一致观察；absence 的 exit0 不表示停止支持动作完成。exit2 表示未知或被 guard 拒绝。没有发送、HTTP、watch、自动重试、保存或重载入口。

## 索引与对象合同

复用冻结 relation() 证明选定 typed country 的 embedded root=`country+0x14f8`、owner、country+0x1510 及 row 的完整双方句柄。R50 原生 getter 仅经 row[0] 读取 O+0x140 数组、O+0x14c 有符号数量，以16 B步长比较 DWORD key，返回首匹配条目+8，包括零值；原生不检查类型、端点或生命周期字段。

独立 nullable_index 读取 `<Qii>`：+140 数组、+148 capacity、+14c used。**capacity、非负数量、最多256条、容量最多4096、正且有界唯一key、非零值的canonical/alignment均为额外reader guards**，不能说是 native 验证。保留 NULL entry value，不调用冻结 index() 的 nonnull 限制。只读取 active used entries。

两侧 selected_pointer 都为0才报告当前选定任务缺席；每侧 `key_present`、`lookup_zero_reason` 分别保留 missing/NULL 原始事实，允许混合。单侧非零或两个不同非零指针均 unknown。两侧同一非零 P 才读64 B；额外要求 vt RVA1c7c1c8、P08 DWORD raw357、P28 lifecycle候选 BYTE 为0、P10/P18完整端点集合等于选定pair，否则 unknown，不能当 absence。同地址不构成 lifetime lease。

P10/P18只称 endpoint1/endpoint2，不无条件命名 actor、target、supporter。crosswalk f25d2760…仅证明条件式初始化映射，交接和callee保留内存未知。P20/24/30/38/3c 原样输出，不命名日期、进度或继承结果；完整64 B raw保留。当前任务存在不是完整C++类验证、原请求效果、AI接受、最终继承人结果或持久化证明。

## 读取与身份边界

仅 status 接受显式 PID、16位非零小写creation、不同三字符actor/target。验证真实 held identity、精确 game path/PE/SHA、research module 拒绝和 manual pause=1。fresh readonly nonce 不当安装session或原请求ID。

沿已审 integration 的共享预算、journal、正常with退出再提交结构；exact-compile frozen direct-v1 Libraries，复用 oldhost sourceverify/host_sample。不会执行旧 main、固定80340 capture、Frida、registeredargv 或 Job。在生产 status 中 only QUERY/VM_READ/SYNCHRONIZE；没有写游戏内存或分配目标内存。

每遍完整fresh1380 pointer table、选定typed country/fullhandles、tablebinding、双向 relation 和 nullable index；两遍结果及原始table必须相等。loaded R48 `[595120,5961b4)` 4244 B 与 R50 `[a69ab0,a69af0)` 64 B 前后精确匹配，每轮4308 B、合8616 B；R50末5 B保留原像校验不等于把它们解码。正常返回CFG或原像匹配不开放游戏函数调用。

host前后/code前后/table/selected全部共用4096 calls、512 KiB、单读64 KiB预算，ordered raw RPM journal记地址、大小、顺序、bytes及失败。冻结 RuntimeCapture 入口PE身份8192 B读取另列。两遍相同、host/source后验、正常with退出、held.handleNone及最终source guard都满足才commit。CloseHandle原OS返回值未独立检查，输出明确 `close_os_return_checked=false`；非原子快照。

## 审查和离线准备

固定 R48/R50 exact manifest、contract、owned raw、两份独立静态审查与crosswalk；不执行静态producer或重读EXE。候选生产 gate 使用顶层 `independent_source_review={path,bytes,sha256}`，无需额外nested candidate map。draft自身的source_manifest不能代替source-ready或生产授权。

新fake只覆盖本模块NULL/missing、pointer/object、coherence、loaded/profile与commit边界。fixture初始化来自固定integration测试文件的setup，**未复制或运行其24个TestCase方法**；仅编译冻结reader选定纯函数AST，host仅对owned fake memory读。首次新测试、check、catalog通过后停止，由独立审查决定是否准备生产清单。

所有 selected/request effect、AI acceptance、final heir result、native mapping/predicate/ready、sender、完整class、lifetime、atomic、persistence flags 始终 false。未知不会被解释为原生拒绝或可重发许可。
