# 当前验收状态

第二版已完成源码、生产差异和新增 D 路径的真实只读验收。CLI SHA256：`31afcf307f62d77ab8dedaf8d01e73617488f07543e348ecfa891facd7a951e0`；生产清单：`15a221ec3eb1d63f1598a9c5305d2cbfd50b7e2c8492fbb10ce695b27b28ee93`，27 个源码 pin。本页记录验收，不参与运行时授权；冻结 README 保留准备时点。

```powershell
python -B work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py check
python -B work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py catalog
python -B work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py status --pid 80340 --creation 01dd5c075fcf8c26 --actor POR --target ORL
```

示例身份来自本次进程，新进程须提供真实 PID/creation。要求手动暂停，无需游戏前台。四个限定正常路径在外部计算返回值，不调用游戏停战函数；不支持的条件继续 unknown/null。

新增 D 路径要求 actor 严格独立、目标与其关联国家的 typed dependency/双索引/完整端点有效、linked 与 actor 的 16 位 slot 不同、header61 非零和 loaded K15。它不消费 header60/62/63 或 actor-linked cache。POR→ORL 一次真实新查询返回 `computed_selected_native_return_projection / false`，退出0；此前 v1 的 unknown 原样保留，没有重复 v1 的三组采样。

12 个新 delta 方法首次通过，check/catalog 各首次一次通过。之后两处路径/lineage 元数据窄修均保留原像和回执；计算、采样和退出逻辑的 AST 未改，未重跑套件，旧结果明确为修正前源码见证。最终源码独审53pins、生产差异7pins、真实采样独审63pins通过。

新查询的2958次选定读取、56008B全部独立重放一致，包括两遍完整1380表、typed国家/完整句柄/双索引和五个 loaded code/K blocks。另有 host92reads/600B和入口 PE8192B，分开计数。observe4917.123ms，完整CLI Job6.985s；前者不含run初始来源验证和Libraries构造，不是纯RPM时间。Job2进程已收齐、active0，peak46350336B，无监听器。

没有 Frida、native调用、游戏字段写入、外交请求、保存或重载。正常退出清除本地handle；CloseHandle的OS返回值未核验。双遍一致不是原子快照或对象寿命保证。实际native predicate、完整停战、期限、议和完成、原请求效果、native_ready和lease均保持false，随机nonce不表示安装会话。

证据：[真实回执](../../reports/linked-truce-projection-v2-root-queries-20261015-r1/receipt.json)、[63pin原始采样独审](../../reports/linked-truce-projection-v2-live-review-20261015-r1/findings.json)、[最终源码独审](../../reports/linked-truce-projection-v2-source-review-20261015-r1/independent-source-ready.json)、[生产差异独审](../../reports/linked-truce-projection-v2-production-review-20261015-r1/production-passed.json)。原 [v1验收](../linked-truce-projection-1375-v1/STATUS.md)和稳定[15请求效果工具](../../../docs/runtime-observer-1375.md)保持。
