# 1.37.5 和平窗口发送与所有权

这份报告闭合了本机精确构建的 `send` 按钮绑定、原生回调、独立和约克隆及 command 移交。仅分析磁盘 PE，没有读取进程、调用原生函数、发送外交或修改冻结研究 DLL。`runtime_verified=false`，`execution_verified=false`。

- 游戏 SHA256：`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`
- [机器报告](../work/reports/native-peace-gui-send-1375.json) SHA256：`1aa1be072578a2c3f21e432ba6c0928ab01d9920d85063060a91512e9a882b64`
- [生成器](../work/trace_peace_gui_send_1375.py)：`python -B work/trace_peace_gui_send_1375.py --check`
- 输入 [owned peace 生命周期报告](native-owned-peace-1375.md) 的 SHA256 固定为 `f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d`，没有更改那份报告。
- 11 个函数，5,426 字节解码；每函数最多 2,000 条指令、窗口 8 KiB，总预算 32 KiB，内存上限保护 768 MiB。

## 按钮绑定

解包本体 `interface/peaceview.gui:454–463` 声明 `name="send"`、`buttonText="SEND_OFFER"`；源文件 SHA256 为 `821c09cc2cc83dd1239a6a2fe0302f1cca74210b5619448dc85b974c80980e18`。

GUI 构造 `1309320` 在 `13096a8..13096bd` 设置 listener：

| GUI 偏移 | 值 |
| --- | --- |
| `+668` | listener 虚表 `1cb80c8` |
| `+670` | GUI 自身指针，即 listener 的 owner `+8` |
| `+678` | 回调 `130f1b0`，即 listener 的 callback `+10` |

初始化 `1309b70` 在 `1309fa8` 取这份 listener，`1309faf` 引用字符串 `send`（`1d593cc`），通过 GUI root 的 `+68` 虚槽查控件，检查重复后在 `1309fe7` 注册到 button `+c8` 的 listener 列表。listener 虚槽 `+18=836430` 取 callback `+10`，将 owner `+8` 作为 RCX 并尾跳至回调。这里没有把旧版本的 `130f080` 地址直接套用。

## 真正发送回调

`130f1b0` 接收 GUI，先分配原件 `requestpeace`，大小 `0x210`，再调用 `598af0` 构造：

| 参数 | 实际来源 |
| --- | --- |
| actor | game `+1e60` 的有效国家句柄；仅 `+1e66==7 && +1e6f!=0` 时取 `+1e68` |
| target | GUI `+2c` |
| demand | GUI `+660` |
| offer | demand 为真时 GUI `+48`，否则 GUI `+208` |
| date | game `+1dd0` |

有效国家句柄的来源与 game.player `+1da0` 不同，不能混称同一个字段。构造函数经 `975f40` 深复制选中的完整 `CPeaceOffer` 到原件 `+48`；`diplomats+40=1`，`force+208=0`。

回调取得原生理由缓冲对象、清空并保证 40 条记录容量，然后调用 action 虚槽 `+120=59bee0`，第三参数为 false。返回值大于等于 1 时，回调设置原件 `+208=1`。此槽包含 game `+23a1` 条件分支及已有 force 分支；普通分支调用 `1bf150` 计算。这里只记录精确原生 UI 规则，**没有把分数或 force 标志称为 AI 接受，也没有开放强制接受参数**。

发送前还保留原生日期门槛：actor 与 game.player 的 slot 相同才检查 game `+1d9c`；任何 actor 都要求当前日期大于国家 `+24a0`。失败时跳过包装与提交，仍释放原件。原生这里使用 slot 比较，不足以替代未来外部接口的完整句柄及 world epoch 检查。

## 三份独立对象与移交

```text
GUI 中完整 CPeaceOffer
  └─ 598af0 → 975f40 深复制
       原始 requestpeace（0x210，嵌入 offer +48）
         └─ 4e9930 → virtual+b0=59ba40 → 975f40 深复制
              command（0x58）+50 拥有另一份 requestpeace 克隆
```

`130f307` 调 `4e9930` 包装原件。包装器经 action `+b0` 克隆完整 requestpeace，原生 clone `59ba40` 另分配 `0x210` 并深复制嵌入和约；新 command `+50` 拥有它。GUI 和约、原件和约、command 克隆和约是三份独立实例。

回调从 `GUI+978 → +330 → +370` 取 context，在 `130f312` 调 `14ca210(context, &command)`。后者一进入就取出并清空 caller 容器；通过 context/command 门槛才调用 transport 虚槽 `+30`。返回 true 仅表示该调用已返回，不能证明执行器消费、外交接受或和约生效。回调忽略这个 bool，随后继续 UI 收尾。

context 的早期拒绝路径也已消费 caller 容器，且该函数没有展示每一条拒绝路径都删除局部持有的 command。因此不能在进入该函数后根据 false 自行析构或重试；沿用既有引擎的未知所有权冻结边界。

正常回调尾部 `130f323..130f34d` 清理原件 `+48`，然后释放原件的 `0x210` 分配。它没有再删除 command 的克隆。command 析构 `4e7470` 在 action 虚槽 `+a8` 为 false 时调用 action deleting destructor；requestpeace 该槽确为 false leaf `8f450`，故 command 负责其克隆及嵌入和约的清理。

## 尚未闭合

这次补齐发送回调和普通返回路径的所有权，不替代运行期 ABI、分配失败与 SEH 中途展开验收。未枚举完整输入设备到控件事件的派发链，也未追踪 transport 环消费与最终和平执行。战争身份、条款合法性、AI 回复、结算、保存重载及可靠 world epoch 仍须各自证明。所有证据仍为静态，不增加外部执行能力。
