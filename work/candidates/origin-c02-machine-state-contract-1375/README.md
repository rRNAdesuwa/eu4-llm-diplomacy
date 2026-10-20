# C02：C01 试点的机器状态与异常政策合同

这是新建的静态合同及离线反例模型，**目前没有任何获准执行的 hook profile**。未编译原生代码、未写跳板、未读进程、未修改冻结输入。`prepare.py --check` 从钉扎的 C01、集成计划和捕获核心重建 `contract.json`；本轮新增 EXE 解码为 0。`model.py` 只处理最多 16 KiB 的合成 JSON，不是原始状态采集器，也不将成功比较转化为原生调用权限。

## 两个边界必须独立

入口 B0 位于 `80b4c0` 首条原指令之前，原 RSP 模 16 为 8；RCX 是目标，RDX 是来源，`[原RSP]` 必须仍是 `base+803d2c`。返回 B1 位于 `803d2c` 的 NOP 之前，RSP 应是该次 B0 的原 RSP+8，模 16 为 0，RAX 是原目标；thread/span/parent/generation 必须属于同一实例。数字相等不认证线程来源，父 span 不能伪造，C01 也没有完整 SP 来源链。

**记录器透明性**比较发生在同一个原始 PC：保存前与恢复后之间没有原指令。必须保留该点全部存活状态；不能只保存普通函数要求的 nonvolatile 寄存器。另一个边界才是执行被搬移原指令：入口 MOV 会写原 shadow 槽，PUSH/SUB 会改变 RSP，SUB 会改变算术 flags；返回处有 server+19f8/+1a00 的正常写零。它们不能提前、遗漏、重复，也不能被“恢复现场”撤销。当前模型不模拟这些指令，更没有运行重定位测试。

## 保存范围与真正缺口

Windows 常规 x64 ABI 将 RBX/RBP/RDI/RSI/RSP/R12–15 及 XMM6–15 的低 128 位列为 nonvolatile；其余普通参数、暂存与上层向量状态可能被函数调用修改。MXCSR 的状态位和控制位亦有不同 ABI 规则。这里的插入记录器不是原程序主动进行的普通调用，合同因此要求全部存活状态透明，包括 volatile 值。[Microsoft 调用约定](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170)

| 状态 | C02 要求 | 尚未支持的具体点 |
| --- | --- | --- |
| GPR / RIP | 原始 16 个 GPR 完整保留；RIP 由原位置到跳板再回到准确续执行位置 | 没有第一条保存到最后一条恢复的机器码；scratch、自引用 RSP、扩展 GPR/APX 尚未闭合 |
| RFLAGS | 在记录器执行第一条改 flags 指令之前捕获所需状态，并在恢复后保持等效 | 合成 uint64 比较不证明用户态可还原全部位；DF、TF/RF、调试状态与异常语义需要 ISA/Windows 精确合同。没有批准 PUSHFQ/POPFQ 方案 |
| XMM / YMM / 更多扩展 | 所有实际启用且存活的状态，不止 XMM6–15；不得无意 VZEROUPPER | 未查询真实 CPU/OS 支持与启用掩码；AVX512、AMX、PKRU、CET、APX 等均未获支持 |
| MXCSR / x87 | 完整控制、状态及实际数据，不能只满足 ABI control 位 | 不存在经验证的保存区域、合法掩码和恢复顺序；浮点待决异常也未测试 |
| TLS / 线程副作用 | recorder 不留下 LastError、errno 或 engine TLS 变化 | 没有逐指令 leaf 证明；C++ noexcept、原子 API 与“无分配”均不能证明无访问故障或无 TLS 改写 |

