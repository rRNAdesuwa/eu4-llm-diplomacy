# 三项朝贡候选纯数据判定器

`tributary_effect_oracle.py`只提供`catalog()`与`evaluate(action, before, after, receipt)`，仅导入stdlib `re`，不读取文件、进程、PE、网络，也不导入冻结observer。没有CLI、HTTP、capture或dispatch入口。稳定15、独立候选18及其pins均不修改。

唯一正结果为`status="candidate_pattern_match"`。它只表示输入JSON中的候选依赖子状态转换匹配；`inputs_authenticated`、`selected_effect_verified`、`native_action_mapping_verified`及所有授权/AI/持久化标志始终false。其它结果为`unknown`或`pattern_not_matched`，不表示原生拒绝、等待AI或允许重发。`native_calls=0`只描述这次纯函数，不抹去输入所描述的历史派发。

| 动作 | 属国角色 | 领主角色 | 前状态→后状态 |
|---|---|---|---|
| establish_tributary | target | actor | 双方索引无此dependency、target原领主sentinel → tributary_state、target领主actor |
| ask_to_be_tributary | actor | target | 双方索引无此dependency、actor原领主sentinel → tributary_state、actor领主target |
| convert_tributary_to_vassal | target | actor | tributary_state且领主actor → vassal且同领主actor |

这是已独审合同的候选语义；native执行→最终key/角色映射仍未闭合。dependency两个端点无序比较，方向使用显式完整领主句柄；不猜哪个端点是领主。对象地址可以改变；同地址不会替代类型转换证明。357是既有country/root校验值，不新增dependency marker。

输入采用新schema，不能把它直接当冻结observer原始输出。测试中的`fixture()`展示完整合成数据形状；所有dict键集合均按源码明确校验。

- `before/after`的`schema`是`EU4-TRIBUTARY-CANDIDATE-SNAPSHOT/1`，`phase`分别为`before/after`，`game_sha256`固定1.37.5。`country_count`是exact int且2..32768。
- `identity`沿用真实TAG会话字段名：`pid, creation, session, dll_sha256, manifest_sha256`。PID为非零DWORD；creation为非零小写16hex；session为非零小写32hex；两个SHA为非零64hex。前后、receipt和audit_claims必须完全一致；nonce别名不能替代session。字符串一致不证明它就是实际安装会话。
- `command`恰为`request_id, action, actor, target`。原request ID为1..96个`A-Za-z0-9_.:-`字符；三份命令及audit中的原ID一致。TAG为3位大写字母/数字且双方不同。
- `pair`包含actor/target TAG、完整句柄、各自完整领主句柄，以及exact bool `dependency_present`和`dependency_type`。完整普通句柄按既有reader编码校验：非零高byte、保留byte零、positive slot且小于country_count/32768、低24位TAG一致。合法领主sentinel仅为`0x2d2d2d`。
- `dependency_indexes.actor/target`是**全部active used entries**的有界投影（每方向最多256），每项恰为`slot,object_address`。检查positive unique slots及canonical用户地址。不是整个capacity，亦不要求扫描无关对象body。双方选定counterpart slot的对象地址须一致。
- 缺席状态要求双方选定slot均无项、type为null、object为null。存在状态要求`dependency_object`恰含`address,vtable_rva,removed_byte_28,endpoints,type_key`，固定vt RVA `0x1c81758`、removed exact int0、无序完整端点与双方相等，key与pair投影一致。地址只比较，从不解引用；不据它证明lease或ABA不存在。
- `capture_claims`的`two_pass_equal,typed_countries_and_roots,complete_active_indexes`须exact true。before另有`baseline_claims`：`immutable,before_publication,intent_absent_before,intent_absent_after,publisher_lock_absent_before,publisher_lock_absent_after,intent_absent_before_commit,publisher_lock_absent_before_commit`均exact true，包含journal提交前复查声明。这些是输入声明，纯函数不认证它们。
- receipt使用`EU4-TRIBUTARY-CANDIDATE-RECEIPT/1`，包含同game SHA/identity/command、完整双方binding、sequence exact int1..128、state dispatched；native_result须status exact int4，submitted/slot_consumed/ownership_closed exact true，owned_live/quarantined/adapter_fault/submit_exception exact int0。拒绝、unknown、缺失或部分字段都不匹配。
- `audit_claims`包含installation_record_verified/original_request_audit_complete/native_dispatch_audit_complete exact true、同identity/原request_id、非零64hex audit_sha256。它必须由未来host的真实`recorded_snapshot`验证链导出；不能拿这些自报bool当认证。

当前冻结capture并不直接输出全部active index条目和本schema。未来host需要独立新适配器：重新认证安装session/真实原请求与完整审计，重放有界raw类型/端点/索引读取，检查publication前基线不可覆盖、held身份与source前后guard，再提供投影。R38与native链对应另需pair等于C和C+18f0链接国家；本模块没有声称完整native predicate等价。世界epoch、exclusive causality、loaded definition与原生commit不能由这些JSON恢复。

`run_first_tests.py`只是作者首次离线验收程序，精确复用已审Job helper，唯一child运行本目录新测试；不属于模块API。它要求事先sealed source-manifest，输出排他，不会重跑旧套件或接触游戏。首次结果另见report.md及offline-first-run/receipt.json。
