# v17 单字节 pin 修复候选

仅候选文件与离线回放；尚未正式物化、编译、链接 DLL、读取游戏进程或投递请求。

冻结 v16 第4请求在 image pin 阶段拒绝，未调用 handler。648B handler校验串
在 RVA 0xe50222 预期20，完整SHA匹配的EXE及原静态报告为10（7710 / ja e50233）。
成因已精确复现：v16生成器对全部源码执行8771→8772字符串替换，污染了机器码
字符串中的d87710。原v16停止日志和失败摘要保留，不将complete-only当成功。
诊断8177389f…c5f5与追加成因fc1ec458…a7cb均由lineage绑定。

## 最小差异

从冻结v16的47输出派生：22原生、12宿主、5fixture为39个新版本目标；8shared
仅核验，内容不变。所有native均不执行任何端口替换。只有两个冻结Python完整
配置行（make_server的port默认值、CLI --port default）8772→8773；普通十进制
ID、长数字、任意URL、hex pin都不会替换。版本名v16/V16→v17/V17独立处理。
唯一native语义差异是handler pin20→10；全体8条实际source pin合计945B和
13条数据/指针检查、6个PE头条件由精确游戏SHA离线核验。

`pin-only.diff`展示这一个字节字符变化，`diffs/`为全部来源差异。
`native-source-review.json`只绑定native22及静态证据，宿主protocol的三个inventory
常量引用该稳定native-only摘要，避免与整体review循环。22源/12宿主/8support
manifest、9C+++1ASM/10obj和动态BridgeStart导出解析均沿用；未编造新DLL/RVA。
EU4LAB/3、36IDs、四阶段20/1/72/72、accept_on/submit/off保留槽位、once/no-retry、
严格TTL/ownership、v16pristine初始化和关闭历史全部不变。生产执行仍0。

## 离线检查

```text
python -B work/candidates/v17-acceptance-pin-review/prepare.py --check
python -B -m unittest discover -s work/candidates/v17-acceptance-pin-review -p test_*.py -v
```

56项继承测试加8项精确pin/端口污染/失败complete-only回归，共64项。
`prepare --refresh-candidate`只能CREATE_NEW本目录镜像；已有不同内容拒绝，正式
v17 runtime/build/session出现后拒绝生成，没有物化/编译/进程选项。正式构建脚本
仍需根代理独占审查授权，当前无构建许可。C++ mock源保留但本轮没有编译。

lineage继承旧173inputs及独立核验49旧pins，再绑定v16全部源码/候选、正式DLL、
manifest、根审批/构建、停止失败与诊断。首次生成因机械转换误改历史v15plan路径
失败；第二次被唯一字节断言拦截，揭示无边界端口替换污染。两次均未写拟输出，
没有测试执行；旧生成器字节与preparation-history记录保留。最终只认可validation
中的成功版本/输入前后相同记录。

离线pin匹配不是已安装代码的实测，也不是handler成功、普通AI接受、外交效果、
world epoch、严格SP、保存/重载或生产后端证明。v16失败进程已退出，不能重试或热修。
