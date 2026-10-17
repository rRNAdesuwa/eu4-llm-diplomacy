# Ghidra 完整分析与缓存查询

记录日期：2026-10-14

适用环境：`rea-agents` 6.4.0、Ghidra 12.1.4、JDK 21、Node 24.13.0。目标是已经与项目索引核对过 SHA-256 的 EU4 PE。本文描述项目专用的持久化 Ghidra 工程和查询入口；它不改变已安装的 REA/Ghidra 包，也不修改 Codex 配置。

## 这里的“完整分析”是什么意思

这里的完整分析是指：把目标 EXE 导入一个持久化的 Ghidra 工程，并让 Ghidra 默认的静态 auto-analysis 正常结束，把整个 EU4 Program 和分析数据库保存下来，供后续查询复用。

它不表示已经批量反编译了全部函数，也不表示已经读懂全部游戏逻辑。函数伪代码和函数级 dossier 仍然在提出查询时生成；完整工程提供的是整个 Program 的已保存分析状态、符号、函数、指令、数据和可供查询的引用关系。默认分析仍可能无法确定间接调用、所有语义类型、完整 ABI 或运行时行为。没有运行游戏，也没有把静态结果当成运行时事实。

这条链路与[REA 故障诊断与按需分析](REA故障诊断与按需分析.md)中的 seeded 路线不同：seeded 路线使用 `-noanalysis`、临时数据库和声明入口的 `.pdata` 有界范围，适合快速验证单个函数，但全局 caller、字符串、类型和 CFG 覆盖不完整。本文的缓存路线先完成一次默认静态分析，之后按函数按需查询。

## 缓存的组成和生命周期

每个缓存目录包含一个独立的导入副本、Ghidra 工程、阶段报告和日志。目录结构的关键部分如下：

```text
work/runtime/ghidra-full/<cache>/
  input/eu4.exe                 # 与目标绑定的导入副本
  project/EU4Full.gpr           # Ghidra 工程标记
  project/EU4Full.rep/          # 持久化 Program/数据库
  build.json                    # 目标、版本、阶段和完成状态
  import-status.json            # 导入阶段摘要
  analysis-status.json          # 默认分析阶段摘要
  analysis*.log                 # Ghidra 日志、脚本日志和控制台日志
  cache.lock                    # 当前构建、恢复或查询的独占锁
```

缓存只接受 `program=eu4.exe`、`project_name=EU4Full`。`ghidra_cache.py:37-50,191-213` 会流式计算导入副本 SHA-256，并用项目索引再次核对目标；缓存副本被替换、哈希不符或元数据指向其他文件时，操作会停止。

构建分为两个阶段（`reverse_engineering/ghidra_cache.py:451-617,958-1035`）：

1. `-import <cache>/input/eu4.exe -noanalysis`：只导入目标，保存一个可恢复的 Ghidra 工程。
2. `-process eu4.exe -analysisTimeoutPerFile <秒>`：在同一个 `EU4Full` 工程中执行 Ghidra 默认 auto-analysis，并通过 `Eu4FullAnalysisStatus.java` 写出报告。

默认资源边界是 Java heap `512M`、`-max-cpu 2`，以及针对实际 Java 进程 private/committed/VMS 数值的 `1 GiB` 监督上限。`512M` 是 JVM heap 设置，不是整个进程的内存上限。默认分析预算为 `7200` 秒；Ghidra 的参数是每文件分析截止时间，外层监督还会给阶段增加有限收尾时间。导入阶段有独立的 `900` 秒监督截止。

构建器只终止自己拥有且命令行确认是 Ghidra headless 的 Java 子进程（`ghidra_cache.py:333-431,500-575`）。它保留阶段日志、退出码、清理状态和峰值内存；不会扫描或读取大型反汇编文本。

