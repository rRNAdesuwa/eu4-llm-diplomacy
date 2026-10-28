# 统一外交接口：静态接入 → 同一 DeepSeek 会话测试与修复

## 授权与工作目录

用户授权你在本会话完成测试和修复；遇到错误直接继续静态逆向、修改接口/原生代码并验证，无需返回 Codex 请求逆向或批准。全部新代码、日志、报告保存在 `E:\work\Programming\eullm`。只使用此可见会话，不开新代理。

先读根 `AGENTS.md`、`work/AGENTS.md`、`HANDOFF.md`，再读 `docs/diplomacy-api-completion-1375.md`、现有自动化流程和本文件。旧报告和旧 Unknown 请求保留为历史。禁止计算/验证哈希。保留现有游戏、mod、外交官和时间配置；不退出游戏；最多使用现有三个存档槽，不新建槽。每项第一次成功后记账并跳过，准备提交前仅一次集中回归。

## 本轮已经修改的源码

1. `bridge/diplomacy_operations.py`：从 UnifiedDiplomacyAPI 的现有路由和 effect profiles 动态生成逐行动目录；查询调用原 codec.validate；参数类型细节保留 typed capabilities；合并当前条件、候选列表和效果字段；统一响应 DTO 保留 generated decision、pending、delivery、reply、apply 和原始证据路径。
2. `eu4harness/v32_diplomacy_tools_20261020.py`：注册 actions/query/preview/response 四个工具，共用已有 owner，执行仍走原 submit/production，效果仍走原 prepare/effect/outcome。
3. `eu4harness/diplomacy_owner_v1_20261022.py`：接入 GET `/v1/actions`、GET `/v1/actions/ACTION`、POST `/v1/diplomacy/query`、POST `/v1/diplomacy/preview`、GET `/v1/requests/ID/response`。
4. `work/candidates/v32-parameterized-tag-1375/unified_api.py`：capabilities 行动去重并按去重结果计数。
5. `tests/test_diplomacy_operations.py`：新增离线回归，交给你运行。

Codex 本轮只读取源码与已有逆向证据，并完成 Python compile 语法检查；没有运行测试或调用游戏。现有源码是 153 普通行动 + 45 属国 + 3 幕府 + 3 当前战争 + 3 雇佣军 + 1 卖船 + 2 叛军 + 1 朝贡响应 + 1 总督选择 + 宣战/议和。按最终目录去重计数，不硬编码完成数。

## 四阶段使用

| 阶段 | 路径 | 内容 |
|---|---|---|
| 查询 | GET /v1/actions/ACTION；POST /v1/diplomacy/query `{request}` | 精确参数、类型细节、条件、候选和效果合同；纯参数查询不发送 |
| 原生预览 | POST /v1/diplomacy/preview `{request,ttl_ms,allow_writes:true}` | 普通 TAG 和 offer_peace 支持 send=0；独立新 ID，随后读 status |
| 执行 | POST /v1/prepare `{request}`；POST /v1/production/requests `{request,ttl_ms,allow_writes:true}` | 先保留 before，再使用原 owner 执行一次；开发请求仍走 /v1/requests |
| 响应 | GET /v1/requests/ID/response | AI 决定、回复传递、执行/Apply 阶段分别输出 |
| 效果 | GET /v1/requests/ID/effects 或 /outcome | 原 request 对应的 selected state、进展与证据 |

特殊 typed codecs 当前没有 send=0，目录会返回 native_preview=false；查询仍走精确 codec，执行原生 Full/Local gates。朝贡 accept/reject 继续用 confirm_tribute_action；总督选择继续用 event.choose_governor_option。其他人类收件箱手动 accept/reject 若为 demo 所需，按真实 pending command 路径补接，勿把初始外交 state 直接写成回复 state。

## 逐项接入与测试矩阵

