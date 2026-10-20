# 独立方向关系只读观察候选

本目录只准备新观察器，未访问游戏、投递请求、修改原有观察器或冻结的 v14 support/host/native。不会注册后端、添加实际效果能力或升级任何旧实验。`runtime_verified=false`、`production_ready=false`。

入口是本目录 `observer.py`。它复用按 SHA 固定的 v10 关系读取器，加上协议动作到原生 family/角色的严格映射、必需的 PID/creation 绑定和固定补贴参数。它可以供后续 v14 研究的前后只读取样使用，但不读取 DLL/邮箱、不验证当前研究宿主、单人来源、世界代次、暂停或请求因果。固定构建仍是本机 1.37.5 / SHA `9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A`。

## 十个选定协议方向

| 协议 ID | 原生 family / mode | 选定关系角色 |
|---|---|---|
| `dissolve_alliance` | allianceaction / false | 双方对称，不能识别发起者 |
| `cancel_military_access` | milaccess / false | FRA 持有、target 授予 |
| `revoke_military_access` | offermilaccess / false | target 持有、FRA 授予 |
| `offer_fleet_basing_rights` | offer_fleet_access / true | target 持有、FRA 授予 |
| `cancel_fleet_basing_rights` | fleet_access / false | FRA 持有、target 授予 |
| `revoke_fleet_basing_rights` | offer_fleet_access / false | target 持有、FRA 授予 |
| `embargo` / `revoke_embargo` | embargoaction / true / false | FRA 对 target 的 outgoing bit |
| `give_subsidies` / `cancel_subsidies` | warsubsidy / true / false | FRA 付款、target 收款；每月1000 milli、10年 |

actor 固定 FRA，target 只允许 ENG/POR/NAV/FOI 的已核完整句柄。这里的十项是静态可观察方向，不是十项已验收效果。没有另行接受 `cancel_alliance`、`expel_*` 等自由别名；使用实际协议 ID。未包含动作的 `describe` 明确 `unsupported`，`sample` 在打开进程前拒绝。

## 角色与消费者证据

`evidence-contract.json` SHA `fb1e47ca36655a1ef371e8ef5e85ae7bd77de0e747c50a19cf06d787de8307a7`，固定9个依赖文件（3,308,170B）、8项静态事实及134条原指令锚点。来源是既有静态报告，不是本轮运行证明：

- `native-pair-extension-effects-v10-1375.json` SHA `b6f4b69db38f5e3eae0c3cebf1fa5298701b86a98e8299d6f0e9759b84861f62`。
- `native-pair-extension-v10-1375.json` SHA `0c1731b0b29b296da73dc406fb31544ada59c17c275d17d623677b16998698bd`。

军事对象 `+10` 为持有方、`+18` 为授予方；生产路径 `5243d9` 和 `5352ca` 的 ask/offer 赋值相反。注册消费者 `a70270` 将同一对象写入持有方 b0/bc、授予方 c8/d4；解除 `a70310` 清两边。停泊对应 `52db58/531f66`、注册 `a70760`、解除 `a70840`，索引是持有方 e0/ec、授予方 f8/104。这些角色来自生产和注册/解除路径，不从 proposal order 推导 provider。

同盟在双方80/8c索引里保持同一个对象，解除 `a5d790` 清两侧。补贴双方共享110/11c索引，但对象 `+10/+18` 固定付款/收款，`+40/+44` 是金额/年数；`547979/5479ba→a697a0` 写入，`a62f80` 取消并清两边。来向补贴不能充当 FRA 付款关系。禁运只读取 FRA 的 counterpart record `+46 & 2`，不把来向禁运、dirty bit 或停战当成禁运。

通行对象 `+40` 是 `enforce_peace`，必须为0才支持普通外交协议的效果比较。条件通行规则是另一条计算路径；没有选定对象不代表不能移动。

## 观察与比较的保守条件

独立审查发现旧候选 `8458a31e…9ce44b` 的导入报告校验仅检查第一遍，且 Python 对象相等会将 `False`、`0`、`0.0` 等视为相等。该版本全部七个文件及原验证记录已逐字节归档到 `archive-8458a31e/`；原 `validation-results.json` 保留为历史，不能代表修复后的源码。当前验证记录是 `validation-strict-two-pass.json`。冻结的旧读取器及其九项依赖未修改。

新候选逐遍重新执行完整字段检查，再用保留 JSON 类型的规范序列化比较两遍完整数据，以及逐遍重建状态与存储状态；布尔、整数、浮点数不能互相替代。非法第二遍、两遍同样非法、仅篡改存储状态均返回 unknown。23 项离线测试保留40项动作/目标成功组合，并增加21项逐遍数字类型反例、6项存储状态反例、3项未解释字段类型反例以及非 JSON 容器/atomic 伪声明拒绝。此修复尚未用于读取游戏。

取样只使用 `QUERY_INFORMATION | VM_READ`，先校验完整磁盘 EXE SHA及已加载模块 PE 身份，再用持有句柄核对显式 PID/creation；两次完整读取必须一致，前后还核对日期、世界根、玩家和完整国家句柄。对象必须在双方正确索引中唯一出现，并且指针、虚表、type marker、完整方向、起始日期及未移除标志一致。最大单次读取1MiB、总读取16MiB、每索引4096条；不扫描heap、外交官或任务列表。

新增模式只接受 absent→active，取消只接受 active→absent。全部比较要求同一 raw date，来排除已知跨日推进造成的混淆，但这不证明游戏暂停或排除其他同日原因。补贴固定1000/10，正向核对after，取消核对before，且必须尚未名义到期；外部不能传入金额、期限、family或方向来适配观察结果。禁运对比还要求 opposite bit 不变。关系缺失、错误索引、反向对象、enforce-peace、未完成读取或不稳定快照均保持 unknown，不能当成拒绝或成功取消。

CLI会先核对候选合同与旧读取器的固定依赖。输出只允许新的 `.json` 文件，使用 CreateNew，不覆盖旧证据。比较输出绑定两个输入的完整SHA。选定状态变化仍不证明AI接受、request-ID因果、严格单人来源、可靠world epoch或完整世界不变。内层 `family_snapshot` 保留旧读取器的原始结构，外层候选profile不能混入已有v10/v11或能力历史。

## 供主任务后续使用的命令

本轮只执行下面的 `describe` 和 synthetic tests；没有执行 `sample`。

```text
python work/candidates/directional-pair-observer-1375/observer.py describe --action offer_fleet_basing_rights
python -m unittest discover -s work/candidates/directional-pair-observer-1375 -p test_observer.py -v
```

后续取样必须明确提供当前 PID 和小写16位 creation；取消动作的before/after都使用同一个取消协议 ID，不能先用ask快照再改名成revoke：

```text
python work/candidates/directional-pair-observer-1375/observer.py sample --pid <PID> --creation <creation> --target POR --action revoke_fleet_basing_rights --output work/runtime/fleet-revoke-before.json
python work/candidates/directional-pair-observer-1375/observer.py sample --pid <PID> --creation <creation> --target POR --action revoke_fleet_basing_rights --output work/runtime/fleet-revoke-after.json
python work/candidates/directional-pair-observer-1375/observer.py compare --before work/runtime/fleet-revoke-before.json --after work/runtime/fleet-revoke-after.json --output work/runtime/fleet-revoke-comparison.json
```

取样不会发送取消，也不会执行任何 native 函数。实际请求、最新暂停/健康帧与所有权守卫仍由独立研究流程处理。
