# Frida entry observer：未附加的 source/offline 候选

全局 EU4_ENTRY_OBSERVER_CONFIG 由 root 以安全 JSON 字面量前缀渲染，恰有8字段：schema=EU4-FRIDA-ENTRY-CONFIG/1、pid、creation16hex、固定game_sha256、实际module base字符串、固定原入口32B expected_prefix_hex、observer_nonce32hex、max_attempts=16。script不接收外部函数地址、模块名、预算或timeout。实际creation/SHA由root-held身份前后认证，script不自称验证它们。

只定位eu4.exe+10a6ec0。PID/base/x64/windows/pointerSize/module extent/原32B prefix不符时不hook。固定prefix复用R4已封字节，不能由config放宽。Interceptor是临时代码hook，可能写原代码并引入agent/runtime开销；这不是纯RPM。script不调用游戏函数，不构造游戏对象，不写游戏字段，亦不授权任何动作。

onEnter直接取得context.rsp/rcx/r8与threadId；Frida depth须0，threadId须正uint32。Q检查整个+4b0范围及entry16对齐余8，但仅保留六个8B槽：0/40/370/3f0/440返回和4a8 main holder。每槽含offset、实际source address、raw8 hex和uint64 hex value；不读取栈间隙。

五个return先预筛；静态链不符只等待当前一次hook下的下个callback，最多16次。首个匹配的五槽可复用为同scope first pass，随后读取first holder/typed世界字段，再从当前Q复读6槽及重新解析当前roots。code/data实际内存异常、坏上下文、type/identity/预算失败或两遍变化，立即terminal unknown，不重试或换callback补齐。whole-script固定1000ms deadline，root的单次CLI时限1500ms负责外部释放。

两遍核当前global outer/game、outer primary/secondary vt、current40/pending70/previous78、raw48/80 bytes、read64(game+1e00)==current==原R8、server vt/update、server+330/holder+360==原RCX、main holder==当前outer。optional app raw vt仅uint64诊断；不升级完整extent/ownership。world字段也保留source address/raw bytes，便于离线复核。每遍重取root/optional，不沿第一遍消失指针读取。

| 整次script最坏：第16次才匹配 | reads | requested bytes |
| --- | ---: | ---: |
| 16次五槽预筛 | 80 | 640 |
| first holder与world | 18 | 130 |
| second六槽与world | 23 | 170 |
| hook前、清理后code prefix各32B | 2 | 64 |
| 合计 | 123 | 1004 |

固定硬上限128reads/8192B覆盖script所有显式readByteArray请求。正常首candidate optional=48reads/404B，null optional=44/372B。分类counter为prefix_before/prefilter/stack/world/prefix_cleanup；exact_bytes只计有效owned byte copy。预算不统计Frida内部实现、module API或JIT/agent内存访问，不能称全进程CPU读取次数。

callback内同步复制两份owned hex/scalar后设置terminal。延后setImmediate只处理owned结果和固定module code target，listener.detach一次、Interceptor.flush，再核32B prefix；不再读Q/heap对象。每次script最多一个send envelope，ASCII且≤16KiB，无binary附带数据。cleanup异常或prefix未恢复会将匹配结果降为unknown；host仍须采独立code恢复及REA unload/detach回执，不能仅信脚本flag宣布所有hook资源释放。

输出schema=EU4-FRIDA-ENTRY-OBSERVATION/1，status仅structural_match或unknown。全部native_ready/native_entry_authenticated/lifetime_lease/atomic/creation/imageSHA认证均false；temporary_code_hook说明hook尝试，field_game_data_writes/native_game_calls为0。没有memory_written=false误称。thread与调用链观察不是world或sentinel lease。

读取本地REA docs/frida-instrumentation.md后未找到安装的frida-gum类型defs；API另参考官方[Frida JavaScript API](https://frida.re/docs/javascript-api/)的onEnter context/threadId、listener.detach、flush、readByteArray语义。选定API的文档依据不等于此机attach验收。Node VM只模拟这些API与真实布局字节图，不导入Frida、不调用REA、不访问游戏。script在本机Frida17.23.2中的实际加载、寄存器呈现、cleanup恢复及采样尚未执行，须root单独审查/授权。
