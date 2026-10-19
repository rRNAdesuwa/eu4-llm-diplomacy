# REA 接入与 EU4 外交逆向工作流

2026-10-15当前增量：新增独立方向性停战缓存CLI已完成12首次离线方法、4独立fake反例、源码和封存差异审查，以及真实4方向只读status/51pin实采审计。工具直接QUERY/VM_READ，无需游戏前台或保存重进；当前状态、原请求效果和持久化继续分别报告。R23–R28使用固定EXE的普通Capstone窄范围及有界原始字节搜索，均不冒充REA深度引擎证据；新原生地址仍研究合同。R26失败断言导致一次同窗最小修复重放，唯一13B与累计26B/32B分别留账。当前游戏顶层native总数仍只有此前R19一次owned body调用；后续缓存工具和静态分析未增加调用/外交效果。详见[实时工具](runtime-observer-1375.md)和HANDOFF顶部；旧MCP不可用状态未重复尝试。

2026-10-15最新增量：fresh CLI通过新的owned system FFI实跑与独立审计（固定lstrlenA/GetCurrentProcessId、ev_b8a73545…），再完成固定80340一次[游戏body-only调用](../work/reports/war-peace-api-20261015-r19-body-live/report.md)，REA ev_c4caa336…、唯一顶层500560 attempt1/normalreturned1、owned A/G前后字节和独立入口恢复一致，255local/11external实采文件审计通过。新调用使用独立namespace/manifest；原零调用入口采样源与stable QUERY/VM_READ观察器均不改。该实验不是完整生命周期/宣战/议和或通用ABI证明，native_ready/sender/lease仍false。无外交请求、世界字段写、保存或重载；owned buffer写与临时代码patch明确另计，全Frida资源unmap不声称。旧节“无游戏函数调用”只适用其当时R12范围；旧MCP错误未重试，成功仍属于fresh CLI。

2026-10-15最新实测：锁定binding修复后的fresh CLI已真实完成一次自有fixture metadata-only attach/scriptload/cleanup，Evidence ev_e3717e49…，77pin独立审计通过；再以审查封存host固定80340自然入口采样，Evidence ev_faef7e7e…、真实Q/tid/5returns/对象链、44reads/372Bowned投影与host原32B恢复通过239pin审计。详见[实机采样报告](../work/reports/war-peace-api-20261015-r12-entry-live/report.md)。CLI所有自有进程已收齐，游戏无请求/函数调用/字段写/保存重载，临时代码钩子不是pureRPM；全agent unmap未证。现存MCP此前旧binding错误原因仍未隔离、未重复调用；成功属于fresh CLI，不冒称MCP已修好。下方device-only/尚未attach是较早准备阶段记录。

2026-10-15增量：实际Frida设备调用发现已有17.23.2可选包缺失binding，现按锁定包的prebuild-only流程补齐，本轮没有修改REA源码、package/lock、Codex配置或全局工具链。[修复回执](../work/reports/rea-frida-repair-20261015/report.md)固定archive/binding与7个来源pin。新启动CLI `python tools/rea.py list-frida-devices --format json --full-output` exit0返回local/socket/barebone；现存MCP仍返回原缺绑定错误，具体缓存原因未隔离，不能称MCP已修复。设备库存无Evidence ID，也不证明attach/script能力；尚未Frida附加EU4或加载hook。外部RPM观察器独立可用，Ghidra/IDA深度引擎仍未配置。下方“未验收Frida”等为2026-10-13初次集成历史。

[独立修复审计](../work/reports/rea-frida-repair-20261015-independent-audit/report.md)核17个输入pin、归档唯一regular member与安装binding流式散列一致；package/lock/manager三个准确源码路径与HEAD相同。配置和全局Node/npm没有前后pin，未做全源码扫描，相关“本轮未修改”是执行记录而非独立全量差异证明。manager保存failure字段，但仍可重新尝试loader，不能将该字段直接解释为禁止重试的原因。没有重新执行REA或attach。

2026-10-13：已将本机 `${USERPROFILE}/rea` 源码构建接入 Codex；当前调查仍以 `HANDOFF.md` 顶部状态和原禁止复测台账为准。

## 接入状态与复现

- REA 源码提交：`e05d3399f19f25fdf04285a02b293418256b26dc`，包版本 `6.4.0`。这是本地源码构建，不能仅凭版本号等同 npm 发布包。
- MCP 注册：`${USERPROFILE}/.codex/config.toml` 的 `mcp_servers.rea`，指向已有 Node 和 `${USERPROFILE}/rea/scripts/rea.mjs mcp`；启动期限30秒。
- 原配置备份：`${USERPROFILE}/.codex/config.toml.rea.backup`。已解析比较：删除新增 rea 节后，配置与备份语义一致。
- 技能：`${USERPROFILE}/.agents/skills/reverse-engineer-anything/SKILL.md` 及其按需参考资料。
- `doctor --client codex --skill` 通过。`mcp doctor` 实际完成 production-stdio 初始化、191个工具、6个提示的精确目录核验，以及 `binary_session` 请求。此结果证明测试客户端可用，不声称当前聊天已热加载新的 MCP 工具。
- 当前会话使用 `python tools/rea.py ...`：从已有 Codex 注册读取命令，原样传递 CLI 参数，复用其环境，不再次安装或启动持久后台服务。下次客户端重连可发现 MCP。

