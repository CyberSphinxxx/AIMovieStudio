param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$studioRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'runtime.ps1')
$pythonPath=Get-StudioPython $studioRoot
if(-not (Test-Path -LiteralPath (Join-Path $studioRoot 'client/dist/index.html'))){throw 'Build the interface first: cd client; npm ci; npm run build'}
$existing=Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
foreach($listener in $existing){
  $studioProcess=Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
  if($listener.LocalAddress -ne '127.0.0.1' -or -not (Test-StudioProcessOwned $studioRoot $studioProcess)){
    throw 'Port 8765 belongs to another app or Studio folder. It has been left running; close that copy first.'
  }
}
if(-not $existing){
  $logDir=Join-Path $studioRoot 'data/logs'
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $quotedRoot='"'+$studioRoot+'"'
  Start-Process -FilePath $pythonPath -ArgumentList @('-I','-B','-m','uvicorn','studio.api:app','--app-dir',$quotedRoot,'--host','127.0.0.1','--port','8765') -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'server.log') -RedirectStandardError (Join-Path $logDir 'server-error.log') | Out-Null
}
$ready=$false
for($i=0;$i -lt 40;$i++){
  try{$health=Invoke-RestMethod http://127.0.0.1:8765/api/health -TimeoutSec 2; if($health.service -eq 'ready' -and $health.database -eq 'ok'){$ready=$true;break}}catch{}
  Start-Sleep -Milliseconds 250
}
if(-not $ready){throw 'Studio did not become ready. Check data/logs/server-error.log; port 8765 may be in use.'}
Write-Host 'AI Movie Studio is ready at http://127.0.0.1:8765'
if(-not $NoBrowser){Start-Process 'http://127.0.0.1:8765'}