`Eu4FullAnalysisStatus.java:12-31` 会核对当前 Program 的 executable SHA，并报告 `stage`、`analysis_timed_out`、`default_auto_analysis_completed`、函数数、指令数、定义数据数和符号数。导入阶段的函数入口统计不能当成完整分析完成证明；只有 analysis 阶段的完成标记有效。

## 何时可以发布和复用

缓存只有同时满足以下条件才会被视为完整：

- 最新 analysis 尝试退出码为 `0`，原因是 `completed`。
- 报告的 `stage` 是 `analysis`，`analysis_timed_out` 为 `false`，`default_auto_analysis_completed` 为 `true`。
- 报告中的 `target_sha256`、`program` 与 `build.json` 和导入副本一致。
- `EU4Full.gpr`、`EU4Full.rep`、`project.prp`、阶段报告和日志均存在；日志包含针对 `/eu4.exe` 的 Ghidra `Save succeeded` 记录。
- `EU4Full.lock` 和 `EU4Full.lock~` 均不存在，最近一次受控 Java 进程已经退出。

这些条件由 `ghidra_cache.py:784-908,911-955` 重新读取文件、日志尾部和进程记录来判断。任何不完整状态都不会写入可复用的发布指针；异常退出留下的锁文件也不会被自动删除。确认拥有者进程已经退出后，应先处理该 checkpoint，再使用 `resume` 或显式修复，而不是把锁当成完成标志。

成功完成后，构建器原子写入项目相对路径 `work/runtime/ghidra-full/latest.json`。指针绑定缓存目录、目标 SHA 和 `build.json` 的 SHA-256。`status` 会重新计算完成条件；`publish --cache` 会再次验证同样的条件后发布或更新指针。`latest.json` 只表示一个已经完成并经过验证的缓存，不表示所有函数都已经反编译。

`resume --cache <目录>` 只接受已有导入工程的 checkpoint，并要求没有 Ghidra 项目锁（`ghidra_cache.py:1049-1110`）。恢复会从 `-process eu4.exe` 继续默认分析，使用新的带编号日志和阶段记录；完成后同样必须经过完整证据检查才能发布。

## 构建、检查和发布入口

以下命令均在项目根目录运行。`build` 和 `resume` 会启动 Ghidra；`status` 和 `publish` 只读取/验证缓存元数据、工程文件和有限日志尾部，不启动 Ghidra。

```powershell
# 创建新的缓存；--output 必须是不存在的目录
python -m reverse_engineering.ghidra_cache build `
  --output work/runtime/ghidra-full/eu4-full-new `
  --analysis-timeout 7200

# 将变量设为要检查的已有缓存目录
$cacheDir = 'work/runtime/ghidra-full/b23fa0e1f698d31b-20261014T054913Z-6dda97'

# 只读查看缓存状态、锁和完成证据
python -m reverse_engineering.ghidra_cache status `
  --cache $cacheDir

# 从已导入但未完成的 checkpoint 恢复默认分析
python -m reverse_engineering.ghidra_cache resume `
  --cache $cacheDir

# 在确认完整后发布 latest.json
python -m reverse_engineering.ghidra_cache publish `
  --cache $cacheDir
```

`--output`、`--cache` 和项目文件均按目标 SHA、工程名和缓存锁绑定；不会覆盖已有目录。想继续分析前，先用 `status` 检查 `status`、`project_save_evidence`、锁文件和最近阶段的 `exit_code`，不要只看工程目录是否存在。

## 按需查询入口

持久化工程完成并发布后，可以继续使用项目自己的 REA 公共 CLI 入口：

```powershell
# 默认使用 work/runtime/ghidra-full/latest.json 指向的完整缓存
python -m reverse_engineering.rea fn.receive.reconstruct

# 明确指定一个已完成缓存
python -m reverse_engineering.rea fn.receive.reconstruct `
  --cache $cacheDir

# 指定另一个输出目录或首个查询的监督时限
python -m reverse_engineering.rea fn.receive.reconstruct `
  --cache $cacheDir `
  --output work/runtime/rea-cache-query-receive `
  --timeout 180
