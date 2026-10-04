<#
 Instalação do python-video no Windows (rode no PowerShell, de preferência SEM "Executar como administrador"
 para que a tarefa agendada rode no seu usuário, que é quem tem o G: do Google Drive).

   powershell -ExecutionPolicy Bypass -File .claude\skills\python-video\scripts\install_windows.ps1

 Faz: confere/instala Python 3.12 e FFmpeg (winget) -> cria .venv -> instala requirements -> roda os testes rápidos
 -> confere a pasta do Google Drive -> registra a tarefa diária (02:00 + recuperação 05:00).
#>
param([switch]$SkipTask, [switch]$SkipTests)
$ErrorActionPreference = "Stop"
$skill = Resolve-Path (Join-Path $PSScriptRoot "..")
Write-Host "Skill: $skill"

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# 1) Python
$py = $null
foreach ($c in @("py", "python")) { if (Have $c) { $py = $c; break } }
if (-not $py) {
  if (-not (Have "winget")) { throw "Python não encontrado e o winget não existe. Instale o Python 3.12 em https://www.python.org/downloads/ (marque 'Add to PATH') e rode de novo." }
  Write-Host "Instalando Python 3.12 (winget)..."
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  $py = if (Have "py") { "py" } else { "python" }
}
& $py --version

# 2) FFmpeg
if (-not (Have "ffmpeg")) {
  if (-not (Have "winget")) { throw "FFmpeg não encontrado. Instale (https://www.gyan.dev/ffmpeg/builds/) e coloque no PATH." }
  Write-Host "Instalando FFmpeg (winget)..."
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  if (-not (Have "ffmpeg")) { Write-Warning "FFmpeg instalado, mas só aparece no PATH depois de reabrir o terminal. Reabra e rode este script de novo." ; exit 1 }
}
ffmpeg -version | Select-Object -First 1

# 3) venv + dependências
$venv = Join-Path $skill ".venv"
if (-not (Test-Path $venv)) { & $py -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip
& $vpy -m pip install -r (Join-Path $skill "requirements.txt")

# 4) testes rápidos
if (-not $SkipTests) {
  & $vpy (Join-Path $skill "tests\test_pipeline.py") --fast
  if ($LASTEXITCODE -ne 0) { throw "Testes rápidos falharam. Veja a saída acima." }
}

# 5) pasta de destino
$out = "G:\Meu Drive\DRIVE - COMPUTADOR\MARKETING\Videos do Pyton"
if (-not (Test-Path $out)) {
  Write-Warning "Pasta de destino não existe: $out"
  Write-Warning "Abra o Google Drive para computador (conta correta) e confira o caminho; ou ajuste paths.output_dir_windows em config\config.json."
} else { Write-Host "Destino OK: $out" }

# 6) ElevenLabs (opcional)
if (-not $env:ELEVENLABS_API_KEY -or -not $env:ELEVENLABS_VOICE_ID) {
  Write-Host "ElevenLabs NÃO configurado (vídeos saem sem narração). Para ativar:"
  Write-Host '  setx ELEVENLABS_API_KEY  "sua-chave"'
  Write-Host '  setx ELEVENLABS_VOICE_ID "id-da-voz-oficial-pt-BR"'
}

# 7) tarefa agendada
if (-not $SkipTask) {
  & $vpy (Join-Path $skill "scripts\scheduler.py") install-task
  Write-Host "`nConfira em: Get-ScheduledTaskInfo -TaskName ALNA-PythonVideo-Diario"
  Write-Host "Lembrete: o PC precisa estar ligado (ou em suspensão com temporizadores de ativação), com seu usuário logado e o Google Drive aberto."
}
