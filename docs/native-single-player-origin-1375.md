# 1.37.5 单人来源静态研究

本轮找到了从前端单人选择到运行 server 配置的具体数据流，也找到了多人分类器返回 false 的确定分支反例。**严格单人、当前世界来源、不可加入的会话模式仍未证明；生产后端仍不能据此启用。** 本轮没有读取进程、调用游戏、注入或修改冻结的原生文件。

构建限定为 `9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A`。可复现脚本是 `work/trace_single_player_origin.py`，报告是 `work/reports/native-single-player-origin-1375.json`，报告 SHA256 为 `0622c8a67f085984db81aa3c5d2e15675ded40f8466bc7b41643b10ca10a7788`。报告检查 19 个函数、95 个指令锚点、4 个虚表槽、6 个字符串和 1 个导入符号；总解码 41,706 字节，报告 1,183,529 字节。每个入口限定 16 KiB / 4,000 条指令，总预算 256 KiB，内存上限 768 MiB，不自动跟随调用。较大函数的片段不被声明为完整函数或完整写入者集合。

## 已闭合的数据流

| 环节 | 磁盘证据 | 可以得出的结论 |
|---|---|---|
| 单人按钮 | `10eb670` 把 `10f03b0` 回调绑定到 `single_player_button`；`10f03cd` 写 `game+747c=0` | 0 是这条前端单人选择路径的值 |
| 多人按钮 | 同一构造函数把 `10f0510` 绑定到 `multi_player_button`；`10f0564` 写 `game+747c=1` | 该字段含前端模式选择；不是不可变的世界身份 |
| 前端控制对象 | `10d23c0` 安装虚表 `1d5a8c8`；`10d2542` 初始化 `(controller+400)+2e8` 的 WORD 为 `0001` | 小端两个配置字节默认是 `(1,0)` |
| 单人 Play 路径 | `1120dd0` 检查模式 0；`1120fed` 写临时配置 WORD `0001`，`1121004` 调用 `ad6a70` 复制到 `controller+400` | 一条实际启动路径明确重设 `(1,0)`，并在尾部设置 `controller+715=1` |
| 网络相关路径 A | `10f7709` 写 WORD `0100`，复制到同一配置，`10f777a` 写模式 2 | 配置 `(0,1)` 与密码 / 会话路径关联 |
| 网络相关路径 B | `10f7f8a` 写 WORD `0101`，复制到同一配置，`10f8601` 写模式 1 | 配置 `(1,1)` 与 private-checkbox / password 会话路径关联 |
| 转为运行 server | `10da520` 检查 `controller+715`，把 `controller+400` 作为第 5 个参数传给 `803270` | 前端配置被带入运行 server 构造 |
| 运行配置 | `803270` 安装 `1cb8460`，把上述参数复制到 `server+1708`；`80b4c0` 明确复制 `+2e8/+2e9` | 两字节最终位于 `server+19f0/+19f1` |

第 5 个参数的位置经过 x64 栈布局核对：调用方写 `[rsp+20]`，callee 入口后位于入口 RSP `+28`；callee 的 `rbp=入口RSP-388`，读取 `[rbp+3b0]` 正好对应它。不能把这个复制链误读为另一个栈参数。

`ad6a70` 是两个配置字节的赋值路径；前端 `1102e00` 也会把两字节复制出去再写回。因此它们不是只读的原生 epoch 或不可变的模式封印。A/B 与 client/host 的角色对应目前是基于 UI 和模式分支的推断；报告没有将其提升为覆盖全部平台的 enum。

## 为什么现有检查会误判

`6eaa10` 的第一步是调用对象虚槽 `+318`。对运行 server 虚表 `1cb8460`，该槽为 `80ff80`，读取 `server+19f1`。但即使这个字节为 1，函数仍可能返回 false：只要 context `+54/+55` 至少一个非零，且 `game+a50` 玩家链为空，或链上所有 DWORD `node+18` 都等于 context `+8c` 的本地 ID。链的 next 位于 `+60`。这是精确的控制流反例；本轮没有实测相应网络会话可达性，不将其写成已观察到的 MP host。

