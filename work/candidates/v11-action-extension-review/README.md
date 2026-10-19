# 八类外交引擎增量审查包

本目录只生成隔离候选源码、差异和离线证据；没有修改 `work/native/v10`、`work/native/v11`、目录执行声明或生产 backend，没有访问游戏进程，也没有构建/加载 DLL。

## 可合并边界

`generated/` 恰好包含五个文件：`pair-engine-1375.h/.cpp`、`pair-probe-v6-1375.cpp`、`pair-preview-v6-1375.cpp`、`pair-command-v6-1375.cpp`。它们以完整 SHA 固定的 v10 五份文件为基础，保持原有所有权、SEH、线程、提交边界与无重试流程。合并者只取这五项或审查 `action-extension.diff`；**不要覆盖 v11 的 mailbox host、loader、manifest、协议或 CLI 修改。**

宿主/CLI/phase validator 必须独立同步：20 个 family、36 个白名单 ID；生命周期 20 项，预览与 command 各 72 项，即 FRA→ENG/POR 的 36 个真实模式。四类单向动作不得产生 false case。旧 24 个 ID 的 ordinal 未改变，但新引擎改用显式 `kModes`，不能继续使用 `index / 2`。

| 新 ID | family 索引 / native token | value |
| --- | --- | --- |
| warn | 12 / warningaction `2942` | true |
| insult | 13 / insultaction `2947` | true |
| form_coalition / leave_coalition | 14 / form_coalition `2de0` | true / false |
| support_independence / cancel_independence_support | 15 / support_independence_action `2f2e` | true / false |
| request_trade_power / cancel_trade_power_transfer | 16 / transfer_trade_power `2e09` | true / false |
| steer_trade / cancel_steer_trade | 17 / steer_trade `3778` | true / false |
| send_gift | 18 / giftaction `2948` | true |
| trade_favors_for_gold | 19 / trade_favors_for_gold `3bce` | true |

## 参数和日志

公开参数仍只有固定 ID 与已知 TAG：FRA/ENG/POR/NAV/FOI；不接受金额、比例、索引、指针或其他原生字段。

`fixed_gift_amount_milli=25000`（25 金币）、`fixed_transfer_fraction_milli=500`（50%）、`fixed_insult_index=-1`。贸易权 action `+44=0`。其他 family 对应日志项均为 0。旧补贴保持 `fixed_subsidy_amount_milli=1000`、`fixed_subsidy_duration_years=10`，只有补贴正/取消使用这两项。上述五个字段统一出现在 lifecycle/preview/command case 与 core begin/dispatch_intent/complete 日志。宿主应按确切 family 比较，不可用“出现在固定参数字典”来推断补贴。

人情换金币的 factory/clone/getter/0x40 大小已闭合，没有派生金额输入，不被排除。本候选保留原生计算和回复流程；不得向对象尾部写金额，不得把原生返回或国库差额称为该请求已接受或已经生效。

## 方向与拒绝条件

所有新增取消在分配前、setter 后、最终 dispatch 前重新采样并比较 `Binding`。支持独立同时绑定当前 dependency 对象、开始日期、overlord 完整 handle 与 definition 身份；保留实际 proposal 字段顺序。首版严格限已解析的 overlord TAG，以及 registry 对应 `vassal/client_vassal`、正确 EngineString 名称、definition `+11a` 非零。其他附庸类型和未知宗主明确拒绝；这不是完整支持独立类型覆盖。

两种贸易正向均要求双方向不存在当前对象。取消要求仅一个方向存在、双方索引指向同一对象、精确 vtable/type/full handle/start date/removed=0/特殊标志=0；贸易权进一步限比例 500。方向和对象信息纳入三次绑定；同时存在相反方向时拒绝。警告正向也拒绝覆盖已有双边警告。

包围网要求 actor 当前 coalition 完整 handle 与方向匹配，目标 linked list 前后链、尾部、count 一致，不在迭代中；删除节点不读取其国家对象。活动成员 slot 同时小于实际 database `+124` 的 lookup count 和 4096，上限 1024 节点。遍历前后重新检查 array/count；这些只是有界一致性检查，不是可靠 world epoch 证明。

`legality_only/dispatched/dispatch_unknown`、command clone 归属和原有提交前后处理不变。跨入 context submit 后不析构、重试；异常或不确定所有权冻结。旧阶段通过不能为新增八类提供运行验收。

## 复现与证据

从仓库根目录运行：

```powershell
python -B work/candidates/v11-action-extension-review/prepare.py --check
python -B work/candidates/v11-action-extension-review/verify_candidate.py
```

后者逐项验证 PE 的 96 个方法槽和 57 份前缀、生成结果及 72 项唯一模式矩阵，再以 MSVC `/std:c++17 /O2 /W4 /WX /MT /GS` 编译四个独立单元并运行伪内存测试。当前 377 项检查全部通过，包括真实 helper 的方向/重复索引/失效完整 handle/删除标志/实际 lookup 越界/依赖更换/单向动作白名单，以及所有 36 ID 固定字段日志与日志失败处理。伪内存可执行文件没有调用 `invoke`、游戏函数或打开进程。

`review.json` SHA256：`5a367293b5b71e327b0496f700a43c2db5f5922231aee486b8c5f3a1e871eee7`。

两份静态输入完整 SHA 固定在 `prepare.py` 与 `review.json`：`native-pair-extension-v11-1375.json` 和 `native-pair-extension-effects-v11-1375.json`。`validation.json` 记录实际编译输出、测试数量、生成/测试工具 SHA。`runtime_verified=false`、`execution_verified=false` 始终保留。
