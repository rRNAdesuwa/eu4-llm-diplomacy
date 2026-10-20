# 用人情要求第三国断盟：1.37.5 静态合同

本候选只分析 `break_alliance_favor`（token `0x3bcb`，虚表 `0x1c3e438`，对象 `0x48` 字节）。它与普通 `break_alliance`（`0x3375`）及自身 `dissolve_alliance` 不同。没有原生调用、进程读取、实际发送或效果验收；所有 production/runtime/execution 标志为 false。

## 参数、生命周期与正常调用

`129530` 叶构造接收 RCX=this、RDX=请求方、R8=被要求断盟国、R9=第三国完整 handle，第五参数是日期 DWORD 指针。通用字段为 actor+10/currentactor+18/recipient+20/date+28/+2c、envoy+30=-1、state+34=0、value+38=1、flag+39=0、id+3c=0；+40 是第三国完整 handle，不是指针。serializer `7c6790` / parser `7c67d0` 以 `third_party` token `0x3228` 保存/读取它。工厂 `36015e..3601f2` 分配 0x48 并调用此叶构造；本次没有闭合大工厂内部的 token 算术分派，名字/token/虚表映射引用已有 inventory。

clone `7ca3e0` 分配新对象，把源 primary date+28 同时复制到 clone+28/+2c，随后通用 wrapper `4e9930` 会把 clone+2c 改为当前 GAME 日期。不能把任意源 secondary date 原样复制作为预期。+40 为值复制，无独立扩展分配。删除析构 `129500` 仅按 DL&1 释放 0x48。

正常 AI `13a670` 先尝试普通断盟分支，随后构造 favor action；`13a7ee..13a877` 明确 state0/value1、三国角色及 date。`13a9d3→129b60` 经 `+88(NULL,false)`、`+80` 后调用 `+40=4e9930`，创建 0x58 command，clone 位于 command+50 并由 command 析构拥有。队列 `AI+a68` 接管 command，原 action 独立存活/销毁。本证据是正常原生 AI 队列，不是人类 GUI 或最终 context_submit 的闭合证明。异常后不猜测清理或重试；模型也不声称能够处理真实 SEH。

## 合法性与回复

full+88=`7ca480` 保留 NULL sink/modefalse ABI；它调用通用 `4e9d00`，sink 非空才添加说明。family+80=`7ca5a0` 与 command+40=`4e8630` 分开。检查包括：actor+eb8/+ec0 的8字节 token/expiry 向量中 3bcb 未过期项；recipient+19b8 盟国链包含 actor；双方 +289b 战争字节；recipient+1510[actorSlot*0x48]+20 人情毫单位达到 global233f454*1000；recipient+2380/+2388 的有符号16位关系值达到 global233f460。`7c7a20` 还检查附属关系例外、战争/同盟索引、GAME+25c8 的 `db5380` 与脚本 `4ebdb0`。`db5380` 会解析两个对象并调用虚槽40，类型和可能懒初始化尚未闭合，不能拿它当 RO getter。

解包 defines 包含相应 cost=50、required opinion=50、action cooldown=10、force break truce=10；这里只钉扎文本，并未追注册器把这些名称与每个运行 global 一一绑定，因此真实代码应读已确认 runtime 值而不能写死默认值。native 许可还涉及 TLS 懒初始化；暂停与两遍读数相同都不能把 native preview 宣称为无副作用。

virtual+d0=`542af0` 在 state34==0 时返回 true，正常提议会等待回复。state1/2 分别走拒绝/接受效果。没有正常 false 取消调用链，也不能将 state2 作为外部参数绕过 AI 回复。测试模型拒绝这两种扩展。

## 接受效果超出一个同盟标志

`7cb190` 接受分支扣 recipient 对 actor 的人情（`a658d0` 本身还有共享 gate），调用 `3eb120` 写相关日期/期限，并更新 actor 的 3bcb 冷却记录，然后进入 `7c67f0`。拒绝分支有负向数值/修正调用，再进入共享通知逻辑；pending 不应当作接受。

共享接受分支会分配 0x40 forced-break relation（+10=recipient，+18=third，+20=current date），登记到 GAME+1bb8；`a5f440` 双边注册，`a5f590` 从 recipient↔third 的同盟索引移除原关系（`a5d790`→`a5bb00`→free48）。它还检查根170、1a0、248、110并在部分条件下调用任务、关系析构，包含贸易/补贴等关联效果；本次未逐一闭合全部派生类型及脚本响应。`7c67f0` 还包含全局懒分配、国家修正、历史与通知。因此未来观察器至少需要完整三国身份、recipient↔third 双边同盟图、recipient→actor 人情、actor 冷却向量，并记录其他相关关系变化；只见同盟消失不能证明这个请求的独占因果。

## 下一步与已知缺口

最小后续实验可先做带完整 third handle 的 factory/clone/wrapper/析构，无发送；普通队列证据为其提供字段预期，但仍需要原生主线程/世界生命期、完整参数合法性、SEH/所有权审查。实际发送应等待国家 resolver、第三国同盟对象 RO 验证、回复观察和副作用范围收敛。这里没有 sender、DLL、raw sampler 或 API 执行适配器。

顺带核查 curry：现有分支 `598675→9751b0` 的 85B 函数仅访问共享 globals/TLS 许可；不能据此识别 DLC 或外交面板分类。现有 curry 合同也未闭合 human GUI visibility。

## 重放与预算

`python -B trace.py --check` / `python -B prepare.py --check` / `python -B -m unittest discover -s <本目录> -p test_*.py -v`。模型只检查静态字段合同、角色、日期、拒绝未知与所有权状态，不认证引擎 ABI。

三次保存探索共13,086B（每 CFG 窗口8KiB，预算48KiB）。误起始 360169 的138B、35f311的115B完整保留但不采用；正确起始36015e/35f2ef独立保存并复核。没有从大反汇编扫描或整程序扩展。所有采纳指令、虚槽与引用字符串以精确 EXE 原字节核验；prepare 钉扎输入及源码，validation 保存所有子进程退出和来源前后 SHA。
