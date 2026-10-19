# 原生和平命令队列入口审计

范围：只读核对 `work/runtime/peace-send-callback.txt`、`peace-dispatch-14ca110.txt`、`peace-dispatch-1580270.txt`，并从当前 `eu4.exe` 静态 `.rdata` 核对命令/和平 action 虚表。没有注入、发送或改代码。

## 已确认的调用链

原生发送回调 `RVA 0x130f080` 在 `0x130f1d7` 调 `RVA 0x4e9960` 包装 action，返回 `&command` 容器；随后在 `0x130f1e2` 调 `RVA 0x14ca110`，参数为 `RCX=dispatcher`、`RDX=&command`。因此原生 UI callback 不直接调用 transport 的虚表方法。

`0x14ca110` 的成功路径为：

1. 取出 `*command` 并在 `0x1414ca12d` 立即把容器清零。
2. 若 dispatcher 的 `+0x58` 为空或 command 为空，返回假。
3. 当 `dispatcher+0x55==0` 且 `dispatcher+0x80d==0` 时，先调用 command vtable `+0x80`；若假再调用 command vtable `+0x58`，两者都假则在 `0x1414ca170` 返回假，不进入 transport。
4. 通过门槛后，在 `0x1414ca18f` 取 `transport=[dispatcher+0x58]`，于 `0x1414ca196` 调用 `transport` vtable `+0x30`，并在 `0x1414ca19c` 将返回值置为 1。

所以 `submitted=true` 的确切含义是 `0x14ca110` 走到了 transport `+0x30` 分支；它不是 `4e7c80` 已执行、也不是和平已接受的证据。静态命令 vtable 中 `+0x58` 与 `+0x80` 都指向 `RVA 0x8f450`（`xor al,al; ret`），因此在这份静态镜像下，若两个 dispatcher 标志都为零，命令会在 transport 前被拒绝；观测到 `submitted=true` 说明运行时应命中了标志旁路，或相关槽/对象发生了运行时替换。下一版诊断应记录 `dispatcher+0x55`、`dispatcher+0x80d`、command vtable `+0x58/+0x80` 和 transport `+0x30` 目标。

## `transport+0x30` 的行为

已确认 `transport` vtable `+0x30` 的目标为 `RVA 0x1580270`。该函数接收 `RCX=transport`、`RDX=command`，修改 command 的调度字段（可见 `command+0x38`、`+0x48` 等），随后在 `0x141580915` 使用原子计数选择环形槽位，并在 `0x141580933` 调 `RVA 0x1580ef0`。`0x1580ef0` 具有槽位容量/生产者消费者索引、等待与位图更新，并把临时记录写入环形结构；这足以确认 `+0x30` 不是单纯的返回值检查，而是进入了传输队列写入流程。

当前证据不能把 `0x1580270` 的入队记录与之后某次 `0x4e7c80` 调用建立完整静态边关系。因此“已排入 transport 环”已确认，“已由游戏命令执行器消费”仍未知；七天后没有 response 与 FRA last 更新，正好说明不能把 `submitted=true` 当作实际执行。

## 通用命令执行器的虚表槽

静态 `.rdata`：

```text
command vtable 0x141c814b0 = base+0x1c814b0
  +0x48 -> 0x1404e7c80 = base+0x4e7c80
  +0x58 -> 0x14008f450
  +0x80 -> 0x14008f450

peace action vtable 0x141c7b840 = base+0x1c7b840
  +0x48 -> 0x140598f00 = base+0x598f00
  +0x80 -> 0x14059b480 = base+0x59b480
  +0x120 -> 0x14059bf10 = base+0x59bf10
```

因此下一版若要记录真正的 generic command executor，应在命令对象的 vtable `+0x48`（目标 `RVA 0x4e7c80`）观察；当前 response trace 钩的是和平 action 的 `+0x48`（`RVA 0x598f00`），两者不是同一入口。

## `+0x208` 与非玩家 actor

原生回调在包装前调用 action vtable `+0x120` 并据返回值设置 `action+0x208`，但本次核对的 `0x14ca110` 和 `0x1580270` 没有直接读取 action+0x208，也没有按该字段选择另一条 transport 入口。非玩家 actor 只影响原生回调前面的日期保护：`0x130f17b` 比较 actor 与当前玩家句柄；actor 非玩家时跳过玩家专用的 global-last-date 分支，之后仍执行同一 `4e9960 -> 14ca110 -> transport+30` 链。没有发现 AI actor 或 `+0x208=1` 自动改用另一队列。

## 结论与下一步记录项

本轮确认：`submitted=true` = `14ca110` 已调用 transport `+0x30`，且该 transport 具有环形队列写入行为；不能据此证明 generic executor 已消费。`4e7c80` 的实际槽是 **command vtable `+0x48`**，不是当前 action response hook 的 `+0x48`。

下一版只读诊断应优先记录：command vtable、command `+0x48` 目标、dispatcher `+0x55/+0x80d`、command gate `+0x58/+0x80`、transport vtable `+0x30` 目标，以及对 `RVA 0x4e7c80` 的实际入口计数。尚未确认 transport 环的消费线程和其调用 `+0x48` 的具体函数，标记为未知。

## execution_v1 增量复核（2026-10-04）

范围仅限 `BRIDGE_TRACE_COMMAND_EXECUTION` 这次增量；未修改源码、未注入或发送动作。

### 已确认

- `work/native/eu4_bridge_execution_v1.dll` 的 SHA-256 为 `92A44ABBF4EA0F6B95050377CA25D610EE793ADD45C846F33E7D222BA23FBB05`，与提交的构建值一致。`build.ps1` 强制要求 `TraceCommandExecution` 同时启用 `TracePeaceResponses`；`start-probe.ps1 -AIExecutionTrace` 选择该 DLL 并执行同一哈希检查。
- 新构建仍只安装一个观察槽：`base+0x1c814b0+0x48`，并在安装前确认原指针为 `base+0x4e7c80`。尾跳仍使用既有 `bridge_response_stub`/`bridge_response_original`，没有第二个 hook 或汇编增量。`frame_stub.S` 当前内容未出现差异。
- observer 先确认 `command[0] == base+0x1c814b0`，再读取 `command+0x50` 作为 owned action；随后确认 action 虚表为 `base+0x1c7b840`，再做 FRA/ENG 过滤并读取既有字段。`work/runtime/peace-action-executor-4e7c80-full.txt` 的原生入口也明确执行 `rsi=rcx`、`[rcx+0x50]`，随后调用该 action 的虚表 `+0x80`，因此这次 ownership 偏移与目标入口相符。
- 事件仍写入既有 64 槽 bounded queue，observer 只读内存、填充记录并发布 `ready`，不调用引擎、不写 action、不改变 command；帧线程只将事件名改为 `native_peace_command_execute_entry`。安装失败和保护恢复失败沿用同一回滚分支。

### 结论与边界

本增量未发现阻塞性 ABI、生命周期、槽位选择或回滚问题。它观测的是 generic command 的 `4e7c80` 方法入口，因而能证明该 command 对象进入执行器；它不能单独证明某条 transport 环已被消费，也不能把 `state_raw` 解释为接受或拒绝。由于 `4e7c80` 是通用执行器，其他 command 也可能到达该入口，但 action 虚表和 FRA/ENG 过滤会把无关对象丢弃。该结论是静态/构建复核，尚未替代运行时日志验证。
