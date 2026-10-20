# v14 十方向实验：独立停止会话审核候选

此目录仅有离线审核逻辑、空模板和合成测试。没有真实 case、真实审核结论、游戏读取、构建、安装、请求或能力升级；任何实际 case 由 root 完成最终账本、停止审计与固定哈希后另行 CREATE_NEW。不会扫描日志猜序号、最近一次合法性、效果或保存重载。

固定 PID 18356 / creation `01dd56aa6f724ea8` / frame thread 47264 / world `0x221c8dac040`；这些字段不证明 world epoch。固定 v14 DLL `abfb2e343f7e7332efa96c45b1dd2b89c00ac2b4085cbd9fc32e8f90db299296` 与 manifest `aa09084d3d1d7c9adff164b67356d72e2c511b519e79b382e7bc54a80c96ec75`。没有改动冻结 host/native、旧 reviewer、observer 或共享接口。

## 继承与增量

从 `work/verify_v12_experiment_1375.py` 借鉴连续账本、完整停止目录、host-intent/native claim、状态精确日志前缀、所有权与独立监督器规则；没有运行或导入 v12 宿主，没有复制其六动作保存匹配器。新版新增：

- 重放已冻结 directional preflight reviewer `25deb003…478a90`，包括精确 BridgeStart `0x59c0`、20 / 1 / 72 / 72、owned-peace 九条 core、持久 wrapper、后续健康帧、真实阶段 claim、两份 held-RO 身份。默认空 offer 不代表白和平、战争身份或议和发送。
- 每条尾部 frame 都验证完整原生 schema、严格 JSON 类型、身份、序号、日期单调、阶段与 lease；不会因阶段证明已缓存而跳过尾部。
- 每个 pair begin / dispatch-intent / complete 都检查 typed 字段、五项固定参数、所有权、phase、exception、freeze 与无重试。原生返回和消耗所有权不等于 AI 接受或状态生效。
- 每次 submit 必须由显式 `legality_sequence` 绑定紧前一条同 action/actor/target、同游戏日期的成功 legality-only。不能用最近一次或相似参数猜匹配。submit 自身的原生 preview/gate 也必须通过。
- 完整 speed 证据必须有固定 12 秒独立监督器的 armed/complete、原生运行和自动暂停回调、durable pause claim、暂停读回与独立最终状态。缺失、终止、异常或未知不能重投或被略过。租约触发阈值不是无条件实时保证。
- 每个十方向 submit 都须显式提供观察比较，成功或 unknown 皆须账本明示。使用冻结 observer `acb38546…ce1496`，先验证其 contract/dependencies，再独立重检每一遍完整原始状态和 canonical typed 比较；actor/target/full handles、vt、角色、removed、同日和补贴起止规则保持原合同。

十方向为 dissolve_alliance、cancel_military_access、revoke_military_access、offer_fleet_basing_rights、cancel_fleet_basing_rights、revoke_fleet_basing_rights、embargo、revoke_embargo、give_subsidies、cancel_subsidies。普通联盟、ask access、offer military 等 setup 请求仍完整审核，但不借十方向比较器新增它们的效果结论。actor 固定 FRA；target 由请求白名单和观察绑定共同限制。

UI 拒绝只能保存为 `root_ui_annotation`、`native_evidence:false`；不作为原生拒绝或 AI score 证据。缺失关系不等于拒绝。当前 `persistence` 必须为空数组；不推断保存重载，也不把其他版本的 matcher 用到新方向。

## 文件与有界读取

`pins.json` 固定 36 个依赖，包含 frozen v14 宿主/共享代码、监督器、观察器证据合同与依赖、前缀 case/summary、独立复审、DLL/manifest。正式审核先对 case 的全部 artifact 读取上限内字节、核 size/SHA，再解码；最多 512 文件、每件 8 MiB、总计 64 MiB、case 512 KiB、请求 128、选择路径深度 6、JSONL 行 16 KiB。所有路径为仓库内规范相对路径，拒绝链接、junction、重复路径、目录逃逸。结束再次逐文件核 bytes 与代码依赖。

