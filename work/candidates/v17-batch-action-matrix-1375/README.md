# v17：一次批量完成 36 研究 ID，再做最终状态观测

这是离线固定矩阵，不包含 PID、未来 request sequence、native 调用、可发布请求或新授权。36 行覆盖 20 family：16 正向/取消对，加警告、普通侮辱、赠款、人情换金币四个单向动作。本次实际默认只有 **initial + final** 两组聚合快照；不用中间 S1，不逐动作调用效果 observer。所有逐项 `effect_verified=false`，批末输出只称选定状态盘点。

执行契约：已有当前会话四阶段通过、FRA 玩家/完整身份不变、测试 fixture 已启用、暂停、acceptance closed/flag0、无 pending/lease/freeze，才可由既有受限 host 编排。不要重复 fixture_on；最后也不要在持久外交官任务仍在执行时先 fixture_off。新 batch 不自动调用 accept_on/off，更不改变冻结 native。普通授予停泊权即使合法投递也可能被正常 AI 拒绝；当前静态路径 score=-1000，不能把更多外交官当作 AI 接受。

每行依次做一次新 legality，原生 preview 与 command gate 允许、所有权清楚时才可 submit。每次请求仍须收取严格完成日志、确认正常归属、无异常/冻结，才能消费下一序号；这不是效果观测。明确合法性拒绝可记录后继续独立行；unknown ownership、异常、审计缺失必须终止余下批次，不补投、不补取消。不能从 reason17 单独推断具体失败原因。

同一 target 的普通原生命令仍要求 `current_raw_date > last_native_target_threshold`。Mod 的 cooldown=0 不放宽这个严格比较，也不清旧存档阈值。计划优先在日期推进前执行其他 target 的已就绪行；同 target 轮次需要通过已有 exact-process supervisor 的有限 speed 租约正常推进并回到健康暂停。每一行 law/submit 使用同一暂停日期；旧 law 不跨天复用。100 外交官是可并行占用的有限池，不是100个白名单国家、同日冷却豁免或100条并行邮箱请求。

`order` 是稳定拓扑优先级，不是实时 sequence。`after_attempts` 含语义依赖和前一个同目标动作；不同目标的就绪行可在同日依序执行，邮箱始终最多一个未完成请求。取消的前态由当前 native 双边对象/方向/flags/type/fullhandle guard 重查，不能用正向 dispatched 代替 active，也无需额外插入逐步效果读取。

目标约束：POR 为大部分友好提议候选；改善关系放 FOI、间谍网放 ENG，两种持续任务分开目标且 spy 排在 ENG 一次性提议之后。NAV 经 fixture 成为 FRA vassal，可供取消附庸；FOI 静态历史是 FRA appanage，不能作为当前只接受 vassal/client_vassal 的取消替代。`offer_vassalization(POR)` 没有已证明可行的新小国前态，预计可能被大小/关系等原生规则拒绝，排末尾；它与取消 NAV 不是同一条正取消回环。

支持独立的两行用 NAV 明确核对自身宗主作用域拒绝：当前 FRA 是 provider 也是 NAV overlord，不满足独立第三方支持；默认只 guard survey。ENG/POR 两独立国也不创造依附对象，FOI 又是自己的 appanage。包围网的资格/AE、人情换金币的人情数量均未由 fixture 建立，允许合法拒绝，不新增强制条件。贸易权取消先于转移贸易只是提高受限测试可行性的保守顺序，不声称原生普遍禁止两者并存。

批量跨日期使 initial/final 无法用于旧同日 effect matcher。不得改报告日期、抹掉日期约束或推导请求因果；初末相同的关系可能曾建立再取消，只可报告最终状态及期间被审核的 legality/dispatch/ownership。最终缺失也不能解释成 AI 拒绝。若某行有跨日自动过期/自然结算，仍不是该请求的效果证明。未来可选正向边界方案不在本次实际计划中。

| 优先级 | action ID | 固定目标 | 行为类别 |
|---:|---|---|---|
| 1 | `royal_marriage` | NAV | 需要原生回复/接受 |
| 2 | `offer_alliance` | POR | 需要原生回复/接受 |
| 3 | `improve_relations` | FOI | 持续派遣任务 |
| 4 | `guarantee` | POR | 单向原生动作 |
| 5 | `give_subsidies` | POR | 单向原生动作 |
| 6 | `ask_military_access` | POR | 需要原生回复/接受 |
| 7 | `offer_military_access` | POR | 需要原生回复/接受 |
| 8 | `ask_fleet_basing_rights` | POR | 需要原生回复/接受 |
| 9 | `offer_fleet_basing_rights` | POR | 需要原生回复/接受 |
| 10 | `request_trade_power` | POR | 需要原生回复/接受 |
| 11 | `cancel_trade_power_transfer` | POR | 当前对象取消/清理 |
| 12 | `steer_trade` | POR | 需要原生回复/接受 |
| 13 | `cancel_steer_trade` | POR | 当前对象取消/清理 |
| 14 | `send_gift` | POR | 单向原生动作 |
| 15 | `trade_favors_for_gold` | POR | 需要原生回复/接受 |
| 16 | `warn` | ENG | 单向原生动作 |
| 17 | `insult` | ENG | 单向原生动作 |
| 18 | `embargo` | ENG | 单向原生动作 |
| 19 | `form_coalition` | ENG | 单向原生动作 |
| 20 | `build_spy_network` | ENG | 持续派遣任务 |
| 21 | `support_independence` | NAV | 需要原生回复/接受 |
| 22 | `stop_improving_relations` | FOI | 当前对象取消/清理 |
| 23 | `stop_building_spy_network` | ENG | 当前对象取消/清理 |
| 24 | `revoke_guarantee` | POR | 当前对象取消/清理 |
| 25 | `cancel_subsidies` | POR | 当前对象取消/清理 |
| 26 | `cancel_military_access` | POR | 当前对象取消/清理 |
| 27 | `revoke_military_access` | POR | 当前对象取消/清理 |
| 28 | `cancel_fleet_basing_rights` | POR | 当前对象取消/清理 |
| 29 | `revoke_fleet_basing_rights` | POR | 当前对象取消/清理 |
| 30 | `leave_coalition` | ENG | 当前对象取消/清理 |
| 31 | `cancel_independence_support` | NAV | 当前对象取消/清理 |
| 32 | `break_marriage` | NAV | 当前对象取消/清理 |
| 33 | `cancel_vassalization` | NAV | 当前对象取消/清理 |
| 34 | `dissolve_alliance` | POR | 当前对象取消/清理 |
| 35 | `revoke_embargo` | ENG | 当前对象取消/清理 |
| 36 | `offer_vassalization` | POR | 需要原生回复/接受 |

完整先决条件、方向、固定参数及拓扑边见 plan.json。两方向军事/停泊权不互换：ask/cancel 是 FRA 持有、目标授予；offer/revoke 是目标持有、FRA 授予。补贴固定 FRA 付款/每月1000 milli/10年，赠款25金币，贸易权500/flag0，侮辱index=-1；人情换金币金额由原生计算。

纯离线复现：

```
python -B work/candidates/v17-batch-action-matrix-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v17-batch-action-matrix-1375 -p test_plan.py -v
```

历史：preseal-target-lane-draft 保存尚未显式添加目标 lane 边的初稿；最终图只增加前一同 target 的先后依赖，未改动作、目标、固定参数。首次12 tests中一项在测试代码把原版非UTF8历史文件整体decode时失败；原测试与 failure记录保留，改为精确ASCII字节检验，矩阵不变。最终验证另存，不能以末尾check的退出0掩盖前一测试退出1。
