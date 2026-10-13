<#
.SYNOPSIS
  AI Usage Hub 에이전트를 Windows 로그인 시 자동 실행(창 없음)되도록 작업 스케줄러에 등록한다.

.DESCRIPTION
  먼저 대시보드 설정 → 기기 관리에서 기기를 등록하고, 안내된 명령으로 사용자 환경변수
  AIHUB_URL, AIHUB_DEVICE_TOKEN 을 설정해야 한다.

.EXAMPLE
  cd <저장소>\backend
  powershell -ExecutionPolicy Bypass -File .\collector\install-agent.ps1
  powershell -ExecutionPolicy Bypass -File .\collector\install-agent.ps1 -Uninstall
#>
param(
    [switch]$Uninstall,
    [string]$TaskName = "AI Usage Hub Agent"
)
$ErrorActionPreference = "Stop"

if ($Uninstall) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "작업을 삭제했습니다: $TaskName"
    return
}

$backendDir = Split-Path -Parent $PSScriptRoot
$uvw = (Get-Command uvw -ErrorAction SilentlyContinue).Source
if (-not $uvw) {
    throw "uvw.exe 를 찾을 수 없습니다. uv 를 설치하세요: https://docs.astral.sh/uv/"
}
foreach ($name in "AIHUB_URL", "AIHUB_DEVICE_TOKEN") {
    if (-not [Environment]::GetEnvironmentVariable($name, "User")) {
        throw "사용자 환경변수 $name 이(가) 없습니다. 설정 → 기기 관리에서 기기를 등록할 때 표시된 명령을 먼저 실행하세요."
    }
}

# --no-project: 에이전트는 표준 라이브러리만 쓰므로 백엔드 의존성을 설치하지 않는다
$action = New-ScheduledTaskAction -Execute $uvw -Argument "run --no-project python -m collector.agent" -WorkingDirectory $backendDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

# 재설치(토큰 재발급 후 등) 시 이전 토큰으로 돌던 에이전트를 멈추고 새 설정으로 다시 시작한다
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Claude Code·Codex 토큰 사용량을 AI Usage Hub 로 업로드" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "등록 완료: 로그인할 때마다 자동으로 실행되며, 지금 바로 시작했습니다."
Write-Host "실행 로그: $env:USERPROFILE\.aihub\agent.log"
Write-Host "삭제: powershell -ExecutionPolicy Bypass -File .\collector\install-agent.ps1 -Uninstall"
