# Download UK Companies House monthly snapshot (7 parts) with retry/resume.
# Independent process; log to data/download_uk.log
$log = "d:\S.Q\kyb-mcp-server\data\download_uk.log"
$dir = "d:\S.Q\kyb-mcp-server\data\uk_snapshot"
New-Item -ItemType Directory -Force -Path $dir | Out-Null

function Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line
}

$base = "https://download.companieshouse.gov.uk/BasicCompanyData-2026-10-01-part{0}_7.zip"

for ($i = 1; $i -le 7; $i++) {
    $url = $base -f $i
    $out = Join-Path $dir ("part{0}_7.zip" -f $i)
    $done = $false
    $attempt = 0
    while (-not $done) {
        $attempt++
        Log "part $i attempt $attempt: downloading..."
        & curl.exe -sS -L -C - --retry 5 --retry-delay 5 --connect-timeout 30 -o $out $url 2>&1 | Out-Null
        if ((Test-Path $out) -and ((Get-Item $out).Length -gt 50MB)) {
            $sz = (Get-Item $out).Length
            Log ("part $i ok: " + [math]::Round($sz/1MB,1) + " MB")
            $done = $true
        } else {
            $sz = 0; if (Test-Path $out) { $sz = (Get-Item $out).Length }
            Log ("part $i invalid (exit $LASTEXITCODE, size $sz bytes), retry in 20s")
            Start-Sleep 20
        }
    }
}
Log "ALL PARTS COMPLETE"
