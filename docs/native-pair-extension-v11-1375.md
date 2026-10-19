# 1.37.5 下一组八类普通外交：静态候选

本报告为 v11 研究候选，未构建或注入 v11 DLL，未访问游戏进程。它不改变目录或生产 backend。八类均为既有 88-family factory 中的真实类，不通过复用一个 setter 虚增 family 数量。`runtime_verified=false`、`execution_verified=false`。

生成器：`python -B work/trace_pair_extension_v11.py`；复现：同命令加 `--check`。

报告：`work/reports/native-pair-extension-v11-1375.json`，SHA256 `ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344`。
游戏 PE SHA256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。生成器固定三个既有报告的完整 SHA，逐项复核方法槽，并重新解码选定函数；还记录本体 diplomatic actions、alert 定义、defines 和英文词条的文件 SHA/行号。DLC 名字不会覆盖到本体命名空间。

## 精确候选

| 原生 family / token | 动作 vt / 大小 | 正向操作 | 取消语义 | 派生参数 |
| --- | --- | --- | --- | --- |
| `warningaction` / `2942` | `1c7fa40` / `40` | 警告目标 | **不提供**；已审效果入口未按 value 分支 | 无 |
| `insultaction` / `2947` | `1c7f6b0` / `48` | 普通侮辱 | **不提供**；false 不等于撤回侮辱 | `+40 int32 index=-1`，内部固定 |
| `form_coalition` / `2de0` | `1c7c788` / `40` | 对目标建立/加入包围网 | `value=false`，退出针对该目标的包围网 | 无 |
| `support_independence_action` / `2f2e` | `1c805f0` / `40` | 请求/提供独立支持，由当前依附状态判别 | `value=false`，结束已请求/已提供的支持 | 无；依附状态是前提，不是输入位 |
| `transfer_trade_power` / `2e09` | `1c7cea8` / `48` | 要求目标向 actor 转移贸易权 | `value=false`，取消当前方向的条约 | `+40` 定点比例；`+44=0` 内部固定 |
| `steer_trade` / `3778` | `1c7d238` / `40` | 要求目标为 actor 转移贸易 | `value=false`，取消当前方向的条约 | 无；序列化 `dummy` 被忽略 |
| `giftaction` / `2948` | `1c7f450` / `48` | actor 赠款给目标 | **不提供**，不存在据此证明的退款 | `+40` 金额，千分之一金币 |
| `trade_favors_for_gold` / `3bce` | `1c80980` / `40` | actor 用人情向目标索取金币 | **不提供**；正常请求仍需要回复 | 无；金额由原生计算 |

表中数字均为十六进制。建立/加入包围网是同一 true 模式的状态别名；请求/提供独立支持也是同一类的不同角色，不是更多工厂。普通 pair 只指定已解析的 actor/target，并且保持 native 自身合法性和接受流程。

## 构造和所有权边界

八类 `+40` wrapper 均为 `4e9930`，`+a8` 均为 `8f450(false)`，`+e0` 均为 `4e99d0`（只写 `value+38`）。五类对象为 `0x40`，侮辱、赠款、贸易权为 `0x48`，后者派生字段均为标量；没有新增拥有所有权的字符串或 war-goal 图。

必须由 `35d210` factory 构造真实对象，再初始化完整国家 handle、原始 actor、日期和派生标量。wrapper 的 command 拥有独立 clone；原对象仍单独拥有。跨入 context-submit 后不能补析构或重试。旧五类和 v10 的生命周期结果不能自动证明这八类已通过。

回复谓词 `+d0`：警告、侮辱、包围网、赠款为 false；支持独立、贸易权、转移贸易返回 value；人情换金币恒 true。需回复的正向效果另有 `state==2` 分支。宿主不应写 state2 来绕过回复，也不能把 gate/returned/dispatched 称为 AI 接受或效果已发生。

## 已闭合的参数与方向

普通侮辱 factory 的 `35d8a9→35d8bd` 明确写入 `index=-1`；效果在 `53794e`、`537eb3` 比较正负。非负 index 进入额外定义逻辑，故本候选不接受 scornful 原始索引。共享 value setter 不创造取消路径。

赠款的 `money` 与贸易权的 `amount` 均经已复核的有符号 `×1000` 数值解析器。赠款传给 `AddExpense(3387f0)` 的国家是 actor，传给 `AddIncome(338540)` 的是 target，两次金额相同。将来适配器还需限制正值、金额范围和乘法溢出；本报告未恢复完整赠款滑块范围。

