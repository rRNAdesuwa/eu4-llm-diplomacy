# 当前 integration task 只读候选

独立候选只回答指定当前 pair 的选定索引状态。CLI 为 `check`、`catalog`、`status --pid … --creation … --actor FRA --target AUV`。默认 source-manifest 是 draft：`sealed=false`、`runtime_capture_authorized=false`，所以 status 在构造 runtime observer 或打开进程前拒绝。只有候选独审完成、root 另行封生产清单后才可实采。本目录不会替换 stable15/候选18、原 native 或已有 observer。

- `selected_task_present`：两个方向的 +0x200 索引选择同一个 P，P 精确匹配所选静态 vtable、完整端点集合与 P+0x28==0。
- `selected_index_absent`：两方向都没有所选键。它只表示当前选定索引缺席。
- `unknown`：单侧、其他 vtable、完整端点不匹配、removed 非零、源变化、读取失败或未支持状态。不会将别种任务当成 absence。

status 的退出码 0 可对应 presence 或 absence；check/catalog 的 0 是文件验证成功。2 是 unknown/非法输入。退出码都不是整合动作成功、取消成功或整合完成；没有重试、dispatch、HTTP、watch、publisher 或原请求/session 授权。

## 精确读取范围

复用冻结 direct-truce 源 `5429932a…` / manifest `47cfc947…` 的 Libraries 与 oldhost 的 source guard / host_sample。只 exact-compile 其固定字节，不运行旧 main、固定80340捕获、Frida、REA、registered argv 或旧 Job。PID/creation 来自当前用户选择；要求非零 DWORD PID、非零小写16hex FILETIME、两个不同三字符TAG。RuntimeCapture 的 held身份、游戏绝对路径、PE/disk SHA与module集合照旧严格验证，manual pause必须1，研究模块拒绝。

每pass重新读取完整1380指针表，并通过完整句柄/正slot映射选国家。冻结 typed country 与 relation() 核 country+14f8 的 root type/owner、country+1510 的 rows 指针、row[0]=root、row+8=owner fullhandle、row+10=other fullhandle。索引属于这个 embedded relation root，**不是 country 本体的 +0x200**。

冻结 index() 用 `<Qii>` 的 array/capacity/used 与 `<i4xQ>` entries 读取 +0x200 索引，全 active used entries 检查正slot/唯一性/指针边界。capacity+0x208、唯一性、双向同P等是 reader 的额外 guard，不冒充 R45 native getter 已核。两方向都存在时读 P 的0x48 B：只要求 vtable=base+1c816d8、P10/P18完整端点集合匹配、P28==0。P8保留原像但不要求 marker357。P+20仅输出 `raw_u32_at_20`，不叫 date、start 或 progress。端点有序值原样保留，不给 actor/target 补领主或发起者角色。

两个完整sample必须相等，包含表、国家、pair raw、索引摘要和任务raw；同地址不是跨时刻原子性/寿命证明。R44/R45/R46及独审提供静态profile，实际typed匹配不等于完整C++ class或全部副作用。

## Loaded profile、预算与提交

前后各核四块：R44 `51b6e0` 完整2259 B，R45 getter `a6a780` 完整103 B，slot `1c81720` 8 B按本次真实base改成LE64(base+a72f50)，leaf `a72f50` 6 B。每轮2376 B，两轮4752 B。不会将磁盘preferred VA直接当 loaded slot。leaf没有调用执行；其RET隐式stack读取也不是本工具实际行为。

一个共享 BudgetReader 覆盖 host_sample前后、code/slot前后、两遍完整表和所有选定对象，限制4096 calls、512 KiB、单次65536 B。host per-sample预算由独立view计数，但底层仍进同一reader；无修改冻结模块。ordered raw RPM journal 按stage保留成功原始字节和失败原因。冻结RuntimeCapture入口的1次8192 B PE身份读取单独列账，未进入此journal，不假称全进程原子快照或全部RPM都已journal。

只有正常退出 with、held.handle确实为None、最后source guard通过后才提交presence/absence。冻结close没有证明OS CloseHandle返回成功，输出 `close_os_return_checked=false`。任何错误都留unknown，不自动重采。

新的nonce仅是只读关联nonce，绝不重标为安装TAG session或原请求。native/effect/action mapping/lifetime/atomic/persistence/完整class flags始终false。presence不证明AI接受、完成或持久化，absence也不证明取消或拒绝。

## 来源和离线准备

候选清单固定21个选定输入，精确bytes/SHA见生成的source-manifest。选定R44/R45/R46合同/原像与各封存manifest互相绑定；R44/R45独审 `4bce2319…`、R46独审 `72e009de…` 已有真实文件，候选自身独审仍pending。静态producer依赖不被重新执行；direct/oldhost完整闭包由其冻结verify函数校验，旧19/215来源不复制成新实现。来源在import前、读前、读后和最终commit前校验。

只运行本候选新fake字节图测试，以及check/catalog各首次一次。`run_offline.py` 使用精确锁定Job helper，为每个新子进程提供45秒/768 MiB限制，收齐退出码和active0；不重复冻结测试、不执行status或触游戏。失败时保留首次回执，后续只做必要窄修。当前源待独立审查与root生产seal，不含实机验证声明。
