# v12 固定会话离线审查

`work/verify_v12_experiment_1375.py` 只读已经停止的 PID 17676 / creation
`01dd56989186135c` 会话。它固定核对 v12 DLL、14 源 manifest、夹具 profile、
不可变 20/72/72 预检前缀，再检查完整序号、持久意图、claim、原生归属、效果和可选保存重载。
它不读取进程、不启动服务、不发布请求，也不修改 capability 索引。

尚未停止时，case manifest 必须保持 `finalized: false`，审查器立即拒绝。
正常退出需要同一进程句柄的 `WaitForSingleObject` 与 `GetProcessTimes` 证据：

```json
{"exact_process_exit_observation":{"pid":17676,"creation":"01dd56989186135c","process_exit_filetime":134000000000000000,"exit_observed":true,"method":"held_handle_wait_and_getprocesstimes"}}
```

这里退出时间仅为形状示例；真实值必须大于该进程创建时间。不会接受界面已关闭、
启动另一进程或操作者描述作为替代。内容哈希绑定不能认证日志来源，输出保留这一限制。

## Manifest 结构

顶层字段固定为：

```json
{
  "schema_version": 1,
  "purpose": "v12_finalized_experiment_case_manifest",
  "finalized": false,
  "inputs": {},
  "exit": "exit-proof",
  "preflight": "preflight-summary",
  "session_files": {},
  "final_status": {"input":"final-status","select":["report"]},
  "requests": [],
  "cases": []
}
```

`inputs` 是名称到 `{path,size_bytes,sha256}` 的映射。路径必须是仓库相对路径，
使用 `/`；SHA256 必须小写完整 64 字符。不能使用绝对路径、`..`、符号链接、junction、
重复路径或未被实际引用的证据。上限：384 文件、单件 8 MiB、总计 64 MiB，manifest 512 KiB。
实际保存文件另用 `--save-root` 下的固定文件名，最多 512 MiB，流式处理。

`preflight` 引用固定 `preflight-summary-17676.json`；其 15 个 `input_sha256` 引用
也必须进入 `inputs`，路径规范化为 `/`。审查器重新运行三份 `verify_phase`，
不是只相信 summary 的布尔字段。

`session_files` 映射真实会话目录内的文件名到 input 名称，须完整列出目录中所有文件：

- `session.json`、`install.claim`、`research-1375.jsonl`；
- 三份 `phase-*.claim` 与相应 `.claim.host-intent`；
- 每个序号的 20 位十进制 `.host-intent`、`.claim`；
- fixture 的 `.fixture-profile`；
- 正速度的 `.lease-pause.claim`、`.supervisor.jsonl`、`.publisher-output.txt`；
- 经 HTTP 发布的 `.http-intent`。

任何残留 `.request`、临时文件、未知 claim 或目录都会拒绝完整成功审查，不能通过
省略引用隐藏。完整日志只在退出证据通过后读取，核对全部字节；运行中状态报告必须
对应完整日志中准确的行边界前缀和当时最新 frame。最后 CLI 状态可以早于 UI 正常
退出的最后几帧；最终日期、暂停和完整性取停止日志，不从较早状态推导。

## 每个请求

`requests` 必须按 1..N 完整列出，包括 fixture、速度和合法性检查；不能只列成功提交。
每项固定字段：

```json
{
  "sequence": 10,
  "request": {"operation":"pair","mode":"submit","action":"cancel_trade_power_transfer","actor":"FRA","target":"POR","speed":0},
  "outcome": "dispatched",
  "publication": {"kind":"cli","evidence":{"input":"cancel-publish","select":["report","publication"]}},
  "status": {"input":"cancel-ready","select":["report"]}
}
```

`select` 是最多六步的 JSON 键/数组索引，便于引用已有固定包装报告；不会执行表达式。
CLI `publication` 引用首次 `published` receipt，status 引用带完整 `request` 历史的状态。

HTTP 使用 `kind: "http"`，evidence 指向完整四步 HTTP 报告（通常 `select: []`），
要求先查询、首次 POST 202、读取结果、相同 POST 200且不再写入；另核永久 HTTP intent。
HTTP 的 `status` 可为 null，因为完整结果已被四步报告绑定。

速度使用 `kind: "supervised_speed"`，evidence 引用 `completed_and_paused` 包装内层对象，
`status` 可为 null；永久 supervisor JSONL 必须恰有 armed 与 complete，完整绑定同一
PID/creation/sequence、暂停前后态与原生 lease_complete。它不会计入外交提交。
publisher-output 的完整 stdout 另外绑定首次发布 receipt 和健康 frame 的精确日志前缀，
不将其输出本身作为效果或完成证明。
fixture 使用普通 CLI receipt/status，outcome 为 `fixture_callback_returned`；不宣称夹具效果。

允许的 pair outcomes：

