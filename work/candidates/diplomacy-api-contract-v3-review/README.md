# 正式 Contract/3 应用候选，仅 staging

本目录准备八项正式应用文件的完整 staging 副本、明确 patch 和应用清单；原 bridge/tools/docs 及所有封存来源未修改。`files/` 其余文件是未改的有界 pinned dependency 副本，用于隔离验证。后续仅能在独立复核后应用 application-manifest.json 列明的八项文件，本候选不执行该步骤。

新正式协议为 `EU4DIPLOMACY-CONTRACT/3`，envelope 使用 protocol/request_id/action/parameters，不接受 TenFamiliesDraft/2 的 contract/action_id。工厂 `DiplomacyAPI.contract(version=3)` 复用 verified V2 的 274 项目录、已有 typed 描述、严格 JSON/canonical snapshot 和预算，额外固定 pin 十族 R2 contract、source-index、private static index、作者 report/review 和独立复核。文件验证不认证游戏进程、session、world 或原生权限；所有 274 项请求仍 unsupported，backend 数量和生产可执行数量为零。

十族 V3 参数应用与已封 Draft/2 一致；相对 V2 有四项明确不兼容迁移：sell price(number)→price_integer(整数金币 0..2147483)；enforce war_id/defender→opposing_country(TAG)；threaten 必须显式 taker_country==actor；trust 删除 favors，仅双方 TAG 的一步原生工厂 intent。旧字段拒绝，不暗丢、舍入、默填 10/5 或补 actor。actor/target 必须不同；opposing_country、third_country 必须不同于双方。所有这些仅是静态形状/语法约束。

trust 公开 metadata 只说明 NDiplomacy 两个 native loaded signed int32 define key 来源、cost×1000 和整数 trust points，current_values=null。reduce 公开输入仍 third_country TAG，未来 private resolver 需从已认证 loaded country registry 取得当前完整国家身份；当前未实现 live TAG 解析。十族 public describe/symbolic 不展示可执行 RVA/pointer/full handle/native 控制字段，输入也拒绝这些字段。旧 V2 typed metadata 对其余族保持原样。

新增 HTTP GET /v3/actions、GET /v3/actions/<action>、POST /v3/validate 和 POST /v3/requests。501 响应仍携带可用 unsupported 草案。V3 路由只在 loopback binding 可用，沿用 Host/Origin/Bearer 和固定 16 KiB/深度/节点预算，不添加 submit/preview/status/audit/reconcile 别名。V1/V2 原路由及参数保持原义。

实际外交 CLI 是 tools/diplomacy.py，新增 --api-version 3，只允许 describe/validate/request。tools/serve_diplomacy.py --api-version 3 自动 contract-only、仅 loopback；不构造 V1、不读取 executable/local configuration、不打开 SQLite、不允许 remote/catalog/queue-db 选项。旧无版本 serve 和 --contract-only 调用方式保留，旧默认 durable V1 启动仍按原设计使用数据库。V1 回归测试的 SQLite 仅存在临时 synthetic fixture；V3 的零副作用另用 connect/V1-init/Popen 拒绝桩验证。

```powershell
python -B work/candidates/diplomacy-api-contract-v3-review/prepare.py --check
# 以下命令的 cwd 为本目录 files/
python -B -m unittest bridge.tests.test_diplomacy_api bridge.tests.test_diplomacy_reconciliation bridge.tests.test_diplomacy_contract_v2 -v
python -B -m unittest bridge.tests.test_diplomacy_contract_v3 -v
```

相关原回归为 20+15+15=50 项，新增 V3 为 12 项，包括真实 loopback HTTP、真实 CLI/serve 子进程、四项 legacy 拒绝、严格 bool/float/subclass/duplicate/unknown-key、跨字段 distinct/taker、274 项 canonical unsupported/noSQLite 草案、固定来源 tamper 拒绝以及 report 不提升 runtime readiness。所有精确测试子进程和 HTTP 线程在结束前收齐；单命令限 55 秒、768 MiB guard。无游戏/目标进程读取、新 PE 解码、原生调用、编译、DLL 或正式应用。
