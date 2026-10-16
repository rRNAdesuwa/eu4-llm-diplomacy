# 原生和平/外交权限 hook 窄审计

范围：只读核对 `work/runtime/peace-action-executor-4e7c80-full.txt`、
`work/runtime/peace-dispatch-4e9960.txt`、`work/runtime/peace-response-598f00.txt`、
`work/runtime/peace-action-constructor.txt`、`work/runtime/offer-action-4e64.txt`，并对照
`work/runtime/native-peace-authority-before.json` 的既有日志。
本轮没有改源码、改游戏、注入或发送动作。重点是判断在
`command vtable +0x48 -> RVA 0x4e7c80` 入口跳过执行是否安全，以及当前证据能否支持
按国家和 state 做外交权限隔离。

## 1. 在 generic command executor 入口跳过

`RVA 0x4e7c80` 先保存 `RCX` 为 command，读取 `[command+0x50]` 作为 owned action，
再调用 action vtable `+0x80`，随后调用 action vtable `+0x100` 并按
`action+0x34` 进入后续业务路径。函数正常尾部（`0x1404e8440`）只恢复寄存器和栈并
`ret`，没有建立有意义的返回值；`RAX` 只是最后一次内部调用留下的值。

已确认的直接调用者（例如 `0x14050329b`、`0x140503456`、`0x1405037bd`、
`0x140503a8b`、`0x140506a08`、`0x1406ce4ef`）在构造 command、调用
`0x4e7c80` 后，立即以 `EDX=1` 调 command vtable slot 0 析构，并没有消费 `RAX`。
这表明该执行器本身不负责释放外层 command；在这些调用路径中，入口短路后正常返回不会
因为执行器被跳过而泄漏，前提是仍让原调用者继续完成析构。

transport 队列消费者从 `0x14ca110` 到 `transport vtable +0x30` 的完整消费者到
`0x4e7c80` 的静态边仍未完全建立；因此不能把“所有未来调用者都忽略 RAX”或“所有
队列对象都由同一处析构”说成已证明。不过 `0x4e7c80` 自身没有析构或释放逻辑，当前
没有发现短路会使队列索引死锁的证据。实际 hook 必须返回到调用者的正常析构路径，不能
丢弃 command 指针，也不应伪造依赖 RAX 的结果。

结论：若目标是硬阻止一次已经到达执行器的和平 command，在确认 command vptr 和 action
vptr 后于 `0x4e7c80` 入口返回，是比改 action validity 更干净的拦截点；生命周期风险
目前为“直接调用者已证实、队列消费者仍需运行时确认”，不是零风险证明。

## 2. 把 action validity `+0x80` 改为 false 不是硬拦截

在 `0x1404e7ca1`，执行器调用 action `+0x80`；返回 false 后跳到
`0x1404e83a0`。该旁路仍调用 action `+0x100`，若其返回 true，还会经过国家/对象查找，
并在 `0x1404e8423`/`0x1404e842a` 取参数，再在 `0x1404e8431`、`0x1404e843b`
调 `0x14025a900`、`0x14025a3f0`。
它绕过了正常主路径（主路径从约 `0x1404e8023` 继续），但仍可能产生业务、通知或
清理副作用。因此把和平 action 的 `+0x80` 强制返回 false 不能保证“什么都不发生”，
也不适合作为第一版原生 AI 权限隔离。

## 3. peace action 的字段和 state 分支：目前不足以直接推出决策主体

peace action 构造函数 `0x140598b20` 设置：

```text
action+0x10 / +0x18  = 第一个国家句柄（构造时同一参数）
action+0x20          = 第二个国家句柄
action+0x34          = state，初始为 0
action+0x41          = 构造时传入的布尔标志
vptr                 = 0x141c7b840 (base+0x1c7b840)
```

`RVA 0x598f00` 在 `0x14059951b` 读取 `action+0x34`：

* `state == 0`（`0x140599531`）先用 `action+0x20` 做国家表查找，再用
  `action+0x10` 计算另一组关系/条件（`0x14059954e` 起）。这说明该分支确实区分
  两个句柄，但不是一个显式的“谁有权限”判断。
* `state == 1`（`0x140599658`）在 `0x140599661` 读取 `action+0x18`，并在
  `0x14059966a` 与当前玩家槽 `r15w` 比较；不相等时转到 `0x140599893`。
  这是玩家/拥有者相关检查，不能单凭它把 state 1 命名为“recipient 决定”。
* `state == 2`（`0x140599bb8`）先调用 `0x1404ec190`，再按 `action+0x41` 在
  `action+0x10` 和 `action+0x20` 之间选择顺序：标志为真时先取 `+0x10`、再取
  `+0x20`；标志为假时交换。两个句柄随后作为参数传给 `0x140985060`。该段没有
  直接把 `+0x20` 与当前玩家/拥有者比较的代码。

