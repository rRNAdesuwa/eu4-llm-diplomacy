# v19 固定发送 context 字节与私有快照合同

本候选只从已封报告复用小段指令，再逐字节 seek 核对 exact 1.37.5 EXE。没有新解码、内存读取器、resolver、native call、hook、DLL、请求发布或实际授权。`sender-pins.h` 只有常量；`contract.py` 仅验证合成输入，不证明这些值来自游戏。

选定调用是 Windows x64 `bool(context*, command**)`，入口 **14ca210**。RCX 是 context，RDX 是本方 `command` 容器地址；必须已有非空、独占、类型已核且 clone 由它拥有的 command。14ca22a 先读 QWORD 容器，14ca22d 立即写 QWORD 零，14ca234 才检查 transport。显式 ready 路径读取 **BYTE +55 或 BYTE +80d**，非零即为真。此受限合同不使用 command 虚槽 +80/+58 的另外放行路径；两字节为 0 不可绕过。

14ca274 将 context DWORD+8c 写入 command DWORD+38；14ca27d 读 context DWORD+68，经原生 signed compare/WORD 选择写 command WORD+48。Host 不伪造这两个 command 字段或复刻该选择。14ca299 调 transport+30，正常返回后 14ca29c 设 BL=1，14ca2b1 `movzx eax,bl`。空 command 虽有内部跳转，不是有效调用输入。其余 false 或异常路径已经可能消费原容器，不能恢复本方归属。

**14ca2d0 不可替代**：RDX 直接是 command 对象，未使用 `command**` 容器，前置检查与 false 路径也不同。本候选把它列为禁止选择的不同 ABI 证据；没有导出可供用户指定的 RVA，也不会调用 world sender、transport、consumer 或 drain。

只读字段链与精确宽度如下。每次读取前需要由未来私有 Host 先验证非空、用户地址范围、字段界限、完整 held 模块和 SEH/错误处理；本目录不实现读取。

| 来源 | 字段/宽度 | 作用 |
|---|---|---|
| image+233fe78 | QWORD | game 根；来源是 world wrapper 的 RIP 引用 |
| game+1e00 | QWORD | server |
| server+0 | QWORD | 必须等于 base+1cb8460 |
| server vtable+80 | QWORD | 必须等于 base+811aa0 |
| server+330 | QWORD | holder |
| holder+370 | QWORD | context；getter 的两次解引用可改为只读读取，不能调用 getter |
| context+58 | QWORD | transport |
| transport+0 | QWORD | 必须等于 base+1d96178 |
| transport vtable+30 | QWORD | base+1580370 |
| transport vtable+48 | QWORD | base+8b0e0，返回 transport+c8 队列地址 |
| context+55 / +80d | 各 BYTE | 原始 0..255 值；必须按 BYTE 读取，不接受 bool 冒充 |

没有推定 context 自身的 vtable，也没有由 transport 类型推定严格单机。暂停、两遍同值、指针相等不排除同址对象替换、ABA、加载/销毁或跨线程修改。world epoch、SP 来源、owner thread 与同步仍由未闭合的独立研究处理。

建议未来 Host 私有 context stamp 与既有 owner/world stamp 合并，记录：完整 PID+creation、session、EXE/DLL/manifest、模块基址、game/database/countries、完整 FRA/ENG/player handles 与对应已解析 country 指针、日期、owner/current thread、真实 frame call 序号与 uptime，再加上表 server/holder/context/transport、两个 vtable、三个 slot target 和两字节原值。这些不是公共请求参数；客户端不能提供 raw 指针、ready=true 或 preflight=true 获得权限。

固定调用顺序建议：该项永久 claim 和所有前置阶段由独立 Host 认证；本项 fresh action full+88、wrapper 与 command gate 正常完成；原件独立正常析构；持久 dispatch intent **成功后**，同 owner callback 内重新读取完整根链、slot 与原始字节、完整身份/日期/线程/预算/TTL；紧邻原生入口再次确认 Host guard。指针改变、类型不符、不可读、guard/日志失败均停止。若尚未进入 submit，只有已证明的本方独占对象才可按单独已审清理合同处理；若进入，立即先撤销本方 command/clone 权属，任何 false/SEH/非空 slot 或缺返回都冻结，无读旧对象、free、补发或重试。此描述与合成检查结果本身都不授予实际调用能力。

receiver 证据只说明已知正常静态路径：transport+48→c8 队列，context consumer 再 gate，栈 callback 通过 instrumentation/invoker 最终尾跳 command+48。rbp=rsp+100，`rbp-78` 是容器 `rsp50+38`。正常 transport 分支 `1580c4a..5a` 删除原 command，消费末端 `14cb13b` 删除所消费的 command；二者可为序列化重建前后不同对象，不能靠地址归一。小 pins 不覆盖完整函数/异常展开，不证明消费线程、调度、队列已清或效果生效。宿主不得调用这些 consumer 函数催促结算。

`sender-pins.h` 使用 namespace `eu4_spy19_sender`，提供 `CodePin{uintptr_t rva,const char* hex}`、`SlotPin{uintptr_t rva,target}` 和 `kCodePins/kSlotPins`。字节串从完整指令边界拼接，最长 180 B，可由实现拆成小块读取比较，但不能截断 pin。它不是 trampoline 补丁长度，不含 unwind/寄存器恢复保证。类型2 transport、callback、command 槽均按实际 PE QWORD验证；ASLR时目标是模块base+RVA。

复现仅离线：

```powershell
python -B work/candidates/v19-spy-send-context-pins-1375/trace.py --check
python -B work/candidates/v19-spy-send-context-pins-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v19-spy-send-context-pins-1375 -p test_contract.py -v
```

静态范围小于每函数 8 KiB；本轮新增解码 0。所有未来实际发送、运行验证、效果、生产状态仍为 false。
