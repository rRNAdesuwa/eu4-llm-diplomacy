# 1.37.5 受限研究测试控制

`work/native/test-controls-1375.h/.cpp` 只提供整数速度控制 `set_speed(0..5, Host)` 和只读 `observe`。它没有 hook、DllMain、邮箱、claim 创建、存档调用、任意控制台字符串或脚本执行入口。本阶段只编译到 TEMP 中的独立 object，未链接或调用游戏函数；原生行为仍须由研究宿主逐项观察。

可复现静态生成器为 `work/trace_test_controls.py`，报告 `work/reports/native-test-controls-1375.json` SHA256 为 `9161f51016cb21eeca70889fb939c106ed35cfa101c782011233d012a1e6e022`。二进制固定为 SHA256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。报告包含 19 个指定入口、7 组事实、12,873 字节代码（含重叠），四个控制台注册记录均校验了函数指针及命令名称。全部 `runtime_verified=false`。

```powershell
python work/trace_test_controls.py --deps-dir "$env:TEMP\eu4-native-analysis-deps"
```

## gamespeed 的确切约定

注册槽 `1fce998` 指向 `e913a0`，签名按机器约定写为：

```cpp
NativeResult40* callback(NativeResult40* out, const Vector24<String32>* args);
```

RCX 为输出对象，RDX 为只读参数 vector，返回 RAX 为同一输出地址。输出 `+0` 是 success BYTE，`+8` 是拥有存储的 String32。String32 前 16 字节为 SSO/指针 union，`+0x10` QWORD length，`+0x18` QWORD capacity。参数 count 是 `(end-begin)/32`，必须正好为 1。新模块只构造长度 1、capacity 15、NUL 结尾的 ASCII 数字 `0` 至 `5`，不接收其他字符串。

正常返回后，模块确认返回地址、bool 和有界 String32，再调用 `95660(&out.message)` 释放原生输出字符串。输入参数完全使用栈上 SSO 存储，不申请引擎堆内存。发生异常后不对可能部分构造的字符串运行析构，也不再调用任何引擎函数或自动重试。

## 数值与暂停不同

callback 接受 `0..5`，但 `7579f0` 把它截取为内部索引 `0..4`，写 game `+0x1e08`。显示值是该索引加 1，因此 4 和 5 都是最大档，输入 1 对应内部 1，不能宣传成 UI 的第 1 档。

| 请求整数 | 期望内部 index | 期望暂停 |
|---:|---:|---|
| 0 | 0 | 是 |
| 1 | 1 | 否 |
| 2 | 2 | 否 |
| 3 | 3 | 否 |
| 4 | 4 | 否 |
| 5 | 4 | 否 |

callback 用 `7e01b0` 判断暂停状态，再按需要调用 `7e0250` 切换，不能只通过速度 index 判定暂停。server 虚槽 `+0x100=8024d0` 返回 server `+0x418` pause manager。暂停谓词为：

```text
manager+0x48 手动暂停 BYTE 非零 → paused=true
否则 native multiplayer classifier 6eaa10(manager+0x50 server) 为 true → paused=false
否则 manager 向量 begin(+0) != end(+8) → paused=true
否则 paused=false
```

`observe` 只读复现上述公式，并核对固定模块前缀、server vtable/虚槽、manager 的 server 关联、指针及有界玩家链。它不调用 pause predicate。`native_multiplayer_classifier=false` 仍不构成严格离线身份的独立证明，详见 world lifecycle 报告。

## 与研究宿主的边界

宿主在进入 `set_speed` 前创建并 Flush 唯一 attempt claim，通过 Host 声明已验证完整 exe SHA、游戏线程及该已领取测试请求。模块检查 game/server/pause manager/player/date 身份，调用 Host guard，持久化 `test_speed_begin`，重新读取身份和 guard 后才进入 callback。Host callbacks 必须不抛异常、不调用引擎、不重入、不加载/推进世界；logger 返回 true 必须代表完整日志已经持久化。

回调正常返回、输出字符串析构后，模块再次只读获取实际 index/paused，确认同一线程内对象身份和日期不变，再调用 after guard，最终记录 `test_speed_complete`。这只观察该同步调用的结果，不宣称日历推进、冷却完成或任何外交效果。跨帧等待一个月应由宿主观察 rawdate 并发送单独的 speed=0 请求，不能在游戏线程里阻塞 sleep。

`Result.write_entered` 在进入 callback 前置位。一旦进入后出现非正常结果、异常、审计失败或读回不符，模块冻结后续控制，并令 `retry_allowed=false`；宿主应冻结该研究会话，不在不明状态下自动重试。保存、恢复、重启策略由受限研究宿主处理，模块不访问文件。

`observe` 还返回 game `+0x7485` 的 `world_reset_active` 和 game `+0x74c8!=nullptr` 的 `load_source_present`。它们可在活跃时拒绝请求，但不是 generation，也不能保证逐帧采样会捕获所有读档。正式 backend 的完整世界世代条件没有因本模块而解决。

## savegame 仍未实现

注册槽 `1fc74b8` 指向 `e7b3e0`，该 callback 不读取参数 vector，因此传入文件名不会形成受控的命名保存。它构造大小 `0x78`、token `0x2df4`、vtable `0x1cba3b8` 的 `savegamecommand`，通过 context transport 提交。甚至 transport 路径因条件跳过后，callback 仍在 `e7b556` 写 success=true；该结果不能证明存档文件已产生。

command `+0x50` 的嵌套对象 vtable 为 `0x1cb1f50`。其 serializer `1558480` 写入的是 `hard_check`、`local_check`、`randomlog`、`hotjoinlog`、`randomlog_stack`、`randomlog_frames`，应视为校验/日志设置对象，不能当成可写文件名的 SaveInfo。

execute `847e30` 整理游戏/校验状态，并生成 `ready_after_hotjoin` token `0x2dd1`。本轮有界链尚未确认最终文件 writer、路径和命名模板、同名碰撞处理或不覆盖保证。因此新模块没有实现任何保存调用；不能以“默认保存大概安全”作为自动化验收依据。

`run` 与 `date` 的注册回调只保留在静态报告中，不通过新模块暴露。推进测试冷却使用真实速度及暂停控制，不开放任意脚本/日期字符串。
