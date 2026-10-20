# 五类取消动作的私有只读图检查器（1.37.5）

共同作者：Root（初稿）与 native_inventory（布局核对、严格边界、测试和封存）。本候选实现 `cancel_reader.h/.cpp`，只接受注入的 `SyntheticReadPort`，没有 Windows 游戏读句柄、native 调用、发布器或 DLL。可接入 sealed V21 R2 的假引擎取消检查端口；这不是生产接口，也不是取消动作的执行许可。

支持负向 Vassal、Marriage、Improve、Guarantee、Curry。SpyNetwork 明确返回 false，使用独立任务绑定器，不能借这五族的关系指针替代。

| 族 | actor / target 索引 | 关系 vtable RVA | 额外要求 |
|---|---|---|---|
| Vassal | 128 / 128 | 1c81758 | target.overlord 为 actor；definition 必须同时匹配 registry+58 或+60及精确 vassal/client_vassal 名称 |
| Marriage | 68 / 68 | 1c80be0 | 同一对象、双向登记；允许对象保存的双方顺序相反，但输出按请求双方归一，不声称发起国 |
| Improve | 1d0 / 1e8 | 1c81658 | relation+30 指向唯一 matching 2ddb mission；entry 状态1或2 |
| Guarantee | 1a0 / 1a0 | 1c817d8 | 对象+10必须是保证国 actor，+18必须是 target，双边登记不能替代方向 |
| Curry | 158 / 无断言 | 1c7b178 | actor outgoing，relation+30 与唯一 matching 3acc mission 相同，entry状态2 |

所有字段来源见可再生成的 `evidence.json`，含旧报告的原 JSON pointer 和指令字节。Country 自身先核 vt1c574a0/marker165，再读+20完整 handle。country+1480/1488/1490 的 empty 初始化和0/1/2/3 append，第四 manager 的 vt1cac380/marker165/token2746/kind3、非对齐完整 owner+16，entry 自身 vt1cac2f0/marker165/kind3、mission vt1c4b2b8/**marker182** 都分开核对；不能用 mission 的 type 代替 entry 的 type。没有调用任何 getter。

每轮核已知 globals、DB array/count/capacity、指定双方的完整当前对象和普通 current-player handle/date，以及已有 reset/load 零值。角色使用私有 PairStamp；没有 public TAG 到当前对象的 resolver，也不认证其中 process/session/thread/world_witness 值。普通 handle 的三字符、保留字节和上限采用已审 resolver 的**保守研究 profile**，不声称穷尽 EU4 合法 handle 类型。

每个选定关系索引完整读取 counted 16B 项，检查 signed count/capacity、slot范围、slot和object各自唯一；同类关系双边指针必须一致。先核关系类型与 removed==0，才读取双方、日期、派生字段。不会解引用未选中关系对象。Improve/Curry 完整读取最多256个外交官条目；任何未知或矛盾条目都拒绝整个结果，不把它解释为空闲、缺席或可取消。选中 mission 同时绑定 full actor/target、ID、entry 和 relation；其他 mission 仅核当前已知类型、backrefs和保守 handle 形状，不认证第三国对象。父容器和根在轮末重读。

`two_pass` 用同一20,000次/512KiB预算做两次完整读取并比较每个地址、字节与输出；单读最多32KiB，关系索引容量4096，manager池容量256，holder容量16，名字长度128。`recheck` 用新的单轮预算重新读取并与以前完整 transcript 比较。跨多次 V21 callback 没有一个全局累计预算，未来宿主必须另外限制总工作量。

返回 false 包括 unsupported、未知类、缺图、状态不符、变化、预算失败、读异常；不是“已取消”或“关系不存在”。输出参数只在成功时替换，调用者不得在 false 后继续使用旧输出。此函数不维护宿主终止状态，未来宿主应按自己的 fail-stop 合同处理，不能因重试终于相等而恢复 native 权限。

两次或即时相等仍不能排除同值 ABA、对象释放后复用、同址 world 重载或未读字段改变。测试刻意让同值 ABA 通过并标出该限制。原始日期、外交官状态和图链接只构成有界只读前置条件；不能替代 full+88、command gate、truce/cooldown、server/资源检查，也不能证明召回、取消或 AI 接受已发生。

离线检查（明确不给 OS/game reader）：

```powershell
python -B work/candidates/v21-five-cancel-reader-1375/prepare.py --check
python -B work/candidates/v21-five-cancel-reader-1375/validate.py validation-review-new
```

第二命令只在全新输出目录编译实际 `cancel_reader.cpp`、sealed R2 `pair_component.cpp` 和假内存测试；另一个内部预算 EXE include 同份实现来验证精确阈值，未链接外交 DLL。MSVC `/std:c++17 /O2 /W4 /WX /MT /GS /EHsc`，仅自己的编译子进程树受768MiB commit/55秒 Job 限制。正常测试29组，预算边界6组。测试内 R2 Engine 是假对象表，不会解析 RVA 或调用游戏函数。

第一次开发编译仅测试范围 `int -> uint8_t` 的 C4244 警告（/WX）导致失败；源码、对象和日志均保留。第二次28组已通过；随后加入 ordinary handle 保守形状及实际 Reader 的预算边界测试，是新的检查内容，不是重复重跑既有通过构建。最终验证与源hash见 `validation-final/validation.json`；测试成功只证明这份源码在假内存上的合同。
