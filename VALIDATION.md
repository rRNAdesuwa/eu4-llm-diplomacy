## 2026-10-16 发布检查点

[统一验证报告](docs/unified-diplomacy-validation-1375.md)记录原120批次与补测。当前48项选定效果信号、44项历史持久化、42候选保持；不得把派发数、当前absence或离线测试计为新外交成功。

和平v2空目标队列与继承人双向missing-key的实采及完整非作者raw复核已完成。R86/R87静态合同完整独审接受；R89仅源码与4份保留case审查通过，v7仅方案。源码里保留旧测试与回执；本次上传没有重新运行这些测试或实际查询。

本次只执行文件出口检查：独立Python源码AST（.inc.py片段除外）、JSON、原文件前后SHA、索引94来源及346指针、公开树/本机路径/凭据模式与diff检查。文件导出最初将include片段误当独立Python、以及遇到超4MiB历史analysis时中止；修正导出分类后继续，未放宽单文件读取上限，也未重复目标操作。完整本地采样记录不随公开快照全部分发。详情及限制见[研究进展](docs/research-20261016.md)。以下为历史验证。

# 验证记录

## 2026-10-04

- 计划与实现已开始；本机安装标识 1.37.4.0 Inca。
- 已创建独立 llm_bridge 模组；没有修改安装目录原版文件。
- 原启用配置已备份，保留两个汉化模组并追加本模组。
- 已用 computer-use 启动游戏、新建 1444 年英国普通模式测试局，当前暂停。
- 解析器与白名单编译器 12 项离线测试通过（随后添加了动作结果条件，需整合后再测）。
- 启动 error.log 搜索未发现 llm、unknown effect、unknown trigger、unexpected token；存在原有字体/编码类错误。此项不替代脚本实际执行验证。
- 游戏新局介绍窗口暂未响应自动化点击及按键，已请求用户手动关闭并打开控制台。

## 尚未完成

- 真实日志中的数值插值与国家作用域。
- run 桥接执行及动作效果确认。
- 月度触发、原生 AI 持续行为与外交动作锁。
- Codex CLI 真实模型决策与完整闭环。

当前不能宣称游戏闭环已经成功，也不能宣称完全接管外交。

### 首次人工执行反馈
真实日志确认 run 能找到 llm_bootstrap.txt，但 llm_bridge_snapshot 为未知 effect；当前启用列表缺少桥接模组，因此此前安装启用并未持续到实际测试。不能将锁标记存在视为外交限制已生效。已生成不依赖模组的 llm_probe.txt，待用户执行。日志解析改为仅严格解码协议负载，忽略其他行的汉化编码；12 项离线测试仍通过。

### 状态读取实测成功
用户执行 run llm_probe.txt 后，解析到完整法国快照：treasury=64.654、manpower_raw=15.992、stability=0、year=1444、ai=1、war=0、locked=1。This 变量数值插值和日志解析已确认有效。locked 仅为旧脚本设置的标记，尚不能证明模组限制生效。已保存快照并生成 llm_roundtrip.txt，待测试清除/设置标记与两次回执。

### 标记读写闭环实测成功
两条 roundtrip_unlock_01/roundtrip_lock_01 回执均为 applied；对应快照 locked=0→1，ai 始终为 1，财政、人力和稳定度未变。日志未出现 llm_roundtrip 新解析错误。证据保存在 work/runtime/roundtrip-real.json。外交限制仍未验证。安装描述符改为绝对路径并重新启用，需重启加载测试。

### 重启后模组已被引擎读取
启用列表包含 llm_bridge，error.log 明确识别 llm_bridge.1 事件，证明模组文件被读取。仅发现隐藏事件缺 title/desc/options/picture 警告，已补源文件与安装副本，下一次加载生效；当前先验证 scripted effect，无需为此马上重启。此次 game.log 暂无快照，待执行 bootstrap。

### 模组导出存在异常；准备独立宣战试验
bootstrap 调用不再报告未知 effect，但快照 treasury/stability 为空，manpower_raw/year 缺失，只有 ai=1、war=0、locked=1 正常。尚未定位原因，不将此快照用于模型决策。独立 inline 导出此前已成功，宣战测试复用该路径。

prepare_war_test.py 生成固定 FRA→ENG 收复核心宣战测试，要求法国仍为 AI、独立、有锁标记、有 cb_core、无停战且尚未交战；执行后检查 war_with 才回报 applied。这是手工测试脚本，不加入模型动作白名单。尚待游戏内执行；外交锁实际阻止原生 AI 的能力仍未验证。

### 宣战失败诊断
三次 war_test_01 返回 rejected，最后一次为 1445.01.26。1445.02.02 只读诊断确认全部前置条件成立：两国存在，法国 AI/独立/有锁/请求未使用，无英法战争及停战，有 cb_core。因此尚不能归因于首月或缺少 CB。增加分支日志，并在带锁宣战失败时于同一脚本内清除锁、重试宣战、立即恢复锁，以检验外交条件是否同时阻止脚本 effect。此对照尚待实测。

### 宣战目标省份修正
1445.02.04 日志证明进入 effect 分支，带锁与临时解锁均未产生战争。对照原版 disaster_GeorgianCrisis.txt 的 cb_core 用例发现测试遗漏 war_goal_province。现补 177（Maine），并检查该省属于 ENG 且为 FRA 核心。待实测；之前不能归因于外交锁。

### 宣战实测成功（1445.02.10）
日志为 effect_entered → ACK applied，没有临时解锁分支；快照 ai=1、war=1、locked=1。确认收复曼恩战争可由带锁脚本发起，法国仍为 AI。用户也确认看到战争。证据保存于 work/runtime/war-success.json。普通原生 AI 宣战是否确实被外交锁阻止仍未验证。

桥接 snapshot 动作改为已验证的内联导出，模型入口拒绝缺字段、空数值、非有限数值、非法标记及非 AI 法国。自动月度导出仍待修复与实测。

### 原生 AI 作战与议和测试准备
用户确认法国及盟友正常作战；1445.04.02 快照 ai=1、war=1。已生成双向外部白和平提议及接受脚本，提议仅设置 pending 标记，接受后调用原版使用的 white_peace = ENG，并检查英法战争消失才报告 applied。尚未执行，尚未验证盟友退出、停战及重复执行。原版外交文件仅列出 requestpeace 内建动作，未在本地事件及效果中找到可发送或接受原生和平弹窗的脚本接口；不能将 white_peace 描述为发送原生和平提议。

### 自定义外交动作原型
原版 common/new_diplomatic_actions/00_diplomatic_actions.txt 明确支持 category、require_acceptance、is_visible、is_allowed、on_accept、on_decline、ai_acceptance，并存在实际动作实现。已新增并安装独立 01_llm_bridge.txt：英国提交白和平（仅写法国待处理标记和日志）、英国接受法国待处理白和平（执行 white_peace 后验证）。使用 require_acceptance=no 避免提交请求时由原生 AI 自动决定谈判结果，ai_will_do=no。按钮英文以适配现有汉化特殊编码。必须重启才能加载；尚未运行验证。没有发现外部 effect 可发送自定义外交动作的接口；LLM主动提议仍需脚本标记/事件通知，不能声称已有原生和平条约发送接口。

