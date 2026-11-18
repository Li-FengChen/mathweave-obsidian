$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '请先安装 Python 3.12，再运行打包脚本。' }
}
& $buildPython -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw '构建依赖安装失败。' }
if (-not (Test-Path -LiteralPath 'assets\vendor\manifest.json')) {
    & $buildPython tools\fetch_assets.py
    if ($LASTEXITCODE -ne 0) { throw '本地公式资源下载失败。' }
}
if (-not (Test-Path -LiteralPath 'assets\licenses\QtWebEngine-About.html')) {
    & $buildPython tools\collect_licenses.py
    if ($LASTEXITCODE -ne 0) { throw '授权资料收集失败。' }
}
$env:MATH_OBSIDIAN_HOME = Join-Path $PSScriptRoot '.qa\build-state'
& $buildPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw '回归检查未通过，未生成分享包。' }
$buildOutput = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'dist\数学知识织网'))
if (-not $buildOutput.StartsWith([IO.Path]::GetFullPath($PSScriptRoot) + [IO.Path]::DirectorySeparatorChar)) { throw '构建路径超出项目。' }
& $buildPython -m PyInstaller --noconfirm MathWeave.spec
if ($LASTEXITCODE -ne 0) { throw '程序打包失败。' }
& $buildPython tools\verify_release.py
if ($LASTEXITCODE -ne 0) { throw '独立程序验证失败，未生成分享包。' }
& $buildPython tools\package_release.py
if ($LASTEXITCODE -ne 0) { throw '分享包生成失败。' }
Write-Host '完成：release 文件夹中有可双击程序、分享压缩包和源码压缩包。'
