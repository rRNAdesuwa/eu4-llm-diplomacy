# 属国军役：FRA→NAV 原始只读生产者候选

本目录实现精确 EU4 1.37.5 的有限只读生产者，以及严格离线 snapshot 校验和稀疏内存反例。**没有访问实际游戏、构建/加载 DLL、执行 getter、创建 command 或写入任何国家字段。** 默认 actor 是当前完整 FRA，target 仅完整 NAV；没有任意国家、命令、RVA 或 TLS 参数入口。本候选不使用已结束批次的存档来推定当前属国关系。

`capture(reader,base)` 只调用提供者的 `read`；`sample_process(pid,creation,executable)` 是未来显式的 RO 入口，没有 CLI。后者持有同一个 QUERY_INFORMATION|VM_READ handle，核对 PID/完整 creation/未退出、精确路径、磁盘完整 EXE SHA、加载模块 PE signature；前后再核持有身份、PE、磁盘 SHA，并在 finally 关闭。所有测试均替换真实 OS reader/身份查询，不对任何 PID 采样。

## 原始数据链

1. 全局 DB `233d8d0`、game `233fe78`，DB array+118/count+124。count 1..4096，FRA/NAV 固定 full handle 的 slot 必须在真实 count 内；country+20 要匹配完整 generation。game+1e60 必须是 FRA，rawdate+1dd0 正数，已知 reset/load 排除字段 +7485/+74c8 为零。FRA 完整句柄的 byte6 不是 GUI 特殊 selector 值7，因此不会用该 GUI 的备用 player+1e68 分支；本候选不模拟任意切换玩家。
2. FRA country+1a18..+1a20 是 full subject handles，8 字节步长，最多256。每条都重新按 DB slot 读取 country+20/full handle 和 +18f0/overlord，必须实际属于 FRA、不可重复或别名。容量字段未在此读取或假设。NAV 要在该向量中出现一次，并且 NAV.overlord==FRA。
3. 双方 country+1510 的 opposite-slot×0x48 记录，核 +8 owner 和 +10 counterpart 完整句柄。记录 +0 指向 relation index owner；其 +128 array/+134 signed DWORD count 为 stride16 的 slot→object 索引。最多4096项，所有 slot 小于真实 DB count、slot 不重复、object 指针规范；只解析所选 FRA/NAV object，不跟随其他关系对象。
4. 两索引必须指向同一 dependency，vtable=`base+1c81758`、DWORD+8=`165`、+10=FRA、+18=NAV、BYTE+28=0，+40 为 definition。未知 vtable 在读取派生字段前拒绝。+20 原始 started_date 仅保留；它不能归属于某条请求。
5. definition vtable=`base+1ce7488`、marker165；`name+10` 为有界 String32；`DWORD+30` 为注册向量 ordinal，`QWORD+38` 为 self 指针；`BYTE+14f` 和 `BYTE+15a` 分别是 uses_military_focus/can_set_mil_focus，不能混用。两个字节原样输出严格0/1；0不代表采样失败，也不被当作授权。目标 `DWORD+2864` 必须0..5，另保留命令 gate 所读 country+1344 和 +26，未调用 gate。
6. global `233ffd8` 的 registry+40/+48/+50 是 definition pointer vector。读取的 selected definition 必须出现在其 ordinal，向量唯一、count/capacity受限；若名称为 vassal，另要求 cache+58 同指针。其他向量项仅记录 canonical pointer，不读取未知对象。注册数量、定义向量数量相等是本候选保守一致性条件，不声称游戏的普遍上限或全部加载过程都满足它。
7. 名称 lookup 进一步按原生 FNV-1（32位乘后异或）选 registry+18 的桶，mask在+30、bucket_count在+38。只读一个桶，从 bucket+8 的 last 沿 node+8 逆向到 bucket first；node+10 是 String32、node+30 是 definition。核名字属于该桶、唯一、相邻 next 反链及指针属于定义向量，最终精确名称只能映射所选 definition。最多256 collision nodes，绝不调用 `b23df0` 或 `1fd1a0`。未知/未完整关闭的链明确拒绝。

