# 十族公开参数候选

本目录只提供 `TenFamiliesDraft/1` 的 JSON 描述、严格形状校验和 unsupported 草案。它不是正式 API 新版本，不修改现有 Contract/1、Contract/2 或 274 项目录，不注册 backend，不创建数据库，不预留 request_id。所有十族的 native legality / runtime / execution / production 仍为 false。相同 request_id 可以产生不同草案，不具有已持久化的幂等语义。

| 动作 | 草案参数（另需 actor、target TAG） | 证据范围与缺口 |
|---|---|---|
| claim_throne | 无 | 静态单边王位宣称；不保证继承战争结果 |
| sell_province | province_id、price_integer | 整数金币 0..2147483；接受路径再乘 1000。范围仅避免已见 signed32 溢出，不代表原生完整合法范围 |
| enforce_peace | opposing_country | TAG 对应未来完整国家 handle，绝不是 war_id；限制第三国不同于双方。拒绝路径可能加入战争 |
| threaten_war | province_id、taker_country | taker_country 必须等于 actor。正常 caller 是 local +80→wrapper→bfe50；未闭合正常 full +88 caller。拒绝可能宣战 |
| trade_favors_for_gold | 无 | 金额由原生动态计算，不接受 amount |
| trade_favors_for_men | 无 | 人力由原生动态计算，不接受 amount |
| trade_favors_for_sailors | 无 | 水手由原生动态计算，不接受 amount |
| trade_favors_for_war_prep | 无 | 备战不等于实际开战 |
| trade_favors_for_trust | 无，仅表达 pair intent | **binding unclosed**。+40 是 favors_milli DWORD（global×1000），+44 是 trust_int DWORD（另一 global）；未验证当前值，不默填 10/5，不开放自定义两数。旧 public `favors` 参数迁移仍未闭合 |
| reduce_relations_favor | third_country | **selector unclosed**。只检查 TAG 语法；普通 AI 构造仍为无效第三国且评分为零，不能宣称正常参数化选择/发送已闭合 |

TAG 仅 `[A-Z0-9]{3}`，不表示存在或已解析为活国家。province_id 为 1..INT32_MAX 的语法整数，不证明省份存在、归属、战争或可转让。公开输入拒绝完整 handle、原始地址、RVA、state、value、envoy、TTL、线程、取消开关与任意额外字段。JSON bool/float 不可替代整数。

`native_descriptor` 中 offset/vtable/token 仅用于绑定静态证据，不是可输入执行地址。虚槽 full preview 的 false 参数/false 结果与取消不同；预览及拒绝也不保证无副作用。

`legacy-parameters.json` 是生成时十项旧 schema 的有界历史快照。其余正式 API 文件不读取、不导入、不永久 pin。候选的新命名（price_integer、opposing_country、显式 taker_country）只在此目录生效，没有自动把旧 price / war_id / defender / favors 翻译成新语义；不影响既有客户端。

```python
from catalog import describe, validate, request
describe('enforce_peace')
validate('sell_province', {'actor':'FRA','target':'POR',
                         'province_id':183,'price_integer':100})
request({'contract':'TenFamiliesDraft/1','request_id':'review-1',
         'action_id':'threaten_war',
         'parameters':{'actor':'FRA','target':'ENG',
                       'province_id':183,'taker_country':'FRA'}})
# status='unsupported', draft_only=True, request_id_status='not_reserved'
```

离线验证：

```powershell
python -B work/candidates/ten-families-public-contract-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/ten-families-public-contract-1375 -p test_*.py -v
```

输入是已封 favor6 静态报告、WAR4 原静态报告与 R2 所有权模型及独审。无新 PE 解码、进程/游戏/UI/引擎调用、编译或 DLL。`generate.py --check` 从这些固定资料重现 contract.json；`prepare.py` 另核候选文件。后续需要独立审查，这份小候选不承担实际执行或完整服务设计。
