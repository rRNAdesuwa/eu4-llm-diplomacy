# TAG 外交条件查询与拒绝诊断（1.37.5）

2026-10-13 最新[外交行动API查找](tag-action-lookup-1375.md)已接入24条有来源散列的定点发现，包含请求卫戍国/知识分享的反向委托、知识分享门槛、旧取消标签与附庸主动解除的执行路径。`native_research_findings` 按动作返回，区分机器观察和语义推断；原51族引用索引保留原样，新增选定helper解码不代表所有族条件完整。

上轮[四候选条件报告](../work/reports/rea-diplomacy-20261013/four-candidate-conditions.md)已确认四项公共关系成本分支可静态排除；外交官条件新增 `actor+0x1498` 的ID匹配容器；march硬编码条件与scriptable外部尾跳已进一步解码。旧准备计划将trust好感写成 `>-200`；机器比较包含等号，在阈值为-200时应为 `>=-200`，整体合法性仍未证明。

新增只读条件查询，覆盖现有120个绑定。它返回原版脚本条件、仓库中配置的测试Mod条件、已编译原生检查位置及未解码边界；不访问游戏，不调用预览，不回答某个当前国家组合是否一定可用。

```powershell
python -B tools/tag_command.py conditions --action offer_vassalization
python -B tools/tag_command.py conditions --action create_pronoia
```

HTTP：`GET /native/v1/conditions/{action}`，使用已有Bearer令牌。延期动作仍拒绝，不会因有百科或脚本文案而获得可执行入口。字段 `evaluated_in_game=false`、`complete_legality_documented=false` 明确保留。

数据为 `bridge/tag_action_conditions_1375.json`；`python -B tools/build_tag_action_conditions.py --check` 核对可重现输出。条件与注册表、原生manifest、Mod manifest散列绑定，Mod源文件变化后需要重新生成。39个脚本动作有完整的原 `is_visible/is_allowed/require_acceptance` 条件树；普通原生动作的附加脚本条件按数组保留重复 `condition`。缺少脚本块不表示没有条件，51个原生族的局部与完整检查仍参与判断。两条宿敌命令使用独立路径。

`native_local_condition_evidence` 返回该动作所属族的离线索引：检查入口、直接调用、提示键及英文文本、解码范围和未跟随边界。51族共记录433处键引用、228个不同键，其中199个取得英文文本；118个普通动作使用此索引，两条宿敌命令的 `family=null`。提示键可能来自未命中的分支，调用的内部逻辑没有随之解码，因此不把它们自动转换成完整可用条件。Scriptable族保留外部尾跳转截断标记；其余族的范围闭合也不等于全部条件已逆向。

原索引 `work/runtime/tag31-local-condition-index-20261013.json`（962029字节）SHA-256为 `f0253495ce7a440f05840ff6d6a7993ad0e4d1cca90f9cb68fc99dcdcd1d92f9`。查询核验原索引、编译profile、原脚本及全部测试Mod文件，包含特殊属国助手；无需加载会话或访问游戏。`capabilities.condition_reference` 提供查询入口。

`record.native_check` 现同时提供编译profile的对象大小、token、vtable、clone、析构、setter、local/full检查和command wrapper RVA；两条宿敌命令保持独立路径。`native_research_findings` 有24条共享记录（23 observation、1 inference），每次只返回关联动作。每条保留 `unknowns`、`source/evidence_files` 和 `historical_failure_branch_proven=false`。新增 `source_pins.native_catalog/native_research` 及profile声明来源；API拒绝来源漂移，不会据此运行原生检查。

## 已定位的四类原生条件

以下来自精确本机EXE和已有磁盘存档；不是重新测试结果，也不是历史调用中首个失败分支的记录。

