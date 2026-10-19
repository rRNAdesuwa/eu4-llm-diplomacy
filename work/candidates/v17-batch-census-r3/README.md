# 批次初始／最终状态汇总

只在两个批次边界读取内存，不做逐动作比较，也不调用引擎函数。使用已冻结 v7、v10、v11 与普通侮辱只读采样器，统一保留 22 个类型化观察及两份完整国家／外交官诊断；每个子观察器仍执行自身两遍校验。外层持有精确 PID/creation 句柄，前后核对世界、玩家、日期和暂停状态；跨多个采样器的组合并非原子快照。

`sample(command)` 接受批调度器的内部 observe 命令，预先以 CREATE_NEW 保留输出路径，失败不覆盖、不重试。输出 `cross_date_selected_state_census`；两个边界之间可以推进日期，禁止将它们送进旧同日效果 matcher。state0 外交官只记候选资源，不能替代原生合法性。正向后取消的中间状态未观察，individual effect / causal / SP / epoch / production 均为 false。

本候选尚未实测、未注册到生产接口。纯校验测试：`python -B -m unittest discover -s work/candidates/v17-batch-census -p test_census.py -v`。sampler 的原有原生布局及具体状态解析并未在此重复证明。

R2 validates each diagnostic stability flag and boundary binding; compares full handles numerically to preserve canonical padded encodings. Original candidate remains sealed.

R3 binds the selected observers reference full player handle to the held outer process snapshot before any selected observer. Two fake-memory pipeline regressions exercise this call site. R1/R2 remain sealed.
