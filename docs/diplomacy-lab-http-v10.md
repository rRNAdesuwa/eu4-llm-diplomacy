# v10 独立研究 HTTP 适配

入口 `tools/serve_diplomacy_lab_v10.py` 固定使用 v10 的 protocol、DLL、manifest、14 个原生源码和会话目录。它复用 [v9 HTTP 的传输、持久幂等和未知结果规则](diplomacy-lab-http.md)，通过内部类属性绑定 v10 依赖；HTTP 输入不能选择模块、DLL、路径或版本。v9 入口仍只有原十项，路由不互通。

```text
python tools/serve_diplomacy_lab_v10.py --pid <PID> --creation <16位小写FILETIME>
```

仅监听 `127.0.0.1`，默认端口 `8767`。必须预置 `EU4_LAB_HTTP_TOKEN`，格式和鉴权规则同 v9。所有路由前缀为 `/research/v10`：

| 方法 | 路由 |
|---|---|
| GET | `/research/v10/capabilities` |
| GET | `/research/v10/status` |
| GET | `/research/v10/requests/{sequence}` |
| POST | `/research/v10/pair` |

JSON 请求仍严格包含 `protocol/pid/creation/sequence/mode/action/actor/target/ttl_ms` 九个字段，`protocol` 为 `EU4LAB/2`。同一协议版本串不表示不同实验 DLL 兼容：manifest purpose、原生会话、加载模块、fixture profile、进程创建时间均独立校验。新请求必须通过 v10 的 12 个 lifecycle、48 个 preview 和 48 个 command case 证据及当前暂停/lease/线程/世界守卫。发送 actor 仍只能是 FRA，TAG 限 FRA/ENG/POR/NAV/FOI。

除原十项，v10 固定增加以下 14 项，共 24 个受限研究入口：

| 方向 / 家族 | 正向 | 撤销 |
|---|---|---|
| 同盟 | `offer_alliance` | `dissolve_alliance` |
| 请求军事通行 | `ask_military_access` | `cancel_military_access` |
| 给予军事通行 | `offer_military_access` | `revoke_military_access` |
| 请求驻港权 | `ask_fleet_basing_rights` | `cancel_fleet_basing_rights` |
| 给予驻港权 | `offer_fleet_basing_rights` | `revoke_fleet_basing_rights` |
| 禁运 | `embargo` | `revoke_embargo` |
| 补贴 | `give_subsidies` | `cancel_subsidies` |

补贴只使用编译时固定的**每月 1.000 金、10 年**参数。`monthly_amount`、`amount_milli`、`duration_years`、`duration_months`、`parameters`、原生字段等一律不能随请求提交，即使其值恰好等于固定值也拒绝。撤销补贴的原生绑定同样限制在该固定数值实验范围。发现响应、发布响应及已知请求状态用 `fixed_research_parameters` 显示这些值；没有推导其他金额、期限或所有现有补贴都可撤销。

`http_pair_contract.actions` 表示当前适配器的 24 项编译白名单。`history_actions` 表示绑定 v10 profile 的 24 项版本化历史入口，其中只有四个新增 positive 获得效果验收（与先前十项合计十四种效果），`v10_candidate.runtime_verified=false` 不会因存在源码、静态映射或候选构建而改为 true。`live_readiness=null`；当前可否发布须另读 status，且 POST 再次检查。所有响应保持 `research_only=true`、`production=false`、`production_backend_registered=false`、`world_generation_verified=false` 和 `strict_live_single_player_verified=false`。

fixture、速度、阶段执行、加载和解冻没有 HTTP 路由。未知结果永久保留 `.http-intent`，同序号不能重发或更新 TTL；上条 native completion 不绕过最新暂停和 lease 守卫。HTTP 不注册生产 EU4PAIR/1 backend。

离线检查：

```text
python -m unittest bridge.tests.test_diplomacy_lab_http bridge.tests.test_diplomacy_lab_http_v10
```

该组 39 项测试包含 v9 原合同回归和 v10 隔离检查；24 项两种模式均在临时目录编译并发布合成请求。测试没有创建监听 socket、访问游戏或投递真实请求。另有固定运行验收：PID46408 的 seq3 经此 HTTP 发布 `offer_alliance` FRA→POR，随后相同 POST 仅返回 `replayed=true/request_written=false`；独立观察同盟新增。`work/runtime/native1375-v10/http-alliance-submit-3-46408.json` 与固定 experiment summary 绑定该次记录。其后该会话在未 claim 的 seq13 冻结，由监督器终止；不能将这一条 HTTP 运行验收推广到全部 24 项，且未验证保存/重载。
