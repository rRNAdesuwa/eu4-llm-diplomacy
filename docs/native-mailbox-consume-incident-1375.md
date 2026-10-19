# v10 序列 13 消费失败与 v11 候选

事故对应 PID `46408`、creation `01dd568ed7034bcb`。本次只读取保存的文件，未访问游戏进程，未重发请求，未改变 v10 源码、DLL、manifest、claim 或原运行记录。

## 已证与未知

保存的 `00000000000000000013.request` 长 144 字节，SHA256 为 `3bc64afefcd9576c17d9eb55103bf2a2be6d843465c7b67c86ac847fc00905f0`，与 host-intent 的内容/哈希和 publisher 输出完全一致。请求为 speed5、sequence13、PID/creation 正确。最后 healthy frame 的 last_sequence 为 12。

原 v10 `lab-request-1375.h` 在 MSVC `/W4 /WX` 独立 speed-only harness 中接受了原始文件，完整身份字段匹配；Python 解析也通过。harness 中 pair 解析分支是明确拒绝的 stub，实际未进入，未链接任何游戏调用。复现命令：

```powershell
work/candidates/mailbox-consume-review-1375/parser_probe.cmd
python work/review_mailbox_consume_1375.py --sharing-fixture
```

保存的日志只有合并错误 `request_invalid_expired_or_already_claimed`，没有具体阶段、Win32 error 或失败时 uptime。末帧 uptime 为 `396299562`，请求 expires 为 `396305218`；5000ms TTL 对应请求构造时 `396300218`。保存的发布时间/冻结时间间隔也短，支持“正常情况下应尚未过期”，但**不能精确重建原生比较时刻**。不把磁盘时间当作 GetTickCount64 的严格替代。

未找到 seq13 claim，未找到 `lab_request_claimed`，request 仍保留。按冻结 v10 实现，成功 CREATE_NEW 之后即使写入或 flush 失败也会保留 claim，后续 disposition/close 失败也不删除 claim。因此在“没有外部删除记录”的运行合同内，故障更接近打开/读取/验证/创建 claim 之前；原日志不能在这些分支中定位。

## 合理原因范围

| 原因 | 当前证据 |
| --- | --- |
| `CreateFileW(GENERIC_READ\|DELETE, share=0)` 遇共享冲突 | 可复现但未证明就是事故原因。现有读句柄即使允许 share7，consumer 的 share0 仍与读访问不相容，返回 32；读者关闭后同一文件立即可开 |
| rename 可见性与临时句柄/杀软/索引短暂竞争 | 可行解释，没有保存的 handle/error 证据，不能指认具体进程 |
| 原生 parse / identity 错误 | 保存字节用同一原解析器通过；未观察到事故时内存变量，不能逻辑上排除内存损坏 |
| TTL 过期或过远 | 保存时序不支持正常过期，Python/C++ 都使用 GetTickCount64 且 Python 返回宽度为64位；原生失败时刻未记录 |
| 文件权限、删除权限、链接/类型/长度、ReadFile、claim CREATE_NEW 错误 | 均被旧实现折叠成同一句；保存时普通文件形状不能证明失败瞬间状态 |
| claim 写入/flush 或 disposition/close 错误 | 按旧实现通常应保留 claim；当前未见 claim，支持度低，仍以完整事件证据为准 |

publisher 在 rename 前已经 flush/fsync/close temp，MoveFileEx 无 replace 且 WRITE_THROUGH，返回后不再打开 final。supervisor 读取日志与已经声明的 claim，不读取 pending request。**没有在当前源码中发现可以确定归责的主动读取 final 的自身竞争。**原子发布也不承诺其他时刻所有句柄都与 share0 相容。

## v11 mailbox 基础候选

`work/candidates/v11-mailbox-review/prepare_build.py` 从固定哈希的 v10 14 源生成独立 v11 14 源、recorder 和相同 fixture_v3 五文件。当前仍 24 个研究 ID，未合并后续 8 family。任何 v10 输入哈希变化都会拒绝生成；已有 v11 会话时拒绝重写；已有 DLL 时拒绝改变原生源。生成后的 mailbox diff 位于同目录 `native-mailbox.diff`。

只有**尚未取得 request handle、也尚未创建 claim**的 `ERROR_SHARING_VIOLATION=32` 会跨帧返回 `deferred`。上限为 250ms 或 16 次 open，以先到者为准；没有 Sleep，也不在同一 callback 里重试。原请求 TTL 不延长。得到 handle 后仍独占解析、CREATE_NEW claim、写入/flush、同句柄 disposition 删除。等待后文件消失、其他打开错误、解析/身份/TTL错误和任意 claim 后失败都冻结，保留单次尝试合同。phase markers 使用独立同类等待状态，不会因 marker 的短暂文件锁立即冻结。

日志每次等待最多一次 begin 和一次 end；任何终止错误另有一条 failure。无逐帧洪泛、无原始请求正文、无任意路径写入。两类诊断事件：

* `lab_input_wait`：`wait_state=begin|end`、`input_kind=lifecycle|preview|command|request`、`input_sequence`（phase为0，request为当前last+1）、PID/creation、已claim的 `sequence`、`outcome`、初始 `win32_error=32`、`uptime_ms/attempts/elapsed_ms`、固定上限、`claim_created=false/native_invoked=false/retry_allowed=false`。
* `lab_input_failed`：同身份与 kind/sequence，另有 `stage/win32_error/close_win32_error/uptime_ms/expires/bytes/attempts/claim_created/claim_flushed/request_deleted`，`native_invoked=false/retry_allowed=false`。Win32 API 失败立即保存 GetLastError；逻辑谓词失败的 error 为0，不输出陈旧错误值。

这些事件不是执行 ACK。phase 等待可能发生在三阶段尚未完成时；未来 Python verifier 应先处理诊断状态，再执行原 `lab_*` 的阶段证明规则。等待 begin 应阻止外部新请求发布，end 并不证明消费；只有后续正常 claim 与完整原生证据链才证明进入了相应阶段。failure 应终止会话有效性，并允许随后保存的 freeze 信息补充诊断。

真实文件 fixture 命令：

```powershell
work/candidates/v11-mailbox-review/test_consume.cmd
python work/candidates/v11-mailbox-review/prepare_build.py --check
```

首轮 53 个 checks 通过，直接包含生成器的同一 `consume-input.inc`，验证真实 Windows 文件锁、释放后消费、时间/次数上限、等待中 TTL 过期、文件消失、已有/partial claim 不覆盖、硬链接拒绝、非共享打开错误、日志失败不进入 claim。时间使用可控测试 clock；没有调用游戏、加载研究 DLL 或写入真实邮箱。原 DLL 构建需在候选源码独立审查后由父任务决定，不能把单元测试当运行验证。
