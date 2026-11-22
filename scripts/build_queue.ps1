$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup.bat first.' }
& $pythonPath -m PyInstaller --noconfirm --clean --windowed --onedir --name AudioExtractQueue queue_main.py
if ($LASTEXITCODE -ne 0) { throw 'Queue build failed.' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'mini_app\README.md') -Destination (Join-Path $projectRoot 'dist\AudioExtractQueue\README.md')
Write-Host 'Built: dist\AudioExtractQueue\AudioExtractQueue.exe'
