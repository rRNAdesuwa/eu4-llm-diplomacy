# 议和前提：原始只读内存生产者候选

本目录把前一个已审 RO schema 的字段路径实现为有限原始内存读取。**没有在游戏进程上执行过**，没有调用任何游戏函数、安装 hook、写进程或构造 offer。当前可运行部分只有稀疏内存测试和磁盘字节核验。

`raw_observer.capture(reader, base, actor, recipient, direction)` 仅调用传入 reader 的 `read(address, size)`，返回两份一致的字段观察与读取地址/宽度/SHA 轨迹。生产者会在两次采样前后核对固定指令与已识别战争目标的虚表槽，完整枚举所有选定有界数组，拒绝缺页、短读、负计数、超限、重复键、完整 handle 不匹配或采样变化。

`sample_process(...)` 是供下一次独立审查使用的显式函数，**没有 live CLI，也没有在本轮调用真实实现**。它复用固定 SHA 的 `work/probe_diplomacy_current.py::ProcessReader`，仅申请 `PROCESS_QUERY_INFORMATION | PROCESS_VM_READ`；要求调用者显式提供 PID、16位十六进制 creation、精确 `eu4.exe` 路径与双方完整 handles。构造前核磁盘完整 SHA；持有句柄后核路径、加载模块 PE 时间戳/大小、`GetProcessId/GetProcessTimes`，采样后再次核同一句柄身份、PE 与磁盘 SHA。所有退出路径均关闭句柄。没有增加线程查询、NtQuery、TEB 或 TLS API。

## 已实现的读取

| 查询 | 范围与拒绝条件 |
|---|---|
| 当前 roots | 全局 `233d8d0/233fe78`，database `+118/+124` 指针向量，game `+1dd0` 日期；实际容量必须1..4096。`+110` wrapper/`+118` pointer/`+124` count 的相邻销毁清零锚另加入 `pins.json`，每个国家仍必须以 `country+20` 完整 handle 再验证。 |
| 双向战争索引 | 关系记录 `+0/+10`，root `+50/+5c`，16字节项。双方完整 handle、唯一 slot key、同一借用 war 必须一致。仅两个完整索引都无匹配，返回 `no_matching_war`；一侧缺失/另一侧存在为错误。 |
| 战争双方 | war `+48/+50` 与 `+78/+80`，每侧1..64 full handles；所有成员重新对应 country，拒绝同 slot 不同 handle、重叠双方、谈判国不在相反侧。保留 A/B 名称，不伪造 war ID。 |
| 国家政府 | `country+1420`、instance `+10`、variant pointer `+170/+110`。仅 type0/-1 才读取 variant `+8` byte；其他类型不假读 bool 存储。政府动态 vtable 始终标记 unreviewed，直接字段观察不宣称整个类已识别。 |
| 延迟缓存全局 | `233fe88` nogovernment 与 `242bc80` secondary 只读取指针值；缺失实例不调用 getter，也不解引用缓存来假装实例存在。 |
| 战争目标 | war `+160`：未知 vtable 只记录该 vtable，不读取 take_colony 派生字段。精确 `1d1fd90` 方法槽已核后才复现已审 `+70` 的只读字段判断，检查省份数组长度和 `blocks+index*2e10+560`。失败时不调用或解引用 fallback 类，也不沿用原定义条件。fallback 全局是 `2340030`。 |
| 条件与附庸定义 | `233ffd8→+80` 独立定义，`+48/+54` 条件列表；识别目标定义的四个条件容器 `50/140/288/378`。每个最多64项。只读取对象 vtable 与 virtual30 地址；仅当 vtable 位于精确模块只读非执行 section 时才读槽。未知外部类不继续解引用，任何情况均不执行条件、不声明纯度。无战争时不追附庸定义。 |
| TLS 全局门槛 | 仅 `233ff94/233fed6` 两 BYTE 和 `233c574` DWORD 索引。没有 thread ID/GS/TEB 的真实来源，因此 TLS 实例明确 `unsupported_subject_thread_gs_provenance`。 |

读取预算累计最多16MiB、单次64KiB、最多8192次；数组容量另有更小上限。legacy live reader 的16MiB总预算也覆盖 PE 守卫读取，新查询预算不取代它。报告中 `process_bytes_including_pe_guards`（仅 future wrapper）记录完整 legacy 计数。每次失败只结束这一轮，没有重新采样直到“碰巧一致”的重试。

## 为什么尚不输出旧 schema 的完整通过证明

旧 schema 必须有真实目标线程的 TLS 观察和严格 bool 的暂停值。此生产者尚未证明如何安全取得那个线程的 GS/TEB，也不凭空引入暂停字段。因此报告明确 `schema_projection.available=false`，列出缺少的线程/TLS、暂停观察与完整投影 adapter。没有填 `thread_id=0`、虚构 TLS 值或把缺页当作 `paused=false`。它产生的是已完成部分的原始字段观察，未调用旧 parser 来伪造完整 schema 通过。

后续若实现投影，还必须保留 null/missing/unsupported 的区分，绑定每个派生值的原始地址与宽度。政府 bool variant 不是 condition pointer；没有匹配战争不是默认 offer/白和平；未知目标类不能套用示例类布局。双采样和相同 root/date 不证明世界世代或对象生存期，暂停也不能消除 lazy cache、TLS 与脚本/日志副作用。

`parameter_constructor_authorized`、`parameter_selftest_ready`、`runtime_constructor_verified`、`world_epoch_verified`、`object_lifetime_verified` 和 `production_ready` 始终为 false。稀疏内存测试只验证读取与拒绝逻辑，不能证明实际游戏对象当前存在。

## 固定输入与重放

`prepare.py` 校验前一个候选五文件、精确 EXE、两个 legacy reader 源、基础 build/config 源及 world-epoch 报告。复用已审指令，没有新增解码或全文件反汇编。`pins.json` 固定 SHA 为 `e468636ad6d210304112382a5ef44627411caa146e10a63fd55cb41943cf939c`。先前 RO schema 与 v14/共享 support 保持原字节。

```powershell
python -B work/candidates/peace-constructor-preconditions-raw-ro-1375/prepare.py --check
python -B work/candidates/peace-constructor-preconditions-raw-ro-1375/test_raw_observer.py
```

测试构造稀疏虚拟地址空间；代码 pin、虚表单元及只读字段都由测试字节提供。对 future wrapper 的测试明确 mock `ProcessReader` 和 held identity；不会打开真实句柄。
