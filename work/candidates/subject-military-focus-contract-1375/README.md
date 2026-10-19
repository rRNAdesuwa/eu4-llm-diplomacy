# 属国军役六枚举：1.37.5 静态合同候选

这次补齐 `subject.set_military_focus` 的独立命令布局、默认构造、正常 clone/析构、序列化与 GUI 条件来源。没有访问游戏进程，没有编译、注入或开放接口；所有运行、效果与生产标志仍为 false。`contract_model.py` 只用 Python 字节数组和人工 snapshot 做合同反例，**不生成原始内存证据，不认可调用者传入的 bool 为真实游戏证明，也不授权任何原生调用**。

## 可确认的命令合同

命令名为 `set_subject_military_focus`，token `0x3017`，vtable `0x1c54678`。这是 **0x60 独立 command**，不是普通 pair action，也不是已有 0xa0 singleton subject interaction。载荷为 `+0x50` 属国完整句柄和 `+0x58` DWORD 枚举：

| 值 | 名称 |
|---|---|
| 0 | no_focus |
| 1 | aggressive |
| 2 | supportive |
| 3 | passive |
| 4 | defensive |
| 5 | siege |

0 是独立状态，不是 false/cancel。没有金额、日期、外交官或 actor 句柄载荷。不要把 rawdate 写入 `+0x2c`（它在内嵌 String32 中），也不要把 actor 国家句柄写到 `+0x38`：后者序列化名是 `sender`，由 context `+0x8c` 填 DWORD。`+0x48` WORD 序列化名是 `tickstamp`，由 `min(context+0x68,0x7fff)` 填；`+0x4a` 是 `istargetasynchronous`，`+0x4c` 是 `identity`，本地传输使用计数器填充。未借名称推断 context+68 的完整时间单位。

`0x2b2850` 在新分配对象上初始化 vtable、type=0x165、String32 空 SSO、sender=-1、token、tickstamp=0xffff、无效句柄 `0x2d2d2d` 和 focus=0。它没有初始化全部 padding。注册入口 `0x249120` 的精确块 `0x24a84d..0x24a86b` 分配 0x60、调用此构造，再以 `0x14c6930` 按 token 放进全局原型数组 `0x23587b0..0x23587b8`。原型是借用对象，不可修改或析构。

虚槽 `+0x60` → `0x2b2a70`：RCX 为源对象，RDX 是**会由 callee 正常销毁的临时 EngineString32**；返回新拥有的 0x60 对象。`0x14c6500` 从 parser `+0x648` 复制字符串再传给该槽，闭合第二参数来源。不能照搬 pair action 的无第二参数 clone。clone 复制 `38/40/44/48/4a/4b/4c/50/58`，重建空 String32，清 `+0x3c`，不拷贝全部 0x60 字节。未来最小生命周期实验可用独立新建的 empty SSO 临时字符串；这是静态提案，尚未运行。

虚槽 `+0` → `0x98940`：RCX 为对象，EDX bit0 控制释放；先 `0x95660(this+0x18)`，再 bit0 分支 `0x17394f0(this,0x60)`。属国句柄是值，不拥有 country。这里只证明正常指令路径，未证明 allocator/clone/string cleanup 的异常展开能安全恢复。遇异常须停止后续调用，不猜测还应析构哪些对象。

serializer `0x2b2900` 调 base `0x14c6290` 后写 `subject_country(0x3018)`、`subject_focus(0x3019)`；parser `0x2b29b0` 对称写 +50/+58，未知 token 交 base `0x14c63c0`。parser 遇缺失 CountryDatabase 会分配并发布全局，base parser 也可能分配字符串。因此它们不是只读查询，更不是简单填字段的安全捷径。

## 宗主权限与可用枚举需要分别证明

命令 gate `0x2b2b30`（virtual+40）只检查目标 `DWORD+0x1344 !=0 || BYTE+0x26==7`，以及 unsigned focus<=5。它直接用句柄 slot 索引 DB array，没有完整句柄复核、数组界限或 null 检查，**默认构造的无效句柄不能拿去调用 gate**。这也没有证明 actor 是宗主或有权改变军役。

GUI 批量路径 `0xf4f9e0` 从有效玩家选择器得到国家，遍历其 `+0x1a18..+0x1a20` 的完整属国句柄，沿目标 `+0x18f0` 宗主和 relation dependency 索引取 definition，检查 `definition+0x14f`。定义解析 switch 已独立核两层表：

