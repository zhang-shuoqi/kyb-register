
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*_dl_au*' } |
  ForEach-Object { Write-Output ("killed " + $_.ProcessId); Stop-Process -Id $_.Id -Force }
