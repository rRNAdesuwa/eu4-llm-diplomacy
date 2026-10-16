# 1.37.5 剩余间谍行为：五个小对象家族的静态契约

本候选仅分析磁盘上的精确 EXE：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。没有读取游戏进程、调用引擎、编译 DLL、编辑研究宿主或增加对外可执行能力。所有家族仍是 `runtime_verified=false / production_ready=false`。

复用了原生目录、派生字段、值模式、共同 command、取消和普通 AI 队列报告。新解码 52 个明确入口、35,419 字节；另外验证已有报告中 5,061 字节的指令，避免重扫工厂和共同预览。每 CFG 窗口 16 KiB、最多 4,000 指令，新解码总限 40 KiB；只沿窗内直接分支，**不等于整个可达调用图**。运行峰值约 101 MB，低于 AGENTS 限额。工作探索保留在 `*-exploration.json` 和 `exploration-report-draft.json`，最终结论以 `report.json` 为准。

`trace.py --check` 会复核 16 个输入 SHA、完整 EXE SHA、重新生成有限 CFG、核验复用指令和 190 个虚槽字节，再与最终报告逐字节比较。报告 SHA：`274221df57719404edfcacd7451ebc28c678369dab9d4377e6201be5db734774`。

## 可以推进的五族

| 家族 | token / vtable RVA | 效果 +48 | 本族条件 +80 | 完整本族预览 +88 | clone +b0 |
|---|---|---|---|---|---|
| 腐化官员 `corrupt_officials` | 337c / 1c7c4a8 | 581ac0 | 5823f0 | 582730 | 582b20 |
| 破坏声誉 `sabotage_reputation` | 2ddd / 1c7cfd8 | 57ddc0 | 57e610 | 57e900 | 57eca0 |
| 散布不满 `sow_discontent` | 2ddf / 1c7c9e8 | 5844e0 | 584d30 | 585020 | 5853a0 |
| 诋毁商人 `slander_merchants` | 337b / 1c7c378 | 57f6e0 | 57ff30 | 580260 | 580650 |
| 破坏征募 `sabotage_recruitment` | 33bf / 1c7c5d8 | 5808d0 | 581120 | 581450 | 581840 |

五族均分配 `0x40`，没有已见派生字段或拥有式额外指针。其工厂分支最终到 `36044d`：`+30=-1`，`+34=0`，`+38=true`，`+39=false`，`+3c=0`，`+28/+2c=0x29c77f8`，三个 handle 为未绑定 `---`。工厂头 `35d226` 清 EDI，不能仅由公共尾部写 EDI 猜默认值。

五个 clone 都拷贝三完整 handle、日期、envoy、state、value、id；但 **clone+2c 取原件+28，而不是原件+2c**，并清 clone+39。wrapper `4e9930` 随后再把 clone+2c 写为当前日期，分配 `0x58` command，拥有 clone 于 command+50。原件仍独立拥有；生命周期测试不能把原件当 command 的同一对象。析构槽 `129450` 对 `0x40` 对象使用引擎释放。

只为“腐化官员”额外闭合了普通 AI 调用：`13c365..13c3c4` 从 AI+28、目标 country+20 和 GAME+1dd0 填完整 handle/当前日期，state=0、envoy=-1、value=true，交给 `129b60`。该函数 `129da0` 调虚槽 +88，`12a6e3` 调 +40 wrapper，再将 command 移入 AI+0xa68 并清临时指针。这是正常 AI 拥有式队列证据，不是人类 GUI 回调，也不是现场发送成功证明。其余四族本轮没有重新闭合普通初始化调用者，不因大小一致自动扩权。

## 本族预览、费用与提交

最重要的增量是 **完整预览必须保留 +88**。例如 `582730` 先调用通用 `4e9d00`，再检查 actor+2440 指向对象的 `+86` 字节。其他四族分别检查 `+80/+83/+81/+82`。解包 `common/technologies/dip.txt` 的 `may_*` 项与这些能力用途一致；字节数据流是已证，动态对象类型和载入定义仍需只读核验。

