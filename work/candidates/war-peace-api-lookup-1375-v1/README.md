# War/peace 离线合同查找候选

这是 EU4 1.37.5 已保留证据的检索工具，不是可运行的 war/peace API。它只打开本目录的索引和 19 个已固定报告文件，不访问进程、游戏 EXE、网络或 REA，不派发请求，也没有执行、分配或服务器命令。固定证据目标 SHA-256 为 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`；这不是当前磁盘游戏或进程的身份认证。

在项目根目录使用 Python 3.12：

```powershell
python work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py check
python work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py catalog --family peace
python work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py search command --limit 5
python work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py lookup declare_war.constructor
python work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py lookup 宣战构造
python work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py lookup 0x500560
python work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py lookup peace.date_check --base 0x140000000
```

`catalog`、`search` 返回摘要和证据引用；`lookup` 返回签名已证部分、调用现场、owned/borrowed 范围、未解条件及证据 JSON pointer。名称、别名和家族匹配忽略大小写；RVA 只接受 `0x` 前缀的 32 位十六进制值，且必须命中已收录端点。`search` 按精确命中、前缀、子串排序，同级按稳定 ID 排序。完整家族可用 `war` / `declarewar` / `宣战` 或 `peace` / `requestpeace` / `议和` 查询。完整函数原型没有被补猜；已知参数只是静态或 raw probe 的局部签名。

43 条记录中，42 条阶段为 `static`。`declare_war.body_destructor` 的阶段为 `real_rawbody_postcondition`，仅指 R19 已审的一次自有 A98/G60 raw ABI test double 正常返回及其最终 postimage。它没有证明合法 C++ 对象、构造等价、完整生命周期、宣战/议和效果或 header/world/module lease；静态两个 A0 写点也不等于观察到了瞬时写入。完整 sender 或 constructor 的阶段不会因此提升。`kind=callsite/basic_block` 也不会被当作函数入口。

议和 local80、full88 和独立 date90 分开索引。检查记录引用 R4 已纠正的 country-root 字段别名关系；共享 root 读取路径不会被当成第二个独立战争索引。R5 的“仅已知 referent”限制随所有相关记录保留。旧报告中比本索引更宽的 host 设想不构成本工具的权限。

所有返回的 `callable`、`native_ready`、`sender_authorized`、`gameplay_effect_verified`、`process_authenticated` 均为 false。`native_calls=0` 和 `requests_published=0` 仅统计本次离线查询，不抹去 R19 历史实采中的一次顶层调用。退出 0 只表示本地查询/核验成功；退出 2 是 unknown 或输入/来源拒绝。无匹配的搜索正常返回空集，精确 lookup 未命中返回 unknown。

可选 `--base` 只为已收录 RVA 做用户给定 base 的条件整数加法：要求 page aligned、低半 canonical 用户范围且不越界。输出明确 `conditional_arithmetic_from_user_supplied_base`，不认证模块基址、映射大小、指针可读性或进程，也不提供任意地址执行能力。不安全 base 或未知 RVA 会丢弃整个结果，不输出条件 VA。

CLI 源内固定 `data-manifest.json` 的 SHA，在解析索引前先验证清单、索引和每个所选来源的大小/SHA，再验证证据 JSON pointer 与字段边界；返回前再次核验全部来源。单文件上限 4 MiB、总图上限 32 MiB。路径必须在项目 `work/reports/` 内，拒绝穿越和解析后逃逸。此双遍是文件完整性检查，不声称提供原子文件系统锁。CLI 不接受外部 manifest/root 参数；内部 `SourceGraph` 参数仅供离线临时 fixture 测试使用。源码本身的完整性由独立 source manifest 与后续审阅 pin 保证，不伪称自我认证。

`build_index.py` 是人工编目作者工具：按明确 JSON pointer 引用选定源，使用排他创建，已存在索引时不会覆盖。它不是 CLI 的运行依赖，也不是自动反汇编或自动解释器。修改目录或源清单后必须重新审阅，不能沿用旧 source pin。

`test_lookup.py` 是本候选新增的 13 个纯文件/纯数据测试方法；不导入或重跑旧测试。`verify_offline.py --run` 仅用于首次新增测试，在已审 r3 Job helper 下限制新 Python 子进程树为 768 MiB、8 个累计进程、45 秒，收齐 stdout/stderr/退出结果并排他写入 `offline-r1`。已存在回执时拒绝复跑。`verify_offline.py --check` 只核验新 source manifest 和已保留首次回执。Job 管理系统调用只属于测试外壳，不属于 CLI；游戏进程不会分配给该 Job。

本目录是未封存的查找候选，提交 root 审阅；不改稳定 public/native、任何已封源或原测试回执，也不开放既有 war/peace gate。