### 原生和平页面条款原型
已安装 common/peace_treaties/01_llm_bridge.txt 与独立英文BOM本地化。测试特意缩小为10杜卡特，基础战争分数10，power_cost_base=1、prestige_base=0、ae_base=0。作用域、可支付条件、requires_is_allowed=no 已独立静态核对；未修改CB。ai_value=10 是条款意愿权重，不是原生接受总分。参考 Common Universalis 作者公开源码的同类字段（链接见 work/NATIVE_TREATY_TEST.md），未安装外部模组。生成 llm_treaty_probe.txt 记录双方财政及结算标记。尚待用户重启、查看原生页面评分；不能宣称原生发送、接受或结算成功。

### 原生页面与接受评分已显示
用户两张截图显示 LLM test 条款可见、选中费用10战争分数和20外交点数，原生接受提示赞成3/反对1082：盟友相对实力+3、至少需要10战争分数提出要求-1000、战争持续时间-43、要求超出战争分数-24、当前和平提议-10、法国控制首都-5。这是原生接受判断已参与自定义条款的证据；尚未发送或结算。不能把常数费用视为已复用原生黄金或省份费用算法。本地化出现数字122和缺失国家名称，属于独立显示缺陷。后续应保留原生割地/赔款条款及其引擎计价，仅用自定义条款扩展已有规则不能表达的内容。

### 原生只读国家对象验证

2026-10-04 加载后使用 QUERY_INFORMATION|VM_READ 成功读取 ENG（槽46）、FRA（槽122）及256个索引一致的国家槽位。新增有界议和窗口指针图探针已运行，未找到满足vtable/owner/callback三项校验的对象。此项只验证只读状态访问；发送回调与构造/投递路径仅有静态证据，没有运行调用或写入游戏进程。

### 原生议和窗口对象实测定位

用户保持英格兰对法国原生议和窗口打开、清空提议且暂停。指针图仍无匹配，改用限时20秒/限量4GiB的只读私有可写区域扫描，9.078秒扫描约1.07GiB后找到对象0x2a79faeaca0。同时满足窗口vtable、监听器owner等于窗口自身、发送callback等于本机RVA0x130f080三项校验；窗口+0x2c目标句柄与已验证FRA一致，+0x660方向标志为1。两份0x1c0字节候选条约记录已保存到 work/runtime/native-peace-empty.json。它们包含动态数组及双方句柄，尚未确认全部字段含义或原生费用所在位置；没有执行发送回调。

### 原生赔款单步差分

用户在原生要求页增加一次金钱赔款，读到总金额25.6、英国份额8.22、费用1战争分数/0外交点数/0侵略扩张。接受判断为+3/-1051，详细原因保存在 work/runtime/native-peace-gold-one-observation.json。重新读取原窗口只需直接校验地址，没有再次扫描堆；条约window+0x48相对+0xf0的u32从0变1000，另有辅助容器指针变化；window+0x208对象未变化。证据支持+0xf0与金钱条件相关，尚不能认定其单位是金币或战争分数。此时仍未发送。副代理确认复制构造深复制多个容器、回指针必须重设，详见 work/peace-offer-layout.md；不可将内存块浅复制作为新提议。

第二次按钮实测51.2金币/2战争分数，条约+0xf0为2000，反对因素1054、正面3、净意愿-1051；原始快照与用户转录已保存。额外只读验证原生投递context链，末级transport方法RVA0x1580270；未调用、未注入。两档结果只证明该局部变化关系，尚不能泛化为完整金额/费用算法。

### 进程内线程探针构建

work/native/probe.cpp 与 frame_stub.S 已用本机 x86_64 MinGW GCC 以 -Wall/-Wextra/-Werror 构建通过。反汇编核对易失寄存器与XMM0–5的保存/恢复、200字节总栈调整、尾跳转；DLL仅导入Windows/UCRT，不需要额外libwinpthread。已在独立Python进程通过WinDLL加载并解析BridgeStart导出，没有调用该导出，没有注入EU4。

默认模式只观察帧回调线程与玩家句柄；另有明确文件请求控制的一次性原生空条约构造/析构测试。DLL启动删除过期请求，不包含外交发送函数。线程暂停安装、原生构造/析构均尚待游戏内实测，动态trampoline没有单独的异常展开记录，属于实验性实现。用户首次实测前需另存测试局；启动需加载器显式--ack-test-save。

inject_probe.py 由副代理完成，主代理检查后修正所有未确认完成的LoadLibrary等待路径均保留远程参数内存，并将非零BridgeStart退出码视为失败。已通过py_compile、CLI帮助、PE架构/导出RVA解析、系统LoadLibrary所属模块定位、游戏SHA256检查；这些检查没有创建远程线程。start-probe.ps1只在用户显式传入-SavedTestGame时启动，PowerShell语法解析通过，未运行。最终DLL SHA256为585b0674b034d01be171b012f83dc67331f7a3c8f3789086d6c6d343c2e85f39。

### 线程探针与空条约生命周期实测通过

用户已执行加载器。probe.jsonl持续记录同一线程16424、country_valid=true、player=ENG、thread_changed=false。截至证据汇总已有321条帧日志，最大累计18581帧，游戏进程22168仍有响应。主代理通过文件请求触发一次原生空条约构造/析构，得到roundtrip_begin→roundtrip_ok，其后帧日志继续。证据汇总为work/runtime/native-thread-and-offer-validation.json。没有发送提议，没有调用和平结算。

下一版eu4_bridge_lifecycle.dll新增显式action-roundtrip.request，验证FRA→ENG空条约、外交动作、原生深复制和命令包装/析构，不调用投递器。也读取帧入口this指针的候选投递上下文链。-Werror构建通过、独立Python加载及BridgeStart导出解析通过，SHA256=6750599cb9c1b1edcce2a570235054c55ba1173e752f19e62b097745c4883db1，尚未游戏内运行。加载器现在拒绝同一进程任何已加载eu4_bridge_* DLL，需重启测试游戏再安装第二版。

### 原生动作与命令生命周期实测通过

用户已安装第二版。线程32296、ENG句柄持续有效；触发action-roundtrip.request得到action_roundtrip_begin（FRA→ENG、send=false）→action_roundtrip_ok，其后帧日志继续，游戏进程18024仍响应。证据work/runtime/native-action-lifecycle-validation.json。帧入口this的+0x330投递链不可读，明确排除该对象作发送上下文。

重新只读定位原生议和窗口（即使窗口未打开也已构造），获取UI根和投递器链；模块RVA0x2349550中找到唯一相同UI根指针，末级方法仍为RVA0x1580270。原始证据work/runtime/native-peace-lifecycle-context.json。

第三版eu4_bridge_sender.dll加入固定FRA→ENG空条约发送、原生日期保护和投递器身份核对，默认不发送，必须显式whitepeace.request。构建及独立Python加载/导出检查通过，SHA256=0534c863cb23ef3674e1c77a76ae4d81d586147b5c839a4446002d8338382711。尚未在游戏发送；不能将submitted返回true等同接受或结算。

