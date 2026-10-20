# EU4 1.37.4：启动时载入指定存档

记录日期：2026-10-05。用途：供其他 agent 在后续独立测试中使用。

## 结论与验证状态

本机 `eu4.exe` 的静态反汇编确认存在 `continue` 启动参数：读取参数值，添加 `save games/` 前缀，并将路径交给原生加载流程。建议首次验证使用：

```text
eu4.exe -enabletelemetry -gdpr-compliant -continue=llm_ai_peace_before.eu4
```

**2026-10-05 已实测启动指定基线存档。** 新进程参数含 `-continue=llm_ai_peace_before.eu4`；用户确认进入暂停地图。只读探针确认 player=POR、FRA/ENG 完整句柄、current_raw_date=56461776，与基线 1445.5.30 对应。证据：`runtime/startup-continue-native-state-20261005.json`、`runtime/authorized-peace-baseline-20261005.json`。启动遇到“模组修改无法获得成就”提示，需要用户点击确认；因此当前流程仍有人工弹窗确认步骤。尚未验收其他文件名及和平结果重载。

本方法用于启动新游戏进程，不能向已运行的游戏追加参数，也不是控制台命令。运行中不关闭游戏切换存档的原生接口仍在研究。

## 本机路径与版本

- 游戏：`EU4_GAME_ROOT\eu4.exe`（由 `local.env` 指定）
- 测试版本 SHA-256：`B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77`
- 本机用户目录：`EU4_USER_DATA`（由 `local.env` 指定）
- 示例目标：用户目录下的 `save games\llm_ai_peace_before.eu4`

参数值应为存档文件名，包含 `.eu4`。示例传 `llm_ai_peace_before.eu4`，不传绝对路径，也不重复传 `save games/`。因为该分支会自行加此前缀。首次验证优先使用已有 ASCII、无空格文件名；带空格、中文、子目录和云存档的处理尚未验证。

## 后续测试用 PowerShell 示例（本次没有执行）

仅在当前游戏已正常退出、其他 agent 的测试已经结束后执行。示例拒绝在存在 EU4 进程时启动，不关闭或终止任何现有进程。

```powershell
. .\work\native\import-local-env.ps1
Import-ProjectLocalEnv -ProjectRoot (Get-Location).Path
$gameExe = Join-Path $env:EU4_GAME_ROOT 'eu4.exe'
$saveName = 'llm_ai_peace_before.eu4'
$saveRoot = Join-Path $env:EU4_USER_DATA 'save games'
$expectedHash = 'B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77'

if (Get-Process -Name eu4 -ErrorAction SilentlyContinue) {
    throw 'EU4 is already running; leave the current test process untouched.'
}
if (-not (Test-Path -LiteralPath (Join-Path $saveRoot $saveName) -PathType Leaf)) {
    throw 'Target save does not exist.'
}
if ((Get-FileHash -LiteralPath $gameExe -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Executable differs from the statically reviewed build.'
}

Start-Process -FilePath $gameExe `
    -WorkingDirectory (Split-Path -Parent $gameExe) `
    -ArgumentList '-enabletelemetry -gdpr-compliant -continue=llm_ai_peace_before.eu4' `
    -WindowStyle Normal -PassThru
```

此示例的 `$saveName` 与 `-ArgumentList` 中的文件名须一起修改。保留的两个原参数来自 `runtime/game-launch.json`；若后续启动配置发生变化，应保留当时所需的原参数，并追加一个 `-continue=文件名`。不要同时传 `-continuelastsave`，该分支先处理最近存档，可能使显式指定存档分支被跳过。

`native/restart-game.ps1` 现已增加 `-SaveName`：例如 `-SavedTestGame -SaveName llm_ai_peace_before.eu4`。它校验文件存在，保留其他原启动参数，移除旧 continue/continuelastsave 参数，再追加指定目标。该脚本会关闭当前实验进程，仅在已授权的实验重启中使用；不要打断其他 agent 正在进行的测试。

## 另一入口：继续最近存档

`-continuelastsave` 分支读取用户目录的 `continue_game.json`，取其中 `filename` 字段作为加载路径。本次读取时，该字段为 `save games/llm_ai_peace_before.eu4`；这是当时的文件内容，不保证后续仍相同。

指定任意存档优先使用 `-continue=文件名`，不需要重写 `continue_game.json`。仅修改该 JSON 也不能让已运行游戏立即读档。

## 静态证据（均为模块 RVA）

| 位置 | 观察到的行为 |
|---|---|
| `0x1719050` → `0x1719230` | 启动参数解析；状态机处理 `-`、`=` 和引号 |
| `0x876588` | 引用 `continuelastsave`，检查该参数是否存在 |
| `0x8766B6` → `0x5D16A0` | 读取 `continue_game.json`；成功后设置继续加载标志并复制 filename |
| `0x876883`–`0x87688A` | 若继续加载标志已经设置，跳过显式 continue 参数处理 |
| `0x876895`–`0x8768A6` | 获取 `continue` 参数值 |
| `0x8768DD`–`0x87692D` | 构造 `save games/` 前缀，追加参数值，写入全局路径字符串 `0x1FD3A08` |
| `0x204BBE`–`0x204BC6` | 路径字符串非空时进入加载分支 |
| `0x204ECA`–`0x204ED4` | 将全局路径传给原生函数 `0x2111F0` |

这些地址仅适用于上述哈希的本机二进制。记录地址用于复核，不表示可以从任意线程直接调用加载函数。

## 首次实测验收

1. 在其他测试完成后，使用独立测试存档启动；不覆盖基线存档，不自动发送外交或控制台请求。
2. 核对实际加载的玩家国家、日期和战争状态与目标存档一致；不要仅依据窗口出现或进程存活判断读档成功。
3. 记录是否经过选国页面、是否需要额外确认，以及加载后是否暂停。需要额外操作时，分别记录，不能宣称已完成无人值守加载。
4. 如需安装诊断 DLL，在确认读档完成后另行执行对应流程；启动参数不会自动安装 DLL。
5. 将实测结果和失败条件补充到本文件；实测前保留“仅静态确认”状态。

本记录来自离线读取本机 exe、界面文件及已有文档，没有启动游戏、操作进程、注入 DLL 或修改用户存档与配置。
