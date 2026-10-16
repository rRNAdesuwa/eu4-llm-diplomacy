# 外交行动实时效果观察器（1.37.5）

## 2026-10-15 统一入口增量

最终对外入口为`tools/eu4_observer.py`。15请求效果profile之外，新增联盟/联姻/保障的3个当前typed relation查询，保障反向明确区分；不是18个新请求效果profile。知识reader已通过现存3active与2absence实机正反验证，不计新API效果；组合HTTP13case通过、public CLI通过，详见[完整使用说明](runtime-observer-1375.md)。旧R1/R2/live/source manifest不变。

上一轮封存入口为`tools/eu4_runtime_observer_r2.py`，复用本文冻结R1/R2；当前使用上方最终入口。该轮新增严格知识reader v2与外交组合层，以及当前战争独立只读查询；新知识两pair当前absence实机、战争正反HTTP验收通过，均不是新外交派发。知识活动效果需发送前精确pair absence+完整原回执+新精确活动对象，不把总数变化当效果；机构完成仍false。34组合、19host、6入口回归测试通过。旧R1/R2源、manifest与journal保持；保存、重载用于单独持久化验证。

观察器直接读取游戏内存，将请求回执、发送前基线和当前选定状态关联起来。即时效果核验不需要保存或重进游戏；保存、冷重载另用于批次持久化验收。

下方冻结R1提供15个profile：13项可判断选定效果，旧知识分享的两个方向只提供诊断。最终入口使用独立新版知识reader，按精确双方活动对象和原请求证据判断，仍不能由总计数证明分享。其余动作明确返回unsupported；没有声称120项效果或宣战/议和全部完成。

## 状态含义

| 字段/值 | 含义 |
| --- | --- |
| transport_state=dispatched | 原生发送路径已消费命令；尚不等于接受或生效 |
| effect.status=observed | 对应profile要求的发送前后变化已观测 |
| completion_state=in_progress | 已确认启动吞并；不等于吞并完成 |
| completion_state=selected_effect_observed | 已确认取消任务、退出包围网等选定即时效果 |
| effect.status=not_observed | 当前有效样本尚未出现所需变化；不是失败或重发许可 |
| unknown | 缺基线、身份/回执不符、内存不可读或状态不稳定 |
| unsupported | 尚无该动作的已核验效果profile |

自然吞并完成、所有延迟副作用、AI接受、世界世代及持久化仍需要各自证据。工具不会用吞并索引消失推断吞并完成，也不会把读取失败解释为原生拒绝。

## CLI

在项目目录运行；session-file使用当前TAG后端生成的会话文件。

```powershell
python -B tools/observe_diplomacy.py catalog
python -B tools/observe_diplomacy.py --session-file <session.json> prepare --commands <new.commands.json>
# 然后通过现有TAG接口发布一次；测试继续使用 --test-only，既有禁重发规则保持。
python -B tools/observe_diplomacy.py --session-file <session.json> status --request-id <id> --compact
python -B tools/observe_diplomacy.py --session-file <session.json> watch --request-id <id> --duration-seconds 30 --compact
```

prepare只读取并保存基线，不发布请求；已预留请求不能倒补“实时发送前基线”。只有显式`--legacy-probe`可导入已有的完整双遍探针，保留原文件散列及来源类型。新测试应使用实时prepare。

status/watch不会注入DLL、执行游戏函数、保存游戏或重发动作。watch最多300秒，间隔250–10000毫秒；只有状态变化才打印。每次样本和判定保存在`work/runtime/effect-observations-v1/<process-session>/<request-hash>/`。退出码0表示观测到选定效果；吞并进行中也可在期限结束后返回0，绝非自然吞并完成。

基线与请求的PID、creation、session、完整国家句柄和请求内容必须一致。缺基线时仍可报告当前typed状态，但不会归因为该请求生效。即时资源与信任profile要求同一游戏日期，避免把月度自然变化误计为外交效果。

## 只读HTTP

设置本地环境变量`EU4_OBSERVER_TOKEN`（16–256个ASCII字符），再运行：

```powershell
python -B tools/observe_diplomacy.py --session-file <session.json> serve --port 8775
```

仅绑定127.0.0.1，使用Bearer token，拒绝Origin、无效Host和所有写方法。接口为：

- `GET /observer/v1/capabilities`
- `GET /observer/v1/effects/<request-id>`

该服务没有请求发布端点；基线由CLI准备。命令后端与观察器保持独立，读取失败不能触发自动重发。默认不启动持久服务。

## 实现与证明边界

