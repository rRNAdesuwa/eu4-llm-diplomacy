# v7 外交锁下的授权宣战核对

日期：2026-10-05。修改已完成，19 项 Python 测试通过；新入口与 v7 DLL 同时运行的带锁宣战已通过运行验证，保存和重载尚未验收。当前使用固定 FRA→ENG 收复曼恩模板，不代表任意国家、CB 和目标省份的通用宣战 API。

## 问题与修改

实际有两层机制：模组 `declarewar` 的 `llm_diplomacy_locked` 条件阻止普通宣战入口；原生 v7 在 generic command 执行 hook 中只识别和平 action。v7 源码 `bridge_response_observe` 先核对 command vtable `0x1c814b0`，再核对 peace vtable `0x1c7b840`，非此类型直接透传。没有原生宣战专用锁或授权宣战发送器。

缺口是外部入口：此前 `bridge.compiler.ALLOWED_ACTIONS` 不允许 `declare_war`，harness 的 schema、validator、prompt、decision→request 映射也不支持它。`work/prepare_war_test.py` 是白名单外的手工脚本，并带有清锁重试分支。历史 `VALIDATION.md` 记录该脚本在 1445.02.10 未进入解锁分支即成功，`runtime/war-success.json` 有 ai=1、war=1、locked=1；该 JSON 本身不含完整分支日志，不能单凭它独立证明没有执行清锁。

本次为 compiler、harness、decision schema 和可选 planner 加入 `declare_war`。JSON 只允许 `id/action/target`，target 必须 ENG；CB 和省份固定为 `cb_core`、177。脚本要求法国仍为 AI、独立、有锁，两国存在、未交战、无停战、未结盟、有正确 CB，177 属英国且是法国核心。只调用一次 `declare_war_with_cb`，没有清锁或重新设锁效果。确认 `war_with = ENG`、锁仍开启、ai=yes 后才标记请求已执行和输出 applied；未满足条件或未产生战争输出 rejected。

`prepare_war_test.py` 改为复用正式 compiler，移除清锁重试，默认请求 `war_v7_01`，追加快照。诊断脚本采用相同请求 ID，并补上联盟和目标省份检查。它们都接受 `--request-id`。本次没有修改 v7 DLL、加载哈希或模组锁条件，保留原和平验收版本。

## 原生逆向证据

二进制 SHA256：`B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77`。以下地址全部为此版本的 RVA。

| 对象或位置 | 证据 |
| --- | --- |
| effect 参数解析 `0x629650` | 错误文本包含 `declare_war_with_cb effect`；解析目标句柄到 +0x38、CB 对象到 +0x40、目标省份到 +0x48 |
| effect vtable `0x1ca3678` | +0x20 指向上述解析器，+0x78 指向 `0x629b10` |
| effect 执行 `0x629b10` | 有效国家句柄、已交战和 CB 检查；调用 `0xd9d090` 构造/枚举目标，按 CB 与目标省份查找对应对象 |
| `0x62a576` | 调用战争 action 构造器 `0x5004b0`，传入攻击方句柄、目标句柄、日期和原生目标对象 |
| 构造器 `0x5004b0` | 设置 vtable `0x1c80d90`，动作类型字段 +0x8=0x165；+0x10/+0x20 为上述句柄，+0x48 为 `0xd9a960` 返回的目标副本 |
| `0x62a583` | 把构造完成的 action 交给 `0x4ea850`；随后在 `0x62a590` 调用 `0x500590` 清理临时对象 |
| v7 的 hook | 仅识别 command `0x1c814b0` / peace `0x1c7b840`；战争 action `0x1c80d90` 与二者不同 |

据此可以判断脚本 effect 使用独立原生战争动作，现有 v7 和平过滤不识别该类型。不能把和平对象布局、state 编号或克隆授权槽直接套到宣战类；本次也没有这样做。脚本 effect 与正常外交按钮的全部费用/规则是否完全相同，尚未逐项验证，不能宣称普通宣战全规则等价。

证据文件在 `work/runtime/war-with-cb-parser.txt`、`war-with-cb-execute.txt`、`war-command-constructor.txt`、`war-command-dispatch.txt` 和 `native-war-path-evidence.json`。反汇编均按 PE 函数范围生成，最大约 3 KB 机器码，没有读取历史 350 MB 全量反汇编。

可重复核对：运行 `python work/inspect_native_war.py`。该工具先核对准确 EXE 哈希，再读取固定 vtable 槽、call 目标和构造器 vtable 指令；不附加游戏、不修改内存、不发命令。反汇编使用现有 `disassemble_native_function.py`，RVA 分别为 `0x629650`、`0x629b10`、`0x5004b0`、`0x4ea850`。

## 验证与当前等待点

`python -B -m unittest discover -s bridge/tests -v`：19 项通过。新增测试覆盖非法目标/任意 CB/省份字段拒绝、没有清锁效果、结果检查先于请求标记和 ACK、重放守卫，以及 harness 宣战决策不会错误落入 hold→snapshot。这些测试不替代游戏运行结果。

已将 `llm_war_test.txt` 和 `llm_war_diag.txt` 写入 local.env 指定的用户数据目录。用户建立新的 `llm_war_v7_before.eu4`：1445.1.1、玩家 POR，英法无交战/停战/联盟，cb_core 存在，177 为 ENG 所有的 FRA 核心。只读存档与实时身份检查后安装固定哈希 v7，BridgeStart=0。

用户在暂停游戏依次执行诊断与宣战脚本。全部诊断条件为1；日志 `locked_war_effect_entered` → `ACK|war_v7_01|applied`；其后完整快照 ai=1、war=1、locked=1，日期仍为1445.1.1。用户确认战争爆发，葡萄牙收到英国请求入战的通知。原生帧日志 country_valid=true、thread_changed=false，player=POR。证据已归档 `runtime/war-v7-validation.json`、`war-v7-game-log-evidence.txt`、`war-v7-native-runtime.jsonl`。此结果只证明手动 run 的带锁宣战与 v7 兼容；不证明宣战自动发送、存档重载或玩家 FRA 场景。

自动化缺口：v7 帧线程目前只消费 whitepeace/gold 请求文件，没有 war 请求消费器。harness 虽能生成 declare_war 脚本，仍不向游戏提交。完全自动执行需要单独研究原生战争构造与发送或固定脚本执行入口，再在帧线程消费有边界的请求；不能从外部注入线程直接调用未验证的游戏接口。需要新 DLL 和新进程，不能热替换现有 v7。

玩家 FRA 不支持当前流程：脚本的 ai=yes 检查拒绝玩家法国，原生授权加载器的 player=POR 检查也拒绝。若用户希望玩家法国也由 LLM 辅助发外交，应先明确新的控制角色，再给人类法国设计独立受限入口；不能静默移除现有 AI 与身份检查。

运行验收步骤：核对指定存档条件，启动并保持暂停，安装固定哈希 v7（如玩家不是 POR，现有加载器会拒绝，应单独处理实验身份），执行 `run llm_war_diag.txt` 检查全部条件，再执行 `run llm_war_test.txt`。核对 war_v7_01 applied、快照 locked=1/ai=1/war=1、实际英法战争与战争目标；重放同一命令应 rejected。独立另存后核对战争、CB/目标、锁和 AI，再重载确认。没有这些证据前不更新为“v7 宣战实测通过”。
