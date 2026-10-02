# Starts the bot VM automatically when you log in to Windows.
# Run once in PowerShell (no admin needed):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\autostart-vm.ps1
# Remove it again with:
#   Unregister-ScheduledTask -TaskName "skillbot VM" -Confirm:$false
param(
    [string]$VmName = "skillbot",
    [int]$DelaySeconds = 60
)

$vbox = Join-Path $env:ProgramFiles "Oracle\VirtualBox\VBoxManage.exe"
if (-not (Test-Path $vbox)) {
    throw "VBoxManage.exe not found at $vbox - is VirtualBox installed in the default folder?"
}
& $vbox showvminfo $VmName --machinereadable | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "No VirtualBox VM named '$VmName'. Pass -VmName with the name you used."
}

# --type headless: runs without a window; open it any time from VirtualBox with "Show".
$action = New-ScheduledTaskAction -Execute $vbox -Argument "startvm `"$VmName`" --type headless"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT$($DelaySeconds)S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "skillbot VM" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Starts the skillbot VirtualBox VM at logon" -Force | Out-Null

Write-Host "Done: the '$VmName' VM will start $DelaySeconds seconds after you log in to Windows."
