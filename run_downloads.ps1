# kyb downloads auto-resume on login.
# For each pipeline: skip if already running (process check), skip if done (flag check),
# otherwise launch its supervisor (supervisor itself loops the downloader until flag appears).
$exe = 'C:\Users\31720\AppData\Local\Python\bin\python.exe'
$base = 'd:\S.Q\kyb-mcp-server'

# all four downloads finished -> nothing to resume, no keepalive needed
$flags = @('done_uk.flag','done_sg.flag','done_au.flag','done_fl.flag')
if ((($flags | Where-Object { Test-Path "$base\data\$_" }).Count) -eq $flags.Count) { exit 0 }

# keepalive always launched (blocks Modern Standby)
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "$exe `"$base\_keepalive.py`"" } | Out-Null

$pipelines = @(
    @{ script = "$base\_dl_cor_heal.py";   flag = "$base\data\done_fl.flag"; marker = '_dl_cor_heal' },
    @{ script = "$base\_dl_au_par.py";     flag = "$base\data\done_au.flag"; marker = '_dl_au_par' },
    @{ script = "$base\_dl_uk_par.py";     flag = "$base\data\done_uk.flag"; marker = '_dl_uk_par' },
    @{ script = "$base\_pull_sg_par.py";   flag = "$base\data\done_sg.flag"; marker = '_pull_sg_par' }
)

# Collect command lines of running python processes (avoid double-launch)
$running = ''
try {
    $running = (Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object { $_.CommandLine }) -join ' '
} catch {}

foreach ($p in $pipelines) {
    if (Test-Path $p.flag) { continue }                                    # done
    if ($running -like ('*' + $p.marker + '*')) { continue }               # already running
    $cmd = "$exe `"$($p.script)`""
    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd } | Out-Null
}