发送代码独立复核通过六参数ABI、Wrap输出指针容器、Submit消费后不重复析构，以及源offer/动作内副本分别销毁。审计发现未执行原生按钮的vtable+0x120预览步骤，已补充相同的线程局部理由池、重置/预留与0x59bf10调用，再按原页面条件设置内部+0x208。该内部标志与原始返回值不作为对方接受证据。修订后-Werror构建通过，最终发送DLL SHA256=e3f95e0eacf023b55440e45d41866a95bb2a7d1aa3b5c3135e171a8eb5224c8a；尚未注入该版本。手工填入空条约双方字段的完整业务语义仍待首次原生接收验证。

### 首次原生白和平投递

用户安装发送版，线程32804、ENG句柄有效，固定全局UI根到投递器链持续可读。主代理创建一次whitepeace.request，得到whitepeace_begin（FRA→ENG）→whitepeace_native_preview（raw_result=-39、native_flag_208=0）→whitepeace_submitted（accepted=unknown），其后帧回调继续，游戏进程19072仍响应。这里只确认原生投递器返回true；用户是否收到和平通知、命令是否被引擎执行、接受/拒绝及结算尚待验证。不自动重试。

### 原生白和平通知接收成功

用户在暂停且未推进日期时已收到法兰西的原生和平提议：双方代表整个同盟，无条件和平，双方无所得/所失；同时显示法国战争前12个月、战争分数高于-10时单独媾和额外-25威望提示。原文含义及是否实际施加该惩罚尚待结算验证。用户尚未报告接受或拒绝；记录work/runtime/native-whitepeace-receipt.json。

该结果确认构造→预览→命令包装→原生投递→玩家原生接收链打通，且无需推进游戏日期即可收到。本次仍不能证明原生AI目标接受/拒绝、结算与含条款费用API。下一步先拒绝验证战争继续，再由同一DLL发送并测试原生接受结算；无需为重复动作重启游戏。

### 玩家拒绝与同日重发限制

用户确认已拒绝。使用同一已加载DLL触发重发，日志为whitepeace_rejected、reason=native_date_guard，没有新的提交。只读证据work/runtime/native-whitepeace-retry-guard.json显示当前原始日期与法国+0x24a0相等（56460528）；下一次必须严格大于该值。全局缓存actor不是法国，没有该分支限制。未修改日期或冷却字段，未绕过原生保护。让用户推进1天后再检查并尝试发送；战争是否继续仍未通过状态导出独立确认。

用户推进1天后，原始日期56460528→56460552（本次观测为24单位/日），法国记录仍为上次日期，保护检查通过。使用同一DLL再次发送得到whitepeace_begin→native_preview(-39、flag=0)→whitepeace_submitted，游戏仍响应。证明无需重启即可重复发送，尚待第二次接收与接受结算验证。证据work/runtime/native-whitepeace-retry-ready.json及probe.jsonl。

第二次接收失败：用户确认暂停及解除暂停后都未收到第二次提议。重新只读检查当前原始日期56460816、法国记录仍56460528，日期guard通过。帧线程与dispatcher持续正常，game.log没有提供发送/拒绝处理细节。此前“重复发送”仅证明重复构造与投递层返回true，不能视为重复原生接收已成功。原因尚未确定，可能需核对后续合法性与pending状态；没有证据要求重启，也未绕过保护或继续重复提交。诊断证据work/runtime/native-whitepeace-missing-receipt.json。

用户提出通用外交频率限制。核对本机common/defines.lua:352，DIPLOMAT_COOLDOWN_TIME=1，注释明确DIPLOMATIC ACTION COOLDOWN IN MONTHS。此前只核对发送按钮日期保护，未覆盖通用按对象的外交冷却；推进1天不足以排除该原因。尚未完成对应执行分支/存档字段的映射，因此把1个月冷却作为有依据的待验证解释，而不宣称已定位拒绝分支。首次发送为1445.04.08，下一对照拟在1445.05.09之后同一进程重发，无重启或冷却字段修改。

### 超过月度冷却后的重发执行

用户继续推进后，当前原始日期56461344，相对首次日期56460528经过816原始单位（按已观测24单位/日为34日）。同一DLL触发一次重发，得到whitepeace_native_preview=-35、flag=0、whitepeace_submitted。随后只读确认法国+0x24a0从56460528更新为56461344，这与已定位的命令执行器写入路径一致，强于投递器返回true，支持此前重发失败由月度外交冷却导致；仍未精确映射该冷却分支。没有重启或修改冷却。证据work/runtime/native-whitepeace-month-retry-{ready,after}.json。当前等待用户确认新通知及接受结算。

### 原生接收后闪退：发送版停用

用户确认收到月度冷却后的提议，随后报告Paradox Crash Reporter。尚需确认是点击接受还是打开/查看提议时触发。报告目录为userdata/crashes/eu4_20261004_154955，exception.txt报告C0000005，异常地址0x7ff7577dd670。结合已记录基址0x7ff756750000，故障RVA=0x108d670，函数范围0x108cd90–0x108d6f7。指令先取[rsi+0x40]，再解引用该指针；参数来源是函数第四参数，尚待dump寄存器/对象确认。原生条约默认构造后的参与方数组为空，而真实原生页面初始化后的条约数组非空，这是当前有依据的候选原因，不是已确认结论。

minidump.dmp约74MB已生成，未上传。暂停所有发送测试；新增work/native/SEND_DISABLED，启动脚本-Sender拒绝加载。原生接收成功不能等同安全结算，接受/结算验证当前失败。没有继续提交、没有修改冷却或强制和平。

### 接受崩溃的直接原因已确认

用户确认点击“接受”后闪退，此前点击“拒绝”未闪退。本地 minidump 解码证明：RVA 0x108d670 的 `mov rcx,[rax]` 读取空地址，RAX 来自 RSI+0x40。RSI 指向虚表正确的 CPeaceOffer，双方句柄为 ENG/FRA，但 +0x28、+0x40、+0x58、+0x70 四组参与国数组全部为空。直接触发原因是接受路径读取不完整提议的空参与国数组，而不是仅凭现象推测。证据在 work/runtime/native-crash-analysis.json。

默认构造器只完成结构初始化；手填双方句柄不足以构造可安全结算的战争提议。拒绝成功、深复制和析构测试均没有覆盖这一要求。尚不能凭崩溃断言和平后果在崩溃前是否已经执行。源码新增硬拒绝分支，不允许默认空对象进入发送流程；旧 DLL 仍禁用。下一步定位完整的原生战争上下文初始化入口，先验证参与国、方向与条款完整性，再重新验收接受结算。

离线定位完整构造候选 RVA 0x975bb0，调用 0x97bd10 初始化四组战争参与国数组，并初始化其他派生数据；两个原生调用点支持四参数 ABI。新的 eu4_bridge_warcontext.dll 构建通过，SHA256=7507628825191c8f12f85841053b24ea5bc98437bac9ff0eb7c12fc337c08fc6，只提供不发送的构造/深复制/销毁测试。发送入口仍硬拒绝，未注入、未实测。审计记录 work/offer-initializer-audit.md。

