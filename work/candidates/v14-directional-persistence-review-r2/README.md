# v14 selected directional persistence candidate

这是独立离线候选；不改冻结 experiment reviewer、host、native、存档或观察器。交付时没有实际 case、实际 full-save 重解析或真实审核结果。root 审核逻辑后自行明示最终 case 并决定运行。模板始终 finalized:false，输出 CREATE_NEW。

## 固定输入与范围

固定两个纯文本 ASCII 文件名、全部物理字节 SHA 和大小：

| 标签 | 日期 / raw | 文件名 | 字节 / SHA256 |
|---|---|---|---|
| positive | 1444.12.1 / 56457456 | llm_diplomacy_1375_v14_positive_military_alliance_subsidies_20261008a.eu4 | 36150844 / ec7d782cb472f271fa79f7eda7b9a5ba7fc717f8f4bc1303c30c85f77c9dbb9f |
| final | 1444.12.7 / 56457600 | llm_diplomacy_1375_v14_final_cancellations_20261008a.eu4 | 36370490 / 42a2ccb5d69c41697eaa7222dbfde6c8039c2a4275b546315dda0ac46242a463 |

原进程固定 PID18356 / creation01dd56aa6f724ea8 / world0x221c8dac040。阳性冷重载固定 PID35552 / creation01dd56b0fafda55d / world0x24b15e60070；最终冷重载固定 PID59012 / creation01dd56b271750dad / world0x1340dcc6010。这些指针不是世界世代证明。身份来自 root 已提供的实际只读记录；没有本候选打开游戏进程。

完整保存解析仅闭合已直接观察的三种记录布局：

- alliance：first、second、start_date；双方无方向，不从顺序声称发起国。
- military_access：first=持有国、second=授予国、start_date、enforce_peace=no；cancel_military_access 为 FRA→POR，revoke_military_access 为 POR→FRA。自动/战争条件通行不等于显式协议。
- subsidies：first=付款 FRA、second=收款 POR、start_date、amount=1.000、duration=10（年）。不做月份换算或宽松浮点数值等价。

selected pair 的未知额外字段、嵌套字段、重复字段/记录、缺少字段、反向记录冒充正向、金额/年数/起日不符均拒绝。起日分别为 alliance1444.11.25/raw56457312、military1444.12.1/raw56457456、subsidies1444.11.15/raw56457072。DATE_RAW 是本轮保存记录与原生起日的固定直接配对，不推广为通用 EU4 日历算法。

阳性组固定3项 active：cancel_military_access、dissolve_alliance、cancel_subsidies。最终组固定6项 absent：上述3项、cancel_fleet_basing_rights、revoke_military_access、revoke_embargo。因此最多9项只读状态一致性，其中7项有已闭合序列化布局；另外舰队与禁运2项只输出 typed_reload_selected_absence_only，serialized_layout_supported=false，不把未证实的保存 key 缺失当作序列化取消证据。

## 原文件的完整有界重放

`parse_saved` 先逐64KiB块核整个文件的大小/SHA，再完整流式语法解析，再逐块重哈希并核stat。只接受 EU4txt；拒绝zip/bin、缺括号、异常token、重复国家/顶层容器。复用固定的 tokenizer/events（其自身消费并校验6字节签名），专门保留所选三类双方记录；全部字节必须解析到EOF。没有 PowerShell 大文件数组或全文件读入。

文件上限64MiB；token64KiB、depth128、单块capture128KiB/4096nodes、扫描4096项相关类型记录、最多32条所选记录。其他数据流式跳过；未存储世界全量对象。与既有完整 extraction 的所选记录、date/player、sourceSHA/size 再严格比较，不单信已保存摘要。

JSON先全部冻结哈希再解码，最多64件、单件4MiB、总计16MiB；规范仓库内相对路径、拒绝链接/junction/逃逸/重复路径，使用 duplicate-key/non-finite 拒绝的 decoder，末尾逐件重核字节。两个原始大存档从 root 显式 --save-root 下固定文件名读取，仍只读。

## 重载匹配