```

`reverse_engineering/rea.py:68-94` 的选择规则是：有 `--cache` 时必须验证指定缓存；没有 `--cache` 且存在已验证的 `latest.json` 时使用最新缓存；如果没有已发布缓存，普通命令会回退到原有的 seeded 按需路线。要明确使用旧路线，可加 `--seeded`；要声明其他已确认入口，可用 `--seed`。缓存查询不能和 `--seed` 或 `--seeded` 同时使用。

```powershell
# 明确强制使用旧的临时、有界入口
python -m reverse_engineering.rea fn.receive.reconstruct --seeded
python -m reverse_engineering.rea fn.receive.reconstruct `
  --seeded --seed fn.wrapper.clone
```

缓存查询的 `--timeout` 默认 `180` 秒，允许 `30–900` 秒。它控制此次查询的启动/监督边界，不会重新运行完整默认分析。每次查询都会创建新的 `work/runtime/rea-cache-*` 结果目录，保存 `request.json`、REA `evidence.json`、`stderr.log` 和 `run.json`；持久化 Ghidra 工程本身仍由缓存目录持有。

## 查询坐标和名称

查询位置可以是三种形式：

- 索引中已登记的函数入口 ID，例如 `fn.receive.reconstruct`。`cache_query.py:71-76` 会将其 RVA 加上索引 image base，作为静态 VA 查询。
- 以 `0x` 开头的 RVA 或静态 VA。小于 image base 的数值按 RVA 处理，否则按静态 VA 处理（`cache_query.py:76-79`）。
- 其他字符串作为精确的 Ghidra procedure/symbol name 传递（`cache_query.py:80-81`）。名称查询依赖 Ghidra 已保存的准确名称，不是模糊搜索。

RVA 是映像内坐标，静态 VA 是 `image_base + RVA`；运行时 VA 需要重新取得模块基址，不能把静态 VA 当作游戏进程地址。`--binary` 可以指定另一个本地 EXE，但入口会重新核对它的 SHA，不能用另一构建的 EXE 复用当前数据库。

## 持久化工程适配器做了什么

`reverse_engineering/rea_cache_loader.mjs` 是一个只在本次 Node 进程内生效的 `node:module registerHooks` 适配器。它没有改写安装目录中的源码，也没有修改 `package.json`、REA 配置或 Ghidra 安装。

它在进程开始时拒绝以下情况：REA 版本不是 6.4.0；`build.json` 不是 `complete`；默认 auto-analysis 没有明确完成；目标不是 `EU4Full/eu4.exe`；工程缺少 `EU4Full.gpr`；环境还带有 seed；或没有由查询入口计算出的数据库 commitment（`rea_cache_loader.mjs:8-27`）。所有源码替换都要求 anchor 唯一匹配，版本变化时会 fail closed（`:29-34,67-74`）。

它只变换三个已核对的 Ghidra 模块：

1. `GhidraLauncher.js` 的最终参数从临时 `rea-project -import <target>` 改为外部持久化工程 `EU4Full -process eu4.exe -noanalysis -max-cpu 2`，并删除 `-deleteProject`。基础 launcher 原有的 `-readOnly`、bridge、descriptor、日志、Windows DACL、Job Object/ownership 和私有临时目录逻辑保留（`rea_cache_loader.mjs:35-42`）。
2. `GhidraAnalysisProfile.js` 写入 `eu4-persistent-default-analysis-v1`，并承诺 loader SHA、完成 manifest SHA、数据库 SHA、`query_reanalysis=false` 和 `database_mutation=read-only-no-save`（`:43-53`）。
3. `GhidraProviderCapabilities.js` 在本进程内说明读取的是已经完成的默认分析数据库，查询不会再次自动分析，关闭时只清理 REA 私有 endpoint、日志和临时输入；同时明确间接调用、语义类型和运行时行为仍可能未知（`:55-65`）。

