# 五核心 normal full88 与外交官 entry 类型补证

此候选只补静态证据和 typed record 模型，不读取进程，不含 native adapter、DLL、发送器或权限判定。没有修改 V17、V19、V21 或任何已封存文件。

五族 `vassalaction / royal_marriage / improve_relation / guaranteeaction / spy_network` 都有普通 AI 双模式路径：`12b860` 根据 proposal token 构造局部 action，原始第三参数 R8B 表示取消。正向保留 value1，取消前四族直接写 value0；spy 取消在完整国家身份设置后调用 void `586330`，由该函数解析已有外交官 ID，未找到可能仍为 -1。五族 actor/original 来自 proposal+0，target 来自 proposal+8，两日期同 game+1dd0，state0、flag0、id0。婚姻另有 String32 空 SSO 与 force=false。

这些局部 action 到共同 `129b60`：经过 AI 分数等前提后，`129d98/129d9b` 清 R8D/EDX，`129da0` 调真实 action virtual+88(NULL,false)，拒绝就退出；其后 `129db9` 还会单独调用 +80，并执行其他虚槽/AI 条件。满足后 `12a6e3` 调 +40 wrapper，`12a6f2..12a6fb` 将返回容器中的 command 移到 AI owner+a68 并清临时指针。不能将 +80、generic4e9d00 或这个结构性路线称为无条件允许。

`4e9930` 调 +b0 创建独立 clone，更新 clone+2c 为当前日期，创建 0x58 command，将 clone 放 +50。`4e7470` 先查 clone virtual+a8；本五族 slot 均为 `8f450` (false)，因而正常 deleting destructor 路径调用 clone virtual0(flags1)，再销毁 command 自有字符串，按 flags&1 释放 0x58。该结论有 35 个精确 vtable slot pins。

**原件的存储不能误写成堆对象。** 普通 AI 原件是栈局部；四个简单族在共同返回处释放栈，婚姻在调用返回后按 String32 capacity 清理自有堆缓冲。此链没有“删除独立堆原件”的调用者证据，也不授权对损坏或未知对象调用析构。

Spy entry 类型不是从 mission 类猜出：国家构造 `2cb745..2cb818` 创建 token2746、kind3、owner=country+20 的 manager，并作为 country+1480 指针向量第四项追加。`586384/586395` 的取消 setter 选择同一个第四 manager；它的 `6fec80` 分配 0x48 entry，将 manager+14 kind 传 R8B、向量序号传 R9D，调用 `6ff4e0`，写 vt1cac2f0、marker165、kind+40、ID+44。manager 自身是 vt1cac380、marker165、token+10、kind+14、非对齐 owner+16、vector+20/+28/+30。类型先读 vtable，再读 marker/kind；未知类型不得先读派生字段。entry 的 marker165 与 mission 的 marker182 不可混用。该资料足以构建未来保守的已知类型检查，不证明当前内存对象仍活着或未知子类不存在。

`report.json` 每条指令保留原 source 和 JSON pointer。除原 CFG 未跟进的两项 jump-table 分支外，全部复用已封存记录。`exploration-01.json` 包括完整两段各147B，共294B新增解码，以及7项 table 原始字节；没有未采用的新解码。每函数/范围≤8KiB、总预算32KiB，内存检查768MiB。`trace.py --check` 只重放字节、验证 exact EXE SHA、seek 核指令及 data pins，不重复解码。`explore.py` 是一次探索命令，已有输出时拒绝覆盖。

`contract.py` 仅验证注入的 typed record，不是 raw sampler、注册表或完整身份认证；所有 profile 保持 native_ready/runtime_verified/production_ready=false。没有提升正式 catalog 或后端能力。未知 live 对象来源、loaded definitions、TLS/DLC、同时替换、epoch、strict SP 与 lifetime lock 仍无证明。

离线验证：

```powershell
python -B work/candidates/core-five-full88-and-spy-entry-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/core-five-full88-and-spy-entry-1375 -p test_*.py -v
```

初稿报告曾将 4e7450 错称为清理辅助；在封版前直接复核既有指令已纠正。初稿原字节保留 `preimages/report-draft-01.json`，不属于有效最终合同。没有新增相应解码。

首次纯测试的未知类型 Trap 只覆写 get 却未提供对应字典键，导致测试假对象 KeyError；已仅补入其声称存在的未知 vtable 键，原测试和失败输出保留。生产合同未因此放宽；最终验证使用新 `validation-final` 目录，全部命令与输入前后字节保留。
