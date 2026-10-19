# 外交行动定向验证与宣战、议和逆向增量

2026-10-14：从上轮固定结果存档继续，6项新ID定向测试完成；5项选定效果通过实时、保存和新进程冷重载核对，换继承人被原生full+88正常拒绝。当前120绑定中44项已有独立历史或补测选定效果证据，不能称全部120效果通过。

## 本轮实测

玩家保持FRA，暂停日期1445.2.22；测试进程19876/creation01dd5b2fd032fd53，V31 build-7。没有修改原生内存或重发原批次。普通冷却、外交官ID排除容器、精确依赖和加载Mod分别读取；39请求脚本定义均找到。新6条使用`--test-only --ttl-ms180000`一次发布。

| 行动 / 国家 | 结果与选定效果 |
|---|---|
| trade_favors_for_gold，FRA→SCO | 派发；FRA/SCO金币分别+457736/−457736原始milli |
| trade_favors_for_men，FRA→SCO | 派发；兵源字段分别+2040/−2040原始milli |
| trade_favors_for_sailors，FRA→SCO | 派发；水手字段分别+126756/−126756原始milli |
| trade_favors_for_war_prep，FRA→SCO | 派发；SCO prepare_war=FRA，期限1446.2.22 |
| trade_favors_for_heir，FRA→SCO | full+88正常false，清理闭合；没有派发或新继承人效果，首个失败条件未知 |
| revoke_march，FRA→ORL | 派发；march→vassal、领主仍FRA；法国稳定度3→2 |

三项资源的FRA/SCO合计分别守恒；SCO→FRA人情98.160→94.160，为整批合计变化，没有逐条采样证明各项独立扣费。全部6份回执及持久开发预留逐项重构：5×7+1×4=39对原生调用全部normal/exception0；全部ownership_closed、owned_live/quarantined/adapter_fault为0。5项派发永久禁测；继承人干净拒绝只保留修复条件后另行定向测试的资格，不是自动重试许可。

证据：[实时文件审计](../work/reports/diplomacy-corrective-20261014/runtime-file-audit.md)、[独立保存/冷重载验收](../work/reports/diplomacy-corrective-20261014/cold-reload-verification.json)、[当前120项矩阵](../work/reports/diplomacy-corrective-20261014/current-action-validation.md)。实时审计在保存前封存，其saved/cold=false保持；后续成功证据单列。

## 保存与冷重载

用户save games目录新增`llm_diplomacy_1375_corrective_after_20261014.eu4`，42,716,535B，SHA256 `7594ffd44816d1754e871f3f46bc9b68d00e04f3896ff8c3efc42d622e3a1727`。旧日期文件先核对固定SHA再改名保留，命名unified_after原件不改。新存档由游戏UI保存；两份完整流式解析核对资源、人情、备战、依赖和稳定度。

61688/creation01dd5b34111e69c5冷载这个固定副本，无研究DLL、无新原生调用、无重发，仍1445.2.22/FRA/manual_pause1。两次RPM相同；5项选定投影及三个token冷却均与保存前保持。冷载进程正常退出，held-handle取得exit0；当前EU4进程为0。第一次进程在观察器取得身份前已不存在，失败空回执及错误记录保留，不能声称它exit0。

复核：`python -B work/validate_corrective_persistence_20261014.py --check`，54来源pin通过。原生44源码pin、manifest和DLL保持。两个存档解析进程和退出观察器均已收齐。

## 修正跨版本禁测遗漏

原53只是旧最终批次的干净拒绝余项。232份有界历史输入/2,003条相关观测发现两项此前已派发：提供驻港权（V30、V27等），撤销驻港权（V17 seq8）。两项均排除，不能利用较新的拒绝记录重开测试。最小证据含5个固定来源与精确行号；Python发布前增加散列/过程身份/sequence/派发事实核验，缺失或变更即拒绝，普通调用语义保持。

最新分组：35历史选定效果、4前轮选定效果及重载、5本轮选定效果及重载、25其他原派发、2补认历史派发、2稀疏拒绝阻断、1其他未知、46修复候选。46中继承人本轮正常拒绝1，其余45本轮未测。原唯一批次41派发/77拒绝/2未知、38项历史成功台账及旧矩阵不改。

发布策略和相关HTTP/V31检查共53个不同Python测试通过；先后39项和14项，首轮发现测试类重复收集后的52次执行不计入该总数。新测试覆盖历史源缺失/变更、删改名单和换TAG/ID仍在runtime及预留前阻断。

## 原生逆向

[宣战与议和合同](war-peace-api-1375.md)补15条静态观察：普通宣战GUI发送回调、稳定成本确认、wrapper/发送器交接、三种盟友向量及联动；议和完整检查和独立日期检查、pending enforce_peace与第二战争索引的null风险。三个有界脚本的检查和来源pin通过，仍未开放宣战/议和执行器；当前CB、完整目标/条款、世界生命周期、下游所有权及实际应用仍待闭合。

另补6条人情前置观察：[冷却与No Heir布局](../work/reports/diplomacy-corrective-20261014/native/README.md)。前三个资源动作使用独立actor token冷却，end为指针，等号不阻断。country+e00参与破产期限检查，旧last_favor_date名称错误，封存旧观察保持原文；本轮最终观察器改为country_raw_e00。非null的No Heir对象也可表示无有效继承人，不能把指针非零当作拒绝原因。
