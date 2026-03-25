$action = New-ScheduledTaskAction `
  -Execute 'C:\Users\JoeDB\AppData\Local\Programs\Python\Python313\python.exe' `
  -Argument '"C:\Users\JoeDB\OneDrive\Coding and statistical info\first algo and backtest\run_alerts.py"' `
  -WorkingDirectory 'C:\Users\JoeDB\OneDrive\Coding and statistical info\first algo and backtest'

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 4:30PM

$settings = New-ScheduledTaskSettingsSet `
  -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
  -StartWhenAvailable `
  -WakeToRun `
  -RunOnlyIfNetworkAvailable

Register-ScheduledTask -TaskName 'TradingAlerts' -Action $action -Trigger $trigger -Settings $settings -Force
