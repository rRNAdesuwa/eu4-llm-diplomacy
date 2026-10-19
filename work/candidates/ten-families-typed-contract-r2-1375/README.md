# 十族 typed contract 第二候选

本目录是隔离的 `TenFamiliesDraft/2` 提案，只提供参数描述、严格纯校验、十项请求例子和 unsupported 草案。它不注册正式 `EU4DIPLOMACY-CONTRACT/2`，不修改正式 API、274 项目录、backend 或数据库。request_id 不预留，不提供持久幂等、队列、执行、接受或效果承诺。

前一份已封 `ten-families-public-contract-1375` 草案有八项受限静态参数形状闭合，两项未闭合。新候选保留原草案的公开参数形状，并用已封 `favor-trust-reduce-bindings-1375` 及独立离线复核补齐两项的静态参数来源。十项 `parameter_binding_closed=true` 都仅表示 `restricted_static_parameter_shape_and_source_only`。实际 runtime binding 数量仍为零。

| 动作 | 明确公开字段，另需 actor、target TAG |
|---|---|
| claim_throne | 无 |
| sell_province | province_id、price_integer，整数金币 0..2147483 |
| enforce_peace | opposing_country，第三国家 TAG；不是 war_id |
| threaten_war | province_id、taker_country；taker_country 必须等于 actor |
| trade_favors_for_gold | 无；金额由原生动态计算 |
| trade_favors_for_men | 无；人力由原生动态计算 |
| trade_favors_for_sailors | 无；水手由原生动态计算 |
| trade_favors_for_war_prep | 无；备战不保证实际开战 |
| trade_favors_for_trust | 无；只表达原生工厂的一步，不接受 favors、amount 或任意两数 |
| reduce_relations_favor | third_country，必须在 TAG 语法上不同于双方 |

trust 的静态加载来源是 `NDefines.NDiplomacy.INCREASE_TRUST_COST` 和 `INCREASE_TRUST_AMOUNT` 两个 signed int32 global。私有绑定将观测 cost 整数乘 1000，amount 保持整数 trust points。RVA、offset、完整句柄和 token 只保存在独立 `static-binding-index.json`，不进入公开请求，也不默填解包文件的 10/5。loaded globals、注入 reader 输出、缓存 extras 和两次相等快照都不能证明当前进程身份、生命周期、原生合法性或执行许可。

reduce 的已审静态 GUI 路径为 country 的完整 QWORD handle 经 dialog 保存到 owned action extra。公开输入仍是 third_country TAG；未来的已认证 loader/private country resolver 必须从当前 loaded country registry 解析 full handle，核 generation、三个国家不同、两 pass 指针及完整句柄、末尾根/date/player，并另做 owner-thread 权限和生命周期处理。本候选没有实现 TAG→live handle 解析；已有注入 reader 模型接受外部给定完整 handle，不能替代它。正常 GUI 刷新是 +80 mutable text sink/false，与已审 AI +88 NULL/false 不同。正常 wrapper 到 14ca210 仅是静态传递证据。

`formal-api-diff.json` 精确记录当前正式 V2 的差距：四项公开 schema 需要另行版本迁移（sell 的 price、enforce 的 war_id/defender、threaten 缺 taker_country、trust 的 favors），reduce 的 TAG 字段形状不变但缺少新的静态来源说明。正式 V2 目前对十项均无 typed extension；其 `_schema` 只特殊处理另外的 steal_maps/support_rebels。本候选不自动丢弃旧字段、插入 actor、舍入金币或转换 war_id。

文件用途：

- `contract.json`：十族描述与静态来源/运行限制；没有公开 native_descriptor。
- `schema.json`：十项 JSON 请求形状；跨字段约束用 `x-cross-field-constraints` 说明并由 catalog.py 强制。
- `request-examples.json`：十项语法请求例子，固定预期 unsupported；省份及国家例子不代表 live 选择。
- `static-binding-index.json`：私有静态 RVA/layout 与精确封存报告引用，actual runtime values=null。
- `contract-delta.json`：上一草案 8→10 的静态来源变化，公开参数形状不变。
- `formal-api-diff.json`：供另行正式 API 应用审查的四项 schema 差异和十项绑定差距。
- `report.json`、`validation.json`、`review.json`：CREATE_NEW 封存来源前后 pin 和验证结果。

离线命令：

```powershell
python -B work/candidates/ten-families-typed-contract-r2-1375/build.py --check
python -B -m unittest discover -s work/candidates/ten-families-typed-contract-r2-1375 -p test_*.py -v
```

37 项输入（含精确当前正式 API 文件快照）作为本次差异审计来源；catalog.py 只读本目录固定 hash 的 contract.json，不导入正式 API，不把可变正式文件作为运行依赖。无 PE 新解码、游戏/目标进程读取、原生调用、DLL、编译或 backend 注册。后续正式应用需独立审查和明确版本策略。
