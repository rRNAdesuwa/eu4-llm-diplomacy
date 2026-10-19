# v15 固定 accept-all 测试控制：最小候选计划

本目录只有计划。未写原生实现，未物化 v15，未编译、注入、调用回调或访问游戏。冻结 v14 的 20 原生源、11 宿主、8 support、5 夹具文件及 DLL/manifest 已逐项核对；完整基线在 `input-pins.json`。

目标是在可丢弃、明确绑定 PID/creation/存档、暂停且原生窗口线程正确的研究局内，经游戏已注册的**固定零参数 handler**控制测试接受标志。绝不直接写 `game+23a1`，不向控制台输入命令，不接受外部文本、脚本、地址或原生参数。普通 AI 对 offered fleet 的评分与测试标志分支仍需引用最终静态报告；本轮提示地址不能作为实现许可。

## 必须先闭合的静态输入

等待 `work/candidates/offered-fleet-ai-response-1375/report.json` 最终 SHA 与独立复核。当前仅有未钉扎提示：callback `e50180`，显式输出似为 Result40（success BYTE0、EngineString32+8）、正常输出字符串析构 `95660`；仍要确认普通 dispatcher 的完整 ABI、零参数容器的第三指针及调用者初始化、参数拒绝分支、结果归属与 SEH 后未知边界。不得据此猜结构或先写调用代码。

## 对外是 on/off，原生 toggle 只允许一次

`accept_on` 只在 fresh flag=0 时调用一次 handler，正常返回后独立读到1、正确清理输出并完成持久审计，才建立授权窗口。`accept_off` 只在该窗口 fresh flag=1 时调用一次并核0。已是目标值时只能返回明确的 no-native 诊断；不能借此建立、替换、延长或关闭原 bound window。非0/1、异常、未知归属、写日志失败、线程/世界改变均冻结，保留所有 claim，不猜析构，不补第二次 toggle。

根代理指定首轮最严窗口：on 绑定唯一 `FRA → target`、一个已存在 pair action、紧邻未来提交序号 `on.sequence+1`。开启后只许这一次完全匹配的 submit；其他 pair（包括新的 legality-only）、speed、fixture 都拒绝。fresh legality 在 on 前完成，真正 submit 仍重复原生合法性与归属守卫。已消费 grant 永远不能补发。

已知 submit 返回/归属明确后，保留只读效果采样，再显式 off。即使效果未知，也不能编造 applied/accepted。只有 off 正常返回、flag0 回读、持久 core/wrapper 结果和后续健康暂停帧0全部具备，才结束窗口、恢复普通动作/速度。未知归属或 SEH 后不能为了清理而调用另一次原生函数；停止实验并保留证据，关闭/丢弃精确测试进程也不等于已验证 off。未关闭窗口不得继续下一组或保存验收。

## 版本与最小改动范围

建议新 `EU4LAB/3` 和 `restricted_pair_lab_1375_v15`。保留原固定字段，新增 `bound_action / bound_target / bound_submit_sequence`；on/off 必须绑定原 grant，其他操作这三项固定为 none/none/0。没有选定任何未来实际 PID、sequence 或目标。

36 个 pair ID、五个固定原生标量和 20/1/72/72 四阶段保持不变。建议22原生源：原20文件版本隔离复制，仅宿主、协议、pins、构建列表有明确功能差异，另加 `test-acceptance-1375.h/.cpp`；共9 C++ +1 ASM、10链接对象。原11宿主复制为v15，加独立 acceptance 离线验收器，共12。8个共享support保持原hash；若确实需新增逻辑，另建v15隔离文件。夹具5文件字节不变，仅新候选来源目录；不加 yesman 脚本效果。

新 manifest 拟 schema3，显式绑定新增静态报告/模块/窗口合同和源列表。新的 native-only review 必须先稳定，不能与宿主总体 review 循环自哈希。新DLL必须独立读取实际导出，不把 v14 的 BridgeStart RVA 当成 v15事实。root独占后续物化及正式单次构建；本计划不会执行这些步骤。

## 证据与计划测试

`plan.json` 列出30项尚未运行的合成测试，覆盖严格codec、claimed-once、on/off前后状态、单次精确submit、旁路拒绝、零参数容器、结果归属、SEH/审计失败、no-native不改grant、off后续健康帧、保留v14 pins和旧协议拒绝。未来测试必须调用实际共享helper，不能复制镜像实现。未来 `/c /W4 /WX` 和 mocked callback/Win32文件测试不构建正式DLL。

所有日志必须区分 handler returned、控制字节 readback、host durable completion、后续健康帧以及独立关系效果。测试接受标志开启期间的效果始终标记 forced-test，不是 normal AI acceptance，不提升 production、可靠 world epoch 或严格 SP。暂停不保证没有其他 native 行为，flag 的保存语义仍未知；关闭边界与可丢弃存档要求不能省略。
