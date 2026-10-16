# EU4 1.37.5 限定研究会话 v6

此工具用于可丢弃 FRA 测试局，协议为 `EU4LAB/1`。它与生产协议 `EU4PAIR/1`、HTTP API 的执行后端分离；不会注册生产后端，也不会修改正式动作白名单。原生合法性通过、原生命令返回、游戏效果、存档和重载验证是不同证据。

完全离线的机器可读说明：`python tools/request_diplomacy_lab.py capabilities`；仅十个 pair 入口与速度控制可加 `--research-only`。该命令同时展示全部目录动作的静态映射、受限实验入口、固定历史观察和正式 unsupported 状态，不访问游戏。字段及证据截面见 [能力分层说明](diplomacy-research-capabilities.md)。

v5 的固定 FRA→ENG 改善关系实验已经完成原生命令发送、运行时 relation/mission/envoy 图、保存和重载验证。该结论只覆盖已记录的固定实验，不替代 v6 各次请求的验证，也不证明其他动作可执行。相关报告见 `work/runtime/native1375-v5/` 的 `saved-effect-verification-46972.json`、`reload-verification-45564.json`。

## 构建与安装边界

`work/native/build-lab-1375.cmd` 构建 `work/runtime/native1375-v6/eu4_pair_lab_1375.dll`，然后调用 `record_lab_build.py`。固定 12 个原生源文件、DLL、游戏 SHA 和运行速度开关均由 `build.json` 绑定。记录器仅记录构建证据，`runtime_verified` 与 `production_backend_registered` 始终为 false。Python 验证器不接受缺源、源或 DLL 哈希变化、其他游戏构建或不同用途的 manifest。

加载器 `work/native/inject_lab_1375.py --pid PID --creation CREATION --ack-test-save --plan-only` 只检查。移除 `--plan-only` 才会安装固定 DLL；不会自动发布任何阶段 marker 或动作。`--test-save` 可选择两个已核对字节的测试存档，默认 baseline；文件存在不证明当前游戏加载了它。加载器拒绝已有任意已知 bridge 模块或该进程的既有 v6 会话目录；安装失败也不能直接重试或热换 DLL。

CLI 以只读进程句柄独立核对 exe 路径、完整 exe SHA、PE 时间戳与映像大小、PID 创建时间、DLL 精确路径及 PE 身份、FRA 玩家句柄和世界根。磁盘 DLL SHA 与 loaded PE 身份是两项独立检查；没有声称对重定位后的整个内存 DLL 做字节 SHA 比较。

## 会话与阶段

原生宿主在 DLL 所在目录创建独占私有目录 `session-PID-CREATION`，CREATION 是 16 位小写十六进制 Windows FILETIME。目录已有即拒绝；不得通过删除目录重新启用同一进程。目录中 `session.json` 和永久 `install.claim` 必须完全匹配，日志固定为 `research-1375.jsonl`。外部日志内容不得指定文件路径或地址。

`tools/request_diplomacy_lab.py --pid PID --creation CREATION status` 是只读状态。以下阶段分别显式运行，命令默认只作检查计划，添加 `--publish` 才发布：

```text
python tools/request_diplomacy_lab.py --pid PID --creation CREATION stage lifecycle --publish
python tools/request_diplomacy_lab.py --pid PID --creation CREATION stage preview --publish
python tools/request_diplomacy_lab.py --pid PID --creation CREATION stage command --publish
```

阶段必须逐一完成，且每阶段后有新的健康 frame 才允许后续阶段。每个 marker 都有永久独占 claim：

| 阶段 | marker | 精确 ASCII 内容 | claim |
|---|---|---|---|
| lifecycle | pair-selftest.request | `PAIR_SELFTEST_1375\n` | phase-lifecycle.claim |
| preview | pair-preview.request | `PAIR_PREVIEW_1375\n` | phase-preview.claim |
| command | pair-command.request | `PAIR_COMMAND_1375\n` | phase-command.claim |

Python 从同一安装边界流式验证五项生命周期、20 项合法性、20 项命令生命周期证据与相应 claim。它只将各阶段后的第一个健康 frame 之前的原始日志送入既有 no-send 验证器，后续真实动作不混入这段证明；不会补造日志字段。帧必须绑定窗口线程、进程创建时间和世界/玩家身份，不允许回退日期或被冻结会话。发布要求近期心跳（最多 2500 ms）；阶段与 pair 请求还要求暂停和独立读取日期一致。

## 请求协议与状态

