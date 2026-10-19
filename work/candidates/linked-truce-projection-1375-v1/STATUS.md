# 当前验收状态

后续独立[第二版](../linked-truce-projection-1375-v2/STATUS.md)增加 header61 非零的第四条路径，并完成 POR→ORL 一次新查询及63pin独审。本页及v1原unknown保持，不修改冻结实现。

此独立只读 CLI 已完成源码、封存差异和真实采样的独立审查。固定生产清单 SHA256：`176cb7ce2638767be0b98afbe673c06f08fa6430db41cb267a5eb3996b53da47`；代码 SHA256：`873ea638227e7543dbe2a18d74097559083756f08bc3186c945412c6d9907225`。冻结 README 保留源码准备时点；本页只记录后续状态，不参与运行时授权。

在项目根目录运行：

```powershell
python -B work/candidates/linked-truce-projection-1375-v1/linked_truce_projection.py check
python -B work/candidates/linked-truce-projection-1375-v1/linked_truce_projection.py catalog
python -B work/candidates/linked-truce-projection-1375-v1/linked_truce_projection.py status --pid 80340 --creation 01dd5c075fcf8c26 --actor FRA --target ENG
```

示例身份来自本次实测；新进程需提供真实 PID 和 creation。采样要求手动暂停，无需游戏前台。工具使用 QUERY/VM_READ，在外部计算三个已解析正常路径的返回值，不调用原生停战检查函数。

| 实测国家对 | 路径 | 输出 | 退出码 |
| --- | --- | --- | --- |
| FRA → ENG | 目标严格独立 | `computed_selected_native_return_projection / false` | 0 |
| FRA → ORL | 目标关联到 actor，且定义 byte11a 非零 | `computed_selected_native_return_projection / false` | 0 |
| POR → ORL | 定义 header61=1，超出本版本三路径 | `unknown / null` | 2 |

第三组不是否定结果；本版本没有解析这条非空分支，也没有自动重试。其他未知包括关联缓存为真后所需的外部属性调用、未证明布局、身份或代码变化。true 和 false 都可代表计算成功，均不表示外交动作已完成。

21 个新离线方法首次通过，check/catalog 各一次通过。三组真实查询共 8784 次选定读取、165558 B，六份完整 1380 项国家表、完整句柄、typed root、dependency 双索引、原始 U 字段及五个 code/K blocks 前后均在独立文件重放中一致。每组另有 host 92 reads/600 B 和入口 PE 检查 8192 B，不混入选定计数。observe 范围为 7.856/6.651/6.555 秒；CLI Job 范围为 11.719/10.094/9.610 秒。

所有 Job 已结束、active=0，无后台监听器。没有 Frida、游戏原生调用、字段写入、请求、保存或重载。正常 context 退出后本地 handle 清空；CloseHandle 的 OS 返回值未核验。双遍相等不是原子快照或对象寿命保证。`selected_effect_verified`、`actual_native_predicate_evaluated`、`expiry_verified`、`peace_completion_verified`、`native_ready` 与 `lifetime_lease` 始终 false；只读 nonce 不是安装会话。

证据：[三组真实回执](../../reports/linked-truce-projection-root-queries-20261015-r1/receipt.json)、[56 pin 独立实采审查](../../reports/linked-truce-projection-live-review-20261015-r1/findings.json)、[源码审查](../../reports/linked-truce-projection-source-review-20261015-r1/independent-source-ready.json)、[封存差异审查](../../reports/linked-truce-projection-production-review-20261015-r1/production-passed.json)。稳定观察器仍为 [eu4_observer.py](../../../tools/eu4_observer.py)，其 15 请求效果 profile / 98 pins 未改变。
