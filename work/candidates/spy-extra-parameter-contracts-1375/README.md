# 剩余间谍参数：精确 1.37.5 静态合同候选

当前最小可推进对象是正向 `stealmap`，但本目录不提供原生调用器或实际只读生产者。支持叛军的派系寿命和正常拥有式发送调用者仍未闭合；“窃取科技”没有查得可直接开放的独立原生 family。全部 runtime / execution / effect / production 标志均为 false。

| 路径 | token / vtable RVA | 分配 / 派生字段 | 本轮边界 |
|---|---|---|---|
| stealmap | 0x33c8 / 0x1c7d108 | 0x48；+0x40 signed DWORD 区域索引 | 正常 AI 到 full-preview、wrapper 和拥有式队列已闭合；区域身份、实际效果观察未闭合 |
| support_rebels | 0x2dde / 0x1c7c248 | 0x48；+0x40 QWORD 借用派系 | 工厂、clone、序列化、效果已见；只见 GUI 栈上 local-preview，未闭合正常拥有式提交 |
| scriptable_diplomatic_action | 0x3662 / 0x1ce1e28 | 0x48；+0x40 QWORD 借用脚本定义 | 正常 AI 构造与拥有式队列已见；动态条件、已加载定义和寿命仍未知；不能等同窃取科技 |

## 对象与公共命令

三个分配大小分别由指令确认，不能由大小相同推导参数相同。公共字段为 marker +8，完整 actor/controller/target handles +10/+18/+20，日期 +28/+2c，envoy +30，state +34，value/flag +38/+39，id +3c。普通正向调用者使用当前日期、envoy=-1、state=0、value=true、flag=0；+40 则必须按 family 设置。地图默认 -1 只是通用候选预览，不能当作已选区域。

三条 clone 都把源 **primary date +28** 复制到克隆的两个日期字段；不能假设 source secondary date 原样复制。wrapper `0x4e9930(action, command**)` 再将克隆 +2c 改为当前 GAME+1dd0，分配 0x58 command，把克隆存入 +50。原件与克隆分别拥有；正常 command 析构先检查 action+a8=false，再通过 action 的删除析构释放克隆。三个 action 的删除析构 `0x129500` 只释放 0x48 action 本身，**不释放借用的派系或定义**。异常中的部分对象归属没有由这份静态合同证明，不能继续猜析构或重试。

`action+0x80` 局部检查、`action+0x88` 完整检查和 `command+0x40` 冷却 gate 必须分开。正常 AI `0x129b60` 使用 `+88(action,NULL,false)`，随后局部 +80；满足其评分和其他条件才调用 wrapper，将 command 移交 AI+0xa68，清空临时拥有者。这证明普通拥有式排队，**不是 context_submit 或玩家权限、严格单机、线程同步证明**。full preview 可涉及 TLS、脚本或 lazy 状态，暂停不能证明其无副作用。

## 地图：最小下一项

正常 helper `0x13aa00` 在栈上完整初始化，选择目标完整 handle 和区域索引，走局部检查/筛选/评分后调用上述公共 AI 路径。工厂 `0x35f04b`、clone `0x57f3e0`、local `0x57f0d0`、full `0x57f290`、effect `0x57ef00`、序列化 `0x54ee00/40` 均已逐指令绑定。序列化字段 token=0x2a4e。

区域源为 `*(base+0x233fed8)` 的 +4f0/+4f8 指针向量；区域 +a0/+a8 是省份索引向量。正向 effect 拒绝负索引和越界索引。false 直接返回，不会撤销地图，因此不开放“取消窃取地图”。省份函数 `0xa0a1d0` 确认会 OR 省份 +5e0 的 actor discovery bit，但后续还有通知/缓存等路径；本轮不声称完整效果模型。

