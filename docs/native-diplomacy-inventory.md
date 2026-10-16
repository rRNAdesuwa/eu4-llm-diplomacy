# EU4 1.37.5 原生外交静态清单

本轮先使用 `work/runtime/unpacked-1.37.5/` 中解包后的资源建立种子，再离线分析本机 `eu4.exe`。完整机器可读证据在 `work/reports/native-diplomacy-1.37.5.json`。报告发现 **88 个不同的原生外交动作类型、3,344 个虚表槽地址、426 条已从函数边界解码核对的虚表引用**。这是类型、构造、克隆、序列化及分支的静态覆盖；它不等于 88 种动作都已可执行，也不证明这些类型涵盖所有脚本自定义动作及所有参数组合。

本报告限定的 EXE：

| 项目 | 值 |
|---|---|
| SHA-256 | `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a` |
| 文件大小 | 38,462,504 字节 |
| PE ImageBase | `0x140000000` |
| PE TimeDateStamp | `0x66fe6ab9` |
| PE SizeOfImage | `0x25e0000` |
| 标准节 | `.text`, `.rdata`, `.data`, `.pdata`, `_RDATA`, `.rsrc`, `.reloc` |

所有地址均为这个文件重发现的 RVA。虽然部分地址碰巧与旧版研究相同，工具没有以旧地址作为扫描起点，也不允许将此身份判断替换成版本名称。

## 可重复发现方法

```powershell
python -m pip install --target "$env:TEMP\eu4-native-analysis-deps" capstone==5.0.9
python work/discover_diplomacy.py `
  --exe ..\eu4.exe `
  --game-root work\runtime\unpacked-1.37.5\base `
  --deps-dir "$env:TEMP\eu4-native-analysis-deps" `
  --output work/reports/native-diplomacy-1.37.5.json
```

脚本只读取磁盘 PE 和资源，不附加游戏、不注入、不修改二进制。单个输入 PE 上限 128 MiB，单次函数范围上限 64 KiB，每轮引用验证最多解码 16 MiB；Windows 下在进程提交内存超过 768 MiB 时主动停止，留出低于仓库 1 GiB 约束的余量。本轮峰值提交内存约 134 MiB。报告中的资源实测值会随运行变化，因此报告文件的 SHA-256 不是稳定版本标识；应使用 `binary.sha256` 核对构建。

1. 从解包资源的旧式动作头部、定义和 `static_actions` 读取 78 个动作名种子。
2. 遍历 PE 的 MSVC RTTI：发现 507 个名称，其中 82 个能连接到经自引用 RVA 核验的 Complete Object Locator。主要为模板、容器和辅助类型，未发现外交 Action/Command 本身的 MSVC RTTI 名称，不能凭空补造 C++ 类名。
3. 改用引擎自身的整数 token。`.data` 中保存 `uint32 token` 及相邻名称；寻找严格的 `mov eax, token; ret` getter，并要求 getter 被 `.rdata` 函数指针表引用。
4. 对脚本种子反查虚表起点，统计最常见的 getter 槽。`+0x98` 有 77 个不同脚本名称支持，远高于其余候选。要求表前 `0xc0` 全部为指向可执行节的函数指针，避免把包含字符串的普通数据误认成表。
5. 对共同引用函数排序，自动找到 `0x35d210`：它直接引用 68 个种子动作虚表，并按整数 token 分配及初始化对象。再合并共享包装方法的动作类型、特化包装类型和工厂直接构造的类型，得到 88 个不同动作。
6. 从每类 `+0xb0` 槽追踪克隆方法。全部 88 个克隆都观测到分配器 `0x1a332d4`；有直接工厂分支的类型，其分配尺寸与克隆尺寸均相同。

报告的 `native_actions.actions[]` 包含 `name`、`token_id`、`descriptor_rva`、`accessor_rva`、`vtable_rva`、`slots`、`references`、`factory_branch`、`clone` 和 `layout`。`clone.source_field_reads` / `memory_writes` 是指令层面的读写证据，不是完整别名分析或已经确立的所有权模型。

## 工厂和共用布局

候选签名为 `action* factory(uint32_t token, const void* scripted_definition)`，Windows x64 参数寄存器分别为 ECX、RDX。工厂 RVA 为 `0x35d210`；第二参数只在 `scriptable_diplomatic_action` 分支作为 `+0x40` 指针使用。固定原生类型可用空的第二参数做生命周期实验。未知 token 返回 `image + 0x1fd1ca0` 的哨兵对象，**不是空指针**；调用方必须检查 token 白名单、返回对象身份和虚表，不能把任意 token 当成合法工厂参数。

基础反序列化方法 `0x4e8b40` 明确给出了以下 token/字段对应关系：

| 字段 | 相对偏移 | 宽度 | 证据说明 |
|---|---:|---:|---|
| `actor` | `+0x10` | 8 | token `0x2931`，写指令 `0x4e8c84` |
| `original` | `+0x18` | 8 | token `0x2d87`，写指令 `0x4e8d10` |
| `recipient` | `+0x20` | 8 | token `0x2932`，写指令 `0x4e8d7d` |
| `date` | `+0x28` | 4 | token `0x284d` |
| `last_command_date` | `+0x2c` | 4 | token `0x2a2e` |
| `envoy` | `+0x30` | 4 | token `0x2ad6` |
| `type` | `+0x34` | 4 | token `0xe1`；不是每个动作都可默认视为无参数 |
| `value` | `+0x38` | 1 | token `0x3ec`；正向/取消分支的布尔参数 |
| 尚未命名标志 | `+0x39` | 1 | 各核心克隆均将它清零 |
| `id` | `+0x3c` | 4 | token `0xb` |

