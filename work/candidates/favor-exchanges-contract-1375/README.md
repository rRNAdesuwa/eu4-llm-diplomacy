# 人情交换六族：1.37.5 有界静态合同

本候选只分析精确 SHA256 `9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A` 的磁盘 PE。无进程读取、引擎调用、DLL、发送器、原始内存观察器或正式目录改动。`contract.py` 是离线类型、布局和归属模型，不是可执行 ABI 适配器。所有 native/runtime/effect/production 验证标记保持 false。

| 动作 | token | vtable RVA | 大小 | 对象扩展 |
|---|---:|---:|---:|---|
| reduce_relations_favor | 3bcd | 1c7e828 | 0x48/72 字节 | +40 第三国完整 QWORD handle；正常选择调用者未闭合 |
| trade_favors_for_gold | 3bce | 1c80980 | 0x40/64 字节 | 无自由金额参数 |
| trade_favors_for_men | 3bcf | 1c80ff0 | 0x40/64 字节 | 无自由人力参数 |
| trade_favors_for_sailors | 3bd0 | 1c81250 | 0x40/64 字节 | 无自由水手参数 |
| trade_favors_for_trust | 3bd3 | 1c80c60 | 0x48/72 字节 | +40 DWORD 人情千分值；+44 DWORD 整数信任 |
| trade_favors_for_war_prep | 3bd4 | 1c80ec0 | 0x40/64 字节 | 无额外参数 |

## 真正闭合的正常调用链

普通 AI 函数 `133ea0` 将 `1dc23c0/1dc23b0` 两个常量块和尾项 `3bcb` 组成九项 token 数组，其中包括本次全部六族。它经 `35a8f0` 选择后调用 `35d210(token,0)`，写 actor/currentActor/recipient 三个完整句柄，调用 +e0 setter(true)，写 +28 当前日期，再分别调用 +80(NULL,false) 和 +88(NULL,false)。评分较高的候选才交给 `129b60`，后者通过虚槽 +40 的 `4e9930` 生成拥有式命令并转移到 AI owner+a68。原件随后正常析构。这条链是真实普通 AI 源证据，不是当前游戏已执行记录。

工厂分支也已单独闭合：token 高分支用 `token-0x3b85` 索引 `360768` 的 byte table，再索引 `36073c` DWORD table。`trace.py` 重读六组表项，并逐一验证实际分支与 vtable。不能依据同大小猜函数。

通用默认是 marker 0x165、三个无效代际 `---` 句柄、envoy=-1、state=0、value=true、flag=0、id=0，两个日期都是工厂常量 `0x29c77f8`。**普通 AI 此处只写 +28；不能声称原件 +2c 已是当前日期。** 各族 clone 用源 +28 初始化两个日期、清 +39；wrapper 再将 clone +2c 改为当前世界日期。0x58 命令 +50 拥有 clone，原件独立。`4e7470` 通过 clone 的虚析构清理它，随后释放命令。异常后的归属和引擎 cleanup 未经实验，模型只允许终止，不能猜测释放或重试。

“降低关系”仍有实质缺口：共同 AI 枚举创建的 +40 保持无效第三国。评分 `557aa0 → 5575b0` 先检查第三国代际字节，零代际直接返回 0。不能把 token 出现在列表里提升成“完整参数化正常发送已闭合”。其 QWORD 序列化、clone、接收效果可以独立说明；真正的 UI/专用 AI 第三国选择还不支持。未将邻近 `557c80` 的另类析构误认为此动作的新虚槽。

## 参数与效果方向

金币、人力、水手均由专用 helper 动态计算额度。金币读取接收国收入分类；人力和水手结合双方相应生成量与配置月份。这里未把这些 getter 当作安全只读函数，也没有暴露外部金额字段。接受分支从 **接收国持有的 actor 关系记录** 扣人情；接收国资源减少、actor 资源增加。人力最终 setter 写 country+db8，水手写 +dc0，但 setter 自身还可能写日志/全局状态，故绝不能用于 RO 采样。最小未来观察器必须直接读两国已验证字段和接收国到 actor 的关系，另关联正常回复；单个数量变化不证明此次请求因果。

信任工厂从 live global `233db7c * 1000` 填 +40，从 `233db80` 填 +44。前者序列化 favor token32c9 为固定小数；后者 trust token32d5 为整数。stock defines 的 10/5 只作为配置上下文，尚未追 define 注册，不能硬当当前内存值。接受分支消费 recipient+1510[actorSlot*0x48]+20 的人情，修改**同一方向**的 BYTE+1e 信任，限制到 0..100。信任并非 actor 对 recipient 的相反方向关系。它与其他五族不同：+f0 getter 为 true，既有 command response 分支因此可把回复 clone state 设为 2；这是有条件的内部回复逻辑，不准 API 强写接受状态。

备战接受路径扣人情后调用 `3e1ad0(recipient, actorFullHandle)`，写 recipient DWORD+2728 到期日期及非对齐 QWORD+272c 的 actor handle。关系/战争/联盟/脚本门槛仍由原生检查决定，不承诺必定开战。

降低关系接受路径对 recipient 关于第三国添加 registry `233ff08 + d48` 所指 opinion modifier；费用仍来自 recipient 对 actor 的人情。modifier 的 live definition 名称、期限、唯一关系图以及真实第三国选择调用者尚待关闭，不猜固定减值。

所有完整 +88 预览都调用通用 `4e9d00`，它和本族 +80、命令 +40 gate、+48 execute 必须区分。正常 AI 为 +80/+88 明确给 NULL sink 与 false 模式；这不证明传递调用没有脚本、缓存、TLS 副作用，也不证明任意线程可调用。局部预览 false / command gate false 是拒绝结果，不是 cancel。state=0/1/2 分别是 pending/refused/accepted 分支，拒绝也可能改冷却或关系，不能只用冷却当接受证据。

## 证据预算与未采用探索

新增 40,585 解码字节，含重复前缀、未采用邻族、一次解释器未处理 `ja` 的失败探索；每个 CFG/窗口 ≤8KiB，总预算48KiB。重用证据逐字节再核原 PE，未重扫全程序。有限 AI 搜索只检查 0x120000..0x140000 的 E8 相对目标候选，唯一 `133fa3` 后以有界正常函数确认。首次 pdata fragment133eff 与后续完整133ea0 都保留；金额/文本相邻函数也没有从预算删除。

历史 exploration-12 的累计字段漏计了早先失败的111字节。报告用所有文件的 `new_this_file` 重算为40,585，保留原始历史数值并明确纠正；后续 explorer 已将该额外计数纳入。exploration-11 解释器走到间接表就停止，没有假称完成动态解释；六项实际表值由 trace 精确读取并断言。全部事实有 `facts.json` anchors，全部函数保存 source JSON pointer。

下一步可先设计人力、水手、备战的独立无发送生命周期→本族完整预览→拥有式命令实验，忠实保留 factory 默认 pending/true/-1。信任另记录两种单位及 live 默认。降低关系必须先补正常第三国选择，不并入同一可执行门槛。仍缺严格世界世代/单人来源/线程/暂停/配置同一性、全部传递脚本副作用、真实执行和保存重载证明。

## 离线复核

运行 `python -B trace.py --check`、`python -B -m unittest discover -s <此目录> -p test_*.py -v`、`python -B prepare.py --check`。它们只读磁盘证据与纯模型；不加载任何游戏 DLL或进程。`validate.py` 将命令、exit、stdout 和输入前后 SHA 封存在新的 validation-results 子目录；最终 review 不覆盖旧记录。
