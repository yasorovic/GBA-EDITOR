# Installe la chaine GBA (devkitPro) dans un dossier propre a Backstage, sans droits
# administrateur. Lance par l'installateur (installer.nsi) des le debut de l'installation, en
# arriere-plan et sans fenetre : l'installateur montre l'avancement dans sa propre page, a partir
# du fichier -ProgressFile. On peut aussi le lancer a la main (reparation, portable) : il ecrit alors
# seulement dans la console et dans le journal.
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
# Ce dossier n'est PAS un devkitPro partage : le desinstallateur de Backstage peut le
# supprimer, et il ne touche jamais C:\devkitPro.
#
# -ProgressFile : une ligne, reecrite a chaque etape, "pourcentage|etape|nom|numero|total" (ASCII).
#   etape : download, extract, done ; en cas d'echec "-1|error|raison".
#   Si le fichier <ProgressFile>.cancel apparait, le script s'arrete et nettoie.
# -Force refait l'installation meme si elle est a jour (essais a la main).
# Le journal est dans %TEMP%\BackstageSetup\install_devkitpro.log.
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'Backstage\devkitPro'),
    [string]$Manifest = (Join-Path $PSScriptRoot 'devkitpro_manifest.json'),
    [string]$ProgressFile = '',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$work = Join-Path $env:TEMP 'BackstageSetup'
$cache = Join-Path $work 'packages'
$log = Join-Path $work 'install_devkitpro.log'
$partial = "$Root.partial"
$marker = Join-Path $Root 'backstage-toolchain.json'
$tar = Join-Path $env:SystemRoot 'System32\tar.exe'

function Write-Log($message) {
    "$(Get-Date -Format 'HH:mm:ss') $message" | Add-Content -LiteralPath $log -Encoding UTF8
}

# L'installateur lit ce fichier pendant qu'on l'ecrit : un echec d'ecriture n'est pas grave,
# la ligne suivante la remplace.
function Write-Progress-File($line) {
    Write-Host $line
    if (-not $ProgressFile) { return }
    try { [IO.File]::WriteAllText($ProgressFile, $line, [Text.Encoding]::ASCII) } catch { }
}

function Test-Cancelled { $ProgressFile -and (Test-Path -LiteralPath "$ProgressFile.cancel") }

New-Item -ItemType Directory -Force $cache | Out-Null
Write-Log 'started'

trap {
    Write-Log "error: $_"
    Remove-Item -LiteralPath $partial -Recurse -Force -ErrorAction SilentlyContinue
    Write-Progress-File "-1|error|$($_.Exception.Message -replace '[^\x20-\x7E]', '?' -replace '\|', '/')"
    exit 1
}

$fingerprint = (Get-FileHash -Algorithm SHA256 -LiteralPath $Manifest).Hash
$gcc = Join-Path $Root 'devkitARM\bin\arm-none-eabi-gcc.exe'
if (-not $Force -and (Test-Path -LiteralPath $marker) -and (Test-Path -LiteralPath $gcc) `
        -and ((Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).manifest -eq $fingerprint)) {
    Write-Log 'toolchain up to date, nothing to do'
    Write-Progress-File '100|done'
    exit 0
}
$packages = @((Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json).packages)
$totalBytes = ($packages | Measure-Object -Property size -Sum).Sum
$count = $packages.Count

# Telecharge (ou reprend du cache) puis verifie l'empreinte. Leve une erreur dont le texte
# dit QUEL paquet pose probleme. Le telechargement compte pour 90 % du poids du paquet,
# l'extraction pour le reste.
function Get-Package($package, $index, $doneBytes) {
    $file = Join-Path $cache (Split-Path $package.url -Leaf)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        if (-not (Test-Path -LiteralPath $file)) {
            Write-Log "download $($package.name) $($package.version) (attempt $attempt)"
            $stream = $null; $out = $null
            try {
                $request = [Net.HttpWebRequest]::Create($package.url)
                $request.Timeout = 60000
                $request.ReadWriteTimeout = 60000
                $response = $request.GetResponse()
                $stream = $response.GetResponseStream()
                $out = [IO.File]::Create($file)
                $buffer = New-Object byte[] 1048576
                $read = 0
                $last = [DateTime]::MinValue
                while (($n = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $out.Write($buffer, 0, $n)
                    $read += $n
                    if (([DateTime]::Now - $last).TotalMilliseconds -gt 250) {
                        $last = [DateTime]::Now
                        if (Test-Cancelled) { throw 'cancelled' }
                        $percent = [int](($doneBytes + 0.9 * $read) * 100 / $totalBytes)
                        Write-Progress-File "$([Math]::Min($percent, 99))|download|$($package.name)|$index|$count"
                    }
                }
            } catch {
                if ("$_" -eq 'cancelled') { throw }
                Write-Log "  failed: $_"
                if ($out) { $out.Close(); $out = $null }
                Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 3
                continue
            } finally {
                if ($out) { $out.Close() }
                if ($stream) { $stream.Close() }
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

if (-not (Test-Path -LiteralPath $tar)) { throw 'tar.exe was not found (Windows 10 22H2 or later is required)' }
if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Recurse -Force }
New-Item -ItemType Directory -Force $partial | Out-Null

$doneBytes = 0
$index = 0
foreach ($package in $packages) {
    $index++
    if (Test-Cancelled) { throw 'cancelled' }
    $file = Get-Package $package $index $doneBytes
    Write-Log "extract $($package.name)"
    Write-Progress-File "$([Math]::Min([int]((($doneBytes + 0.9 * $package.size) * 100) / $totalBytes), 99))|extract|$($package.name)|$index|$count"
    Expand-Package $package $file
    $doneBytes += $package.size
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
Write-Log 'done'
Write-Progress-File '100|done'
exit 0
