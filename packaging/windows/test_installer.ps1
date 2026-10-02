<#
.SYNOPSIS
  Teste l'installateur Windows de bout en bout : installation, mise a jour par-dessus,
  desinstallation. Lance par la CI de release, sur un runner jetable.

.DESCRIPTION
  Ce script ECRIT dans HKCU (cle de desinstallation, association .project), le menu
  Demarrer, %USERPROFILE%\BackstageProjects et %APPDATA%\Backstage. Il est fait pour une
  machine jetable : il REFUSE de tourner ailleurs sans -AllowLocal.

  Verifie :
   1. installation vierge : fichiers, cle de desinstallation, association, raccourci ;
   2. le binaire installe passe son smoke test ;
   3. mise a jour : un fichier de l'ancienne version disparait, un plugin de
      l'utilisateur reste, le binaire demarre toujours ;
   4. desinstallation : l'application, son raccourci et ses cles disparaissent ;
      les projets et la configuration de l'utilisateur RESTENT.
#>
param(
  [Parameter(Mandatory = $true)][string]$Installer,
  [Parameter(Mandatory = $true)][string]$Version,
  [switch]$AllowLocal
)

$ErrorActionPreference = "Stop"
if (-not $env:CI -and -not $AllowLocal) {
  throw "Ce test modifie le registre et le menu Demarrer : il ne tourne que sur la CI (variable CI) ou avec -AllowLocal."
}

$AppName   = "Backstage"
$InstDir   = Join-Path ($(if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP })) "BackstageInstallTest"
$UninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
$AssocKey  = "HKCU:\Software\Classes\.project"
$ProgIdKey = "HKCU:\Software\Classes\$AppName.Project"
$StartMenu = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
$Projects  = Join-Path $env:USERPROFILE "BackstageProjects\Keep"
$Config    = Join-Path $env:APPDATA $AppName

$failures = New-Object System.Collections.Generic.List[string]
function Check([bool]$Condition, [string]$What) {
  if ($Condition) { Write-Host "  ok     $What" } else { Write-Host "  ECHEC  $What"; $failures.Add($What) }
}
function Run([string]$File, [string[]]$Arguments) {
  $p = Start-Process -FilePath $File -ArgumentList $Arguments -Wait -PassThru
  return $p.ExitCode
}
function SmokeTest([string]$Label) {
  $report = Join-Path $env:TEMP "backstage-smoke-$Label.txt"
  Remove-Item $report -ErrorAction SilentlyContinue
  $code = Run (Join-Path $InstDir "$AppName.exe") @("--smoke-test=`"$report`"")
  if (Test-Path $report) { Get-Content $report | ForEach-Object { Write-Host "    $_" } }
  Check ($code -eq 0) "smoke test du binaire installe ($Label), code de sortie $code"
}

if (Test-Path $InstDir) { Remove-Item $InstDir -Recurse -Force }

# --- 1. installation vierge ------------------------------------------------
Write-Host "== 1. installation vierge"
# /D doit etre le DERNIER argument, sans guillemets (convention NSIS).
$code = Run $Installer @("/S", "/D=$InstDir")
Check ($code -eq 0) "l'installateur rend le code 0 (obtenu $code)"
Check (Test-Path "$InstDir\$AppName.exe")          "l'executable est installe"
Check (Test-Path "$InstDir\Uninstall.exe")         "le desinstallateur est installe"
Check (Test-Path "$InstDir\LICENSE")               "LICENSE est installee a la racine"
Check (Test-Path "$InstDir\THIRD-PARTY-NOTICES.md") "THIRD-PARTY-NOTICES.md est installee a la racine"
Check ((Get-ItemProperty $UninstKey -ErrorAction SilentlyContinue).DisplayVersion -eq $Version) "version affichee dans 'Applications et fonctionnalites' = $Version"
Check ((Get-ItemProperty $AssocKey -ErrorAction SilentlyContinue).'(default)' -eq "$AppName.Project") "l'extension .project est associee"
Check (Test-Path "$StartMenu\$AppName.lnk")        "raccourci du menu Demarrer"
SmokeTest "installation"

# --- 3. mise a jour par-dessus --------------------------------------------
Write-Host "== 2. mise a jour par-dessus l'installation"
# Un fichier et un dossier de l'ANCIENNE version, un plugin de l'utilisateur, et de
# quoi verifier que la desinstallation epargne ses donnees.
Set-Content "$InstDir\obsolete.txt" "reste d'une ancienne version"
New-Item -ItemType Directory "$InstDir\obsolete_dir" -Force | Out-Null
Set-Content "$InstDir\obsolete_dir\old.dll" "ancienne dll"
New-Item -ItemType Directory "$InstDir\plugins\mon_plugin" -Force | Out-Null
Set-Content "$InstDir\plugins\mon_plugin\plugin.py" "# plugin de l'utilisateur"
New-Item -ItemType Directory $Projects -Force | Out-Null
Set-Content "$Projects\Keep.project" "{}"
New-Item -ItemType Directory $Config -Force | Out-Null
Set-Content "$Config\toolchain.json" "{}"

$code = Run $Installer @("/S", "/D=$InstDir")
Check ($code -eq 0) "la mise a jour rend le code 0 (obtenu $code)"
Check (-not (Test-Path "$InstDir\obsolete.txt"))   "le fichier de l'ancienne version a disparu"
Check (-not (Test-Path "$InstDir\obsolete_dir"))   "le dossier de l'ancienne version a disparu"
Check (Test-Path "$InstDir\plugins\mon_plugin\plugin.py") "le plugin de l'utilisateur est conserve"
Check (Test-Path "$InstDir\$AppName.exe")          "l'executable est toujours la"
SmokeTest "mise a jour"

# --- 4. desinstallation ---------------------------------------------------
Write-Host "== 3. desinstallation"
# _?= : le desinstallateur tourne sur place et RENDS la main a la fin (sinon il se
# recopie dans %TEMP% et rend la main aussitot, avant d'avoir fini).
$code = Run "$InstDir\Uninstall.exe" @("/S", "_?=$InstDir")
Check ($code -eq 0) "la desinstallation rend le code 0 (obtenu $code)"
Check (-not (Test-Path "$InstDir\$AppName.exe"))   "l'executable est supprime"
Check (-not (Test-Path $UninstKey))                "la cle de desinstallation est supprimee"
Check (-not (Test-Path $AssocKey))                 "l'association .project est supprimee"
Check (-not (Test-Path $ProgIdKey))                "le ProgID est supprime"
Check (-not (Test-Path $StartMenu))                "le dossier du menu Demarrer est supprime"
Check (Test-Path "$Projects\Keep.project")         "les projets de l'utilisateur sont conserves"
Check (Test-Path "$Config\toolchain.json")         "la configuration de l'utilisateur est conservee"

# --- menage (le desinstallateur ne peut pas se supprimer lui-meme avec _?=) ---
Remove-Item $InstDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Split-Path $Projects) -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$Config\toolchain.json" -Force -ErrorAction SilentlyContinue

Write-Host ""
if ($failures.Count -gt 0) {
  Write-Host "INSTALLATEUR : $($failures.Count) ECHEC(S)"
  $failures | ForEach-Object { Write-Host "  - $_" }
  exit 1
}
Write-Host "INSTALLATEUR OK"
