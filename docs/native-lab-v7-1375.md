# EU4 1.37.5 v7 独立研究工具

v7 使用独立的 `EU4LAB/2` 协议、`restricted_pair_lab_1375_v7` 用途、`work/runtime/native1375-v7/eu4_pair_lab_v7_1375.dll` 和新的进程会话目录。旧 v6 的 Python 工具、DLL、原生源和证据语义保持不变；v7 不接受 EU4LAB/1 请求，也不能热替换已安装的 v6 hook。

Python 入口为 `work/native/inject_lab_v7_1375.py`、`tools/request_diplomacy_lab_v7.py`、`work/native/run_lab_speed_v7_1375.py`，构建记录器为 `work/native/record_lab_v7_build.py`。它们不注册生产后端。`capabilities` 子命令读取经固定 SHA 审查的 v6/v7 历史，并保留 v5 固定改善实验；不会检查当前进程。具体截止范围、NAV 正向联姻/附庸保存重载一致性及因果限制见 [研究能力说明](diplomacy-research-capabilities.md)。

## 与 v6 相同的约束

三阶段仍是独立显式 `stage lifecycle/preview/command`，完成后必须有新的健康帧。pair、阶段和 fixture 需要暂停；序号、PID/creation、世界、主线程、TTL、永久 intent/claim、未知所有权和无重试规则继续生效。正速度仍只能通过新版本的外部监督器发布，出现未知状态时终止精确绑定的可丢弃进程。

pair 增加 NAV、FOI 两个固定 TAG，完整集合为 FRA/ENG/POR/NAV/FOI。所有 submit 的 actor 仍只能是 FRA；`legality_only` 的允许输入不等于原生合法性通过。固定 handle/slot 由新原生源码内部核对，不是 API 参数。

## 固定夹具及构建证明

新 `fixture` 操作只接受 `fixture_on` 和 `fixture_off`。线上 ASCII 字段固定为：

```text
operation=fixture
mode=submit
action=fixture_on
actor=FRA
target=FRA
speed=0
```

`fixture_off` 只替换 action 值。其他 mode、目标、脚本文本、事件名、路径和任意控制台字符串均拒绝。调用示例默认不写文件；只有显式 `--publish` 才发布一次：

```text
python tools/request_diplomacy_lab_v7.py --pid PID --creation CREATION fixture fixture_on --sequence N
python tools/request_diplomacy_lab_v7.py --pid PID --creation CREATION fixture fixture_off --sequence N --publish
```

构建 manifest 绑定 `work/native/v7/` 下十二个原生源文件，以及两个 `test-fixture-v7-1375` 文件。另有 `fixture_profile`，包含 `profile_id=1375_test_fixture_v1` 和五个固定 mod 文件的完整 SHA：descriptor、defines、`events/llmt_fixture.txt`、event modifier、opinion modifier。规范 JSON（ASCII、键排序、紧凑分隔符）的 SHA 固定为 `3a7f514eadacee07494fef32e8ebca62d1020c6936c9877490ddba0bd59223c1`，与原生宿主常量及健康帧相同。任何定义变化必须产生新的审查与构建，不能沿用原 profile。

加载器和 fixture 发布器分别只读核对仓库定义、用户 mod 目录中的相同字节、启用列表、外部 `.mod` descriptor 指向，以及这些文件修改时间早于精确进程创建时间。这是磁盘安装/启动条件证明，返回 `engine_registration_verified=false`；没有声称引擎实际加载了事件。原生回调还会查找固定事件并可能拒绝。

## 一次性发布证明

创建永久 `.host-intent` 后，发布器重新检查已安装定义和启动时间，再独占持久写入 `<sequence:020d>.fixture-profile`，最后才原子发布 request。证明文件精确为：

```text
EU4FIXTURE/1
pid=PID
creation=CREATION
sequence=N
profile=3a7f514eadacee07494fef32e8ebca62d1020c6936c9877490ddba0bd59223c1
```

所有行使用 LF，末尾也有 LF。原生宿主要求该文件与本次 claim 的 PID/creation/sequence/profile 字节完全一致。已存在的 intent、证明或 claim 不能覆盖；任何中间失败都不自动重发。

`test_fixture_begin/complete` 通过 `lab_native_record` 绑定请求序号。Python 校验固定 `llmt.1/llmt.2`、FRA、线程、profile、日期、参数未变、输出字符串析构、回调标志恢复和世界身份；外层 `lab_request_complete` 必须一致。异常、失败或不明所有权永久冻结，不尝试补调用 fixture_off。正常回调返回仍有 `fixture_effect_verified=false`、`applied_verified=false`，效果必须由后续独立观察证明。

## 夹具改变的范围

当前固定脚本 fixture_on 为 FRA 增加 100 外交官和 100 外交声望，对 NAV/FOI 设置双方 +200 关系修正，并创建 FRA–NAV 联盟。这是人为测试前提，不能证明正常外交条件下 AI 会接受。fixture_off 撤除这些 modifier/opinion；它不撤销已创建的联盟，也不是完整世界回滚。

纯离线测试覆盖新旧协议隔离、TAG/actor 限制、固定 fixture 语法、manifest/profile、磁盘启用和时间证明、永久侧文件、核心与宿主 ACK 一致性、异常/清理状态以及禁止效果夸大。测试不打开游戏、不安装 DLL、不发布实际请求。
