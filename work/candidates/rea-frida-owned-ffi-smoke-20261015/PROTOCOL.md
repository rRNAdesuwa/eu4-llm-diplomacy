# Owned-only kernel32 FFI smoke：源码候选

这是新 namespace，复用已审 metadata smoke 的 controller/fixture/严格 REA parser 流程并明确记录来源。旧候选、EU4、native DLL/public 工具都不改。当前阶段只准备源码、固定清单和运行新离线测试；**没有创建真实 fixture、执行 REA、导入 Frida binding 或调用 NativeFunction。必须由 root 审查后才执行一次 owned-only smoke。**

目的只有：验证本地 locked Frida 是否能以指定 Win64 ABI/options，给系统导出传递自有 pointer 并同步取得两个整数。即使以后成功，也不证明游戏 action ABI、C++ 对象构造、完整生命周期、游戏线程/TLS/lease 或执行器可用；native_ready、native_ABI_ready、lease 均保持 false。

## 唯一脚本行为

配置恰为 `{schema:'REA-OWNED-FFI-SMOKE-CONFIG/1', pid, nonce}`。pid 是 host 新创建 Popen child 的 uint32 PID，nonce 是本次随机 16 字节的 32 位 lowercase hex。额外字段、地址、export、时限或外部 PID 选项均不接受。脚本在解析任何模块、分配或调用之前要求 Process.id 精确相等、Windows/x64/8 字节 pointer。

1. `Process.getModuleByName('kernel32.dll')`，仅解析 `lstrlenA` 与 `GetCurrentProcessId`。
2. 两个 `NativeFunction` 分别固定为 `int(pointer)` 与 `uint32()`，options 都是 `{abi:'win64', scheduling:'exclusive', exceptions:'propagate', traps:'none'}`。
3. `Memory.allocUtf8String('rea')` 获得此脚本自有 NUL 结尾字符串。局部 owning pointer 保留在同步 lstrlenA 调用期间；不从目标既有堆取字符串、不接受地址输入、不调用 readByteArray 或复制 live heap。
4. 只调用 lstrlenA 一次、GetCurrentProcessId 一次；严格要求返回整数 3 与本次 self PID。无替代 ABI/options、无 fallback、无 retry。
5. 只 send 一份 ≤256B ASCII payload，不传二进制、不打印日志、地址、环境或异常消息：

```json
{"schema":"REA-OWNED-FFI-OBSERVATION/1","pid":31415,"platform":"windows","arch":"x64","pointer_size":8,"nonce":"abababababababababababababababab","lstrlenA":3,"GetCurrentProcessId":31415}
```

没有 hook、Interceptor/Stalker、NativeCallback、Thread.runOnThread、异常 handler、code write、game field 读写、游戏 native call 或 world 对象访问。**这不是零内存写入**：Memory.allocUtf8String 会分配并写入自有字符串，Frida 也会注入运行时；不证明 Frida 所有内部分配释放或映像 unmap。脚本不手动调用任何系统 free。

