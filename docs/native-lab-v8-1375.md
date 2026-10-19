# EU4 1.37.5 v8 独立研究工具

v8 为固定夹具事件增加一个只有 `name = OK` 的空效果选项，使出现的事件窗口具备关闭选项。两个事件仍保留 `hidden = yes` 和原有 immediate 效果；没有加入解除停战脚本，也没有改变 pair 原生发送实现。构建和离线测试不能证明运行时窗口行为或外交效果，后者应单独查看明确进程、序号和观测报告。

## 版本和定义选择

v8 继续使用 `EU4LAB/2`，但目的为 `restricted_pair_lab_1375_v8`，DLL 为 `work/runtime/native1375-v8/eu4_pair_lab_v8_1375.dll`。14 个原生源文件、输出目录、会话目录和 fixture profile 均与 v7 分开。相同协议版本不表示可以混用 v7/v8 session 或 DLL；当前进程的已安装 hook 不支持热替换。

新夹具为 `1375_test_fixture_v2`，规范 JSON profile SHA 为：

```text
68f5c90d63343fd2db64ccd64bd232877409dc43302bf5d40c854c30c84ae918
```

五份构建输入来自 `work/candidates/fixture-v8-1375/mod/llm_diplomacy_test/`。manifest 的文件名仍使用 `mod/llm_diplomacy_test/...`，运行前安装核对读取真实用户数据目录中的这些文件、启用列表、外部 descriptor 和修改时间。候选目录的字节匹配不能代替实际安装证明，也不能证明引擎已经注册事件。旧仓库 `mod/llm_diplomacy_test/` 继续保留冻结 v7 源定义。

安装器明确选择 `--fixture-profile v8` 才读取候选定义；默认 `original` 不是 v8 定义。安装会先备份并更新真实用户 mod，随后需要新进程加载。不能以安装后的新文件校验成功来认证安装前已经运行的进程。

## 入口与操作范围

Python 入口为 `work/native/inject_lab_v8_1375.py`、`tools/request_diplomacy_lab_v8.py`、`work/native/run_lab_speed_v8_1375.py`。记录器为 `work/native/record_lab_v8_build.py`。加载器要求明确的 `--test-save`，仅接受三个已绑定 SHA 的可丢弃测试档；新增的正向实验档为：

```text
llm_diplomacy_1375_v7_marriage_vassal_20261008a.eu4
F6A56C25FD366522C5F625BAFF086B33F02473EDCD34AAE3E3C2984D30436FB8
```

文件名中的 v7 表示存档来源，不是加载器版本。磁盘文件存在、SHA 和序列化 FRA 单机前提匹配，仍不代表已经从引擎读取并确认当前加载文件路径。加载器保留 `loaded_save_identity_verified=false`。

不访问进程的能力查询，以及不写请求的计划示例：

```text
python tools/request_diplomacy_lab_v8.py capabilities --research-only
python tools/request_diplomacy_lab_v8.py capabilities --action offer_vassalization
python tools/request_diplomacy_lab_v8.py --pid PID --creation CREATION status
python tools/request_diplomacy_lab_v8.py --pid PID --creation CREATION pair cancel_vassalization --target NAV --mode legality_only --sequence N
```

`capabilities` 只读离线目录和经 SHA 审查的历史，`discovery_source=v5_v6_v7_v8_v9_v10_reviewed_history_only`。v8 的已审阅运行切片包含至 seq6 的唯一 pair 提交和保存一致性；独立补充报告还核对了 PID 20276 的选定状态重载一致性，原收尾摘要保留。它返回 `v8_live_readiness=null`，不因构建成功自动增加历史能力。十个 pair 入口、FRA/ENG/POR/NAV/FOI 固定 TAG、仅 FRA 可 submit、显式三阶段、主线程/世界/PID/creation、暂停、TTL、单调序号及永久 claim 的约束继续生效。fixture 只接受固定 `fixture_on/fixture_off`，不能传任意脚本或事件名。

所有发布都需要显式 `--publish`。正速度必须通过 v8 外部监督器，由其绑定精确 PID/creation 监督租约后暂停；普通直接 CLI 无权绕过监督器。结果未知时不自动重发，不对所有权不明的原生对象补清理。以上研究入口不注册生产后端；正式 API 继续为 `unsupported`，白名单为空。

## 离线核验

首个候选构建通过 MSVC `/W4 /WX`，原生语法测试 74 项、Python v8 独立测试 15 项通过。DLL SHA 为 `43BFC582EE15E612410B2CC8D8F9B63CA6D47F2135CBD2301578718901E557A4`，manifest SHA 为 `6ddae83ec9a154cb597c70c118a6500440a2ee92c83e0b78cff9b13f99830240`。这些结果仅认证对应文件和离线契约。

Python 测试覆盖 profile、实际安装和启动时间、永久证明文件、核心和宿主 ACK、异常/清理结果、v7/v8 命名隔离、候选目录与旧 mod 源隔离，以及缺少明确测试档时在访问进程之前拒绝。测试只写临时合成文件，不注入 DLL、不发布游戏请求。构建审查记录见 `work/candidates/v8-build-review/`；已有实验的效果和保存重载边界见 [研究能力说明](diplomacy-research-capabilities.md)。

## 固定 v8 运行记录

PID39216 / creation `01dd5681d5d0e053` / 主线程34592 使用上述 DLL。成就提示已经通过 Computer Use 点击确定；重载待处理 `llmt.1` 出现空 OK，关闭后仍暂停，日期、103个外交官对象以及 NAV 联姻/附庸选定状态不变。`work/verify_v8_fixture_window_1375.py` 和 `work/runtime/native1375-v8/fixture-window-review-39216.json` 将 UI 人工代理观察与只读选定状态核对分别记录。

五类 lifecycle、20 preview、20 command 检查均通过。seq1撤下增益、seq3重新启用增益均正常返回、析构结果及复原 callback flag，无异常；两种事件窗口均可关闭。撤下后的独立存档已没有 FRA modifier 字段，但外交官对象 vector 仍为103；这不是即时可用上限或缩池结果证明。

seq4无发送检查允许解除 NAV 联姻，seq5真正提交后独立关系观测确认移除；seq6受监督推进后重新暂停于1444.11.17，新保存同样没有 FRA/NAV royal_marriage，仍有原 vassal dependency。独立结果档 `llm_diplomacy_1375_v8_break_marriage_20261008a.eu4` SHA 为 `0000E4218F266CA3F29E2A3695FA16F4A8F405B91168C2C15F9E14070DC49571`，原收尾摘要仅证明保存结果一致。后续 `work/runtime/native1375-v8/break-marriage-reload-review-20276.json` 在单独进程 PID 20276 / creation `01dd568c4bc812d0` 核对婚姻仍不存在、选定附庸完整身份仍一致，保存字节 SHA 未变。补充记录的 `saved_reload_state_consistent=true` 不代表引擎已证明所加载文件路径、精确请求因果或全世界一致性；旧摘要未被改写。

可复查 `work/verify_v8_experiment_1375.py` → `work/runtime/native1375-v8/experiment-summary-39216.json`，绑定14份输入及实际存档/DLL哈希。此进程有1次 pair实际提交；fixture和速度不计入外交提交。精确请求归因、当前引擎加载文件路径、全世界不变和生产接入仍未证明。v8源文件、DLL、manifest及fixture输入现已冻结。
