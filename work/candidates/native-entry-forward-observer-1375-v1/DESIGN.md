# Native-entry forwarding：仅离线 Win64 模型

此目录是未封存的独立设计和可编译 ABI harness，不连接 EU4。模拟函数使用本 EXE 的实际 CALL 返回标签，不把返回地址替换为 gamebase+RVA。固定游戏观察目标仍为 RVA10a6ec0、SHA2569ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a；此 harness 的任何地址都不认证该来源。没有 installer、patch、detour、任意 continuation 指针、DLL 加载或游戏 API。

## 汇编入口和保存区

模拟 adapter 真正入口的 RSP 为 Q。先 SUB RSP,e8 得 S=Q-e8；Qmod16=8，因此 CALL 前 Smod16=0，callee 原始入口 T=S-8=Q-f0。这里捕获的是入口汇编的 RSP，不从 C++ body 当前 RSP 反推。

| 相对 S | 范围 | 用途 |
| --- | --- | --- |
| 00–1f | 32B | 供 callback 使用的 Win64 shadow space |
| 20/28/30/38/40/48/50 | 各8B | 原 RAX/RCX/RDX/R8/R9/R10/R11 |
| 58–5f | 8B | 未用，不接其它数据 |
| 60–bf | 6×16B | XMM0–5 的低128位 |
| c0–df | 32B | EntryBorrow：Q、原 RCX、原 R8、S |
| e0–e7 | 8B | 未用 |
| e8 | Q | 模拟原 caller return slot，保持不变 |

32B descriptor 在 c0..df，不与 shadow、保存区或原返回地址重叠。callback 的 RCX 指向该 descriptor。同步实现先 copy 为 owned 数值，再用已知模型内存读取两个投影；返回后仅保留数字和值数组。adapter 恢复 volatile GPR/XMM 后直接 RET 到模拟 caller。没有在此目录实现真实原指令 replay。

非 volatile GPR/XMM6–15 依赖标准 ABI；harness 记录前后值核该依赖。SUB/ADD 不保存 flags，本模型不声称 flags 透明。低128位 XMM 保存不覆盖 YMM/ZMM 上部、xstate、MXCSR/FPU、异常重入或 arbitrary callback 的约定破坏。

## 真实嵌套模型栈

模型 main 的 active RSP+60 保存 fixture outer。四层 frame reservation 依次为 loop48、relay78、server328、wrapper38，每次 CALL 另压8B。于是 adapter Q 的真实返回地址分别为：Q+0→wrapper、Q+40→server、Q+370→relay、Q+3f0→loop、Q+440→main，main holder 为 Q+4a8。这些是实际机器 CALL 产生的栈槽，不手填伪造返回地址。

wrapper 有两条入口路径：CALL adapter；或 CALL leaf thunk 后由 thunk JMP adapter。后者不额外改变 RSP，二者都 RET 到各自真实 wrapper 标签。harness 不执行 EU4 的入口、callback 或任何生命周期函数。

## owned snapshot 和错误边界

EntryBorrow/OwnedEntry 各32B，OwnedProjection23个 uint64=184B，OwnedSnapshot432B，使用固定标准布局断言。投影字段与 r2 Python 字节 reader 对应，byte 扩为数值、optional null 的 raw vt 用0编码并由 pointer 字段消歧。fixture root、vt、typed对象和 update 都是本 harness 私有 storage/label；固定 reader 仅允许其明确 span 和当前模型栈 span。预算单读≤8B、两遍≤64 reads/1024B，错误停为 unknown，不自动重试。

callback entry assembly 记录真实 T 数值，实际写满4个 shadow qword，C++ producer检查其与保存区分离；callback 返回前有 leaf 故意覆盖 volatile GPR/XMM，检验 adapter 恢复。callback 输出结构不含指针类型/ReadPort/descriptor 引用；归还后清空 fixture，owned evaluator 仅评估已经复制的数值。数值地址不能在回调后重新解引用。

## 验证计划和明确未完成项

离线测试：CALL/JMP×optional/null、实际五层 return-slot identity、Q/S/T、shadow canary、全部 volatile 恢复、nonvolatile 前后、返回后 owned 评估；再破坏 fixture type/current/map、越界 pointer、模拟短读、预算、两遍 root/optional 变化和 malformed owned descriptor，必须 fail closed。负面返回槽只在 reader 返回值中改变，不写实际 CPU return slot。

源包含 FRAME/.allocstack 供模型正常编译，但本轮不证明异常 unwind 或 game hook 的 unwind coverage。AVX/xstate、真实安装来源、held process/image/owner thread/reentry 认证和 header/world lifetime 仍未完成。所有 authority/native_ready 固定 false。默认 build7/44pin/DLL、旧 R1/R2 reader 与报告不改。源码自测后交独立审计，审计前不 seal。
