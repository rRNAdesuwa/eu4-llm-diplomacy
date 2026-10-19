# 当前方向性停战缓存读取 CLI（候选）

本工具只读 actor→target 的 relation record `+0x45 & 1`。这是原生消费者使用的直接缓存标志；不执行完整 `506d70`/关联国家路径，不证明 typed truce 对象、期限、removed、原请求效果或和平完成。反向需要另一份当前方向样本；两方向不自动等价。

目标固定 EU4 1.37.5，EXE SHA `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。目录内 `source-manifest.json` 尚未封存时全部命令拒绝；源审完成后由 root pin/封存，再另行允许实际读取。本轮只准备源码及纯离线测试，没有运行真实 `status`。

```text
python work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py catalog
python work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py check
python work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py status --pid PID --creation FILETIME16HEX --actor FRA --target AUV
```

`catalog/check` 只读文件。`status` 必须显式给出真实 PID、非零 16 位小写十六进制 creation 和两个不同的三字符大写 TAG；不使用历史 PID/creation/Q/heap 作为当前身份。不接受请求 ID、installed session、任意地址/模块/脚本、动作、watch 或服务端参数。

退出 0 对 `catalog/check` 表示文件校验成功；对 `status` 表示当前布尔缓存状态已取得，**false 同样退出 0**。退出 2 表示 unknown/参数不合法。JSON 的 `direct_pair_cache_flag_set` 为 true/false/null，`selected_effect_verified`、`peace_completion_verified`、`request_effect_verified` 与 `native_ready` 始终 false，`requests_published` 始终 0。退出码不是外交成功信号。

精确编译 R24 源 `1677ccf7…` 为独立 library，复用 `AlignedPort`、`owned_country`（经 `pair_sample`）、`pair_sample` 和 `check_country_table_binding`，不运行其 `main`，不改 `PAIRS/OUT`。R23 静态来源图经固定 manifest 展开核验。旧 host `b3982356…` / manifest `e7673b0e…` 只复用来源验证、`load_local` 及 `host_sample`；215 个本地/11 个选定外部 pin 委托原 verifier，原 80340 capture 授权没有迁移。不会执行其 capture、registered argv、REA、Frida 或 Job helper。

仅 `status` 加载 observer/创建 `RuntimeCapture`。该复用层持有输入 PID/creation，验证精确游戏路径、磁盘 SHA、载入 PE 与模块集合，只申请 QUERY/VM_READ/SYNCHRONIZE。新 CLI 拒绝研究模块；要求 manual_pause=1 和稳定 world roots，并沿 R24 完整 handle/typed country/owner relation/positive array slot 两遍读取，核初始 table 中地址与采样地址一致，拒绝同 handle 从 table A 偷换为 B。完整 0x48 raw record 保留为证据，但没有把其中 `+0x30` 等字段解释为停战日期。

成功仅在正常退出 `with`、held handle 字段已清空、最终 source guard 通过之后提交。旧 `Held.close` 不检查 Windows `CloseHandle` 返回值，本工具因此显式保留 `close_os_return_checked=false`，不冒称 OS 级关闭返回已验证。其他 cleanup/source/read 错误返回 unknown，部分 raw 样本仅为诊断。两遍相等不是原子世界快照，不能排除瞬时写、ABA，也不授予对象 lifetime lease。

选定读取预算沿用 4096 次/512KiB、单读≤65536B；两次 host sample 的独立预算另列。来源前后校验是完整性比较，不是文件锁。fresh nonce 只关联这份只读结果，绝不伪装原 TAG/request session。工具无写进程、注入、native helper、构造、保存、重载或派发入口；旧 stable 15/98pin、43 端点索引、DLL/120 动作限制保持。

首次新离线测试只覆盖 CLI 接入：参数、positive slot 映射、真实 R24 table binding 的采用、import 前 source/未封拒绝、真假状态/退出码、source 前后变化、正常 context 退出后提交、文件命令不加载 observer。使用自有 Python 字节与 fake process adapter，不重跑旧 R24 八个 guard 或其他历史套件，也不访问 EXE/游戏。