所以“state 0 由 action+0x10、state 1/2 由 action+0x20 决定”目前只能作为运行时
语义假设，不能直接作为 hook 权限判定。既有 `native-peace-authority-before.json`
确实记录了 FRA→ENG 的 state 0→2，以及 ENG→FRA 的 state 0→2；这与“state 2 是
接收方处理阶段”的假设相容，但日志没有证明执行结果，也没有证明 `+0x20` 是该阶段
唯一的权限来源。尤其 ENG→FRA 的 state 2，静态代码显示还有 `+0x41` 的方向选择；
必须用已确认的 actor/recipient 运行时记录或对照原生 UI 测试验证决策主体。不要把
`state_raw` 当成接受/拒绝含义，也不要在未验证方向前强制读取未知字段。

## 4. `4e9960` 的覆盖范围：通用 action-to-command 包装器，但不能据此读通用字段

`RVA 0x4e9960` 通过输入 action 的 vtable `+0xb0` 复制/克隆 action，然后创建
command vtable `0x141c814b0 (base+0x1c814b0)`，将 owned action 写入
`command+0x50`，并返回 command 容器。其实现没有 peace 类型判断，因此这是通用的
action-to-command 包装器；在 `offer-action-4e64.txt` 中可见多个不同调用上下文，
包括和平相关调用（如 `0x1404e6519`、`0x140502d3f`、`0x140570d2c`）和其他尚未完成
类型归类的调用（如 `0x14051b07a`、`0x14051d750`、`0x14130f1d7` 等）。

这支持“command `+0x48` 是广泛的 command 执行闸门”，但不支持把 peace action 的
`+0x10/+0x20/+0x34` 当成所有外交、军事、经济 action 的统一 ABI。当前只有
action vptr `0x141c7b840` 的字段和方法被核对；未知 action vptr 的偏移语义应视为未知。

因此，单在 generic command 槽按“FRA 字段”拦截全部动作会有误杀军事/经济命令的风险。
第一版应先做双重识别：

```text
command[0] == 0x141c814b0
command->action[0] == 0x141c7b840
```

只有命中已识别的 peace action 才读取 `+0x10/+0x20/+0x34/+0x41` 并执行权限判断；
未知 action 通过。若要隔离“法国全部外交”，还需要枚举其他外交 action vtable，或找到
比 action 类更高层、能可靠区分外交类别的字段/入口；当前证据不足以直接承诺 generic
slot 已经等价于“全部外交”。

## 5. 建议的最小权限策略

第一阶段可在 generic command `+0x48` 入口只对已确认的 peace action 做权限隔离：
记录 command/action vptr、两个国家句柄、state、`+0x41`，以已验证的 actor/recipient
规则决定放行或短路；字段方向或 action 类型不明时放行并记录，避免把未知外交或非外交
动作误杀。短路走正常返回，保留外层调用者的析构。

不要以 action `+0x80=false` 代替入口短路。要扩展到全部外交，先建立外交 action vtable
清单和每类的 actor/recipient 布局，再把同一权限策略逐类加入；在此之前，“generic
wrapper 通用”只能证明它是候选总闸门，不能证明它是安全的全部外交过滤器。

## 6. `peace_lock_v1` 增量复核

复核对象：`work/native/probe.cpp`、`work/native/frame_stub.S` 的当前增量，以及
`work/native/eu4_bridge_peace_lock_v1.dll`。没有修改源码、注入或发送动作。

### 已确认

* 编译条件在 `build.ps1` 中强制 `PeaceAuthorityLock` 必须同时启用
  `TraceCommandExecution`，且不能启用 `EnablePeaceSend`。当前 DLL SHA-256 为
  `230A6A81153D1CE6D2B94113126A87E7AA1421A245437C38465889C9C545105F`，与提交值一致。
* C++ 观察器先确认 command vptr `base+0x1c814b0`，再确认 owned action vptr
  `base+0x1c7b840`，才读取和平字段。非和平 action、未知 command、指针读取失败都
  返回 `1` 透传；没有把未知 action 当和平 action 处理。
* 锁定条件不是低 24 位 tag：它从数据库数组 slot 122 取得对象 `+0x20` 的完整 FRA
  handle，并同时校验高位 slot 为 122、低位 tag 为 FRA。actor 或 recipient 任一完整
  handle 等于该值时，`authority_blocked=1`，无论 state、方向或请求/响应方向均返回
  `0`。
* 决策在 metadata 读取、日志入队和 `64` 槽边界检查之前完成。metadata 读取失败或
  队列溢出返回已经算出的 `forward`，不会把已识别的 FRA action 改成放行；非 FRA/未知
  action 的 `forward` 为 1。观察器本身没有引擎调用、action 写入或文件 I/O。