下一轮最小无发送实验需要先建立只读区域身份/vtable/name、完整向量边界和省份数组边界，选一个明确有效区域索引，再做 factory→初始化→clone 日期→full +88(NULL,false)→wrapper→command gate→正常析构。即便所有检查返回 true，仍不等于授权提交。后续效果观察需要原区域中目标已知/actor 未知省份集合与实际 discovery bit 改变，不能只看外交官或网络费下降。

## 叛军：不能把派系指针当作普通整数参数

`0x5843e0/0x584420` 通过 token=0x2933 保存/解析派系 +10/+14 两个 DWORD 的身份，在 target+e68/+e70 中解析借用对象。clone 只复制指针。当前没有给出可接受外部地址的接口，也没有已验证的 faction vtable/type/lifetime raw reader。

正向效果给派系 +10c 写 actor 完整 handle，加入 actor+e50 支持向量，并给派系 +100 写到期日。还调用 `0xaa75c0` 计算国库费用，经 `0x3387f0`、类别 **0x0f（十进制 15）** 支出；不能只检查 spy network。成本函数涉及定义、虚调用和其他对象，本轮保留完整有界切片而不推导简化金额。尤其 selected faction 未在目标向量中找到时，后续成本路径仍可到达；通用 preview 不能替代借用对象身份和成员关系核验。

false effect 扫描目标派系并选第一个 supporter slot 匹配 actor 的对象，调用 `0xaa1a50` 清支持；它不按 action+40 取消。完整 preview `0x5839b0` 对 false 返回 false，局部 `0x5836f0` 对 false 返回 true。当前正常 GUI `0xeeddc0` 仅闭合复制 action/所选 faction 后调用 local tooltip 检查，没有证实正常 false 提交。因此**不提出取消接口**。清除支持不等于 spy_network 任务/外交官召回。

## “窃取科技”的真实已见路径

安装原始脚本 `common/new_diplomatic_actions/00_diplomatic_actions.txt:2031` 中 `steal_modern_ideas` 属于通用 scripted family，require_acceptance=no。它消耗 24/30 spy network、增加 `russian_modernization_mechanic` 政府力量；没有给出技术等级提升。现有 `SPY_NETWORK_TECH_EFFECT` / `STUDY_TECHNOLOGY_MIN_TECHS_AHEAD` defines 也不能证明独立“窃取科技”命令。

该 family 工厂从 RDX 接收借用 definition，序列化 token=0x3668 保存 definition+10 的 EngineString32 名称。`0x5b6b80` 是 lazy registry getter，可能分配和初始化，禁止用于只读采样。正常 AI 遍历 registry 并初始化完整 stack action 后走拥有式队列。local `0xac6750` 转发到 definition allow `0xac8f10`，动态 condition 调用 virtual+30；effect 调用嵌入脚本虚槽，不能用“同布局”把它当成五类固定间谍 modifier。当前缺口是已加载定义精确绑定、脚本条件/效果实例与生命周期，而非猜造一个技术等级参数。

## 复现与资源

```powershell
python -B work/candidates/spy-extra-parameter-contracts-1375/trace.py --check
python -B work/candidates/spy-extra-parameter-contracts-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/spy-extra-parameter-contracts-1375 -p test_*.py -v
```

新增 36 个有界 CFG/块共 26,985 解码字节，每块窗口不超过 8 KiB，总预算 48 KiB。三个 exploration 文件保留全部探索，包括未采纳为完整合同的传递函数；没有追踪未知调用目标，没有扫描巨大反汇编。复用既有保存 CFG 后逐指令与 exact-SHA EXE 核对；报告保存原始文件与 JSON pointer。`trace.py --check` 不再反汇编。探索峰值约 81 MB，最终校验约 97 MB。

`contract.py` 是严格字段/归属反例模型，不是引擎模拟器、只读采样器或生产者。它刻意要求正向显式参数、保留未知和禁止执行标记；full handle 与记录都由测试注入，不能据此声称真实对象已验证。也未解决原址 ABA、持有寿命、world epoch、跨线程同步、TLS/global override、严格单机来源。
