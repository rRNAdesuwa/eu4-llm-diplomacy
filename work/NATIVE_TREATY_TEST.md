# 原生和平条款最小测试

## 实现与参考

- 依据本机原版 common/peace_treaties/00_peace_treaties.txt 的接口说明。
- 查阅 Common Universalis 作者公开源码：https://github.com/Corpsemania/Common-Universalis-Internal/blob/master/common/peace_treaties/cu_peace_treaties.txt 。其中 force_protectorate 使用同一接口、常数战争分数费用、requires_is_allowed=no 及 ai_value。本项目独立编写测试，不安装该模组，不假定旧模组适配本机版本。
- 新增 llm_test_pay_10：只限英法双方，赔款10杜卡特，基础战争分数费用10，条款本身不增加侵略扩张或威望。CB、国家修正和引擎取整可能影响界面费用；不预先承诺最终显示10。
- requires_is_allowed=no 按原版说明可在未被CB明确允许时使用但产生外交点数费用；因此先不覆盖CB或战争目标文件。
- ai_weight 是自定义条款意愿参数，不是已证明能调用或复刻原生接受总分的接口。接受总分以原生和平窗口实际显示及响应为准。

## 用户手动步骤与检查点

1. 保存当前战争测试局，重启加载模组后读档，保持暂停。
2. run llm_treaty_probe.txt，保存双方财政及条款标记基线。
3. 以英国身份打开与法国的原生议和页面，选择“要求贡品”，在条约分类寻找 LLM test 条款。先只选择此条款，检查实际战争分数、外交点数和AI接受原因；此阶段不发送。
4. 若显示正常，后续先记录是否愿意接受，再发送并推进必要时间。在被拒绝时应继续战争且无条款结算；在被接受时应由引擎结束战争，执行条款转账，收到 treaty_pay10_01 回执。
5. run llm_treaty_probe.txt 验证方向、资金变化和标记。必须结合游戏日期、正常收入及其他条款判断金额；只把探针紧邻结算的观测用于精确金额对照。

## 边界

该测试验证自定义条款进入原生评分/结算路径，不验证 LLM 自动发送。对玩家来说法国仍为原生AI接受方；法国侧LLM尚未接管接受决策。不要使用 yesman 影响评分。先不切国家、不强制白和平、不加钱以改变测试条件。
