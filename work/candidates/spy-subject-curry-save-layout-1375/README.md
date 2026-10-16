# 固定 12 月 26 日存档布局

这是保存文件的布局研究，**不是** 11 月 11 日 UI 批测的持久化验收。用户局之后推进至 `1444.12.26`，正常菜单保存并退出；没有 held exit handle，所以不声称进程退出码或 FILETIME。没有运行游戏、进程读取、原生调用、存档修改或重载。

固定副本为 `llm_diplomacy_1375_spy_subject_curry_batch_20261008a.eu4`，36,756,072 字节，SHA256 `8a8f812ab9a33b8479f36007077e05a870128e79afa90961eac579340f1d8566`。实际路径从已固定 SHA 的 root snapshot report 取得，保存在本候选 `report.json` 的 evidence source 中。

`parser.py` 复用既有 `inspect_diplomacy_save.tokens/events/Capture`，每块 64 KiB，单 token 64 KiB，单 capture 128 KiB/4096 nodes，总 retained 4 MiB/32768 nodes，深度 128。总文件上限降为 64 MiB，未扩大旧界限。不会保存完整国家或整个文件到内存。只允许已知的顶层 `map_area_data { ... }` 裸键特殊语法；命名赋值、引号伪别名、重复容器和外交裸字段不能借此通过。

`research.py` 完整读到 EOF 并核固定 SHA/大小及文件 stat 前后相同；保留 38 个选定路径与 8,927 字节原始片段，每片段都有确切路径、行、起止偏移和 SHA。所有数字来自原 token，Latin-1 仅做字节可逆映射。`report.json` 含原 token 和规范化的选定布局；`exploration.json` 是初次有限路径调查，保留不改。

| 选定保存布局 | 本文件观察 |
|---|---|
| `countries.ENG.modifier` 五个重复块 | `corrupt_officials`、`reputation_sabotaged`、`discontent_sowed` 日期 `1449.11.11`；`merchants_slandered`、`recruitment_sabotaged` 日期 `1449.10.17`。不把不同日期改写为统一值，也没有 actor 字段。 |
| `countries.NAV.subject_focus` | `5`；另有 `overlord="FRA"` 与 `dependency first=FRA second=NAV subject_type=vassal`。 |
| `countries.NAV.subject_interactions` | 七个裸布尔值 `no yes no no yes no yes`，零基位置 1/4/6 为 true。已审内存合同的 embargo/scutage/divert 位索引也是 1/4/6，但保存 serializer 的位序尚未独立闭合，故命名位序验证明确 false。 |
| NAV 的附带保存状态 | `trade_embargoes={BUR}`，BUR 对应 `trade_embargoed_by={NAV}`，NAV→BUR `is_embargoing=yes`；NAV→FRA trade power `amount=1.000 is_enforced=yes`。这些只是同一存档字段，不能反推交互请求或完整副作用成功。 |
| `diplomacy.curry_favors` | `first=FRA second=POR start_date=1444.11.11 envoy=0`。 |
| `countries.FRA.diplomats.envoy` | 103 个条目，id 唯一；id0 的 `action=2 type=3`。未保存的 action 字段保留 null，不推断空闲。姓名保留原字节。 |
| `provinces.-227.diplomacy_construction` | `country=actor=FRA recipient=POR envoy=0 action_token=curry_favors once=no`，省份 owner/controller 都是 POR。`from_province=183 to_province=227 total=original_total=12 date=1444.11.23`。日期含义未作结束/过期判断。 |
| 当前 rival 重复块 | FRA 只有 BUR；BUR 为 ARA/FRA/ENG，日期均 `1444.11.11`。`enemy`、`historical_rivals`、`active_relations.attitude` 是不同字段，保留分开。 |

规范化模型严格核国家角色、重复/缺失、未知选定变体、envoy id 与建设对象/关系的三个引用、type/action、完整所选列表及源 token 类型。它不推导缺字段代表关系不存在。只能说本文件的这些引用彼此一致。

```powershell
python -B work/candidates/spy-subject-curry-save-layout-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/spy-subject-curry-save-layout-1375 -p test_parser.py -v
# 只读重现固定存档；候选 report 不覆盖
python -B work/candidates/spy-subject-curry-save-layout-1375/research.py --check
```

21 项纯小型文本测试覆盖三向引用、重复/缺字段、反向角色、布尔/整数/日期 token、引号内大括号、跨 chunk、完整 EOF、列表/深度/token 预算及投影类型别名。实际文件研究记录和 synthetic 测试输出分开，不把测试 fixture 当实际数据。

尚未闭合：保存 bitset 的命名位序、外交官遗漏 action 的默认解释、construction 日期的完整原生意义、modifier actor 归属/费用/存档前变化过程。未建立保存前相同日期的对应 RO，也未重载这份文件。因此所有因果、单项效果、保存重载、原生接口、SP/epoch 和 production 验证保持 false。