```powershell
python tools/rea.py --version
python tools/rea.py mcp doctor --json
python tools/rea.py inspect-pe-resources '..\eu4.exe' --json
```

本次使用已有 Node 24.19.0、Visual Studio 附带 npm 10.5.2；未升级全局工具链。依赖按原 `package-lock.json` 执行 `npm ci --ignore-scripts --no-audit --no-fund`，再通过依赖一致性检查、生成元数据检查、TypeScript 编译、运行时打包和技能生成。仓库建议的精确开发版本是 Node24.18.0/npm11.16.0，本机版本有差异；没有据此声称完整上游开发验证通过。Turborepo路径初次启动遇到已有 npm.cmd 相对路径错误，之后直接执行同一构建链各步骤完成构建。未改 REA 跟踪源码；未运行依赖安装脚本，因此未验收 Frida 等可选能力。

当前未配置 Ghidra/IDA，Windows 原生 addon 构建产物也未提供。REA 的深度原生反编译暂不可用；不能将191个已广告工具当作191个引擎能力已验证。继续使用项目既有 Capstone 窄反汇编，并明确标为普通文件分析。后续已有合适 Ghidra/JDK/原生包后，再按 REA 的 `docs/windows-ghidra-p0.md` 诊断和配置；不要为解决注册问题反复安装分析引擎。

## 已阅读的目录结构

已清点3314个Git跟踪路径，读取仓库规则、中文说明、技能、CLI/安装说明和实际构建/注册入口；没有宣称逐份阅读所有源码。完整目录清单摘要见 `work/reports/rea-integration-20261013/source-inventory.json`。

| 目录 | 当前工作中的用途 |
| --- | --- |
| `.agents/skills/reverse-engineer-anything` | 调查步骤、证据边界和按需参考资料 |
| `src/domain`、`src/contracts` | 证据语义、工具输入输出合同 |
| `src/application`、`src/composition` | CLI/MCP共享工作流、提供方装配、安装与诊断 |
| `src/cli`、`src/server` | 命令行和MCP入口 |
| `src/ghidra`、`src/ida`、`src/hopper` | 深度原生分析提供方 |
| `src/windows`、`src/process`、`src/artifacts` | Windows约束、进程资源、文件来源和生命周期 |
| `bridge`、`native/windows` | 外部分析引擎桥、Windows原生控制源码 |
| `scripts`、`tests` | 构建、生成、诊断、边界与一致性验证 |
| `docs`、`experiments` | 能力说明、证据格式、效率实验 |
| `third_party`、`licenses`、`website` | 第三方来源、许可、网站内容 |

## EU4 证据规则

1. 先读最新交接、成功排除台账、原调用审计。不得重发原120条批次、已成功、已派发、unknown或所有权未闭合动作。
2. 核对实际 EXE SHA256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`，38,462,504字节。拒绝将旧1.37.4地址应用到它。RVA和载入后VA分别记录。
3. 用最小地址范围回答一个明确条件问题；遵守 `work/AGENTS.md`，禁止大型反汇编整文件加载。保留范围、字节散列、工具版本、资源记录和未跟随callee。
4. REA Evidence保留 `evidence_id`、目标散列、provider、operation和limitations。普通反汇编不包装成REA生成的证据。静态分支、历史快照和当前实时状态分别说明。
5. 先完成条件证据，再决定是否满足既有 `--test-only` 审计许可；full88通过仍不等于语义正确、AI接受或效果成功。任何新行为仍按原项目发布与统一观测流程处理。

本次 REA PE 资源实测得到9个资源节点，证据ID `ev_c34c4669401685a71703ddf79a295b0d135a844f15a086652fbd6c36122d8caf`，目标散列与现有原生profile相同。它只证明文件身份与资源结构，不证明外交逻辑。完整文件：`work/reports/rea-integration-20261013/eu4-pe-resources.json`。

## 本次外交逆向增量

详见 [四候选条件报告](../work/reports/rea-diplomacy-20261013/four-candidate-conditions.md)。对象为换信任、设卫戍国、释放索尤尔加尔、解除贸易保护国。

- 三个family的 `vtable+0x108=false`、`+0x118=0`：四项都跳过公共关系成本不足分支，不能继续用该分支猜测旧拒绝原因。
- `+0x100=true`：四项仍有冷却及外交官检查。公共外交官门槛除state=0数量N，还匹配 `actor+0x1498` 容器中记录的外交官ID数量R，普通模式要求R<N；容器业务名称仍属推断。
- 设卫戍国在Mod legacy条件之前检查战争、primitive、annex索引、精确领主与 `vassal/client_vassal` 类型。
- scriptable local80的外部尾跳已补定点证据；空tooltip full88走公共检查，其local80遍历definition allowed向量。可见性中的类型/方向条件不能由该路径代替。
- 换信任的好感比较为包含等号的阈值比较；旧准备计划中 `>-200` 的文字过严，在阈值确为-200时应为 `>=-200`。保留旧历史文件，通过新报告更正。

当前未闭合：实时外交官匹配容器、march的完整primitive/context、trust的正确执行线程TLS、scriptable实际条件对象及既有冷却。未操作游戏、注入或发送外交命令，历史38项成功与原41派发/77拒绝/2未知均不变。