请求是固定顺序、严格 ASCII、LF 结尾、最多 1024 字节；整数为规范十进制，PID 为正 uint32，sequence 为 1 至 2^63−1，creation 为非零 16 位小写 hex。示例仅展示格式，不能用于真实会话：

```text
EU4LAB/1
pid=1234
creation=01da123456789abc
sequence=1
expires=12345678
operation=pair
mode=legality_only
action=improve_relations
actor=FRA
target=ENG
speed=0
```

`expires` 是 Windows `GetTickCount64` 的绝对毫秒时间。TTL 须为未来且不超过 60000 ms；默认 5000 ms。native 在读入和变更前检查，不把到期作为自动重发理由。严格下一序号为 `last_sequence+1`，文件名固定 `<sequence:020d>.request`，对应永久 `.claim`。

支持十个 pair ID：`offer_vassalization`、`cancel_vassalization`、`royal_marriage`、`break_marriage`、`improve_relations`、`stop_improving_relations`、`guarantee`、`revoke_guarantee`、`build_spy_network`、`stop_building_spy_network`。协议仅允许 FRA/ENG/POR TAG，actor≠target，pair speed=0。`legality_only` 可检查这些 TAG 组合；`submit` 只允许当前玩家 FRA。客户端不能提供指针、RVA、函数地址或原生对象字段。

```text
python tools/request_diplomacy_lab.py --pid PID --creation CREATION pair improve_relations --target ENG --mode legality_only --sequence 1
```

上述默认不写文件。发布添加 `--publish`；提交须显式 `--mode submit`。Python 在原子发布前创建永久 `.host-intent`，记录 manifest SHA、原始请求字节及 SHA，再核对身份、世界、序号与期限。临时文件使用独占创建和持久化，无覆盖原子 rename。任何后续失败都会留下 intent；不能删除它并重试。native 持有独占 request 句柄，从同一已验证句柄读取、创建永久 claim、删除输入，之后才执行一次。

`published` 只表示文件已发布，不能当作 native dispatch。`lab_request_claimed` 证明宿主已持久领取；`lab_native_record` 绑定同一序号的核心日志；`lab_request_complete` 必须与核心完成记录一致。`submit_entered`、`submit_returned` 或 status=2 只描述调用边界，`applied_verified` 始终 false。所有权未知、异常、身份变化、缺失/冲突证据均禁止重发；只读 `status --sequence N` 不会修补或重试未知操作。

## 运行速度租约

速度 0 表示暂停，可直接以明确序号发布。正速度仅允许由 `work/native/run_lab_speed_1375.py` 监督器运行，例如：

```text
python work/native/run_lab_speed_1375.py --pid PID --creation CREATION --sequence N --speed 1 --ack-disposable
```

监督器直接启动 CLI，传入自己的 PID/创建时间。CLI 保持并核验直接父进程的只读同步句柄；普通直接 CLI 的正速度发布在任何 intent 写入前拒绝。此契约防止误用，不是防御同一用户恶意伪造父进程的权限边界。

native 对正速度设置 5000 ms 或 48 原始日期单位（两日）的租约，在达到任一阈值后的健康帧尝试暂停。租约期间不消费新邮箱请求。暂停也有永久 `.lease-pause.claim`，不是原请求重试。异常/日志失败会冻结会话，因此 native 租约不能保证所有故障下仍能暂停。

独立监督器在发布前保持精确 PID/creation 的可终止句柄，确认暂停基线，监听对应序号的完整租约日志并独立读取暂停状态。12 秒是轮询终止阈值，不是抵抗操作系统 I/O 停顿的硬实时保证；失败、未知或超时终止同一个可丢弃进程，最多等待其退出 5 秒。不会再调用未经确认的原生暂停。正常完成须有绑定的 claim/core/lease 完成记录及实际 paused 读回。

## 验证与限制

`bridge/tests/test_diplomacy_lab.py` 的合成文件测试覆盖协议严格性、阶段证据、永久 claim、计划不发布、重复/过期/跨世界发布、身份绑定、未知结果以及速度租约证据。它们不访问游戏、不加载 DLL、不证明原生运行效果。`test_restart_arguments.py` 仅测试纯参数分词辅助文件；不会调用重启脚本。

当前世界根与单调日期仅构成限定测试会话的保守 guard，不是可靠的所有读档路径 generation。严格单机来源也未通过完整状态机证明；`world_generation_verified` 保持 false，生产白名单保持空。后续每个正向/取消动作仍需独立运行时和保存/重载验收。
