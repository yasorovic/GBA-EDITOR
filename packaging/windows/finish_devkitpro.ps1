# Lance par l'installateur (installer.nsi, .onGUIEnd), en arriere-plan, en meme temps que
# le devkitPro Updater. Il termine l'installation de devkitPro, puis lance Backstage.
#
# Le Updater enchaine, dans un seul processus, la mise a jour du coeur de MSYS2 puis
# `pacman -S gba-dev`. Sur une installation neuve la seconde etape echoue sans message, et
# le Updater se termine comme si de rien n'etait. La meme commande relancee ensuite passe,
# sans droits administrateur. Ce script attend la fin du Updater ; si les outils GBA manquent
# alors que la case GBA Development etait cochee, il les installe en montrant une petite
# fenetre de progression (sinon l'utilisateur n'a rien a l'ecran pendant une minute).
# Dans tous les cas, il lance ensuite Backstage (-AppExe), que la page de fin de
# l'installateur n'a pas lance elle-meme.
#
# -SkipUpdaterWait et -Force servent aux essais a la main (pas d'attente du Updater, et
# passage de pacman meme si devkitARM est deja la).
#
# Meme commande que Toolchain.install_gba_packages (core/toolchain.py).
# Le journal est dans %TEMP%\BackstageSetup\finish_devkitpro.log.
param(
    [string]$AppExe = '',
    [string]$Root = 'C:\devkitPro',
    [switch]$SkipUpdaterWait,
    [switch]$Force
)
$ErrorActionPreference = 'Continue'
# La sortie de pacman est en UTF-8 : sans cela, PowerShell la lit en page de code OEM (« … » devient « ÔÇª »).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$gcc = Join-Path $Root 'devkitARM\bin\arm-none-eabi-gcc.exe'
$bash = Join-Path $Root 'msys2\usr\bin\bash.exe'
$log = Join-Path $env:TEMP 'BackstageSetup\finish_devkitpro.log'
$french = (Get-UICulture).TwoLetterISOLanguageName -eq 'fr'

function Write-Log($message) {
    "$(Get-Date -Format 'HH:mm:ss') $message" | Add-Content -LiteralPath $log -Encoding UTF8
}

function Get-Updater { Get-Process -Name 'devkitProUpdater*' -ErrorAction SilentlyContinue }

$script:launched = $false
function Start-Backstage {
    if (-not $script:launched -and $AppExe -and (Test-Path -LiteralPath $AppExe)) {
        $script:launched = $true
        Write-Log 'starting Backstage'
        Start-Process -FilePath $AppExe
    }
}

# Quoi qu'il arrive, l'utilisateur ne doit pas se retrouver sans Backstage.
trap { Write-Log "error: $_"; Start-Backstage; exit 1 }

New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
Write-Log 'started'

if (-not $SkipUpdaterWait) {
    # Le Updater apparait apres l'invite UAC : on lui laisse jusqu'a 5 minutes. S'il n'apparait
    # jamais (UAC refuse), il n'y a rien a terminer.
    $deadline = (Get-Date).AddMinutes(5)
    while (-not (Get-Updater) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    if (-not (Get-Updater)) { Write-Log 'updater never started'; Start-Backstage; exit 0 }
    Write-Log 'updater running'
    while (Get-Updater) { Start-Sleep -Seconds 2 }
    Write-Log 'updater finished'
}

if ((Test-Path -LiteralPath $gcc) -and -not $Force) { Write-Log 'devkitARM present, nothing to do'; Start-Backstage; exit 0 }
if (-not (Test-Path -LiteralPath $bash)) { Write-Log 'msys2 missing, nothing to do'; Start-Backstage; exit 0 }

# Seulement si l'utilisateur a coche GBA Development.
$ini = Join-Path $Root 'installed.ini'
$enabled = $false
if (Test-Path -LiteralPath $ini) {
    $section = ''
    foreach ($line in Get-Content -LiteralPath $ini) {
        if ($line -match '^\[(.+)\]') { $section = $Matches[1] }
        elseif ($section -eq 'GBADev' -and $line -match '^Enabled=1') { $enabled = $true }
    }
}
if (-not $enabled) { Write-Log 'GBA Development not selected, nothing to do'; Start-Backstage; exit 0 }

# La fenetre de progression : une barre qui tourne et une phrase qui dit ce qui se passe.
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Backstage'
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.ControlBox = $false
$form.TopMost = $true
$form.ClientSize = New-Object System.Drawing.Size(420, 110)
$text = New-Object System.Windows.Forms.Label
$text.Location = New-Object System.Drawing.Point(16, 14)
$text.Size = New-Object System.Drawing.Size(388, 50)
$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(16, 72)
$bar.Size = New-Object System.Drawing.Size(388, 20)
$bar.Style = 'Marquee'
$form.Controls.AddRange(@($text, $bar))

function Set-Message($french_text, $english_text) {
    $text.Text = if ($french) { $french_text } else { $english_text }
    [System.Windows.Forms.Application]::DoEvents()
}

Set-Message "Finalisation de l'installation de devkitPro...`nCela prend environ une minute. Backstage se lancera ensuite tout seul." `
            "Finishing the devkitPro installation...`nThis takes about a minute. Backstage will then start by itself."
$form.Show()
[System.Windows.Forms.Application]::DoEvents()

$succeeded = $false
$out = Join-Path $env:TEMP 'BackstageSetup\finish_pacman.txt'
for ($attempt = 1; $attempt -le 3 -and -not $succeeded; $attempt++) {
    Write-Log "pacman attempt $attempt"
    $p = Start-Process -FilePath $bash -ArgumentList '-lc "pacman -S --noconfirm --needed gba-dev"' `
            -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError "$out.err"
    $null = $p.Handle      # sans cela, ExitCode reste vide apres la sortie du processus
    # La fenetre reste vivante pendant que pacman tourne : on vide la file de messages.
    while (-not $p.HasExited) { [System.Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 100 }
    foreach ($file in $out, "$out.err") {
        if (Test-Path -LiteralPath $file) {
            Get-Content -LiteralPath $file -Encoding UTF8 | ForEach-Object { Write-Log "  $_" }
        }
    }
    if ($p.ExitCode -eq 0 -and (Test-Path -LiteralPath $gcc)) { $succeeded = $true } else { Start-Sleep -Seconds 5 }
}

if ($succeeded) {
    Write-Log 'done'
    Set-Message 'devkitPro est installé. Lancement de Backstage...' 'devkitPro is installed. Starting Backstage...'
    Start-Sleep -Seconds 1
    $form.Close()
    Start-Backstage
    exit 0
}

Write-Log 'failed'
$bar.Style = 'Continuous'
Set-Message "L'installation des paquets GBA a échoué. Dans Backstage, ouvrez les réglages (File > Settings) puis cliquez sur « Installer les paquets GBA »." `
            "The GBA packages could not be installed. In Backstage, open the settings (File > Settings) and click Install GBA packages."
# Backstage se lance tout de suite ; la fenetre reste jusqu'a ce que l'utilisateur la ferme.
Start-Backstage
$form.Hide()
$form.ControlBox = $true
[void]$form.ShowDialog()
exit 1
