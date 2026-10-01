$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
python -m pip install --upgrade pip wheel setuptools
python -m pip install --prefer-binary -r requirements-desktop.txt
python -m pytest -q
python -m PyInstaller --noconfirm --clean packaging/NepaliSongGen.spec
& .\dist\NepaliSongGen\NepaliSongGen.exe --self-test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
New-Item -ItemType Directory -Force release | Out-Null
if (Get-Command iscc.exe -ErrorAction SilentlyContinue) {
  iscc.exe installer\nsg.iss
} elseif (Test-Path "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") {
  & "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\nsg.iss
} else {
  throw "Inno Setup 6 not found"
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-FileHash release\NepaliSongGen-Setup-x64.exe -Algorithm SHA256 | Format-List
