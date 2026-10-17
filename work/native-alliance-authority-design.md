# 联盟权限隔离候选设计

## r17c 实际进展与当前接入边界

当前 session 为 `60892-1dd5b1d26b30a9b`，DLL SHA256 为 `e4c14dadfcfe13f967e3d6ca220b0a81e27680af15cad221f1055cd3c8256c87`，原生执行与权限隔离仍关闭。8组查询、9项guard和35天自然流转已通过。675条wrapper field begin、20条Alliance wrapper clone、2条同wrapper/action/完整payload的clone→entry链另由 `runtime/alliance-query-20261013-r17c/r17c-protocol-validation-002.json` 独立复核；6项定向测试通过。旧001报告遗漏wrapper地址关联条件，保留为历史，以002为准。

`incoming-receive-contract-20261013-r17c.md` 恢复了 `0x15800c0..0x158026e` 的接收重建流程：wrapper clone原生返回时header为ffff/0/0；调用者随后复制source sequence到target，再放入列表。执行入口的对象地址与payload连续性以及sequence恢复已实际观察；列表写入本身仍只有静态证据。shared `0x17067e0` 确实调度联盟及wrapper字段解析，旧“排除deserialize”段仅保留当时静态范围，不能继续作为该backend无解析能力的结论。完整网络/本地发送来源证明仍未取得。

新增 `native/alliance-authority-ledger.h` 是未接入DLL的纯C++底座。它分别绑定outgoing、incoming与target代际，保存完整Alliance payload、阶段、会话、期限与native header；只有单次ticket可沿已证实的clone marker和sequence恢复合同移交。正常source析构按移交阶段detach，目标析构、提前销毁、显式撤销和过期使许可失效。`authority-ledger-fixture/review-003/verification.json` 为163项独立检查，覆盖分配器在同一intent内复用已detach地址而旧代际许可仍拒绝。此fixture不证明native source或实际业务执行；capacity64保留终态tombstone，尚无长期容量回收策略。

下一步应核对接收namespace/owner和当前未解析的wrapper selector `0x240`，再实现trusted_pipeline_proof适配与真实sender。这个proof参数必须由原生接入层根据当前hash、会话、完整来源与对象转换生成，不能由外部调用者随意传true。generic recipient route `0x4e8163..0x4e81c5` 的roster和secondary predicate语义仍待实际核验；直接断盟七caller仍未证明主动AI/强制/外方来源，见 `direct-break-source-role-20261013-r18.md`，不能全局跳过 `0x3d2350`。完成这些边界后继续受控Offer隔离、授权正常发送、其他国家真实接受/拒绝及保存重载，不提前扩展家族。

2026-10-13。仅适用于已核对的EU4 1.37.4二进制；权限方案尚未实现。以下分别区分已取得的查询/只读身份运行证据与待实现的授权链。

## 已恢复的边界

- 普通命令的执行入口为generic wrapper方法，先执行原生有效性及外交官等处理，随后进入动作处理、响应或队列链。
- `delivery-decision-flow-20261013.md` 证实Offer的AI响应选择发生在执行器克隆提议之后：调用原生接受检查，将克隆状态写成2（接受）或1（拒绝），再正常包装、投递。
- 同一执行器另有向recipient国家的原生待处理队列插入独立克隆的路径。这是外来提议送达受控国的候选路径。不能以返回false强迫AI拒绝来代替送达。
- `decision-semantics-branch-map-20261013.md` 以分支和消息文本证实响应决策国为recipient；Offer发起国为actor。断盟是独立变体。
- `authority-entry-coverage.md` 证实断盟helper存在绕过generic wrapper的直接调用。业务通知方法的入口可能已晚于真实关系变化；最早选择/结算边界仍在核对。
- 后续 `authority-entry-prebusiness-effects.md` 已确认该helper在通知前写pending-list及country-owned vector。必须在首次副作用前区分实际决策来源；不能仅在通知入口停止，也不能把所有维护/强制断约调用都视为受控国的主动选择。

## Offer的候选拦截方式

1. 在generic执行入口识别精确类、当前完整句柄、变体与阶段。受控actor未经授权的Offer发起在任何资源或队列副作用前停止。其他国家的Offer发起保持原生行为。
2. 对actor不受控、recipient受控的状态0 Offer，保留原生有效性、外交官与发起处理；在AI响应选择之前，研究是否能转入该执行器已有的待处理队列分支。只能对已识别的这类动作改变决策来源，不修改国家的玩家/AI全局身份，不影响军事经济AI。
3. 外部查询只读识别受控国队列中的提议，返回不含地址的proposal标识。接受/拒绝必须绑定当前队列对象、双方、原始日期和生命周期；不能依据任意双方tag捏造回应。
4. LLM回应复制仍有效的原生提议，在独立克隆上选择原生响应状态，再沿UI已经恢复的clone/wrapper/dispatcher链提交。原始队列对象不由桥接直接改字段。
5. 对受控recipient未经授权的响应，在generic入口停止。非受控recipient的响应保持原生接受检查和正常投递；授权不覆盖其选择。