贸易权 GUI 计算函数 `14003f0` 把整数百分比换成临时 action `+40` 的 `percent×10`：50% 是 500，100% 是 1000。该结论来自算术和常量 `1dc1938=1000.0`，不是把 slider 整数直接当金币或 native 比例。这里尚未恢复完整 dialog-submit ABI/全部范围，不能开放任意数值。clone `57adbe..57adc8` 复制 `+40` 却把 `+44` 清零；因此 `+44` 不是可直接透传的公开参数，初版只研究普通零标志条约。

人情换金币没有派生金额字段。`4f3fe0` 从目标国选择收入分项求和，乘 12，再乘 native `233f4cc/1000`；`state==2` 才进入人情扣减和 target 付款、actor 收款。资源有 `TRADE_FAVORS_FOR_GOLD_FAVOR_COST` 等定义，但定义值会受运行配置影响，报告不把 caller 自选金额或固定人情数伪装为参数。

## 持久状态和取消观察起点

| 行为 | 关系/状态 | 明确方向与撤销入口 |
| --- | --- | --- |
| 警告 | `0x40` 关系，vt `1c7fca0` | `+10=actor,+18=target,+20=action date`；双方通过 `a6a090` 注册。未证明公开撤销 |
| 包围网 | actor `+18f8` 完整目标 handle；目标 head `1910`、tail `1918`、DWORD count `1920` | `373880` 修改成员归属；false 路先核现有目标 slot，再传 invalid handle。未来宿主应升级为 full-handle 核验 |
| 独立支持 | `0x40`，vt `1c80570`；双方 root `170` / count `17c` | 关系 `+10/+18` 保留 proposal actor/target 顺序，**不是固定 provider/dependent 顺序**。false 经 `a69d30→a5e130` 移除 |
| 贸易权 | `0x48`，vt `1c571f0` | `+10=target供给方,+18=actor受益方`；供给方 root `230/23c`，受益方 `248/254`；取消 `a74b90` 清索引并置 removed |
| 转移贸易 | `0x48`，vt `1c7d498` | `+10=target,+18=actor`；转移方 root `260/26c`，受益方 `278/284`；取消 `a74f20` 清索引并置 removed |

索引条目沿既有 `16B(slot, object)` 结构处理时仍应有数量上限、完整 handle/marker/vtable 校验和双遍采样。包围网 list node 为 `0x20`：成员完整 handle `+0`、prev `+8`、next `+10`、removed BYTE `+18`。本报告没有实现这些只读观察器。

两种贸易取消入口都会尝试相反方向的索引；未来引擎必须绑定具体对象和供给/受益方向，不能仅凭“双方有记录”就发送。还应拒绝未审的非零特殊标志：贸易权 relation `+44`、转移贸易 relation `+40`。支持独立需重新读取当前 overlord 与 dependency definition；不能仅把 actor/target 交换来声称另一种支持操作。

## 下一步与未纳入项

先做八类 factory/clone/command 生命周期和合法性预览；经济类使用经过单位校验的固定小额/固定比例。之后分别实现警告、包围网、支持独立及两种贸易关系的 bounded observer，再做正向、合法取消、存档和新进程重载。赠款与人情换金币需要经济分项与回复观察，单一国库差额不足以证明请求因果。

本次不纳入 scornful 定义选择器、loan 多标量时长组合、sell/charter province、condottieri/rebel/舰船对象、和平/宣战 owned 图、联盟/联邦名称字符串或未明确的 forced-trade 变体。这些仍在外交总覆盖目标内，须各自闭合，不能从本报告借用执行声明。

资源上限：最多 100 函数块、每块窗口 16 KiB / 4,000 指令、合计 128 KiB 解码、768 MiB 内存守卫。实际 83 块 / 57,247 解码字节。CFG 的间接跳转和未展开调用不代表全程序完备；无进程句柄、游戏调用、UI 或注入。

验证：生成器 `--check` 字节一致；另一路独立读取 PE，复核报告 13,398 条指令字节和 80 个 vtable 槽全部一致，并检查八类、三种 `0x48` 大小、四类禁止取消、侮辱固定 `-1`、贸易标志固定 `0` 和全部执行状态为 false。未重跑与本增量无关的 API/live 测试。
