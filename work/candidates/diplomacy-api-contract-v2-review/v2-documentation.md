## 可选 Contract/2：只生成请求草稿

显式 `/v2` 与 `--api-version 2` 提供全部 274 项的描述、结构校验和请求草稿。V1 的三个字段、原参数、SQLite 幂等和审计行为不变。V2 不使用 V1 submit、后端、数据库、进程或研究邮箱；它永远不会发送外交动作。

| 方法 | 路由 | 返回 |
| --- | --- | --- |
| GET | `/v2/actions` | 274 项目录和不可执行状态 |
| GET | `/v2/actions/{action_id}` | 参数、旧参数、15 类静态 binding 描述和未决项 |
| POST | `/v2/validate` | 规范 JSON、摘要和结构校验；不是游戏合法性 |
| POST | `/v2/requests` | HTTP 501，保留可用草稿正文、规范 parameters 和 unsupported 原因 |

V2 的请求有且只有四个字段：

```json
{"protocol":"EU4DIPLOMACY-CONTRACT/2","request_id":"maps-draft-1","action":"steal_maps","parameters":{"actor":"FRA","target":"ENG","region_index":0}}
```

仅两项参数迁移：`steal_maps.region_id` 字符串改为 `region_index` 整数 0…2147483647；`support_rebels.rebel_faction_id` 字符串改为 `faction_identity:{low:uint32,high:uint32}`。其余 272 项原参数保持不变。两词身份不是派系指针，也不证明对象存在或寿命。V1 继续接受两个旧参数，V2 不做隐式转换。描述中的 `legacy_parameters` 可直接查看旧形状。

```python
from bridge.diplomacy_api import DiplomacyAPI

v2 = DiplomacyAPI.contract(version=2)  # 不构造 V1，不打开 SQLite
description = v2.describe("subject.scutage")
draft = v2.request({
    "protocol": "EU4DIPLOMACY-CONTRACT/2", "request_id": "scutage-draft-1",
    "action": "subject.scutage", "parameters": {"actor": "FRA", "target": "NAV", "enabled": True}
})
assert draft["status"] == "unsupported" and draft["draft_only"] is True
assert draft["idempotency_scope"] == "not_reserved_contract_only"
```

```powershell
python tools/diplomacy.py --api-version 2 describe steal_maps
python tools/diplomacy.py --api-version 2 validate request-v2.json
python tools/diplomacy.py --api-version 2 request request-v2.json
python tools/serve_diplomacy.py --contract-only
python tools/diplomacy.py --api-version 2 --url http://127.0.0.1:8765 request request-v2.json
```

V2 CLI 仅支持 describe、validate、request，request 返回草稿并以退出码 2 表示不支持执行；不把 preview/submit/status/audit/reconcile 解释成 V2 别名。`--contract-only` 服务只启用 V2，不建立 V1 数据库或探测 executable。默认旧服务仍可使用 V1，并同时提供 V2；启动旧服务本身仍会初始化 V1 数据库。V2 没有 GET 请求状态或审计路由。

`request_id` 在 V2 **不预留**，同 ID 重复或不同内容只产生各自的 unsupported 草稿，不是持久幂等 ACK。`request_written=false`、`queued=false`、`native_called=false`，当前 `native_legality=null`、`native_binding_resolved=false`。desired-state 开关的 current/cancel 保持 null；不会假定 already_desired。不得用草稿摘要作为执行凭据。

V2 正文上限 16 KiB，保留严格 JSON 类型、重复键/未知字段拒绝、深度与节点预算；不接受 RVA、地址、backend、脚本、native state/value/envoy 或进程控制参数。静态证据逐文件有界校验，固定目录与 bindings 不从 HTTP 载入。目录与原生证据尚不完整时仍只提供结构信息，生产可执行动作保持 0。
