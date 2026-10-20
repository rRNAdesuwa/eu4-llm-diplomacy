# 脚本建立附庸与休战来源（1.37.5）

静态可行的固定测试效果为在 FRA scope 中执行 `vassalize = NAV`，前提是已核验的
基线中 NAV 存在、独立、与 FRA 无同盟且双方无休战。`create_vassal` 另有释放国家和
转移省份的流程，不能作为这个效果的同义词。尚未运行新夹具；取消附庸前必须重新
只读核验关系类型、双方完整 handle 和双方休战。

工具 `work/trace_vassal_effects.py` 只读精确版本磁盘 PE 与两个 stock 脚本，
`--check` 可重现 `work/reports/native-vassal-effects-1375.json`。
EXE SHA256 为 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`；
报告 SHA256 为 `3c47d50e9bda8ced0933f61f4490f9347a9e133e74e7afcfb9f6807311d8eed6`。
范围为 17 个有界函数和 8 个精确代码块，共 17,384 字节指令，没有整段大工厂反汇编。
报告不把有界子图当作所有递归调用的完整证明；全部 `runtime_verified=false`。

## 目标与类型解析

stock `missions/Brunei_Missions.txt:133–142` 在确认 SUL 存在、自由或朝贡后，直接
`vassalize = SUL`，提供了对已有国家执行的 primary 用法。

| 环节 | 静态证据 |
|---|---|
| token / 工厂 | `vassalize=0x2758`，工厂 `0x5dec50` 的 case `0x5dfbdb` |
| 对象 | `0x68` 字节，ctor `0x5de510`，vtable `0x1c9e7a8` |
| 目标 | scalar parser `0xdd4e60` 调 `0x286120`，完整 handle 保存于 `+0x38` |
| 固定 TAG 读取 | slot `+0x98 = 0xdd50b0`，返回 `+0x38`；动态 scope 使用另一个分支 |
| 类型 | ctor 把 String32 `+0x40` 初始化为 `vassal` |
| 实际执行 | slot `+0x78 = 0xdd9370` |
| 类型查找 | `0xdd9eb0 → 0xb23df0`；定义必须通过 `0xb22380` 的 potential-overlord predicate |
| 关系创建 | `0xdd976c → 0x4e5630`，RCX=definition，RDX=当前 scope 宗主，R8=目标附属国，R9=当前日期地址 |

`+0x60` 和 `+0x61` 分别由 `keep_liberty_desire`、`message` 解析，默认都是 true。
它们不能解释为“不要休战”开关。该 scalar 夹具不添加推测参数。

`0x4e5630` 会处理已有附庸和其他外交关系，构造新的 dependency 时写
`+0x40=definition`、`+0x10=overlord`、`+0x18=subject`、`+0x20=传入日期`，注册后
调用 `0xa5ff20` 更新关系。因此这不是无副作用的单字段设置。固定测试必须使用审查过的
独立 NAV 基线，不能把已经附庸的 positive save 再作为同一个夹具起点。

## 同盟清理会带来休战

关系创建的清理循环在 `0x4e6581` 调 `0xa68d90` 查找已有同盟；没有同盟对象时跳过
这条删除分支。有同盟且 `0x2f1620` 返回 true 时，`0x4e65e2` 调同盟删除
`0xa5d790`。`0x2f1620` 开头明确将“当前国家的 overlord 等于另一国家”判为 true。

`0xa5d790` 在 `0xa5d8b3`、`0xa5d8e0` 调 `0x3eb120` 处理两方向。
`0x3eb120` 按已有到期日与配置比较，条件允许时写双方 relation：

- `+0x34`：当前日期，写入点 `0x3eb2b8 / 0x3eb337`。
- `+0x24`：算出的休战长度，写入点 `0x3eb2e2 / 0x3eb375`。
- 调用 `0xa675b0`，由 `0xa6763d..0xa67681` 计算到期日并更新 `+0x45 & 1`。

这闭合了一条“同盟被附庸化清理后产生休战”的原生链。它可以解释现有夹具先建立同盟
造成的现象，但静态链不是某个 live request 的因果审计。没有同盟只保证跳过这条分支，
不能从部分调用图证明任何其他世界状态都绝不会带来休战。

后续 v9 候选仅把 `llmt.1` 中 `create_alliance = NAV` 替换为
`vassalize = NAV`，保留原增益、好感与空 OK option；`llmt.2` 只撤增益，不承诺撤销
附庸。这是单独标注的测试准备条件，不应与正常外交请求的接受、拒绝和取消验证混同。

## 为什么不用 `create_vassal = NAV`

`create_vassal=0x27a9` 进入 case `0x5e05a1`，构造 `0x40` 字节对象，
vtable `0x1d240f8`，apply `0xddbbe0`。它调用 `0x36d120` 取得可释放对象列表，要求
目标 slot 出现在其中，再从目标核心省份中筛选当前国家拥有和控制的省份，调用
`0xa87a00` 后建立 `vassal` 关系。另有 rebel 特例。

stock `common/rebel_types/nationalist.txt:278` 的 `create_vassal = REB` 与这种
释放流程一致。本报告不将它泛化为把任意独立国家无条件改成附庸的入口。
