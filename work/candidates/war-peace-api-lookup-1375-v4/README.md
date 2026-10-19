# 离线 war/peace API 合同索引 v4

本候选复用固定 v1 文件查询引擎和 v3 wrapper 逻辑。保留 v3 的 54 条 JSON 记录原样，新增四条已完整独审的静态端点，共 58 条、59 个选定 JSON 来源。仅 `check`、`catalog`、`search`、`lookup`，没有进程、派发、HTTP 或游戏调用入口。

```powershell
python work/candidates/war-peace-api-lookup-1375-v4/war_peace_lookup.py check
python work/candidates/war-peace-api-lookup-1375-v4/war_peace_lookup.py lookup 0x97b2c0
python work/candidates/war-peace-api-lookup-1375-v4/war_peace_lookup.py lookup 0x97b8a0
python work/candidates/war-peace-api-lookup-1375-v4/war_peace_lookup.py lookup 0x994f00
python work/candidates/war-peace-api-lookup-1375-v4/war_peace_lookup.py lookup 0x1a337f0
python work/candidates/war-peace-api-lookup-1375-v4/war_peace_lookup.py search "v4 已审合同"
```

97b2c0 将选中元素的 DWORD+30 或零写到借用输出指针；97b8a0 收集、筛选或移除原始指针，未证明金额单位或业务类型。994f00 保留 R66 历史合同，并另列 R68 条件上下文：正常返回时固定栈帧可推导，但 GS 派生写可能别名 H/T、保存槽或返回槽，后续 fresh H/T 仍必须读取。1a337f0 的具体寄存器保持并不证明指向内容保持或安全可调用。

全部新记录是静态证据，所有调用、效果、运行时、租约与重试权限恒 false。旧唯一 `real_rawbody_postcondition` 记录仍只表示历史受限 body 实验；没有新增现场效果。`--base` 仅对用户给定基址做有条件 RVA→VA 算术，不认证进程或可调用性。R69、R70 未加入。

候选交付状态为 SOURCE-READY、等待 root 非作者完整审查。每次查询按冻结引擎进行来源前后检查；退出 0 只表示文件查询成功。原 stable observer、v1/v2/v3、48/44/42 与 15 profiles 均未改变。

构建/文件分析预算 24 MiB；最多 7 个首次 v4 查询另限 64 MiB，并按查询双遍来源与 controller 读取分别记账。每个 CLI 使用冻结 Job helper，45 秒、768 MiB、每流 2 MiB。账目是显式文件读取，不是全 OS I/O；不会运行旧 CLI main、旧测试或历史 producer。失败保留并停止，不自动重试。
