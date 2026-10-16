# 早启动单人来源观察器候选（1.37.5）

本候选把既有静态证据收敛为一个有限、可实现的观察协议。新增的是磁盘证据、事件合同和可运行的**离线回放状态机**，不是已安装的原生 hook。它从不读游戏进程，不调用游戏，不产生外交请求；`production_ready`、`native_hook_coverage_verified`、`engine_lifetime_synchronized` 始终为 false。

新增报告：`work/reports/native-origin-witness-observer-1375.json`，SHA256
`1a6808bfe956d7738b1498fd693b099de9acd276a340deb4c93e3f83a0c03517`。
复现 `python work/trace_origin_witness_observer.py --check`。该报告固定四份前置报告的哈希，逐字节核验 23 个既有锚点，并新增 5 个有界函数。没有扩大为整文件反汇编或全程序覆盖主张。

## 本轮增加的两个边界

`1120dd0` 的 RCX 是 Play 回调对象。真正 frontend 来自 `[callback+0x30]`（`1120f86`、`1121685`）；不能把 RCX 本身写进来源绑定。

`10da520` 在 `10dae6c` 取 frontend `+0x330` 的 holder，作为运行 server 构造 `803270` 的第 4 个参数 R9。后者在 `8032d2` 把它传给基类构造，最终 `6e8c15` 写入 server `+0x330`。第 5 个参数仍是 frontend `+0x400`，callee 原始入口 RSP `+0x28` 指向它；`803d27` 把这份配置复制到 server `+0x1708`。

新观察点 `14c2530` 在 `10daede` 被调用：它将输入 owning pointer 移入 holder `+0x70`，清空输入指针，并可能在返回前通过 virtual 0 析构旧 server。因此，已经绑定的 holder 在这个入口上必须先撤销旧见证。初次受控启动则分别记录 entry 和正常 exit，确认移动的是本次构造的 server，不能只把相邻的两条日志视作因果。

运行 server 虚表 `1cb8460` 的槽 0 是 `80b420`。该入口调用 `80b570`，随后按标志释放 `0x5bc8` 字节；它是仅比较已绑定 server 地址的析构后备。上述两个点补充既有 world/context/transport 撤销集合，不替代它们。

`6ea0b0` 虽然紧随 server 构造被调用，实际有界代码只维护 server `+0x34/+0x38` 的计时状态。它不是已证明的 `game+0x1e00` 发布函数，不能用它的返回替代实际身份核验。

## 最小观察 profile

第一版仅识别完整看见的 **SP Play / direct type2 fallback** 序列。Steam 可用的 type1 / LobbySession 路径可记录原始事件，但本原型不为它建立见证；这不是把 type1 判为多人，而是限制首轮实现范围。

1. 捕获器已在 Play 发生前完成 exact-build 钉扎并报告事件序号起点。中途附加后只看到地图字段，不能补建来源历史。
2. 进入 `1120dd0`，绑定 callback、其 `+0x30` frontend、holder、game，以及 mode 0 和配置 `(1,0)`。新 Play 使旧 generation 失效。
3. 在该 Play 调用实例内看见 `811ab0` 清空 context，再看见 `113b350 → 14c8940` 以 type 2 构造 context；确认 `+54/+55=(0,1)`、transport 虚表 `1d96178`、`transport+70` 反向链接。
4. 同一 Play 实例内通过 `811ab0` 安装这个 context，确认输入 owning pointer 已消耗。Play 正常返回时，再读 frontend mode/config/start-pending。回退路径不会自动把旧网络配置修成单人配置，故任何非 `(1,0)` 值拒绝。
5. 后续 `10da520` 调用实例必须来自同一个 frontend。嵌套 `803270` 的调用返回地址为 `10daeb2`，第 4/5 参数分别绑定原 holder 和 frontend `+0x400`。`80b4c0` 的返回地址为 `803d2c`，源和目的必须分别是该配置与新 server `+0x1708`。
6. server 构造正常返回且类型/配置一致，随后 `14c2530` 在同一 frontend-update 实例中移动这个 server。所有 entry/exit、父实例及对象必须明确匹配；缺失、乱序、异常或跨线程事件不能靠后来的快照修复。
7. 所有受观察 native scope 退出后，在后续 `10a6ec0` frame 入口，核对实际 game/server/holder/context/transport、配置、玩家、数据库/block/index 和完整国家 handle。快照的 generation 必须前后一致。此时只能报告 `origin_sequence_observed=true`，不能报告生产可执行。

观察实例使用 observer 自有单调 span ID；它不是游戏对象地址，也不是用户 request ID。只允许 producer 从保存的原始寄存器、原始入口栈和只读结果建立事件。离线 JSON、外部 HTTP 请求或用户提交的 `bound_identity_match` 都不是可信来源，不能用于实际授权。

