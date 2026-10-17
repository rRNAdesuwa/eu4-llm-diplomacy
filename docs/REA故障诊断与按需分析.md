# REA 故障诊断与按需分析

记录日期：2026-10-14

后续已完成完整默认静态分析并建立持久化查询库：65,423 个函数，receive / wrapper clone 的缓存查询用时 30.80 / 26.41 秒。当前优先使用[完整分析与缓存查询](Ghidra完整分析与缓存查询.md)；下文保留超时根因和旧的临时有界路线。

适用环境：`rea-agents` 6.4.0、Ghidra 12.1.4、JDK 21、Node 24.13.0，目标为已核对 SHA-256 的 EU4 PE。REA 包源码坐标均相对于已安装包根目录。具体安装位置取自本机 `~/.codex/config.toml` 的 `mcp_servers.rea.args[0]`（`scripts/rea.mjs` 的上两级目录）。

## 结论

安装、Java、Ghidra 和桥接协议本身均可工作。故障发生在首个 EU4 查询之前：原版 REA 6.4.0 的 Ghidra Windows 启动参数导入整个 EXE 后仍保留 Ghidra 默认自动分析，REA bridge 作为 `-postScript` 在自动分析之后才启动。因此，首个查询等待的是整个 EU4 的导入和自动分析，而不是只等待声明的函数。

小型 control PE 已经通过原版 REA MCP 返回 `return 7`，证明安装和连接路径正常。EU4 的受控 direct Ghidra 实验也能完成进程级清理，但日志显示自动分析在每文件 60 秒处截止；这与历史上的 330/900 秒无成功 Evidence 一致，根因是分析阶段超时或被外层监督终止，而不是 MCP endpoint 配置失败。**原版 stock MCP 仍然默认走全量自动分析，本次项目适配器没有修改它。**

项目专用按需链路的 seeded-receive-v3 已完成验证：目标 SHA、REA 6.4.0、loader/helper/range 承诺、profile 回读、函数体范围、汇编和伪代码均通过，当前 `fn.receive.reconstruct` 可以按需查询。这个结论只适用于声明入口和选定 PE unwind range。

## 已完成的实验

| 实验 | 证据 | 结论 |
| --- | --- | --- |
| 原版 REA MCP + control PE | `work/runtime/rea-diagnostics-20261014/rea-control/evidence.json` 的 `raw_result.value`（约第 65 行）包含 `return 7`；Evidence ID 为 `ev_2271d4a8de3e7ffb2f153321d85978b6407bacea01fb7bfea4a8a0273483bd6d` | 原版 Node、Java、Ghidra、MCP bridge 能完成一个小目标 |
| 原版 Ghidra + EU4，`-analysisTimeoutPerFile 60` | `work/runtime/rea-diagnostics-20261014/direct-eu4-budget60/console.log:278-291`、`application.log:289` | `Disassemble Entry Points` 用时 `58.933 s`，随后报告 60 秒分析截止；`run.json` 记录总用时 `97.75 s`、Java 峰值 committed `803328000` 字节，说明全 EXE 自动分析是主要阻塞阶段 |
| 项目适配器 v2（中间样本） | `work/runtime/rea-diagnostics-20261014/seeded-receive-v2/run.json` | 进程以 `exit_code: 0` 返回，但函数 body 只有 1 字节、`assembly` 为空；仅保留为 bridge 启动诊断，不能作为最终函数覆盖结果 |
| 项目适配器 v3 + `fn.receive.reconstruct` | `work/runtime/rea-diagnostics-20261014/seeded-receive-v3/run.json`、`evidence.json` | `exit_code: 0`，耗时 `38.14 s`，Evidence ID 为 `ev_6062bf4522b8b95a026fe3359d8b9d87ea83a1bacab95e31cc4b7f221770f61b`，profile digest 为 `7699edde0cc12768880468dcbac12aa6701092773ba5224c1aec6cf720bb371f`，Java 峰值 `772653056` 字节（约 `736.9 MiB`），PID 60772 已结束；目标函数 body 为 430 字节、112 条汇编、19 个基本块、15 条 outgoing references，其中 3 个为已解析 direct callees |

v3 的一次请求声明了 `fn.receive.reconstruct` 和 `fn.wrapper.clone` 两个入口，实际查询的是 `fn.receive.reconstruct`。其 RVA 范围为 `[0x15800c0, 0x158026e)`，对应 VA 范围为 `[0x1415800c0, 0x14158026e)`；范围来自目标 PE 的精确 `.pdata`/`RUNTIME_FUNCTION` 记录。`request.json` 记录的原始 `seeds.tsv` SHA-256 为 `10cd5251291706bed8ae252b60f262f0fa1ba2426d818c345b59a570c50ec816`，REA 规范化并写入 profile 的 seed SHA-256 为 `609be0d49bf9832f8f6da98ca1a9ea4958379df886f4b2534ca0de62ed6f2b87`；两者分别记录，差异来自规范化格式，不是目标或 seed 内容未核对。

