# Stiahne najnovsiu verziu aplikacie z GitHubu a prepise subory (config.txt a venv ostavaju).
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = 'martik-wq/investapp'
$branch = 'main'
try {
    Write-Host 'Kontrolujem aktualizacie...'
    $tmp = Join-Path $env:TEMP 'investapp_upd'
    $zip = "$tmp.zip"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Invoke-WebRequest "https://github.com/$repo/archive/refs/heads/$branch.zip" -OutFile $zip -UseBasicParsing -TimeoutSec 30
    Expand-Archive $zip $tmp -Force
    $src = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
    robocopy $src $PSScriptRoot /E /XD venv cache .git __pycache__ data /XF config.txt spustit.bat spustit.command .gitignore /NFL /NDL /NJH /NJS /NP | Out-Null
    Remove-Item $tmp -Recurse -Force
    Remove-Item $zip -Force
    Write-Host 'Aplikacia je aktualna.'
} catch {
    Write-Host 'Aktualizacia sa nepodarila, pokracujem so sucasnou verziou.'
}
