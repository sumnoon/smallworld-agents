# Start the local Ollama service with an existing model folder.
# Run in a separate terminal; Ctrl+C stops it. No global settings are changed.
param(
    [string]$ModelsDirectory = $env:OLLAMA_MODELS,
    [string]$OllamaExecutable = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
)
$ErrorActionPreference = 'Stop'
if (-not $ModelsDirectory) {
    $ModelsDirectory = Join-Path $env:USERPROFILE '.ollama\models'
}
if (-not (Test-Path -LiteralPath $ModelsDirectory -PathType Container)) {
    throw "Model directory not found: $ModelsDirectory. Pass -ModelsDirectory with your Ollama model folder."
}
if (-not (Test-Path -LiteralPath $OllamaExecutable -PathType Leaf)) {
    throw "Ollama executable not found: $OllamaExecutable. Pass -OllamaExecutable with its installed path."
}
$env:OLLAMA_MODELS = (Resolve-Path -LiteralPath $ModelsDirectory).Path
& $OllamaExecutable serve
