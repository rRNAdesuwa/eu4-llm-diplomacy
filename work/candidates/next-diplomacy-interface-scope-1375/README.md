# 剩余外交接口的有限盘点与下一轮范围

本候选只读取 20 个固定文件，共 6,749,093 字节；单文件硬读取上限 4 MiB，总量上限 16 MiB。不读取游戏进程、不调用研究 CLI、不扫描增长日志、不新增原生代码、不修改任何目录或接口。机器报告为 `report.json`，逐项保留 237 个剩余目录 ID 的来源、参数完成度、静态映射类别和当前阻断原因。

## 覆盖数字应如何理解

| 层级 | 当前固定证据 |
|---|---:|
| 目录描述 | 274 |
| 任一静态映射 | 270 = 167 ordinary + 41 subject + 9 special + 53 peace |
| 冻结 v17 研究入口 | 36 |
| 这些入口对应的目录 ID | 37 |
| 按显式绑定扣除后的目录差集 | 237，其中 233 已静态映射、4 未映射 |
| 历史索引中有选定状态效果的外交动作 | 28 |
| 正式可执行动作 | 0 |

直接比较名字会得到 34 个交集、240 个差集，不能拿它代替语义绑定。`request_trade_power` 对应目录 `transfer_trade_power`；研究 `cancel_independence_support` 对应两个目录取消别名。这两个别名的存在不证明两个角色方向都已执行或生效。当前 274 项是已对账目录，也不是所有脚本、所有条件分支和全部游戏行为已经穷尽的证明。

237 项按来源分为：普通外交 134、属国交互 44、政府机制 3、和平条款 54、历史请求 2；其中 159 项参数形状为 `specified`，78 项为 `partial`。4 个未映射项仍是 `break_vassalization`、`gold`、`whitepeace`、`peace.full_annexation`。

本次仅读取并绑定历史能力索引，不重审其中 876 个证据文件或大型存档，不根据正在进行的批测增加效果数。首次报告生成时将 `control.speed` 误计入外交效果导致断言失败；修正为按目录绑定过滤后得到 28，首次失败没有生成报告，也没有游戏访问。

## 现有对外接口已经提供什么

正式 `/v1/capabilities`、`/v1/actions/{id}` 已暴露全部 274 个动作的参数、证据和阻断原因。`/v1/preview` 只验证请求形状与能力，明确不检查原生合法性、AI 接受、外交官可用性。`/v1/requests` 在不支持时持久记录 `unsupported`；状态、事件与只读 `reconcile` 保留幂等和未知冻结语义，不会补发。

使用现有 `_readiness` 方法、固定本机 SHA 和 `backend=None` 离线计算：274 项都有 `unsupported_build` 和 `backend_unavailable`；271 项另有 `action_unimplemented`，80 项另有 `parameters_unresolved`。计数有重叠。历史三项 verified 属于旧构建，不能用于本机。`specified` 只表示公开 JSON 形状确定，不是原生公参绑定或生命周期已经验证。

独立 `/research/v17` HTTP 只提供 36 项固定 pair 的 legality-only/submit 和状态查询。EU4LAB/3 固定 13 字段、完整进程身份、严格序号和常量参数仍受冻结宿主管理；fixture、speed、阶段、加载、重置、accept_on/off 不经此 HTTP 开放。正式 EU4PAIR/1 后端草案没有注册，研究日志不会生成生产白名单。

## 建议下一三类

| 次序 | 限定入口 | 批测价值 | 最小必补合同 |
|---|---|---|---|
| 1 | `subject.set_military_focus` | 六个有限枚举值，已有明确写入字段 | 独立 0x60 命令生命周期、完整目标身份、当前宗主权限、目标 `+0x2864` 只读观察 |
| 2 | `subject.scutage`、`subject.divert_trade`、`subject.embargo_rivals` | 三项共享 subject command，可形成六方向矩阵 | 借用 singleton 与独立 0xa0 命令所有权；desired enabled 与当前 cancel 状态转换；各自旗标、费用和合法性 |
| 3 | `curry_favors`、`stop_currying_favors` | 有限 start/stop，适合外交官任务观察 | 此 family 工厂/clone/析构、完整 preview/gate、即时外交官/任务身份、取消归属与后续 favors 观察 |

军役枚举必须使用 GUI 已证实的 `0=no_focus,1=aggressive,2=supportive,3=passive,4=defensive,5=siege`。其原生 gate 不足以证明调用者的宗主权限，不能只检查枚举范围后发送。它也不是普通 pair action 或借用 singleton 的 subject command。

属国布尔交互的构造器会从当前状态推导 `cancel`。公共 `enabled` 不能直接当任意 byte 写入；同目标已经是期望状态时应明确返回无原生操作，而不是伪称应用成功。单例永不由调用方析构，String32 和独立命令必须另验所有权。此轮不顺带开放第三国、任意 index 或字符串字段。

积攒人情取消的 `value=false` 目前是 UI 模式证据，不等于取消效果成立。100 个外交官对象或空闲候选也不保证特定行动合法；即时 envoy/mission 身份仍需在消费时重查。

NAV/POR 均只是下一轮候选目标，不是合法性承诺。本次没有读取当前世界；此前批测可能已解除 NAV 属国。必须先证明新的同世界身份、dependency、类型、可用资源及实际 native gate。支持独立、宗教或政府机制需要的结构不会因外交官增多而满足。法律拒绝只算覆盖了拒绝路径。

保持用户要求的 initial/final-only：开始后取消可能抹去中间状态，最终 census 不得将全部正反操作标为效果已验证。可验证最终保留的枚举/任务/旗标；不能由最终无关系推断中间成功，也不能由命令返回推断经济经过一次结算。

五项已有静态间谍候选明确排除：corrupt_officials、sabotage_reputation、sow_discontent、slander_merchants、sabotage_recruitment。不重复 C01/C02。和平/宣战、favor 数额交易、吞并整合、脚本政府机制各有战争上下文、资源、时间或定义解析缺口，暂不作为本轮最快有限批测范围。

所有新类仍需新的研究版本及独立生命周期与参数验证；本报告不授权发送。严格单人来源、同世界代次撤销、原生生产消费者、即时暂停证明、白名单与未知归属对账仍是正式接口的共同阻断，不在这里重复展开静态扫描。

离线复核：

```powershell
python -B work/candidates/next-diplomacy-interface-scope-1375/review.py --check
```

该命令只重算固定集合、描述符与无后端 readiness，并逐字比较已封存报告；不运行游戏或对外服务。