完整停止 session 目录的每一项都必须在 `session_files`；无法藏住 request、孤立 claim、未解释意图或额外文件。允许本轮 CLI 与受监督 speed，不支持 HTTP receipts 或外部未审核协议。审核仅在临时目录重放已经哈希冻结的字节。

## 显式 case 合同

`prepare.py --template <new.json>` 只 CREATE_NEW 一个 `finalized:false` 空模板，不寻找当前游戏或日志。root 准备最终 case 时明确填写：

1. `inputs`：任意稳定 key → `{path,size_bytes,sha256}`；每个输入都必须实际使用。包含完整 session、独立 captures、两份 preflight 固定记录及其中 11 项输入、exit 与 stopped audit、选定方向 before/after/comparison。
2. `exit`：`{input,select}` 指向原始 held-handle exit 对象。要求同 PID/creation、FILETIME、游戏 full SHA、read-only、wait/exit_code 0、正常退出且 observer 未发出终止请求。
3. `stopped_audit`：指向 root 明确冻结的新投影 `{pid,creation,process_exit_filetime,complete_log,session_files,stopped:true}`。`complete_log` 为完整日志 descriptor；`session_files` 是文件名→descriptor，须与 case 和最终目录逐一完全匹配。该投影不替代原始 exit 证据，也不宣称签名认证。
4. `preflight_case` / `preflight_summary`：输入 key，路径分别固定为 directional-preflight-case-18356.json / directional-preflight-summary-18356.json；初始不可变前缀 162394 bytes、SHA `d255e57d97bc20deefd11a3475cc81883d4cf182852ed774fa39cb183f98595d` 必须是完整日志的原字节前缀。
5. `requests`：每项精确 `{sequence,request,outcome,legality_sequence,publication,status}`。request 精确含 operation/mode/action/actor/target/speed；sequence 必须严格 int 且连续 1..N。outcome 仅 dispatched、legality_allowed、legality_rejected、guard_rejected、fixture_callback_returned 或 completed_and_paused。非 pair-submit 的 legality_sequence 必须为 null。
6. publication/status/final_status 都用 `{input,select:["report"]}` 引用已保存 `one_explicit_v14_cli_capture`，要求 exit_code 严格 0、stderr 空、automatic_retry/applied false。speed publication 的 report 为监督器完成 receipt；子 publisher JSON 从 session 文件独立重放。每个请求都需要自己的最终 status。
7. `effects`：精确 `{sequence,before,after,comparison,expected_observed_effect}`；后四者前三个为输入 key，最后为严格 bool。所有十方向的 submit 必须出现一次，setup 不伪装为新方向效果。comparison 要和实际共享 checker 的完整 typed 输出及两个输入 SHA 完全相同。
8. `annotations`：仅 `{sequence,source:"root_ui_annotation",text,native_evidence:false}`。`persistence:[]`。

`select` 的列表索引要求严格整数，bool/float 不可替代；字段必须实际存在，null 不等于缺键。

## 离线命令

```powershell
python -B work/candidates/v14-directional-experiment-review/prepare.py --check
python -B work/candidates/v14-directional-experiment-review/verify_tests.py
python -B work/candidates/v14-directional-experiment-review/prepare.py --template <new-empty-template.json>
# 仅 root 完成并明确固定最终 case 后，另行决定运行：
python -B work/candidates/v14-directional-experiment-review/reviewer.py review --case <final-case.json> --output <new-summary.json>
```

输出全部 CREATE_NEW。测试跑真实四阶段和 typed 观察器，不 mock 原生日志判定；仅把固定 build 的物理位置、依赖加载和合成 prefix 字节重定向至临时数据。无 ProcessReader、注入、请求或实际外交调用；所有运行记录含 source before/after 与 stdout 哈希。

首轮 19 tests 的 2 errors 是合成夹具重序列化原始前缀；第二轮 3 errors 是夹具日期未绑定和 ProbeError 未归一化。原始失败记录保留；之后 19/23 tests 已通过，新增正常退出与所有权反例后再次完整验收。最终精确次数、版本和哈希见 review.json，不能将较早失败说成通过。