### 完整战争上下文构造实测通过

用户加载 warcontext 版后，进程32004、帧线程43960、玩家ENG句柄与投递器链持续有效。触发一次 action-roundtrip.request，原生完整构造生成 +0x28/+0x40/+0x58/+0x70 四组数组，成员数2/6/2/6，每个国家句柄均与数据库对象匹配。日志 action_roundtrip_begin→四条 war_context_vector→action_roundtrip_ok，send=false，其后帧回调持续，没有线程切换。证据 work/runtime/native-warcontext-lifecycle-validation.json。

该结果验证完整构造、动作复制与析构，不验证双方成员语义、接受或和平后果。没有发送。只读探针新增参与国数组明细读取，下一步与用户打开的原生空议和页面核对方向及成员，发送禁用状态继续保留。

### 原生页面参与方对照与修复发送版准备

用户打开英格兰对法国空议和页面后，只读确认原生 +0x48 条约数组成员数6/2/6/2：法方 FRA/AMG/AUV/BOU/FOI/ORL，英方 ENG/POR；另一方向 +0x208 为2/6/2/6，首成员和顺序对应反向双方。所有句柄通过数据库一致性检查。证据 work/runtime/native-warcontext-ui-comparison.json。前一次完整构造的数组人数与反向条约一致，但未记录其逐项成员，因此不称为已经逐成员完全对照通过。

修复版加入条约双方字段、各列表领头国家检查，以及包装动作深复制的四组数组必须独立分配、逐项与源条约相同的检查；不满足则不投递。成员句柄逐项写入日志，便于下一次实测对照。使用完整原生构造，仍保留原按钮预览、日期保护、原生投递与所有权流程。编译发送功能仅通过显式 EnablePeaceSend 开启，旧 sender DLL 禁用标记保留；新参数 RepairedSender 核对新 DLL SHA256。

eu4_bridge_sender_repaired.dll 的 -Werror 构建通过，SHA256=1481e6993653757ecc3244e251aae1595dc42986eeb7377316df12b1d181f193；独立 Python 进程以 DONT_RESOLVE_DLL_REFERENCES 映射确认x64架构及 BridgeStart 导出 RVA 0x3370，不执行其代码。尚未注入、尚未发送、接受结算仍未通过。下一步新进程加载修复版，先执行带完整检查的不发送测试，再受限发送一次并验收接受及战争状态。

### 修复发送版完整预检通过，等待外交冷却

用户加载修复版后，进程22148、线程20452持续正常。一次不发送测试记录四组列表的每个句柄，与原生页面反向条约逐项比较完全一致；新增双方字段、列表首成员及独立深复制完整性检查全部通过，日志 action_roundtrip_ok/send=false，其后帧继续。证据 work/runtime/native-repaired-sender-lifecycle-validation.json。

只读日期预检显示当前56461200，上次法国外交日期56460528，差672单位，按既有24单位/日观测为28天。按钮日期保护通过，但一个月通用外交冷却未排除，因此本次未发送。需要推进超过冷却，再执行一次受限发送；无需替换 DLL 或重启。

### 修复版单次白和平已执行，等待玩家接受验证

用户推进后当前原始日期56462184，上次法国操作56460528，差1656单位，按既有观测为69天，已超过一个月。帧线程20452正常。仅触发一次 whitepeace.request，四组完整参与国列表有效，原生预览 raw_result=-34/flag=0，投递返回true。随后只读确认法国+0x24a0从56460528更新到56462184，与本机已定位的原生命令执行路径一致；其后帧回调持续。证据 work/runtime/native-repaired-whitepeace-submission.json 及 ready/after 快照。

当前仅确认构造、完整复制、投递及操作日期更新；尚未获得玩家收到通知、点击接受和战争结束反馈。没有重复提交，未修改冷却或强制和平。下一验收项为原生通知内容、接受后无崩溃、英法及本次战争参战方停止交战。

### 修复版原生白和平接受与结算通过

用户明确报告：“战争正常结束，产生了截止到1450.7的停战期”。接受后进程22148仍运行，线程20452持续记录 frame、thread_changed=false、country_valid=true；没有再次出现此前空数组崩溃。已验证 FRA→ENG 原生白和平的构造、预览、深复制、投递、玩家接收、接受与战争结束；停战期截止月份由用户观察，未独立读取存档核对。证据 work/runtime/native-repaired-whitepeace-acceptance.json。

此为重大里程碑，但不是完整外交接口交付：原生 AI 作为接收方的接受/拒绝、带赔款或割地条款、原生报价导出、外交动作白名单和真实模型连接均未验证。拒绝测试来自旧版，修复版拒绝尚未重复验证。旧 eu4_bridge_sender.dll 仍禁止使用，修复版仅固定 FRA→ENG 白和平，不自动重发。

### 白和平保存恢复与原生赔款下一版

用户另存后重新载入，明确报告没有异常；该反馈支持本次原生结算结果可保存和恢复，不等于已验证所有条款。存档独立检查另记在 work/peace-save-verification.md（如果尚未生成则仍待审计）。

独立读取英格兰1445_06_16.eu4：日期1445.6.16、玩家ENG；ENG human=yes/was_player=yes，FRA没有这两个字段且有原生AI初始化块。英法双向关系均 truce=yes、last_war=1445.6.16，两国 last_war_ended 同日。该战争记录含双方及盟友的rem_attacker/rem_defender和outcome=1，支持原生结算；即时存档active_war容器仍在，不能称为战争文本记录已完全消失。没有显式truce_until，因此1450.7仍为用户界面确认。证据 work/peace-save-verification.md、work/runtime/native-whitepeace-save-validation.json。

原生页面金额更新链复核：0x97b130/0x97b200/0x97b3a0 实际接收 CPeaceOffer 指针，而非独立控件。新增赔款测试版调用原生上限裁剪、金额条款 setter/getter，并要求条款与+0xf0汇总一致；不直接修改金额字段。gold-roundtrip.request仅构造、读取原生费用原始数值、包装及销毁；gold-peace.request才投递固定 FRA要求ENG支付的一档赔款。所有旧参与国与独立深复制校验保留。当前不是任意金币或任意国家API。

eu4_bridge_gold.dll -Werror构建通过，SHA256=57e22df6c4ab9f7366c459df15c438a7226ff236323405e9b2ee24a72248d744，x64/BridgeStart RVA0x3790经独立进程只映射验证。未注入、未执行金额setter、未发送赔款。下一次需要加载英法仍交战且外交冷却已过的存档，在新进程安装GoldSender，再先做不发送测试。

### 首版赔款预检发现单位错误，未写入或发送

用户安装 gold 版，进程40732、线程46588、ENG句柄与帧回调正常。一次 gold-roundtrip.request 中，0x97b3a0 输入1000输出34400；首版错误地要求二者相等，因而在调用setter前停止。日志 native_gold_terms valid=false/send=false、native_gold_rejected，之后帧持续。没有执行setter，没有构造或投递带赔款动作。证据 work/runtime/native-gold-v1-lifecycle-rejection.json。

