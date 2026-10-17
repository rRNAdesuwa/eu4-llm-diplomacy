$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$taskReportPath = Join-Path $taskRoot 'work/runtime/diplomacy-goal-session-20261013.json'
$taskSession = Get-Content -LiteralPath $taskReportPath -Raw | ConvertFrom-Json
if ($taskSession.model -ne 'gpt-6.1-sol' -or $taskSession.reasoning_effort -ne 'max' -or $taskSession.goal_status -ne 'active') {
    throw 'The prepared session does not match GPT-6.1 Sol Max with an active Goal.'
}
if ($taskSession.started) {
    throw 'This session was already launched. Resume its existing window instead of submitting the startup task twice.'
}
$Host.UI.RawUI.WindowTitle = 'EU4 外交系统开发 · GPT-6.1 Sol Max · Goal'
Set-Location -LiteralPath $taskRoot
$taskText = [System.IO.File]::ReadAllText($taskSession.prompt, [System.Text.Encoding]::UTF8)
$taskInput = "该线程已经设置了持久化 Goal，状态为 active。先读取当前 Goal，沿它开始实际开发，不创建重复目标，不因完成文档而结束。以下是用户批准的完整任务：`n`n" + $taskText
$taskSession.started = $true
$taskSession | Add-Member -NotePropertyName window_pid -NotePropertyValue $PID -Force
$taskSession | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $taskReportPath -Encoding UTF8
& $taskSession.codex --no-daemon --enable goals --approve-for-me --search resume $taskSession.thread_id -C $taskRoot -m gpt-6.1-sol -c 'model_reasoning_effort="max"' $taskInput
if ($LASTEXITCODE -ne 0) {
    Write-Host "Codex exited with code $LASTEXITCODE. Session: $($taskSession.thread_id)" -ForegroundColor Red
}
