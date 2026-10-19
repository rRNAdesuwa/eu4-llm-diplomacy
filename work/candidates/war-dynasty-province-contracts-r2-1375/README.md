# WAR4 独占包装模型 R2

此目录只修复原纯 Python `OwnedModel` 的一次包装约束。它不是原生实现，不读取或认证实际内存，不授予发送/执行能力。四族仍是 claim_throne、sell_province、enforce_peace、threaten_war；原始参数、构造、clone、拒绝后战争副作用与未闭合限制完全保留。

原独审 `406f925939ab1ef6df26575176b16460edeac7e866ed1e04221a5b4aed96430a` 的 F1：第一次 wrap 后销毁 command，原件还活，第二次 wrap 会生成新的 clone，却继承 `clone_destroyed=True`，无法正常追踪清理。原 sealed 候选和四个反例原样保留。

最小修正仅三处：新增 `ever_wrapped=False`；`wrap()` 入口要求它仍为 false；一次正常包装完成后将它置 true。销毁 command 不清除该标志。重复包装在 clone 之前拒绝，保持已有对象和清理状态；原件/命令两种清理顺序仍允许。无效日期在第一次包装前拒绝，不产生 clone。此 latch 是离线模型状态，不是对引擎支持多次克隆的新增判断。

`repair.diff` 只含以上模型变化，35 个原测试逐字复制，8 个新增方法覆盖四族原始反例、拒绝后状态不变及剩余原件可清理、两种正常清理、重复在用包装、终态异常与无发送许可。没有新增静态解码。原静态 `report.json`、facts、exploration、source index 和独审结论仅以哈希引用，不复制重写；prepare 同时核对原始整目录和输入，确保旧 seal 没被修改。

复现仅离线：

```powershell
python -B work/candidates/war-dynasty-province-contracts-r2-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/war-dynasty-province-contracts-r2-1375 -p test_*.py -v
```

`validate.py` 在本新候选的全新 validation-results 目录保存源输入前后 SHA、完整命令、输出和退出码。它不编译、不调用游戏、不改原静态证据。R2 封存后仍待独立修复复审；原静态支持不等于运行、效果、完整 unwind 或生产就绪。