| 动作 | 已解码的局部条件 | 对原测试状态的判断 |
| --- | --- | --- |
| 提议结盟 | 不能以对方为行动者的包围网目标；双方好感须过阈值；另有既有盟约、战争、属国、宿敌等检查 | FRA→SAV基线确有coalition_target=SAV，双方cached_sum=-10000。仅改冷却不足以修正该测试条件 |
| 提议附庸 | 自身宗主关系、目标自由市、属国资格、发展度上限、特殊属国类型及附加脚本条件 | NAV发展度7、与FRA结盟且好感足够，但原报告没记录全部原生属国标志，不能宣布条件全部可行 |
| 王室联姻 | 宗教组、双方政府能否联姻、双方属国类型、已有联姻列表、附加脚本条件 | FRA/POR均为天主教君主国；仅这些存档字段不足以证明所有局部检查通过 |
| 人情换信任 | 未命名全局/TLS门槛；目标对行动者的好感、信任<100，以及目标→行动者关系中的人情足够支付原生对象成本 | NAV→FRA为好感10000、信任55、人情99.244。反向FRA→NAV人情0.126不是该比较字段；历史对象成本和入口门槛未记录，保留未知 |

证据 `work/runtime/tag31-native-rejection-leaf-20261013.json`。局部检查RVA分别为51f020、4ef3b0、511d60、4fdfa0。公共full检查在未传说明字符串时可能先短路返回false，甚至不执行局部检查；因此不能把上述候选阻碍写成历史逐调用诊断。

百科搜索缓存补充说明：外交附庸通常要求190关系、盟约、目标和平及不超过100发展度，且还有科技、核心等限制。见[中文百科附庸国](https://www.eu4cn.com/wiki/Diplomatic_annexation)。普通联姻有政府和宗教组限制；百科列出基础的人情换信任为10人情换5信任。见[中文百科外交](https://www.eu4cn.com/wiki/%E5%A4%96%E4%BA%A4)。页面部分内容标为旧版本，只作为核对线索；本次取得的是搜索缓存摘录，直读仍超时。测试Mod已改变某些门槛，不将百科数值当成当前进程的完整条件。英文百科仍返回401，贴吧正文仍未取得。

## 特殊属国类型为何变回普通附庸

已闭合的脚本调用链：

1. 原 `common/on_actions/00_on_actions.txt:5410` 的 `on_dependency_gained` 调用事件助手。
2. `common/scripted_effects/01_scripted_effects_for_on_actions.txt:4885` 将ROOT宗主、FROM属国交给 `convert_special_subject_to_vassal`。
3. `common/scripted_effects/01_scripted_effects_for_diplomacy.txt:76` 在宗主缺少has_eyalets、enables_pronoias或persian_influence_mechanic时，把对应特殊属国重建为普通vassal。

此前测试Mod放开了动作入口和类型的潜在宗主条件，却没有覆盖这一步。AMG新君主、ORL着色标志、三个关系同日开始及最终vassal类型，与该调用链吻合；未取得逐调用trace，不能声称已直接观察helper命中。

本次修复只将这一个助手的外层 `if.limit` 改为 `always=no`，原创建动作 `on_accept` 和其他助手保持逐字一致。新文件按原相对路径覆盖，原版3293字节源SHA为 `f5b15d6f30de12da1df2b09d304308327e4932dda57d3cddd69d3d51e39f165c`。修复已备份安装，仅离线验证，未重发这些已派发动作。

另有正常生命周期：文化势力圈在宗教或政府变化后可能解散；可继承pronoia在君主死亡且自由欲望低于50时可能被继承。本轮短程创建操作没有证据要求关闭这些机制，因此保持原逻辑。

新进程61988已载入修复后的Mod并停在1445.2.16的非铁人暂停地图。安装文件逐一匹配仓库manifest，39个所需脚本动作定义齐全，内存普通冷却配置为-1月；相关脚本的错误日志筛选为空，但游戏日志仍有其他告警。证据 `work/runtime/tag31-mod-load-61988.json`。本轮未加载外交DLL、未发送请求，未验证同日连续行动或特殊属国创建效果；原保存中的附庸类型与旧冷却截止日期不会被此配置追溯修复。

57个干净拒绝候选的逐项准备计划见 `work/reports/tag31-corrective-plan-20261013.json` 和同名Markdown。分为24项特定政府/机制、25项前置关系/资源、4项未解原生条件、4项可静态准备。分类是准备工作量，不能解释为可立即发送数量。原最终存档已冷重载并重新暂停保存：31国选定关系、外交官和全局外交记录保持，DAN属国计数字段从3变2，实际依赖记录未变；详见 `work/runtime/tag31-cold-reload-20261013.json`。没有重复执行任何动作。
