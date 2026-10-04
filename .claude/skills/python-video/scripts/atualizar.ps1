<#
 Atualiza o python-video do GitHub SEM mexer no que é só seu (.venv, work, cache, output, teste, logs, API\, APIpixabay*, voice.lock.json).

   powershell -ExecutionPolicy Bypass -File C:\ALNA\python-video\scripts\atualizar.ps1

 Usa uma cópia do repositório em C:\ALNA\_repo (git clone/pull) e espelha só a pasta da skill para C:\ALNA\python-video.
 Parâmetros: -Branch (padrão claude/youthful-faraday-q0o4b7)  -Dest (padrão a pasta onde este script está instalado)
#>
param(
  [string]$Branch = "claude/youthful-faraday-q0o4b7",
  [string]$Repo = "https://github.com/alnacommerce-afk/Videos_marketplaces.git",
  [string]$Cache = "C:\ALNA\_repo",
  [string]$Dest = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git não encontrado. Instale o Git for Windows e abra um novo PowerShell." }
if (-not (Test-Path (Join-Path $Cache ".git"))) {
  Write-Host "Clonando o repositório em $Cache ..."
  git clone --branch $Branch $Repo $Cache
  if ($LASTEXITCODE -ne 0) { throw "git clone falhou (confira login do GitHub / acesso ao repositório)." }
} else {
  git -C $Cache fetch origin $Branch
  if ($LASTEXITCODE -ne 0) { throw "git fetch falhou." }
  git -C $Cache checkout $Branch
  git -C $Cache reset --hard "origin/$Branch"   # a cópia em _repo é só espelho: nunca edite lá
}
$src = Join-Path $Cache ".claude\skills\python-video"
if (-not (Test-Path $src)) { throw "Pasta da skill não encontrada em $src" }
Write-Host "Copiando $src -> $Dest (preservando o que é só seu)"
robocopy $src $Dest /E /XD ".venv" "work" "cache" "output" "teste" "logs" "API" "__pycache__" /XF "APIpixabay*" "API*.txt" "voice.lock.json" "*.key" ".env" /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) { throw "robocopy falhou (código $LASTEXITCODE)" }
$venvPy = Join-Path $Dest ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
  & $venvPy -m pip install -q -r (Join-Path $Dest "requirements.txt")
  & $venvPy (Join-Path $Dest "scripts\doctor.py")
} else { Write-Host "Sem .venv ainda: rode scripts\install_windows.ps1." }
Write-Host "Atualizado. Commit: $(git -C $Cache rev-parse --short HEAD)"