复核精确金币加号回调0x130f270：普通点击路径以1000作为战争分数内部步进，0x97b3a0将其换算成金币金额增量；中央更新0x13116e0另用100000计算金额上限，裁剪累计金额后按100单位精度取整，再调用0x97b200。因此金额条款值不应与条约+0xf0费用汇总要求相等。首版返回34400是换算结果，不能当作失败或输入单位的裁剪值。

修正版 eu4_bridge_gold_v2.dll 按上述原生顺序取得增量和上限、裁剪并采用相同取整，再set/get金额；单档测试要求条款金额读回与目标相等、费用汇总+0xf0为1000，保留深复制等检查。-Werror编译通过，SHA256=b4ea6eea06753909f8cc6d2f5d135468112e85116fc7f2f3a93caf9e46d6db84，x64/BridgeStart RVA0x37b0只映射检查通过，尚未游戏内运行。GoldSender启动参数现在选择v2。需要替换DLL的新进程，但后续不发送/发送测试可在同一v2进程完成。

### 赔款第二版首次请求因没有有效英法战争停止

用户安装v2，进程33732、线程35580持续正常。触发一次不发送请求，完整原生构造产生参与国数组人数0/0/1/0，校验失败即停止。没有进入金额上限或setter流程、没有发送、游戏帧继续。当前日期56462184且法国上次操作日期相同，与此前已结算和平的日期相符；不能把此次停止当作v2金额算法运行结果。证据 work/runtime/native-gold-v2-no-war-rejection.json、native-gold-v2-preflight.json。下一步在同一进程载入仍交战的 llm_peace_after_reject 存档，再检查，不需要替换DLL或重启。

### 原生赔款构造、写回及费用读取通过

用户在同一进程载入交战存档后，一次 gold-roundtrip.request 完成：参与国2/6/2/6有效；原生一档换算金额34400、原生最高金额860000；setter/getter均为34400，条约+0xf0汇总1000，原生费用函数0x978ed0返回1。随后独立动作副本金额与完整参与国校验通过，日志 action_roundtrip_ok/send=false，帧持续。证据 work/runtime/native-gold-v2-lifecycle-validation.json。

该结果验证了无需原生议和窗口的条约级金额设置及原生费用读取，仍未发送或结算赔款。按此前单位观测推测为34.4金币、1战争分数，具体金额/费用显示仍待原生通知对照。当前日期56461200，上次法国外交56460528，仍为28天；先推进超过一个月再发送一次，不修改冷却、不重启、不在和平存档强制宣战。

### 原生赔款提议已投递并执行，等待显示与结算对照

用户推进后当前56461920，相对法国上次操作56460528经过1392单位（既有观测下为58天）。同一进程33732触发一次 gold-peace.request：原生金额换算/读回34400、费用汇总1000、费用函数返回1，完整复制校验通过；原生预览raw_result=-100/flag=0，投递返回true。随后法国+0x24a0更新为当前56461920，帧线程35580继续。没有绕过冷却、没有强制和平。证据 work/runtime/native-gold-v2-submission.json 及 send-ready/send-after 快照。

预览返回值业务含义尚未完全恢复，不将-100称为已确认接受意愿。玩家是否收到赔款条款、实际显示金额/分数、接受及金币变动仍待反馈。本次只发送一份，未自动重试。

### 原生赔款接受与战争结束通过

用户报告战争正常结束，接受前国库显示45，接受后11，界面没有小数。进程33732、线程35580的帧回调继续、玩家句柄有效，没有闪退。结合本次原生金额条款34400、费用函数返回1，确认带赔款条款的构造、复制、发送、玩家接受及结算链正常，并产生约34金币的扣款显示。与预计34.4金币一致，但整数国库显示不足以独立证实精确扣款34.4；用户尚未明确提供通知条款原文或带小数金额。证据 work/runtime/native-gold-v2-acceptance.json。

下一步另存赔款结算后的存档，核对精确财务字段及停战/战争记录，并测试重载。白和平此前的重载成功不能替代赔款重载验证。原生AI接收方及割地条款仍未验证。

### 赔款结果重载并继续运行

用户另存、重新载入并推进两周。进程33732继续运行，线程35580帧日志持续、country_valid=true、thread_changed=false，没有报告异常。支持本次赔款结算结果可保存、恢复和继续推进；精确财务差分与存档结构另做只读检查，不能从重载成功推导全部外交操作安全。

### 原生AI接收方测试版准备

eu4_bridge_ai_response.dll 保留同一固定FRA→ENG完整构造、原生预览/费用、深复制、投递流程；唯一场景变化是发送前要求人类玩家为POR，双方FRA/ENG均不是玩家，不能在玩家ENG场景发送。配合用户在交战测试存档执行tag POR，验证ENG交还AI后由原生引擎响应，不直接替AI接受。

-Werror构建通过，SHA256=2225fe321a703bced28c6be2e633779e98f6d5730ec8e69903fed6d8a449188c；x64与BridgeStart RVA0x3910经独立进程只映射检查。启动参数-AIRecipient，默认只观察、仍需显式文件请求，尚未注入或发送。该版本仅允许这个有界场景，不是任意国家外交接口。实际接受/拒绝必须用响应或战争状态证据确认，不把preview返回值当作结果。

### 赔款重载存档身份不匹配，持久化验证仍未完成

只读检查未找到 llm_gold_after_accept.eu4；最新候选英格兰1445_06_16.eu4的SHA256仍为3354b5520934587156acedba1f4c2e9820b0d6c7bf994608e9c43beaecf5c3bc，即此前白和平证据文件。ENG treasury=45.651，不能用于证明本次赔款后的约11国库。详细证据 work/gold-save-verification.md、work/runtime/native-gold-save-validation.json。

当前进程只读日期56461608，法国上次外交56460528；早于本次赔款提交/执行日期56461920，且外交记录也回到旧值。当前很可能重新加载了交战旧档，需要用户确认战局、国库与文件名。native-gold-after-reload-state.json保存此证据。前文“用户重载并推进两周”仅保留为用户操作报告，不能判定赔款结算已正确重载。赔款当时接受/结算成功与当前保存恢复是否选择正确文件是两项独立验收。没有再次发送或新开战。

用户随后澄清没有保存，当前确为战争存档。因此本次赔款保存/重载验收明确未完成；保留当时成功结算与整数国库变化记录，不把重载旧档当作赔款持久化证据。继续采用战争存档开展AI接收方测试，不需要重做已通过的玩家接受实验。

### AI接收方场景构造预检通过，等待冷却及基线存档

用户安装AIRecipient版并执行tag POR。进程26048、线程47268，帧日志player=POR/country_valid=true/thread_changed=false，投递器链有效。一次不发送的动作构造测试完成完整参与国2/6/2/6、深复制及销毁，action_roundtrip_ok/send=false，其后帧继续。ENG/FRA均不是当前玩家，但双方human字段仍需基线存档确认。

日期仍56461200，上次法国外交56460528，28天；当前未提交提议，月度冷却尚未排除。证据 work/runtime/native-ai-recipient-lifecycle-validation.json、native-ai-recipient-preflight.json。下一步推进超过一个月、另存POR场景发送前基线，再受限发送一次。AI响应仍未验证，战争继续不能单独当作拒绝证据。

