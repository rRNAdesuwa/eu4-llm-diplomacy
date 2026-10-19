# 当前和平队列 v2：源码候选

本候选按固定 EU4 1.37.5 字节布局查询 actor→target 收件队列。尚未通过新的独立源码审查或生产批准；草稿 `status` 在 Libraries 或进程访问前拒绝。本轮只允许六项新 fake 和首次文件 `check`、`catalog`，禁止真实 status。

相对 v1 的行为变化只在 module+0x233e064：每遍仍以共享预算读取4字节并保留有序日志，但不再要求 signed32 == -1。完整 sample 附 `unclassified_scalar`，含 `rva/raw_hex/i32/u32/semantics="unknown"`。原有完整样本两遍相等比较包含该字段；变化、短读、预算或任一原有结构检查失败仍 unknown。没有 override 参数。此字段不是已证 Mod、汉化、单/多人或加载状态；本候选不宣称所有 Mod 兼容。

PID/creation、真实持有句柄、精确游戏路径/PE/SHA、735字节代码前后核验、完整1380国家表/完整句柄、暂停、队列链/计数/类型/先判tombstone、源前后核验与关闭后提交逻辑保留。`queue_sample/sample_selected/capture_class/host_sample/code_guard/SharedReader/Libraries/run/result_code` 的 AST 与 v1 相同。schema更新为 `/2`，来源清单增加 v1/授权/提案及新增本地文件。详见 `source-delta.json`。

成功只表示当前所选队列存在或缺席。ID0、重复ID与state原样保留，不证明原请求关联、AI接受/拒绝、议和完成、条款结算、生命周期、原子性或持久化。所有effect/native/lease/retry权限恒false。readonly nonce不是已安装会话；OS CloseHandle返回未核，不能称OS关闭返回已验证。

六项新 fake：稳定-1缺席、稳定1缺席、稳定1存在、1→2拒绝、4B短读拒绝、tombstone先拒绝而不读坏action。仅复制经过检查的 v1 Memory/FakeLibraries 等定义，不导入旧测试文件、不运行旧31方法。新测试必须在源码图冻结后首次运行。文件命令委托的旧固定宿主闭包保持原核验，流式读取单独计账，不运行旧host main/capture/Frida。

审查顺序：新源码冻结→六新fake与check/catalog→完整非作者source/new-fake审→root独立生产决定→另行明确真实只读授权。当前只到前两步；v1及历史失败原像不修改，原48/44/42、稳定15profiles保持。