AI 原生调用处 `0x135df6..0x135e36`、`0x597c78..0x597cb5` 直接构造相同基础布局：`+8=0x165`，`actor=original=行动者句柄`，`recipient=接收者句柄`，两个日期为游戏当前日期，`envoy=-1`，`type=0`，`value=true`，`+0x39=0`，`id=0`。国家句柄不是国家对象指针，也不是只含三字母的字符串。

本轮未发现独立且已经确立 ABI 的通用 initialize/setter。工厂会先完成派生对象初始化，随后原生 AI 调用方直接写基础字段；这给实验适配器提供了依据，但不允许跳过类型专属字段、合法性、外交官、冷却和命令所有权检查。

尺寸分布：55 类为 `0x40`，22 类为 `0x48`，3 类为 `0x50`，2 类为 `0x68`，2 类为 `0x60`，另有 `0x58`、`0x70`、`0x98`、`0x210` 各 1 类。**`0x40` 只表示未观测到基础结构之外的分配空间，不证明该动作没有模式、第三方国家、省份或其他参数。**

## 五类核心动作及取消模式

| 原生名称 | token | 虚表 RVA | 尺寸 | clone RVA | scalar deleting destructor RVA |
|---|---:|---:|---:|---:|---:|
| `vassalaction` | `0x2940` | `0x1c7fd20` | `0x40` | `0x51fa00` | `0x129450` |
| `royal_marriage` | `0x28df` | `0x1c80ab0` | `0x68` | `0x4f07d0` | `0x4ed5b0` |
| `improve_relation` | `0x2ddb` | `0x1c7dd68` | `0x40` | `0x574b20` | `0x129450` |
| `guaranteeaction` | `0x2941` | `0x1c7fe50` | `0x40` | `0x5224c0` | `0x129450` |
| `spy_network` | `0x3378` | `0x1c7cc48` | `0x40` | `0x586200` | `0x129450` |

在这五类的描述文本方法中，`value=true` 进入新建/开始分支，`value=false` 进入取消分支；对应合法性方法也检查该字段。证据包括 `MARNEWDESC` / `BREAKRMDESCR`、`GUARANTNEWDESC` / `REVOKEGUARANTNEWDESC`、`IMPROVERELATIONDESC_NEW` / `CANCEL_IMPROVERELATIONDESC_NEW`、`BUILDSPYNETWORK_LONG_DESC_1` / `CANCEL_BUILDSPYNETWORK_LONG_DESC`、`VASSALNEWDESC` / `VASSAL_CANCEL_CONFIRM`。

因此 `break_marriage` 应映射到 `royal_marriage` 的 `value=false` 变体；它没有单独的原生 token getter。附庸取消的合法性方法 `0x51f020` 将行动者保存为 r15；false 分支在 `0x51f435..0x51f491` 比较行动者的宗主句柄与接收者，如果相同便使用 `IS_SUBJECT` 拒绝。因此该变体静态映射为 `cancel_vassalization`（宗主取消附庸），不能用来实现 `break_vassalization`（附庸摆脱宗主）。它还存在 `CANT_CANCEL_WITH_TRUCE`、`CANCELVASSALNOPOSSPRES` 检查；真实取消结果仍需运行验证。

婚姻对象在 `+0x40` 有字符串对象，在 `+0x60` 有额外标志。工厂及 clone 均正确初始化这些成员；不能给它分配 `0x40` 再手填基础字段。析构器 `0x4ed5b0` 先处理字符串再按 `0x68` 释放，其他四类的 `0x129450` 按 `0x40` 释放。二者均通过第二参数的最低位决定是否释放：`flags=1` 为删除对象的路径。所有权只能在确实由工厂/clone 返回且身份核对成功的对象上使用；命令投递后的对象移交是另一条需要独立验证的路径。

## 实验模块和证据边界

`work/native/pair-probe-1375.cpp` 提供 `bool pair_selftest(uintptr_t base, void (*logger)(const char*))`。它不会自行安装 hook、创建线程或在 DllMain 执行。调用方须在已观测的游戏帧线程上明确调用一次。

模块核对磁盘完整 SHA-256、已加载 PE 的时间戳/映像大小、工厂字节前缀和五类虚表/token getter。随后逐项执行默认对象的 factory → clone → 各自析构，核对上述基础默认值及婚姻字符串状态；不填写有效国家句柄，不调用合法性方法，不构建外交 command，不发送外交行为。日志的 `submitted` 恒为 `false`。即使这一生命周期实验全部通过，也只证明这些默认对象的构造、克隆及析构路径在该线程可用，不证明外交行动成功。

帧前缀 `4c89442418555357488d6c24b04881ec50010000` 在当前文件唯一命中 `0x10a6ec0`。首 `.pdata` fragment 到 `0x10a6f9b`，但有跨 fragment 分支；不能将其误当成完整函数。字节命中本身也不是游戏线程证明，线程必须通过观察确认。

供复核的有界证据文件：

- `work/reports/action-factories.json`：工厂、AI 构造及调用处；最大单函数范围约 14 KiB。
- `work/reports/core-action-clones-and-base.json`：核心 clone 和基础序列化器。
- `work/reports/core-action-value-behavior.json`：五类正向/取消分支与合法性方法。
- `work/reports/frame-and-core-destructors.json`：帧序言和两种已核对的析构器。
- `work/reports/native-command-1.37.5.json`：由共同命令路径分析维护的配套证据；命令队列、日期门槛及发送阶段与本清单分开验证。

完整动作目录还需结合脚本动作、自定义 action 定义、各类参数 schema、游戏冷却/外交官状态以及逐动作的发送/接受/拒绝/取消结果。此报告中的 `runtime_verified=false` 保留这些边界，外部接口不得以静态映射存在为理由自动解除执行门禁。
