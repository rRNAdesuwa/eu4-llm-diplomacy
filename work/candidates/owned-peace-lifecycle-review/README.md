# 默认 owned peace 生命周期候选

此目录隔离于所有 v11/v12 源与宿主。准备阶段只生成、核对磁盘证据；**没有编译、链接、注入、读取进程或调用游戏**。没有接入正式外交接口。不是可发送和平的后端。

## 固定实验

`eu4_owned_peace_lifecycle_1375::run_once(const Host&)` 每次装载最多接受一次实验；无外部 action、国家、指针、条款、RVA 或脚本参数。

1. 持久记录步骤开始，重新检查宿主 guard、游戏线程及映像 pins。
2. `factory(0x293c, nullptr)` 返回默认 requestpeace；只读核验默认布局。
3. 调原件虚槽 `+b0` 克隆；核验原件未改变，两对象各自 8 块已知分配完全不重叠。
4. 调原件 deleting destructor(1)，核验存活克隆仍满足同一默认布局且所有分配地址不变。
5. 调克隆 deleting destructor(1)，返回完整结果。

不会调用 war 参数构造器、合法性或 AI 预览、GUI、和平组件工厂、command wrapper、submit。不会手工初始化 native 对象、深复制结构体或单独释放嵌入和约。

## 三份和约的时间关系

factory 内部先以 `2c6890` 构造临时和约，通过 `598af0 → 975f40` 深复制到返回 action 的 `+48`，并在返回前调用 `9761c0` 清理临时。之后外部虚克隆 `59ba40` 再深复制一次。这是先后存在的三份独立和约；候选只能同时直接核验返回原件与克隆这两份，**不会宣称观察到已销毁的内部临时**。

GUI 的真实三实例链另见 [GUI 发送报告](../../reports/native-peace-gui-send-1375.json)：GUI 源提案、原始请求、command 拥有的克隆。本候选没有创建 GUI 或 command，不能拿默认生命周期替代那条运行期链。

## 只比较已闭合的默认字段

- 外层 action 大小 `0x210`，嵌入 offer 在 `+48`、大小 `0x1c0`；双方类型 DWORD `0x165`，虚表严格分别匹配 `1c7b840`、`1c578b8`。
- actor/original/target/giver/taker 均为无效句柄 `0x2d2d2d`，两日期 `0x29c77f8`，envoy=-1，state=0，value=true，ID=0。
- **外层 demand=true，内嵌 is_demand=false**；diplomats=true、force=false。不能将外层方向直接复制给内嵌对象。
- 七个向量三元组 `+28/+40/+58/+70/+88/+a0/+b8` 全空。返回对象的 `+d0` 为独立分配的 40×24 字节类型索引，每个内层向量全空；临时 default ctor 的索引为空，但 copy ctor 会创建 40 项。
- `offer+e8==offer`，不是 outer action，更不能指向 source；`f0/f4=0`，`1b8=0,1b9=1`。
- 三个空 hash：sentinel 分配大小分别 `0x30/0x40/0x40`，next/prev 指回自身；size=0，load bits=`0x3f800000`，mask=7、bucket_count=8，16 个桶指针和容量均为 16，全部指向本 hash 的 sentinel。新有界 helper 切片闭合空 hash copy 后的 rehash 仍为 8 buckets。
- 不比较未初始化 padding、哨兵 payload 或未命名非默认业务数据。不遍历实际条款、hash 节点或国家对象。

`default-contract.h` 是可注入 reader 的纯只读核验器，每次最多 512 次标量读取、8 KiB，所有容器循环固定长度。每个对象只接受已知 8 块分配（外层、类型索引、三哨兵、三 hash 桶数组）；同时检查对象内与对象间重叠。

## 宿主合同与失败

宿主需在经验证的游戏线程、暂停的可丢弃会话中调用，事先绑定精确 PID/创建时间、完整游戏 SHA、会话状态及 durable attempt claim。每个 native call 前 guard 必须重新检查世界/模式/线程并阻止并发实验。这里没有创建宿主、证明 world epoch 或暴露公共接口。

logger 必须全长写入并 flush，成功才返回 true。每步 begin 在 native 调用前持久化；写入后再次检查 pins/guard。日志事件采用独立前缀 `owned_peace_lifecycle_*`；宿主收到 Result 后应另记最终 wrapper/健康帧，不能仅凭最后一条可能未 flush 的日志宣告通过。

布局、别名、guard、日志失败或任何 SEH 后立即终止并要求冻结，不再猜测析构或重试。此策略可能保留有限的未释放研究对象；应退出该研究会话，不执行“修复”。SEH 后本模块也不调用 logger，交由外层记录 Result。进入析构后只有明确返回才计为完成。任何返回都 `retry_allowed=false`、`execution_verified=false`。

## 复核与后续编译

准备期已运行的只是：

```powershell
python -B work/candidates/owned-peace-lifecycle-review/prepare.py --check
```

`review.json` 固定输入报告、源文件和 pins；默认布局增量证据为 `default-layout-evidence.json`。无循环引用 catalog。当前按“不构建”约束，没有运行下面的编译或合成测试命令。独立审核后可在 MSVC x64 环境、临时输出目录执行：

```text
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /c peace-owned-lifecycle-1375.cpp /Fo:<temporary-directory>\peace-owned-lifecycle.obj
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 test_contract.cpp /Fe:<temporary-directory>\test_contract.exe
<temporary-directory>\test_contract.exe
```

`test_contract.cpp` 使用真实核验器检查默认差异、非零 padding、40 项边界、self 指针、哨兵、空 hash、跨对象浅复制别名、读失败预算和原件不可读时的克隆核验。它没有调用 native；尚未编译/运行，不能当作测试通过证据。

未来真实和平另需战争 fixture、完整参与方及 war 生命周期绑定、非空 term clone/删除、真实 wrapper/command 生命周期、合法性/AI 回复、效果与保存重载验收。默认空对象通过也不能证明参数构造器与真实战争安全。
