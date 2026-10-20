# 五类间谍费用 dense 数组的只读增量合同

本目录只补齐费用计算的数据表示，不改变旧 `spy-modifier-observer-1375`。没有进程打开器、实际采样 CLI、游戏调用、DLL、注入或发送接口。`dense_ro.capture(reader, base, actor, family)` 是由调用者提供只读 reader 的局部 kernel；目前只用稀疏模拟内存验证。全部运行、原生许可、合法性、实际费用和效果声明保持 false。

精确映像为 1.37.5、SHA `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。`trace.py` 重用已封五类动作和观察器的 CFG，并只新增六个函数、6,850 字节；单个 CFG 窗口 8 KiB、总新增预算 16 KiB。报告逐指令核对 EXE 原始字节。构造与重算函数仅作为磁盘证据，绝不实际调用。

## 已闭合的数据链

| 字段 | 类型/含义 | 直接证据 |
|---|---|---|
| country+28c8 | DWORD cache state；本 kernel 只接收 2 | 93d130：93d51f 写 1、93d5f9 写 2；既有 93d750 |
| country+28d0 | aggregate；首 QWORD vtable=base+1c42770 | 939ef0 与 8e6120 |
| aggregate+8 / +10 | DWORD type=165 / BYTE dense=1 | 8e6122、8e6129、93ad00 |
| aggregate+50 | vector vtable=base+1c37fa0 | 8e6139、8e6160 |
| aggregate+58 / +60 / +64 | QWORD data / DWORD capacity / DWORD count | 8e6164..6f；1b2370 |
| data+index*8 | DWORD id、signed DWORD value | 1b23e4..f4；93d6c8..d2 |
| index=261 的 value | data+130c | 4ea66c、4ea670 |
| base+2358080 → +e4a0 | 全局 transform 对象指针 | 4ea6a4..ca；非空会调用虚槽 +8 |

构造尾部 `939ef0→8e6190→1b2370` 把 dense 数组初始 count 设为 **0x287=647**，每项填 **{id=0x286, value=0}**。因此未设置的 dense 项，其 id **不等于自身下标**。`93d130` 的一个已核写入例子将 index `0xd5` 的 id 写为 `0xd5`、value 写为 1000；它不是所有写者的完整清单。

`1b2370` 把 count 更新为所请求的长度；不足 capacity 时，以 `max(2*capacity, requested)*8` 分配并经 `94030` 替换 storage。本研究不调用分配器，也不把 root 转述的实测 count=694 视为固定规格或自己采样所得。只要 `610 <= count <= capacity <= 4096`，选中项就在已声明的有效跨度内。除 8 字节选中记录外不遍历整个 dense 数组。

费用函数的 dense 分支忽略 record id，直接取 index261 的 value。本 kernel 有意采用更窄的可解释集合：接受 `id=261`，或构造的原始空项 `id=286,value=0`；其他组合标为 unsupported，不推测其来源。它并未证明未知 id 对应的非零值一定无效。

## 投影与拒绝边界

五个 family 的 base cost RVA 从已封观察器报告取得；调用者不能传入任意 RVA 或金额。`cache_state==2`、精确 aggregate/vector 类型、dense==1、非空 transform root 且 transform==null、合法数组界限，以及局部前后两遍完全相同，才能输出：

`base_milli * (1000 + modifier_milli) // 1000`

只接收 base `0..21474831`、modifier `-1000..1000000`，最终费用也须在 base 的范围内。此区间乘积非负，Python 整除与原生有符号除以 1000 的截断方向一致；范围外返回 unsupported，避免模拟溢出或负费用。空 transform root 不等于“没有变换”，必须 unknown；非空 transform 不解引用、不执行。

未知 cache state、vtable、类型、dense 值和 vector bounds 都在读取相应后续对象前停止。稀疏存储留给旧观察器，不在此重复实现。代码与虚槽 pins 是局部篡改检测，不能替代完整进程/映像验证。reader 必须返回精确长度 bytes；最多 8 KiB、256 次读取、单次 64 字节。固定 family 及整数/指针均严格检查，bool 和 float 不充作地址。

## 尚不能由本 kernel 证明的前提

未来独立版本的完整观察器须把此 kernel 放在已有的 held PID creation、磁盘 EXE SHA、加载模块路径/PE/代码验证、完整玩家与目标 handle、DB 索引边界、国家对象、日期和世界根的前后验证之间；还须保留 actor→target spy network 的完整 owner/counterpart 方向核对。此 kernel 不读取这些身份字段，也不会伪称已验证。它没有打开游戏的入口，不能单独成为 live observer。

`93d750` 有线程关联状态与诊断 fallback；`93d130` 会重建缓存、写 TLS，并通过函数指针表运行其他逻辑。状态 2 或暂停不证明缓存新鲜、引擎线程同步、对象存活或所有相关 writer 均已停止。两遍相同只证明所读字节相同，不能排除中途写入后恢复。费用投影也不证明真正动作的可用性、外交官、能力字节、目标解析、费用实际扣除或请求因果。

下一步的动态前置工作应是新观察器版本整合并独立审查上述完整身份外壳，再显式获准对固定样本做纯 RO；本候选不修改旧版本、不自动升级能力、不授权该步骤。

## 复现

在仓库运行：

```text
python -B work/candidates/spy-dense-aggregate-contract-1375/trace.py --check
python -B work/candidates/spy-dense-aggregate-contract-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/spy-dense-aggregate-contract-1375 -p test_*.py -v
```

测试覆盖默认 sentinel、带符号值与取整、五个固定 family、610/647/694/4096 长度、短数组/过量/空指针/溢出、未知类型与 transform 不继续读取、双遍变化、严格类型、代码 pin、返回类型和预算。mock 不是引擎 ABI、实际内存或缓存生命周期证明。
