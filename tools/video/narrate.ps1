# Generate a local synthetic narration track per scene (no cloud service).
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$taskOutput = Join-Path $taskRoot '.video-build'
New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
$taskScenes = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'storyboard.json') | ConvertFrom-Json
$taskSpeaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $taskAvailable = $taskSpeaker.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
    if ($taskAvailable -contains 'Microsoft Zira Desktop') { $taskSpeaker.SelectVoice('Microsoft Zira Desktop') }
    $taskSpeaker.Rate = 0
    $taskSpeaker.Volume = 100
    foreach ($taskScene in $taskScenes) {
        $taskSpeaker.SetOutputToWaveFile((Join-Path $taskOutput ($taskScene.id + '.wav')))
        $taskSpeaker.Speak($taskScene.voice)
        $taskSpeaker.SetOutputToNull()
    }
} finally { $taskSpeaker.Dispose() }
