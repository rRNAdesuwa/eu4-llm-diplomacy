# 未封存 ABI 自测记录

当前采用 `build-attempt-04/receipt.json`，SHA256 `2473fbf604ab009b97d898fc3f4dad30300cce179d37fb902e74ae43ec7d61ae`。已有 MSVC14.44.35207 的 ml64/cl 完成 assembler、C++17 /W4 /WX /EHsc /Od /GS 编译及 standalone EXE link；14 个案例、157 项断言通过。没有安装工具链、创建 DLL、游戏访问、注入或游戏 native 调用。所有子进程已 wait/close。

模型正常路径验证 CALL/JMP 两入口、五个实际嵌套 return slots、真实 entry Q/RCX/R8/S/T、完整32B shadow 写入与32B descriptor分离、7个 volatile GPR 与 XMM0–5 low128恢复、8个 nonvolatile GPR 与 XMM6–15 low128前后保持。4个正常 case 覆盖两入口×optional/null，selected reads 为46/340B或42/308B；此外固定32B descriptor copy与32B shadow probe单独列账，未将 selected counters 冒充全部CPU内存操作。

负面案例是 typed fixture 破坏、非法对象范围、短读/预算、reader 返回的坏 return value、两遍 pending/byte变化。实际机器 return slot 没有被改写。pending 在第二遍移除时不再沿第一遍旧 pointer 读取。离开 callback 后清空 fixture，再调用 owned evaluator，后者没有 reader、Q 或对象解引用。EntryBorrow 及 Reader 均不从 callback 逃逸。

attempt01 的 MASM external XMM buffer误声明 BYTE导致 operand尺寸错误；attempt02 修 OWORD 后，C++标签忘加extern导致重定义 link失败。均未运行失败 EXE，原receipt及日志保留。attempt03首次全部通过，但其旧runner保存全量SET环境输出；attempt04只由明确 helper 输出 PATH/INCLUDE/LIB/LIBPATH JSON，环境可以传编译子进程但不保存全量。

安全勘误仅修改这三个新scope日志：`build-attempt-01/environment.stdout.txt`、`build-attempt-02/environment.stdout.txt`、`build-attempt-03/environment.stdout.txt`，删除非工具链字段，没有明文备份或消息展示变量值。独立 `environment-redaction.json`（SHA256 `ed8026bca17f3fd592b043202c850dcb17c56dbc322a677e4d67f8d44adb76b3`）保留三者原/脱敏hash及原因。旧receipt不覆写，其原环境hash是历史观察，不再是当前可重放文件输入；复核须使用redaction映射。最新验收仅采用04，ASM/header/C++三源在03→04保持相同pin。

04 runner直接监测自身Popen stage handle，60s/768MiB；观测到C++driver峰值34,025,472B、ml64 1,150,976B、测试EXE720,896B。该统计不宣称覆盖driver所有内部子进程的峰值。没有遗留shell或listener。预算不用于任何运行游戏进程。

本次不是实机callback：无真实installed provenance、held process/image/thread/reentry认证、header/world lifetime或atomic snapshot。异常unwind、AVX/xstate及真实入口安装未完成；结构内所有authority常量false。`FRAME/.allocstack`能编译不等于异常路径已验收。源码仍未封存，供独立审查。