因此，按需入口已经能够对声明入口产出可审计的 v3 Evidence；它验证了启动、桥接、哈希回读和有界函数体恢复。这个结果仍只覆盖选定 PE unwind range，不能等同于完整系统化逆向或全局调用图。

## 原版启动顺序和根因

已安装包的 `dist/ghidra/GhidraLauncher.js`：

1. `:230-234` 构造 `-import <target>`；`:264-269` 加入只读项目、`ghidra.log` 和 `script.log`。
2. `:278-285` 若配置了 seed，只把 `ReaGhidraApplySeeds.java` 作为 `-preScript` 放在导入之后。
3. 该参数列表没有 `-noanalysis`；Ghidra 因而执行默认的全程序自动分析。
4. `:292-297` 才加入 `-postScript ReaGhidraBridge.java <session.json>`。

`bridge/ghidra/ReaGhidraBridge.java:203-211` 在脚本中结束导入事务、初始化 decompiler，然后进入 `serve`。Windows 的 `:247-276` 绑定 `127.0.0.1` 随机端口、写出 endpoint 文件并接受客户端；`:278-281` 在结束时删除 endpoint。也就是说，endpoint 的发布位于 bridge 脚本阶段，而 bridge 脚本本身位于默认自动分析之后。默认能力文本 `dist/ghidra/GhidraProviderCapabilities.js:16-20` 也明确写着：只有 Ghidra 报告默认自动分析完成后才提供操作，不暴露 incomplete analysis 的 partial result。

REA 6.4.0 的默认启动截止时间来自 `dist/config/ghidraStartupTimeout.js:2-12`，默认值是 `330000 ms`；可选环境变量是 `REA_GHIDRA_STARTUP_TIMEOUT_MS`。包内没有 `REA_GHIDRA_DISABLED_ANALYZERS` 的实现，也没有在 launcher 中提供 `-noanalysis` 或 `-max-cpu`。Ghidra 官方 headless CLI 支持这些参数，但 stock REA 没有转发它们。

seed 的实际变量名是 `REA_GHIDRA_SEED_FILE`，见 `dist/config/environment.js:34-40`。文件格式和边界见 `dist/ghidra/GhidraAnalysisSeeds.js:9-14,47-102`：`rea-ghidra-seeds-v1`，最多 32 MiB、1,000,000 条记录，记录种类为 `function`、`code` 或 `label`。seed 是调用方声明，不会把它自动变成“只分析这些函数”；在默认 launcher 中它仍发生在整个自动分析之前。

Ghidra Java 启动参数的 `-Xmx` 由 `dist/ghidra/GhidraJavaLaunch.js:47-63` 从 `GHIDRA_HEADLESS_MAXMEM` 或 `GHIDRA_MAXMEM` 读取，缺省为 `2G`；同处固定 GC/JIT 线程数为 2。direct EU4 的 `803328000` 字节峰值表明 JVM heap 数字和进程 committed/private memory 不能混为一谈。

## 项目专用按需入口

项目没有改写已安装包，也没有改 Codex 配置。`reverse_engineering/rea.py` 启动一个独立 Node 进程，并通过 `--import reverse_engineering/rea_seeded_loader.mjs` 在进程内变换三个已核对的 REA 模块，同时为选定入口生成有界 PE unwind range。

- `reverse_engineering/rea.py` 的 `main()` 定义命令行；位置参数必须是索引中 `address_role=procedure_entry` 的节点，`--seed` 可重复，`--timeout` 允许 30–900 秒。
- `main()` 去重并限制一次最多 32 个声明入口，通过 `unwind_ranges()` 读取目标 PE 的精确范围，为每次运行创建新的 `work/runtime/rea-seeded-*` 目录、`seeds.tsv` 和 `ranges.tsv`。
- `main()` 设置 `EU4_REA_PACKAGE_ROOT`、`REA_GHIDRA_SEED_FILE`、`EU4_REA_DECODE_SCRIPT`、`EU4_REA_RANGES`、启动截止时间和 `GHIDRA_HEADLESS_MAXMEM=512M`，把目标 SHA、原始 seed SHA、适配器 SHA、helper SHA、范围 SHA、REA 版本和覆盖限制写入 `request.json`。
- `MEMORY_LIMIT` 设定 1 GiB Java 进程内存监督；`_owned_children()` 和 `_stop_process()` 配合监视归属 Java 进程，超过内存或监督截止时间会终止它。1 GiB 是进程级上限，不是 `-Xmx512M` 的替代品。
- 运行目录保留 `request.json`、`run.json`、`evidence.json`、`stderr.log`、`ghidra-tail.log`、`script-tail.log`、`seeds.tsv` 和 `ranges.tsv`，便于在临时 Ghidra 目录清理后复核。

`reverse_engineering/pe_ranges.py` 的 `unwind_ranges()`（`:6-70`）只按文件偏移读取 PE 头、节表和 exception directory，校验 x64、唯一文件映射、可执行节、精确入口和不超过 `0x8000` 字节的范围，不把整个 EXE 读入内存。它读取的是 shipped `.pdata`/`RUNTIME_FUNCTION` 观察值，不宣称完整语义函数块或可外部调用 ABI。

