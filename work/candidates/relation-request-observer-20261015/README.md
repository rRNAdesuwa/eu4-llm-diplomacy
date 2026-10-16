# 原请求关系观察候选层

状态：未封存，等待独立审计。仅新增 `offer_alliance`、`royal_marriage`、`guarantee` 三个请求效果观察 profile 的工程实现。未改任何冻结 reader、manifest、公共入口、默认 build7/DLL 或 44-pin 图。稳定入口仍有 15 个请求 profile；此候选组合 catalog 为 18 个。它不增加真实成功、接受或持久化证据：48 效果信号 / 44 持久化 / 42 候选保持。

2026-10-15 自验：46 项合成测试全通过，runner 墙钟 170.75 秒，子进程 peak committed 71,831,552 B；所有 shell/测试子进程已收齐。重新核对现稳定 public manifest SHA `23c6831a861425c5f3012b583c93c6c1ccf7d10c769f9a23389474d389c9b361` / 98 pins、native 44 pins / 120 actions，均保持原值。独立审计尚待完成。

## 文件与复现

- `relation_request_observer.py`：候选适配器、真实安装身份检查、基线、原请求 status、候选 catalog。
- `test_relation_request_observer.py`：临时文件中的实际 `recorded_snapshot` 链与 native-layout byte graph 集成测试。不会调用真实 publisher、loader 或 WindowsRuntime。
- `run_tests.py`：测试子进程 committed memory 上限 1 GiB、墙钟上限 600 秒；结束或超限时收齐准确子进程。
- `test-run.log`、`test-run.json`：离线验证结果及该次源码 SHA；这是测试回执，不是封存 manifest，也不是实机证据。

从项目根目录执行：

```powershell
& '${USERPROFILE}\AppData\Local\Programs\Python\Python312\python.exe' work/candidates/relation-request-observer-20261015/run_tests.py
```

## 身份、基线与结果含义

新 `RelationRequestCapture` 接收真实 TAG 安装 identity，复用冻结 `RuntimeCapture` 的 QUERY/VM_READ 句柄。它不调用 `RelationStateObserver`，也不生成随机 session。身份同时绑定默认 native manifest SHA `d4b3069cfac70cf9ff8e1270733ad64592c3d545a6d005fd0ed8b26c6070728a`、44 个源 pin、DLL、原始 loader intent、bootstrap packet、成功安装报告及唯一 `hook_installed` 完整审计。安装记录只证明曾安装；当前 host 是否在模块表中另记。序列 0 的安装记录由 loader thread 写出，不能错误要求其等于游戏 owner；序列大于 0 仍要求 owner thread。

`prepare` 只写本地观察基线，要求原请求 intent 与 publisher.lock 在捕获前、捕获后和写前均不存在；要求真实安装审计尚未 terminal、捕获期间审计不变、现场默认 TAG host 已加载且明确允许读取。只接受完全 absent 的双方 typed index。基线以 `xb` 独占写入，不能覆盖或从 legacy/current-only 样本补造。

基线写完后还要复查 intent/lock、安装文件、完整 audit 和源图，再独占写入 `relation-request-baseline-commit.json`，绑定 baseline SHA。status 必须验证该提交记录，并在捕获后复查它和 baseline 均未改变。最后写入间隙若出现发布或磁盘失败，只有孤立 baseline 而没有有效 commit，必须 unknown；不能覆盖孤立文件来重试。此提交是本地观察日志提交，不是外交请求提交。

`observe` 通过原始 `recorded_snapshot` 读取 request/claim/intent、pair_bound、dispatch 和 request_result；不调用后端 status、publish、load。基线 audit digest 必须是当前完整审计的严格前缀，前缀中不能已有该请求 sequence。缺失基线/commit、错误 session、partial audit、不完整所有权/派发回执、改变的绑定或源图都会保留 unknown，不生成“被拒绝”或可重试结论。新源图失败时仍可保留先已通过文件核对的 transport receipt，但 effect 保持 unknown。

新捕获重新扫描国家表并解析完整句柄；绑定必须与现场同一代 handle 相等。调用冻结 `read_relation_pair` 完成两个完整样本，两端 typed index、同一 typed object、完整端点、日期及 removed/insertion-failed 字节均保留并检查，再复查国家表、世界根、进程身份、模块、安装文件、审计和源图。持久化 capture 使用冻结 `_capture` 重放原始 index/object 字节，再交给纯 `evaluate_relation_effect`。`guarantee` 的逆向对象返回 not_observed；联盟和王室联姻按对称关系处理。

只有“发布前 absent → 现场 selected indexed relation”可产生 `selected_effect_observed`。这仍不是独占外部 request ID 因果、AI 接受、全局关系注册、完整生命周期、世界 epoch、原子快照或保存/冷重载证明。旧请求没有合格基线时保持未知，不能补发来制造证据。原四项及原 120 项等已派发、未知或所有权未闭合动作继续永久禁重发。

## 边界与未闭合项

- 单次候选捕获共用 `BudgetReader`：4,096 calls / 512 KiB / 单次 65,536 B；包括选定 TAG 扫描、研究 DLL header、两遍 reader 和末尾复查。继承 `RuntimeCapture.__enter__` 的主模块 8,192 B PE 检查在该内部预算之外，不能把内部统计称为全部 RPM。
- typed index signed count ≤256，capacity ≤4096；完整国家表固定 1380 entries，开头与末尾各读一次。所有句柄/对象都有固定 profile 验证，没有新的游戏函数调用。
- 安装报告和 bootstrap 各 ≤128 KiB；audit / baseline / capture journal 各 ≤2 MiB。只有本地观察目录写入。
- intent/lock 外部检查不等于持有 publisher 锁；两遍外部读可漏 transient/ABA，不提供 world lease。
- 候选自身仅做前后/基线 source pin 一致性检查；正式信任根必须等独立审计后另建 manifest。冻结依赖 manifest 已逐项验证。
- 合成 byte graph 不等于实机 API 效果或接收国接受。当前没有新增实机采样。

## 公共 CLI 接入建议（尚未实施）

独立审计完成后，由 root 决定是否生成新的组合 manifest/入口。不要修改现有 `tools/eu4_observer.py`、98-pin manifest 或默认 DLL pin。组合层可将这三个 action 的 prepare/status 路由到 `RelationRequestObserver`，其他 15 个沿用冻结 `LiveDiplomacyObserver`；current relation GET 保持独立 current-only 语义。

输入须使用已有真实 session 安装报告的完整 identity，以及原 request ID / actor / target。prepare 对应用户以后明确授权的新请求的发布前本地观测；它本身没有发布权限。status 对既有请求只观察，缺基线则 unknown。CLI catalog 应区分“18 个工程 profile”与“新增实机效果 0”；界面分别显示 transport、selected effect、reply、persistence，不能只把 dispatched 或退出码 0 显示为完成。

审计范围建议包含晚到 intent/lock、安装 nonce 混用、完整句柄代数、双向索引不一致、typed/raw projection 损坏、缺/改 receipt、源图和审计读后变化、本地 journal 写失败，以及真实当前 host 不存在时禁止新基线但允许核历史 status。