* 汇编的阻止分支完整恢复 XMM0–5、`RSP`、保存的通用寄存器和 flags，再用 `ret` 弹出
  原始返回地址；透传分支执行同样恢复后 tail-jump 到原方法。按 Win64 入口栈计算，
  `7` 个 8 字节 push 加 `0x88` 分配、对应 add/pop 与原始 `RSP` 平衡，未发现阻止分支
  残留栈字节或返回地址错误。保存的原始 `RAX` 也会恢复，因此不伪造 executor 返回值。

### 边界与一个需保留的运行时 caveat

当前锁是“身份已成功解析时的 fail-closed quarantine”；如果数据库数组、slot 122 或
对象 `+0x20` 的读取失败，`controlled_valid` 为 false，事件会按 `forward=1` 透传。
这避免了未知内存状态下误杀游戏命令，但也意味着它不是在内存读取异常时的 fail-closed
安全锁。运行时应把 `controlled_valid=false` 记录为诊断/安装失败信号并停止宣称锁已覆盖
法国，不能把这种情况当作法国已被隔离。

除此之外，本增量未发现阻塞性 ABI、返回栈、非和平透传或日志溢出放行问题。它仍只覆盖
已确认的和平 action 类；其他外交类别保持未锁定，符合当前窄范围设计。

## 7. generic command 仅按 command vptr 泛化的窄复核

本节只回答是否可以去掉 action-vptr 检查、直接把 `command vptr ==
base+0x1c814b0` 当成所有 `CDiplomaticAction` 的统一布局。结论是不应这样做。

### 支持“存在公共前缀”的证据

`0x4e7c80` 从 `command+0x50` 取 owned action，先通过 action vtable `+0x80` 和
`+0x100`，随后在 `0x1404e7cca` 无条件读取 `action+0x34`。不同 state 分支还会读取
`+0x10`、`+0x18`、`+0x20`、`+0x28`、`+0x30`。因此，能够进入该执行器正常路径的 action
至少被执行器当作具有这一段公共前缀的对象；`+0x34` 很可能是 action 基类中的状态字段。

`0x4e9960` 也确实是通用包装器：它调用输入 action 的 vtable `+0xb0` 复制对象，随后
把复制品放进通用 command 的 `+0x50`。这解释了为什么 command vptr 固定而 owned
action vptr 可以变化。

### 不能把前缀语义泛化为 actor/target 的证据

当前反汇编已经看到至少三类不同的 action vptr：

* peace action `0x141c7b840`，在 `0x1404e64d9`、`0x140570cdf`、`0x14059bae1`
  等位置构造；其 `+0x10/+0x18` 是第一个国家句柄，`+0x20` 是第二个国家句柄。
* `0x141c7f910` 在 `0x14051af02` 附近构造，随后由 `0x14051b07a` 包装；
  `0x141c7f7e0` 在 `0x14051d5b2` 附近构造，随后由 `0x14051d750` 包装。它们也
  复制了 `+0x10/+0x18/+0x20/+0x28/+0x30/+0x34/+0x38/+0x3c` 这一段，但当前材料
  没有证明这些字段的业务语义，也没有证明它们属于外交而非其他 action 类。
* 另有多个 `4e9960` 调用点（例如 `0x14053fd1b`、`0x140543660`、
  `0x1407c584b`、`0x140a605db`、`0x140e69dd3`、`0x14130f1d7`、
  `0x141499c21`）尚未完成 action vptr 归类。

因此，`+0x34` 的“可被 generic executor 读取”与 `+0x10/+0x20` 的“必然是国家
actor/target”是两件事。公共字段形状的证据是正面的，公共字段语义的证据是不足的。
军事或经济 command 是否也经由该 wrapper，在当前窄审计中不能排除；这些调用点中尚未
有足够证据把对应 action 类归为军事/经济，也不能反过来说它们全部不经过该 wrapper。

### 对“只按 command vptr 读取并阻止”的判断

只确认 command vptr 后读取 `action+0x10/+0x20/+0x34`，在对象指针确实有效时通常是
可读的，但会产生两类错误：

1. 对拥有公共前缀但 `+0x10/+0x20` 不是国家句柄的 action，可能误判或无效读取业务
   语义；即使 full FRA handle 的偶然命中概率低，也没有类型安全证明。
2. 对外交 action 的其他类，若其国家字段位置不同，会漏掉法国外交，达不到“所有外交
   禁用”的目标。

所以不能在仅 `command vptr == 0x141c814b0` 的前提下声称已经识别全部
`CDiplomaticAction`。当前最安全的策略仍是先确认 owned action vptr，再读取该类已验证
的字段。若要扩大范围，应先收集 action vptr 清单并逐类验证 `+0x10/+0x20` 的句柄身份；
未知类透传并记录，不能用猜测的公共布局替代类型判定。

