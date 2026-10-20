# 三项朝贡候选纯数据判定器：作者首次验收

本候选只比较调用方提供的数据。`catalog()`列出三项候选合同，`evaluate(action, before, after, receipt)`返回`candidate_pattern_match`、`pattern_not_matched`或`unknown`。源码仅导入stdlib `re`，无文件、进程、PE、网络或原生调用路径，不导入冻结observer。没有live CLI、HTTP、dispatch或capture。

23项新unittest方法首次全部通过（0.027秒，含各方法内的子边界）；未重跑任何旧套件。运行前先固定23项源/合同pin，运行后逐项相等。唯一测试树由已审Job helper启动：累计2个进程，最终active=0，直接child已收齐，exit=0，error=null，Job峰值15,056,896 B，单进程峰值13,787,136 B；上限805,306,368 B。本次测试外层shell也已返回exit0。输出与回执保存在`offline-first-run/`，首次记录不覆盖。

## 已实现的候选比较

| 动作 | 基线 | 选定后状态 |
|---|---|---|
| establish_tributary | 双方active索引缺席，target原领主为sentinel | typed tributary_state，target领主为actor完整句柄 |
| ask_to_be_tributary | 双方active索引缺席，actor原领主为sentinel | typed tributary_state，actor领主为target完整句柄 |
| convert_tributary_to_vassal | typed tributary_state，target领主为actor | typed vassal，target仍以同actor为领主 |

两国完整句柄跨前后状态和原receipt binding保持一致；不能用TAG、slot或同地址替代。双方索引须有界、positive unique slots，并指向相同选定对象；存在对象的vtable RVA、removed byte、无序完整端点和key投影须一致。缺席不能由空字段、漏一个索引或读取失败推导。索引是全部active used entries，不是capacity；不要求读取无关对象body。对象地址可改变；同地址而key未转换不匹配。

输入identity采用原TAG会话的PID/creation/session/DLL SHA/manifest SHA字段，拒绝nonce冒名；PID为非零DWORD，creation为非零16hex。原request ID、action、双方TAG、完整binding、完整dispatch字段及审计声明逐项关联。baseline声明包含发送前、不可覆盖、intent/发布锁capture前后和journal提交前复查；这些bool仍只是未经认证的输入声明。

## 验证与来源范围

`preseal-static-check.json`只记录源码AST形状与23个方法名，不运行候选或测试。之后首次运行23项测试：三动作正侧、反向、已有依赖/错误旧领主、typed absence、对象端点/类型/removed、索引重复/边界、完整句柄代际和保留位、PID/creation、session/request错配、partial/拒绝/unknown回执、strict bool/int、提交前声明、同地址无转换与换地址转换、纯模块无运行时入口。每个evaluate断言同时要求全部authority flags为false。

合同来源为`tributary-effect-contract-20261015-r1/contract.json`（SHA d687a32748ae7674567d1bfd17b220148090b5c2eca3f9e875dd024e7bf5781f），独审findings为e3fc6d32dac17eb3d9a1f3a8eac065c2d7b2eb4a75a10880a58514e8c23ad41b。源图同时固定其10项选定来源、既有reader/profile/identity编码与已审Job helper。没有重算整个历史闭包，没有改动stable15、候选18、任何原source pin、DLL或observer。

`source-manifest.json`在首次测试前封存，`manifest.json`另固定源码、回执和本报告。`verify.py --check`仅校验这些固定文件，不导入候选、不运行测试、不访问PE或目标进程。外部独审必须以交付的manifest SHA作为信任锚；本地清单不能自行证明其真实性。

## 未闭合项

正结果仅表示自报JSON满足候选依赖子状态变化。`inputs_authenticated`、`selected_effect_verified`、`native_action_mapping_verified`、`native_ready`、`callable`、AI接受、持久化、独占因果、world lease及重发/派发许可始终false。`native_calls=0`仅描述本次纯函数，不否定输入描述的历史派发。

完整native动作→方向/key映射仍是已审候选推断；无真实host认证、原安装和原request审计重放、raw类型读取重放或source guard证明。未来host须另外处理held身份、baseline发布时序与不可覆盖、完整raw索引/端点/definition key重放、loaded profile及source前后检查。R38对应native链还需要selected pair确为C及其+0x18f0链接国家；本函数不声称全输入的完整native predicate等价。

当前没有新增实机效果、接受、持久化或运行时profile。tribute资源、mandate、费用、liberty desire、关系修正等完整副作用以及definition寿命均未验证。非匹配或unknown不表示原生拒绝、AI等待或允许重发。作者源与首次结果已固定，等待独立审查。