| outcome | 必需边界 |
|---|---|
| `dispatched` | status 2/reason 0，submit entered/returned、container consumed，无异常或未知归属 |
| `legality_allowed` | status 1/reason 0，无提交，原对象和命令清理完整 |
| `legality_rejected` | status 1，reason 17/18，精确 preview/command 阶段和清理 |
| `guard_rejected` | 目前仅固定 reason 13/phase 3/status 0；未分配、未调用 preview/gate、未提交 |

summary 保留原 status/reason 和实际调用标志。guard 拒绝不算原生合法性检查，合法性
通过也不等于 AI 接受。不同日期的明确新序号仍是不同请求，不会自动合并为 retry。

## 效果与保存重载

`cases` 只列确实审查效果的 submit 序号，每项字段固定：

```json
{
  "sequence": 10,
  "before": "trade-before-cancel",
  "after": "trade-after-cancel",
  "comparison": "trade-cancel-comparison",
  "expected": {"expected_fraction_milli":500},
  "persistence": null
}
```

贸易权必须固定 `expected_fraction_milli:500`，gift 必须固定
`expected_amount_milli:25000`，其他已支持关系用 `{}`。不允许从观察到的经济差额生成
expected。赠款要求同日双方金额精确变化且 favors 不变；favors-for-gold 尚无本轮独立
成本合同，不支持效果晋级。取消必须 active→absent；absent→absent 永远不算成功取消。
insult 尚无效果 observer，仅记录合法性。

可选 `persistence` 当前支持贸易权、转移贸易方向、警告关系的实际保存与独立进程重载：

```json
{
  "filename":"llm_diplomacy_1375_v12_trade_power_positive_20261008a.eu4",
  "size_bytes":35800906,
  "sha256":"0fa8e8482968acc86597b102bef46410c5d6c0d7bb7b13398b6381df7d3baa9a",
  "report":"trade-positive-save",
  "pre_save":"trade-before-save",
  "saved_date":"1444.11.23",
  "start_date":"1444.11.11",
  "reload": {
    "snapshot":"trade-positive-reload",
    "launch":"positive-reload-launch",
    "identity":"positive-reload-held-identity",
    "exit":"positive-reload-held-exit",
    "pid":12345,
    "creation":"0123456789abcdef",
    "world":"0x123456789",
    "raw_date":56457264
  }
}
```

reload 示例身份需替换真实证据，未重载时为 null；取消的 `start_date` 必须 null。
保存解析会重新流式运行并与原提取报告比较，只忽略采集时间和保存路径拼写。
若报告带 snapshot_save 的 `copy_evidence`，会先单独校验有界结构、CreateNew 声明、
保存大小/SHA与目的文件名；重解析比较再排除此字段。原始文件路径和 stat 保持为记录的
来源信息，不声称重读了原始文件。只读冷启动使用精确的
`disposable_save_cold_reload_read_only` 合同，绑定新PID、完整创建时间、保存SHA、
previous_eu4_process_absent和native_injected=false，与旧 restart 合同分别验证。
选定关系方向、fraction、flag、保存日期、start_date和前存原生关系身份必须匹配。
重载必须新 PID/creation、两遍一致观察、相同完整国家 handles和选定关系语义，另有
指向该保存 SHA 的 launch 报告。程序不猜测保存日期与原生 raw_date 的换算。
重载还必须引用独立 held identity 和正常退出报告；校验身份前后相等、与 observer
相同的 roots/player/date/国家完整身份，采集时间处于该创建时间与退出时间之间。
这些只读文件不被提升为严格暂停、单人来源或可靠 world epoch 的证明。
选定状态一致不证明引擎当前加载文件的精确路径、整个世界、请求 ID 因果或赠款跨日余额因果。
不支持的 family persistence 请求会拒绝，绝不返回伪造通过。

警告使用实际存档键 `warning`（原生观察 family 为 `warningaction`），方向为 FRA→target，
严格字段为 first/second/start_date，不添加贸易关系的 is_enforced 假设。依据是
`final-cancel-steer-warning-save-17676.json` 完整解析中 line 1785702 / offset 36045715 的
唯一 FRA→POR warning，start_date 为 1444.12.3；反向记录、同名不同 family、重复或未知变体拒绝。

## 执行

仅在 root 收集结束日志、退出证据、全部请求和所需保存重载证据后：

```powershell
python work/verify_v12_experiment_1375.py --manifest work/runtime/native1375-v12/experiment-cases-17676.json --output work/runtime/native1375-v12/experiment-summary-17676.json --save-root "${USERPROFILE}\Documents\Paradox Interactive\Europa Universalis IV\save games"
python work/verify_v12_experiment_1375.py --manifest work/runtime/native1375-v12/experiment-cases-17676.json --output work/runtime/native1375-v12/experiment-summary-17676.json --save-root "${USERPROFILE}\Documents\Paradox Interactive\Europa Universalis IV\save games" --check
```

首次输出使用 CreateNew。`--check` 重新计算，仅忽略 `reviewed_at_utc`，不会覆盖原审查。
缺失文件、未知结果、未终止会话或不一致证据都不会生成成功 summary。
所有结果保持 production/strict SP/world epoch/请求因果/精确加载路径 false。
