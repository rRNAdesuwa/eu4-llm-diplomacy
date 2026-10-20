# 1.37.5 世界身份撤销边界增量

`5cf740` 不是统一世界清理入口。它只闭合读档解析 helper；重置、game 析构与 base game 析构有其他路径。本轮将游戏和国家数据库的销毁/重建链静态对应起来，给出有限路径集合上的 4 个入口候选。仍未证明所有界面/联网/异常路径覆盖，也没有安装或实测 epoch hook。

EXE SHA-256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`；机器报告 SHA-256 `d4ee6ad5c8a3577dff2209ec5884978862552c700338e07ef669bd866a30de05`。全部 runtime_verified/execution_verified/production_ready=false。只读磁盘，不访问游戏进程、不修改冻结源、DLL 或目录。

复现：`python -B work/trace_world_epoch.py --check`。每函数 16 KiB / 4,000 条指令，最多 64 函数，总解码 192 KiB，768 MiB 内存保护；不递归追所有调用。

## 证据改变了什么

1. `5cf740` 的唯一已验证直接调用来自 `5cdc60`；共享清理 `74a260` 还有 `749020` 和 `74bf70` 两个直接调用者。只在 `5cf740` 撤销会话会漏这些路径。
2. 外层 `5d0580 → 826c20 → 210000` 明确使用 ResetGamestate / ResetGame 字符串。`210000` 在随后读档前已通过 game 虚析构销毁旧对象、把全局 `233fe78` 清零、重新构造 game 与国家数据库。因此只在 `74b8a0` 撤销也可能晚于旧世界销毁。
3. runtime game 虚表 `1cb00c8` 的槽 0 是 `74bf70`。该析构在 `74a260` 之前就清 context+830/+838，随后进入 `74dd50`。base 虚表 `1cb0020` 的槽 0 是 `74d890`，直接进入 `74dd50`，绕过 `74a260`。
4. `74dd50 → 286250` 确实析构连续国家存储（每项 0x9b78），释放 database+108 和 lookup+118，清空指针/计数，释放数据库并清零全局 `233d8d0`。`2830a0` 随后分配国家块、构造国家和重新填充 lookup。
5. `74a260` 还会在原有国家地址上调用 `2e1a30`；其日志字符串是 `CCountry::Clear()`。该函数清外交关系存储、外交官 holder 状态及宗主句柄。指针、TAG、日期相同不能证明世界未变。

## 有限已审查路径上的入口集合

| 候选入口 | 必须先撤销的原因 |
| --- | --- |
| `0x74b8a0` | direct in-place load before game+74c8/server rebind and any5cf740 cleanup |
| `0x749020` | reinitialize before game+1e00 server unbinding and common reset |
| `0x74bf70` | derived game destructor before context+830/+838 clear, common reset and base destruction |
| `0x74dd50` | base cleanup backstop including74d890 path that bypasses common reset |

这 4 个点是针对本报告明确路径族的较小入口截断集合，不是全程序最小性或通用覆盖证明。`210000` 可另作更早外层重置观察；`74a260`、`286250` 可作异常来源的观察后备。重复进入只需再次撤销，不能在退出时恢复旧授权。

`749020` 在 common clear 前已经写 game+1e00=null；`5cf740` 在 common clear 前已清其他 game 子对象。故把所有状态变化统一延后到 `74a260` 也不成立。前缀字节只用于构建钉扎，尚未审查 trampoline、指令搬迁、重入、线程/异常与安装生命周期。

## 不应把正常国家创建当成读档

`2e1a30` 的另两个调用在 `75d1e0`，来自 `481f90`。后者直接引用 dynamiccountries.cpp、client_vassal/crown_colony、NEWCOLONIALCOUNTRY/NEWCLIENTCOUNTRY，说明普通动态国家创建共用 Clear。不能直接在每次 Clear 上计全世界 epoch 后宣称所有命中都是读档；这还需要单独的国家 incarnation 策略，或接受保守撤销造成的额外中断。

## 仍未覆盖的具体点

- The precise UI callback/vtable dispatch for every New Game, Return to Menu and RNW/error callback is not closed;112aba0's stored pointer and indirect calls in112fd10/1131470 require binding before universal UI coverage is claimed.
- Direct relative-call and selected RIP-mov store coverage does not cover computed function pointers, alternate instruction encodings, bulk copies, all exception/unwind paths or unreviewed networking/resynchronization.
- No runtime hook coverage, trampoline/relocation, reentrancy, cross-thread ordering or SEH behavior has been verified. Prefix pins are not installation code.
- Session/context origin can change without world teardown; combine separate811ab0/14c9930/14cd8b0 provenance invalidation evidence. This report does not replace strict SP provenance.
- Ordinary dynamic-country reuse needs a per-country incarnation policy. Raw TAG/full-handle equality alone is not proven to prevent logical identity reuse after Clear.

对 global game 指针的有限 RIP-mov 扫描找到且验证 3 处写入：1ff07c（应用清理置空）、21031d（ResetGame 置空）、74c156（新对象发布）。这不是全部可能写法或间接写的穷尽证明。setup 的 112aba0 两条分支都进入 ResetGame，但尚未完整绑定每个 UI 按钮；不能据 REVERT_SAVE_CAL 文案就称“返回菜单全部覆盖”。

同样，RNW 两个错误 helper 的字符串只证明拒绝/错误分支存在；其中间接回调仍未解析，不能仅凭出现日志判定有没有破坏世界。已闭合的 gamestate 解析失败则明确发生在清理之后，因此失败也必须保持撤销。

外层加载器的失败时序也不同：`5d0580` 的空文件/source 分支在这里的 `826c20` 调用前返回 2；server/source 分支经过该重置后仍可能返回 3。返回码 3 本身也不证明重置分支必定执行；不能从任意“加载失败”文案推断它是否经过撤销边界。候选入口一旦命中则始终保持撤销。

## 下一步的有限验收

先仅安装观察/撤销逻辑，按同存档重复加载、成功/失败加载、setup revert、返回菜单/新局和进程退出逐项核对入口命中顺序，确保旧请求不能在第一次破坏前继续消费。另把 context setter/reinitialize/transport 变化纳入 SP provenance 失效。需要新握手才能重新授权；本报告没有把这些候选提升成生产 gate。

本轮解码 31 个有界函数、81866 字节（含重叠）。
