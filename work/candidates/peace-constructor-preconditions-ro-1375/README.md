# 议和参数构造前提的只读观察候选

本候选提供**离线、严格 schema 的观察数据解析器**，没有进程读取器、hook、原生函数调用、构造器或 sender。即使所有字段完整且两次完全相同，输出仍固定 `parameter_constructor_authorized=false`、`parameter_selftest_ready=false`、`runtime_verified=false`。观察前提不是调用许可。

目录内 `prepare.py` 只读取精确 SHA 的 EXE 和两份已有报告，校验有限指令与虚表字节，生成 `static-contract.json`。没有重新解码原有 CFG，也没有递归扫描。输入报告是 `native-peace-parameters-1375.json`（SHA `93dda379...c5677`）和 `native-peace-candidate-boundaries-1375.json`（SHA `8d0f6885...13f8e`）；完整 SHA 在契约中。EXE 固定为 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`。

## 本轮核对与补充

政府实例与政府定义应分开。`country+1420` 指向实例，实例 `+10` 是该路径读到的定义指针。`97d4e0` 把实例 `+38` 作为 wrapper 传给 `7ace30`，后者取 wrapper `+138`，所以最终 **variant 指针在实例 `+170`，不是 `+138`**。另一条 `97db60` 路径取实例 `+110`。这两者是带类型码的布尔 variant，并非脚本 condition 对象。

| 原生路径 | 第一布尔 variant 指针 | 第二布尔 variant 指针 |
|---|---:|---:|
| `country+1420` 非空实例 | `instance+170` | `instance+110` |
| `798dc0` 返回的 `nogovernment` 定义 | `definition+1b0` | `definition+150` |
| 下层 `7a73c0` fallback | `secondary+190` | `secondary+130` |

实例为空时，原生 getter 可能初始化全局 `233fe88`；下层全局为 `242bc80`。后者是语法上的 null fallback，不宣称正常成功的第一层 getter 必然进入它。候选只解析已有直接实例；实例缺失时即记录缺口，**不调用 getter、不预热缓存、不用“缓存已有”伪造实例存在**。已识别布尔表示为 signed DWORD 类型 `0` 或 `-1`（按 `t>=0 ? t : ~t` 归一为0），存储在 variant `+8` 单字节；其他类型、null variant、非0/1字节都留下缺口，不能据此执行。

TLS 的旧报告文字只列出了一个充分条件，完整分支还包含前一个字节：`97e207/97ea11` 先检查全局 `233ff94`。**进入 TLS 路径的条件是 `byte[233ff94]==0 || byte[233fed6]!=0`；仅当第一字节非零且第二字节为零才跳过。** 两个 caller 均从 `GS:[58]` 数组第0项读取 TLS `+c/+10`。初始化函数却使用全局 DWORD `233c574` 的模块索引并写对应 TLS `+c`。因此需同时记录第0项和该索引项，不能只采集某个方便取得的 TLS 块。`+c=0` 表示调用初始化函数的路径；`+10=0` 会跳过候选分支，不是国家外交拒绝。

战争目标 fallback 全局确为 **`2340030`**；**`233ffd8` 是另一附庸定义注册表，其 `+80` 定义的条件指针/计数是 `+48/+54`**。两者不得混用。当前只对已钉扎的 `take_colony` 虚表 `1d1fd90` 识别有效定义：`+78=8f440` 常真、`+70=d9f0b0` 检查实际省份绑定、`+58=9b120` 读取 `this+10`。任何其他动态类或进入 fallback 后的虚函数族均保持未知。

## 将来只读采集器的查询顺序

以下为设计，不是已实现的进程访问权限或运行守卫。原始查询字段应记录地址、读取宽度和捕获时序；现在的 parser 仅处理已解码字段，不能独立证明生产者实际从这些地址读取。

1. 持有只读进程句柄，核完整 PID/creation/path/磁盘 EXE SHA、模块基址/大小/时间戳。由调用者给出双方完整 handle 和 demand/concede 方向，解析 signed16 slot，再对当前数据库槽位和 country `+20` 的完整 handle 核对。国家数组由数据库 `+118` 读取；实际数据库容量及游戏日期等基础字段需要复用并绑定独立现有 RO probe 的已审契约，本轮未重新证明其所有原生 setter。不能只用硬上限替代真实容量。
2. demand 时 taker=actor、giver=recipient；concede 同时交换双方。按 `country+1510` 的关系表，以对方 slot 乘 `0x48` 定位；项 `+0` 为 root，`+10` 为对方完整 handle。`root+50` 指针、`root+5c` signed DWORD count 的数组每项16字节，`+0` DWORD 是国家 slot key，`+8` 为借用 war 指针。它不是 `war_id`。候选要求双向各唯一匹配同一 war，并拒绝重复 key、空项、越界及不同借用对象。
3. 读取 war 侧 A `+48/+50`、侧 B `+78/+80` 的完整 handle 向量；不把它们未经证明地命名为攻方/守方。双方必须各在不同侧，所有成员的完整身份必须重新对应当前 country 对象。候选要求观察所有战争成员的政府字段，这是对原生实际谈判成员的保守超集；直属属国筛选、dependency `+121` 与全部辅助列表仍未复现。
4. 对识别出的 war `+160` goal 记录对象、虚表、`+58/+70/+78` 实际方法 RVA。`take_colony` 的 `+70` 读取 goal `+18` signed province index、`+30` province 指针、province `+24` DWORD marker；game `+1c90/+1c98` 得到省份数量，game `+1ca8` 为块起点，块步长 `0x2e10`，目标字段 `blocks + index*0x2e10 +560` 必须等于 province 指针。parser 检查这条地址算术；索引非法时禁止提供“已解引用”的块字段。
5. 若已识别 goal 的 `+70` 为假，真实路径改用 `2340030` 指向的 fallback goal。候选不沿用原 goal 的定义或条件；记录未知并停止相应解析。为真时，直接定义 `+10` 的四组条件容器为 `+50/+140/+288/+378`，各自 `+8` 指针、`+14` signed DWORD count、步长8。taker 在 A 侧选 `50/140`，否则 `288/378`；两种 flag 路径分别登记。记录每个 condition 对象、vtable、virtual `+30` 的实际地址，不执行虚函数，不从名称猜只读性。
6. 另行记录 `233ffd8 → registry+80 → definition` 的条件。parser 用容器基址 `definition+40` 表示此结构，因此真正指针/计数仍为 `+48/+54`，没有把指针偏移 `48` 错当 wrapper 基址。未知条件对象即使可读，也不算传递调用已审。
7. 记录两字节 TLS gate、模块索引及目标原生线程的 `GS:[58]` 数组来源。外部进程如何可靠取得该线程的 GS/TEB 与线程生命周期，本候选未实现；JSON 中的 `thread_id/gs58_array` 只是未认证元数据。不能使用 Python/注入工作线程的 TLS 替代未来原生调用线程。
8. 重读相同全部字段；两次捕获时段严格分开，任何差异或不完整记录拒绝生成“结构一致”结果。字段相同仍不排除期间析构重建、原址复用、异步改写或重入。暂停值只作诊断，即使为 false，本离线解析也不会授予任何执行能力。

## 离线合同与范围

`observer.py` 的 `parse(raw, contract)` 只接受精确字段集合；JSON 上限1MiB，禁止重复键、浮点数、NaN/Infinity、bool冒充int和额外权限字段。全局硬上限4096国家槽位；每侧最多64成员；每个战争索引最多64项；每个条件容器最多64项。上限是保守拒绝策略，不宣称引擎允许的最大值。缺页或不完整读取不能用0、null或空列表代替；只有原始字段确实为 null/空时才能如此编码。

字段定义由 `snapshot()` 的 `exact()` 调用给出；`test_observer.fixture()` 提供完整 synthetic 示例。`source_kind` 仅允许 `synthetic` 或 `external_capture_unverified`。目前未实现内存字节→已解码字段的生产者，因此 parser 的一致性结论不认证输入的真伪、句柄来源、TLS 来源或原始读取地址。当前测试不使用游戏数据。

`static-contract.json` 的 SHA 在 parser 中固定；单独篡改报告和输入中的 SHA 不能自洽绕过。生成器会在磁盘精确 EXE 上复核全部选中指令及示例虚表槽，再检查报告是否与候选字节一致。报告是有限静态证据，不是全程序纯度证明。

下列属性始终未知：war 的真正拥有者/析构同步、world epoch、原生调用线程来源、TLS/缓存跨调用稳定性、全部具体脚本条件的传递副作用、剩余辅助函数的全局写入、部分构造异常的所有权。静态已确认的 lazy cache、TLS 写入及诊断日志不能被暂停或双采样抹去。空条件列表仅跳过该处循环；默认拥有式 offer 的生命周期成功也不能代替这里的战争参数前提。

运行（只读磁盘与离线合成数据）：

```powershell
python -B work/candidates/peace-constructor-preconditions-ro-1375/prepare.py --check
python -B work/candidates/peace-constructor-preconditions-ro-1375/test_observer.py
```

没有构建 DLL、安装 hook、读取当前进程、调用游戏函数、修改 v14 或共享 support。