这里“只变换最终参数”很重要。REA 的 private runtime 仍用于 descriptor、endpoint、日志、HOME/TEMP 和目标副本，外部 `projectRoot` 只作为 Ghidra CLI 的项目位置传入。这样既能保留 REA 的进程 ownership 和清理边界，也不会把持久工程放入会在关闭时递归删除的 REA 临时 runtime。stock MCP 不加载这个适配器，仍然是原版的临时 `-import` 和默认分析行为。

## 查询前后的完整性检查

`reverse_engineering/cache_query.py:20-33,59-178` 在每次缓存查询中执行以下检查：

1. 获取缓存独占 `cache.lock`，重新核对导入副本 SHA、`complete` 状态、Ghidra 12.1.4、工程身份和 `latest` manifest。
2. 对 `project` 目录中的文件按相对路径排序，流式计算数据库树 commitment；跳过 Ghidra 的 `.lock` 和 `.lock~` 文件，限制文件数量为 8192。
3. 通过进程内 loader 使用 `-process eu4.exe -readOnly -noanalysis`，把查询绑定到完成工程，不重新跑默认分析。
4. 回读 Evidence 的 `analysis_profile`，确认 preset、loader SHA、完成 manifest SHA、完成数据库 SHA、目标 EXE SHA 和 provider version 一致；还要求 assembly、pseudocode 和函数 body entry 存在。
5. 查询退出后再次计算数据库 commitment。若持久化工程树发生变化，结果失败并记录 `read_only_database_changed`；若 Java 清理不完整，也会失败。

因此，成功的缓存查询不是“相信已有 `.gpr` 文件”，而是目标、完成报告、工程树、profile 和本次 Evidence 的多重绑定。查询仍可能返回 Ghidra 自身的未知项；数据库完整性通过不变性检查，并不把未知项隐藏成确定结论。

## 资源、并发和结果边界

- 同一个缓存一次只允许一个 build、resume、publish 或 query。`cache.lock` 写入 PID、创建时间、命令和主机；冲突时会显示拥有者，工具不会自动删除锁。
- 查询使用 `-readOnly` 和 `-noanalysis`，不会把注释或分析变更保存回完整工程。需要修改工程时应使用隔离副本，并另行记录版本和哈希。
- 完整静态分析仍不是动态分析；未解析间接调用、缺失类型传播、编译器 ABI 细节、运行时加载模块和游戏状态都应保留为未知。
- 查询某个函数会请求该函数的 assembly/pseudocode/dossier，但没有批量反编译全 EXE 的步骤。不要为了“补全”而读取或保存几百 MB 的整包反汇编。
- 所有目标身份使用 SHA-256 绑定。RVA、静态 VA、`.pdata` 范围和反编译地址均属于特定 EXE 构建。
- 进程超过 `1 GiB` committed/private 监督上限时，必须检查精确命令并停止归属的 Ghidra 进程；不要停止无关的 Java 或游戏进程。

## 本次验证结果

2026-10-14 已完成并保存默认全程序静态分析，发布了 `latest.json`。工程位于 `work/runtime/ghidra-full/b23fa0e1f698d31b-20261014T054913Z-6dda97/`；[构建记录](../work/runtime/ghidra-full/b23fa0e1f698d31b-20261014T054913Z-6dda97/build.json)、[分析报告](../work/runtime/ghidra-full/b23fa0e1f698d31b-20261014T054913Z-6dda97/analysis-status.json)和 [Ghidra 日志](../work/runtime/ghidra-full/b23fa0e1f698d31b-20261014T054913Z-6dda97/analysis-console.log)保留本机。

