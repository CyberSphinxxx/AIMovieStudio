param([switch]$Browser)
$ErrorActionPreference='Stop'
$studioRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
function Run-Check([string]$Executable,[string[]]$Arguments){
  & $Executable @Arguments
  if($LASTEXITCODE -ne 0){throw "Check failed: $Executable $Arguments"}
}
Push-Location $studioRoot
try{
  Run-Check './.venv/Scripts/ruff.exe' @('check','studio','tests','scripts')
  Run-Check './.venv/Scripts/python.exe' @('-m','pytest','-q')
  Push-Location client
  try{
    Run-Check 'npm.cmd' @('run','lint')
    Run-Check 'npm.cmd' @('run','build')
    Run-Check 'npm.cmd' @('run','test')
    Run-Check 'npm.cmd' @('audit','--audit-level=low')
    if($Browser){Run-Check 'npm.cmd' @('run','test:e2e')}
  }finally{Pop-Location}
  Write-Host 'All requested checks passed.'
}finally{Pop-Location}
