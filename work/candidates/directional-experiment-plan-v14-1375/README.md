# v14 十方向实验计划候选

这份计划只编排冻结 v14 已有的研究接口，不发送请求，也不证明目标当前允许某个动作。历史已审外交效果仍为20项，生产执行白名单为0；这十项和另外六项 wire ID 尚未效果验收。`plan.json` 是固定参数、前置状态和观察规则；`input-pins.json` 绑定输入；`offline-wire-checks.json` 记录28个纯编码往返检查（十项待验动作和四项历史已验 setup，各含 legality_only/submit）。没有 `.request` 文件或可直接投递的实时身份。

格式固定为 `EU4LAB/2`、purpose `restricted_pair_lab_1375_v14`、FRA→POR、operation=pair、speed=0。调用方只提供协议已有的 action、actor、target、mode、PID/creation、序号和过期时间；不能传入金额、年限、指针、RVA、envoy ID、force、console 或事件字符串。补贴由宿主固定为每月1.000、10年，包括取消校验。磁盘校验实际检查冻结的20项 native、11项 host、8项 support 和 DLL/manifest；不等于检查正在运行的进程。

## 每一组的步骤

先处理任何已经发布的请求，再检查最新状态。四阶段及其后健康帧必须在当前会话通过，且暂停、日期一致、无 pending/lease/input-wait/thread/world-change/freeze。`complete` 记录本身不能授权立即并行下一项。每次 legality_only 和 submit 都使用当前 `last_sequence+1` 的不同显式序号；表内组号不是序号。计划不固定未来序号，也不自动重试。

对当前选定动作取得 typed 两遍一致的 before；发送独立 legality_only 后，只有 preview 和 command gate 都允许、归属清楚且无异常，才可进入独立 submit 步骤。发送前宿主仍重新检查世界、线程、玩家、冷却、当前外交官和选定取消绑定。原生 status2/消费归属明确只说明已投递；after 观察到选定变化才是有限效果证据。未知归属、异常、冻结或日志缺失即停止，不再发送同一意图。

每个 before/after 比较必须同一 PID/creation、世界和完整句柄、相同 raw date。需要推进日期时只用现有带 exact-process 监督器的 speed 路径，等新健康帧确认 lease 完成且暂停，再重新取该动作的 before。不会把跨日自然过期当取消。生产严格单人/world epoch、AI接受、request因果、全世界不变和保存重载仍不由这个观察器证明。

| 顺序 | 固定动作及自然前态 | 有效角色与选定 before→after |
| --- | --- | --- |
| 1 | `embargo` → `revoke_embargo`；新增前 FRA 对 POR 的 bit2 必须未设，撤销前必须已设 | FRA 对 POR 的关系记录 +46 的 0x02 位：0→1→0；POR 对 FRA 的反向禁运不变。不要将其他 flag 当禁运。 |
| 2 | `offer_fleet_basing_rights` → `revoke_fleet_basing_rights`；先无选定普通协议，后唯一 active 协议 | **POR 持有、FRA 授予**。FRA f8/104、POR e0/ec 指向同一对象，+10 POR / +18 FRA；absent→active→absent。 |
| 3 | 已审 `ask_fleet_basing_rights` 仅在缺失时作有条件 setup，再 `cancel_fleet_basing_rights` | **FRA 持有、POR 授予**。FRA e0/ec、POR f8/104；+10 FRA / +18 POR；取消必须 active→absent。 |
| 4 | 已审 `offer_military_access` 仅在缺失时作有条件 setup，再 `revoke_military_access` | **POR 持有、FRA 授予**。FRA c8/d4、POR b0/bc；+10 POR / +18 FRA；active→absent。 |
| 5 | 已审 `ask_military_access` 仅在缺失时作有条件 setup，再 `cancel_military_access` | **FRA 持有、POR 授予**。FRA b0/bc、POR c8/d4；+10 FRA / +18 POR；active→absent。 |
| 6 | `give_subsidies` → `cancel_subsidies`；取消前必须是未名义到期的精确1000/10对象 | **FRA付款、POR收款**。双方110/11c同一对象，+10 FRA / +18 POR、+40=1000、+44=10；absent→active→absent。不推断即时扣款或未来每月结算。 |
| 7 | `dissolve_alliance`；先要求双向同盟，缺失时才有条件调用已审 `offer_alliance` 并等真实关系形成 | FRA/POR双方80/8c同一同盟对象；句柄顺序对称，active→absent。不能从对象认定谁发起；不宣称停战、好感或全局状态还原。 |

