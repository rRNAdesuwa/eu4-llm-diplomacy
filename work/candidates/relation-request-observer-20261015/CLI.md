# 原请求关系候选 CLI（待独立审计）

新增 `relation_request_cli.py`、`test_relation_request_cli.py` 与 `run_cli_tests.py`。稳定公共 CLI/HTTP、98-pin manifest、默认 native 44-pin 图都不修改。无 HTTP/serve、installer、publisher、重发或 legacy baseline 导入。此阶段没有创建 `candidate-cli-manifest.json`，默认调用会返回 unknown/2，且不会导入候选模块。

## 清单与导入顺序

正式入口只能读取同目录固定 `candidate-cli-manifest.json`；没有 `--manifest` 旁路。独立审计后由 root 创建清单，要求 schema `EU4-RELATION-REQUEST-CLI-MANIFEST/1`、`sealed=true`、固定 game/native SHA、`candidate_module_sha256` 和 `source_pins`。清单需覆盖 CLI、CLI tests、本说明、候选 module/module tests/README、五个冻结 observer/reader manifest 的完整源图、native manifest 的 44 个源文件及 DLL。每个 pin 是 `{bytes, sha256}`。

使用标准库先校验整个图、固定冻结 manifest SHA 和直接依赖闭包，再编译已核 module 的源字节（不加载候选 `.pyc`）。导入后再次验证清单、源图和 module 自身报告的依赖集合。每次 prepare/status/watch 操作前后继续校验；上层 CLI 源变化会关闭为 unknown，不能仅依靠较低层 module 的 pin。仅测试函数私有参数允许注入临时 sealed fixture 清单与纯离线 loader，不对命令行暴露。

源图 ≤256 文件，总大小 ≤128 MiB，单文件 ≤16 MiB，流式 SHA 每块 64 KiB；manifest ≤256 KiB，session 输入 ≤32 KiB，单个输出 JSON ≤2 MiB。源路径必须是项目内的规范相对 POSIX 路径，不允许绝对路径、`..`、反斜杠、盘符或解析后越过项目根目录的链接。

## 操作与退出码

```text
relation_request_cli.py check
relation_request_cli.py catalog
relation_request_cli.py --session-file ORIGINAL_SESSION.json --allow-tag-host prepare --request-id ORIGINAL_ID --action ACTION --actor FRA --target SCO
relation_request_cli.py --session-file ORIGINAL_SESSION.json status --request-id ORIGINAL_ID --compact
relation_request_cli.py --session-file ORIGINAL_SESSION.json watch --request-id ORIGINAL_ID --compact --duration-seconds 30 --interval-ms 1000 --max-samples 32
```

以上仅为审核后的接口示例，目前无 sealed manifest，不能执行。prepare/status/watch 必须提供真实安装会话文件和原 request ID。CLI 通过候选模块的 `installed_session` 再核原始安装证据；current-only 随机 nonce 不能转换成 TAG 会话。三个新 profile 使用 `RelationRequestObserver`，其他 15 个保留其冻结委托。没有 legacy 导入选项。

- check/catalog/prepare 的退出 0 表示该本地操作完成。JSON 明确 `operation`、`selected_effect_verified=false`、`requests_published=0`；prepare 只保存本地基线。
- status/watch 的退出 0 只表示 `effect.status=observed` 且严格布尔 `selected_effect_verified=true` 和 transport 已派发；原 profile 如 annex 的 `in_progress` 仍保留其具体阶段，不等于完整外交目标完成。
- status/watch 的退出 3 要有冻结 ask_for_march reader 的 `sampled_equal`、唯一 typed state-0 pending 行、匹配身份/双方完整句柄和 native ID。单独 waiting 文本不够。
- 其他情况退出 2，包括 unknown、not_observed、缺基线、坏清单、源图变化、读取错误。不能据此自动重发。

compact 输出自包含原 request/command/identity、transport/effect/reply 状态、关系状态及方向、完整关系端点、知识分享方向和相关失败，不从其他 CLI 导入 compact。它不把 current relation、native dispatch 或退出 0 等同于 AI 接受或持久化。

watch 仅重复 observe，时长 1..300 秒、间隔 250..10000 ms、样本 1..128 三重限制；成功或任一界限达到即结束。样本上限也覆盖时钟不前进的离线反例。单次已开始的受限捕获可能越过墙钟 deadline；不把 polling deadline 说成强制中断 OS 读取。没有任何动作重试、派发或安装调用。

## 离线检查与原候选审计修复

运行 `python work/candidates/relation-request-observer-20261015/run_cli_tests.py` 只做临时清单和 mock observer 的离线测试，输出独立 `cli-test-run.{json,log}`。runner 对子进程设置 1 GiB committed 与 600 秒边界并收齐子进程。不会覆盖原 module 的 46 项回执。

原 module b1b7…/tests 07c… 的 46 项回执及源码精确前像保存在 `preaudit-b1b7/`。独立审计指出 thread/owner_thread 需 DWORD 上界；未封候选已修为 exact int 1..0xffffffff，seq0 允许合法 loader thread 不同于 owner，seq>0 仍要求 owner。修后 module SHA `4bdd6e6454a17d9277885f905559036c3929e39173b9543f172cbaeea7debceb`；`installation-delta-run` 记录了 6 个受影响/新增用例全部通过，不声称重新跑过全部 50 个 module tests。CLI 清单必须 pin 修后已审版本，不能引用旧 b1b7 digest。

当前仍无新实机采样、外交请求、AI 接受或持久化证据，48/44/42 保持。整个 CLI 是待审候选，不能据此宣称稳定工具已经升级为 18 个请求 profile。