| 分组 | 行动/路由 | 重点条件与效果证据 |
|---|---|---|
| 经济 | offer_loan、give_subsidies/cancel_subsidies、sell_province、sell_ships | 金额/利率/期限、当前船队 ID、双方财政/贷款对象、省份和舰队所有权；loan-map-civic-effects-1375 |
| 港口与贸易 | offer/ask/cancel/revoke fleet basing、embargo/revoke_embargo、steer_trade/cancel、transfer_trade_power/cancel | 双向关系与方向、贸易比例/流向；spy-trade-effects-1375 |
| 地图/思潮 | request_maps、steal_maps、knowledge_sharing、ask_knowledge_sharing、subject.knowledge_sharing | 当前地区探索位图、思潮关系和支出；loan-map-civic-effects-1375、subject knowledge 文档 |
| 吞并/合并 | annex_vassal/cancel_annexation、integrate_union/cancel_integration | 起始/取消和时间推进；dependency、进度和最终所有权区分 |
| 战争扩展 | call_to_arms、enforce_peace、intervene_in_war、threaten_war | 当前真实战争 leaders/date，参战方、停战/和平、省份；current-war-action-effects-1375 |
| 间谍 | counterespionage/stop、fabricate_claim/state、support_rebels/stop、corrupt_officials、sabotage_recruitment/reputation、sow_discontent、agitate_for_liberty、infiltrate_administration | 当前间谍网、科技、派系身份、claims、modifier 和支持关系；ordinary-claim-selected-effect-1375、spy-trade-effects-1375 |
| 人情扩展 | trade_favors_for_sailors、break_alliance_favor、return_core_favor、trade_favors_for_war_prep | 人情和水手差值、第三国断盟、受益国核心、省份归属、战争准备标志；third-country-diplomacy-effects-1375 |
| 属国/殖民国 | subject_codec.ACTIONS 全部45项；government codec3项 | 当前属国类型/ability、真实殖民国/战争；按现有 subject 系列文档和 profiles逐项 |
| 朝贡 | establish/cancel/ask tributary、subject.set_tribute、confirm_tribute_action、convert_tributary_to_vassal | 真实朝贡身份、pending tribute identity、支付数额与拒绝结果 |
| 教廷 | cardinal、crusade、excommunication 系列 | 用 curia_controller 候选绑定实际控制者；cardinal/crusade-selected-effect-1375 |
| 神罗 | HRE invitation、religious unity、unlawful territory、imperial grace、reichskrieg、freecity | 皇帝/成员/改革/宗教和当前省份；对应 docs/native effect profiles |
| 列强 | influence_nation、take_on_debt、break_alliance、intervene_in_war | 当前列强资格、影响修正、贷款消失/国库、第三国关系、战争参与 |

## 优先检查的接线点

- 运行新增离线测试一次；补真实 source API 的 catalogue/validate 覆盖，逐行动核对参数和 effect_profile，发现空项直接修正。
- 原 live registry 是一次安装；按项目现有自动化在当前可用 owner 上加载新工具，不重复 bind 或启动第二会话。release build15 与旧 research build3 的路径、协议、加载状态按实际区分。
- 查看当前 native host 是否可继续使用，绝不重放 HANDOFF 中的5个旧请求。已有成功证据优先复用，新增接口做代表性端到端，未验证行动依条件逐项推进。
- 现有 UnifiedDiplomacyAPI.submit_batch 的 test_only 普通行动限制和 resident publisher 的开发/生产路径不同；遇到 typed publication 限制定位实际调用链，直接修改，不通过换名称或丢弃字段绕过。
- 普通/特殊身份参数按真实游戏条件选择；缺条件记录具体条件及下一有效样本，不重复相同失败。
- 保持 response 的 generated decision、delivery、effect 独立；同一个 request_id 对齐各阶段。每次动作保留 prepare → execute → response → effect 的证据。

## 交付

在本目录输出 `results.json` 和 `REPORT.md`：每行动 route、参数样本、条件、旧证据/新请求 ID、执行、响应、效果、修复文件和后续项。成功清单持久化用于跳过。最后一次集中回归后整理精确文件清单；不要提交无关预存改动，不推送。无需就错误重新询问 Codex，直接完成修改与测试。
