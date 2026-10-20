# 三项普通关系的独立只读 reader

新增 `bridge/relation_effect_reader.py`，仅支持 offer_alliance、royal_marriage、guarantee；没有改 R1/R2/实时服务、DLL、策略或旧报告。当前关系观测与请求关联的选定变化分为两个入口。只接受调用方已核身份的有界只读 port，不打开进程、不调用原生函数、不写内存、不发布请求。

目标固定 EU4 1.37.5 SHA256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。所有原生地址均为 **eu4.exe RVA**。117条旧指令按固定PE重放；仅为三条回复谓词新增16B普通Capstone5.0.7解码，未使用REA/Ghidra，也未安装依赖。

## 字段与实际原生 presence

| action | index对象相对root | data/cap/count相对root | 关系对象vt / size | 方向 |
|---|---:|---|---|---|
| offer_alliance | 78 | 80 / 88 / 8c | 1c7a740 / 48 | 对称；两端可交换，不能判发起方 |
| royal_marriage | 60 | 68 / 70 / 74 | 1c80be0 / 40 | 对称；两端可交换，不能判发起方 |
| guarantee | 198 | 1a0 / 1a8 / 1ac | 1c817d8 / 48 | +10=保障方actor，+18=被保障target |

数值均为十六进制。root是country+14f8的实体，vt1c4f5f8、marker165、owner+10必须为该country；record向量+18/+20/+28、stride48，选定record的前三个QWORD必须是root/owner完整handle/other完整handle。country+1510是root+18的别名，不作为第三份独立证据。

每个generic index本体24B，vt=1c3a538，data+8、signed cap+10、signed count+14，元素stride10、signed slot+0、object+8。复用289b50的已保留构造指令，分别在root+60/+78/+198写同一vt。reader核vt、非负count/cap、count≤256、cap≤4096、指针/cap对应关系、完整capacity地址范围、合法signed slot、重复key、选定对象不得别名到其他key，并在读对象前后重新核header和used entries。

三个原生getter为a68d90、a68be0、a6a050；它们实际按完整handle中的signed16 slot查对应索引，返回元素+8 pointer或null。它们不查record+46 bit4，也不逐个解引用关系对象。reader在此基础上要求双方索引指向同一对象，再核完整对象vt、marker165、完整双端点、有效start rawdate(+20)、removed(+28)=0、global插入失败标志(+29)=0；读取整个40/48对象两次。比原生裸getter更严格，异常或不一致返回unknown，不放宽guard迎合样本。

对象marker/vtable及端点来自三条创建路径和婚姻/保障构造；+29来自共享global_add4e12f0的4e1504。三族创建都调用该global_add。这里**没有读取global manager成员图**，global_membership_verified始终false；不声称完整生命周期/expiry、政治外交合法性或所有传递拥有图已核。当前关系的精确定义是“当前双方原生索引里有相同typed对象且选定字段一致”。

## 接口及状态

`read_relation_pair(port, base, action, actor_handle, target_handle, identity)` 使用R1 BudgetReader/roots/country/relation，保留byte7 valid、selector0、signed slot、完整lookup country头、manual pause、game+2521/reset/load/ironman等守卫。两遍重新解析完整选定图；没有旧裸指针输入或重试。可传已有BudgetReader，预算共享而不重置。

返回current_relation_observed、pair_absent_observed、reverse_relation_observed（仅保障相反方向）或unknown，同时包含两遍投影、snapshot、原身份、read_budget、native_calls=0。+46整份record仅参与稳定性，不当关系位；双方空索引只表示此选定索引关系缺失，不代表拒绝、退休、AI决策或全世界所有机制不存在。双遍相等不是atomic/world lease或epoch。

`evaluate_relation_effect(action,before,after,receipt)` 要求完整同身份、同pair、同world root的两个有效capture及原始完整V31回执，重核raw index/object证据；只接受pair_absent_observed→current_relation_observed。原receipt必须含command/request_id/audit SHA/sequence、完整pair_bound和request_result身份、status4/normal_dispatch_slot_consumed、7次adapter调用/3次owned issued、transfer1、全部submit bits true、ownership_closed true以及live/quarantine/fault/exception为0。known_cleanup_complete原值保留，可为false，不能将传输消费称为全本地析构完成。

缺基线/缺回执/换国家世代/不完整capture/不一致字段均unknown；已存在→已存在、缺失→缺失或移除均not_observed，不猜拒绝。observed仅是与请求身份关联的**选定索引状态变化**，不证明排他因果、精确外部ID归因、保存持久化、全局注册、完整外交效果或AI接受。调用方仍须以既有基线journal机制保证采样在派发前且无publisher竞态；此纯函数不自行证明基线先后，也不提供发送许可。

## 回复边界

联盟action vt1c80720的+d0→50f120（mode!=0），联姻vt1c80ab0的+d0→4e4d50（返回mode），正向二者都需要回复；实际创建分支分别50f80b/4edb7a要求state2。保障action vt1c7fe50的+d0→8f450恒false。16B新增解码只闭合这些槽，不扩整个executor。

本reader不读pending或通知队列。当前R2回复reader仅识别ask_for_march，不能改一个vt常量就当作三动作的已验收回复解释。联盟/联姻未出现关系不等于拒绝，原请求排队/消失也不等于接受；状态对象state2、相应通知键及精确请求关联需要另行闭合。保障无回复要求也不意味着它的原派发自动有选定效果。

## 只读current-state验收推荐

已保存1445.5.19检查点SHA `09d3835dd0ac7a5e7e447fb05322b02aa7fbfcd84aaa20d67477b9022c912807` 的完整解析 `work/reports/diplomacy-corrective-20261014-r3/runtime/batch-after-save-selected.json` 保留：

- 联盟 FRA→POR，save行2204299，start1445.1.10；反向也应为同一对称关系。
- 联姻 ORL→BRI，save行2204479，start1445.5.11；反向也应为同一对称关系。
- 保障 FRA→SAV，save行2204309，start1445.2.16；反向只应显示reverse_relation_observed。

这是只读正样本推荐，不是新内存实测、不是任一新请求效果，也不授权重发已成功/派发动作。三action均属于旧35个已绑定历史效果集合且继续禁测，历史来源与当前绑定见contract.json。若当前状态已被正常游戏规则改变，应如实报告新读结果。

复核：`python -m unittest bridge.tests.test_relation_effect_reader`，37项实际字节图检查；`python bridge/relation_effect_reader.py --check`；本目录verify.py --check核静态字节及独立manifest。测试覆盖三个正/反/空图、完整handle/根归属、generic index类型与signed分配边界、重复/别名、short read、对象类型/双端点/+28/+29/date、原生getter变更、pass内外变化、旧裸指针不追及完整基线/回执反例。未访问游戏，shell收齐。
