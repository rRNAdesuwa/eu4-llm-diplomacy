# C01：配置复制试点的 unwind / relocation 有界说明

本目录只读精确 SHA 的磁盘 EXE，复用既有来源 CFG；没有编译、hook、游戏访问或冻结文件修改。报告共解码 810 字节，其中此前报告未覆盖的 524 字节，低于 8 KiB；有界元数据读取含重复仅 2635 字节。`trace.py --check` 可重放。所有候选覆盖长度都只是分析对象，`approved_patch=false`。

## 指令和栈边界

原 CALL 是 `803d27: e894770000`，其正常返回为 `803d2c`。RCX 来自 `RSI+1708`；RDX 从 `[RBP+3b0]` 取得。父构造入口建立 `RBP=entry_RSP-388`，所以该来源槽等于原始入口 RSP+28，即第五参数；不能在记录器改栈后再按未变的偏移读参数。

callee `80b4c0..80b544` 全长 132 字节。prolog 长 15，保存 RBX、RCX，push RDI，再分配 20h：完整 prolog 后 RSP 比入口少 28h，RBX 保存槽相对新 RSP 为 38h。callee 正常返回 RAX=目标对象；continuation 的 RSP 必须等于 callee 原入口 RSP+8。父构造分配 450h、另有 7 个 push，总差 488h；保存 RBX 及 XMM6–12。寄存器保护必须以真实机器状态为准，不能只保护 Windows 参数寄存器。

| 位置 | 容纳至少 5 字节的整指令区 | 容纳至少 14 字节的整指令区 | 局部指令性质 |
|---|---:|---:|---|
| callee 入口 80b4c0 | 5 字节，首条保存 RBX | 15 字节，完整 prolog | 无 RIP 相对或控制转移；15 字节跨越 push/sub 栈变化 |
| continuation 803d2c | 12 字节，NOP + 一条写零 | 23 字节，NOP + 两条写零 | 无 RIP 相对或控制转移；写 server+19f8/+1a00，必须保持顺序 |

近跳转还要求目标在 rel32 范围内，本轮没有分配位置或跳板。绝不能把 identity pin 当作 patch。既有有限 CFG 中未发现进入这些区间内部的 direct branch，但父构造 CFG 本来就未覆盖整个 pdata 范围；未知间接入口及其他调用者未排除。报告因此不宣称完整入边证明。

## 两个函数都有终止处理，不是无清理的普通 leaf

两个 UNWIND_INFO 都是 version1、flags2 (`UHANDLER`)，没有 chain，handler RVA 为 `1a34e3c`。该 handler 读取语言数据，再调用 `1a34360`；其逐位字段解码及压缩整数表与本机 Microsoft `ehdata4_export.h` 一致。该头的 SHA 被钉扎，报告只把这条有限证据识别为 FH4 格式，未将语言数据误当通用 SEH scope table。Windows 的标准 unwind 字段及语言数据边界依据 [Microsoft x64 异常处理文档](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170)。

callee 的 FH4 header 为 28h，含 EHs 和 unwind map；仅 1 项清理。状态 0 的类型为“栈槽中对象指针”，frame offset 30h，action `956c0` 尾跳 `95660`，对应构造中的 String。IP 表在 `80b509` 为 -1，`80b517` 为 0。这是异常清理合同，不是允许记录器调用析构的授权。

父构造有 146 项 unwind entry 和 89 项 IP→state。`803d27` 及 continuation `803d2c` 属 state31；该链先清理 server+16d0（funclet `1ae6870`），未包含 state32 的 server+1708 配置清理（funclet `1ae6890`→`80b550`）。这与原编译器只在其选定的可能抛异常点发布清理状态有关：**在 continuation 插入新的记录器调用，若其抛出或故障，不能仅借用原 PC 的状态31就宣称新构造好的配置仍得到正确清理。** 本轮不猜如何将新 IP 映射到 state32 或后续状态。

## 可以推进的最小下一步与仍不支持项

1. 先定义固定的机器状态保存合同与异常行为：入口/continuation 的全部现场、RFLAGS、向量/XSTATE、原始 RSP/返回地址、同线程及父 span。新记录函数应无分配、无引擎调用，但这仍不自动排除访问故障。
2. 为每个跳板指令边界设计独立 unwind 元数据；原函数的 pdata 不自动覆盖搬移地址。用隔离合成函数核 RtlVirtualUnwind、正常返回和异常穿越，并证明不会吞异常、丢失 active token 或误清理引擎对象。
3. continuation 的异常归属是具体阻断：需审阅能保持原清理语义的方案。不能靠 catch-all 返回、超时撤销或人为替换 `[RSP]` 绕过它。
4. 安装前线程静止、未知入边、早启动来源、原址替换撤销、真实 owner thread 和引擎生命周期同步仍是独立未闭合项。

严格单机、世界世代完整覆盖、引擎同步、可执行 hook 均为 false。这份 RO dossier 不授权参数构造或外交执行。
