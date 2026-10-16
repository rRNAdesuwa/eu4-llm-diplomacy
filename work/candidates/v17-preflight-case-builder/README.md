# v17 显式 preflight case 构建器模板

这里只构造文件，不运行 preflight/experiment reviewer，不访问进程，不导入宿主接口，不发布阶段或请求。尚未填入新进程身份，`plan-template.json` 中的 null 必须由根代理根据明确文件补齐；模板本身不能通过检查。

PID 22784 的冻结 seq0 前缀及相关固定 captures 已另存输入清单于 `../v17-preflight-case-builder-22784/inputs.json`，缺口见该目录 `blocked.json`：只有一份完整 RO diagnostic，后续 fixture/外交状态不能冒充第二份 seq0 对照。这组记录没有生成 case、scope 或 summary，也没有晋升。

新进程的计划必须显式给出：

- scope 中的 PID、完整 creation、world、线程、日期、DLL/manifest SHA、BridgeStart RVA、冻结前缀字节数/SHA。
- 固定七文件目录 `work/runtime/native1375-v17/directional-preflight-prefix-<PID>`；禁止指向任何 `session-*` 路径。只枚举这个明确的冻结目录，不查找 latest。
- 独立 before/after 完整 RO diagnostic，须为不同文件、相同完整进程/选定世界身份、先后不重叠且选定字段相同。缺 after、复制 before、CLI status 或 fixture 后外交官数量变化都会拒绝。这里不声称采样精确包围每个原生事件。
- loader actual、最后 seq0 status、build、prefix snapshot 以及十个明确 capture（loader plan、install health、四阶段 publish/status）。所有描述均包含相对路径、精确字节数及 SHA；命令阶段 status 可在两个逻辑角色中引用同一已固定文件。
- 全新 output_directory，scope 的 preflight_case/preflight_summary 必须分别指向其中 `preflight-case.json` / `preflight-summary.json`。

每件输入最多 2 MiB，总读取计数最多 8 MiB；实际读取使用 `read(MAX+1)`。路径拒绝链接、跳转、活动 session；文件在构造结束前复核。仅按固定格式构造 case，不代替冻结审核器的完整四阶段/原生日志验证。测试中的简化 loader/phase 数据有意不能作为真实 preflight 通过证据。

项目根命令：

```text
python -B work/candidates/v17-preflight-case-builder/build_case.py --config EXPLICIT_PLAN.json
python -B work/candidates/v17-preflight-case-builder/build_case.py --config EXPLICIT_PLAN.json --create
```

第一条只检查并构造内存对象。第二条先完成同样检查，再独占创建新目录，写 scope.json、preflight-case.json、construction.json，全部 CREATE_NEW 并 flush/fsync；中途失败留下的目录不可覆盖。**不会创建 preflight-summary.json**。construction 的 finalized=false / formal_review_performed=false / runtime_promoted=false 明确表示尚未正式审核；case 严格沿冻结 reviewer schema，因此不额外插入 finalized 字段。

根代理审阅后才可自行运行冻结 `v17-acceptance-experiment-review/reviewer.py preflight --case .../preflight-case.json --scope .../scope.json --output .../preflight-summary.json`。本轮没有执行此命令，也没有准备实际完整实验 case。

`source-pins.json` 绑定冻结 v14 case 构造格式来源及 sealed v17 审核源码；`case-construction.diff` 展示从旧 prepare 的构造职责到新 helper 的差异。新 helper 刻意不继承旧 prepare 的 `review(case)` 调用。验证只用临时目录中的 synthetic 文件。