* `uses_military_focus(0x35c3)` → `0xb1fca1` → BYTE `definition+0x14f`。
* `can_set_mil_focus(0x3695)` → `0xb2036b` → BYTE `definition+0x15a`。

两字段不同。`0xf576f0` 使用 `0x3d79f0(subject)` 获得 dependency definition 并看 +14f；行构造 `0xf5d880` 另看 +15a。`0x3d79f0` 是沿索引寻找 definition 的 helper，**不是宗主授权函数**。现有范围没有找到一条能单独代替完整授权的原生布尔检查。候选只能明确列出应先核的完整玩家/属国/overlord/索引/definition 条件，不能用 gate=true 冒充权限成立。

GUI 还调用 `0x975360(enum)` 和 `0x9753f0()`。前者0无条件可用，1/2首先看全局 `0x233ff94`，3/4/5首先看 `0x233ff20`，共同检查 `0x233fed6`；其余分支读 GS TLS vector 的 slot0，再看 +0xc/+0x10，必要时调用 `0x1a334c0`。第二函数用同一分支计算六枚举可用数。报告保存完整跳表和分支，不把全局字节命名为某个已验证 DLC，也不把 TLS 查询称无副作用。TLS 实例身份/懒初始化边界未闭合时，RO 输出 entitlement=unsupported，不能因暂停或两次相同就授权调用。

最小研究政策可限制 actor=当前 FRA、target=当前 NAV，但必须重新证明 NAV 仍是 FRA 的属国；历史批次可能已释放。要求 both flags=1 是保守测试限制，不宣称这就是所有原生 UI/网络授权条件；不要扩大到任意 subject 类型或换玩家。

## 命令传递与观测边界

UI 直接把拥有的 command 交给 context `+0x58` transport virtual+30；不经过 `0x4e9930` action wrapper。可研究的现有容器入口 `0x14ca210(context,command**)` **先清空调用方容器，再检查 transport 和 flags**。context55/80d不允许时，本类+80/+58都是false。失败也不会恢复原指针，因此进入函数后，无论返回true/false/异常，调用方都不能自行析构或重试。

本地 type2 transport `0x1580370` 将原件序列化，经 `0x14c6500` 重建命令，再调用 parser virtual+18，最后经 `0x1580ff0` 把重建指针放入队列。不是所有端到端对象都保持相同地址。原生队列最终消费点、gate/execute 的实际线程和拒绝结果本轮未闭合；仅这部分静态传递证据不允许发送。

execute `0x2b28c0` 直接写目标 `DWORD+0x2864`。最小只读验证点是完整 actor/target/current player、target.overlord、actor subject vector、双方 dependency/type identity、两个定义字节及目标 focus。未来生产者应有 held PID/creation/exact EXE/module 身份、DB array/count 界限、完整 handle generation、最多256属国、至多4096定义/索引项（额外限制，不是游戏上限）、有界 String32 名称、两遍同世界/日期/对象关系。定义 vtable `0x1ce7488` 与 parser+20已从构造块核对；定义名在+10，但完整 registry/name 生产者在此仅列设计，不实现或调用 getter。

两遍一致只证明采样一致，不证明引擎生命周期同步、SP 来源、TLS 身份。初末 focus 相同也不证明六次修改都应用；若将来逐项测试，需要每条命令独立绑定只读结果、日期和唯一拥有状态，另做保存重载。这里所有 `effect_verified`、`native_call_authorized`、`production_supported` 均 false。

## 复现、预算与下一步

```powershell
python -B work/candidates/subject-military-focus-contract-1375/trace.py --check
python -B -m unittest discover -s work/candidates/subject-military-focus-contract-1375 -p 'test_*.py' -v
python -B work/candidates/subject-military-focus-contract-1375/prepare.py --check
```

`report.json` 保存确切 EXE SHA、输入文件 SHA、全部指令字节、21个 command 虚槽、定义 parser 表项和 enum 表项。新增正式解码约10.5KiB，每 CFG window 8KiB，总预算64KiB；加探索的唯一字节保守上界44KiB，未做全程序反汇编。探索 raw-pattern/misaligned输出和不相关函数保留为草稿，不能当可调用入口；正式 facts 只引用已钉扎函数/明确表项的指令。模型测试不是 ABI 测试。

下一步应先实现受限原始只读生产者，独立审核 registry 与 subject graph，再单独审无发送生命周期模块。此候选不生成 DLL、不修改冻结 v17/host/catalog/HANDOFF，不开放六项实际执行。