军事/停泊对象的 type marker 必须357、removed必须整数0、`enforce_peace` 必须整数0。条件通行和强制和平通行不能用于普通取消验收。两侧索引必须唯一一致，完整句柄、虚表、起始日、方向也必须匹配。取消前态用**取消动作的 ID**重新取样；不得拿 ask/offer 的报告改名使用。对缺失关系做 absent→absent 不是成功取消。

四项 setup 最多额外产生四次有条件提交；存在有效关系时可省 setup。但 setup 也需要当时合法性，历史成功不保证POR接受。计划不自动替换目标，不要求为了跑满表格强行建立关系。同盟 setup 可以在友好组之前单独做，但同盟不是这里证明过的通行必要条件；解除尽量放在这些组之后。

## 已知截面与目标限制

保存的 PID18356/creation `01dd56aa6f724ea8` seq2 `embargo` FRA→POR 的 native preview、command gate 均允许，没有 submit。这里只读取该不可变报告和 fixture 后只读报告，不读取增长日志或之后的请求。计划生成时会校验其SHA；它不代替执行时的新状态检查。计划首组紧接这一已检查方向，撤销禁运后再尝试友好提议；恢复 bit 不保证恢复所有好感或惩罚。

另一个已停止的 PID29492 预检前缀显示：POR的七个相关family正向preview/gate允许，取消均不允许。28条原始case均无发送。取消不允许不能推导“关系一定不存在”；仍需当前只读对象证据。此前成功目标或相同日期也不能代替当前合法性。

fixture v3增加FRA外交官/外交声誉、只给NAV/FOI添加双方意见修正，并将NAV变为FRA附庸；它不保证POR好感，不直接建立本计划中的通行、停泊、同盟、补贴或禁运。`fixture_off` 也不撤销NAV附庸或保证外交官池回到3。不要重复 fixture_on，不把callback成功当完整前态证明。若POR不能满足某项，记录明确拒绝/未满足条件并停该组，不更换未审核目标或参数。

## 本轮之外的阻塞

| 尚未验收 wire ID | 有限已知证据与缺口 |
| --- | --- |
| `insult` | v12 seq28 legality允许，固定 index=-1；未实际提交，没有本候选可用的效果布局/比较规则。 |
| `form_coalition` | v12 seq23/25在两个日期被native preview以reason17拒绝。fixture没有建立AE/coalition资格；不允许绕过。 |
| `leave_coalition` | 需要FRA确实属于针对目标的coalition及匹配成员表，当前未证明此前提。 |
| `support_independence` | v12 FRA/POR在原生preview前就status0/reason13拒绝；双方独立不满足scope。fixture后的FRA→NAV也不满足，因为FRA正是NAV宗主。不得假设FOI或另一个TAG有合法结构。 |
| `cancel_independence_support` | 需要宿主支持角色中的active支持关系；没有已建立的合法positive前态，不可将缺失当取消。 |
| `trade_favors_for_gold` | v12 seq27 preview以reason17拒绝；fixture不证明所需favor条件。不从观察后的经济数字反推expected值。 |

更广目录的静态映射不扩大36个wire ID；尚未实现的请求参数绑定、生产consumer、严格单人来源、可靠世界代次、同步生命周期、跨目标行为和异常恢复仍是生产阻塞。研究命令的native ownership和只读状态变化都不自动满足这些条件。

## 离线复核

```text
python work/candidates/directional-experiment-plan-v14-1375/prepare.py --check
python -m unittest discover -s work/candidates/directional-experiment-plan-v14-1375 -p test_plan.py -v
```

初次生成使用无 `--check`，仅以 CreateNew 写本目录三个 JSON。检查模式不改文件。测试禁止 process/publish/listener；只使用冻结编码器和模拟PID1/creation1/sequence1检查格式，不生成实时可投递请求。各输入数量、单文件和总字节上限写入pins。修复后的观察器 SHA `acb38546adea4d1fef88803a1057e465d7e5ff297fe4959760757d3b7fce1496` 和独立复审报告一并绑定。此计划不修改任何旧候选、能力索引、共享support、冻结宿主/native或存档。
