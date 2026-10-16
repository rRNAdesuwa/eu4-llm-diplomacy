# 1.37.5 五类外交动作的效果验收

本文件是离线静态证据，**不是实际发送成功报告**。没有读取或写入运行中的游戏，也没有调用原生方法。适用的 `eu4.exe` SHA256 为 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`，所有地址均为相对此模块的 RVA。

机器报告：`work/reports/native-pair-effects-1375.json`，SHA256 `b67e9e3ec3d333ad5603c9bcb7a70d614bab1107f283c6f01d99e7c744730ae0`。报告包含 15 项观察规范、47 个指定入口的有界控制流和 61,141 字节代码（包括入口间重叠）；所有 `runtime_verified` 均为 `false`。每项事实的 `evidence_instructions` 保存确切指令及原始字节，`vtable_checks` 自动计算六处构造 LEA 的 RIP 相对目标并断言。生成器不跟随调用，不扫描全部代码，单入口限制 16 KiB / 4,000 条指令，内存保护阈值为 768 MiB。

```powershell
python work/trace_pair_effects.py --deps-dir "$env:TEMP\eu4-native-analysis-deps"
```

## 应记录什么

原生提交函数返回真、容器被消耗、外交冷却改写、空闲外交官减少都不能独立证明效果生效。正式验收应在同一国家对的前后快照中记录下列证据，并把无法确定的结果留为 `unknown`。

| 动作 | 正向生效的核心证据 | 取消的核心证据 |
|---|---|---|
| 改善关系 | actor 的 outgoing、target 的 incoming 索引指向同一活跃改善关系对象；对象 actor/target 匹配；`relation+0x30` 关联 token `0x2ddb` 的外交官 mission | 两个方向对应索引项被移除；重新解析索引，不再读取原来的已释放对象 |
| 间谍网 | actor→target 的关系字节 `+0x46 & 8`；外交官 mission token `0x3378`；`mission+0xa0` 指向身份、目标与外交官 ID 匹配的 spy task | 活动位清除，task 从所属列表移除，`mission+0xa0` 清零；外交官仍可能在返程 |
| 保证独立 | 保独索引中有活跃对象，且 `object+0x10=保证国`、`+0x18=被保证国` | 两侧索引均移除该对象；方向必须用对象字段判断 |
| 王室联姻 | 接受回复后存在活跃婚姻对象，两侧索引一致，双方完整 handle 匹配 | 两侧婚姻索引移除；已有其他关系不受这一验收条件替代 |
| 提议附庸 | 接受回复后有活跃 dependency 对象，`+0x10=宗主`、`+0x18=附庸`，类型定义匹配；附庸 `country+0x18f0=宗主handle` | dependency 索引移除，附庸 overlord 字段刷新；不可只检查一个通用“臣属”位 |

这里的“存在”只能证明该快照的结果状态。要把新状态归因于某次发起，必须记录前态、发起国家对、动作模式、原生日期，以及协商动作的请求 ID / 回复状态；已有关系不能算本次执行新增。

## 关系对象的只读定位

`country+0x1510` 指向每项 `0x48` 字节的关系记录；用另一国家的已验证 slot 索引。记录 `+0` 指向所属国家的关系索引根，`+0x10` 是另一国家的完整 handle。

各索引有一个数组指针和一个 DWORD 项数。元素大小为 `0x10`，元素 `+0` 为 DWORD slot，`+8` 为关系对象指针。线性查找与引擎 getter 一致。必须限制项数、验证指针可读、核对完整 handle，不能仅相信 slot。

| 索引 | 根+数组指针 | 根+DWORD数量 | 原生 getter |
|---|---:|---:|---:|
| 联姻 | `0x68` | `0x74` | `0xa68be0` |
| 附庸 / dependency | `0x128` | `0x134` | `0xa69970` |
| 保独 | `0x1a0` | `0x1ac` | `0xa6a050` |
| 主动改善 | `0x1d0` | `0x1dc` | `0xa6a350` |
| 接收改善 | `0x1e8` | `0x1f4` | `0xa6a450` |

关系对象共有 actor `+0x10`、target `+0x18`、开始 rawdate `+0x20`；apply 写 `+0x28=0`，remove 写 `+0x28=1`。这些是关系对象字段，与 diplomacy action 的同偏移字段不可混用。

| 对象 | 大小 | vtable RVA | 额外证据 |
|---|---:|---:|---|
| 改善关系 | `0x48` | `0x1c81658` | `+0x30` 为外交官 mission 指针 |
| 保独 | `0x48` | `0x1c817d8` | 对象 handle 确定保证方向 |
| 婚姻 | `0x40` | `0x1c80be0` | 双方索引引用同一对象 |
| dependency | `0x90` | `0x1c81758` | `+0x40` 为类型定义指针，定义 `+0x10` 为原生字符串名称 |

保独与婚姻的关系记录 `+0x46 |= 4`、国家 `+0x2884=1` 会同时出现在添加和移除路径，是刷新标记；**不能将 bit 4 当作关系存在标志**。证据：`a69ed0@a69f30/a69f5d`、`a68a80@a68b37/a68b5a`。

## 具体应用与取消路径

改善关系 effect `0x573050` 以 action `+0x38` 区分模式。正向在 `573114/573118/57311c` 写关系 actor/target/date，`573129` 注册、`573135` 调用 apply `a73540`；后者使用 `a6a250` 写 actor→target outgoing，使用 `a6a390` 写反向 incoming。通用结算 `4ea820@4eaf12` 把所选外交官 mission 写入关系 `+0x30`。

取消路径 `573c0b→a6a350` 找到 outgoing 关系，`573c16→a73740` 注销并清两侧索引，随后析构并释放 `0x48` 字节。已积累的好感是另一项状态；停止任务不意味着好感立即归零。

保独 effect `0x520900` 在 `520e3d` 检查 value。正向 `520e89/520e8d` 保存 actor、target，`520ea6` 注册，`520eb2→a5f230` 把同一对象放入双方索引。取消 `52144a→a6a050` 查对象，`5214d5→a5f2d0` 清双方索引后析构。索引是双向可见，保证方向只在对象内部字段中。

婚姻 effect `0x4ed640` 先在 `4edb77/4edb7a` 检查 action `+0x34==2`，然后 value=true 才创建关系。state=1 进入拒绝分支；state=0,value=true 不创建婚姻。正常取消 state=0,value=false 在 `4eed24` 后进入移除路径，`4eee31→a68be0` 查找，`4eee3c→a5eaa0` 删除双方索引，`a5f00c` 写 removed。

附庸 effect `0x51d810` 同样要求 state=2,value=true 才创建：`51dd37/51dd3a` 把 target/actor 传入 `4e6e00`，后续 `4e5630` 分配 dependency，`4e5da2/4e5da6` 保存宗主与附庸，`4e5d55` 保存类型定义；apply `a5ff20` 更新双方索引。`36c730` 先使 country `+0x18f0` 无效，再根据 dependency `+0x10` 确定宗主并写回；同时更新宗主的 subject handle vector `+0x1a18..+0x1a20`。取消通过 `51ed90→a69970`、`51ed9b→a61420→a61900`，清双方索引并对两国调用 `36c730`。这个 dependency 家族能表示其他附属类型，因此类型定义名称也是验收条件。

## 外交官任务：区分改善与间谍网

外交官路径为 `country+0x1480 → +0x18 manager → +0x20..+0x28 指针向量`。entry `+0x44` 为 DWORD ID、`+0x18` 为 BYTE 状态、`+0x10` 为 mission 指针。`4e7550` 分配 `0xf8` 字节 mission，构造函数 `257a40` 设置 vtable `0x1c4b2b8`。

| mission 字段 | 含义 | 写入证据 |
|---|---|---|
| `+0x80` / `+0x88` | actor / target 完整 handle | `4e758a` / `4e7595` |
| `+0xa8` DWORD | 原生 action token | `4e75f0` |
| `+0x48` QWORD / `+0x50` DWORD | entry 指针 / envoy ID | `4e77bc` / `4e77c3` |
| `+0x20` / `+0x24` DWORD | 当前行程开始 / 计算到达 rawdate | `4e7879` / `4e787c` |
| `+0xa0` | spy task 指针；改善使用关系对象的 `+0x30` 链接 | `4eaf57` |

token：改善 `0x2ddb`，间谍网 `0x3378`，保独 `0x2941`，联姻 `0x28df`，附庸 `0x2940`。创建可将 entry 状态置为 1（`4e77d7`），持续任务结算会置为 2（`4eacec`）；状态值本身不能区分任务类型。返程 `25a3c0` 会重新写 mission 的开始/到达日期（`25a638/25a641`），因此这些日期不是永久的首次发起时间。

间谍任务由 `af04a0` 针对 token `0x3378` 创建，大小 `0x50`，vtable `0x1ce3ba0`。task `+0x18=actor`、`+0x20=target`、`+0x2c=envoyID`。通用结算把它挂到 mission `+0xa0`，再调用 task 虚槽 `+0x68=af0960`，后者将 actor→target 关系记录 `+0x46` 的 bit 8 置位。

task `+0x10` 指向 **target country 的 `+0x14b0` 对象**；这由 `4ebd80` 明确读取，不能误写为 actor country 指针。该对象的任务链表 head/tail/count 分别在 `+0x4f0/+0x4f8/+0x500`。节点 `+0` 为 task、`+8` previous、`+0x10` next、`+0x18` removed byte，添加路径 `a21fc0`。

task 虚槽 `+0x58=af0880` 更新 actor→target 关系记录 `+0x18` 的 signed WORD，限制在 `[0,10000]`。它支持“网络确实在增长”的后续观察；本函数不能独立证明 UI 百分比换算。暂停游戏时未增长不代表启动失败。

取消经 `4ea820@4eb03a→25a3c0→25a680` 移除任务列表项，调用 task `+0x80=af09e0` 清 bit 8，再析构任务并清 mission `+0xa0`。该路径不会直接将网络规模写零；外交官返程也不意味着任务仍在运行。取消命令如何正确携带已有 envoy ID 必须结合 action 初始化/合法性路径核对，不能给 `-1` 后仅因提交成功就宣称取消。

## 原生回复与待处理队列

原生 command 执行 `4e7c50` 对 state=0 且需要回复的动作处理 AI 或待回复队列。AI 路径 clone 后调用 action 虚槽 `+0xb8`（`4ea1e0`）；该包装器调用 `+0x120` 并以 `score>=1` 为接受。vassal 的评分方法为 `51fab0`，marriage 为 `4f0bf0`，都包含游戏规则及可选的控制台作弊分支，不能用静态固定分数替代。

`4e81c9..4e81d0` 将回复 clone 的 `+0x34` 设置为 `1 + accepted`，因此 1 为拒绝、2 为接受；随后 `4e81e7` 包装、`4e81ed` 提交回复 command。原请求并不会因发起成功而自动等价于收到接受回复。

保独、改善、间谍网的 `+0xd0` 均为 false，不走这条协商接受链。联姻 `+0xd0` 返回 value；附庸 `51fa90` 返回 `state==0 && value`。

针对人工/待处理回复，recipient country 的队列字段为 head `+0x18d8`、tail `+0x18e0`、DWORD count `+0x18e8`。节点 `+0` action、`+8` previous、`+0x10` next、BYTE `+0x18` deleted。queued clone 获得 `action+0x3c` 请求 ID（`4e82a9`）及 `+0x2c` 当前 rawdate（`4e82b9`）。可只读记录 ID、token、actor/original actor/target、value、state。state=0 的匹配节点表示待回复，不能表示接受。

AI 回复 command 可能很快消费；当前未定位独立持久的“最后拒绝”存储。关系未生成、队列项消失、外交官返程，都不足以排除超时/取消/合法性失败。可靠的 `rejected` 归因需要捕捉匹配 ID 的 state=1 原生回复处理事件；没有捕捉到时只报告未知，而不是用缺少关系倒推拒绝。

## 下一版观察器的最小实现范围

第一次真实发起改善关系前后，读取 FRA→ENG outgoing、ENG→FRA incoming、所有 FRA 外交官 mission 身份与 token。通过关系对象 vtable、双方完整 handle、removed=0、两侧索引一致、relation+0x30 对应 envoy mission 来确认任务已创建。即使 transport 返回 true，也要等这些结果后才报告效果。

只读实现应在同一稳定游戏帧执行或采用重复快照一致性核验；限制向量/链表长度，记录不可读与状态变化，不读取已移除指针，不调用上述 getter。这个报告提供读取算法和静态字段来源，不替代运行验证，也不更改对外接口的执行能力标记。
