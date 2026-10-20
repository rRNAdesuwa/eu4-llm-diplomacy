# 公开 EU4 原生插件逆向桥接参考

## 范围和证据

本报告只读检查 GitHub API 的递归 tree、README，以及与对象、Hook、命令和商人投放直接相关的 raw 源文件；没有下载完整仓库、安装 DLL、启动游戏或修改游戏状态。为避免分支继续变化，结论固定在以下提交（检索日 2026-10-04）：

- [rdavislee/eu4-per-good-trade `b54d922`](https://github.com/rdavislee/eu4-per-good-trade/tree/b54d922afcfd5634a22b16e01b1a427be06e9af4)（`main`，README 标称 EU4 1.37.5；[实现目录](https://github.com/rdavislee/eu4-per-good-trade/tree/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll)）。
- [Celec7/EU4dll `9c1eda2`](https://github.com/Celec7/EU4dll/tree/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f)（`develop`，README 标称 EU4 v1.37.x；[插件源码目录](https://github.com/Celec7/EU4dll/tree/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin)）。

## 结论矩阵

| 仓库 | 1.37.x 证据 | 国家对象 | 主线程/游戏线程 Hook | 命令投递 | 通用外交/议和 |
|---|---|---|---|---|---|
| `eu4-per-good-trade` | 明确是 1.37.5/build `835bfdf8` | 有贸易所需的裸 `CCountry*`、国家句柄、商人容器和贸易记录布局 | 有：月度贸易驱动、帧更新、加载路径均有原生 detour | 有：`pgt.CMD` → 原生 `CConsoleCommandManager::Execute`；另有直接 `PlaceMerchantAtNode` 调用 | 未发现；现有接口全部是贸易/商人/贸易收入 |
| `EU4dll` | README 说 v1.37.x；版本扫描代码接受版本号 `>= 370` | 未发现国家对象布局或国家业务 API | 有字节模式跳转、Steam vtable 等文本相关 Hook；没有通用主循环/外交调度 Hook | 未发现游戏命令投递实现 | 未发现；仓库范围是编码、字体、UI、文件和 Steam 状态 |

## `eu4-per-good-trade`：可直接复用的原生贸易桥

### 版本和对象范围

README 把运行目标限定为 Steam Windows EU4 1.37.5，并说明 DLL 在启动时校验游戏二进制、其他 build 拒绝；`OFFSETS.md` 的第一行进一步固定 build `835bfdf8`，所有地址都是加模块基址的 RVA，更新后必须重新推导：[README#L6-L6](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/README.md#L6)、[README#L91-L95](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/README.md#L91-L95)、[OFFSETS.md#L1-L6](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/OFFSETS.md#L1-L6)。因此这些 RVA 不能直接移植到本机 1.37.4。

它没有一个可包含的、稳定 ABI 的 `CCountry` C++ 类；代码以 1.37.5 内存偏移和函数指针访问“国家对象”。`aiwire.h` 给出了可复用的国家对象发现方法：国家管理器的对象数组来自 `base+0x233D8D0` 指向的数据库对象 `+0x118`，`country_by_index` 以 8-byte 槽读取 `CCountry*`；商人枚举沿 `CCountry+0x1480` 的 `vector<CEnvoyContainer*>`，取 `vec[1]`，再读取 `CEnvoy+0x10/+0x18/+0x44` 和 `CMerchantConstruction+0x80`：[aiwire.h#L20-L26](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/aiwire.h#L20-L26)、[aiwire.h#L113-L123](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/aiwire.h#L113-L123)。

同一文件还暴露了贸易业务函数 `CCountry::CanSendMerchantTo` 的 1.37.5 RVA `0x3532C0` 和调用签名；这是商人可达性判断，不能当成外交动作入口：[aiwire.h#L62-L70](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/aiwire.h#L62-L70)。`livetrade.h` 的国家记录是 `CTradeNode+0x18`、数量 `+0x24`、步长 `0xC0`，记录内读取国家索引、贸易力量、收入和商人状态；同文件还把 `CCountry::AddDelayedIncome(country, 2)` 标到 `0x338A90`，说明它接的是贸易收入类别：[livetrade.h#L458-L504](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/livetrade.h#L458-L504)、[livetrade.h#L526-L530](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/livetrade.h#L526-L530)。这些是很有价值的 1.37.5 国家对象/句柄线索，但字段覆盖的是贸易系统，不是通用外交对象。

### 游戏线程和主循环边界

最清楚的游戏线程 Hook 在月度贸易驱动 `0xB4BA90` 内部的 `0xB4BF09`。`ticklive.h` 说明该点位于价值计算后、收款 pass-10 前，寄存器中有 `rsi=CTradeManager`；处理器写入 `current` 和国家贸易分成后，由引擎继续计算 `rec.total`、`rec.money` 和贸易收入：[ticklive.h#L1-L22](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/ticklive.h#L1-L22)。安装函数用精确字节序列验证 `0xB4BF09` 并拒绝其他 build：[ticklive.h#L1355-L1375](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/ticklive.h#L1355-L1375)。月度处理器还明确把命令 drain 放在“GAME THREAD”上，在读取本 tick 世界前执行：[ticklive.h#L779-L789](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/ticklive.h#L779-L789)。

还有一个帧级游戏线程 Hook：`frame.h` 在地图更新 `0x10A6EC0` 捕获 map renderer，并每 30 帧轮询命令；注释明确指出渲染在暂停时仍运行，因此暂停时也能执行引擎命令：[frame.h#L12-L22](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/frame.h#L12-L22)、[frame.h#L46-L69](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/frame.h#L46-L69)。加载路径还在 `0x774C3B`/`0x775EEC` 等调用点包装新游戏、读档、开局商人安置：[earlyload.h#L1-L15](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/earlyload.h#L1-L15)、[earlyload.h#L38-L47](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/earlyload.h#L38-L47)。

`detour.h` 是桥接方法本身的参考：安装前比较预期字节，构造 trampoline，暂停其他线程确认没有线程正在执行被覆盖区，再写入绝对跳转；stub 保存寄存器并把 `Regs` 传给 C++ handler：[detour.h#L1-L13](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/detour.h#L1-L13)、[detour.h#L127-L205](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/detour.h#L127-L205)。耗时的 30 图求解放到后台线程，以锁保护整份结果；游戏线程只请求、快照和消费已发布结果：[resolver.h#L1-L14](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/resolver.h#L1-L14)、[resolver.h#L149-L193](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/resolver.h#L149-L193)。这个“后台计算、游戏线程提交”的边界可作为外交桥的结构参考。

### 命令投递和原生商人投放

`console.h` 实现了一个真实的进程内控制台桥：读取 `pgt.CMD`，按空格拆成 `argv`，调用原生控制台管理器 `0x6E74C0` 和 `Execute` `0x1721320`；注释要求命令必须在游戏线程运行，文件执行后删除以保证一次性：[console.h#L10-L30](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/console.h#L10-L30)、[console.h#L85-L111](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/console.h#L85-L111)、[console.h#L114-L143](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/console.h#L114-L143)。这是“向原生已注册控制台命令投递字符串”的通用机制；源码只把它用于测试/世界刺激，`shock.h` 还明确选择直接写省份发展值来模拟 `develop`，没有外交命令示例：[shock.h#L1-L12](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/shock.h#L1-L12)。

贸易插件还找到了一个更直接的原生函数：`0x3BAD90 PlaceMerchantAtNode(CCountry*, CEnvoy*, mode, CTradeNode*, steerLinkIndex, force)`。`envoy.h` 记录它分配 `CMerchantConstruction`、登记 envoy、设置 trade record，并说明强制模式没有命令队列、门槛或旅行延迟；代码通过函数指针调用它：[envoy.h#L8-L25](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/envoy.h#L8-L25)、[envoy.h#L51-L58](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/envoy.h#L51-L58)、[envoy.h#L514-L523](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/envoy.h#L514-L523)。

`nocollect.h` 又在 `SetTrader(CTradeNode*, handle, type)` `0xB596E0` 的外层函数上做 detour，覆盖到达、即时投放、`send_merchant`、贸易首都移动四条调用路径，并可通过返回地址/栈扫描记录调用者：[nocollect.h#L7-L30](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/nocollect.h#L7-L30)、[nocollect.h#L86-L125](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/nocollect.h#L86-L125)。这对“识别原生发送者、在正确线程拦截/改写参数”很有参考价值，但它拦截的是商人 `SetTrader`，不是外交命令。

另一个重要边界是：`cmdspy.h` 只有调查注释，确认 `send_merchant` 经由命令 vtable `0x1C4D6C8 + 0x48 = 0x274180`，并列出 UI、AI、国家贸易视图和主循环派发者等创建路径；该文件没有通用命令构造器或发送实现：[cmdspy.h#L1-L6](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/cmdspy.h#L1-L6)。

对于商人指向，插件也明确绕过了原生 `steer_command` 的表达限制：原生命令 token `0x2DB9`/`Execute 0x5DA4F0` 只把 outgoing 列表序号写到 `rec+0xA8`，无法命名被 Phi_w 画成 incoming 的端点；插件改用 `(country,node)->target` 旁路表，并在已有记录上同步 `+0xA8/+0xAC/+0xAE`：[assign.h#L8-L19](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/assign.h#L8-L19)、[assign.h#L88-L110](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/assign.h#L88-L110)、[syncrec.h#L9-L22](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/syncrec.h#L9-L22)、[syncrec.h#L54-L114](https://github.com/rdavislee/eu4-per-good-trade/blob/b54d922afcfd5634a22b16e01b1a427be06e9af4/impl/dll/syncrec.h#L54-L114)。这说明“有一个原生命令”不等于“它能表达任意外交对象/条款”。

### 外交和议和判定

在该提交的公开 tree 与针对性源文件中，未发现 `diplomacy/peace/war/treaty/truce/alliance/vassal` 等外交/议和实现；代码中实际命名的国家函数仅包括商人可达性、商人投放、贸易记录和贸易收入。没有外交提议对象布局、外交命令 payload、议和条款序列化或 AI 接受/拒绝投递入口。因此不能把 `CCountry*`、`Execute`、`send_merchant`、`SetTrader` 或 `PlaceMerchantAtNode` 解释成通用外交/议和接口。

唯一可保留的“通用性”是 `CConsoleCommandManager::Execute`：如果目标版本确实注册了某个外交控制台命令，它理论上可以执行命令字符串；本仓库没有提供这样的命令名、参数或和平提议证据，不能据此宣称已经打通原生议和。

## `EU4dll`：适合作为 Hook 技术参考，不是外交桥

README 将项目定义为双字节字符显示 DLL，功能是 UTF-8 转换、Steam Rich Presence、校验码覆盖和 Proton/Wine 支持，并写明仅支持 EU4 v1.37.x：[README#L5-L18](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/README.md#L5-L18)。`src/plugin/dllmain.cpp` 在 `DLL_PROCESS_ATTACH` 校验版本后依次初始化 FileRead、字体、主文本、tooltip、地图文本、事件对话框、存档、日期、IME、输入和本地化 Hook，没有国家、外交、和平或命令模块：[dllmain.cpp#L4-L30](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/dllmain.cpp#L4-L30)、[dllmain.cpp#L40-L91](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/dllmain.cpp#L40-L91)。其 [CMake 源文件清单](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/CMakeLists.txt) 也只列这些文本/UI/文件模块。

版本识别是扫描字符串 `EU4 v1.??.?` 后读取三位版本号，代码注释写“接受 1.37.x 及以上（370+）”；因此 README 的“1.37.x only”比检测代码更严格，且没有 1.37.5 的固定 build SHA 或国家对象偏移：[version_detect.cpp#L18-L35](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/version_detect.cpp#L18-L35)。实际 Hook 依赖字节模式和版本专用汇编跳板，例如输入 Hook 扫描特征后 `MakeJMP`：[input.cpp#L16-L69](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/hooks/input.cpp#L16-L69)。这对“按特征定位、保存返回地址、写跳板”有参考价值，但不是游戏主循环或外交 dispatcher。

`injector.h` 提供 `VirtualProtect` 保护切换、相对地址解析、近距离/远距离 `MakeJMP` 和 `MakeCALL`；`plugin_64.h` 的 `ParadoxTextObject` 只是文本对象的 `std::string` 兼容布局：[injector.h#L63-L88](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/injector.h#L63-L88)、[injector.h#L125-L193](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/injector.h#L125-L193)、[plugin_64.h#L62-L100](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/plugin_64.h#L62-L100)。Steam Rich Presence Hook 明确另起 `CreateThread` 等待 Steam，再改 `ISteamFriends` vtable；这不是 EU4 主线程调度器：[steam_rich_presence.cpp#L117-L195](https://github.com/Celec7/EU4dll/blob/9c1eda2127f616a52bd2dd9fdcca2acf25e1918f/src/plugin/hooks/steam_rich_presence.cpp#L117-L195)。

递归 tree 中没有外交、和平、战争、国家或命令模块路径，且已检查的源码只围绕字体、文本、输入、地图、事件对话框、存档和文件读写。因此 `EU4dll` 没有可复用的国家对象、外交消息 payload、和平提议发送或 AI 接受/拒绝调用；它与本任务的关系仅是提供成熟的字节模式/跳板 Hook 先例。

## 对当前原生议和路线的实际启示

1. 可移植的技术模式是：先校验精确 build 和预期字节；在游戏线程 Hook 内只做轻量读取/提交；复杂计算放到后台并以整份结果交换；所有写入前验证对象槽位、句柄索引和线程边界。
2. `eu4-per-good-trade` 的 `CCountry*` 线索只能支撑贸易国家对象和商人对象。要保留原生外交/议和接受判断，仍需在本机 1.37.4 上定位外交提议对象、原生发送函数以及进入其命令/通知队列的游戏线程入口；公开插件没有替代品。
3. `pgt.CMD` 是可复用的“投递已存在控制台命令”通道，而不是任意内部命令构造器。若 `helplog` 或本机静态审计找不到和平提议命令，就不能从该通道推导出议和发送能力。
4. 不要复制 `eu4-per-good-trade` 的 1.37.5 RVA 到本机 1.37.4。其 `OFFSETS.md` 是固定 build 的实测地图；旧注释和后续修订可能存在字段命名差异，应以同一提交的 consolidated `OFFSETS.md`、调用点字节和本机反汇编为准。

## 受限结论

这两个公开插件证明了 EU4 1.37 系列可以通过原生函数 Hook、对象偏移、游戏线程 detour 和内部控制台执行实现贸易/文本桥接；它们没有公开通用国家外交 API，也没有公开原生议和提议的构造、发送或响应队列。当前报告不把贸易 Hook、编码 Hook、GUI 控件名或 `CCountry*` 贸易布局误标为外交/议和接口。