`4e9d00` 最后只调用 +80；command gate `4e8630` 也只调用 +80。因此仅复制现有通用预览调用会漏掉这些附加能力条件。普通 AI 的 +88 调用提供 `RCX=action, RDX=null, R8=false` 的正常无 tooltip 形态。未来候选必须精确钉扎本族函数后调用该形态；不能把返回 false 当基础设施故障，更不能替换其结果。

这些原生“预览”**不纯只读**：`8ecec0` 可为全局 `242bd08` 分配定义注册表；部分族会触发 TLS 懒初始化；`4ebdb0` 可为全局动作定义表分配内存、建立脚本 scope、调用条件。即使 tooltip=null，也不能据暂停或“不发送”声称不写缓存、没有副作用或任意线程可调用。

费用虚槽 +118 返回每族的定义值，`4ea610` 应用 actor 的费用修正，结果以 milli 表示。共同 gate 把 actor 关系表中实际计费对象的 signed WORD `relation+18`（百分之一点）乘 10，与费用 milli 比较。计费目标经 `3b9fa0` / `3ba040` 处理，附属国目标可能指向宗主国；不可永远用传入 target slot。

真实扣减在 `4eaadc..4eab20`：对费用乘 100 后有符号取整、加到 actor 关系 WORD，夹到 `0..10000`。state=0 分支先更新 actor 的行为统计，但 `4eaa23` 正常落入费用扣减块，不能误读成“state0不扣费”。正值范围内公式是 `max(0, network_centipoints - round_half_away(cost_milli/10))`。`contract.py` 仅模拟这段有限整数范围，明确拒绝潜在 32-bit 溢出。

五族 +100、+f8、+d0 都是常量 false，+108 为 true。因此共同 command 的普通外交冷却和外交官分配分支在这些具体虚槽值下被跳过，正常待回复分支也被跳过；**不能沿用“空闲外交官减少”验收这些行为**。执行器仍重新调用本族 +80，并经 `4ea820` 执行效果。没有证据要求为这些族开启 yesman。

现有通用 transport ownership 不因新 token 而改变：submit 之前必须检查完整预览及 command gate；转移进入后不重试、不对可能已转交的对象补析构；返回 true 或 container 消耗只证明分派观察。本候选没有重新证明 context ABI，更没有提供调用代码或生产授权。

## 效果及只读观察器需求

| 家族 | registry+槽 | country+2440 能力字节 | duration 全局 RVA | 设置到天 | stock 设置 / 得到天数 | stock 修正 key 候选 |
|---|---:|---:|---:|---:|---:|---|
| corrupt | 160 | 86 | 233fae0 | ×1 | 1825 / 1825 | corrupt_officials |
| reputation | 150 | 80 | 233fae4 | ×1 | 1825 / 1825 | reputation_sabotaged |
| discontent | 140 | 83 | 233faf8 | ×1 | 1825 / 1825 | discontent_sowed |
| merchants | 170 | 81 | 233faf0 | ×30 | 60 / 1800 | merchants_slandered |
| recruitment | 180 | 82 | 233faf4 | ×30 | 60 / 1800 | recruitment_sabotaged |

定义来源为解包 `common/defines.lua:203..219` 与 `common/static_modifiers/00_static_modifiers.txt:1655..1682`。stock 默认费用依次 25/60/80/70/80 点，实际运行受定义/修正影响，不能硬塞这些常数作原生参数或验收预期。注册表槽与 stock 名称的联系仍标候选，须有界读取动态 definition+158 的 String32 名称再确认，不能调用 getter 来验证。

五个效果都先调用 `4ec160` 动作脚本钩子，然后在 target 上添加定义修正，再重算/置脏缓存并生成通知。结尾的 `4eb900` **不是扣费函数**：它在 target+14b0 非空、value=true、envoy!=-1 时进入另一组动作脚本回调。这两组回调都可能有定义决定的额外世界写入。