选项含义按 [Frida 官方 JavaScript API](https://frida.re/docs/javascript-api/#nativefunction)：exclusive 在调用时保持 JS 锁，propagate 让原生异常交给目标处理，traps none 禁止相关 instrumentation traps。它们不建立世界锁或游戏线程身份。类型、export 和 Memory 生命周期也由同一官方 API 文档核对；本地是否实际支持必须以后在 owned fixture 验证，离线模型不能替代。出错可能生成 REA error 消息或导致自有 fixture 退出，均拒绝成功，不在 EU4 试错。

## 宿主边界

`launch_smoke.py` 没有默认执行操作；`check` 只验文件 pins。将来的 `run-reviewed` 不接受任意 PID/executable/script/command/duration：

- 固定 Python/Node/REA 位置；source-manifest 检查本目录全部源码、选定项目证据与 external pins。manifest 的 runtime_executed=false 描述源码准备时状态，不替代以后独立运行回执；selected external pins 不宣称 node_modules 完整传递闭包。
- 随机 nonce 和 exclusive 新目录/claim，不覆盖旧回执。只用经过 hash 检查后载入的 r3 `job_tree.py`，SHA `5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011`。controller 验证继承 Job 限制后创建新的 fixture。没有 OpenProcess 或外部 PID 接入。
- target PID 只取该 `Popen`；creation 只经该持有 handle 的 GetProcessTimes。fixture 的 stdout-ready nonce/PID 绑定须成功；held identity/liveness 在 provider cleanup 后复核。脚本配置只传 self PID/nonce，creation 是宿主见证而非脚本自证。
- 渲染固定 config 前缀加完整 smoke.js，保存 rendered script bytes/SHA。REA CLI 固定 `instrument-with-frida attach <own pid> --duration-ms 1500 --script-file <new render> --device-id local --format json --full-output`，一次尝试；1500ms 是 provider post-load delay，不是整个操作硬时限。
- controller 的 CLI 最多25s等待，fixture ready5s；launcher r3 Job45s和既有收尾约束。Job硬内存768MiB、active-process limit8；接受累计 **1..8**、最终active0、exit0、direct child已收、无forced descendants cleanup、peak不超限，exact bool/int 检查。累计成员不猜固定数。
- stdout/stderr采用有界落盘/接受检查；采样式检查允许 writer 在拒绝前短暂超过额度，不能宣称无 overshoot。stderr必须空才接受成功。
- 两层 finally 收齐 controller 的 REA CLI 和 fixture。fixture只接受本nonce经stdin停机；成功必须 graceful exit0、handle closed、未terminate，且 cleanup error=null。任何强制回收仅能作用于本 Popen handle，且不能计作 smoke 成功。

这套 future launcher 是待审源码；本轮只运行下一节的离线入口。它没有自动重试机制，也没有将旧 metadata smoke 的成功搬成 FFI 成功。

## 严格 REA/回执接受

保留旧 reviewed parser 的实际 envelope/profile：UTF-8/ASCII、duplicate keys/nonfinite/float/超界拒绝，CLI meta、完整 Evidence keys、固定 provider/predicate/authority、semantic evidence_id、原始 normalized_result、session UUID、script UUID、准确target文本全部核对。必须来自同一session/local/attach/selfpid，准确source_path及**完整渲染SHA**，恰一条 plain send、无 binary/redaction/truncation 字段，两层 cleanup_error 都为 null。

新 payload 在元数据之外只接受两返回值，字段集合精确，pid/pointer_size/两返回值全部 exact int；3.0、true、字符串不能替代整数。旧 metadata-only schema 或nonce回放不接受。controller 和 launcher 均从 retained raw CLI bytes 重跑同一个纯提取器并比较解析回执，执行后源 graph 再验。metadata、creation 与真实 OS handle 的可信来源仍是 pinned producer；JSON本身不能自证创建过进程。

controller success 名称改为 `owned_fixture_kernel32_ffi_observed`，不叫 native ABI ready。未来最终成功还必须满足 Job/fixture/来源全部清理与复核，两个数字匹配不能单独覆盖这些要求。

## 离线测试与可复现性

新测试仅两个 suite，各5方法：

- `test_smoke.js`：纯 Node VM 提供手写 capability model，验证固定两个 exports/types/options、唯一自有 pointer、调用顺序、两个返回值和唯一小消息；错误 config/metadata 在访问前失败，错误返回和 API/options 不支持不 fallback/retry。它没有真实 NativeFunction/Frida binding。
- `test_contract.py`：新的 FFI envelope/旧 schema拒绝、返回值 exact type/PID/nonce、唯一消息和两层cleanup/renderSHA、semantic hash与重复raw键、Job累计1..8/active0及类型边界。只有 bytes/字典运算，不启动 fixture。

只在新目录首次执行：

```powershell
& '${USERPROFILE}/AppData/Local/Programs/Python/Python312/python.exe' 'work/candidates/rea-frida-owned-ffi-smoke-20261015/prepare_manifest.py'
& '${USERPROFILE}/AppData/Local/Programs/Python/Python312/python.exe' 'work/candidates/rea-frida-owned-ffi-smoke-20261015/verify_offline.py'
```

后续核验使用 `verify_offline.py --check` 和 `launch_smoke.py check`，不重跑测试、不启动任何 fixture/provider。初次 runner 使用 r3 Job 顺序运行新 Python 和 Node 测试，保存 `offline-r1/receipt.json`、两套stdout/stderr pins；旧 Job/metadata/entry/host/18JS/41parser 等测试全不重复。失败回执保留，不覆盖重跑。

`source-reuse.json` 固定原 metadata smoke manifest `076ef47c...` 与复制的五源前像；`source-manifest.json` 固定全部新源，sealed=false、source-only pending root review。本轮无实际 FFI结果可报告。审核若发现源码问题，保留当前前像及测试回执后做窄修/窄测试；本目录的源码准备不自动改变任何旧 gate 或允许下一 body-only raw ABI probe。
