# v10 外交扩展候选：同盟、通行、停泊、禁运与补贴

这是一份离线设计，尚未实现或运行新的 v10 DLL，也未修改冻结的 v9。适用 EXE SHA256 为
`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。
可重复证据位于 `work/reports/native-pair-extension-v10-1375.json`，由
`python work/trace_pair_extension_v10.py --check` 核验。报告包含 89 个有界函数/代码块，
总计 81,394 字节；不读游戏进程、不调用原生方法、不遍历整个代码段。

## 范围和方向

这五组行为实际需要七种原生动作，合计十四个正反 ID。请求通行与授予通行是不同 family，
不能靠交换展示名称或只翻转 `value` 混用。

| value=true / value=false 的公开 ID | 原生 family / token | 大小 | 虚表 RVA | actor → target 的含义 |
| --- | --- | --- | --- | --- |
| `offer_alliance` / `dissolve_alliance` | `allianceaction` / `0x293d` | `0x40` | `0x1c80720` | 提议/解盟的一方 → 另一盟友 |
| `ask_military_access` / `cancel_military_access` | `milaccess` / `0x2943` | `0x40` | `0x1c7fb70` | 请求/持有通行权的一方 → 授予国 |
| `offer_military_access` / `revoke_military_access` | `offermilaccess` / `0x2944` | `0x40` | `0x1c7f580` | 授予国 → 使用通行权的一方 |
| `ask_fleet_basing_rights` / `cancel_fleet_basing_rights` | `fleet_access` / `0x2dd6` | `0x40` | `0x1c7ef90` | 请求/持有停泊权的一方 → 港口国 |
| `offer_fleet_basing_rights` / `revoke_fleet_basing_rights` | `offer_fleet_access` / `0x2dd7` | `0x40` | `0x1c7f1f0` | 港口国 → 使用停泊权的一方 |
| `embargo` / `revoke_embargo` | `embargoaction` / `0x293e` | `0x40` | `0x1c80310` | 发出禁运的一方 → 被禁运国 |
| `give_subsidies` / `cancel_subsidies` | `warsubsidy` / `0x2a25` | `0x48` | `0x1c7ed30` | 付款国 → 收款国 |

`break_alliance` 和 `break_alliance_favor` 是带第三国参数的另一组动作，不属于本轮。
舰队停泊的费用由原生规则计算；没有在这两个 `0x40` 动作里发现外部传入金额的额外字段。

## 构造、预览和所有权

七类都经工厂 `35d210(token)` 创建。它们都有普通 pair 字段：actor `+10`、original `+18`、
recipient `+20`（完整 64 位国家 handle），date `+28`、last-command-date `+2c`、envoy `+30`、
state `+34`、value `+38`、id `+3c`。工厂初始化 marker `+8=0x165`、无效国家 handle、
envoy `-1`、state/id `0`、value `true`、`+39=0`，日期默认值在公共尾部 `360453` 设置。
原生适配器应保留工厂分配，再填独立临时动作；不能把外部地址、任意 token 或自行拼接的对象传入引擎。

本轮所有 `vtable+e0` 都是 `4e99d0`，只写 `value` 字节。没有间谍网那种需从当前任务绑定外交官的
特殊 setter。这里没有证据要求取消时填已有 mission envoy ID；其余默认字段仍按正常外交命令初始化。
取消前须核对相应关系及方向，不能把“找到了任意双方关系”当作可撤销己方协议。

预览仍使用公共 `4e9d00(action,null,false)`，并保留类专属 `+80` 合法性与 command gate。
检查必须在已核验的游戏线程、身份/世界/审计守卫之内。原生拒绝是合法结果，不等于测试基础设施损坏。
本轮尚未进行七类的临时对象生命周期、预览或封装实测，旧五类的成功不能替代这一步。

`vtable+40=4e9930` 为七类共同的 command wrapper，`+b0` 克隆函数分配不同对象；command `+50`
持有克隆，原动作由调用方独立持有。clone 会复制 pair 标量，并将 `+2c` 初始化为源 `+28`；wrapper
随后按当前游戏日期更新 clone 的命令日期。七类 `+a8` 都是恒 false 的 `8f450`，因此 command 析构
采用普通独占克隆路径。六个 `0x40` 类使用析构 `129450`；补贴使用 `129500`，按 flags 释放 `0x48`。
七类的派生 clone 均未发现拥有堆资源的指针或字符串字段。

下一版须沿用已审的所有权边界：完成 wrapper 后核对 clone 不同于原件；原件可以独立销毁；未进入
submit 时由调用方清理明确持有的 command；进入 submit 或发生所有权异常后，不能再次析构可能转交的
command/clone，也不能自动重试。`context_submit=true` 仅是投递记录，不能当作效果证明。

## 补贴参数的单位修正

补贴有两个额外 DWORD：

| 字段 | 原生表示 | 直接证据 |
| --- | --- | --- |
| action `+40` | 每月金额，带符号整数，1 ducat = 1000 | parser `5494cb`，clone `54935e/549361`，UI 提交 `1499ce5/1499cf2` |
| action `+44` | 年数，带符号整数 | UI 提交 `1499cf5/1499d02`，到期函数 `a62e14` |

UI 构造 `14999ca` 默认 10，标签在 `14999f1` 明确为 `YEARS`。两个按钮
`149a6ea` / `149a96a` 分别加减 10，限制到 10–400。点击提交直接把 dialog `+2b4` 写入 action `+44`，
没有乘 12。持久补贴的到期检查是 `start_raw_date + duration * 0x2238`，与 UI 的年数一致。

**当前目录 `give_subsidies.duration_months` 不能直接绑定 `+44`。** 候选方案是显式迁移为
`duration_years`，研究版本先接受已证实的 UI 范围和步长。如果保留旧 API 字段，必须明确执行受检转换；
不能把 12 个月当成 12 年，也不能悄悄截断不足整年的请求。本报告没有更改共享目录或生产 API。

金额应通过精确十进制转换为千分单位，检查小数精度、带符号 32 位溢出以及研究实验额外限额。
原生 UI 的 money slider 0–100 是百分比：它将 country `+bb0` 除 1000、滑块除 100，再换回千分单位。
该滑块数值不能直接当金额写入动作。`548c50` 在特定 actor predicate 成立时拒绝 `<100` 的内部金额
（即 `<0.1`）；本报告不把该 predicate 擅自命名为严格单人/当前玩家判定。这个合法性函数没有直接检查
`+44`，因此不能指望预览替 API 校验期限。10–400 是原生 UI 范围，不等于已证明的全部引擎合法域。

## 回应和只读验收

正向同盟的 `+d0=50f120` 返回 value，四种正向通行/停泊动作的 `+d0=51fa90` 返回
`state==0 && value`，所以要走正常的 AI 接受/拒绝流程。禁运和补贴的 `+d0` 恒 false；取消模式也不要求
该回复。适配器不能强制把 state 设为接受，不能用无消息推断拒绝。

已闭合、可供后续观察器使用的起点：

- 禁运：actor 的 target 关系记录 `+46 & 0x02`。`a6fe20` 清除该掩码再写入 `bool*2`；另有 dirty 标志，
  不能混同。取消使用同一方向，观察另一方向不能证明己方禁运已撤销。
- 补贴：索引 root `+110` / DWORD count `+11c`，16 字节 slot/object 项；对象虚表 `1c815d8`，
  大小 `0x48`，payer `+10`、payee `+18`、start `+20`、removed `+28`、amount `+40`、years `+44`。
  同一对象在双方索引注册。取消调用 `a62f80` 清双方索引并标 removed；因此取消守卫还须确认完整 payer/payee
  handle，不能只检查对方 slot 存在。
- 军事通行 getter `a68fb0`：root `+b0` / count `+bc`；舰队停泊 getters `a694c0` / `a69660`：
  root `+e0/+ec` 与 `+f8/+104`。这些只闭合了索引起点；完整关系虚表、方向和接受状态尚需补证后才能
  宣称效果已观察到，不能把自动/条件通行当成显式外交协议。
- 同盟可复用已证实的 root `+80/+8c` 索引起点。解盟会涉及休战等原生副作用；不能假设“建立再取消”回到
  完全相同的基线世界。

## 可编码的下一步

1. 在新版本中加入不可由请求修改的七类常量表和补贴 `0x48` 布局；先只做构造、填参、clone、独立析构测试。
   补贴测试必须实际复制非零 amount/year，避免只验证两个默认零值。
2. 以固定实验国家做七类 × 正反 × 两组国家的 28 项无发送预览/command gate。所有权、日期、原件/clone字段和
   析构均核对；false gate 是普通结果。新 family 未通过这一轮前不开放提交。
3. 分开验证请求和授予方向；先补全通行关系观察器与正常 AI 回复关联，再逐个发送、只读确认、保存并重载。
   禁运先比较精确方向的掩码；补贴比较完整关系、数额、年数和到期信息。
4. 固定单次补贴实验金额/年数和独立基线；只有参数单位与付款方向闭合后，才将更多参数暴露给外部接口。
   新实验仍需独立版本/会话、持久 claim、TTL、线程/世界失效守卫以及未知结果冻结。

本轮完成的是构造和参数工程的静态依据，不是七类动作的运行验收。报告所有 `runtime_verified` 与
`execution_verified` 保持 false，生产后端能力不变。