用户另存 llm_ai_peace_before.eu4 已找到，meta日期仍1445.5.6、玩家POR；当前内存日期仍56461200，未实际推进，距离法国上次操作仍28天。故本轮不发送，不把用户“已完成”当作冷却已过。存档身份明细保存于work/runtime/native-ai-before-save-identity.json，实时预检为native-ai-peace-send-ready.json。下一步让用户明确推进到1445.5.15或更晚，再暂停保存同名基线，避免相对“一周”指令未执行造成重复无效提议。

### 首次FRA→原生AI ENG白和平投递已执行

用户重新推进并保存，基线meta为1445.5.23/player=POR，内存当前56461608、法国上次56460528，相距1080单位（已观测单位下45天），日期保护通过且超过月度冷却。确认没有残留请求后仅创建一次whitepeace.request。日志ai_recipient_context确认玩家POR、FRA/ENG都不是玩家；参与国完整、动作独立复制有效；预览raw_result=-26/flag=0，投递返回true。随后法国操作日期更新为56461608，线程47268帧持续，无崩溃。

证据 work/runtime/native-ai-whitepeace-submission.json、native-ai-peace-send-ready-v2.json、native-ai-peace-send-after.json。这里只验证向非玩家目标发送已执行；AI实际接受或拒绝尚无明确证据。下一步让用户推进短期并另存llm_ai_peace_after，对照战争、停战与响应记录。战争继续本身不等于已验证拒绝，预览-26也不是最终响应。

### AI接收方首轮未结算，响应结果仍无法确定

用户反馈战争未结束、葡萄牙无消息；这与POR不是提议双方的场景相符，不能要求POR必定显示ENG的拒绝通知。存档before=1445.5.23、after=1445.5.28，meta玩家均POR，ENG/FRA均非human，双方战争仍在。法国last_sent_peace_offer_date从1445.4.8更新为1445.5.23。未找到明确接受、拒绝或原生pending/in-flight字段；字段缺失也不能证明没有运行时待处理动作。证据 work/native-ai-peace-save-comparison.md、work/runtime/native-ai-peace-save-comparison.json。没有再次提交。

### 响应记录版准备（尚未实测）

新增可选BRIDGE_TRACE_PEACE_RESPONSES：严格验证本机和平动作虚表+0x48原方法为RVA0x598f00，安装8字节原子指针替换至汇编观察桩。观察桩保存并恢复易失寄存器、XMM0–5、flags及原调用栈，尾跳原方法，避免猜测完整函数ABI或改写其返回值。仅记录FRA/ENG配对对象的双方句柄、+0x34状态、日期、方向、预览标志和费用，原动作不写入。回调只写最多64项有界缓冲，帧线程输出日志，不在回调里执行I/O或额外引擎方法。

安装与帧hook在现有线程暂停期间进行，vtable目标保护/身份失败则恢复帧入口，不重复安装；新方法原值保留用于转发。不支持卸载或同进程替换DLL。状态码0/1/2的完整业务解释仍需结合实际路径验证，单条trace不是所有接受后果的保证。

eu4_bridge_ai_response_trace.dll -Werror构建通过，SHA256=bbb55d002a77a5e6ab83b9352fb5926f0db534ebf39d06eec9315dc0f19efffd；x64/BridgeStart RVA0x3d50仅映射检查通过。启动参数-AIResponseTrace，默认不发送，仍要求玩家POR才允许固定FRA→ENG发送。新观察点尚未安装，继续做独立源码复核，再在before基线重跑一次。

独立审查发现保护恢复失败时hook可能残留；现已补充回滚：恢复虚表原指针及帧原始字节；极端回滚失败单独报告hook_rollback_incomplete并要求重启，不误报未安装。重建-Werror通过，当前AIResponseTrace DLL SHA256=a86295dd111e69673136e9695999f09ca01226ca260ad6de837ca2f2dc6f5489，加载器哈希已同步。旧SHA仅是先前构建历史，未注入。等待增量复核。

增量独立复核通过（work/response-trace-review.md）：残留hook回滚缺陷已修复，当前未发现阻塞性缺陷，DLL哈希一致。64项一次性队列与state_raw未验证语义仍为限制。尚未注入新响应记录版；下一步用户重启、载入1445.5.23的llm_ai_peace_before、暂停并执行-AIResponseTrace。

用户安装AIResponseTrace后：PID50668，response_trace_installed/hook_installed成功，帧线程16296，玩家POR，国别和投递器链有效。只读预检日期56461608、法国上次56460528，guard_passes=true，符合发送前基线。已创建一次whitepeace.request；截至检查日志仅41帧，请求尚未消费，不能报告已投递。需用户返回游戏使帧继续并推进5天。预检证据work/runtime/native-ai-trace-preflight.json。

响应记录首次捕获成功：PID50668/线程16296，FRA→ENG白和平请求已消费，preview=-26/flag0，submitted。随后原生598f00入口记录同双方、date56461824、state_raw先0后1，费用0；帧继续无崩溃。只读当前56461848，法国上次56461824。state1与静态候选执行分支一致，但入口观察不证明分支完成；等待游戏战争/停战与存档核验。实际发送日期晚于创建请求时基线，说明后台帧停滞期间游戏推进后才消费；不再报告发送于基线5月23日。证据native-ai-trace-response-evidence.json和native-ai-trace-after.json。

用户确认state0→1后战争仍未结束。完整控制流窄复核推翻先前状态1结算判断：599658状态1子图无通往59a716/9765a0的边，状态0/2后续才存在调用汇合路径。旧审计已更正，不把本轮state1视为接受。没有重复发送。下一步拟在发送前基线使用控制台给FRA最大战争分，保持ENG原生AI，再验证另一响应路径；不改响应状态、不绕过AI决定。

winwars准备检查：PID50668仍同一记录器，帧日志显示FRA→POR切换，当前玩家POR。只读当前日期56462352、法国上次56461824，距上次仅528单位（已观测24单位/日下22天），且不是发送前基线56461608/56460528。未能确认载入before基线或100%战争分，故未创建发送请求。为排除月度冷却，需要明确重载before后暂停执行tag FRA/winwars/tag POR并确认分数。

用户再次操作后发送前基线核验成功：PID50668/玩家POR，current56461608/法国上次56460528，与before吻合，距离45天。用户已报告执行winwars，但100%数值未独立读取。已创建一次whitepeace.request，等待游戏帧消费和原生预览/响应，不重复请求。预检native-ai-winwars-preflight-v2.json。

winwars第二轮结果：用户推进5天、切到ENG未见提议，战争未结束。日志第二次preview=100/native_flag208=1，submitted，但没有新response事件。只读after current56461728、FRA last56460528（仍是发送前值），故不能称为实际发送成功或AI拒绝。第二轮与首轮的-26/flag0/date更新/response0→1不同；命令可能在队列后的有效性检查被丢弃，具体待执行器审计。证据native-ai-winwars-submission-evidence.json、native-ai-winwars-after.json。当前玩家POR已由只读确认，无新请求。