`328c70` 把天数乘 24 加 GAME+1dd0，分配 0x50 对象，经 `b357b0` 写 vtable `1ce8040`、definition 指针 +30、到期 DWORD +44。目标国家持有链头 `+1f0`、尾 `+1f8`、DWORD count `+200`；每个 0x20 节点 object+0/prev+8/next+10/flag+18。本调用给对象+38关联参数传 null，**没有写 actor handle**。节点 flag 的完整移除语义、定义 virtual90 具体实现、析构/撤销链仍未闭合；未来 observer 先遇非零 flag/未知 vt/链不完整就输出 unknown。

建议第一族仅 `corrupt_officials(value=true)`，流程先生命周期→完整 +88 预览→封装/gate/析构无发送，最后才由新的获准实验宿主决定是否提交。没有额外金额、持续时间、region、faction 等外部参数。必须保留当前玩家 actor、独立 target、已核真实 capability、definition、计费关系与足额网络；不从脚本名称创建任意动作。

其只读验收生产者尚未实现，需要：完整 EXE/PID/creation/world/full handles 与玩家绑定；两次有界一致读取；有界完整修正链、已证明名称/虚表/定义槽；同日 before 没有该修正、after 新对象和预期实际到期日；实际计费对象的 network WORD 前后符合动态费用；可辅以 `CORRUPTOFFICIALSME/THEM` 消息和保存/重载。只能报告同日相关证据，不能因没有其他线程日志就声称排他因果。`contract.py` 的离线 selected-fields 模型仅供审查类型、取整和反例，**没有 PID/完整内存生产者、动态 registry 验证、removed 语义或引擎同步证明**；其结果永远不授权 native 调用。

false 模式不是逆效果：五族的已解码效果没有按 action+38 选择移除修正；一些 +80/+88 的 false 分支会跳过正向限制，故取消文案不能作为安全接口定义。本轮不开放任何 false 模式。

## 其他间谍能力的缺口

* `support_rebels` 是 0x48，+40 为目标所属 rebel faction 的借用指针；已有 parser `584420` 用两 DWORD identity 在目标+e68..e70中查 faction+10/+14。不是可以从外部直接写的 rebel-type 字符串。需独立完整 faction 容器、成本/付款、撤援方向与效果观察证据。
* `stealmap` 是 0x48，+40 为 region 整数（既有 `54ee40/54ee00` parser/serializer）。不能当 province ID；需 region registry、可见性/地图授予效果及合法性证据。
* `infiltrate_administration`、`agitate_for_liberty`、`counterespionage`、`justify_trade_conflict` 本轮仅引用既有映射，没有把 spy_network 的任务/取消结构迁移到它们。infiltrate 目录还没有工厂分支闭合。
* “研究科技”不能虚构为一个 token。`SPY_NETWORK_TECH_EFFECT/MAX` 是间谍网的科技作用配置；`STUDY_TECHNOLOGY_MIN_TECHS_AHEAD` 也不足以证明存在可发送原生家族。`new_diplomatic_actions/00_diplomatic_actions.txt:2031` 的 `steal_modern_ideas` 则是有俄罗斯现代化条件、30/24网络成本的脚本外交行为，属于 `scriptable_diplomatic_action`（3662，0x48，+40原生 definition 指针）。它需要独立脚本定义查找/载入绑定，不能当作裸 token 就完成了接口。

完整世界来源、strict single-player、引擎对象 lifetime/同步仍沿既有 C01/C02 缺口，不能用本报告的布局覆盖这些前提。

复现命令（Python312，磁盘只读）：

```powershell
python -B work/candidates/spy-action-contracts-1375/trace.py --check
python -B -m unittest discover -s work/candidates/spy-action-contracts-1375 -p test_contract.py -v
```

最终检查输出、输入前后 SHA、退出状态和测试记录见 `validation.json`；该验证证明静态报告可重放及离线模型约束，不证明游戏已执行。
