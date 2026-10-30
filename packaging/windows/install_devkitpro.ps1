# Lance par l'installateur (installer.nsi, .onGUIEnd), en arriere-plan, une fois l'assistant ferme.
# Il installe la chaine GBA dans un dossier propre a Backstage (aucun droit administrateur),
# puis lance Backstage (-AppExe), que la page de fin de l'installateur n'a pas lance elle-meme.
#
# La chaine est decrite par devkitpro_manifest.json, a cote de ce script : chaque paquet y a
# sa version, son URL et son empreinte SHA-256. Un paquet dont l'empreinte differe n'est
# jamais extrait. Les paquets sont des archives pacman (.pkg.tar.zst/.xz) : tar.exe, livre
# avec Windows 10 (version 22H2) et 11, sait les lire.
#   - layout "devkitpro" : le contenu de opt/devkitpro/ va a la racine du dossier ;
#   - layout "msys2"     : le contenu de l'archive va dans <racine>\msys2 (make, sh, mkdir, rm).
#
# L'installation se fait dans <racine>.partial, renomme en <racine> a la fin : une
# installation interrompue ne laisse jamais une chaine a moitie posee. Le dossier porte un
# fichier backstage-toolchain.json (l'empreinte du manifeste) : meme manifeste, rien a refaire.
#
# Ce dossier n'est PAS un devkitPro partage : le desinstallateur de Backstage peut le
# supprimer, et il ne touche jamais C:\devkitPro.
#
# -Force refait l'installation meme si elle est a jour (essais a la main).
# Le journal est dans %TEMP%\BackstageSetup\install_devkitpro.log.
param(
    [string]$AppExe = '',
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'Backstage\devkitPro'),
    [string]$Manifest = (Join-Path $PSScriptRoot 'devkitpro_manifest.json'),
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'

$work = Join-Path $env:TEMP 'BackstageSetup'
$cache = Join-Path $work 'packages'
$log = Join-Path $work 'install_devkitpro.log'
$partial = "$Root.partial"
$marker = Join-Path $Root 'backstage-toolchain.json'
$tar = Join-Path $env:SystemRoot 'System32\tar.exe'
$french = (Get-UICulture).TwoLetterISOLanguageName -eq 'fr'

function Write-Log($message) {
    "$(Get-Date -Format 'HH:mm:ss') $message" | Add-Content -LiteralPath $log -Encoding UTF8
}

$script:launched = $false
function Start-Backstage {
    if (-not $script:launched -and $AppExe -and (Test-Path -LiteralPath $AppExe)) {
        $script:launched = $true
        Write-Log 'starting Backstage'
        Start-Process -FilePath $AppExe
    }
}

New-Item -ItemType Directory -Force $cache | Out-Null
Write-Log 'started'

# Quoi qu'il arrive, l'utilisateur ne doit pas se retrouver sans Backstage.
trap { Write-Log "error: $_"; Start-Backstage; exit 1 }

