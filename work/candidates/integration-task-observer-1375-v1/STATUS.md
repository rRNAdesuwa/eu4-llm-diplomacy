# 当前验收状态

此独立 CLI 已完成源码、生产清单和两组真实只读查询的独立审查。代码 SHA256：`ec576a21a4018fa1b91d0864990b281a7a075ed3761404d9bdd7559de8b25cb9`；生产清单：`4b17a5862dbe4461497c6d187d6cb9dc0efb16a489fbb7048f6658ca5794cb9e`，21 个源码 pin。本页只记录后续状态，冻结 README 保留准备时点。

```powershell
python -B work/candidates/integration-task-observer-1375-v1/integration_task_observer.py check
python -B work/candidates/integration-task-observer-1375-v1/integration_task_observer.py catalog
python -B work/candidates/integration-task-observer-1375-v1/integration_task_observer.py status --pid 80340 --creation 01dd5c075fcf8c26 --actor DAN --target NOR
```

示例 PID/creation 来自本次测试，新进程须提供真实身份。采样要求手动暂停，游戏无需前台。只读 QUERY/VM_READ，不调用 getter 或整合函数。

状态包括 `selected_task_present`、`selected_index_absent`、`unknown`。存在要求选定双方索引指向同一 P、vt/完整端点/P28 符合限定原像；P20 只报告 raw DWORD，不称日期或进度。缺席要求双方均无所选键；其他虚表、单侧或变化返回 unknown。退出0可表示存在或缺席，均不是整合、取消或最终完成的效果证明。没有原请求回执、发送前基线和当前对象变化的关联，不提供请求完成结论。

24 个新离线方法及首次 check/catalog 通过，独立另一个非空索引中所选键缺席的 fake 通过。源码审查92pins通过。首次通用生产清单缺少冻结 gate 所需的 candidate review 关联，被审查阻断，未做实采；保留原像后仅补该 metadata，21源码 pin 不变，R2生产差异9pins通过。

FRA→ORL 和 DAN→NOR 两次真实查询均返回 `selected_index_absent / false`，errors为空，正常退出后才提交。35pin独审逐条重放每组2994reads/51980B，包含共享host前后、两完整1380指针表、选定国家完整身份、embedded root/关系行和双向空索引、四loaded code/relocated slot的前后检查。1380表项非零不等于全部国家均经过typed身份验证；完整typed验证只针对所选国家。

入口PE8192B另计、未进journal。内部observe4932.003/5099.312ms，完整CLI Job7.063/7.204s；前者不包含run初始来源验证与Libraries构造，不是纯RPM时间。两Job累计各2进程已收齐、active0，最大peak47153152B，无监听器。CloseHandle的OS返回值未核验；两遍一致不是原子快照或寿命保证。

本次没有活动整合任务的真实阳性样本，也没有新外交请求、Frida、native调用、游戏字段写入、保存或重载。`selected_effect_verified`、`integration_completed`、`native_action_mapping_verified`、`native_ready`、`persistence_verified`、`lifetime_lease`、`atomic_snapshot`保持false。只读nonce不是安装会话。

证据：[真实查询](../../reports/integration-task-observer-root-queries-20261015-r1/receipt.json)、[35pin实采独审](../../reports/integration-task-observer-live-review-20261015-r1/findings.json)、[源码独审](../../reports/integration-task-observer-source-review-20261015-r1/independent-source-ready.json)、[R2生产差异](../../reports/integration-task-observer-production-review-20261015-r2/production-passed.json)。稳定[15请求效果观察器](../../../docs/runtime-observer-1375.md)和原native执行模块保持。
