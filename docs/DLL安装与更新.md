# v9 DLL 自动宣战、和平条约与更新

**提示：以下操作均可直接让agent帮你做**


版本：`v9 experimental`，DLL：`eu4_bridge_automated_diplomacy_v9.dll`。
DLL SHA-256：`1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3`。

v9 在 v7 和平锁与授权议和的基础上加入同一游戏进程内的固定宣战流程：

- 对涉及法国（FRA）的未授权已识别原生和平动作进行拦截；桥接构造并授权传播的和平动作提交原生引擎。
- 通过固定脚本让法国（FRA）向英国（ENG）使用 `cb_core`、目标省份 `177` 宣战，然后在同一进程中完成白和平。
- 保留 v7 已验证的 FRA → ENG 金币赔款路径；v9 当前同进程验收默认使用白和平。

当前没有接入真实 LLM；宣战、白和平和金币请求由本地 Python 入口创建标记文件，再由 DLL 在游戏帧中处理。v9 已完成同进程“固定宣战→实验战争分→授权白和平”的验收；自然战争分接受、v9 保存重载和玩家控制法国仍是后续实验。v7 金币赔款的保存重载结果单独保留。

现有 `release/` 目录中的旧发布包仍按 v7 元数据管理；本文说明的是当前源码中的 v9 实验 DLL。

## 1. 发布包和准备

接收者自行操作自己的电脑。作者不会远程执行程序；解压包不会自动启动游戏、自动注入 DLL 或创建请求。

- Windows x64、64 位 Python 3.10 或更高版本。加载器只使用 Python 标准库。
- EU4 可执行文件必须是经过适配的 1.37.4 构建，SHA-256 必须为：

  `B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77`

  只看游戏显示的版本号不够；哈希不匹配时不要绕过检查。
- 将完整 ZIP 解压到可写且路径较短的独立目录，保留 `tools`、`work`、`release`、`docs` 的层级。不要把 DLL 复制到游戏目录，也不要使用 `regsvr32`。




## 2. v9 实验入口

在项目根目录、已按[路径配置](路径配置.md)载入本地配置后，启动 v9：

```powershell
.\work\native\start-automated-diplomacy.ps1 -SavedTestGame
$GamePid = (Get-Process -Name eu4).Id
& $Python -B .\tools\run_diplomacy_cycle.py `
    --pid $GamePid `
    --test-winwars
```

该入口会安装 v9 DLL，固定执行 FRA→ENG 宣战，等待外交官和关系冷却，再提交授权白和平。金币实验使用：

```powershell
& $Python -B .\tools\request_diplomacy.py gold --pid $GamePid
```

日志、请求文件和人工操作说明见[《人工实验与日志读取流程》](人工实验与日志读取流程.md)。

## 3. 为什么哈希必须一致及多游戏版本配置

这个 SHA-256 是对整个 `eu4.exe` 文件计算出的版本指纹。DLL 的 C++ 代码本身没有把 SHA-256 字符串作为业务条件，但它使用同一构建的固定地址和机器码签名；绕过 Python 哈希检查不会使它变成跨版本 DLL，反而可能导致提前失败、错误读写或游戏崩溃。哈希不同可以让agent帮你完成完整修改。

要支持多个游戏版本，应建立“游戏哈希 → 对应 RVA、机器码签名、DLL 和验收记录”的版本配置。示意结构如下：

```json
{
  "profiles": {
    "<eu4.exe-sha256>": {
      "game_version": "1.37.4",
      "dll": "eu4_bridge_automated_diplomacy_v9.dll",
      "rva_profile": "eu4-1.37.4.json",
      "signature_profile": "eu4-1.37.4.bin",
      "status": "validated"
    }
  }
}
```

启动时先计算 `eu4.exe` 哈希，再选择唯一匹配的 profile；profile 中的 RVA、签名和 DLL 必须成套使用。新增 1.37.x、Steam/GOG 构建或其他补丁时，流程是：取得新 exe → 计算哈希 → 重新确认函数和 vtable → 生成新的 RVA/签名 profile → 编译独立 DLL → 在新进程和实验存档中验证 → 再把该 profile 发布。不能只把旧 profile 的哈希字符串改成新值。

当前发布包仍只有一个已验证 profile。哈希不匹配时应停止，而不是自动选择最接近的版本。

## 4. 让 Agent 协助修改哈希

其他电脑的使用者可以让 Agent 协助维护版本配置，但应让 Agent 先做只读检查并保留备份。可以提供目标 `eu4.exe` 路径、当前包或源码目录，以及希望支持的游戏版本，并明确要求：

1. 计算目标 exe 的 SHA-256，并与现有 profile 比较；
2. 如果只是同一个 exe 换了安装目录，只更新本地路径，不改哈希；
3. 如果哈希不同，先判断是否已有对应 RVA/签名/DLL profile；
4. 只有新构建完成静态检查、编译和实际验收后，才更新 `EXPECTED_HASH`、版本元数据、文档和发布包；
5. 记录新旧哈希、DLL 哈希、验证结果，并保留旧版本回退包。

可直接把下面的请求发给 Agent：

```text
请在这个项目中支持我的 EU4 构建：<eu4.exe 路径>。
先只读计算 SHA-256，并检查现有版本 profile、RVA、机器码签名和 DLL 是否匹配。
如果只是路径不同，请只调整本地路径配置；如果是新构建，请不要只替换哈希，先列出需要重新分析的 RVA/签名并完成验证。
确认兼容后，再更新 EXPECTED_HASH、release 元数据、文档和版本包，并报告每个文件的改动和测试结果。
```

Agent 可以帮助计算、修改和打包这些文件，但“哈希修改成功”只代表门禁配置改变，不代表 DLL 已经兼容。若没有新的地址分析和游戏内验收，应保留拒绝加载状态。

想要手动跑通一遍“安装 v9 DLL—自动宣战—授权议和”的流程，可参见
[《人工实验与日志读取流程》](人工实验与日志读取流程.md)。agent配合在其指示下的少量人工操作也可以方便地完成整个流程。
