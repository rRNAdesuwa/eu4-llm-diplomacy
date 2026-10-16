# 纯数据战争图比较状态

SOURCE-READY：核心与首次离线回执已独立源审，reviewed manifest 的四项元数据差异核验通过。当前只提供 `evaluate_graph_change(before, after, actor_handle, target_handle)` 与 `catalog()` 两个纯数据函数，没有 runtime adapter、HTTP、publisher 或游戏执行入口。

核心 SHA256 为 `c9d10067f897c2d284a9542df896906b0f71c9cb888f80d050c3715a586c4c5c`。核心零 imports，不进行 I/O、进程访问、native 调用、clock、CLI 或 source-code executor。它只验证严格、有界的 copied-view schema，并返回 `observed_data_pattern` 或 `unknown`；不能把当前状态或数据模式解释为原请求完成。

26 个新离线方法首次全部通过，0.156922 秒，tracemalloc peak1,361,717B（仅 Python 分配，不是 OS committed memory）。此后独立源审与 metadata review 均未执行候选、catalog 或重复测试；没有新增 fake、旧 suite、runtime reader 或游戏查询。首次回执 SHA `ebb79c9aec05b60952930727673792043e7d9eb58a43282610084de60a9c3b93`。

## 固定来源与审查

| 文件 | SHA256 |
|---|---|
| [reviewed manifest](source-manifest-reviewed.json) | `b0f391ab568262753f5389fb7debf25ca3f51b4102375908eb6db97372df9af6` |
| [root 独立 SOURCE-READY](../../reports/war-graph-change-oracle-root-review-20261015-r1/independent-source-ready.json) | `4838f98ca9d287bcc0f72b6444be7f91508a7ea61ab7fa1bd98e288eb0d7e06a` |
| [metadata 差异通过](../../reports/war-graph-change-oracle-reviewed-manifest-review-20261015-r1/reviewed-manifest-passed.json) | `e3689ce87bc1eb089f60b3d3faafccb7ef5eb365f287cecdc64e3f2008e5b9a3` |
| [原 draft](source-manifest.json) | `7ab9ad84b0590730c0770bfb6809a170ff7d5ef715536e8ed0c00a56eb16b33f` |
| [原 delivery](delivery-manifest.json) | `d64829229ecb3f27f83d39c2c0f09decd2a0a4023e6489f9528efe03fe557850` |

11 个 source pins 保持不变。reviewed manifest 为独立新副本，仅修改 `sealed`、`independent_source_review_pending`、`stage`、`independent_source_review`；原 draft、delivery、README、PROTOCOL、核心、tests 与首次26项回执均冻结未改。`runtime_capture_authorized`、`native_ready`、`request_effect_authenticated` 仍为 false。此 STATUS 是新增说明，不修改原交付图。

## 数据与运行时边界

新增／消失的 global 地址只表示 copied view 地址集合变化。same-address 载荷、成员或顺序差异不证明连续的同一个对象；全部字段相同也不能排除不可见 ABA。pointer/date、同 PID/creation 与 root metadata 相同均不证明未 reload、同 world epoch、atomic snapshot 或 lease。

纯数据 schema 能比较多个 opposing 地址集合。冻结 war_r2 在所选 pair 超过一场 opposing war 时严格返回 unknown；这一失败 runtime capture 不能供给多场场景，也不能被 oracle 提升。原始 capture/status 字段与 caller authority 字段不符合严格输入 schema；复制数据及 completeness 声明始终未认证。本工具没有自动转换或 runtime 接线。

所有19项 authority 恒为 false：`input_authenticated`、`current_runtime_state_verified`、`original_request_causality_verified`、`request_dispatch_verified`、`effect_verified`、`AI_acceptance_verified`、`terms_verified`、`war_creation_verified`、`war_retirement_verified`、`peace_completion_verified`、`native_ready`、`sender_authorized`、`actual_native_predicate_evaluated`、`world_epoch_proven`、`atomic_snapshot`、`lifetime_lease`、`persistence_verified`、`same_address_continuity_verified`、`authorizes_retry`。

没有宣战／议和／条款的新效果认证，也不增加15/48/44/42历史效果计数。完整输入协议见 [PROTOCOL.md](PROTOCOL.md)，已知结果读取缺口见 [gap ledger](../../reports/war-peace-result-reader-gaps-20261015-r1/gap-ledger.json)。