使用冻结 directional observer acb38546…ce1496，保留其两遍完整数据重算、严格类型和 canonical typed 同一性；不采用 state 摘要代替原始 object/index 检查。每一遍都核完整handle、vt、方向、removed、索引、普通通行variant、补贴1000milli/10年及未到名义结束日。

原进程参考与新进程观察只比较语义：类型、完整handle/方向、起日、flags、金额、年数；对象、数组、国家地址和模块绝对地址不要求跨进程相等。新进程内部的 separate held RO identity 必须与自己的 snapshot 完全一致：严格PID/full creation整数、full EXE SHA、双 held identity、player/date/world/country roots。bool或等值float不能替代整数。两个采样时段都须落在持有句柄的 GetProcessTimes creation/正常exit窗口内。

launch仅证明记录选择了固定文件及一次无注入冷启动前提，loaded_save_verified必须false；不声称独立证明了引擎实际加载路径、连续没有DLL、SP或world epoch。正常exit必须read-only、samecreation、wait0/exit0、observer未发终止。

阳性原进程军事参考应使用 `directional-ask-military-setup-after-18356.json`（raw12.1）。`directional-cancel-military-before-18356.json` 已是12.3，不能标为12.1之前采样。补贴允许给补贴后的 give_subsidies 参考匹配 cancel_subsidies 重载视图，须原共享checker核同family/roles/参数；不通过 retag 绕过原始数据。其它参考action必须相同。

最终的缺失状态不证明哪次请求造成移除；所有 request_causality、settlement、whole-world、AI acceptance、strictSP、production flags 都保持false。

## Case 与运行入口

```powershell
python -B work/candidates/v14-directional-persistence-review-r2/prepare.py --check
python -B work/candidates/v14-directional-persistence-review-r2/verify_tests.py
python -B work/candidates/v14-directional-persistence-review-r2/prepare.py --template <new-empty.json>
# 仅 root 明示准备 finalized case 后另行执行：
python -B work/candidates/v14-directional-persistence-review-r2/matcher.py review --case <case.json> --save-root <explicit-directory> --output <new-review.json>
```

case精确字段：schema_version=1、purpose=v14_directional_persistence_case、finalized=true、inputs、groups。inputs为key→{path,size_bytes,sha256}。groups按positive、final顺序，每组精确：label、binding（pid/creation/world/raw_date）、extraction/launch/identity/exit（输入key）、relations。relations须按GROUP_ACTIONS中固定次序，每项精确：action、prior、reloaded（输入key）、expected、start_date。active须实际对应起日，absent必须null。没有选择最新文件、自动补序号或默认None的隐式路径。

29项纯离线测试包括两存档→原解析器→新matcher→两遍重载→held身份的完整9项合成case，未mock判定逻辑；仅将固定输入依赖切为临时小存档和合成报告。首次测试有转义字符串语法错误（0项执行）；第二轮22项中16errors是重复要求已由tokenizer消费的EU4txt头；均完整保留。修复后22/25/28项已通过；最终完整轮次见review.json。没有在本轮运行实际存档或真实case。

## R2 exact stock container repair

The frozen first reviewer rejected the real save at bare `map_area_data`, byte 2619. Only a bounded 256-byte seek was read for this repair; no actual save was parsed and no actual case was run. `bounded-syntax-evidence.json` retains that slice. The original candidate and failed root case remain unchanged.

The matcher now accepts exactly unquoted top-level `map_area_data` followed by an anonymous `{ ... }` block, once. The shared tokenizer/parser stays unchanged and still requires full balanced closure. Assigned/scalar/quoted variants, duplicates, all other top-level bare keys/anonymous blocks are rejected. Nested diplomacy within this skipped block cannot supply required top-level containers or selected relations. Diplomacy bare/anonymous entries are rejected to prevent false selected absence. Every other save, observer, identity, effect, and persistence contract is unchanged.

The inherited 29 tests plus 8 targeted syntax tests use only tiny synthetic ASCII buffers. No actual-case approval, native execution, game access, or production claims are added.
