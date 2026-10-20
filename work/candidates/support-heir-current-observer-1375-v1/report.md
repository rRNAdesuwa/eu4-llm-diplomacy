# 支持继承人当前任务候选：首次离线准备

独立 current-reader 候选已经实现并通过首次15个新fake方法（0.140s），check/catalog各首次一次通过。源码、测试、README和22项draft清单已固定，等待独立source-ready审查；`sealed=false`、`runtime_capture_authorized=false`，没有实际status或游戏访问。

三份45s/768 MiB受限Job均exit0、累计2进程、active0且direct child已收齐。峰值job committed依次37,515,264 / 32,292,864 / 32,129,024 B；Job时长0.610 / 2.812 / 2.531秒，与方法耗时或整条shell6.3178464秒分开。首次全部成功，无失败重试、无旧套件执行。

读取合同基于已独审R48/R50和crosswalk f25d2760…。nullable root140索引保留每侧missing/NULL事实；两selected_pointer都0才selected_task_absent。单侧非零/不等指针、其他type、raw357不匹配、P28 lifecycle候选byte非零、完整端点不匹配均unknown。P64B完整raw及20/24/30/38/3c原值输出，端点无业务命名；对象检查均标明是reader额外guard。无效果、AI接受、最终继承人结果或持久化认证。

每轮loaded 4244+64=4308 B，前后8616 B。fresh完整1380表、typed选定country、fullhandles、row/root/owner/1510与两方向index双遍；共享4096calls/512 KiB raw ordered journal，入口PE身份8192 B另列。沿已审integration的正常with退出、held.handleNone、最终sourceguard后commit结构；静态AST复核9个共享函数/类完全相同，observe仅预算描述移除不再使用的slot一词。冻结direct Libraries/oldhost仍逐层验源，未调用旧capture或旧固定PID授权。

15个新方法覆盖missing/NULL四组合、0/非零及不同P、raw无业务命名、额外对象guards、nullable索引边界、无关条目不解引用、row/table重新绑定、两遍键存在性变动、对象变化/短读、loaded前后、source/close失败、共享预算、draft gate及顶层review形状、身份/源改变、false与exit0语义。旧integration的24个TestCase方法未复制执行；fixture setup和少量冻结pure函数AST用于owned memory测试。

生产清单只接受顶层 `independent_source_review={path,bytes,sha256}`。静态R48/R50审查在FIXED pins内，不混成额外nested candidate gate。`draft-source-manifest.json`保留当前canonical清单逐字原像；交付check固定该snapshot，未来root单独审查生产metadata时不会破坏本轮历史准备证据。

文件复核：`python -B work/candidates/support-heir-current-observer-1375-v1/seal_preparation.py --check`。这仅核准备文件pins，不重跑测试、CLI、producer、decoder或目标PE读取。所有 shell 已收齐；native/effect/mapping/lease/atomic/persistence仍false，原48/44/42和stable15不变。
