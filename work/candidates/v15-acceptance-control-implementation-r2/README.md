# v15 固定接受控制：隔离实现候选

本目录承接冻结的 v15 计划，修订合同在 `plan-revision.json`。原计划 SHA
`cca6b608…e761b9`、独立计划复核 `1ed3dcdf…b49a9` 和最终 handler 静态报告
`f7eeae58…15eee5` 均绑定完整 SHA。原计划的 ABI pending 记录保留为历史；
本实现以最终报告为依据，仍不代表原生调用或所有权已运行通过。

所有新增源码、生成器、差异和测试只能位于此候选目录。拟输出按仓库相对路径
存放于 `files/`；此目录不具备真实游戏会话或构建产物。不得物化到正式
`work/native/v15`、运行构建、加载 DLL、发布请求、访问游戏或启动服务。
后续步骤由根代理完成独立审查后另行决定。

## 固定窗口

`EU4LAB/3` 保留原十字段，加 `bound_action`、`bound_target` 和
`bound_submit_sequence`。对外只有明确 `accept_on` / `accept_off`，没有
toggle、任意文本、参数、事件名、地址或内存写入口。原 36 个 pair ID 和
5 个固定研究标量保持不变。

- on 的序号必须不大于 `MAX_SEQUENCE-2`。它不可变绑定 FRA、一个已有 pair
  ID、一个非 FRA 白名单目标和紧邻的 submit 序号 `on+1`；off 为 `on+2`。
- on 前须有紧前一条相同动作/目标的成功 native legality+gate、相同世界和
  日期，并仍在其有效期。submit 仍执行原有原生合法性和所有权检查。
- native 永久 claim 与 pending grant 持久审计必须先于 handler。pending
  先存入内存，任何中断保留原绑定。on 成功才进入 armed。
- 窗口内，只允许精确一次 bound submit 和之后精确 matching off。其他
  pair、legality、speed、fixture、on 及 no-native 诊断都在 claim 前拒绝；
  不能借诊断消耗预留序号。未知结果永久冻结，不能自动重发或补 toggle。
- 已知 submit transport/ownership 仅允许继续关闭流程，不证明 AI 已读取
  override。off 正常返回并观察 flag0 仅证明 reset。之后还必须有持久、
  健康、暂停、flag0 的新 frame 才解锁。独立正向 RO 也只证明所选 forced
  test 效果，不证明请求因果或自然 AI 接受。

## 固定原生合同

handler 仅 `0xe50180`，零参数为三个指针全 null 的 Vector24；结果为
fresh Result40。调用前后要求规范 flag0/1、已绑定游戏线程、暂停世界与
现有完整身份守卫。不直接写 `game+0x23a1`。

正常返回且结构/guard 可证后，对唯一返回 message 调用 engine String32
析构 `0x95660` 一次；不用外部 allocator，不 delete stack result。
handler 先翻 flag 后构造文本，故 callback / cleanup / 审计异常都可能
留下未知状态。此时不猜析构、不补 toggle、不重试，不声称自动恢复。

原 normal console 的缓存 gate、可选前置回调和记账没有因直接调用而
自动保留；此处永远是可丢弃研究夹具，不是严格单人来源或世界代次证明。

## 范围与验收状态

计划维持 22 原生源（9 C++ + 1 ASM，10 link objects）、12 独立宿主文件、
8 个原 hash 共享支持与 5 个字节不变的 fixture 文件。四阶段仍为
20 / 1 / 72 / 72。新 manifest schema3 必须绑定静态依据、精确源码清单、
独立 native review 和真实新 DLL/export，不能复用 v14 导出 RVA 为事实。

当前为可供独立源码复核的未构建候选。41 项 Python 离线测试已通过，覆盖
实际协议、完整四阶段及窗口日志回放、临时目录独占发布/重放、HTTP 内存分派、
合成 PE 导出与 schema3，以及已构建/有会话目录的写保护。测试曾指出新
EU4LAB/3 与旧 HTTP 的十字段内部校验不兼容；现仅在新 v15 adapter 覆写
严格 pair 校验，并补入三个固定哨兵。八个旧 shared support 没有修改。

`test_window.cpp` 提供实际原生头文件状态机的后续隔离测试源，尚未编译或
执行。本 README 不将 Python 仿真当作 C++ 编译、SEH/allocator/native
生命周期、handler 或游戏效果测试。候选 `runtime_verified`、严格 SP、
可靠 world generation、自然 AI 接受和 production 均保持 false。

## 文件与复核入口

- `candidate-index.json`：47 个拟输出文件的完整 SHA/大小；31个复制来源中
  19个产生文本差异，逐份补丁在 `diffs/`，其余内容不变。