新增受限发送前诊断BRIDGE_DISPATCH_DIAGNOSTICS：独立clone上调用已确认的+80/59b480有效性方法，参数与4e7c80一致，记录原始返回与状态，不改返回值；失败则不提交并正常释放。eu4_bridge_dispatch_v1.dll构建-Werror通过，SHA256=0c031d88df66c87defd9a534928441e3ff49c4bbf88bdd7bb56525ef7081d70c；启动开关-AIDispatchTrace已配置哈希检查，PS静态语法检查通过。仍是发送前预检，不声称已观察执行器内部返回；新DLL尚未注入，等待增量审查。

诊断增量独立复核通过：未发现阻塞性ABI/生命周期问题，DLL哈希一致。原生+80会在预检和实际执行时调用两次，可能受外部状态变化影响；预检不替代实际执行记录。下一步用户重启加载before，暂停执行tag FRA/winwars/tag POR，再安装-AIDispatchTrace，默认不发送。

用户授权尽量自动化、至少重开游戏由Codex完成。新增restart-game.ps1：精确路径/哈希/单进程验证、保留原启动参数、优先关闭窗口、超时只结束已验证PID，恢复同目录启动。已成功退出旧PID50668并启动PID49860；未修改配置/存档，诊断DLL尚未安装。用户只需载入before和设置测试战局，下一步Codex负责安装和请求文件。

自动化安装dispatch_v1完成：PID49860，用户载入before并报告执行FRA/winwars/POR，预检playerPOR/current56461608/last56460528。加载器exit0、BridgeStart RVA3fe0、响应槽和帧hook安装成功。仅创建一次whitepeace.request等待帧处理；尚未报告发送或有效性结果。用户不再手动执行安装脚本。

dispatch_v1运行结果：线程50072，FRA→ENG参与国有效，preview100/flag2081。新增preflight identitytrue/native_validtrue/state_before0/state_after0，随后submitted。帧继续无崩溃；未发现response。只读current56461776/FRA last56460528不更新，玩家POR。说明发送前有效性通过，不足以证明排队后执行成功；不能归类AI拒绝。证据native-dispatch-v1-evidence.json、native-dispatch-v1-after.json。下一步窄审计14ca110和1580270调度及原生callback实际入口，未重复发送。

队列窄审计确认：原生UI也调用14ca110，成功进入transport1580270环形缓冲路径；命令执行器4e7c80在command vtable1c814b0+48，现有trace是action vtable1c7b840+48响应，两者不同。新增execution_v1仅改一个观察槽，保留原参数尾跳和回滚，不扩大hook数。-Werror构建通过SHA92a44abbf4ea0f6b95050377ca25d610ee793add45c846f33e7d222ba23fbb05，加载器-AIExecutionTrace哈希/PS语法已配置检查。等待独立增量复核，未注入。

execution_v1增量独立审查通过，无阻塞性问题，槽位/owned action/哈希一致。已按持续授权自动重启游戏更换DLL，未写存档，不自动发送。待用户载入before与FRA/winwars/POR后由Codex安装-AIExecutionTrace。

execution_v1自动安装实测：当前游戏实际PID10072（先前自动启动47360已退出；按实际进程重做读取），玩家POR/current56461776/FRA last56460528，基线后7天、距离操作52天，冷却充分。BridgeStart退出0，command_execution_trace_installed槽1c814f8原方法4e7c80。已创建一次whitepeace.request，等待帧执行，尚未报告入队或实际执行。用户报告完成FRA/winwars/POR。预检native-execution-v1-preflight.json。

execution_v1首次AI和平成功结果（2026-10-05用户报告）：线程34416，预览100/flag2081，有效性true，submitted后实际command execute入口记录同FRA→ENG/date56461848状态0→2，费用0。用户确认两国和平、看起来无领土变动，符合白和平。由命令入口及用户结果建立本场景state2与成功结算关联；不把编号推广到其他动作。未伪造响应，ENG与FRA均非玩家，POR玩家。存档结算/停战/领土核验尚待，证据native-ai-whitepeace-acceptance-evidence.json和native-execution-v1-after.json。此前dispatch_v1无执行结果的原因仍未定位，不能称为修复了队列问题，观察版成功可能与运行/战局条件差异有关。

独立存档检查完成：llm_ai_peace_before和葡萄牙1445_05_30字节相同、日期1445.5.30，目标文件仍有英法活跃战争、无双方停战。该文件早于本轮实际发送，不能用于否定用户当前和平结果。2472省份owner与旧beforeBackup相同，只证明旧战争档间无领土变化。用户需另存和平后档llm_ai_whitepeace_accepted；运行态成功与持久化验收分别记录。详细work/native-ai-whitepeace-settlement-save-check.md。

白和平保存验收通过（2026-10-05）：llm_ai_whitepeace_accepted.eu4，meta1445.6.9/playerPOR。与发送前llm_ai_peace_before.eu4（1445.5.30）比较，英法活跃战争1→0，ENG→FRA和FRA→ENG truce均yes，法国last_sent_peace_offer_date1445.6.2。2472个有owner省份逐项比较无所有者变化，符合白和平。证据work/runtime/native-ai-whitepeace-saved-validation.json；验证器work/verify_whitepeace_save.py只读，不改存档。尚未验证重载，不声称稳定性已解决。下一步使用同进程同DLL、重新载入战争基线测试gold-roundtrip后gold-peace（一档native money），需用户保持POR并暂停；先验收原生费用和有效性，再实际发送。

AI赔款预检：用户载入交战档，当前玩家POR/current56461776/FRA last56460528，日期足够，当前execution_v1帧线程34416未变化。仅创建gold-roundtrip.request，构造/读回/克隆/释放一档原生金钱条款，不投递。100%战争分是否保持将以随后原生预览验证，不仅依用户简短答复假设。证据native-ai-gold-preflight.json。

赔款构造测试通过但遭原生AI议和干扰：gold-roundtrip日志send=false，nativecurrency34400（预期34.4金币）、ceiling860000、aggregate1000/nativecost1/validtrue，克隆释放action_roundtrip_ok。本轮没有gold_peace_submitted。随后记录另一条原生ENG→FRA（非桥接固定FRA→ENG）动作，direction0/date56461800/state0→2；用户报告大量英格兰割地并和平，强证据表明原生ENG主动提供条款且原生FRA接受。具体省份尚未保存核验。原生AI外交排他控制目前未实现，不能称LLM独占法国外交。下一次先保持暂停重载基线，直接提交已验证的一档金额，不让两国AI在准备阶段推进天数；后续必须研究按行动主体与响应者分别拦截原生AI和平发起/接受，且保留LLM指定请求及军事经济AI。证据native-ai-gold-roundtrip-interference.json。

AI赔款实际投递准备：用户重载交战基线并保持暂停，玩家POR/current56461776/FRA last56460528，日期保护与冷却充分；当前execution_v1线程34416。已创建一次gold-peace.request，将原生一档金钱条款FRA要求ENG支付，预期34400raw/34.4金币/1战争分，仍先原生有效性校验。尚未消费/提交，不推进天数以降低原生AI竞争。预检native-ai-gold-send-preflight.json。

