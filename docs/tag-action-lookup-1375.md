# 外交行动 API 查找（1.37.5）

2026-10-13 增加离线 `search` 和 `lookup`，把八类目录中的147个标签与当前 V31 build-7 的120个绑定、27个排除项对应起来。查找返回编译绑定、原生入口、条件资料和逆向证据；不打开游戏进程，不创建会话或发布命令。

## 使用

在项目根目录运行：

```powershell
python -B tools/tag_command.py search --query knowledge_sharing
python -B tools/tag_command.py search --query cancel --category covert --support excluded
python -B tools/tag_command.py lookup --action ask_for_march
python -B tools/tag_command.py lookup --action cancel_sow_discontent
python -B tools/tag_command.py conditions --action ask_knowledge_sharing
```

`search` 支持动作ID、英文名、类别、原生族、脚本键、排除原因的大小写无关子串匹配；空格分隔词取交集，动作ID完全匹配优先。查询最长120字符，`--offset` 为0..147，`--limit` 为1..50（默认20）；按 `next_offset` 继续取页，`null` 表示结束。没有结果仅表示这个限定目录内未命中。

类别为 `alliance/influence/relations/dynasty/covert/economy/access/favors`。`--support bound` 表示已编译进当前宿主；`excluded` 表示目前不接受提交，查到资料不改变这一状态。

HTTP沿用127.0.0.1服务、Bearer认证及会话启动方式：

| 方法与路径 | 返回 |
| --- | --- |
| `GET /native/v1/actions?q=knowledge_sharing&limit=20` | 分页搜索，可另带category、support、offset |
| `GET /native/v1/actions/ask_for_march` | 精确查询一个标签 |
| `GET /native/v1/conditions/ask_for_march` | 已绑定动作的脚本和原生条件资料 |

只有集合搜索路由接收上述五个查询参数，重复/未知参数或无效页码返回422。精确查询和条件查询不接受查询参数。CLI查找不需要session；HTTP启动要求见[命令接口](tag-command-interface-1375.md)。

## 返回字段与证据

`lookup` 的 `current_host_binding` 来自当前编译注册表，`catalog_native_mapping` 来自静态目录。二者分别保留，避免把目录里的accessor误当成clone，或把旧目录状态当成当前宿主能力。

118个普通动作的 `native_check` 提供 `profile_family/token_id/object_size_bytes/vtable_rva/clone_rva/destructor_rva/setter_rva/local_check_rva/full_check_rva/command_wrapper_rva/full_caller_evidence`。这些位置解析自build-7实际使用的Profile51源码及字段声明；两条宿敌命令标记 `independent_command`，不伪造普通动作的虚表。排除项的 `current_host_binding/native_check/conditions_endpoint` 为null，仍可查看静态目录和新证据。

所有地址为固定EXE的RVA，SHA-256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。文件image base为 `0x140000000`；RVA不是运行时指针，也不能作为提交参数。

`native_research_findings` 目前包含24条：本轮19条、上轮四候选整理5条。其中23条为机器观察 `observation`，1条为对象语义推断 `inference`。每条包含关联动作、RVA、来源文件和 `unknowns`；lookup和conditions均按动作过滤。来源固定在 `source_pins.native_research`，连同原版/Mod脚本、局部索引、编译profile和目录在查询时重新核对散列；资料变化就拒绝返回，需审查后重新生成。

公共字段保持 `evaluated_in_game=false`、`native_logic_complete=false`；每条发现另有 `historical_failure_branch_proven=false`。绑定数、找到检查入口、局部条件解码或没有命中字符串，都不能证明当前TAG合法、AI接受或效果通过。

## 本轮新增逆向结果

| 范围 | 已确认的静态行为 | 对API查找的意义 |
| --- | --- | --- |
| `ask_for_march(A,B)` | local80构造 `designate_march(B,A)` 临时对象；内层和外层legacy hook方向不同。full88公共检查仍针对原A。 | 请求方向不能机械复用提供方向；临时对象没有执行反向full/发送/效果。 |
| `ask_knowledge_sharing(A,B)` | 委托 `knowledge_sharing(B,A)` 的共享叶；知识提供方B、接收方A，原A承担公共请求门槛。 | 查询明确双方角色；已解码链只对knowledge token调用legacy条件。 |
| 知识分享门槛 | pair战争索引、提供方距离缓存/范围、双方分享计数、机构差异及接收方局部进度都参与；局部进度比较为 `<100000`。 | 单有机构差异不足；首都区域等字段命名保留为推断，TLS和部分helper未解码。 |
| 知识分享false模式 | local直接拒绝，提示仅战争或到期终止。 | 未开放手工取消入口，自动终止路径仍待研究。 |
| 四个旧秘密行动取消标签 | 正式execute重新检查local；通过后先调用具体效果，再进入可能的召回路径。false仍可能写日期、添加修正、宣称或CB。 | 继续排除，不能把value=false等同于撤销效果。 |
| 附庸主动解除 | effect内存在属国方向，但local拒绝actor.overlord==target，execute再次检查local。 | 内部效果分支不足以构成可用公开API，`break_vassalization`仍排除。 |

完整条件证据见[请求与知识分享](../work/reports/rea-api-discovery-20261013/conditions/README.md)，取消控制流见[取消与附庸解除](../work/reports/rea-api-discovery-20261013/cancellations/report.md)。普通Capstone有界反汇编与REA文件身份证据分别标注；没有冒称已配置REA深度原生反编译引擎。

## 验证与后续

本轮36项相关Python检查通过，包含7项新增查找检查，覆盖147标签分页、正反动作、排除项无法提交、独立命令、来源变更拒绝、CLI无游戏访问、HTTP认证和参数校验；其余为原条件/服务/后端检查，数量不与历史测试累加。两个资料生成器的 `--check` 均通过。实际CLI样例与验证回执位于 `work/reports/rea-api-discovery-20261013/`。

本轮没有修改DLL、绑定、测试Mod或历史测试台账，没有注入、运行原生入口、发布请求或新增效果验收。默认build-7及44个原生来源pin保持。下一步可依据原始字段路径补充有界只读采样，闭合外交官ID排除容器、知识分享索引/距离/局部进度及正确线程上下文；有分配或TLS初始化的registry getter不能直接作为只读API调用。历史成功、派发、未知和未闭合动作继续遵守禁止复测规则。