另一个反例是对象类型：前端控制对象虚表 `1d5a8c8` 的 `+318` 指向 `8f450`，后者无条件返回 false。两个虚表的 `+80` 都指向 `811aa0`，读取 `object+330 -> holder+370`。因此“能读取 context，且分类器返回 false”仍不能证明读到的是运行中的单人 server。

运行 server 构造链没有依据这两个配置字节改用一个专属于 SP 的虚表。现有 transport 虚表 `1d96178` 的构造入口是 `157ffe0`，先调用公共构造 `1575350`；仅核对它的地址也没有 SP 排他性证明。

还有一个容易混淆的分支：`1120dd0` 在 Steam 可用且前端模式为 0 时仍会构造名为 `LobbySession` 的配置。IAT `1b676e8` 经 PE 导入表确认是 `steam_api64.dll!SteamAPI_IsSteamRunning`。有 Steam / LobbySession 对象不等于多人游戏；相反，没有远程玩家也不等于会话不可加入。这里的严格单人目标是游戏会话来源和参与者约束，不是声称整个进程断网。

当 Steam / 平台回退条件成立时，Play 函数会跳过显式 `(1,0)` 配置赋值，改走 context 虚槽 `+88` 的路径。这条回退链尚未闭合，不能只凭一个初始化字段接受全部启动方式。前端模式 0 也可在当前世界替换之前被菜单操作写入；保存的 `multi_player=no` 只反映序列化分类结果，继承分类器的限制。

## 可实现的受限来源绑定

先增加独立的只读观测记录，不修改生产握手中 `strict_single_player` 的可信来源。每次记录应绑定完整 exe/DLL hash、PID/creation、线程、采样序号，并保存：

- `game+747c`、实际 `game+1e00` server 地址及虚表、`server+19f0/+19f1` 两个原始 BYTE。
- `server+330 -> holder+370` 的完整链、context `+54/+55` 原始 BYTE、`+8c` 本地 ID。
- 最多 256 个玩家节点的地址、ID、next；检测环、非法指针、越界或不稳定立即拒绝。没有读到节点不能自动解释为无远端玩家。
- 双遍身份 / 字段一致性、已独立核对的暂停状态。报告字段应叫原始字段或候选模式，不能直接改名为 `strict_single_player=true`。

后续的原生消费者可维护一个 adapter 自有的 `origin_witness`：在**已覆盖的** SP 启动入口记录 mode/config/平台分支，核对配置经 `controller+400` 复制到新 server，绑定新世界 epoch，然后在消费请求之前重查相同 origin、实际 server/context、暂停、主线程与完整 request identity。未知启动分支不产生 witness；load/reset/menu/network transition 在修改世界前撤销 witness 和所有待执行请求，失败加载也撤销，不自动重新启用。

这个设计需要先证明生命周期入口覆盖。既有 `native-world-lifecycle-1375.json` 显示同一个 game 指针内部能重置 / 读档，`+7480/+7485` 是可重复布尔，日期也可重复。稳定地址、日期、双遍快照、进程身份只能辅助校验，不能替代世界代次。当前报告因此保持 `strict_single_player_predicate_identified=false`、`current_world_origin_verified=false` 和 `production_ready=false`。

需要补齐的具体证据是：平台回退与 Continue / Load / New Game 的配置来源；context `+54/+55` 的构造和所有写入路径；配置的间接 / 批量写入及返回菜单、host/join、重同步转换；以及这些模式转换与世界失效入口的覆盖。后续动态工作可只做观察：比较新建 SP、继续 SP、平台回退、仅本地玩家的 MP host、加入与返回菜单的记录；不必发送多人外交动作。本轮没有执行这些动态步骤。

复现命令：

```powershell
python -B work/trace_single_player_origin.py --deps-dir "$env:TEMP\eu4-native-analysis-deps"
```

脚本仅加载磁盘 PE 和既有小型静态报告。未知 exe hash、缺失指令锚点、虚表 / 字符串 / 导入符号不匹配都会终止，不生成可执行权限或生产注册。
