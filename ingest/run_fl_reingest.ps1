# run_fl_reingest.ps1 - FL 修正锚点重灌全链（摘触发器→删FL→重灌→FTS rebuild→挂触发器→终验）
$ErrorActionPreference = "Stop"
$ing = "d:\S.Q\kyb-mcp-server\ingest"
$py  = "C:\Users\31720\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$log = "$ing\fl_reingest.log"

function Log($msg) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "$stamp  $msg" | Tee-Object -FilePath $log -Append
}

Log "==== FL reingest start ===="

Log "STEP 1 reset (drop triggers + delete us_fl)"
& $py -u "$ing\reset_fl.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Log "FATAL reset"; exit 1 }

Log "STEP 2 re-ingest FL (new anchors)"
py -V:3.10 "$ing\ingest_fl.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Log "FATAL FL"; exit 1 }

Log "STEP 3 FTS rebuild + triggers"
& $py -u "$ing\build_fts.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Log "FATAL FTS"; exit 1 }

Log "STEP 4 verify"
& $py -u "$ing\verify_ingest.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
Log "STEP 4 verify exit=$LASTEXITCODE"

Log "==== FL reingest done ===="
