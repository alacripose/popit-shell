$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$engine = $null

function Emit($payload) {
  $payload | ConvertTo-Json -Compress -Depth 4 | ForEach-Object {
    [Console]::Out.WriteLine($_)
    [Console]::Out.Flush()
  }
}

try {
  Add-Type -AssemblyName System.Speech
  $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
  $engine.SetInputToDefaultAudioDevice()
  $engine.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
  $engine.InitialSilenceTimeout = [TimeSpan]::FromSeconds(2)
  $engine.BabbleTimeout = [TimeSpan]::FromSeconds(2)
  $engine.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(700)
  $engine.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromMilliseconds(900)
  Emit @{ event = 'ready'; device = 'default capture device' }
  while ($true) {
    $result = $engine.Recognize([TimeSpan]::FromSeconds(3))
    if ($null -ne $result) {
      Emit @{
        event = 'phrase'
        text = [string]$result.Text
        confidence = [math]::Round([double]$result.Confidence, 3)
      }
    } else {
      Emit @{ event = 'silence' }
    }
  }
} catch {
  Emit @{ event = 'error'; detail = [string]$_.Exception.Message }
  exit 1
} finally {
  if ($null -ne $engine) { $engine.Dispose() }
}
