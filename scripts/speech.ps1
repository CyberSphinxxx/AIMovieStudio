param([Parameter(Mandatory=$true)][string]$TextFile,
      [Parameter(Mandatory=$true)][string]$OutputFile,
      [string]$Voice = 'default')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled })
  if ($voices.Count -eq 0) { throw 'No installed Windows speech voice. Choose soundtrack-only in Settings.' }
  $index = if ($Voice -eq 'secondary' -and $voices.Count -gt 1) { 1 } else { 0 }
  $synth.SelectVoice($voices[$index].VoiceInfo.Name)
  $synth.Rate = 0
  $synth.SetOutputToWaveFile($OutputFile)
  $synth.Speak([System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8))
} finally { $synth.Dispose() }
