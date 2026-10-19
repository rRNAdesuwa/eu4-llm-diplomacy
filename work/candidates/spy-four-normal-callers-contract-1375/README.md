# 四个间谍家族：正常 AI 初始化与拥有式队列补证

精确 EXE SHA256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。
这是新的独立静态候选；旧 spy 报告、v18 无发送核心及协议均未修改。
没有打开游戏进程、编译、注入、安装 hook、调用游戏或发布请求。

## 已闭合的四条正常路径

| 家族 | token / vtable RVA | 正常构造位置 | 交给共同 AI 队列 |
|---|---|---|---|
| sabotage_reputation | 2ddd / 1c7cfd8 | 13b810 内 13c20a..13c259 | 13c27e → 129b60 |
| sow_discontent | 2ddf / 1c7c9e8 | 13a1f0 内 13a204..13a258 | 13a384 → 129b60 |
| slander_merchants | 337b / 1c7c378 | 13b810 内 13c2e4..13c32e | 13c350 → 129b60 |
| sabotage_recruitment | 33bf / 1c7c5d8 | 13ade0 内 13adf4..13ae48 | 13af84 → 129b60 |

两个小 helper 的正常父调用也已绑定：13b810 在 13c360 调13ade0，
13c3d4 调13a1f0，参数为 AI 对象、当前目标 country 对象和评分控制 bool。
作为对照，旧 corrupt_officials 分支13c365..13c3c4仍复用，不计作新发现。
这不是新找到的人类 GUI 回调，也不证明 AI 的每次考虑都会进入队列。

上述正常 AI 路径**直接构造栈上 action**，没有调用通用工厂。
具体 factory token 与这些对象的联系来自已钉扎工厂分支、相同 vtable，
以及每族 virtual+98 的 `mov eax,token; ret` 六字节叶函数。
不能把它写成“正常 AI 调用35d210”。

四族均逐字段明确写入，而非仅以0x40相同推断：

- +00：本族 vtable；+08 DWORD marker=0x165。
- +10/+18：AI+28 的完整 actor handle；+20：目标 country+20 的完整 handle。
- +28/+2c：当前 GAME+1dd0 的 DWORD 日期。
- +30=-1，+34=0，WORD +38=1（value=true、flag39=0），+3c=0。
- +0c..0f、+3a..3b padding 不约束。

reputation 中 actor 先在13c0fd从AI+28载入RDI；其13c241清R13D。
随后 merchants 和 corrupt 分支使用这个零值。中间正常调用须遵守
Windows x64 非易失 R13 约定；这里没有新证明异常展开可安全继续。
两小 helper 的栈坐标另算：R11为入口RSP，push/sub后为当前RSP+68，
action位于当前RSP+20；不能套用大 dispatcher 的RBP坐标。

reputation 的57ed60及 merchants 的580730是评分 helper：RDX指向调用者
DWORD输出，正常返回这个指针；其第三bool控制评分分支。两个小 helper
中的r8b也只控制评分。所保存的代码没有把该bool写入action+38，
所有闭合正常构造都是 **true**。不因此开放false/取消间谍修正。
评分体会调用国家关系及虚函数；这里只核 action字段传递，没有声明它们
对世界、缓存或脚本纯只读，也未递归遍历它们的全部被调函数。

## 共同预览与 ownership

129b60先有其他费用和评分门槛。其继续路径在129d95..129da0准备
`RCX=action, RDX=null, R8=false`，调用virtual+88；false转离后续路径。
随后+80另行调用，同样使用null/false。五族+88不同地址由虚表分别绑定，
不能用通用4e9d00或command gate替代其能力检查。

后续12a6e3调用action+40，即4e9930 wrapper。wrapper先virtual+b0克隆，
再把clone+2c写当前GAME日期，分配0x58 command并在+50拥有clone。
AI+a68取走返回容器中的command，临时容器先清零，再析构旧command。
栈上原件没有被存入拥有式队列；其栈寿命与独立工厂原件也不能混同。

直接clone的+2c来自原件+28、+39清零；wrapper随后写的是当前GAME日期。
command析构4e7470核clone+a8，五族该槽为8f450常量false，正常路径
用虚析构(flags1)销毁clone，再销毁command的String32+18并释放0x58。
这只说明正常拥有关系；异常/未知别名/不明确返回不得补析构或自动重试。

## 预算、重放与有限模型

仅新增四个CFG：13ade0、13a1f0、57ed60、580730，共 **1,664字节**。
每函数8KiB窗口、最多2500指令，不递归追call。另直接匹配五个token叶函数
共30字节，总新增代码计 **1,694字节**，低于64KiB。所有探索均在两个
exploration JSON保留，没有失败/被省略的探索。其余5,810字节复用旧报告
并逐指令与精确PE复核，大dispatcher只取必要保存切片。

constructor_model.py只解释这些固定构造片段的mov/xor/lea，在模拟字节内存
验证各自栈布局和所有语义字段；不模拟评分、预览、队列或native调用。
16个离线测试覆盖五个独立构造、bool与数值类型、stale generation、日期、
290处语义字节扰动、padding、超界写和未知指令拒绝。模型通过不是引擎ABI
或运行时证明，输出始终native_call_authorized/runtime_verified=false。

```powershell
python -B work/candidates/spy-four-normal-callers-contract-1375/trace.py --check
python -B work/candidates/spy-four-normal-callers-contract-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/spy-four-normal-callers-contract-1375 -p test_model.py -v
```

仍未闭合：人类GUI完整发送链、传递脚本的全部副作用、异常展开、实际线程
与lifetime同步、strict SP/epoch，以及真实生命周期、分派、效果、保存重载。
本候选只补齐“其余四族正常初始化调用者”这一静态缺口，不改变既有候选
权限，也不授权在当前游戏运行v18阶段。
