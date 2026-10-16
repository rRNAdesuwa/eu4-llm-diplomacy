# Integration current-status 候选准备结果

独立 current pair 工具已实现，仍是拒绝实采的draft。源清单21 pins，R44/R45/R46静态合同与两份独立静态审查均固定；候选自身待独立审查，`sealed=false` / `runtime_capture_authorized=false`。没有修改stable/native/已有reader或晋升运行时profile。

24个本模块新fake方法首次全过（0.192s）；check/catalog各首次一次通过。三个Job各45s/768MiB，均exit0、active0、child collected；peak job committed依次36,782,080 / 32,051,200 / 32,083,968 B。测试与文件查询前后源相同，没有旧套件、实际status、进程访问、PE二进制读取、REA/Frida/native调用或新请求。

首次build的文件自检发现R44清单使用`file_pins`而非R45/R46的`source_pins`。失败在任何新test/check/catalog前；6份精确前像与exit1回执保留在`preparation-failure-r1/`。仅修这一固定格式分支；file-only交付检查重放差异证明没有其他源码变更。修后草稿构建成功，随后才首次跑上述测试和两个CLI查询，没有重跑旧结果。

观察状态为`selected_task_present`、`selected_index_absent`或unknown；两侧同P、vtable1c816d8、完整端点及P28零才能presence。其他vtable/单侧/removed/端点错误都unknown，不视为absence。P8不要求357，P20只输出raw u32。冻结relation核root=country+14f8、row完整pair和country+1510映射，root+200索引capacity/unique等是额外reader guard。

loaded guard四块每轮2376B，前后共4752B（2259+103+relocated slot8+leaf6）；完整1380表每遍fresh。host/code/table/selected统一4096calls/512KiB预算并保存ordered raw journal；冻结RuntimeCapture的入口8192B PE身份读取另列。正常with关闭、held.handleNone和最后source guard全部完成才commit；只读nonce不当安装session。

source/test/README草稿已稳定供独审。纯文件复核`python -B work/candidates/integration-task-observer-1375-v1/seal_preparation.py --check`，只查交付pin、不重新运行测试或CLI。`delivery-manifest.json`封的是准备材料完整性，不是生产授权。所有native/effect/mapping/lifetime/atomic/persistence权限保持false。
