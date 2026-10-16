# 当前状态：文件查询与独立审查通过

第二版当前50条记录，26个固定JSON来源；原第一版43条逐字段不变。源码和索引已通过[独立文件审查](../../reports/war-peace-api-lookup-v2-independent-review-20261015-r1/findings.json)，67项pin核验通过。所有callable、native_ready、sender_authorized、gameplay_effect_verified与process_authenticated保持false；这是一套API证据查找工具。

首次6个CLI查询已通过。独审发现b1e020的“完整局部CFG”文案超过原合同的覆盖范围，现已更正为完整owned字节覆盖、正常返回路径地址有界，保留INT3和外调未闭合；只新增数据check和该entry lookup两个delta查询，均通过。没有重跑原6项或旧测试套件。旧7份源码、索引和清单字节保留在preimage-r1；原回执继续绑定原版本。

当前CLI SHA256：`3d983b60efdcc1711887a149b0d6203a750b99b352edd05476acbf987d799f92`；data manifest：`6f4cb91a1798df84a3ff10b5f2f7244a536a30d2995124f23fe68bb2451cf874`；source manifest：`7c72ee48d57a753526c4731b894e751255eb8267fdc83b086820305770ef6bc6`。清单中的review pending是封存时点，后续审查由独立产物记录；此STATUS不构成运行时或native授权。

用法见[README.md](README.md)。查询仅打开本地保留证据，不访问游戏EXE或目标进程，不调用Frida、游戏函数或发送请求。即时外交效果仍使用[实时观察器](../../../docs/runtime-observer-1375.md)；宣战、议和执行器尚未开放。
