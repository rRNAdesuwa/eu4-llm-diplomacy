# V19 real journal R2：全局 owner 帧与发送局部帧

本候选只修复已封纯 reader 对 seq4 起始帧的建模，不改客户端、bootstrap、Host/Core、DLL、manifest、原日志或旧 seal。没有进程访问、UI、原生调用或请求重试。新增解码为 0。

原错误不是缺少原生日志，而是把“第三阶段首次健康证明所在帧”误当作“seq4 紧邻的上一帧”。Host `status_.owner_frames` 在所有回调中递增，第三阶段完成后仍允许健康回调；`stage3_health_` 在首次建立 proof 时固定，不随其后的空闲健康帧变化。Core 的 frame 和 current item owner_frame 均使用当前全局 `status_.owner_frames`。

固定实际文件显示：第 3 阶段健康证明为 66，完整 preflight 健康日志继续到 84，发送开始是 85。原 Interval 把 frame 初始化为 66，误要求下一帧是 67。原失败已保留在独立 capture 目录，root 原首次失败记录也由 stopped archive 绑定。

## 精确修复

reader 保留原先从安装起逐条回放的全局计数：每对 outer before/after 必须对应全局前值和精确 +1，逐段 raw 长度、SHA、ordinal、线程、时间和 frame 全匹配。seq4 首个回调仅在这条完整链和三阶段后健康 proof 均有效时创建 Interval，并传入已经验证的 `controller_frame_before`。

Interval 单独保留 `third` 和 `origin_frame`，不重写任何 raw/Core/item/result 帧号或时间。全局帧仍必须严格 +1；另派生 `send_local_frame = global_frame - origin_frame`，并逐步核其也严格 +1。局部 1 只是发送模型的第一个回调，不是伪造新的真实帧号。原绝对第三阶段证明仍逐行精确比较。

报告增加 `send_frame_mapping` 和每个 interval 的 `send_local_frame`。未知提交、缺失 Result、未归还所有权、false、异常、日志和 claim 整体边界、later health、完整 footer 门槛均不放宽。意图时间依旧不当作实际入口时刻，`entry_uptime` 保持 null；正常返回只证明该区间内进入并返回。

## 验证与实际文件边界

25 个原测试逐字节保留，增加 7 项 synthetic methods，覆盖空闲帧、前置空闲帧、误用最新健康帧、bool/float、全局/raw/core/item/result 借用局部帧、缺少中间 callback、日志时钟、unknown 和缺 Result。

独立保存的完整实际输入为 raw 820625 字节/355 行、outer 168072 字节/196 行，外加 4 request 和 9 claim；没有截尾或改写。一次新 derived 回放通过，映射为 third 66 / origin 84 / first 85 / last 96 / local 1..12，completed outcomes 为五个 5。这个结果表示固定日志中的正常提交与消费及其后健康证据，不等于效果因果或生产权限。

该单次回放先使用请求时保存的固定副本；root 随后提供正常退出后的归档，`archive-binding.json` 将 15 个输入逐字节绑定到 stopped archive，对应原路径来源保持原样。没有重复实际回放，也不声称曾从归档路径运行。此任务不读取 census、不解释修改器或网络费用变化。

运行纯检查（不会解析实际副本）：

```text
python -B work/candidates/v19-spy-real-journal-r2-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v19-spy-real-journal-r2-1375 -p test_*.py -v
```

`replay_captured_once.py` 是已使用的固定离线取证助手，永久 attempt 目录防止重复执行。此候选没有新的可信实际 publisher 入口；冻结 R2 client 仍绑定原 reader，不应热替换其模块。独审需以当前新 source-index/review 作为离线修订边界。
