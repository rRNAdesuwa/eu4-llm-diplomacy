# 议和条款正当性与释放国家净OE

## R70补充：国家条款与金币组合已查询并实际发送

国家条款现在可以与金币放入同一和约。法国要求勃艮第释放皮卡第并支付1金币、法国让步释放香槟并支付1金币，两种方向都已取得完整原生预览。组合预览分别保留金币承担国、释放国、外交点和各国净OE。新能力声明为 `native_peace_country_money_query`，旧安装继续返回明确的能力不足原因。

法国随后实际发送了一次“释放皮卡第加1金币”。勃艮第原生AI拒绝，请求和回应均保留同一条款、金额和战争；战争继续、省88及89仍归勃艮第，金币结算额为0。终态集中保存和16项核对通过，重新打开结果journal后返回内容完全相同。参见[实际发送与回应](../work/runtime/r70-country-money-execution-20261020-001)、[保存字段](../work/runtime/r70-country-money-save-fields-20261020-001/report.json)和[结果重开](../work/runtime/r70-journal-reopen-20261020-001/report.json)。

[R70查询批次](../work/runtime/r70-country-money-queries-20261020-007/report.json)包含战争发现和15份原生结果，覆盖两方向组合及“释放国家、完全吞并、金币”三条款负例。后者因完整吞并候选不齐而没有应用请求，公共接口保留具体原生结果并撤回费用可用性。最终报告以原事件重新完成校验和完整工具投影，0次重发查询。其余国家条款与割省、赔款等旧条款的混合组合继续按单独能力范围开发。

统一查询现在可以按具体条款对象返回CB正当性，并计算释放国家后双方的净过度扩张。R69实际查询中，法国取得省份88被原生判断为正当；释放皮卡第被判断为不正当。释放皮卡第会转移省份88、89，勃艮第OE从12%降至0，皮卡第新增OE为0。

## AI如何读取条款正当性

继续使用原有 `inspect_diplomatic_action` 和完整 `peace_context`。例如，法国向勃艮第要求释放皮卡第：

```python
inspection = api.inspect_diplomatic_action(
    "release_nation", "FRA", "BUR",
    parameters={"peace_context": {
        "war_id": war_id,
        "direction": "demand",
        "terms": [{
            "action_id": "release_nation",
            "country": "PIC",
            "source": "BUR"
        }]
    }}
)
```

`peace_consequences.justification.terms` 按条款返回：

| 字段 | 含义 |
|---|---|
| `action_id` | 条款类别，例如 `cede_province`、`release_nation` |
| `province_id`、`object_country` | 本条款涉及的省份或国家 |
| `selected` | 该条款是否属于本次实际选择的内容 |
| `status` | `justified` 正当、`unjustified` 不正当、`unknown` 尚未取得可靠结果 |
| `complete` | 是否已完整取得本条款的判断 |
| `source` | `native_rule` 表示判断来自游戏原生规则 |

`selected_terms_status` 汇总已选内容：全部正当时为 `justified`，包含不正当条款时为 `unjustified`，缺少判断时为 `unknown`。白和平没有需要汇总的有效条款，返回 `not_applicable`。

正当性与合法性分别读取。`unjustified` 表示CB未使该条款成为正当要求，游戏可能仍允许玩家付出外交点要求该条款；能否选择或发送仍由 `legality` 判断。外交点费用继续读取 `peace_consequences.diplomatic_power`，数值为0也不能反推全部条款正当。

引擎会在白和平对象中保留零金币占位项，并把它的内部选择位置为真。公共查询排除这个零金额占位项，同时用 `native_selected` 保留原始位。明确索取金币时，该金币条款仍正常参与正当性汇总。

当前判断覆盖常用条款所用的18类原生对象。完全吞并由多条割省组成，白和平没有独立对象。引擎候选中出现其他内部条款时，`unsupported_count` 记录数量，整个候选集的 `complete` 保持为假；已取得的逐条判断仍分别返回。宣战前的CB声明表继续由R66接口提供，本功能在实际战争和完整和约背景下对具体对象求值。

## 释放国家的净OE

`peace_consequences.overextension.countries` 分别返回来源国、释放国及其他受影响国家的当前、增加、减少、净变化和预计最终OE，并列出得失地省份。程序读取释放国家的完整核心省份链，只计算当前由条款来源国拥有的省份。

本批采用同一场景的实际预览：

| 条款 | 来源国失去的省份 | 勃艮第OE变化 | 释放国新增OE |
|---|---|---|---|
| 释放皮卡第 PIC | 88、89 | 12%→0 | 0 |
| 释放埃诺 HAI | 91、1743、1866 | 12%→12% | 0 |
| 释放卢森堡 LUX | 94 | 12%→12% | 0 |
| 法国让步释放香槟 CHP | 185、186、4390 | 勃艮第维持12%，法国维持0 | 0 |

皮卡第方案降低勃艮第OE，因为转出的省份88是勃艮第的非核心省份；皮卡第取得自己的核心省份，因此新增OE为0。埃诺和卢森堡方案转出的省份没有贡献这12%的OE，所以勃艮第仍为12%。

例如，勃艮第在皮卡第方案中的字段为 `current_raw=120`、`lost_raw=120`、`delta_raw=-120`、`projected_raw=0`。`scale=1000` 表示raw值除以1000得到比例，120对应12%；也可直接使用 `current_percentage_points`、`delta_percentage_points` 等已换算字段。

## R69证据与验证范围

[最终查询批次](../work/runtime/r69-peace-rule-queries-20261020-004/report.json)保存了战争发现、12份取得原生结果的查询（含两项条款未应用负例），以及一项混合组合能力边界。预览覆盖两种方向的白和平和金币、四种释放国家及具体割省；两项受益国不匹配的请求明确返回未应用。报告复用之前已取得的原生事件，只对缺少的输入补查。[独立保存字段核对](../work/runtime/r69-release-oe-save-fields-20261020-003/report.json)按存档核心和所有者重建完整转移列表，四种释放方案全部匹配。[19类兼容批查](../work/runtime/r69-peace-family-20261020-001/report.json)共21次查询，通过原生事件和公共投影检查。约195KB的自包含[真实事件样本](../bridge/tests/fixtures/r69_peace_rules_real.json)覆盖原生校验、公共投影和完整工具字段回放，新增4项测试通过。

R69协议支持多个国家条款放在同一和约中，例如释放国家加完全吞并。R70已增加上述国家条款加金币的组合查询和实际发送；涉及其他旧条款的混合请求仍立即返回 `NATIVE_PEACE_EXECUTION_MIXED_INSPECTION_UNAVAILABLE`，后续按原生规则逐组扩展。

本批验证的是原生查询和后果预览。既有议和发送、接受、拒绝及实际所有权变化继续引用R61等历史验收；本次保存核对读取当前载入的源存档，没有新增业务发送、日期推进或专门重载验收。

最终整合回归[848项测试、639项子测试通过](../work/runtime/r69-final-python-unit-20261020-002/report.json)。交付文件与代码快照见[本批清单](../work/runtime/r69-rules-delivery-20261020-001/manifest.json)。

R70整合回归[853项测试、647项子测试通过](../work/runtime/r70-final-python-unit-20261020-001/report.json)，另有16项C++协议检查。自包含真实样本覆盖两方向混合条款及完整吞并未应用的组合，交付见[R70清单](../work/runtime/r70-country-money-delivery-20261020-001/manifest.json)。
