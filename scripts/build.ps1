param([switch]$Gpu, [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$OutputName)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Run setup.bat first.'
}
& $pythonPath -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$appName = 'AudioExtract'
$buildArguments = @('--noconfirm', '--clean', '--windowed', '--onedir', '--collect-all', 'faster_whisper', '--collect-all', 'ctranslate2', '--collect-all', 'av', '--collect-all', 'onnxruntime', '--collect-all', 'tokenizers')
if ($Gpu) {
    & $pythonPath -m pip install -r requirements-gpu.txt
    if ($LASTEXITCODE -ne 0) { throw 'GPU runtime installation failed.' }
    $appName = 'AudioExtractGPU'
    foreach ($package in @('nvidia.cublas', 'nvidia.cudnn', 'nvidia.cuda_runtime', 'nvidia.cuda_nvrtc')) {
        $buildArguments += @('--collect-binaries', $package)
    }
}
if ($OutputName) { $appName = $OutputName }
$buildArguments += @('--name', $appName, 'main.py')
& $pythonPath -m PyInstaller @buildArguments
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
$outputDirectory = Join-Path $projectRoot ('dist\' + $appName)
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $outputDirectory 'README.md')
Write-Host ('Built: ' + (Join-Path $outputDirectory ($appName + '.exe')))
