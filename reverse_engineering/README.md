# EU4 外交逆向模块

本模块将当前联盟外交需求的函数、对象、调用关系、证据和待解决问题集中维护。先阅读[《联盟外交逆向梳理》](../docs/联盟外交逆向梳理.md)，再用索引查询具体地址和来源。

当前适用二进制为本机 EU4 1.37.4，SHA-256：

```text
b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77
```

索引描述已归档实验与静态分析；它不自动读取当前游戏状态，也不执行外交动作。

完整 Ghidra 默认静态分析库已建立并保存：65,423 个函数、6,662,700 条指令。接收重建和 wrapper clone 的缓存查询分别用时 30.80 / 26.41 秒，数据库前后哈希不变。后续函数查询默认复用已发布库，避免重新导入和全量分析。详见[完整分析与缓存查询](../docs/Ghidra完整分析与缓存查询.md)；此前的超时和有界路线保留在[故障诊断](../docs/REA故障诊断与按需分析.md)。

## 文件入口

| 文件 | 用途 |
|---|---|
| [联盟外交逆向梳理](../docs/联盟外交逆向梳理.md) | 当前需求、阶段地图、函数与对象、证据边界、后续顺序 |
| [data/alliance.json](data/alliance.json) | 可查询的结构化索引；稳定 ID 连接函数、关系、来源和问题 |
| [catalog.py](catalog.py) | 离线读取、引用与证据类型校验、EXE 哈希和 PE 映像边界校验 |
| [__main__.py](__main__.py) | 命令行查询入口 |
| [rea.py](rea.py) | EXE 哈希绑定、进程内适配、资源监督和 REA 静态函数查询 |
| [ghidra_cache.py](ghidra_cache.py) | 完整静态库的构建、检查、恢复和发布 |
| [cache_query.py](cache_query.py) / [rea_cache_loader.mjs](rea_cache_loader.mjs) | 复用完整工程，回读 Evidence 并验证数据库未改变 |
| [pe_ranges.py](pe_ranges.py) / [Eu4ReaDecodeFunctions.java](Eu4ReaDecodeFunctions.java) | 流式读取选定 PE unwind 范围，并在临时 Ghidra 数据库中有界反汇编 |
| [AGENTS.md](AGENTS.md) | 后续分析、资源限制和证据维护规则 |

原始日志、反汇编、REA Evidence 和分析运行记录保留在项目本地的 `work/runtime/`。这些文件被 Git 忽略；取得源码索引并不等于取得全部本机证据。`validate --check-sources` 会明确报告缺失文件。

## 使用

离线索引查询在项目根目录运行，使用现有 Python 环境，无第三方依赖：

```powershell
python -m reverse_engineering overview
python -m reverse_engineering symbols
python -m reverse_engineering symbols receive
python -m reverse_engineering questions
python -m reverse_engineering validate --check-sources
```

核对特定 EXE 是否匹配索引时，用本机实际路径：

```powershell
python -m reverse_engineering validate --check-sources --binary '实际路径\eu4.exe'
```

`--binary` 流式计算 SHA-256，并从 PE 头读取映像大小校验 RVA。该命令不启动目标。RVA 是映像内坐标，静态 VA 为 `image_base + RVA`；运行时 VA 使用重新取得的模块基址，不能把磁盘文件偏移或旧进程绝对地址当作 RVA。

对索引中的已确认函数进行静态 REA 分析：

```powershell
python -m reverse_engineering.rea fn.receive.reconstruct
python -m reverse_engineering.rea fn.wrapper.clone
```

该入口另需要 `psutil`（本机已有），已验证 REA 6.4.0、Node 24.13.0、Ghidra 12.1.4 和 JDK 21。默认目标取自现有 `local.env`，只接受索引的精确 EXE 哈希。默认从 `work/runtime/ghidra-full/latest.json` 选择完整库；`--cache` 可明确指定缓存目录。完整库模式也接受 RVA、静态 VA 和准确 Ghidra 符号名。每次启动独立的 REA 官方 CLI，以 `-process eu4.exe -readOnly -noanalysis` 读取已有工程，保留原有 Windows 原生资源管理。结果写入新的 `work/runtime/rea-cache-*` 目录；`--output` 可指定不存在的目录。此命令不运行游戏或执行外交动作。