$fingerprint = (Get-FileHash -Algorithm SHA256 -LiteralPath $Manifest).Hash
$gcc = Join-Path $Root 'devkitARM\bin\arm-none-eabi-gcc.exe'
if (-not $Force -and (Test-Path -LiteralPath $marker) -and (Test-Path -LiteralPath $gcc) `
        -and ((Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).manifest -eq $fingerprint)) {
    Write-Log 'toolchain up to date, nothing to do'
    Start-Backstage
    exit 0
}
$packages = (Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json).packages

# La fenetre de progression : une phrase qui dit ce qui se passe, une barre de avancement.
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
$bar.Minimum = 0
$bar.Maximum = $packages.Count
$form.Controls.AddRange(@($text, $bar))

function Set-Message($french_text, $english_text) {
    $text.Text = if ($french) { $french_text } else { $english_text }
    [System.Windows.Forms.Application]::DoEvents()
}

# Telecharge (ou reprend du cache) puis verifie l'empreinte. Leve une erreur dont le texte
# dit QUEL paquet pose probleme : c'est ce que l'utilisateur lira.
function Get-Package($package) {
    $file = Join-Path $cache (Split-Path $package.url -Leaf)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        if (-not (Test-Path -LiteralPath $file)) {
            Write-Log "download $($package.name) $($package.version) (attempt $attempt)"
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $package.url -OutFile $file
            } catch {
                Write-Log "  failed: $_"
                Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 3
                continue
            }
        }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash -eq $package.sha256) { return $file }
        Write-Log "  checksum mismatch for $($package.name)"
        Remove-Item -LiteralPath $file -Force
    }
    throw "$($package.name) $($package.version) could not be downloaded or did not match its checksum"
}

function Expand-Package($package, $file) {
    if ($package.layout -eq 'devkitpro') {
        $arguments = @('-xf', $file, '-C', $partial, '--strip-components=2', 'opt/devkitpro')
    } else {
        $destination = Join-Path $partial 'msys2'
        New-Item -ItemType Directory -Force $destination | Out-Null
        $arguments = @('-xf', $file, '-C', $destination,
                       '--exclude=.BUILDINFO', '--exclude=.MTREE', '--exclude=.PKGINFO', '--exclude=.INSTALL')
    }
    # Windows PowerShell 5.1 traite tout ce que tar ecrit sur stderr comme une erreur : on ne juge que son code.
    $ErrorActionPreference = 'Continue'
    $output = & $tar @arguments 2>&1
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) {
        Write-Log "  tar: $output"
        throw "$($package.name) could not be extracted (tar.exe exit code $LASTEXITCODE)"
    }
}

Set-Message "Installation de la chaîne GBA (devkitPro)...`nCela prend quelques minutes. Backstage se lancera ensuite tout seul." `
            "Installing the GBA toolchain (devkitPro)...`nThis takes a few minutes. Backstage will then start by itself."
$form.Show()
[System.Windows.Forms.Application]::DoEvents()

$failure = $null
try {
    if (-not (Test-Path -LiteralPath $tar)) { throw 'tar.exe was not found (Windows 10 22H2 or later is required)' }
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Recurse -Force }
    New-Item -ItemType Directory -Force $partial | Out-Null
    foreach ($package in $packages) {
        $file = Get-Package $package
        Write-Log "extract $($package.name)"
        Expand-Package $package $file
        $bar.Value = $bar.Value + 1
        [System.Windows.Forms.Application]::DoEvents()
    }
    # Une chaine incomplete ne doit pas passer pour une chaine installee.
    foreach ($tool in 'devkitARM\bin\arm-none-eabi-gcc.exe', 'tools\bin\grit.exe', 'tools\bin\mmutil.exe',
                      'tools\bin\bin2s.exe', 'libgba\lib\libgba.a', 'libgba\lib\libmm.a',
                      'msys2\usr\bin\make.exe', 'msys2\usr\bin\sh.exe') {
        if (-not (Test-Path -LiteralPath (Join-Path $partial $tool))) { throw "$tool is missing after extraction" }
    }
    @{ manifest = $fingerprint } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $partial 'backstage-toolchain.json') -Encoding UTF8
    if (Test-Path -LiteralPath $Root) { Remove-Item -LiteralPath $Root -Recurse -Force }
    Move-Item -LiteralPath $partial -Destination $Root
} catch {
    $failure = "$_"
    Write-Log "failed: $failure"
    Remove-Item -LiteralPath $partial -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $failure) {
    Write-Log 'done'
    Set-Message 'La chaîne GBA est installée. Lancement de Backstage...' 'The GBA toolchain is installed. Starting Backstage...'
    Start-Sleep -Seconds 1
    $form.Close()
    Start-Backstage
    exit 0
}

# Backstage se lance tout de suite ; la fenetre reste jusqu'a ce que l'utilisateur la ferme.
Set-Message "L'installation de la chaîne GBA a échoué : $failure`nBackstage est installé, mais ne pourra pas construire de ROM. Le journal est dans $log." `
            "The GBA toolchain could not be installed: $failure`nBackstage is installed but cannot build a ROM yet. The log is in $log."
$text.Size = New-Object System.Drawing.Size(388, 50)
Start-Backstage
$form.Hide()
$form.ControlBox = $true
[void]$form.ShowDialog()
exit 1
