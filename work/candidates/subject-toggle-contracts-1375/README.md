# 三个附庸持续交互的静态合同（1.37.5）

本候选闭合 `scutage`、`divert_trade`、`embargo_rivals` 的原生布局和若干正常调用链。它没有进程读取器、DLL、发送器或运行结果。`report.json` 的字节锚绑定游戏 SHA `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。全部运行、效果、生产支持字段保持 false。

这是三种借用的 16 字节交互单例，搭配独立拥有的 `0xa0` subject 命令；不能套用外交 action 的 `35d210` 工厂、`4e9930` wrapper 或 `+88` 预览。亦不能套用先前军役 focus 的 `0x60` 命令。

| 家族 | token | 单例 RVA / 最终 vtable | subject+78 掩码 | 专用检查 |
|---|---:|---|---:|---|
| embargo_rivals | 0x31da | 1fd5278 / 1ce6e58 | 0x02 | 启用要求 actor+2258 != 0；取消不要求仍有宿敌 |
| scutage | 0x31df | 1fd52a8 / 1ce6af8 | 0x10 | 正反两向均要求 subject+289b == 0 |
| divert_trade | 0x3224 | 1fd5338 / 1ce6c60 | 0x40 | 专用槽恒 true；通用宗主/类型/状态检查仍必需 |

`+18f7` 是国家完整宗主 handle `+18f0` 的最高字节，不能另当一个任意 bool。`af4030` 在此字节为零时把 command+90 设为零；否则读取 subject+78 对应 bit。构造器 `af3860(storage,singleton,overlord,subject)` 自动执行这一读取。**+90 是当前状态快照 cancel，不是 desired_enabled。** 未来外部接口只能给明确目标布尔值；已是目标状态应不发命令，需要改变时保留 cancel=current。构造后状态改变，`af3e70` 会拒绝旧快照，不能默默重构重试。

生命周期与权限边界：

- command vtable `1c3a650`；默认参数、每个已证字段宽度、序列化 token 和深复制规则见 `contract.json`。不要逐字节比较整个对象的 padding。
- virtual+60 `af3b70(source, temporary_String32*)` 会正常析构**第二个参数**。它不是普通的一参数 clone。`a7070` 深复制 +70 字符串，重置基类 +18 字符串/+3c，复制 +98 借用指针。`a7180(this,1)` 释放两个字符串及命令 0xa0；从不释放 singleton。
- 全 gate 是 command virtual+40 `af3e20`：先 singleton+30，再 `af3e70(command,null)`。后者核 actor+1344/+26、宗主 slot、依赖定义、类型允许表、状态快照，再调 singleton+28。它自身缺 full generation、DB bounds 和当前玩家授权检查。
- UI `f5c6f0` 证明 common-check 的第二参数可为 null。非 null 是说明输出对象，实际类型尚未闭合，不能传任意 String32。singleton+18/+20/+40 是文本/整数评分相关路径，不能替代 gate。
- 三者 +30 都为 `af61b0`，可能经 TLS 调 `1a334c0`；暂停不令其成为只读。不能凭 globals 或 TLS 值命名 DLC、证明严格单机。

类型许可是 live definition 中独立 token→bool map。`b22910` 使用四字节小端 token 的 64 位 FNV-1a，map 位于 definition+468；sentinel470、size478、bucket vector480/488/490、mask498、bucket count4a0，node+10 DWORD token/+14 BYTE allowed。`b234af → b23e70 → c0330` 提供成员位置、24 字节 sentinel 和初始 bucket 布局证据。未来 RO 要先继承已封军役观察器的完整依赖/registry/name/index/self 验证，再给此 map 加有限链、长度、mask、重复/环、严格布尔和两遍一致核验。本候选仅提供合同，**没有实现该 raw 读取器**。脚本 `00_subject_types.txt` 中某项 yes 不能替代当前 live 表。

正常 UI 的拥有式路径已定位：`f5c7c0` 更新快照；单例+d 决定是否直接执行临时栈对象。三者磁盘初始 +d=0/+c=1，因此选择 heap0xa0 copy `a7070`，经 server virtual80 取得 context，然后调用 `14ca2d0(context,command)`。单例启动注册替换磁盘基类 vtable，因此将来必须核 live token、家族 vtable、+c/+d，而非仅核磁盘。这里不允许借 direct-effect 分支绕过排队。

`14ca2d0` 正常转交前写 sender38 和 tick WORD48，然后调用 transport virtual30；AL1不等于游戏效果应用。其正常提前 false 不释放原件。另一个 `14ca210(context,command**)` 会在检查前清空 caller container，false 不能当归还所有权。已 pin 的 type2 transport `1580370` 序列化原件、借 prototype clone/parse 重建、入队，再在正常路径删除原件；最终 consumer 的线程、生命周期锁、异常展开仍未证明。禁止转交后删除、检查旧指针或重试。

执行后的只读验收不能仅观察一个 bit：

1. **三者都会调用 `327dc0`。** 该函数会重算/失效缓存，可能清另外的 0x20 bit，读写 TLS、动态对象、向量和计数。传入的 source_location 字符串并不说明它只是日志函数。
2. **embargo_rivals** 遍历宗主+2248 宿敌链，对每一国调用 `36cb20(subject,rival,!cancel)`；后者分别做 embargo action 检查和效果。某一宿敌可被拒绝。观察需要有限宿敌链及每一对完整身份、subject→rival relation+46 mask2 等。取消也可能撤掉非此次交互创建的禁运，未保留来源。
3. **scutage 关闭** 还把 `b35df0()+28` 的定义交给 `3c5680`，查找 subject+22b0..22b8 modifier 指针向量，叠加已有条目或新建对象。这里虽然也是 size50/vt1ce8040，定义却在 **+10**，不是五类间谍 timed list 的 +30；不能复用其 parser。定义名称、具体值与期限未闭合，bit off 不是完整回滚证明。
4. **divert_trade 正反两向** 都先移除双方已有 token2e09 trade-power 关系。开启新建 +10=subject supplier、+18=overlord recipient、+44=1 的关系，只有注册成功才写 +40=global233f4f8；bit 已先写，所以不能用 bit 推断注册成功。关闭后 `a612b0` 视依赖定义 +11e/+120 和政府检查，可能恢复 +40=500/+44=1 的默认 50% 转移；因此关闭并不一定意味着 transfer relation absent。旧任意转移不是按历史值恢复。

建议下一步先做新 raw RO 候选：固定当前 FRA→NAV，held PID/creation/EXE/PE/module、完整 handle/DB bounds、宗主向量与双向 dependency、registry/name、singleton 与允许表；读取 subject78、actor1344/26、subject289b 和 actor2258；每项有限预算/双遍同根同 date。随后独立无发送生命周期只能验证 ctor→clone→正常析构；另阶段在已授权游戏线程做 full gate。**本候选并不授权这些后续调用。** 贸易恢复、scutage 修正名及来源、个别禁运效果各需自己的观察合同；initial/final-only 不证明中间的开关都发生过。

复现命令（全离线）：

```powershell
python -B work/candidates/subject-toggle-contracts-1375/trace.py --check
python -B work/candidates/subject-toggle-contracts-1375/find_calls.py --check
python -B work/candidates/subject-toggle-contracts-1375/prepare.py --check
python -B work/candidates/subject-toggle-contracts-1375/validate.py
```

新增 CFG 总量低于 48 KiB，每个 8 KiB 地址窗口；具体 decoded bytes 在 report.limits。既有 report 的字节逐条核对精确 PE，没有巨大反汇编扫描。唯一发现扫描是对已加载 38 MB PE 的 28,724,736 字节 executable sections 搜四个 rel32 target，不解码全段；原始候选只在有界 CFG 命中后才作证据。`bounded_cfg` 可包含非返回错误尾部之后的相邻代码，不能当作完整函数/unwind 证明。新增解码全部入报告，无未记账探索。过程曾因手录证据 RVA `a7044` 不存在而主动失败，已改为实际指令 `a7040` 及完整 destructor 锚；没有放宽校验或执行游戏。

24 个 pure model tests 检查反向状态、只改变目标 bit、full generation、严格类型、缺/多键、失效快照、单例不可释放、clone 第二参数消费及转交/异常后禁止重试。它们不模拟 allocator/引擎，也不证明线程、异常、原始内存或游戏效果。
