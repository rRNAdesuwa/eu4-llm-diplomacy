# 王位宣称、出售省份、强制和平、战争威胁：1.37.5 静态合同

这份候选只绑定 SHA `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a` 的磁盘 EXE。四族均在旧目录有字符串、虚表或字段映射；本轮新增的是正常 AI 构造、预览与拥有式传递、派生参数、执行分支证据。没有读取进程、调用原生、构建 DLL、修改正式目录或公开执行能力。全部 runtime / effect / production 状态为 false。

| 公开名称 / 原生名称 | token / 大小 | 派生参数 | 正常调用边界 |
|---|---|---|---|
| claim_throne / claimaction | 2949 / 40B | 无 | 136ea0 → 129b60 → 拥有式 AI 队列 |
| sell_province / sellprov | 2a29 / 48B | +40 DWORD 整数金币；+44 DWORD 省份 ID | 138090 → 129b60 → 拥有式 AI 队列 |
| enforce_peace | 2dda / 48B | +40 QWORD 完整对战第三国句柄 | 13b810 的 13ca51 分支 → 129b60 → 拥有式 AI 队列 |
| threaten_war | 3307 / 50B | +40 DWORD 省份 ID；**+44 未对齐 QWORD** 受让国句柄 | 13d4c0 的 13e991 分支 → local +80 → 4e9930 → bfe50 |

表中的数字是十六进制。enforce_peace 的额外字段不是战争 ID 或 borrowed war pointer。threaten_war 的已闭合 AI 参数配置只覆盖受让国等于 actor；没有据此开放任意第三国。四族的正常正向 value 都是 true；本轮不定义任何 false/cancel 接口。

## 构造、日期和拥有关系

工厂是 35d210。claim 2949 从一级 byte / RVA 分发表进入 35d94b；enforce 2dda 从另一分发表进入 35e365；sell / threaten 分别由已保存比较分支进入 35dbed / 35ed67。`trace.py` 直接核对两个分发表字节、四个 token getter 和每个库存虚槽，不仅依赖类名。

四族默认共有 marker +8 = 165、+10 / +18 / +20 为 `---` 无效句柄、+28 / +2c = 29c77f8、envoy +30 = -1、state +34 = 0、WORD +38 = 1、+3c = 0。派生参数默认是 -1 或无效句柄。未知 padding 不属于合同；模型 bytearray 的零 padding 是模拟存储初始化，不是引擎已证默认值。

正常 AI 栈对象分别显式写完整 actor、current_actor = actor、target，两日期均来自当时 game +1dd0，并写 state 0、envoy -1、value true、+39 零、id 0。threaten 分支的 EBX 在 13e8f8 归零，再写 state/id；enforce 的 R13D 在 13c241 / 13c455 归零且至该分支无非零赋值。正常 AI 不是把工厂无效句柄对象直接送出。

clone +b0：claim 53cfc0 / sell 550c80 / enforce 572670 / threaten 54bb80。各自分配 40 / 48 / 48 / 50B；复制两个 actor、target、envoy、state、value、id、各自额外字段。两个 clone 日期都取源 **+28**，不是把源 +2c 原样复制；+39 总是清零。wrapper +40 = 4e9930 再创建独立 clone，把 clone +2c 改为当前 game 日期，分配 58B command，将 clone 放在 command +50。

command 析构 4e7470 先查询 clone 虚槽 +a8；四族该槽都钉扎到 8f450（false），随后调用 clone deleting destructor。claim 用 129450 / 40B，sell、enforce 用 129500 / 48B，threaten 用 5445e0 / 50B；它们没有额外 heap-owning 参数。command 同时析构自己的 String32 并释放 58B。原始栈对象或独立原件与 command-owned clone 不是同一个对象，不能双重释放。异常路径的实际引擎清理行为未证明，模型选择终止、不猜析构、不重试。

前三族正常 AI 转到 129b60，129da0 调 full +88(NULL,false)，129db9 调 local +80(NULL,false)；12a6e3 调 wrapper，12a6f5 清临时拥有指针，12a6fb 转入 AI owner +a68，旧 command 另行析构。威胁战争的已见正常 AI 路径不同：只证 local +80 的直接调用，然后构造 command，经 bfe50 将 caller container 清空并调用 14ca210。其 full +88 的实现已核对，**没有证明这个正常发送分支调用了 +88**。本轮不把 bfe50 返回当外交已应用，也没有扩充 sender。

## 参数与预览边界

派生 serializer / parser 复用旧精确 CFG：sell 552ab0 / 552b80 对应 `amount` token 1a1 和 `province` 2843，都是 DWORD 整数；enforce 572eb0 / 572f80 对应 2dda 完整国家句柄；threaten 54c9f0 / 54cb20 对应 province 2843 和 taker 314d。

sell 的 AI 从 2000 整数金币开始评分，再以 200 / 100 / 50 调低。接受执行分支的 54fe0b、54fe49 才将 +40 乘 1000，分别交 338540 / 3387f0 收入和支出路径。因此外部 milli 金额不能直接写 +40。模型仅采用 0..2147483 的保守范围来排除已见 signed32 乘法溢出，不声称这是游戏的全部合法价格范围。