`reverse_engineering/Eu4ReaDecodeFunctions.java` 的 `Eu4ReaDecodeFunctions.run()`（`:16-46`）逐条校验范围文件 SHA 和内存边界，调用 `DisassembleCommand`，在 `:40` 使用 `enableCodeAnalysis(false)`，再在 `:43` 对临时 Ghidra 数据库调用 `Function.setBody(range)`。这一步只把已承诺的范围反汇编并设置为本次 ephemeral session 的函数体，不写回原始 PE，也不触发全局增量自动分析。API 参考：[DisassembleCommand](https://ghidra.re/ghidra_docs/api/ghidra/app/cmd/disassemble/DisassembleCommand.html)、[Function](https://ghidra.re/ghidra_docs/api/ghidra/program/model/listing/Function.html)。

`reverse_engineering/rea_seeded_loader.mjs` 的关键约束如下：

- `:13-30` 要求 Node 的同步 `registerHooks` API、非空 `EU4_REA_PACKAGE_ROOT`、`REA_GHIDRA_SEED_FILE`、`EU4_REA_DECODE_SCRIPT` 和 `EU4_REA_RANGES`，并且只接受 `rea-agents` 6.4.0；同时计算 helper 和范围文件 SHA。
- `:47-55` 对源码 anchor 做单次精确匹配；缺失或重复就 fail closed，不会静默适配未知版本。
- `:73-86` 在 launcher 参数中插入 `-noanalysis -max-cpu 2`，在桥接 `-postScript` 之前加入 `Eu4ReaDecodeFunctions.java`，同时保留原有 import、脚本、原生 ownership 和 Windows DACL 逻辑。
- `:90-108` 将 preset 写为 `eu4-declared-seeds-pdata-noanalysis-v2`，记录适配器 SHA、helper SHA、范围 SHA、`function_body_scope` 和 `xref_scope: declared-seeds-only-global-incomplete`。
- `:104-108` 明确声明当前结果只针对选定 PE unwind range；全局 xref、string、type、CFG 覆盖不完整，空引用不能证明没有 caller。

使用入口示例：

```powershell
python -m reverse_engineering.rea fn.receive.reconstruct
python -m reverse_engineering.rea fn.receive.reconstruct --seed fn.wrapper.clone
```

默认目标来自项目 `local.env` 的 `EU4_GAME_ROOT/eu4.exe`；需要其他文件时可用 `--binary`，需要固定输出位置时可用 `--output`。每次运行都会重新核对目标 SHA；目标不匹配、索引节点不是已确认函数入口、REA 不是 6.4.0 或缺少 Node 24 的 `registerHooks` 时会停止。

## 结果边界和验证状态

当前入口适合按需定位、验证声明入口、取得受限伪代码和保存可审计的运行证据。v3 已通过本次模块和 PE 边界合同检查，可用于当前声明入口的按需查询；它仍不等价于一次完整系统化逆向：

- `-noanalysis` 避免了全 EXE 自动分析，但也意味着未声明的函数、全局 caller 图、字符串、类型传播和 CFG 可能不存在。
- seed 的函数、地址和名字是调用方断言；`.pdata` 范围是 PE unwind metadata 观察值，不能单独证明完整语义函数块或 externally callable ABI。必须结合目标 SHA、原始 seed SHA、REA 规范化 seed SHA、范围 SHA 和 profile 回读判断是否分析了预期对象。
- v3 已用桥接之前的有界 postScript 修复 v2 的单字节 body 问题：helper 只对选定范围 disassemble，禁用增量 code analysis，再设置临时数据库函数体。v2 目录仍保留为中间桥接样本，不能作为最终覆盖结果。
- v3 验收条件已满足：`exit_code=0`；profile preset、REA 版本、目标 SHA、loader/helper/range SHA 回读一致；seed report 与规范化 seed SHA 一致；目标函数 body 为非平凡且有界的 430 字节；assembly 和 pseudocode 均非空；进程没有超过 1 GiB 或监督截止时间。
- 已通过 9 项模块/PE 边界合同测试，覆盖索引引用、fixture 与运行证据区分、EXE 哈希错配、PE 映像边界以及精确 unwind 入口、歧义和范围越界。适配器、临时数据库和结果回读另由本次真实 REA 查询验证；这些检查不代表全局逆向完成。

`ghidra-tail.log` / `script-tail.log` 是每秒采样的最多 64 KiB 尾部，可能缺少退出前最后一条日志。完整函数返回保存在 `evidence.json`。原始运行目录被 Git 忽略，文档和索引不包含所有本机 Evidence。

stock MCP 的全量自动分析行为仍未改变；需要全局 xref、字符串、类型或完整 CFG 时，必须另行规划系统化分析和更长的资源预算。当前 v3 只证明声明入口的有界按需分析链路可用。

