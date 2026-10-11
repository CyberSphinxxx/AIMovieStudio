$ErrorActionPreference='Stop'
$listeners=Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
foreach($listener in $listeners){
  $studioProcess=Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
  if($studioProcess.CommandLine -match 'uvicorn studio\.api:app --host 127\.0\.0\.1 --port 8765'){
    Stop-Process -Id $listener.OwningProcess
    Write-Host 'Studio stopped. Completed steps are saved and resume at next launch.'
  }else{throw 'Port 8765 belongs to a different process. It has been left running.'}
}
