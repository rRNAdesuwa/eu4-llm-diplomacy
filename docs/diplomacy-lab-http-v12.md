# v12 独立研究 HTTP

`tools/serve_diplomacy_lab_v12.py` 使用 `/research/v12`，默认 `127.0.0.1:8769`。它独立绑定 v12 protocol、purpose、14 个 native source、DLL、manifest、fixture profile 和 PID/creation。端口与路由的存在不表示当前可发布请求；PID17676的固定20/72/72无发送预检和后续完整终止会话的六项效果已分别审核；这些历史记录不授权当前会话或后续请求。

接口形状及固定参数沿用 [v11 研究 HTTP 合同](diplomacy-lab-http-v11.md)：36 个固定 ID、`legality_only/submit`、actor/target 限 FRA/ENG/POR/NAV/FOI、submit actor 只能是 FRA。赠款 25.000、贸易份额 500、侮辱索引 -1、补贴每月 1.000 金/10 年均由原生候选固定，外部不能提供或覆盖。没有 fixture、speed、阶段、加载、任意事件或重置路由。

GET 路由为 `/research/v12/capabilities`、`/research/v12/status`、`/research/v12/requests/{sequence}`；唯一 POST 为 `/research/v12/pair`。生产 `/v1`、EU4PAIR/1 后端和白名单保持不变，生产可执行动作仍为 0。

能力查询的 `v12_candidate.runtime_verified=false`、`live_readiness=null`。独立字段 `historical_preflights` 可返回本版本 `historical_preflight_passed=true`，绑定准确PID/creation及固定prefix；不是实时ready，也不宣称每个合法性case都允许。共享历史现含 v5/v6/v7/v8/v9/v10/v12 的二十种指定状态效果。v12六项效果另由完整已停止会话绑定；五项关系有保存/冷重载一致性，赠款只确认同日25.000差额。候选默认标志表示不可据此推广为整个版本已验证，不能覆盖逐实验的历史证据。v11 PID40176 在第十五个 lifecycle 家族失败冻结，不能用于 v12 阶段证明或作为可重试会话。

v12 目标矩阵保持 20 lifecycle、72 preview、72 command cases。新增的 lifecycle 诊断严格区分 factory、clone、retained original：成功记录三组均须 checked=true、默认 state 为 coalition2/其余0、failure mask 为整数0。三组诊断本身只验证工厂默认值和克隆保留值。另有独立静态报告闭合正常 AI 构造和拥有所有权的入队链：`12b860` 写 coalition `+34=2`，经 `129b60→4e9930`，clone 保留该值并进入 `owner+a68`；取消只将 value 置 false。因此候选对准确 token `2de0` 的初始化和检查使用2，其余19族仍为0。该证据不是人类 GUI 点击回调的证明，也不证明最终 dispatch、效果或 DLL 运行通过。报告为 `work/reports/native-coalition-queue-1375.json`，SHA256 `b36c788c3eeb589abaa208df83cb3f97bf3697023188149588b41bb60dde5b65`。八类的条件性效果计划见 [v12 验证顺序](native-v12-extension-test-plan.md)。

宿主候选已有 39 项离线测试通过，生成器检查冻结的 v11 输入及 fixture v3 字节不变；遇到 v12 build、DLL 或 session 后拒绝更改候选。详情见 [宿主候选说明](../work/candidates/v12-host-review/README.md)。本次准备没有启动监听、访问游戏、编译/加载原生 DLL 或发布真实请求，不能将离线测试计为原生预检通过。

固定预检摘要/日志/manifest和37个新增引用的范围、哈希及失败降级语义见 [能力索引](diplomacy-research-capabilities.md#v12-固定无发送预检)。HTTP只在purpose和36-ID合同完全匹配时返回该阶段历史；v9/v10/v11不得借用。研究别名不会追加到274项目录，也不证明角色分支都实际生效。

## 固定终止会话的历史效果

正式离线审核 `work/runtime/native1375-v12/experiment-summary-17676.json` 绑定203项输入、97个session文件、全部28个序号及六次pair提交，完整日志1774777B/SHA `2e4ddef6c8ae1cdc95c52504da737f50c1ec409d31999131c1ba655008c57e10`。六次为seq3贸易权、10取消贸易权、13引导贸易、16赠款、19取消引导贸易、22警告；fixture、速度租约和纯合法性请求不计入外交提交或效果。

seq3的HTTP首次发布、只读status和同体重放证据已纳入该完整审查，重复POST为`request_written=false`；HTTP返回本身仍不证明应用效果。独立关系观察及保存/重载才支持五项选定关系结论。赠款只支持同日FRA −25000 / POR +25000 milli和选定favors不变，没有赠款保存/重载或请求因果声明。

`history_actions` 用明确协议别名映射筛选目录行：`request_trade_power`返回唯一的`transfer_trade_power`目录条目，取消独立支持的两种目录角色仍无效果证明。准确purpose和有序36-ID预检检查不变，`live_readiness=null`、生产执行0不变。完成状态也不授权立即并行发布下一请求，必须重新验证最新健康暂停帧及全部序号/租约守卫。
