# 固定 FRA→NAV 属国开关：原始只读候选

本目录仅观察 `embargo_rivals`、`scutage`、`divert_trade` 的注册、类型允许表和当前原始字段。没有游戏采样、原生调用、DLL、命令创建或发布。`capture(reader,base)` 只调用注入 reader 的 `read`；`sample_process(pid,creation,executable)` 是未来显式 RO 入口，没有 CLI。本轮所有操作系统入口均被 mock。

静态输入为已独立审查的三家族合同、military-focus 原始图观察器，以及精确 1.37.5 的41交互注册清单。`prepare.py` 只从固定 SHA 报告构建 `contract.json`，没有新增反汇编。每个继承依赖/本候选源码及完整 EXE 被 source-index 记录；旧文件不修改。

## 读取与类型合同

- 继承 `subject-military-focus-observer-1375` 的完整 FRA/NAV handle、真实 DB count、当前 FRA 玩家、date/load排除字段、宗主向量、双边 dependency 索引、已知 relation/definition vtable、name/index/self 和 definition registry 精确名字查找。缺项或相互矛盾拒绝。NAV 不属于 FRA 且图一致时输出显式 outside scope，不读取任何新 singleton/permission map。
- global `1fd5228` 为 DWORD entry_count，`1fd522c` 为 DWORD bucket_count，`1fd5230` 为桶指针；`23581c8/1d0/1d8` 是枚举 vector 的 begin/end/capacity，注册函数 `81ee0/820f0/82720` 的 append/capacity 比较被钉扎。向量只能含已静态列出的41单例，指针唯一且与 entry_count 一致；这是保守支持范围，不猜动态/未知单例。
- 三目标单例 live 地址必须为固定 module RVA，vtable 必须为最终家族类，token 匹配，`+c=1/+d=0`。不把磁盘初始基类 vtable 当已注册。对 token % bucket_count 的选中链遍历至 null，node+0 为借用 singleton、+8为next；每个碰撞对象先核已知地址/vtable再读 token。重复、环、错桶、未完整关闭或选中项缺失拒绝。没有调用 `af41b0`。
- definition 的 map 基址 +468，sentinel+470、size+478、vector+480/+488/+490、mask+498、bucket_count+4a0。bucket_count 是 <=4096 的2次幂，mask=count−1，vector 需要 count×16 字节。FNV-1a 对四字节小端 token 先 xor 再乘。只解引用三项所在桶，从 last 沿 previous 到 first，核 reciprocal next、全部 token 已知且唯一、桶一致、allowed BYTE严格0/1。重合桶的节点内容必须相同；总选中节点不超过 size。
- 空桶/查无所选 token 与 found=true/allowed=0 分开输出；都只能表示原始表 lookup 为 false。非标准非零 bool、未知 key、部分链不伪装成 false。未解引用其他桶的节点。读取全桶指针数组用于完整 vector 边界与选中端点绑定。
- 原始字段是 NAV DWORD+78、FRA DWORD+1344/BYTE+26/DWORD+2258、NAV BYTE+289b。current 来自已核完整宗主 handle 高字节和 masks2/16/64；`family_local_condition` 只反映三项专用局部谓词，不包含 actor/common/type/TLS/visibility/full gate。状态不是命令参数，也不授权调用。

两遍完整 snapshot 共用16MiB、8192次读取预算，每读最多64KiB；注册向量最大256（当前白名单41）、权限表最多4096项/4096桶，每选中链最多256。每遍末尾重读 roots，前后核继承和新增机器指令与重定位 vtable pins；完整 canonical typed state 必须一致。输出保留两份完整 passes、对应 snapshot 和每读地址/长度/SHA，不保留原始字节。

`inspect` 严格核所有嵌套形状、整数类型（拒 bool/float）、计数、地址、hash/方向和派生状态。`validated_report` 重算两遍与存储摘要一致，拒绝额外字段和任何授权标志；它仍不能认证导入 JSON 的来源或内存内容。真实取样以后必须另由调用者封存原始报告 SHA。

## 持有身份与边界

未来 `sample_process` 只使用 legacy `PROCESS_QUERY_INFORMATION | PROCESS_VM_READ` reader。打开前核精确 EXE 路径、完整磁盘 SHA、PE；同一 handle 前后核 PID、16位 lowercase creation FILETIME、未退出和 module base，采样后再次核 PE、磁盘 SHA并 finally close。整份采样和 PE读取总量受16MiB限额。没有扫描进程、自动挑选 PID 或 active/latest 文件。

选择指令 pins与磁盘 SHA不等于完整加载映像哈希；双遍相同不证明原子性、ABA/对象寿命、暂停、world epoch、严格单机、TLS或引擎线程权限。所有 `FALSE_CLAIMS` 恒 false。枚举权限和visibility仍为 unsupported，未调用 getter、lazy initializer、command gate/clone/constructor。

副作用没有被补造：embargo 逐 rival 的 gate/效果、scutage off 的另一 modifier 容器与名称/期限、divert off 可能恢复的50%关系均未观察。`compare_snapshots` 只接受同日且完整图/注册/类型表/门槛一致的 selected raw-bit差异；另外报告其他 flag bits 的变化，效果/因果/完整回滚仍为 false。初末状态相同也不能证明中间开关都发生。

## 离线验证

```powershell
python -B work/candidates/subject-toggle-observer-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/subject-toggle-observer-1375 -p test_observer.py -v
```

27个 sparse/mock methods 覆盖注册链、精确最终 vtable/flags、权限空表/缺项/allowed0、碰撞/环/重复/错桶/截断、未知对象短路、全部新整数字段 bool/float替换、两完整 passes与存储摘要、ASLR、同日比较、读预算、mock持有身份失败和finally close。第一轮25 methods已通过，新增2项仅覆盖比较函数；完整封版验证另保留记录。没有执行实际 process reader。
