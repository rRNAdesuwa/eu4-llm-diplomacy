# 1.37.5 五类外交动作的取消构造

本文件只记录磁盘 `eu4.exe` 的有界静态分析，没有执行取消动作、读写游戏进程、创建 marker 或修改已加载的研究 DLL。二进制 SHA256 为 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。以下 RVA 只适用于这份文件。

机器报告为 `work/reports/native-pair-cancel-1375.json`，SHA256 `54dc047d85fe8c06528d5fb3824a1928f56fac2c4bbf24c26e205bcfb08e0df3`，包含 5 个构造 profile、14 项事实、35 个指定入口、36,191 字节反汇编（包括入口之间重叠）。`runtime_verified` 始终为 `false`。生成器 `work/trace_pair_cancel.py` 校验文件 SHA、20 个相关虚槽、全部指令锚点和两处附庸类型字面量；单入口限制 16 KiB / 4,000 条指令，不自动跟随 call，内存保护阈值 768 MiB。

```powershell
python work/trace_pair_cancel.py --deps-dir "$env:TEMP\eu4-native-analysis-deps"
```

## 可编码的五种取消模式

| 对外动作 | native token / 名称 | `value=false` 时的外交官 ID | 新外交官及公共冷却 | 回复 |
|---|---|---|---|---|
| `stop_improving_relations` | `0x2ddb` / `improve_relation` | 保持 `-1`；关系对象关联现有 mission | 不要求 | 无 |
| `stop_building_spy_network` | `0x3378` / `spy_network` | **必须查找并填写现有 spy mission 的 entry ID** | 不要求 | 无 |
| `revoke_guarantee` | `0x2941` / `guaranteeaction` | 保持 `-1` | 要求 | 无 |
| `break_marriage` | `0x28df` / `royal_marriage` | 保持 `-1` | 要求 | 无 |
| `cancel_vassalization` | `0x2940` / `vassalaction` | 保持 `-1` | 要求 | 无 |

`vassalaction=false` 不能映射到 `break_vassalization`。其合法性分支要求特定附庸类型，并拒绝 actor 的宗主正是 target 的方向。

公共资源检查依据是 action 虚槽 `+0x100`：改善关系和间谍网指向 `4e4d50`，直接返回 `value`；另外三类指向 `8f440`，恒真。公共 preview 的 `4ea007/4ea121`、command gate 的 `4e864f/4e8657`、execute 的 `4e7c86/4e7c90` 使用该结果决定冷却、可用外交官、新旅程等路径。因此不能把全部取消动作当成不占外交官、无冷却的行为。

## 共同初始化与调用顺序

每次请求应由原生 factory `35d210(token, null)` 创建新对象，不复用旧请求、clone 或接受/拒绝回复。五类 action 除联姻大小 `0x68` 外均为 `0x40`。

| action 偏移 | 宽度 | 新普通请求的内容 |
|---|---:|---|
| `+0x10` actor | 8B | 实时解析且与 country 对象相符的完整国家 handle |
| `+0x18` original actor | 8B | 与 actor 相同 |
| `+0x20` target | 8B | 实时解析的目标完整 handle |
| `+0x28` date | 4B | 本次游戏线程回调的当前 rawdate |
| `+0x2c` command date | 4B | 同一当前 rawdate |
| `+0x30` envoy | 4B | 先写 `-1`；仅间谍取消进一步解析 |
| `+0x34` state | 4B | `0` 普通发起请求 |
| `+0x38` value | 1B | 对应正向或取消模式 |
| `+0x39` flag | 1B | `0` |
| `+0x3c` request ID | 4B | `0` |

原生 AI 构造现场 `1d59bd..1d59e4` 提供该公共字段初始化证据。factory 留下的 vtable、基础字段和派生对象必须保留。联姻 `+0x40` 是拥有内部存储的 EngineString32，`+0x60` 是 force byte，保持 factory 默认值；不能把它们当作裸指针缓冲区写入。clone `4f07d0` 会重新构造空字符串和 false force，并不复制强制选项。