- `native-source-review.json`：22 个 native 源清单和既有独立 ABI 审查绑定；
  只是本次集成的源码合同清单，不冒充独立集成审查。
- `validation-results-r2/validation.json`：CreateNew 保存的准备检查和41项测试
  实际退出码、输出及全部候选输入哈希；原49个 frozen 输入前后核对。
  `validation-results/` 保留首轮通过结果；r2只同步这段文档的准确差异数量
  和验证器输出目录选项，47个输出及其索引没有改变。
- `assets/` 是新增严格协议头和接受日志验证器的生成源；`native-core/`
  两文件由独立原生代理提供并与镜像逐字节一致。
- `prepare.py --check` 只验证现有候选。`--refresh-candidate` 仅生成本目录
  `files/` 和差异，任何实际或镜像 v15 runtime 产物出现即拒绝生成；
  不提供物化、编译、加载、请求发布或游戏访问选项。

在仓库根运行（只读检查/纯离线测试）：

```text
python -B work/candidates/v15-acceptance-control-implementation-r2/prepare.py --check
python -B -m unittest discover -s work/candidates/v15-acceptance-control-implementation -p test_*.py -v
```

未来独立复核、物化和构建均须另获根代理授权。候选 formal build 脚本额外
要求 `EU4_V15_ROOT_REVIEW_APPROVED=1`，并拒绝既有 DLL/manifest/session；
此环境变量不是本轮构建许可，也不是原生效果证据。

## 拟用请求次序（未执行）

先以已有 `pair <action> --target <TAG> --mode legality_only` 获得明确
legality+gate，并留在暂停、同世界和同日期；其原 TTL 必须仍有效。
若这条序号为 N，则显式 `accept accept_on` 用 N+1，固定绑定同 action/TAG
和 `bound-submit-sequence=N+2`。唯一 pair submit 为 N+2，matching
`accept accept_off` 为 N+3（同一绑定）。所有 CLI 仍要求显式 PID+creation
和 `--publish`；默认仅计划。接受控制没有 HTTP endpoint，HTTP 只可投递
原36项中的精确已绑定 pair，默认 loopback 端口8771、`/research/v15`。

已知提交所有权且 flag1 可以执行 mandatory off，选定 RO 效果仍 unknown
不阻挡安全关闭。不得因为缺少效果而重发。handler、cleanup、audit 或
ownership 任一未知，则终态冻结且不补 toggle。关闭仅在 off 完整返回、
持久 wrapper 和之后的健康暂停 flag0 frame 都成立后确认；它不证明
异步 AI 在窗口内读取过 override。最终独立实验审查仍须另验正向 RO。

## R2: strict replay repair, native bytes unchanged

The original candidate review `3143e610…7247` and its 41 passing tests are frozen. Independent review `5c7b5cbe…d5fa6` nevertheless reproduced four full-reader invalid logs and one wrong enum: already-entered begin, unbound negative control dates, expired native claim, date-changing closing health, and `already_desired` mistaken for `callback_contract`. Those inputs and failed conclusions remain in the independent review directory.

This new directory changes only the generated acceptance replay and protocol reader/path binding, plus candidate generator/test/documentation sources. All 22 native sources, 8 shared support files and 5 fixture payloads remain byte identical. No native compilation, DLL build, materialization, process access or request occurs. The future schema3 manifest records the new Python hashes and binds this directory's native-only inventory; that inventory remains byte identical and its digest has no host/review cycle.

The replay requires all 30 actual native audit fields with strict types: begin stage4 has reason0, positive claim-bound before date, zero after date, observed original flag, unknown after flag, zero_arguments_confirmed true, no_native true, and all call/return/destruction/readback/audit flags false. Complete stage15 requires same-date readback and the existing known cleanup contract. All six no-retry/no-effect/SP/epoch assertions must be false. Closed no-native off accepts actual Reason11 only; callback_contract12 is rejected. Exactly one begin and one complete are permitted.

Each native claim, including ordinary pair/fixture/speed, must record a strict integer claim time at/after the preceding frame and `claimed_uptime < expires <= claimed_uptime+60000`. This is an offline claim-time check, not evidence of an exact callback-entry timestamp. Closing health validates original grant world/player/date/thread/pause before state mutation. Acceptance core logs do not contain world/player pointers: those are bound via the audited claim frame and immutable pending grant plus the pinned native guard; no new pointer observation is invented.

The initial R2 validation contains49 passing tests. The final suite adds a direct comparison against pinned native printf keys and Reason/Stage enums (50 total), with tiny synthetic streams/tempfiles only. `r2-lineage.json` binds every old candidate file and its independent review. `r2-delta.diff` records only the two changed proposed Python outputs; `r2-output-comparison.json` records every output hash and unchanged groups. An initial edit script failed to match the escaped generator string before making that change; it ran no tests, and its note is retained.
