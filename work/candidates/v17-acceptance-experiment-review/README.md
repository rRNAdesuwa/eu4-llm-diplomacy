# v17 停止会话实验审查器候选

本目录只实现离线证据审查；没有访问游戏、启动服务、发布请求、构建 DLL 或运行实际实验 case。成功的 synthetic 回放不代表 v17 实测成功。实际 v16 的无 begin、`reason=6 / stage=1 / no_native=true` 终态失败仍须拒绝，不能填补为成功的接受窗口。v15 初始空字符串失败同样不能通过规范 `none / none` 规则。

`reviewer.py` 使用冻结 v17 精确 pin 修复候选中的真实 EU4LAB/3 codec、四阶段 reader、acceptance validator。`base.py`、`preflight.py` 是冻结 v14 directional r3 和 preflight reviewer 的独立、有差异文件的副本。所有作用域由显式 case 的 `scope` 指定：PID、完整 creation、world、线程、初始日期、DLL/manifest SHA、BridgeStart RVA、精确 prefix bytes/SHA 和 preflight case/summary 路径。不会查找 latest、接受旧 purpose，或把 v14 的旧身份当 v17 身份。两个内部副本不能单独作为命令入口。

本修订另绑定旧 v16 完整回放反例及 v17 原生源码顺序：`frame_tick` 先递增 frames、写可选健康日志、再消费 mailbox。每个 on/off 的完成帧必须是精确整数，并满足 `前健康帧 <= completion_frame < 首个后健康帧`；不允许跳过第一条后健康而借用更晚帧。完整停止日志中缺后健康边界也拒绝。新增约束只位于本目录 reviewer；不改冻结宿主或 acceptance validator。见 `completion-frame-contract.json` 和 `completion-frame-only.diff`。

审查范围：

- 完整停止日志、持有同一进程句柄所得的正常退出证据、精确 session 文件库存；残留请求、未列出文件、缺失永久 claim 或 host-intent 均拒绝。
- 20 lifecycle、1 default-owned-empty-peace、72 preview、72 command 的固定无发送前缀；四个阶段逐一复核原始声明、实际记录和后续健康帧。owned-empty 是默认对象生命周期范围，不是战争、和平提议、白和执行或持续全堆状态证明。
- 每个序号的首次发布、13 字段原始 ASCII claim、原生记录和完成状态。每个缓存 status 必须对应真实日志前缀及该时刻 pending、lease、所选请求、接受窗口。允许停止前较旧但精确的完成前缀，不允许借用后来的关闭状态。
- 初始 fixture_on；一个有界接受窗口。若 legality 序号为 N，on/唯一绑定 submit/off 分别是 N+1/N+2/N+3。on 的 claim 与 durable pending 各自必须尚未过期，且旧 legality 仍新鲜；所有者、动作、目标、世界、日期、线程均不得变化。窗口内不能用 no-native 诊断消费预留序号。
- 进入 handler 或 submit 后，正常返回、销毁、审计或所有权不明确即拒绝；不自动重试或补 toggle。off 成功后还必须出现更晚的暂停、flag0、closed 健康帧，并保留历史 action/target/序号。off 只证明观察到重置，不证明异步 AI 确实使用了 override。
- speed 仅接受完整监督 lease 与回到暂停的证据，保持 r3 的严格 deadline、`mailbox_ready = !lease_active`、日期与 supervisor 绑定。运行租约必须在 off 及后续健康帧之后。撤销授予停泊权须在更晚游戏日期进行。

只有三个 selected-effect submit 方向可被本候选审查：`offer_fleet_basing_rights`、`revoke_fleet_basing_rights`、`insult`。其他 pair 可记录固定协议的 legality/guard 拒绝，但实际 submit 会被拒绝。每个提交都必须提供独立 before、after、comparison；返回值本身不算效果。

停泊权沿已审十方向 observer 的角色定义：POR/NAV 等目标为权利持有者、FRA 为授予者；撤销必须从有关系变为无关系，原本 absent 不算成功。侮辱复用已审 ordinary-insult observer：两遍类型精确的 `insulted` 新对象及目标对 FRA trust 减 5，固定普通侮辱 index=-1；不能只见 modifier 就宣称成功。comparison 由原 observer 重新计算并比对精确输入 hash。有效但未观察到授予关系的方向仍可记 unknown；非法/不一致的观察会拒绝审查。

授予方向带 `forced_test_acceptance_window=true`，只说明位于审计过的临时窗口。`natural_ai_acceptance_verified`、`asynchronous_override_use_verified`、请求因果、严格单人、世界 epoch、生产执行始终 false。保存/重载在此最小 reviewer 中明确不支持，`persistence` 必须为空；未来需要独立绑定的持久性审查，不能复用实验结果替代。

输入上限：case 512 KiB；最多 512 个运行 artifacts；每个 8 MiB、合计 64 MiB；完整日志按行有限解析。代码依赖另限最多 256 个、单件 8 MiB、合计 32 MiB。不会把大型存档作为普通 artifacts 读取。输入拒绝重复路径、链接、路径跳转、未知 selector、bool/int/float 混淆，并在结束前重新核 hash。

纯离线验证命令（项目根）：

```text
python -B work/candidates/v17-acceptance-experiment-review/prepare.py --check
python -B -m unittest discover -s work/candidates/v17-acceptance-experiment-review -p test_*.py -v
```

未 final 的模板由 `reviewer.py template --output NEW.json` 用 CREATE_NEW 生成。`reviewer.py preflight --case PRESERVED_PREFIX_CASE.json --scope SCOPE.json --output NEW_SUMMARY.json` 仅用于将来明确保存的前缀；正式停止实验入口是 `reviewer.py review --case FINALIZED_CASE.json --output NEW_SUMMARY.json`，复核入口是 `reviewer.py check --case FINALIZED_CASE.json --output EXISTING_SUMMARY.json`。本轮没有调用后三个入口去读取实际 case。

成功 synthetic fixture 包含完整真实四阶段解析、fixture、legality/on/submit/off、后续关闭健康帧、监督 speed、后日期撤销和 ordinary insult；只替换磁盘 build 的 synthetic 元数据，不 mock 阶段/窗口/效果验证器。测试还覆盖初始空串、无 begin 终态失败、no-native 伪关闭、重复/异进程序号、过期、错角色、未来状态借用、日期或字段类型错误、未知所有权和残留请求。
