param([Parameter(Mandatory = $true)][string]$Path)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$engine = $null
try {
  Add-Type -AssemblyName System.Speech
  $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
  $engine.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
  $engine.SetInputToWaveFile($Path)
  $result = $engine.Recognize([TimeSpan]::FromSeconds(20))
  if ($null -ne $result) {
    @{ text = [string]$result.Text; confidence = [math]::Round([double]$result.Confidence, 3) } |
      ConvertTo-Json -Compress
  } else {
    @{ text = ''; confidence = 0.0 } | ConvertTo-Json -Compress
  }
} catch {
  @{ text = ''; error = [string]$_.Exception.Message } | ConvertTo-Json -Compress
  exit 1
} finally {
  if ($null -ne $engine) { $engine.Dispose() }
}