用户报告赔款测试仍被割地议和抢先并要求先禁原生AI外交。日志gold条款构造sendtrue/nativevalidtrue/preview100/submitted，随后FRA→ENG state0/date56461776，之后另一ENG→FRA state0→2/date56461824，与原生提议干扰一致。执行入口记录FRA金钱aggregate为0，与投递前1000不同，原因未定位，不声称赔款AI结算成功。当前没有权限锁，暂停条款测试，优先审计拦截点和现有模组覆盖。证据native-peace-authority-before.json。

和平隔离原型peace_lock_v1构建-Werror通过，SHA230a6a81153d1ce6d2b94113126a87e7aa1421a245437c38465889c9c545105f。发送编译禁用，genericcommand observer只识别已验证peace类并匹配完整FRA handle；所有France相关请求/响应在执行前短路，其他命令尾跳原方法。读取日志字段失败/队列满仍保持既定阻止决定。PS加载开关-PeaceAuthorityLock与哈希检查配置通过语法检查。待独立C++/汇编增量审查和运行验收，尚未注入。本版不是所有外交锁，不覆盖事件直接effects。

peace_lock_v1独立增量复核通过：RET栈/寄存器/flags恢复、透传、全状态锁及发送禁用均无阻塞问题，哈希一致。保留边界：法国数据库对象身份读取失败时透传，因此身份必须在运行预检与实测期间有效，失败时不得宣称隔离完整。运行验收尚未开始。

peace_lock_v1安装运行成功：当前真实PID13860（自动启动父PID43832已退出；安装前重新枚举），玩家POR/current56461776/FRA last56460528。只读slot122/fullhandle100007a00415246/index匹配，国别身份有效。BridgeStart返回0，command槽1c814f8/4e7c80安装成功，peace_authority_lock_installed controlledFRA/bridge_sending_enabledfalse/other_diplomacy_lockedfalse。无残留请求，无新和平投递。证据native-peace-lock-preflight.json；下一步高战争分触发原生和平尝试，观察native_peace_authority_blocked和战争持续，军经AI运行需用户观察。尚未称权限隔离验收通过。

和平隔离运行验收通过：用户推进超过1个月仍未和平、军队正常。线程51144帧持续country_validtrue/thread_changedfalse，日志native_peace_authority_blocked共3次：ENG→FRA state0/date56461848，FRA→POR state0/date56461872和56462424。已证实发生过尝试且执行前被阻止，不只是未出现提议。本轮未测试state1/2单独拒绝路径，但策略所有state均拦截；没有新的LLM发送。证据native-peace-lock-validation.json与native-peace-lock-after.json。范围仅原生peace类，不是全部外交，也未开放授权LLM通道。

2026-10-05资源事故：用户报告pwsh天量内存和磁盘读写。即时CIM检查定位本轮子代理遗留PID46320和21524，均全量Get-Content读取350412365字节offer-action-4e64.txt，PageFileUsage分别9476008/9867560 KB，working set因换页仅约180MB。核对准确PID/命令后已终止两者，未停止游戏或用户其他程序；后续枚举仅本次检查shell，系统可用物理内存约6.7GiB。磁盘后续采样读约12.8MB/s、写0、队列0，EU4 PID13860 Respondingtrue。暂停本轮逆向工作，新增work/AGENTS.md限制>10MB文件流式/rg读取、函数范围反汇编、shell session收尾、分析进程提交内存1GB上限。异常是分析方法和进程收尾问题，与游戏hook并非同一进程。

2026-10-05交接整理完成：新增HANDOFF.md作为当前权威状态入口，区分已验证能力、残余技术未知、工程工作、当前和平锁边界、版本/哈希、复现步骤、证据索引、项目外存档资产和资源事故规则，含新对话启动文本。更新README/PLAN首页，原生README改为当前运行手册，旧内容保存README-history-2026-10-05.md。12个证据路径存在性检查通过，peace_lock DLL哈希与文档一致。没有重启游戏、改hook、扫描大文件或重新开始逆向。文档写入shell session已收集退出；进程复查只有本次轻量检查pwsh，无遗留大扫描。
# 2026-10-05 授权宣战入口增量

已静态定位 `declare_war_with_cb` 参数解析 RVA 0x629650、执行 0x629b10、战争动作构造 0x5004b0/vtable 0x1c80d90 与原生处理 0x4ea850；此类型不被 v7 的 generic-command/peace 类型过滤识别。新增 `work/inspect_native_war.py`，准确 EXE 哈希、vtable 槽、构造与处理调用目标核对通过。详见 `work/native-war-authorization-audit.md`。

compiler、Codex harness/schema 和可选 planner 已增加固定 FRA→ENG、cb_core、177 的 `declare_war` 请求。前置检查 AI/独立/锁/国家存在/无交战停战联盟/CB/省份；全程不清锁，只在实际交战且锁和 AI 仍开启时标记请求并回报 applied。旧手工测试清锁重试已移除，复用正式 compiler；已生成 `llm_war_test.txt` 和配套只读诊断。

19 项 bridge 单元测试通过，diff whitespace 检查通过。**尚无本轮与 v7 同时运行的宣战、保存和重载证据**；历史脚本宣战成功不能作为新组合验收。用户选择已有实验档，但已知档为交战或停战状态，转为自行建立葡萄牙非铁人新实验档；等待保存 `llm_war_v7_before` 并保持暂停，之后核对和安装 v7。

## 2026-10-05 v9 同进程自动宣战与白和平验收

v9独立DLL合并v7授权和平发送、v8外交官/关系日期检查与固定原生run宣战请求消费。SHA256 `1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3`，严格编译通过。载入1445.1.1/POR实验基线后BridgeStart=0，PID32336，帧线程45052；此前主菜单预检未通过且没有注入。

固定run evaluator自动执行`llm_auto.txt`，native_success=true，ACK war_auto_01 applied、正式快照ai/war/locked均1，实时战争关联确认英法交战。战争状态授权自检通过。独立实验请求自动tag FRA→winwars→tag POR，三个调用成功，完整玩家句柄恢复。宣战后法国无空闲外交官，首次白和平预检停止且没有生成请求；用户手动推进约一个月后法国一名外交官空闲，日期/冷却通过。

统一动作入口排队白和平，native preview=100/valid=true/authorization=2，授权经原生clone和协议序列传播，原生执行state_raw=0→2。最终同PID只读探针确认FRA和ENG战争关联数组均为空、玩家槽189/POR、日期raw56459208。宣战与议和之间没有重启、重载或重新注入。证据`work/runtime/v9-cycle-validation.json`、`v9-cycle-native.jsonl`、`v9-war-pair-before-peace.json`与`automatic-cycle-settlement.json`。

`tools/run_diplomacy_cycle.py --pid <PID> --test-winwars`串联固定阶段、等待外交官/冷却、原生接受和只读结算；已确认阶段跳过，支持同PID恢复。19项bridge测试通过，diff whitespace检查通过。本轮用了winwars实验条件、用户推进时间；没有验收自然战争分接受、保存重载、玩家FRA或外部模型服务。详见`work/automated-diplomacy-v9.md`。所有分析shell已退出，无残留实验请求。