候选分支地址及寄存器证据见 `runtime/alliance-static-20261013/disasm-4e8080-4e86f0.txt`：AI响应与recipient待处理队列是同一函数内不同分支。中途转向需要独立恢复被覆盖指令、寄存器、栈对齐、所有分支条件及对象所有权，不能直接跳到内部地址试验。上述方案目前没有hook代码或运行证据。

## 授权生命周期

r15运行证据`runtime/alliance-query-20261013-r15/protocol-lifecycle-gaps.json`显示两个CAS→POR候选链的实际序列化origin为2836/2851，而相同sequence的执行入口origin均65535；flags为0、序列分别190/790。这是观察到的字段变化与候选关联，完整发送到重建因果链仍未证明。不能使用历史v9的origin=ffff序列通配放行，也不能未经恢复incoming来源就重写origin。另包装可更新date2c，clone可重置它，执行入口又带相应日期；授权指纹需分阶段验证这些原生变换，不能把完整布局相等当作所有clone的普遍规则。独立报告r15-003整体incomplete、完整链0条；当前授权未实现。

r14/r15已在新进程安装被动clone/wrapper/序列化/析构追踪，并分别完成8组查询和35天自然流转。r15补齐执行入口完整协议key和action快照，使用跨ring统一callback顺序，另记录析构返回但不读取已释放对象。证据为`runtime/alliance-query-20261013-r15`；不能把这些阶段当作桥接授权或提交，完整关联尚待核验。r14独立离线报告中没有完整链，缺失项保持unknown，记录的placeholder协议字段与实际序列化key不同属于待核对的原生分配过程。

新的有界静态审计`runtime/alliance-static-20261013/wrapper-deserialize-20261013.md`排除了wrapper `+0x18`作为已证实incoming deserialize的假设；恢复action `+0x20 -> 0x4e8b70(action,record,field_id)`字段读取链，以及`0x12b860 -> 0x129b60`的另一重建后业务处理入口。该record是否来自网络、协议身份是否保留仍未知，因此只拦generic executor不能先宣称全部Offer路径被隔离。下一步需被动观察字段读取来源和两个业务入口，建立发送到重建的因果证据。

`runtime/alliance-static-20261013/direct-break-callers-20261013.md`逐项记录七条直接断盟caller的参数和局部gate，但尚未证明AI、事件、强制条约归属。早于首次关系副作用的共同边界为`0x3d2350`入口；后续观察应携带原生return/caller身份和决策国，不能仅在`0x50f7c0`通知处停止。

r12 的 `runtime/alliance-query-20261013-r12/transport-owner-live.json` 在精确创建时间、exe和唯一observer DLL哈希校验后，只读核对了 server getter `0x811ad0`、UI与server的dispatcher指针相同、transport vtable `0x1d95fd8` 的 `+0x30=0x1580270`，以及 `transport+0x128` 指向可读的counter。该结果把历史peace候选与当前场景的实际对象联系起来；没有调用getter、sender或dispatcher，`alliance_sender_runtime_verified=false`、`authorization_lifecycle_runtime_verified=false`。不能把对象身份匹配当作原生投递收据。

授权需要分别证明创建、复制、包装、序列化、重建、执行及析构。历史和平的transport owner/counter路径只提供静态候选，不能继承为联盟验收。

授权记录应绑定实验/进程身份、唯一请求、阶段、决策国及动作指纹。clone或序列化后的状态变化不能扩大授权阶段。packet匹配必须有已验证的协议身份和相同参数，不能仅凭对象地址、sequence或永久国家句柄放行；记录应随析构、消费或到期回收。实际native提交收据与journal claim分开。

## 尚待解决与验收

- r12已实际恢复固定Offer/Cancel发起阶段的原生列表选择、按钮启用/tooltip入口及executor validity，七组查询和九类wire guard通过，见 `runtime/alliance-static-20261013/gui-alliance-rule-coverage-20261013.md`。费用/参数成本、接受度原生项目标识和尺度、完整理由、响应阶段仍未完成；该发起层证据不把整项动作标为完成。
- 受控recipient转入待处理队列是否保留外交官归途、提议时限和自然失效，需要真实运行及存档对照。
- 断盟直接helper在通知前的副作用与决策来源必须恢复；阻止通知不能算阻止断盟。
- 联盟建立/解除的真实关系字段、双方通知、请求清理、外交官和费用后果分别取证。执行入口和状态2本身都不等于业务成功。
- 各patch安装应事务化、签名核对、暂停线程后复查并能完整回滚；实验使用新进程，不热替换已有DLL。
- 先分别证明受控国拦截、正常授权发起、其他国家原生接受及拒绝、外来提议送达及LLM回应，再保存、新进程重载核对持久结果。
