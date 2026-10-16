# v11 受限研究 HTTP

`tools/serve_diplomacy_lab_v11.py` 固定绑定 v11 protocol、purpose、DLL、14 个 native source、manifest、fixture profile 与 PID/creation。它复用 [研究 HTTP 的持久幂等规则](diplomacy-lab-http.md)，不注册生产 EU4PAIR/1 backend。

**v11 的运行验收已失败并冻结。** PID40176 / creation `01dd5692d472900c` 的无发送 lifecycle 前 14 个家族完成，第 15 个 `form_coalition` 未通过 factory 默认字段合同；整个 lifecycle 阶段失败，preview/command 均未开始，pair/fixture 请求数均为 0。已有源码、DLL、manifest 和宿主保持冻结，原会话不能恢复或重试。以下路由说明保留为该版本的接口合同，不表示存在可发布请求的 v11 会话。失败摘要见 `work/runtime/native1375-v11/failed-lifecycle-summary-40176.json`；它不新增能力索引的十四种历史效果。

```text
python tools/serve_diplomacy_lab_v11.py --pid <PID> --creation <16位小写FILETIME>
```

仅 `127.0.0.1`，默认端口 `8768`，必需 `EU4_LAB_HTTP_TOKEN`。GET 路由是 `/research/v11/capabilities`、`/research/v11/status`、`/research/v11/requests/{sequence}`；唯一 POST 路由为 `/research/v11/pair`。请求仍严格为 `protocol/pid/creation/sequence/mode/action/actor/target/ttl_ms` 九个字段，不能提供路径、指针、地址、脚本、事件、任意 TAG 或原生参数。

候选白名单为 36 项：原 v10 的 24 项，加 `warn`、`insult`、`form_coalition`、`leave_coalition`、`support_independence`、`cancel_independence_support`、`request_trade_power`、`cancel_trade_power_transfer`、`steer_trade`、`cancel_steer_trade`、`send_gift`、`trade_favors_for_gold`。接口分别允许 `legality_only/submit`；TAG 限 FRA/ENG/POR/NAV/FOI，submit actor 只能为 FRA。预检由 v11 独立的 20 个 lifecycle、72 个 preview 和 72 个 command case 守卫；候选存在不代表当前构建或会话已完成预检。

下列参数由候选编译时固定，发现响应会显示，但请求不能传入，即使值与固定值相同：

| 动作 | 固定参数 |
|---|---|
| `send_gift` | `amount="25.000"` |
| `insult` | `index=-1` |
| `request_trade_power` / `cancel_trade_power_transfer` | `fraction_milli=500` |
| `give_subsidies` / `cancel_subsidies` | 每月 `1.000` 金、`duration_years=10` |

没有 fixture、speed、阶段、加载或重置路由。序号必须由调用者显式指定为下一条；HTTP intent 永久保留。重复相同 POST 只读既有状态，不刷新 TTL、不再次发布。未知结果阻止后续发送；native completion 也不能绕过最新暂停、lease、world/thread 和 heartbeat 守卫。

v11 `input_wait_pending` 单独显示原生尚未取得文件句柄时的有界等待，期间 `pair_publication_ready=false`。该等待只属于原生 pre-handle 共享冲突处理，不授权 HTTP 重发，也不允许重试已经 claim 的操作。

`http_pair_contract.actions` 描述 36 个研究候选入口，历史状态效果仍由独立证据索引决定。`v11_candidate.runtime_verified=false`、`live_readiness=null`、`research_only=true`、`production=false`；没有证明严格单人来源或可靠世界代次。路由、runtime 依赖和 durable intent kind 与 v9/v10 分离。

验证命令：

```text
python -m unittest bridge.tests.test_diplomacy_lab_http_v11
```

测试仅使用合成临时邮箱，涵盖 36 项两种模式、固定参数拒绝、版本隔离、永久幂等和未知结果、暂停/lease/等待守卫。没有监听 socket、访问游戏或发布真实请求；此文档不构成实时验收。