Windows 的扩展状态接口区分系统启用 feature、context feature mask、component 的位置与长度；一个固定 512 字节快照不能作为所有状态的默认覆盖。未来必须逐个支持明确的 CPU/OS profile，并处理初始化状态、未在用 component 与标准/紧凑布局，不能比较未初始化 padding。当前合成 profile 的 x87/SSE/AVX 字段是语义模型，**不是 XSAVE/CONTEXT 二进制布局**；未知 enabled component 直接拒绝。[Microsoft XState 说明](https://learn.microsoft.com/en-us/windows/win32/debug/working-with-xstate-context)

## 栈与返回身份

不能把原调用者的 shadow space 当记录器暂存区，也不能依赖 RSP 以下的 red zone。若未来要调用 C++ helper，记录器应另有受控的 32 字节 home area、正确对齐与有界 frame；当前不选 frame 大小或实现。保存区域不能覆盖原返回地址、原参数或 C01 已有保存槽；也须解决 guard page、stack-limit、探栈及最初尚未保存 scratch 的阶段。[Microsoft 栈使用规则](https://learn.microsoft.com/en-us/cpp/build/stack-usage?view=msvc-170)

原 CALL `803d27→80b4c0` 和实际返回地址都保持原样。禁止用另一个 wrapper 的返回冒充 `803d2c`，禁止改写 `[RSP]` 或绕过返回保护。近跳 5 字节和绝对跳 14 字节仅是 C01 分析候选；其完整指令区为 5/15 和 12/23 字节，不是批准覆盖长度。尚未证明全部入边及实际缓解策略组合，不能关闭缓解策略来获得通过。

## 异常是独立硬门槛

原 callee 与 parent 都有 UHANDLER/FH4。搬移位置不自动继承原 PC 的 unwind 数据，新 frame 的每个中间状态都必须可正确还原。普通 unwind metadata 主要还原非易失状态，不等于任意中断点的完整机器状态恢复证明。不能把代码塞进受限 epilog 后仍沿用原 epilog 识别。[Microsoft x64 异常处理](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170)、[prolog/epilog](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog?view=msvc-170)

C01 证据中的父函数 CALL/continuation 均属于 **state31**，清理链不含 state32 的新配置 `server+1708`；state32 funclet 是 `1ae6890→80b550`。在 continuation 新增可能抛异常的 helper，不能任意使用 state31、伪造 state32 或主动调用 engine 析构来补救。这是当前尚不允许实现/安装捕获器的直接原因之一。

| 发生位置 | 必须达到的政策 | 当前结论 |
| --- | --- | --- |
| entry save / restore 的中间指令 | 部分现场可展开，异常不能被错误地当作正常返回 | 没有逐指令栈/寄存器状态映射，unsupported |
| recorder 自身访问故障 | 不吞故障后继续游戏，不重试，不猜对象清理 | 无透明传播策略，unsupported；noexcept 只可能改变终止方式 |
| 搬移后的原指令故障 | 保持该原指令的内存顺序、异常归属与清理 | 没有 relocated-IP 到原语义的已审核方案，unsupported |
| 原 engine 异常越过 active span | 必须先使捕获失效，不发正常 return 事件，原异常继续正确展开 | 通知与 FH4 交接未实现；不能靠以后发现 missing return 替代立即撤销证明 |
| continuation recorder 故障 | 仍须正确处理刚完成的配置构造与父清理 | state31/32 差异未解，unsupported |
| stack overflow / unwind 中再次故障 | 不承诺仍能写诊断或完成原子撤销 | 无恢复承诺、无继续执行权限 |

在可执行路径允许时，检测到失效要先原子 terminal/revoke，再尝试写 ring；ring 满、发布洞、consumer 缺失、foreign thread、重入、missing return 均不得清除失效。旧 core 的跨 Ring Reservation 不属于合法调用合同，接入层应私有持有单个 core。异常穿越 active span 的策略不是靠该数据结构本身自动获得。

## 最小下一步及验收

1. 选择严格、可查询的 CPU/OS/缓解策略支持集；未支持的 enabled state 在安装前拒绝。逐条记录保存/恢复机器码与所有临时栈状态，第一条保存和最后一条恢复不能留未分析区间。
2. 设计异常/清理方案解决 state31/32 问题后，才制作隔离的非游戏 adapter。为新代码地址提供正确函数表并保持代码、表、捕获存储的共同生命周期；注册成功不是透明性证明。[动态函数表](https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable)
3. 对每条 adapter 边界在隔离对象上核 `RtlVirtualUnwind` 的 RSP/nonvolatile/handler/frame，并执行实际异常穿越、嵌套异常、重入与失败清理。虚拟展开本身不执行完整原生清理，不能独自证明 FH4 路径。[RtlVirtualUnwind](https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-rtlvirtualunwind)
4. 独立审阅 trampoline bytes、正常 bit-pattern 比较和上述 fault matrix 后，再讨论早启动安装；SP witness、生命周期同步和外交授权仍是其他合同，不从 C02 通过推导。

## 离线模型如何使用

`python -B prepare.py --check` 核 frozen pins 和重建合同；`python -B -m unittest discover -s <本目录> -p test_model.py -v` 运行严格类型、缺键/重复键、GPR/flags/向量/栈 canary、同实例 normal return 和异常政策反例。模型只对 64 字节栈样本和选定线程观测值做比较；它不能证明其余内存未写、全部 TLS 未变、线程真实或实际 XSTATE 全部覆盖。

`runtime_supported_profiles=[]`、所有运行证明/授权位为 false，即使全部离线测试通过也不变。`validation.json` 记录命令、退出码、完整 stdout、输入前后哈希与 shell 收齐；本候选不是 DLL、安装器或新运行时许可。
