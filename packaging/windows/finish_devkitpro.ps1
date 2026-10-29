# Lance par l'installateur (installer.nsi, .onGUIEnd), en arriere-plan et sans fenetre,
# en meme temps que le devkitPro Updater.
#
# Le Updater enchaine, dans un seul processus, la mise a jour du coeur de MSYS2 puis
# `pacman -S gba-dev`. Sur une installation neuve la seconde etape echoue sans message, et
# le Updater se termine comme si de rien n'etait. La meme commande relancee ensuite passe,
# sans droits administrateur. Ce script attend la fin du Updater, et la relance si les
# outils GBA manquent alors que la case GBA Development etait cochee.
#
# Meme commande que Toolchain.install_gba_packages (core/toolchain.py).
# Le journal est dans %TEMP%\BackstageSetup\finish_devkitpro.log.
$ErrorActionPreference = 'Continue'
$root = 'C:\devkitPro'
$gcc = Join-Path $root 'devkitARM\bin\arm-none-eabi-gcc.exe'
$bash = Join-Path $root 'msys2\usr\bin\bash.exe'
$log = Join-Path $env:TEMP 'BackstageSetup\finish_devkitpro.log'

function Write-Log($message) {
    "$(Get-Date -Format 'HH:mm:ss') $message" | Add-Content -LiteralPath $log -Encoding UTF8
}

function Get-Updater { Get-Process -Name 'devkitProUpdater*' -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
Write-Log 'started'

# Le Updater apparait apres l'invite UAC : on lui laisse jusqu'a 5 minutes. S'il n'apparait
# jamais (UAC refuse), il n'y a rien a terminer.
$deadline = (Get-Date).AddMinutes(5)
while (-not (Get-Updater) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
if (-not (Get-Updater)) { Write-Log 'updater never started'; exit 0 }
Write-Log 'updater running'
while (Get-Updater) { Start-Sleep -Seconds 2 }
Write-Log 'updater finished'

if (Test-Path -LiteralPath $gcc) { Write-Log 'devkitARM present, nothing to do'; exit 0 }
if (-not (Test-Path -LiteralPath $bash)) { Write-Log 'msys2 missing, nothing to do'; exit 0 }

# Seulement si l'utilisateur a coche GBA Development.
$ini = Join-Path $root 'installed.ini'
$enabled = $false
if (Test-Path -LiteralPath $ini) {
    $section = ''
    foreach ($line in Get-Content -LiteralPath $ini) {
        if ($line -match '^\[(.+)\]') { $section = $Matches[1] }
        elseif ($section -eq 'GBADev' -and $line -match '^Enabled=1') { $enabled = $true }
    }
}
if (-not $enabled) { Write-Log 'GBA Development not selected, nothing to do'; exit 0 }

for ($attempt = 1; $attempt -le 3; $attempt++) {
    Write-Log "pacman attempt $attempt"
    $output = & $bash -lc 'pacman -S --noconfirm --needed gba-dev' 2>&1
    $output | ForEach-Object { Write-Log "  $_" }
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $gcc)) { Write-Log 'done'; exit 0 }
    Start-Sleep -Seconds 5
}
Write-Log 'failed'
exit 1
