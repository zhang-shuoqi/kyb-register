# run_ingest.ps1 - 全量入库总控（坏了重建：先删库，再直线灌入四国，最后建 FTS + 验收）
# 日志：ingest\ingest.log（UTF-8）
$ErrorActionPreference = "Stop"
$ing = "d:\S.Q\kyb-mcp-server\ingest"
$py  = "C:\Users\31720\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$db  = "d:\S.Q\kyb-mcp-server\data\kyb.db"
$log = "$ing\ingest.log"

function Log($msg) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "$stamp  $msg" | Tee-Object -FilePath $log -Append
}

Log "==== run_ingest start ===="

# 0) 删库重建（含 WAL 边车文件）
Remove-Item -Force -ErrorAction SilentlyContinue $db, "$db-wal", "$db-shm"
Log "old kyb.db removed (fresh start)"

# 1) UK
Log "STEP UK begin"
& $py "$ing\ingest_uk.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
Log "STEP UK end (exit=$LASTEXITCODE)"
if ($LASTEXITCODE -ne 0) { Log "FATAL UK"; exit 1 }

# 2) SG
Log "STEP SG begin"
& $py "$ing\ingest_sg.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
Log "STEP SG end (exit=$LASTEXITCODE)"
if ($LASTEXITCODE -ne 0) { Log "FATAL SG"; exit 1 }

# 3) AU
Log "STEP AU begin"
& $py "$ing\ingest_au.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
Log "STEP AU end (exit=$LASTEXITCODE)"
if ($LASTEXITCODE -ne 0) { Log "FATAL AU"; exit 1 }

# 4) FL（必须 3.10 + zipfile_deflate64）
Log "STEP FL begin"
py -V:3.10 "$ing\ingest_fl.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
Log "STEP FL end (exit=$LASTEXITCODE)"
if ($LASTEXITCODE -ne 0) { Log "FATAL FL"; exit 1 }

# 5) FTS 全量建索引 + 触发器
Log "STEP FTS begin"
& $py "$ing\build_fts.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
Log "STEP FTS end (exit=$LASTEXITCODE)"
if ($LASTEXITCODE -ne 0) { Log "FATAL FTS"; exit 1 }

# 6) 验收
Log "STEP VERIFY begin"
& $py "$ing\verify_ingest.py" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
Log "STEP VERIFY end (exit=$LASTEXITCODE)"

Log "==== run_ingest done ===="
