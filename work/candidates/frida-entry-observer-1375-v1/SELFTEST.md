# Source/offline 自测与采用回执

采用 offline-verification-r2.json，SHA256 450f7868693437ed61ac880c57171cc640bc1e05768f226fc90a0106ca4cb424。18项Node VM模拟测试实际exit0/pass18/fail0，direct child峰值41,107,456B，在768MiB guard内，已wait/close。没有加载Frida addon、调用REA、附加进程、安装code hook或访问游戏。

script为14601B/SHA256 4b2107d0a912280c271be66e5436482f1e89bfb348b326dfd25daf2d3308820e；test为16327B/SHA256 30afc138b6b98b1fb4d5ddc0790e74ff9f385ca2457561ff27a7fc748eac654e。此版本尚未封存，独立审查进行中，root未授权本代理进行真实捕获。

最初17项smoke通过后补了五个return槽各自破坏的独立案例，最终18项一次正式运行全部通过。原verify_offline.py错误期待TAP的“# tests”计数，而该Node默认输出Unicode spec计数“ℹ tests”；wrapper因此将实际通过记录为false。原offline-receipt.json和原stdout文件保留，不覆盖；新verify_offline_r2.py仅解析这些既存计数、exit和exact source/Node/helper pin，未重跑测试或改script/tests。stdout文件原名带.tap，但其实际格式是spec；这项文件命名不改变其内容散列或测试结果。

正常首candidate optional48reads/404B，null optional44/372B；15次第五槽错误后第16次成功123reads/1004B。实际fixture只映射六个栈槽，间隙未映射，因此读取整窗口会直接失败。每槽raw8、绝对source address及Q偏移全部核对。timer/16次不合链、原prefix/PID/module/config、thread/depth/Q/returnAddress、outer/game/current/vtable/update/map、非法pointer、短/大/已detached buffer、第二遍退休pending、return变化、reentry、detach/flush/attach失败均有反例。

Fake Interceptor仅修改本测试Map中的code bytes，明确模拟hook代码写入；禁止API会报错。callback结束后Stack区域拒绝任何读取，延后cleanup仍通过，验证没有保存后追Q。结果的ASCII单send envelope由测试逐条核≤16KiB。typed字段payload保留raw/source，agent只用owned数值/hex延后发送。

核验：python -B work/candidates/frida-entry-observer-1375-v1/verify_offline_r2.py --check。该命令不运行Node或Frida。不要使用原wrapper的--check作为最终结果入口，原false回执是保留的parser勘误证据。

真实Frida17.23.2脚本兼容、实际onEnter寄存器及depth、temporary hook安装/恢复、process creation/SHA前后held认证、owner thread与world/header lifetime均未验收。API文档和Node mocks不提升这些条件；全部native_ready/auth/lease/atomic false。所有shell已完成，无listener。
