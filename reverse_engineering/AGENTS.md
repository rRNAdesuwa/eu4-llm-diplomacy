# 逆向模块维护规则

- 本模块维护当前需求的函数、对象、证据和问题索引；默认索引入口只做离线查询、校验和文件哈希检查。独立的 `reverse_engineering.rea` 入口可进行精确 EXE 哈希绑定的静态函数分析、临时文件和 Evidence 归档，并保留进程资源监督。
- 原生分析使用 `reverse-engineer-anything` 技能。先复用相同 EXE 哈希、分析配置和函数的已有证据，再进行有界查询。
- 用户已要求建立完整静态分析库并按需查询：`reverse_engineering.ghidra_cache` 负责持久化的默认 Ghidra 自动分析；完整保存且验证后才发布 `work/runtime/ghidra-full/latest.json`。后续 EU4 查询优先用 `reverse_engineering.rea` 复用已发布库，避免重新导入和全量分析。`--seeded` 才显式选择旧的临时有界路线；stock MCP 不加载项目缓存适配器。
- 完整库与查询用 `cache.lock` 保证单工程单会话。不得对未完成工程发布完成标志，也不得绕过保存日志、EXE/profile 身份或数据库不变性检查。缓存构建不等于全部函数已反编译或游戏逻辑已全部恢复。
- 每条结论记录证据类型、来源、适用构建和限制。静态路径、局部运行链、完整业务链分别登记；预测不能登记为实际响应。
- `.pdata` 地址及反编译地址属于特定 EXE。RVA 与静态 VA 分开维护；运行时地址使用重新读取的模块基址。
- 原始 REA 导出、游戏日志、存档和大型反汇编存放在被忽略的 `work/runtime/`；索引和文档只保存必要的分析结论和来源坐标。
- 遵守 `work/AGENTS.md` 的资源限制：不全量读取大型反汇编，不并发启动重复的 Ghidra 导入；分析进程超过 1 GiB committed memory 时检查精确命令并停止该进程。
- 当前配置的 512 MiB Java 堆不是进程总内存上限。记录实际占用、超时、取消和清理结果；完成任务时关闭自己打开的 REA 会话，收尾所有 shell session。
- 修改索引后运行 `python -m reverse_engineering validate --check-sources`；EXE 构建变化时另用 `--binary` 校验，不能只替换哈希字符串来继承旧结论。
