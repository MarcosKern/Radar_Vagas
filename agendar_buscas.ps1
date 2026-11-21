# Execute com PowerShell a partir da pasta do aplicativo (não requer admin).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command python.exe -ErrorAction Stop).Source }
$argument = if ((Split-Path $python -Leaf) -eq 'py.exe') { "-3 `"$root\monitor.py`" scan" } else { "`"$root\monitor.py`" scan" }
$action = New-ScheduledTaskAction -Execute $python -Argument $argument -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At 08:37
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName 'RadarDeVagas' -Action $action -Trigger $trigger -Settings $settings -Description 'Varredura diaria de vagas de TI' -Force | Out-Null
Write-Host 'Agendamento registrado: RadarDeVagas — diariamente as 08:37 (hora local).'
Write-Host 'Windows executa com a conta atual; para computador desligado ou execucao remota, configure GitHub Actions.'
