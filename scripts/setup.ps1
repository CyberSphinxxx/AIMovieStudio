param([string]$Python='python', [switch]$Development)
$ErrorActionPreference='Stop'
$studioRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $studioRoot
try{
  if(-not (Test-Path .venv/Scripts/python.exe)){
    & $Python -m venv .venv
    if($LASTEXITCODE -ne 0){throw 'Python 3.11+ is needed. Pass -Python with an installed interpreter path.'}
  }
  $requirements=if($Development){'requirements-dev.txt'}else{'requirements.txt'}
  & ./.venv/Scripts/python.exe -m pip install -r $requirements
  if($LASTEXITCODE -ne 0){throw 'Local Python dependency installation failed.'}
  & ./.venv/Scripts/python.exe scripts/setup_media.py
  if($LASTEXITCODE -ne 0){throw 'App-local FFmpeg setup failed.'}
  Push-Location client
  try{
    npm ci
    if($LASTEXITCODE -ne 0){throw 'Frontend dependencies failed.'}
    npm run build
    if($LASTEXITCODE -ne 0){throw 'Frontend build failed.'}
  }finally{Pop-Location}
  Write-Host 'Ready. Double-click StartStudio.cmd. GPU models are installed separately with approval.'
}finally{Pop-Location}