配置复制证明绑定到具体 server-constructor span；构造和 owning-pointer 发布绑定到同一 frontend-update span。重复构造不能借用上一次复制结果，后续 update 也不能借用前一次构造结果。首轮 profile 对重复或错阶段的构造、复制、发布直接拒绝。线程、地址、RVA、span 和 generation 等身份标量只接受严格整数，拒绝 Python 中相等的 bool/float 别名。

## 撤销与重入

继续采用已固定报告中的有限入口：应用清理、ResetGame、读档、game 重置/析构、逻辑 Clear、数据库构造/重建/析构；以及 `811ab0 / 14c9930 / 14c97e0 / 14cd8b0 / 14cd4d0 / 14c88f0 / 14c99c0` 和三类 transport close。再加本轮 holder/server 两个边界。

对共享容器 `8f4f0 / 8f4c0`，只能比较已绑定 `database+0x110` 的整数地址；对 context、transport、server 同样只比保存的入口对象身份。不要先解引用可能已释放的对象再判断它是否“有关”。`2e1a30` 的动态国家 Clear 可暂时保守撤销整份见证，但不能将每次命中命名为读档。

初始 Play 中预期的清空/创建/安装事件属于未授权的候选序列；它们不保留任何旧见证。候选序列之外，同一入口必须先撤销。任何失效发生后，外层函数正常返回也不能恢复旧 generation。新的完整 Play 观察仅能产生新的来源记录；是否创建新请求会话还需独立、显式的握手。

`14ca360` 是普通状态分派，不能每次进入都断言“发生迁移”。可把它作为**不可采样 scope**：入口计深度，退出消除深度，期间不提交观察完成记录；内部若命中已知失效入口则永久撤销本代。它在 transition helper 前已有通知虚调用，因此只在 `14cd8b0` 才开始记录重入是不够的。

## 能实现的同步，以及不能声称的同步

新解码的 frame `10a6ec0` 含 virtual `+8/+a0/+388/+78` 回调；其 helper `10afa70` 还调用其他虚方法。这不是无回调的安全区。静态 call 链没有证明所有读档/析构均在窗口线程，更没有证明引擎拥有一把可供适配器使用的生命周期锁。

未来原生 capture 层可以有限地做到：

- 用一个 packed atomic generation/revoked 值做入口撤销，先 release 发布撤销，再让原函数继续。计数溢出、未知线程、SEH 或未配对退出进入永久拒绝。
- 用固定容量、预分配的事件槽和 observer TLS span 栈记录调用；生产者只保留标量身份，不分配堆对象、不调用引擎、不同步写磁盘。容量或序号丢失使见证失效。多生产者不能让后面的记录越过尚未发布的前一序号。
- 构建候选只接受同一已绑定线程上的匹配 entry/exit；外线程的已绑定销毁入口仍必须立即原子撤销，不能排队等 frame 发现。
- 适配器自己的互斥量只能保护观察器数据，不能把游戏对象变成受锁保护的对象。不要在原生函数或通知回调周围持有会阻塞其他引擎线程的锁，也不要在析构钩子里等待正在运行的游戏调用完成，这会引入重入死锁。
- frame 快照的双读、generation 双读、线程 ID 相同都只能发现部分变化。它们不阻止另一个引擎线程在读取期间释放内存。因此本候选不为任何 native action 提供执行许可。

真正原生 capture 层仍需独立审核 ABI、入口指令搬迁、返回捕获、异常展开/尾调用、安装时机、外线程毁坏顺序和 event-buffer 内存序。它尚未编写或部署。最小动态验收先只观测启动、返回菜单、重复/失败读档、context 关闭/替换及退出；不要在此阶段发送外交动作。

## 可运行离线原型

路径 `work/candidates/origin-witness-observer-1375/observer.py`：读取有界 JSONL，检查上述实例/对象/序号和状态机约束。每次 `readline` 最多读取 16 KiB + 1 字节，超长立即拒绝；最多 10,000 条、最多 32 层 scope、4,096 个 span，候选启动最长 120 秒。EOF 时仍有未返回 scope 或未完成候选即撤销。它不认证输入、进程身份或日志来源，也不将合成回放变成运行证据。

```powershell
python -B -m unittest discover -s work/candidates/origin-witness-observer-1375 -p 'test*.py' -v
python work/candidates/origin-witness-observer-1375/observer.py work/candidates/origin-witness-observer-1375/example-synthetic.jsonl
```

16 个纯离线测试通过，包含完整序列、只有现存世界快照、参数错绑、跨线程、日志缺失/乱序、非规范配置、type1 拒绝、所有声明撤销入口、原址重建、重入失效以及未配对返回。独立复核新增的反例覆盖跨 update 发布、重复 constructor 借用 copy、EOF 未闭合 scope、bool/float 身份别名与读取前的行长度限制。测试不打开进程、不安装 hook，也不构建 DLL。