在完整 actor、target 填好之后，才调用已钉扎的 mode setter：`void __fastcall(action*, bool)`，虚槽 `+0xe0`。间谍 setter 为 `586330`，其余四类为 `4e99d0`。后者只保存 value；前者会读取国家及现有外交官任务来填写 ID。**setter 没有可供判定成功的 bool 返回值。** 复现其只读查找也可作为后续实现方案，但必须逐字段核验已有任务，不能省略 ID 解析。

随后使用已有普通 preview 签名 `4e9d00(action, nullptr, false)`，再构造 wrapper、校验 clone 与所有权、调用 command gate。不要以关闭公共检查的参数预览。wrapper `4e9930` 通过 `+0xb0` clone 后，把 clone `+0x2c` 更新为当前游戏日期。clone 复制 envoy、state、value 和 ID，所以间谍 ID 必须在 clone 前解决。拒绝是正常原生结果；预览或 gate 通过也不是执行成功的证明。

## 间谍取消必须绑定已有任务

`586330` 的 false 分支先检查 actor→target 的关系记录 `+0x46 & 0x08`，再扫描 **actor** 的外交官管理器：`country+0x1480 → +0x18 manager → +0x20..+0x28` 指针向量。它依次要求：

1. entry `+0x18` BYTE 为 `2`，entry `+0x10` mission 非空。
2. mission 的 **vtable 虚槽** `+0x70` 返回 `AL==1`。这里不是读取 mission 实例字段 `+0x70`。
3. mission `+0xa0` task 非空；task 虚槽 `+0x70` 返回 DWORD token `0x3378`。
4. task `+0x20` target 的 slot 与 action target slot 相同。
5. 把 entry `+0x44` DWORD ID 写入 action `+0x30`（`586421/586424`）。

原生 setter 匹配首个 slot 相同对象，且未找到时不会清除先前 ID。因此接口应始终新建 action，将 ID 初始化为 `-1`，并在 setter 后对照完整 handle、已知 mission/task vtable、actor、target、唯一 active entry 和 ID 再检查一次；出现缺失、重复或关联不完整应拒绝构造。不能把调用 setter 本身记成已绑定。

这个检查非常重要：间谍 false 的 per-type validity `5856a0` 检查关系 bit 和附庸限制，却不验证 action envoy。仅写 `value=false` 并保留 `envoy=-1` 可能通过 preview/gate。结算 `4ea820` 的取消分支在 `4eafad` 读取 ID、`4eaff4` 比较 entry ID，只有匹配后才在 `4eb03a` 调用 `25a3c0` 召回该任务。

## 改善关系的关联召回

改善关系 false validity `574460` 检查 actor 的 outgoing improve 索引：索引根 `+0x1d0` 为 entry 数组、`+0x1dc` 为数量；找到目标即可通过对应分支。false effect `573050` 在 `573c0b` 查出关系对象，调用 `a73740` 移除索引，再调用 `a5bb00` 析构关系，最终释放对象。

`a5bb00` 从 relation `+0x30` 取 mission，并以 `EDX=-1` 调用 `25a3c0`。这条召回路径还要求 server 存在、server 虚槽 `+0x140` 返回 false、game `+0x7485==0`、mission `+0x48` entry 指针存在。上述两个状态谓词的完整含义尚未确定；不能据此命名单机状态，也不能假定加载/清理过程中必然召回。

普通取消不需要把已有 entry ID 复制给改善关系 action，也不要在关系析构之外再次手动召回外交官。关系可能立即释放，取消后应重新解析索引，不能再次解引用缓存的旧关系指针。

## 取消后的只读验收

`25a3c0` 将 mission `+0x20` 改为当前 rawdate、`+0x24` 改为返回到达日期；调用 `25a680` 清理 spy task；最后把 entry `+0x18` 写为 `1`。因此取消后可能处于返程中，可用外交官数量未立即上升是正常候选结果。

间谍任务清理会从 owner 的任务列表移除对象，调用 task 虚槽 `+0x80=af09e0` 清掉 actor→target 记录 `+0x46` 的 `0x08`，再析构 task、清 mission `+0xa0`。它没有清空已积累的关系记录 `+0x18` signed WORD 网络值，不能要求该值归零来判定取消。

