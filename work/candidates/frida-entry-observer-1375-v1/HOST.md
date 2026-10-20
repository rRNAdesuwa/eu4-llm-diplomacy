# 固定进程入口采样候选宿主

`capture_once.py check`只检查文件；`capture`只有一个固定目标80340/creation01dd5c075fcf8c26，单次exclusive claim，无目标/输出覆盖参数及自动重试。它只观察自然发生的10a6ec0入口，不调用游戏函数，不派发外交动作、保存、重载或修改游戏字段。Frida会暂时修改代码，所以此工具不是pure RPM。

实际加载前须有独立审查通过的sealed host-manifest.json。先验证完整stable observer和build7 source_pins闭包，以及选定REA编译入口、dispatcher、锁文件、binding和Node文件。选定external pin不宣称REA/node_modules的全传递闭包。候选Python模块用验证过的源字节编译；正常bridge依赖仍由冻结原有导入机制加载。只接受当前已登记的同一本地Node/REA命令、空override env和无cwd；不保存或输出配置与环境内容。

游戏用已有QUERY/VM_READ held handle从attach前一直持有到结束，核creation、EXE/载入PE、base、暂停/世界/类型/模块、原入口32B。渲染文件包含固定8字段config和nonce，REA Evidence的source_sha256必须等于这份完整UTF8文件。Evidence严格验证真实字段、参数/会话/pid/device交叉绑定、semantic ID、唯一send消息、无binary/error/log/truncation和双cleanup_error=null。ID是内容散列，不是签名或进程身份。此固定profile只接受ASCII、safe integer、bool/null JSON，拒绝重复键、float、未知字段和超限。状态running来自close前，不能要求detached。

内部脚本1000ms timer是soft；REA 1500ms delay发生在attach/load之后，均不保证全命令时限。仅新CLI进程树放进独立Job，45秒主循环加独立5秒cleanup阶段、768MiB和8 active限制。两路输出各2MiB是接受上限，writer可能在采样前超出后被拒绝。job无法证明目标agent回收。脚本/REA报告卸载后，宿主无论结果正反都先尝试从held目标直接读原32B，再核世界和源文件；不盲信脚本cleanup语句。

成功仅标记真实入口owned记录的structural_match、当前进程绑定和选定清理检查通过；native_ready、native_entry_authenticated、lifetime lease、atomic snapshot永远false，不开放war/peace执行器。清理检查不证明Frida全部内部分配或agent映像已解除映射。所有不符合预期的结果为unknown，claim保留，禁止自动重试。

当前阶段仅源文件/离线测试，尚无实际Frida attach或script load。原18个JS/41个parser/5个job测试及独立delta审计分别保留，不因host增加而重复全部测试。
