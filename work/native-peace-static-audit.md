# EU4 1.37.4 原生议和静态审计

审计根目录：`EU4_GAME_ROOT`。本报告只读检索原版文本与 GUI；未启动游戏、未操作 UI、未修改模组。

## 结论

- 原版确实登记了内建外交动作 `requestpeace`，但它只出现在 `static_actions` 注册表：`common/new_diplomatic_actions/00_diplomatic_actions.txt:3-6`；旧外交动作文件仅把 `requestpeace` 列在注释清单中：`common/diplomatic_actions/00_diplomatic_actions.txt:21-24`。没有可由事件/决策/脚本效果调用的发送和平提议 effect 定义。
- 原版和平窗口的发送路线是 GUI 控件名交给游戏代码处理：`interface/waroverview.gui:192-220` 的 `goto_peace_view`、`interface/peaceview.gui:421-463` 的 `reset_button`、`suggest_peace_button`、`surrender_button`、`send`。这些块只有 `name`、贴图、文本、快捷键/音效等属性，没有 `on_click`、`action`、`script` 或 effect 绑定（对 `peaceview.gui`、`peace.gui`、`waroverview.gui` 检索无匹配）。因此按钮名可供原生代码识别，但不是可在脚本中复用的命令接口。
- `interface/countrydiplomacyview.gfx:495` 只有 `GFX_diplomacy_action_requestpeace` 图标；外交动作列表是动态填充的，`countrydiplomacyview.gui:2010-2066` 的 `diploactionentry` 只定义通用行和 `ai_accept` 指示图标。没有 `requestpeace` 的脚本 body 或独立 GUI 点击脚本。
- `common/peace_treaties/00_peace_treaties.txt:1-61` 及同目录文件是“完全脚本化和平条款”的定义层，字段是 `is_visible`、`is_allowed`、`effect`、`ai_weight`、战争分数/外交点数成本等；没有 `send`、`accept`、`decline` 或提议队列入口。原版标准条款（白和、割地等）也没有对应的可调用脚本定义。`ai_weight` 是条款选择权重，不是玩家发送或 AI 接受函数。
- `common/new_diplomatic_actions/00_diplomatic_actions.txt:62-176` 的注释模板确实展示了自定义外交动作的 `require_acceptance`、`on_accept`、`on_decline`、`ai_acceptance`，并明确注释“AI will currently never send them”；这套接口属于自定义外交动作，不能据此推导和平提议可调用入口，也没有出现在 `peace_treaties` 定义里。
- 可脚本化的和平相关内容主要是结果回调/条款效果：`common/on_actions/00_on_actions.txt:182-200` 提供 `on_peace_actor`/`on_peace_recipient`（后者为空），`common/peace_treaties/00_establish_trade_protectorate.txt:31-40` 中的 `white_peace = PREV` 是条款执行期间结束其他战争的效果。它们不发送提议，也不进入原生接受算法。

## 对“保留原生 AI 接受算法”的判断

当前静态文件没有把原生“发送提议→AI 接受/拒绝→执行条款”的中间接口暴露给脚本。已确认能保留原生算法的路线是让玩家手动使用上述原生战争总览/和平窗口；内建 `requestpeace` 是另一个应由用户手动确认是否打开同一窗口的候选入口。不能从 `peace_treaties`、事件、决策或 GUI 文本中构造可调用的发送提议 effect/命令。二进制内部序列化名不构成脚本命令证据。

## 候选手动测试（用户操作）

1. 在普通双边战争中手动打开战争总览，点击原生“Offer Peace”入口（`goto_peace_view`），选择白和或低成本条款，点击 `send`，等待原生 AI 的接受/拒绝结果。记录是否出现与普通游戏一致的提议通知/响应。
2. 在同一战争中从目标国家外交动作列表检查 `requestpeace`/求和图标入口（其图标资源是 `GFX_diplomacy_action_requestpeace`），若该入口可见，手动打开并与步骤 1 发送相同条款，比较是否进入同一 `peace_view` 和同一 AI 处理路径。
3. 若后续需要验证“自定义条款能否走原生窗口”，在测试模组中仅增加一个明确 `is_visible`、`is_allowed`、`effect`、`ai_weight` 的和平条款，并由 CB 的 `can_use_peace_treaty` 允许它（原版唯一静态引用见 `common/cb_types/00_cb_types.txt:1533-1537`）；然后仍由用户手动在原生和平窗口发送，观察该条款是否被原生 AI 接受/拒绝。此测试验证的是条款接入，不证明存在脚本发送 API。

不要把直接执行 `white_peace` 或其他战争结束 effect 当作议和提议测试：那会绕过提议与 AI 接受阶段。