owner 是 target country `+0x14b0` 指向的对象。owner `+0x4f0/+0x4f8` 为列表首尾指针，`+0x500` 为 **DWORD** count，node `+0x18` 为 **BYTE** removed。owner `+0x504!=0` 时，`a220b0` 只标记 node removed，不立即摘链和减少数量；此节点内的 task 可能已释放，不应解引用。该列表还能包含其他 task token，不能按“列表里所有节点都是间谍任务”解析。只读观察应核对 linked mission、active 节点、task 类型与完整国家 handle，并检测重复和链不一致。

## 保独、联姻和附庸的额外约束

保独 false validity `521ad0` 检查保独索引根 `+0x1a0` 中是否有非空关系对象。索引是双向登记，仅凭索引存在不能证明 actor 是保证国。对外 `revoke_guarantee` 必须额外检查活跃对象 `+0x10==actor`、`+0x18==target`，否则可能撤销相反方向的保证。

联姻 false 仍调用脚本 allow 条件（`4ef613→4ebdb0`），并要求已有联姻。普通取消始终是 `state=0,value=false`；`state=1/2` 是原生回复状态，不能用作取消参数或强制接受开关。

附庸 false validity `51f020` 要求 dependency 索引项、具体类型、休战和威望等条件。`51f393` 取 dependency `+0x40` 类型定义，必须等于全局 registry `0x233ffd8` 指向对象中的 `+0x58` 或 `+0x60`。初始化 `b23ab0` 从固定字符串构造查找，明确把这两个槽分别绑定为 `vassal`、`client_vassal`；`b238b0→b23df0` 负责名称查找和保存指针。`tributary_state` 绑定的是另外的 `+0x80`，不在本取消分支允许集合内。

随后原生检查关系记录 `+0x45 & 0x01` 休战、一个条件谓词下的 actor `+0xcf8` 负威望，并在 actor 的 `+0x18f0` overlord handle slot 等于 target 时拒绝。因此允许方向是宗主取消附庸，不能把 `break_vassalization` 用同一 false action 暴露。接口还应核验 dependency 对象内宗主/附庸完整 handle，不能只使用 slot 或泛化“臣属”标志。

dependency 的名称可以只读解析：`a62b6c/a62b75` 明确从 relation `+0x40` 取 definition，再加 `0x10` 取 EngineString32。名称 `+0x10` 是 QWORD length、`+0x18` 是 QWORD capacity；capacity `<16` 使用内联字节，否则名称首 QWORD 为数据指针。构造 `b23439..b2346e` 和字符串写入 `95110` 共同确认 length、capacity 及末尾 NUL。观察器应限制长度（如 128）、要求 `length<=capacity`、检查适当的内联边界和 NUL；解析失败只能输出类型未知，不能把未知类型验收为 vassal。

## 非玩家国家与 AI 回复边界

公共 preview `4e9d00` 直接从 action 读取 actor/target 完整 handle 并查 country array；本有界入口未出现与 game 当前玩家相等的要求。AI 构造现场 `1d59a4` 也从 AI 所属国家取得 actor，再设置 actor=original。这支持“结构可表达其他国家作为发起方”的静态结论，但不能证明本机客户端或任意多人角色有权代表那些国家提交。现有法国实验不能自动扩大为任意 actor 的运行验证。

回复由虚槽 `+0xd0` 决定：改善关系、间谍网、保独恒 false；联姻返回 value；附庸返回 `state==0 && value`。因此五种取消均不等待 AI 接受，正向联姻和附庸则需要原生回复路径。不得在新请求中填 `state=2` 强制通过。目标是否使用人工回复队列由其控制状态决定，不能简化为 `target != current_player`。原生 AI 路径在 `4e81c1` 创建回复并在 `4e81d0` 填接受/拒绝 state；人工待处理队列仍应按 effects 报告中的请求 ID、value、state 和国家 handle 观察。

下一版十 ID 构造层可以基于这些 profile 固定映射 token/value，以当前国家为已验证范围；间谍取消增加唯一 mission 解析，保独与附庸增加方向和类型约束。正向联姻/附庸的 AI 回复、单机身份真实谓词、任何读档导致的会话失效、其他 actor 的提交权限以及十种动作的逐项效果，仍须分别验证。transport vtable、提交返回 true、外交官减少或冷却改变均不能替代这些证据。