claim 的 local 53c5c0 覆盖宗教、威望、正统性、政府、摄政、同王朝、独立性、已有宣称、婚姻、继承人及脚本 gate。sell 的 local 5503b0 检查属国、战争、贷款、宿敌、敌人、所有权、殖民、围城和可造核等。enforce 的 local 5715d0 从国家关系中选取已有战争，检查目标战争、宗主/属国、休战、第三国在同场战争、联盟战争类型、好感、进攻方、宣战许可、战争分数和脚本。threaten 的 local 54b200 检查宣战、属国、战争、休战、合格省份以及脚本。

claim / sell / enforce 的 full +88 首先进入 generic 4e9d00，再处理可选说明输出；正常 NULL sink 会跳过该文字部分。generic、family local、full 和 command +40 gate 是独立边界，不能用其中一个替代另一个，也不能将 false 当基础设施失败或发送许可。

这些检查没有只读保证。claim 调用政府 getter 40a6d0；enforce local 会构造带 CB 的临时宣战对象并调用 508db0，最后走虚槽/容器清理；threaten local 与 full 54b860 同样有 CB 克隆、虚槽检查、容器分配与析构。NULL sink / 暂停 / 临时对象均不能证明没有 lazy cache、TLS、脚本、全局或其他游戏状态副作用。完整 transitive CFG 和引擎线程寿命仍未闭合。

## 执行效果和未来只读观察

* claim 的 reply 虚槽 +d0 = false。53b8e0 不先要求 state2；它调用 4ec160，并处理关系/威望/通知。53ba82 对 `actor +1510 + target_slot *48` 调 a6f5f0(true, actor)。a6fc10 / a6fc15 清再设置关系记录 +46 的数值掩码 **1**，并处理其他 dirty bits。最小未来 RO 验收可以绑定该方向的完整记录身份和掩码变化；不能把反向记录、mask4 或 state2 当结果。
* sell 只在 state2 的接受分支转移金币、调用 a020f0 改省份所有权，随后处理相关历史/控制状态；state1 走拒绝通知。future RO 应同时绑定省份 ID、owner +468 完整句柄、双方财政字段与回复消息。这里已证明读 owner +468 和调用所有权 mutator，未追完底层每个写操作，也未建立实际财政采样器。
* enforce 先重检 local 和 +40 句柄高位有效标记。state2 接受时构造 975d40 peace offer、复制到嵌套外交对象，包成 command 后直接调用 +48 execute，再析构原件/clone。state1 拒绝时构造 53e030 join-war action，显式 state2，包 command 后执行；某些宗主/属国分支还有更多 join-war 对象。因此拒绝可能导致参战。未来 RO 要证明当前战争完整身份、双方阵营、第三国参与关系与回复分支，不能以冷却或无 pending 推断。
* threaten state2 把选定省份给 +44 taker，并调用威望、休战、好感、历史和 `have_threatened_war` 路径。state1 拒绝可能由 54afe0 生成 CB，检查其虚槽 +78，构造 500480 后执行 501290 宣战，再析构该 CB。54afe0 的 fallback / 虚槽拥有约定不能泛化成“任意返回指针均 free”。未来 RO 需要省份归属、战争/参战图、双向休战、消息相关性；不是简单币值或单标志观察。

这些是静态分支证据，不是 UI 操作、游戏运行、接受结果、保存重载或因果证明。可以优先设计 claim 的无发送生命周期/预览候选和方向明确的 mask1 RO；执行实验还需真实 held world、完整 generation、引擎线程、权限、冷却和外交官等独立门槛。enforce / threaten 的连锁战争效果应有单独实验与验收设计。

## 可复核边界与预算

`report.json` 将每条旧指令保留 `source` 与 `source_pointer`；`trace.py --check` 逐条对 exact PE 核 bytes / ASCII / 虚表槽 / token / 工厂跳转表。不重新解码导入 CFG。`facts.json` 是锚点索引，`contract.py` 是离线严格类型、字节布局和拥有关系反例模型，均不是 raw producer 或原生 ABI 的运行时验证。

新增解码账本共 **46,674B / 49,152B**：5 个 exploration 文件；最大单 CFG 7,485B。账本包含一次有限 slice 末尾截断失败的 1,223B 保守上界，以及 479B 诊断性重复/错误边界探索；这些不作为证据。第四份只采用后来从确切入口到第一无条件分支的 522B。既存 report 的重用 bytes 另列，不能混入新增额度。探索峰值 commit 89,141,248B；完整重放内存输出留在 validation 日志，均远低于 1GiB。没有全文件反汇编或 350MB 文本扫描。

离线入口（从仓库根执行）：

```powershell
python -B work/candidates/war-dynasty-province-contracts-1375/trace.py --check
python -B work/candidates/war-dynasty-province-contracts-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/war-dynasty-province-contracts-1375 -p test_*.py -v
```

所有 shell exit / stdout / 源输入 before-after SHA 在 `validation-results`；作者 seal 不替代另一 reviewer 的独立审查。
