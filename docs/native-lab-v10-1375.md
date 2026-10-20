# v10 外交扩展研究候选（1.37.5）

v10 为独立离线构建候选，目前没有运行验证，也没有注册为生产外交后端。原 v9 的十个 ID 保留，新增七个原生 family、十四个正反 ID，共二十四个研究入口。研究宿主、线程/世界守卫、永久 claim、TTL、所有权转移和异常冻结流程沿用 v9；旧版本原生源码、DLL、manifest 与测试事件均未修改。

| 原生 family | 正向 ID | 反向 ID | 构造大小 |
| --- | --- | --- | --- |
| allianceaction | offer_alliance | dissolve_alliance | 64 |
| milaccess | ask_military_access | cancel_military_access | 64 |
| offermilaccess | offer_military_access | revoke_military_access | 64 |
| fleet_access | ask_fleet_basing_rights | cancel_fleet_basing_rights | 64 |
| offer_fleet_access | offer_fleet_basing_rights | revoke_fleet_basing_rights | 64 |
| embargoaction | embargo | revoke_embargo | 64 |
| warsubsidy | give_subsidies | cancel_subsidies | 72 |

补贴仅支持固定研究参数：每月 **1.000** 金币、**10 年**。action `+0x40` 的有符号整数为 1000，`+0x44` 为 10；没有外部金额、原始字段或月数参数。金额并非整数 1，期限也不是 120 月。取消仅允许付款方对应的现有 1.000/10 年合同；其它合同保守拒绝。CLI 的计划与离线候选能力明确列出这些固定参数，原生日志与证据验证器也核对两项常量。

三个无发送阶段分别要求十二个 factory/clone/dtor 生命周期案例、四十八个预览案例、四十八个 command wrapper/gate/dtor 案例。预览与 command 矩阵为十二类 × 正反模式 × FRA→ENG/POR；包含旧二十项和新二十八项。补贴先核对 factory 的零默认值，再在自己拥有的临时 action 中写入非零 1000/10，核对 clone 的实际字段复制。command 仍由析构函数释放其专有 clone，原 action 独立销毁；没有单独释放 owned clone。

所有新增 family 钉扎构造分支、clone、派生析构、通用 wrapper 和模式 setter 的前缀，以及对应虚表槽。补贴使用 0x129500 的 72 字节析构路径。当前磁盘检查逐一验证了 72 个函数前缀和 112 个虚表槽。

取消通行时分别核对权利持有国和授予国索引，双边必须指向同一个未移除对象，两个完整 handle 必须符合请求方向；`enforce_peace` 变体保守拒绝。同盟接受双方对象 handle 的任一对称顺序。撤销禁运只接受 actor→target 的 `record+0x46 & 0x02`，不将反向禁运或 dirty 位当成己方禁运。取消时的关系对象和开始日期在 setter 前后、提交前重新比较。普通原生合法性检查继续执行，没有强制接受或跳过冷却。

协议仍为 EU4LAB/2，purpose 为 `restricted_pair_lab_1375_v10`。所有原生源码位于 `work/native/v10/` 和 `work/native/test-fixture-v10-1375.{h,cpp}`；manifest 固定十四个原生源。输出为 `work/runtime/native1375-v10/`。新增 Python/CLI 工具仅导入 v10 协议；原共享后端仍维持原十项，v9 HTTP 也不会自动扩展。

测试事件使用与 v9 **完全相同**的五个文件、`1375_test_fixture_v3` profile 与 SHA256 `f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507`，仅复制到独立 `work/candidates/fixture-v10-1375/`。安装校验仍读取实际用户 mod 目录、文件哈希、启动前时间和启用配置。fixture_on 继续要求当前 NAV 独立、无双方休战且无同盟。磁盘启动白名单仍只有原 baseline 与 after_improve；白名单不证明当前世界状态。

已完成 /W4 /WX 编译、102 项 C++ 请求语法检查、101 项纯合成内存字段/方向检查，以及 30 项 v10 Python 离线协议和证据验证测试。此类检查不执行游戏原生函数，不证明外交行为已经发生。成功传递 command 也仍只报告 dispatched，不能代替独立关系观察、AI 回复和保存重载验收。新增同盟及四类通行的原生 AI 回复需求没有被跳过；效果观察器由独立静态报告和只读工具另行验证。

复现命令（仓库目录，均为离线）：

```powershell
python -B work/candidates/v10-build-review/prepare_build.py --check
python -B work/candidates/v10-build-review/check_pins.py
work/native/v10/build-lab-1375.cmd
work/native/v10/test-lab-request-1375.cmd
work/candidates/v10-build-review/test_extension.cmd
python -B -m unittest bridge.tests.test_diplomacy_lab_v10 -q
python -B -c "from work.native.lab_protocol_v10_1375 import verify_build; print(verify_build()[1])"
```

静态构造依据为 `work/reports/native-pair-extension-v10-1375.json`（SHA256 `0c1731b0b29b296da73dc406fb31544ada59c17c275d17d623677b16998698bd`）。关系效果与方向补充证据为独立的 `work/reports/native-pair-extension-effects-v10-1375.json`（SHA256 `b6f4b69db38f5e3eae0c3cebf1fa5298701b86a98e8299d6f0e9759b84861f62`）；它支持取消守卫，仍不代表运行验收。`work/candidates/v10-build-review/` 保存生成器、六十份冻结文件哈希、版本名归一后的原生差异及磁盘 pin 核验结果。当前构建和测试结果由该目录的 `validation.json` 记录。未安装、启动、注入、发布任何请求或读取游戏进程。
