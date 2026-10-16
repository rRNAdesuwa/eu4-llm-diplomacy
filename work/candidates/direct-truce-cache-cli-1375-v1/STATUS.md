# 当前验收状态

此独立只读CLI已封存，并通过源码审查、封存差异审查和真实游戏查询审计。固定来源清单SHA256为 `47cfc947bac30cf47eaf9aa09b46bc423a0cefb49168930b03af4be6a2b47bb8`。目录内冻结的README描述源码准备时点；本页记录后续验收，不参与运行时授权或改变任何source pin。

在项目根目录运行：

```powershell
python -B work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py check
python -B work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py catalog
python -B work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py status --pid 80340 --creation 01dd5c075fcf8c26 --actor FRA --target AUV
```

示例身份来自本次测试进程；换进程必须提供真实PID/creation。需要手动暂停，游戏无需前台。工具只读当前方向的pair+45 mask1，不发送任何动作。

退出0表示查询成功，缓存false同样可以退出0。读取 `direct_pair_cache_flag_set` 的 true/false/null；`selected_effect_verified` 和 `peace_completion_verified` 始终false。它没有核定完整关联国家判定、停战到期或某个议和请求的效果。

12个首次离线方法、4个独立fake反例通过。真实check/catalog和FRA↔AUV、POR↔BRI四方向status全部通过，四缓存均false；没有为获得阳性样本重发历史动作或写游戏字段。四次observe阶段约5.65–5.83秒，Job CLI完整范围约7.78–7.91秒。

证据：[真实验收](../../reports/direct-truce-cache-cli-root-queries-20261015-r1/report.md)、[51 pin独立实采审计](../../reports/direct-truce-cache-cli-live-review-20261015-r1/independent-live-review.json)。边界和完整参数说明见[冻结源码说明](README.md)。正常结束清除本地handle，冻结实现未检查CloseHandle的OS返回值。

稳定15效果profile、3当前关系及完整战争图仍从[统一观察器](../../../docs/runtime-observer-1375.md)进入；本CLI没有修改其98pin清单。宣战、议和执行器仍在逆向。
