$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$handlerPath = "$scriptDir\open-diff.ps1"

$regPath = "HKCU:\Software\Classes\taskrunner"
New-Item -Path $regPath -Force | Out-Null
Set-ItemProperty -Path $regPath -Name "(Default)" -Value "URL:Task Runner Protocol" -Force
Set-ItemProperty -Path $regPath -Name "URL Protocol" -Value "" -Force

$cmdPath = "$env:SystemRoot\System32\cmd.exe"
$command = "$cmdPath /c powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$handlerPath`" `"%1`""
New-Item -Path "$regPath\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$regPath\shell\open\command" -Name "(Default)" -Value $command -Force

Write-Host "taskrunner:// protocol registered"
Write-Host "Handler: $handlerPath"
