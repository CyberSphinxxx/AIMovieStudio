# Process-local runtime selection and ownership checks. No PATH/registry changes.
function Get-StudioFileSha256([string]$InputPath) {
  $stream=[IO.File]::OpenRead($InputPath)
  $hasher=[Security.Cryptography.SHA256]::Create()
  try{return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}
  finally{$hasher.Dispose();$stream.Dispose()}
}

function Get-StudioPython([string]$StudioRoot) {
  $runtimeDir=Join-Path $StudioRoot 'tools/app-runtime'
  $runtimePython=Join-Path $runtimeDir 'python.exe'
  if(Test-Path -LiteralPath $runtimeDir){
    $receiptPath=Join-Path $runtimeDir 'studio-runtime.json'
    $manifestPath=Join-Path $StudioRoot 'contracts/app-runtime-windows.json'
    if(-not (Test-Path -LiteralPath $receiptPath) -or -not (Test-Path -LiteralPath $runtimePython) -or -not (Test-Path -LiteralPath $manifestPath)){
      throw 'The private Studio runtime is incomplete. Review tools/app-runtime; existing files have been preserved.'
    }
    if((Get-Item -LiteralPath $receiptPath).Length -gt 2000000 -or (Get-Item -LiteralPath $manifestPath).Length -gt 2000000){throw 'Studio runtime metadata exceeds its size limit.'}
    $receipt=Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if($receipt.schema -ne 1 -or $receipt.status -ne 'READY' -or $receipt.python_version -ne '3.11.14' -or $receipt.manifest_sha256 -ne (Get-StudioFileSha256 $manifestPath)){
      throw 'The private Studio runtime does not match the reviewed application manifest. Review its setup report.'
    }
    $manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach($leaf in @('python.exe','python311.dll')){
      $expected=@($manifest.base_files | Where-Object {$_.path -ceq $leaf})
      $inputPath=Join-Path $runtimeDir $leaf
      if($expected.Count -ne 1 -or -not (Test-Path -LiteralPath $inputPath) -or (Get-StudioFileSha256 $inputPath) -ne $expected[0].sha256){throw 'The private Studio Python executable checksum changed. Originals have been preserved; review setup.'}
    }
    return $runtimePython
  }
  $developmentPython=Join-Path $StudioRoot '.venv/Scripts/python.exe'
  if(Test-Path -LiteralPath $developmentPython){return $developmentPython}
  throw 'Studio has no prepared local runtime. Prepare the private runtime or run scripts/setup.ps1 for development.'
}

function Test-StudioProcessOwned([string]$StudioRoot, $StudioProcess) {
  $command=$StudioProcess.CommandLine
  if(-not $command){return $false}
  $escaped=[regex]::Escape($StudioRoot)
  $appDir='(?:^|\s)--app-dir\s+(?:"'+$escaped+'"|'+$escaped+')(?=\s|$)'
  if($command -notmatch '(?:^|\s)-m\s+uvicorn\s+studio\.api:app(?=\s|$)' -or
     $command -notmatch '(?:^|\s)--host\s+127\.0\.0\.1(?=\s|$)' -or
     $command -notmatch '(?:^|\s)--port\s+8765(?=\s|$)' -or $command -notmatch $appDir){return $false}
  $allowed=@((Join-Path $StudioRoot 'tools/app-runtime/python.exe'),(Join-Path $StudioRoot '.venv/Scripts/python.exe'))
  $venvConfig=Join-Path $StudioRoot '.venv/pyvenv.cfg'
  if(Test-Path -LiteralPath $venvConfig){
    foreach($line in Get-Content -LiteralPath $venvConfig){
      if($line -match '^home\s*=\s*(.+)$'){$allowed+=Join-Path $Matches[1].Trim() 'python.exe'}
    }
  }
  foreach($candidate in $allowed){
    if([IO.Path]::GetFullPath($candidate) -eq $StudioProcess.ExecutablePath){return $true}
  }
  return $false
}
