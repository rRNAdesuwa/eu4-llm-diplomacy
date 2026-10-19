# v16 初始接受窗口修复候选

仅本目录中的隔离源码提案；没有物化、编译、构建、游戏访问或请求投递。
完整 lineage 绑定已冻结 v15-r3、实际 v15 源码/DLL/manifest、停止失败摘要与独立原生诊断。
不能把拟输出、Python 合成回放或旧版本编译结果称为 v16 已运行通过。

v15 源码原有 `AcceptanceWindow.action/target="none"`，但实际 `.obj` 的全局窗口
位于 `.bss`，最终 DLL 对应 RVA `0x4fd80` 是零填充。独立相同编译选项的小样本
复现 namespace static/global/function static 三种空串，stack对象正常；不是已经
证明跳过CRT，更不能归因于游戏引擎。冻结失败会话108帧、0阶段、0请求、0外交提交，
完整停止摘要 SHA `2d667210b7d9960ff614cdc8056038c8106014b63a4c918a5a7f21a667705d00`。
独立诊断 review SHA `5580e1dc1df3800fccca7b5f1c5b23efb0edcd6f6c672576b70ad9a7ed44fbc4`。

## 唯一语义修复

`startup-window.inc` 注入新 v16 请求头；新 bootstrap 在 `BridgeStart` 的唯一
`installed` CAS 成功之后、任何日志或hook之前调用它。只接收 pristine closed：
所有序号/world/player/date/thread/off_frame为零，两名称数组完全全零或精确
`none`且尾部为零。helper逐项赋值并显式 memset/memcpy名称，随后精确检查；
失败返回32。任何脏尾、脏字段、未知状态、已有grant或已关闭的历史绑定都拒绝，
且不修改输入。helper本身可重复核验仍pristine的对象；实际启动只由CAS放行一次。

Python验收器不放宽。初始空串继续拒绝，初始规范字段仍是`none`；正常off后只改变
state，保留原action/target/三序号，再接受后续健康frame。没有重置活动窗口，
没有新增toggle、自动off、补偿或重试，更没有更改handler/allocator/所有权代码。

## 输出与测试

`candidate-index.json`固定47个拟输出：22原生、12宿主、8原字节支持、5原字节fixture。
9C+++1ASM/10link objects，36pair IDs、EU4LAB/3、四阶段20/1/72/72保持；purpose/output/
DLL都独立为v16，研究HTTP为`127.0.0.1:8772/research/v16`。source manifest/pin随新版本
生成，未创造DLL或编造新导出RVA。`startup-only.diff`只展示相对纯版本改名的两处原生
语义变化；`diffs/`保留完整v15→v16差异。实际v15、旧候选、shared support均不可覆写。

```text
python -B work/candidates/v16-acceptance-initialization-review/prepare.py --check
python -B -m unittest discover -s work/candidates/v16-acceptance-initialization-review -p test_*.py -v
```

`--refresh-candidate`只允许重建本目录镜像，正式或镜像v16 runtime/build/session出现
即拒绝。不存在物化、编译、加载、进程访问或投递选项。后续正式构建脚本还要求
根代理明确授权的`EU4_V16_ROOT_REVIEW_APPROVED=1`，这不是本轮构建许可。

继承51项协议/完整pipeline/claim/TTL/Stage/Reason/HTTP/manifest测试，另5项直接核
实际停止frame与C++printf完整字段集合、仍拒旧空串、只有初始化字段规范化的合成首帧、
closing保留历史和bootstrap安装顺序。初轮新schema提取测试选到较早同名局部buffer，
造成1个测试失败；已修为匹配唯一research_frame printf，未改变宿主或协议。

`test_initialization.cpp`是待根代理独立编译的真实头文件小样本，包含namespace static、
global、function static、stack、全零/规范对象、全部逻辑脏字段/脏尾、保持关闭历史。
本代理没有编译或运行它；Python源码断言不替代C++执行。原`test_window.cpp`也保留为
独立后续测试源。v16运行、native生命周期/handler效果、严格SP/epoch及生产执行仍未证明。