| 字段 | 结果 |
| --- | --- |
| `build.json.status` | `complete` |
| analysis `exit_code/reason` | `0 / completed` |
| 导入 / 完整分析耗时 | `86.02 / 3426.28` 秒；完整分析约 57.1 分钟 |
| `analysis_timed_out` / `default_auto_analysis_completed` | `false / true` |
| 函数 / 指令 | `65,423 / 6,662,700` |
| 定义数据项 / 符号 | `438,584 / 484,673` |
| Java 峰值 private/committed | `854,487,040` 字节，约 `814.9 MiB`；进程已结束 |
| 目标 SHA-256 | `b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77` |
| 构建 manifest SHA-256 | `de1c738fa2bc9027ceacadabb7828d9890f5f9ff57ec4cde60494968f927333a` |
| 数据库 commitment | `8eec1cad93cce37d2f958c100570550bc7212c5aa86b92b7cf03950f85a83161` |
| 发布指针 | `work/runtime/ghidra-full/latest.json`，已验证并发布 |

随后连续完成两个真实 REA 缓存查询，使用同一数据库及同一 profile digest `b0cb1a440ffe654cdb6c8d5c62e7f6ce6a5b45b422ea7bce2096e5af759482bb`：

| 查询 | 耗时 | 汇编 / 基本块 | Evidence ID |
|---|---|---|---|
| `fn.receive.reconstruct` | `30.80` 秒 | `112 / 19` | `ev_91f5176ff75ebd94ee4d4923c4243832da5041ab5ba46d8870ec4203aa8a38a0` |
| `fn.wrapper.clone` | `26.41` 秒 | `65 / 5` | `ev_3d3eb2d2b8d144c60ee12abdd05e880422124d2e765bd74d3a25c5f81cc948d2` |

两次均 `exit_code=0`、`query_reanalysis=false`、`database_unchanged=true`，且查询 Java 已结束；峰值分别约 `399.7 / 439.1 MiB`。[receive 原始返回](../work/runtime/rea-diagnostics-20261014/cache-receive/evidence.json)、[receive 运行记录](../work/runtime/rea-diagnostics-20261014/cache-receive/run.json)、[clone 原始返回](../work/runtime/rea-diagnostics-20261014/cache-clone/evidence.json)和 [clone 运行记录](../work/runtime/rea-diagnostics-20261014/cache-clone/run.json)保留完整证据。缓存查询日志直接执行 bridge，没有重新导入和自动分析阶段。

全量日志有未解析 TypeDescriptor、部分 demangled variable 数据创建失败及不可读地址等消息。Ghidra 最终报告 `Analysis succeeded`、`Post-analysis succeeded` 和 `Save succeeded for processed file: /eu4.exe`；这些成功标志不消除前述类型和语义缺口。两函数的 `callers=[]` 也不能证明没有调用者，虚表或未解析间接调用仍可能存在。

已通过 18 项模块合同测试和 cache-loader 的真实 REA 模块变换检查；另由完整构建、真实查询、profile 回读和数据库不变性验证完成实际链路验收。原始库和 Evidence 被 Git 忽略，源码副本不包含这些大型本机文件。

## 源码和官方参考

- [持久化缓存构建器](../reverse_engineering/ghidra_cache.py)：资源常量和身份约束 `:37-50`；阶段命令 `:451-617`；完成证据 `:784-908`；发布 `:932-955`；CLI `:1155-1200`。
- [缓存查询入口](../reverse_engineering/cache_query.py)：数据库 commitment `:20-33`；latest 选择 `:36-46`；查询与 Evidence 回读 `:59-178`。
- [REA 缓存 loader](../reverse_engineering/rea_cache_loader.mjs)：manifest/版本检查 `:8-27`；三处精确源码变换 `:29-74`。
- [按需 REA 入口](../reverse_engineering/rea.py)：缓存/seed 路由 `:68-94`；旧有界路线 `:95-245`。
- [完整分析状态脚本](../reverse_engineering/Eu4FullAnalysisStatus.java)：目标 SHA、阶段和 Ghidra Program 统计 `:12-31`。
- [Ghidra analyzeHeadless 官方说明](https://ghidra.re/ghidra_docs/analyzeHeadlessREADME.html)：`-process`、`-readOnly`、`-noanalysis` 和 headless project 生命周期。