`bridge/diplomacy_effect_observer.py`通过既有只读held handle取得进程身份，并使用独立受限VM_READ端口；没有放宽冻结PE-header reader的预算。每次重新解析国家、关系根、双向索引和对象，不保留跨样本裸对象指针。单次最多4096次/512KiB读取，每次≤64KiB，索引≤256项；两个完整样本相等才判定。

守卫包括精确EXE/PE、PID/creation、完整句柄valid byte7/selector0/signed slot、国家类型、关系根类型/owner/vector边界、双方依赖一致、手动暂停原始位、reset/load/cache-recalculation/ironman和alternate-player状态。运行中可采样；日期或状态在读取中变化时返回unknown。两个相等外部样本不是原子主线程快照，不能排除瞬时重建或ABA。

吞并任务从本次双向root+200索引重新解析，核对0x48对象的vtable1cde020、marker165、完整端点、开始日期和removed byte28。索引已无对象时不跟随历史地址；+29及其他未闭合字段没有业务命名。

`bridge/diplomacy_effect_profiles.py`为纯数据判定层，逐profile保留固定来源pin与限制。`bridge/diplomacy_observer_manifest_1375.json`固定20份实现/证据文件及默认原生manifest身份；`tools/build_effect_observer_manifest.py --check`核验来源。原始native回执的known_cleanup_complete=false按原样保留，不能用ownership_closed替代本地析构证明。

## 本轮实机验收

PID42600/creation01dd5bf010accac6，同一暂停日期1445.5.19。读取开始吞并和退出包围网的已派发请求，分别观测到typed吞并任务/in_progress及SAV完整句柄→哨兵，目标状态采集约48.6/37.2毫秒（完整CLI另包含进程与文件校验）。这两项导入已有的发送前双遍探针。

取消吞并使用新工具实时prepare，单次新请求派发后，watch从claimed/unknown转为dispatched/observed；双向任务移除，采集约32.6毫秒。观察过程native_calls=0、saves_written=0，没有保存重进；真正取消请求仍由原TAG后端执行一次。

相关84项检查通过：28个纯profile、32个字节级内存图及24个真实loopback HTTP测试。测试覆盖坏句柄、双向索引/typed任务、短读、状态变化、发送前基线竞态、鉴权与只读接口；这些离线检查不替代实机效果证据。

## R2：待处理请求与回复

独立入口`tools/observe_diplomacy_replies.py`保留R1效果判定，增加`ask_for_march`收件队列及通知关联。R1实现和manifest保持原样；R2另有`bridge/diplomacy_reply_observer_manifest_1375.json`，通过`python -B -m bridge.diplomacy_reply_observer --check`核验15份来源记录（含manifest本体）。

```powershell
python -B tools/observe_diplomacy_replies.py --session-file <session.json> --allow-tag-host status --request-id <id> --compact
python -B tools/observe_diplomacy_replies.py --session-file <session.json> --allow-tag-host watch --request-id <id> --duration-seconds 30 --compact
python -B tools/observe_diplomacy_replies.py --session-file <session.json> --allow-tag-host serve --port 8775
```

`--allow-tag-host`只允许已加载的精确默认build7模块，不会加载模块。HTTP沿用R1鉴权及只读路径，effects响应增加reply；capabilities仍描述R1效果profile，R2 CLI的catalog另列回复profile。退出码0表示选定效果，3表示等待收件人，2表示尚无选定效果或证据不足。

唯一匹配双方完整句柄、typed action和state0的收件节点才给出`request_state=waiting_for_recipient`；当R1效果尚未出现时，completion_state也显示等待。首次记录该节点会独占创建`reply-baseline.json`，保留原生请求号与通知地址集合。之后只把新出现、方向/类型/日期匹配的通知记为关联，不能用历史通知或队列消失推断接受/拒绝。完整捕获留在本地journal，HTTP仅返回选定节点、摘要、计数和散列。

实机已验证同一请求55的两阶段：回应前state0、type=vassal；通过正常游戏UI接受原请求一次后，当前队列无该节点且type=march、领主仍为完整FRA句柄。R1效果独立判为observed，没有通知可见时reply保持unknown。此处接受方是法国玩家界面，不能标为AI接受；没有重发、保存或重进。

R2新增37项纯测试通过，连同R1共121项。待处理与效果部分的实机采集分别约111.3/37.0毫秒；回应后约86.0/33.8毫秒，完整CLI另有身份和文件校验。真实loopback HTTP返回200及observed，原生派发audit散列保持不变，测试监听器已关闭。证据见`work/reports/diplomacy-reply-observer-20261015/live-verification.json`。