缓存 profile 为 `eu4-persistent-default-analysis-v1`，承诺适配器、完成报告和数据库树 SHA。查询前后检查数据库未改变；缓存用独占锁避免并发访问。默认静态分析正常完成仍不能证明全部间接调用、原始类型、外部 ABI 或运行时业务行为。原版 stock MCP 不加载项目适配器，仍使用自己的临时导入流程。

需要完整构建、状态检查或恢复时：

```powershell
python -m reverse_engineering.ghidra_cache build
python -m reverse_engineering.ghidra_cache status --cache '缓存目录'
python -m reverse_engineering.ghidra_cache resume --cache '缓存目录'
```

当前 EXE 已有完整库，可以直接查询。新建构建成功后自动发布最新库，未完成的分析不会发布。超时或资源停止保留已有检查点和日志；详细完成条件与实例路径见完整分析文档。

若明确需要旧的临时有界路线：

```powershell
python -m reverse_engineering.rea fn.receive.reconstruct --seeded
python -m reverse_engineering.rea fn.receive.reconstruct --seeded --seed fn.wrapper.clone
```

旧路线一次最多声明 32 个已确认入口，并要求精确 PE unwind 范围；全局引用覆盖不完整。完整缓存模式不能同时指定 `--seed`。

profile 使用 `eu4-declared-seeds-pdata-noanalysis-v2`，承诺适配器、Java helper 和范围文件的 SHA。只有目标哈希、profile、函数范围、汇编和伪代码回读通过后才报告成功。PE unwind 范围不是完整 C++ 类型或 ABI 的证明；未声明函数的 body、全局 caller、字符串和类型信息可能缺失。空引用不能证明没有调用者。日志尾部每秒采样，可能不包含退出前最后一条信息；完整返回保存在 `evidence.json`。

指定另一个小型索引：

```powershell
python -m reverse_engineering --catalog '其他索引.json' overview
```

索引工具的合同测试：

```powershell
python -m unittest discover -s reverse_engineering/tests -p 'test_*.py' -v
```

测试覆盖悬空引用、fixture 冒充运行证据、EXE 哈希错配和 PE 虚拟布局边界，以及 unwind 记录歧义、非精确入口、越界和非代码范围，避免导入错误目标或无界展开。

## 证据状态

| 状态 | 含义 |
|---|---|
| `runtime_observed` | 指定游戏构建和实验中实际观察到；不自动扩展到其他场景 |
| `static_observed` | 当前 EXE 的汇编、虚表或反编译中可直接核对的关系 |
| `inferred` | 从现有证据推导的语义或路径，仍需补证 |
| `unknown` | 尚未建立证据，或现有方法无法回答 |
| `fixture_verified` | 独立测试程序验证的实现性质；不计为 EU4 业务验收 |

同一个函数的代码、运行入口和业务意义可以有不同证据强度。节点的状态描述其明确记录的结论；字段、关系和限制应结合正文阅读。看见执行入口不代表游戏接受了提议，看见序列号连续也不代表发送者身份或授权连续。

## 继续研究的流程

1. 从 `questions` 选择当前阻塞问题，检查它关联的节点和历史来源。
2. 核对 EXE 哈希，复用匹配的 REA Evidence 或已分析函数；只扩展与该问题有关的函数、引用和字段。
3. 将新原始证据写入新的 `work/runtime/` 路径，记录工具版本、分析配置、Evidence ID、覆盖范围、内存和清理结果。
4. 在 `alliance.json` 增补来源及节点/边，保留未知项，不用新静态证据覆盖旧运行身份。
5. 更新正文中相应结论、证据限制和问题状态，运行索引校验。新的运行证据另绑定会话、DLL 哈希和实验报告。

先完成联盟共用链路，再将其扩展到其他外交动作。版本适配、权限实现和业务验证仍由开发模块承担；逆向索引不会把研究候选直接变成可调用 API。
