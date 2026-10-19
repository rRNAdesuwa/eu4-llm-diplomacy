# 宣战／议和 API 证据查找，第二版

本版提供50个已收录端点的纯文件查询。保留第一版43条记录，新增7条停战检查、关联取值和排除的状态写候选记录。每条返回地址、已证参数、正常返回范围、来源 JSON pointer 和未解条件。它不调用这些地址，不访问游戏进程、游戏 EXE、网络，也没有发送、分配或服务器命令。

在项目根目录运行：

```powershell
python -B work/candidates/war-peace-api-lookup-1375-v2/war_peace_lookup.py check
python -B work/candidates/war-peace-api-lookup-1375-v2/war_peace_lookup.py search truce --limit 10
python -B work/candidates/war-peace-api-lookup-1375-v2/war_peace_lookup.py lookup 从属定义取值
python -B work/candidates/war-peace-api-lookup-1375-v2/war_peace_lookup.py lookup 0xb1e020
python -B work/candidates/war-peace-api-lookup-1375-v2/war_peace_lookup.py lookup shared.literal_state_writer
```

退出0只表示文件核验或查询成功。所有 callable、native_ready、sender_authorized、gameplay_effect_verified、process_authenticated 始终为false。唯一历史R19 raw body实验仍限原第一版那条记录；本版查询自身的native_calls和requests_published均为0。没有新增外交效果或重发许可。

新增停战记录保留以下区别：

- 506d70会先调用关联条件；方向性pair缓存不能代替完整返回值，也没有证明停战期限。
- 3d79f0是已证direct CALL入口，位于pdata间隙；正常有效内存路径具体保留R9/R10。其数据流与冻结dependency reader仅条件对应，选定pair必须恰为C及C+18f0所指国家；旧sample_pair不会自动要求这个前提。原生没有该reader的完整类型、容量、端点和身份校验。
- b1e020的完整3421B owned字节已覆盖解码，正常返回路径的地址有界；INT3 terminal仍未闭合。正常返回段能保持先前AL，但外部调用、module写与未闭合alias写均保留。它不是已证只读、全输入终止或完整业务谓词。
- 6ec450是truce字符串追踪发现的状态写函数。input9条件路径会写receiver+2c及+40，因而作为排除的getter候选收录；显示或视图用途仍是推断。

本版精确编译固定SHA的第一版查询代码，复用其已审JSON、路径、证据pointer、来源前后核验和地址算术。第一版源码、数据、报告和测试回执不修改。新增固定数据清单由本版CLI内SHA绑定；不接受外部root、manifest或任意未收录地址。用户提供的可选base只用于条件VA算术，不认证实际模块或映射。

build_index.py是人工编目的作者脚本，按固定来源生成一次新索引，已存在文件时拒绝覆盖。CLI不会运行它。证据均为已保留静态合同，不能据此认定当前进程身份、对象保活或操作已执行。实时结果仍使用[运行时观察工具](../../../docs/runtime-observer-1375.md)；宣战、议和执行器尚未开放。
