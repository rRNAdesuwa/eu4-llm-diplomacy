# API lookup v4 作者交付

58 条合同、59 个固定 JSON 来源。原 v3 的 54 条记录逐条 data-equal；原 44 个来源 pin 不变。新增 R63 97b2c0、R64 97b8a0、R66 994f00 和 R67 1a337f0。R68 仅作为 994f00 的后来条件上下文，原 R66 历史未知原文保持。

七个首次 v4 文件查询通过：check、catalog、四个新增 RVA lookup 与组合 search。每个 Job exit0、active0，direct child 已收；每流不超过 2 MiB。query 只是文件验证，不代表任何端点可调用或游戏效果。旧 CLI main、旧测试、PE/engine/decoder/game/native/request 全部零新增。

首次构建的 runner 换行匹配断言失败，发生在任何查询前。build_index.py、claim、failure、stdout/stderr 都原样保留；repair_runner.py 仅生成新 runner 并完成来源封存，既有 index/data/CLI 字节不改。没有重跑 builder 或任何旧已通过方法；七个查询均为首次且没有失败。另一个最初 PowerShell 路径语法错误在执行前即停止，原 tool 回执在 build-failure 的读账之外，以 1 MiB 手工检查 allowance 覆盖。

新 wrapper 与 v3 的差异仅 DATA_SHA、tool_revision 和帮助版本文案；逻辑 AST 可精确还原相等。固定 v1 引擎的路径、文件大小、source 数、前后 pin、地址算术与权限守卫保持。新增数据非运行时 API，无外部 root/manifest 或进程执行选项。

R63 不认 DWORD+30 币种/单位或最终值保持；R64 不认 F0 枚举、虚调用返回类或唯一集合；R66/R68 不认排序/守恒/free，保留正常返回、GS alias、fresh H/T、六参低 BYTE 等界限；R67 不按 CRT 名字推行为，寄存器保持不是 pointee 保持或调用安全。所有效果、运行时、租约及重试权限 false。

状态：SOURCE-READY，等待 root 非作者完整文件审查。旧稳定观察器、v1/v2/v3、48/44/42 与 15 profiles 未改；R69/R70 未加入。账目明确区分分析/封存 24 MiB 与首次查询批次 64 MiB，不声称全 OS I/O。
