# R87 完整保留文件独立审查

通过，未发现阻断差异。审查者 D 不是本轮 producer 或实际合同作者；作者为 War，采集执行者为 root。D 的早先 source-peer 仅作为固定上游见证，未递归用来证明本轮 raw 结论。

独立核对全部 256B owned 原像与 61 行/210B 指令范围，重算 6 个 CALL、5 个短分支和 9 个 pdata 三元组。正常 seed 与假设 seed 分别可达 59/2 行；cc32c 虽由当前 record1257 覆盖，R86 的 SAR3 值域仍排除了正常输入沿 JE 到达它。5 个 LEA 为地址计算，不按 Capstone memory-operands 的 read=true 当内存读取。真实显式读取 8 条、显式写入 5 条；CALL/POP/RET 的隐式栈操作另计。

三零 header、D=0、有效读写空间及未知外调正常保留 ABI 的附加条件下，首 payload 写为 M64[S]←fresh M64[E]。950b0 未证明是 allocator，1a35750 的 R8=0 未证明无副作用；c9d60(C,S,1,1) 的 header、清理和所有权仍未知。cc30f 在恢复 R14 前将先前 slot 地址赋给 RAX，返回及 72B 栈读取模型都依赖有效栈、保存值未被别名/调用破坏。不是全函数或安全调用证明。

作者 233+86 次源读合 18,830,537B；PE 两次 SHA 加 108B metadata、256B code 的见证账为 76,925,372B，独立列账。Job 2 个进程、active0、exit0、峰值 25,493,504B、direct child collected。以上是冻结源与生产回执支持的见证，本审未重读 PE/engine，也不声称全 OS I/O。

作者第一次 sealer 的 KeyError、原源与诊断保留；1,310,720B 失败读取按上界而非实测计，源封存上界 5,784,217B，retained 1,215,906B，无 actual 重跑。本审仅文件/AST/原始整数算术，不执行作者程序、测试、CLI、decoder、游戏或 native。所有 callable/native/effect/lease/ownership/retry 权限均为 false；不授权后续 callee。
