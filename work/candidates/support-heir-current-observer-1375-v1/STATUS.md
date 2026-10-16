# 支持继承人当前任务读取器

源码、生产元数据和失败路径已独立审查通过；**已加载游戏世界中的任务存在／缺席实测仍待完成**。

工具通过 QUERY/VM_READ 读取双向 `140` 索引，区分缺项、匹配项为 NULL、匹配活动对象及不一致。两侧选定值都为零时报告 `selected_task_absent`；相同非零对象还须通过虚表、原始标记、完整端点和移除状态检查。它不调用游戏函数，也不把任务存在当作某次请求成功或最终继承人结果。

```powershell
python -B work/candidates/support-heir-current-observer-1375-v1/support_heir_current_observer.py status --pid ACTUAL_PID --creation ACTUAL_CREATION --actor FRA --target POL
```

必须提供当前真实进程身份，并已载入、手动暂停测试局；无需保持游戏前台。不要复制历史 PID。来源变化、世界为空、身份失效或双遍不一致均返回 `unknown`，不自动重发外交操作。

- CLI：21780B，SHA `8b2eba840c3f6b4927f6fbf1aa04878c931fc548372dc10dd8432863ed68ec01`。
- 生产清单：5506B，SHA `f8442eefa3dbacb5a952a5d8387cf0bcea83adfcb059034984af5bd40478c069`，22 个直接 source pins。
- [源码独审](../../reports/support-heir-current-observer-source-review-20261015-r1/independent-source-ready.json)：49 审查 pins；15 个作者首次离线方法、首次 check/catalog 回执，另两个独立新边界案例，无旧套件重跑。
- [生产差异独审](../../reports/support-heir-current-observer-production-review-20261015-r1/production-passed.json)：9 pins，仅四项元数据变化，源码和依赖未改。
- [失败路径独审](../../reports/support-heir-current-observer-unknown-path-review-20261015-r1/findings.json)：40 pins。旧 PID80340 已退出；新 PID92904 的世界根指针前后为零。两次均只有 FRA→POL 的 `unknown`，没有任务样本或结果提交，ENG→POL 未运行。

第二次查询的四条原始读取共4324B：世界根指针两次各8B，以及后检查代码4244+64B。第一次没有选定读取 journal；入口 PE 预算声明不是实际读取证明。两次 Job 子树均回收至0。第二次正常离开 context 并清除 held handle；第一次 enter 失败，不能据此补称关闭已验证。底层 CloseHandle 返回值均未验。

nonce 不是安装会话，raw endpoints 不是无条件认证的 supporter／target 方向。任务业务效果、最终继承结果、完整 C++ 类型、原请求因果、AI接受、寿命 lease、原子世界快照、持久化和 native executor 均未因此获证。稳定15请求效果 profile、98 pin入口及历史48／44／42计数不变。
