# Dense费用与完整间谍只读身份包络

新候选继承固定FRA→ENG的已审只读生产者，不修改旧观察器。它把完整国家、数据库、玩家、目标、定义、能力、网络和修正记录采样放在局部dense费用读取之前与之后；两份完整snapshot必须逐字段一致。各完整采样本身仍做两遍检查，dense kernel也做两遍，最后再次核dense代码pins。共享总预算16MiB/8192次，单次不超过64KiB。

旧报告保留 `unsupported_dense_storage`，新费用候选另列在 `dense`，没有改写历史语义。实际费用、缓存新鲜度、原生合法性、对象生命周期、暂停、SP、epoch、效果和生产标志恒false。未知dense结构仍明确unsupported；费用候选不为原生发送授予许可。

`sample_process` 是未来显式的纯RO函数，尚未实际调用，没有CLI或发布器。它继承固定EXE路径/SHA、PE和模块检查，持有同一QUERY_INFORMATION|VM_READ handle，在采样前后核PID、完整creation和未退出，结束再次核依赖SHA、磁盘EXE与包含PE守卫的总读量，finally关闭。不能用人工JSON或仅局部kernel的输出代替这个身份包络。

四个离线测试方法已通过：五族真实稀疏图接入dense费用，同时保留旧unknown；kernel局部相同而外层日期/网络改变时拒绝；共享预算和精确bytes返回；全部OS调用mock后的初始与末尾held身份失败都会关闭handle。没有进程读取、原生调用、编译或DLL。

固定来源包括旧完整spy observer、dense kernel与它们的独立审查。root独立dense核验逐字节检查1713条现有指令和一个data pin，并验证五个−75%费用数值及两个reserved-id非零拒绝实例；这些仍是磁盘/模拟证据。未来真实样本需独立审查本集成后，再用明确PID/creation/world/date的调用包装器保存原始结果。
