# 宣战条款、议和净 OE 与非法执行原因

AI现在可以读取所选宣战理由的结构化条款声明，并在议和前分别比较各国当前OE、取得省份的增加量、失去省份的减少量和预计净变化。执行非法议和请求时，统一结果还保留具体的原生规则原因。

## 宣战理由对应哪些条款

调用原有 `inspect_diplomatic_action("declare_war", ...)`，结果中的 `peace_term_rules` 包含三组记录：

| 字段 | 含义 |
| --- | --- |
| `disabled.disabled_actions` | 所选CB定义列出的禁用动作。原生记录带附加定义、或者尚未完成动作映射时，单独保留在 `unmapped`。 |
| `attacker_declared.declared_justified_actions` | 战争目标为攻击方声明的正当条款类别。 |
| `defender_declared.declared_justified_actions` | 战争目标为防守方声明的正当条款类别。 |

这些声明帮助AI确定需要比较哪些条款。割让具体省份、受益国能否取得省份，以及某个条款在当前战争中是否合法，继续由选定和约的原生查询判定；`selection_rules_evaluated=false` 和 `target_conditions_evaluated=false` 明确表示宣战理由查询尚未执行这些选择规则。表中没有某项条款，也不能直接解释成该项操作被游戏禁止。

实际查询法国对英国的贸易战争理由时，攻击方声明包括金钱、承认战败和转移贸易力量；CB禁用列表包括割省、归还核心、释放国家、释放或转移附属国、附庸和共主邦联等类别。征服理由的两侧声明包括割省；核心理由还声明归还核心。当前引用[002 校正报告](../work/runtime/r66-cb-rule-queries-20261019-002/report.json)作为 CB 结果。001 中的 `target_evaluation_required` 公共投影有一处错误，程序使用[001 实际查询报告](../work/runtime/r66-cb-rule-queries-20261019-001/report.json)中的同一批真实原生事件离线重投影并修正；002 的查询调用数和业务提交数均为 0，001 仍是 002 的原始事件来源。

## 同一和约分别怎样改变各国 OE

议和查询中的 `peace_consequences.overextension.countries` 按国家返回以下数值：

| 字段前缀 | 含义 |
| --- | --- |
| `current` | 游戏当前缓存的OE。查询同时按该国实际拥有的省份和原生规则重算，以确认缓存与省份状态一致。 |
| `gained` | 仅加入本方案取得省份时的OE增加量。 |
| `lost` | 仅移除本方案失去省份时的OE减少量，为非负数。 |
| `delta` | 同时考虑取得和失去省份后的净变化；负数表示OE下降。 |
| `projected` | 本方案预计产生的最终OE，等于当前值加净变化。 |

每组数值都提供 `*_raw`、`*_fraction` 和 `*_percentage_points`。例如 `delta_raw=120`、尺度1000，表示净增加比例0.12，即12个百分点。当前省份、失地和新增省份先汇总发展度，再统一换算，避免逐省取整后相加造成误差。

在 B 场景的 12 项实际预览中，法国索取省份 88 时，勃艮第当前 OE 为 `120/1000`，即 12%；失去该省后预计变为 0，净变化为 `-120` raw，即减少 12 个百分点。法国取得同一省份的净变化为 `+120` raw，即增加 12 个百分点。十六省方案还分别列出讷韦尔和布拉班特失去的省份，法国预计新增 `1760` raw，即 176 个百分点。[B 的 12 项实际预览](../work/runtime/r66-netoe-consequence-queries-b-20261019-001/report.json)和[A 的独立预览](../work/runtime/r66-netoe-consequence-queries-20261019-002/report.json)均保持国家缓存与重算值一致。

B 的非核心场景由单独的[场景报告](../work/runtime/r66-noncore-scene-20261019-001/report.json)准备：它只从省份 88 的核心列表移除 BUR，并保留 PIC。游戏已实际载入这份场景，B 的安装记录和 12 项查询记录了载入后的状态；场景报告本身只记录文件准备。B 的[独立 savecheck](../work/runtime/r66-overextension-save-check-20261019-001/report.json)和 A 的[独立 savecheck](../work/runtime/r66-overextension-save-check-a-20261019-001/report.json)各自核对 26 行，均为 `passed`、差异 0、未知 0。B 核对包含 3 行非零 loss，A 核对包含 6 行非零 gain；两份核对都检查了 native current、projected、delta 与保存省份数据之间的关系。

当前领土预览处理割省、归还核心和由实际割省集合构成的完全吞并。释放国家的完整失地枚举仍待接入；出现这类条款时，接口返回 `unsupported_territorial_terms=true` 和不完整状态。请求条款没有实际应用时，接口也撤回该请求的净变化可用状态。

100%战争分上限已在 C 构建完成运行验证。单省方案可以选择；只含十六个割省条款的方案，在查询、统一执行和原生执行前复检中均返回“不能提出超过100%战争分数价值的条件”，并保持 `submitted=false`。原生完整费用门使用引擎自己的上限与条款计算；接口没有把接受意愿或未知尺度的数值当作费用上限。[上限报告的8项检查全部通过](../work/runtime/r66-warscore-cap-20261019-004/report.json)，[C 构建的19类条款查询及第三国候选负例也全部通过](../work/runtime/r66-cap-family-queries-20261019-001/report.json)。

这项验收确实发现并修复了缺陷。A/B 的纯割省路径记录了费用值 `233`，却遗漏完整费用门，[003 报告](../work/runtime/r66-warscore-cap-20261019-003/report.json)在查询阶段识别了错误并停止执行。C 把现有原生临时移除—计算—恢复事务接入割省、核心和附属国条款，并比较恢复后的完整载荷。C 使用新游戏进程安装；为消除场景原有的发送冷却，B 和 C 分别在自己的实验进程将日期从 `1455.9.10` 推进31天至 `1455.10.11`，没有发送和约。

## 非法请求返回什么

`execute_diplomatic_action` 的执行前查询发现操作非法时，结果直接提供 `legality_reasons`，保留每项原生原因码和中文说明。请求进入原生执行前复检后再次被禁止时，结果中的 `native_rejection` 保留失败阶段、原生原因和说明。两种结果都会进入统一请求记录，可通过 `get_diplomatic_result` 再次读取。

实际负例包括：外交冷却导致法国暂时不能向勃艮第发送和约；请求由奥尔良取得省份88时，原生候选中不存在该受益国组合。前者返回 `NATIVE_PEACE_COMMON_GATE_UNAVAILABLE` 和可再次发送的1455.10.11日期，后者返回 `NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT`。[两项用例的统一接口与原生复检均通过](../work/runtime/r66-invalid-peace-requests-20261019-001/report.json)，没有提交外交业务。

失败记录中的 `binding_complete` 表示请求、战争、方向、国家和日期已经对应。规则原因的 `complete=false` 表示当前保留原生首先报告的原因，调用方不能把它解释成全部禁止条件的穷尽清单。

本批最终[803项测试、625项子测试通过](../work/runtime/r66-final-python-unit-20261019-001/report.json)。真实事件回放覆盖CB声明、净OE、非法原因和费用上限，并走统一工具投影。交付入口为[R66清单](../work/runtime/r66-python-docs-delivery-20261019-001/manifest.json)，完整goal继续进行。

R67进一步验证了其他参战国受益：ORL88可选，SAV91/193返回原生“不想要”和“无法核心化”，并取得一次实际出站与BUR拒绝。调用与角色见[盟主选择说明](盟主为参战国选择议和省份.md)。
