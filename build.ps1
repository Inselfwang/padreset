# Build dist\PadReset.exe (portable, single file).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

& $py -m pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "tests failed" }
& $py tools\make_icon.py
& $py -m PyInstaller --noconfirm --clean padreset.spec
if ($LASTEXITCODE -ne 0) { throw "build failed" }
Get-Item dist\PadReset.exe | Select-Object Name, @{n="MB";e={[math]::Round($_.Length / 1MB, 1)}}