名称字符串读长1..128、capacity<=4096；capacity<16为SSO，否则读取规范 heap 指针及恰当长度/NUL。ASCII标识符、精确长度、key 内容都被保留。registry 全局 null、缓存未就绪、向量/索引缺项、未知类型或越界均是 unsupported/拒绝，不能用调用原生初始化来“补齐”。

NAV 与 FRA 没有直属 graph 且三方观测一致时，输出 `outside_fixed_direct_subject_scope`，definition/registry=null，不读取未知当前属国类型。overlord、向量与双索引互相矛盾时直接拒绝整份样本，不能制造“无属国”结论。一般其他宗主/subject 类型的权限、特殊 UI 过滤或服务器授权没有实现。

## 静态来源与界限

`trace.py` 复用并逐字节核对 sealed military-focus/cancel/effects 三份报告。唯一新增 CFG 是调用点已经给出的 `1fd1a0`，204 字节，窗口8KiB，总新解码上限32KiB。`b231f0` 中 `b23413..b23479` 证明 definition vector/ordinal/self，`b237ea..b237f7` 证明 append；`b23df0` 证明 hash 和查找后 node+30，`1fd1a0` 补齐桶/逆向链/名称比较。没有全文件反汇编或无界函数扫描。

加载时只核少量原始指令 pins 和已识别 vtable 槽，QWORD vtable slots 按实际 module base 重定位比较。完整磁盘 SHA/PE 不等于加载映像完整哈希。指针约束、字段类型、双遍一致也不证明对象不会释放、ABA不存在、SP来源、world epoch或引擎线程同步。

总 payload 读预算16MiB、单次64KiB、8192 reads；主体向量256、relation index4096、registry definitions/buckets4096、selected hash bucket256。包装器再把 legacy PE 守卫读取纳入16MiB总字节限额。两遍共享预算，每遍末尾重读 roots，前后复核代码与 vtable pins；两遍完整 selected state 必须相同。

## 输出不授予执行能力

enum entitlement 恒为 `unsupported_tls_and_lazy_query`。不读取/命名 DLC globals，也不猜 TEB/TLS slot 或调用 `975360/9753f0/1a334c0`；focus0 的静态 true 叶路径不能证明完整权限。暂停、双采样相同、both definition flags=1、命令 gate 条件候选满足，都不会把 `native_call_authorized` 或 `complete_native_authority_verified` 设为 true。

`compare_snapshots` 仅允许同日、同身份和完整 graph/definition/registry/gate 输入、只改变 focus 值的 selected correlation；所有 native/效果/因果/生产标志恒false。导入 snapshot 具有严格 schema（所有数字拒绝bool/float、所有嵌套字典拒缺键/多键），但不认证文件来源。实际采样以后必须另有独立 PID/creation/原始记录SHA envelope，不能把人工 snapshot 或 mock 成功当成原始内存证明。

下一步只能是由 root 在明确的新 baseline 上安排独立 RO 样本，并确认 graph 符合当前范围。无发送生命周期、clone 的消耗式 String32 参数、异常清理、权限与最终队列执行都属于之后另审的实验，不包含在本候选。

## 离线验证

```powershell
python -B work/candidates/subject-military-focus-observer-1375/trace.py --check
python -B -m unittest discover -s work/candidates/subject-military-focus-observer-1375 -p test_observer.py -v
python -B work/candidates/subject-military-focus-observer-1375/prepare.py --check
```

28个测试 methods 含86个整数字段逐项 bool/float 反例，真实 hash collision 链、缺项/重复/环/边界、unknown vtable 不读派生字段、双遍/root/pin变化、独立NAV不解引用registry、同日focus比较及全部OS入口mock后的finally close。开发首轮仅测试里的“字段数>100”计数假设错误（实际86），改为明确86后所有反例均执行通过；未以删除反例掩盖 producer 错误。`validation-results` 保留封版前后的源SHA、命令、完整stdout和exit。
