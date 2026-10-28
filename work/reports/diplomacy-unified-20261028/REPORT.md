# 统一外交接口：测试与修复报告（2026-10-28，含实机）

## 1. 结论

- 离线：`tests.test_diplomacy_operations` **6/6 通过**；214 项行动逐项参数查询 **214/214 通过**，0 个空参数字段。
- 实机（cold product build15，PID 43212，session b535…，存档 eullm-fixtures/111.eu4，1444.12.7 FRA）：
  - 行动目录实机返回 **214 项**，route 分类完整；
  - typed 查询 `subject.divert_trade` 参数校验通过；
  - **preview 修复生效**：build15 `no_send=false`，preview 在发布前返回 ToolError，未产生请求，owner 保持可用；
  - **production 普通行动 `influence_nation`（FRA→BRI）成功**：sequence 1，status=submitted，native status=4 normal_dispatch_slot_consumed，ownership_closed=true；
  - **响应读取成功**：`diplomacy_response_v32` 返回 stages，generated_decisions=[]、acceptance=unobserved；
  - **效果读取成功**：`diplomacy_effect_v32` 基线无该 opinion，执行后 BRI→FRA opinion **+25（120 月，stack 1）**，native_calls=0、requests_published=0；
  - **typed 属国 production `subject.support_loyalists`（FRA→AMG）**：sequence 2，native gate rejected（status=3，submitted=false，ownership_closed=true），写入/发布链路走通，未产生效果；
  - `subject.divert_trade` production 被永久安全 hold 拒绝（`scope_denied`，历史成功项不重跑）；复用现有证据。
- 修复 4 处：
  1. catalog 行写入 resolved `route`；
  2. `native_preview` 只对 ordinary_tag/offer_peace 为 true（独立命令不再误报）；
  3. `event.choose_governor_option` 增加 event-option effect 说明；
  4. preview/peace_preview 读取加载 build 的 `no_send`，未接通 send=0 时发布前拒绝（避免 owner 被 unknown 历史永久持有）。
- 事故与修复证据：旧 preview 尝试（PID 72316, r27）产生 `dispatch_unknown` + `CentralHistoryUnavailable` 永久 hold；该证据保留，修复后的 build15 会话不再复现。

## 2. 覆盖分组

| 分组 | 行动数 | 离线查询 | 实机/证据状态 |
|---|---:|---:|---|
| 普通经济/贸易/港口/地图/思潮/间谍/人情/教廷/神罗/列强 | 151 | 151/151 | 2 项历史 tag-host dispatched（offer_loan/influence_nation）；27 项历史证据复用；122 项离线 |
| 属国/殖民国 | 45 | 45/45 | 查询实机通过；support_loyalists 实机 native gate rejected；divert_trade/placate 复用 |
| 战争扩展 | 3 | 3/3 | 离线；本存档无战争，下一有效样本需真实战争 |
| 宣战/议和 | 2 | 2/2 | 复用 war-peace 证据（12 条款、净票、多条款） |
| 政府互动 | 3 | 3/3 | 离线 |
| 雇佣军/卖船/叛军 | 6 | 6/6 | 离线；需真实 army/fleet/faction identity |
| 朝贡回复/总督选择 | 2 | 2/2 | 离线；需真实 pending 对象 |
| 独立命令 | 2 | 2/2 | 离线 |
| **合计** | **214** | **214/214** | 见 §4/§5 |

## 3. 离线证据

- 测试：`python -B -m unittest tests.test_diplomacy_operations -v` → 6/6 PASS。
- 覆盖：`offline_coverage.py` → `offline-coverage.json`（214 行；每行参数样本、route、native_preview、effect_profile、query 结果）。
- 参数样本覆盖普通标量/贷款/省份/第三方/地图/宣称/领土/教廷，属国 45 项按 TOGGLES/FOCUS/TRIBUTE/RELEASE/CUSTOMIZE/TYPE/PROVINCE/COLONIAL_WAR/ISOLATION，战争上下文 leader 选择，总督 event/instance/option，雇佣军/卖船/叛军 low8hex_high8hex identity。
- 目录修复：route 字段、native_preview 策略、governor effect_profile_note。

