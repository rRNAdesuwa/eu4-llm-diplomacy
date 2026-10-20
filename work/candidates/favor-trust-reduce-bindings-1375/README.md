本候选补齐两项旧参数缺口：信任交换的动态默认值来源，以及降低关系的正常 GUI 第三国家选择。它只含精确 PE 静态证据、注入字节读取回调的纯只读模型和离线测试；没有进程读取入口、引擎调用、发送器或生产权限。

| 行为 | 参数绑定闭合 | 限制 |
|---|---|---|
| trade_favors_for_trust，token `0x3bd3`，对象 `0x48` | `NDefines.NDiplomacy.INCREASE_TRUST_COST` → DWORD `233db7c` → action DWORD `+40` ×1000；`INCREASE_TRUST_AMOUNT` → DWORD `233db80` → action DWORD `+44` 原整数 | 不能把解包文件的10/5填成实际值；未实现任意GUI步数/金额接口 |
| reduce_relations_favor，token `0x3bcd`，对象 `0x48` | GUI第三国 country `+20` 完整句柄 → dialog `+210` → action QWORD `+40` | 不是省份编号或裸TAG；参数存在不等于合法性、AI接受或发送许可 |

信任的具体加载证据在 `report.json/facts/lua_load_order` 和 `lua_integer_conversion`。`48c940` 的有限前缀先加载 `common/defines.lua`，再处理 `common/defines` 目录及难度输入，最后取 `NDefines` 表。`48f058/48f05f` 与 `48f0e5/48f0ec` 分别钉扎目标全局和原始键名。整数加载器 `14a7650` 的 R8 是目标地址；Lua type3 经 `17eb890` 的 `cvttsd2si` 截断为整数，再写低32位，错误类型记录错误并保持先写的零。文件系统覆盖排序未全量追踪，因此必须读取未来精确进程内的值。

`contract.capture_defaults(read, Context)` 示范私有读取：固定 `module+233db7c` 连续8字节，两次读取之间及末尾重核 game/database/array/count/player/date 和玩家完整句柄，26次/184字节。没有实际OS句柄、模块验证实现；Context中的SHA仅是外层需认证的输入，不能用本模块返回值证明真实身份。原始有符号值始终保留，保守编码域 cost 0..2147483、amount 0..100 之外返回 `favor_milli_candidate=null`，绝不默填10/5或复现溢出。零是明确观测数值，不能解释成取消。

降低关系的人类路径：`f0acd0` 对 action虚槽 `+98` 返回token分支，`3bcd` → `1082b40`。该对话框复用名字为 `ProvDialog` 的布局，实际遍历 `game+1d20` 的国家句柄数组（DWORD数量 `+1d2c`），排除有效玩家，再经 `5575b0(actor,target,candidate)` 和 `557650(actor,candidate,text)` 筛选/启用行。`1080cd0` 把选中国家对象指针保存在 entry `+c8`。`1082fd0` 取该对象的 `+20` QWORD，保存于 dialog `+210` 并写入 owned action `+40`，同时刷新 primary date。空选择保留无generation的 `---`，没有默认第三国。

`contract.third_selection` 示范私有完整句柄解析；只支持当前玩家作actor，三个国家必须不同slot，查DB有界array并逐项比对当前country+20，重复采样指针及句柄，再核末尾根/date。它没有调用GUI谓词、lazy getter或native preview；36次/264字节，两种私有模型各共享48次/384字节预算。非原子采样不排除同址ABA、异步销毁或恢复世界，模型不提供跨调用保存borrowed指针的许可。

拥有关系已找到实际GUI传递链：`edef60` 将输入action克隆到 dialog `+1c0`；AgreeButton回调 `10a0f48` 跳 dialog虚槽 `+50`，reduce为 `edfa40`，trust为仅跳转到同函数的 `eebc10`。`edfa40` 经 action虚槽 `+40=4e9930` 创建拥有独立clone的 `0x58` command，并把容器交 `14ca210`。原dialog析构 `edf890` 独立销毁其 `+1c0` 原件。此前已审clone字段/command析构锚原样复用；这不是本候选执行过的流程。

需要保留两个区别：reduce GUI刷新调用的是 `action+80(action,text,false)`，不能写成 `+88(NULL,false)`；后者的函数签名和正常调用证据来自已审 `133ea0` AI路径。初始state仍0，不因参数绑定完成就写2。GUI/AI调用者存在也不能证明任意线程、暂停时或脚本/TLS环境可安全调用。

`trace.py --check` 精确比较现有指令字节/虚表槽/字符串，绝不再反汇编。新增解码总19,457字节（上限128KiB），单次≤8KiB，包含所有无用或失败探索：exploration01的351字节地址误标且入口未对齐，只核原始字节，不纳入证据；exploration05两条token字节命中实际是rel32位移，保留但不作为token来源。其它tooltip/UI/Lua支路也完整计入。最高记录分析commit约77MB。没有全程序/巨大文本扫描。

开发期trace自检拒绝过两个人工锚地址拼写和trust对话框的虚槽直接目标假设；随后分别校正到真实指令，以及新增5字节 `eebc10→edfa40` 跳板证据。这些都发生在首次report生成和封存前；没有旧候选改写。

离线复核：

```text
python -B work/candidates/favor-trust-reduce-bindings-1375/trace.py --check
python -B work/candidates/favor-trust-reduce-bindings-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/favor-trust-reduce-bindings-1375 -p test_*.py -v
```

静态绑定完成后，下一实现可让私有核心从已持有并认证的映像读取两个动态DWORD、工厂创建后精确核对其extras；reduce从固定公共TAG经已审country resolver得到当前完整句柄，再核克隆/日期/extra。两个步骤仍要在另行审查的引擎线程、生命周期、原生合法性、持久请求和所有权机制下实现；本候选不新增这些权限，也不改正式API/catalog。
