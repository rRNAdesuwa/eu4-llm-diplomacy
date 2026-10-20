# CLI waiting scalar 审计修补

root 的独立反例 `work/reports/war-peace-api-20261015-r10-checkpoint/cli-pending-scalar-boundary-r1.json`（SHA `0d2d1496abb36298836045f22eaacc47412ee02ff15cc265e7e199668ef8b7c0`）证明旧 CLI 9c23… 将 ±2^40 的合成 native request ID 接受为 waiting/exit 3。

冻结 reply reader 的 native request ID 来自 `struct.unpack('<i', raw, 0x3c)`，域是 signed 32-bit，而不是 DWORD。此修补只收紧未封 CLI `proven_waiting`：row 和 reply 的 ID 都须 exact `int`、在 `[-2^31, 2^31)` 中，非零且相等。合法 `19`、`-1`、`-2^31`、`2^31-1` 保持 waiting；正负溢出、零、bool/float 及 projection 不一致保留 unknown/2。

原 CLI 9c23…、tests 9bfc…、CLI说明/runner 和 37 项回执精确前像在 `preaudit-cli-9c23/`；原 `cli-test-run.{json,log}` 未覆盖。新增 3 个测试方法，运行受影响 waiting 子集，不重跑整个 37 项或新总计 40 项 suite。独立 delta 回执在 `waiting-delta-run.{json,log}`，复现命令：

```powershell
& '${USERPROFILE}\AppData\Local\Programs\Python\Python312\python.exe' work/candidates/relation-request-observer-20261015/run_waiting_delta.py
```

已审 module 4bdd6e64…、其原 46 项与 DWORD 修补的 6 项回执、冻结 reader、public 98-pin/native 44-pin 图均不修改。此反例不会绕过真实 reader、native 权限或派发约束；本轮无游戏访问、请求或新效果。候选仍未封存，需等待独立 CLI 审计 ready。