## 4. 实机：cold owner build15

Host：PID 43212 / creation 01dd669e18c7a307 / session b5355527e33f7c35b82cdee23ec86fca；`v32-cold-20261022/build-15/eu4_diplomacy_cold.dll`；存档 111.eu4（1444.12.7、FRA、无战争；FRA 属国 AMG/AUV/BOU/FOI/ORL；国库 70.759，威望 8.758）。

| 阶段 | 请求 | 结果 |
|---|---|---|
| catalog | — | action_count 214；typed_subject 45、typed_war_context 3 等 |
| query | owner-query-subject-01 | subject.divert_trade 参数有效，未发布 |
| preview 守卫 | owner-preview-guard-01 | ToolError：loaded build does not connect send=0；无发布；owner 后续 query 正常 |
| production | owner-live-infl-02 influence_nation FRA→BRI | queued → submitted；native status 4，submitted=true，ownership_closed=true |
| response | 同上 | native observation 已保存；generated_decisions=[]、acceptance=unobserved、effect_completion=unobserved |
| effect | 同上 | profile_completed=selected_named_pair_opinion_changed；before 无 entries；after opinion +25 / 120 月 / stack1；native_calls=0 |
| production | owner-live-loyal-01 subject.support_loyalists FRA→AMG | queued → not_submitted；native status 3 "native gate rejected"；ownership_closed=true |
| production 拒绝 | owner-live-divert-01 subject.divert_trade | scope_denied：历史成功项永久 safety hold，未调用 backend publish |

证据文件：

- `work/reports/v32-resident-session-20261021-r28/`（op intent/reservation/result/status/native observation）
- `work/runtime/effect-observations-v1/43212-01dd669e18c7a307-.../request-6f77...2f696e666c2d3032/`（baseline + observation）
- `work/reports/v32-resident-session-20261021-r27/op-pub-d83e...error.json`（旧 preview 事故证据）
- 汇总：`live-owner-results.json`

## 5. 修复文件

- `bridge/diplomacy_operations.py`：catalog route、native_preview 策略、governor effect_profile_note。
- `eu4harness/v32_diplomacy_tools_20261020.py`：新增 `build_connects_no_send(backend)`；preview/peace_preview 发布前检查 loaded build 的 `no_send`。
- `tests/test_diplomacy_operations.py`：route/独立命令断言 + build no_send 测试。

完整精确清单见 `modified-files.txt`。

## 6. 复用与不重跑

- 历史普通行动 27 项（bridge/diplomacy_research_evidence.json）复用。
- 战争/和平 12 条款、净票规则、多条款（work/reports/war-peace-connectivity-20261027/war-peace-results.json）复用。
- subject.divert_trade / placate_rulers 复用；divert_trade production 再次被 safety hold 拒绝，未重跑。
- 本次两条 production 使用新 request_id；旧 5 个 demo 请求与 unknown 请求未重放。

## 7. 下一有效样本

1. 在 `no_send=true` 的 build 上测试 preview/peace_preview；当前 build15 只允许查询+执行。
2. typed 属国：选一个未被历史 hold 且原生 gate 允许的 action（support_loyalists 已被 gate 拒；需按当前 subject type/ability 选择）。
3. 在当前 owner 上推进一天或等待 AI 回复，读取 influence_nation 的 acceptance/reply；不重发。
4. 战争扩展：加载真实战争存档后，typed production 各测一次 call_to_arms/intervene_in_war/enforce_peace。
5. 保存/重载效果持久化：另一次集中回归，不在本次声称。

## 8. 提交整理

提交清单补齐 HTTP facade、统一行动去重源码和原交接材料，共39项。results.json 的主统计与逐行动状态已同步 cold owner 结果；原 tag host 记录标为历史。当前214项中：31项复用历史证据、180项离线校验、1项派发、1项新实机效果、1项原生条件拒绝。

测试已开始，下一轮直接使用真实战争、有效属国能力、部队/舰队/叛军身份及pending事件开展分组测试。预览需先补 release build 的 send=0；总督选择需补效果关联。
