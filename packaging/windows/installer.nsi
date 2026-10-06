; ---------------------------------------------------------------------
; Backstage - installateur Windows (NSIS), installation par utilisateur.
;
; Compile avec :
;   makensis /DVERSION=0.3.2 /DSRCDIR=<dossier Backstage> /DOUTFILE=<setup.exe> installer.nsi
;
; SRCDIR est le dossier produit par packaging/nuitka_build.py.
;
; Installation dans %LOCALAPPDATA%\Programs : pas d'elevation UAC, donc
; pas de prompt admin a l'installation. Les entrees de desinstallation
; vont dans HKCU en consequence.
;
; NOTE ENCODAGE : ce fichier est volontairement en ASCII pur (pas
; d'accents, meme dans les commentaires). En mode Unicode, makensis lit
; les sources sans BOM avec la page de code ANSI de la machine de build -
; un accent ici donnerait des libelles corrompus dans l'installateur, et
; seulement sur certaines machines. Les libelles accentues standard
; (Suivant, Annuler...) viennent du fichier de langue French.nlf, pas
; d'ici.
; ---------------------------------------------------------------------

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"

; Nom, exe et editeur doivent rester alignes avec editor/core/app_info.py
; (APP_NAME, APP_AUTHOR), la SOURCE UNIQUE, lue par packaging/nuitka_build.py
; (--product-name, --company-name, --output-filename) : c'est ce qui s'affiche
; dans "Applications et fonctionnalites" d'un cote, et dans les proprietes de
; l'exe de l'autre.
!define APP_NAME    "Backstage"
!define APP_EXE     "Backstage.exe"
!define APP_KEY     "Backstage"
!define PUBLISHER   "Yasorovic"
!define UNINST_KEY  "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_KEY}"

; Valeurs par defaut si le script est lance a la main sans /D
!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef SRCDIR
  !define SRCDIR "..\..\build-out\Backstage"
!endif
!ifndef OUTFILE
  !define OUTFILE "Backstage-${VERSION}-windows-setup.exe"
!endif
; VIProductVersion n'accepte QUE du numerique 4 champs. VERSION peut etre
; un tag quelconque ("0.3.2-rc1"), d'ou ce define separe, calcule par
; packaging/nuitka_build.py:numeric_version().
!ifndef VIVERSION
  !define VIVERSION "0.0.0.0"
!endif

Name "${APP_NAME} ${VERSION}"
OutFile "${OUTFILE}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\${APP_KEY}"
InstallDirRegKey HKCU "Software\${APP_KEY}" "InstallDir"
SetCompressor /SOLID lzma

VIProductVersion "${VIVERSION}"
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} installer"
VIAddVersionKey "FileVersion"     "${VERSION}"
VIAddVersionKey "ProductVersion"  "${VERSION}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "LegalCopyright"  "${PUBLISHER}"

!define MUI_ICON   "..\icon.ico"
!define MUI_UNICON "..\icon.ico"
!define MUI_ABORTWARNING

; Images de l'habillage (chemins relatifs a ce script) : 164x314 pour l'accueil et la fin,
; 150x57 pour la banniere d'en-tete. BMP 24 bits, convertis depuis les maquettes.
!define MUI_WELCOMEFINISHPAGE_BITMAP   "installer_welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "installer_welcome.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP   "installer_header.bmp"
!define MUI_HEADERIMAGE_UNBITMAP "installer_header.bmp"

; Pas de page de licence : la GPL n'en exige pas, et LICENSE comme
; THIRD-PARTY-NOTICES.md sont installes a la racine du dossier de l'application.

; Titres courts : le titre par defaut reprend $(^NameDA) ("Backstage 1.0.0-alpha"), et la
; version complete deborde du titre de la page d'accueil. Le titre ne garde que le nom ;
; la version passe dans le texte.
!define MUI_WELCOMEPAGE_TITLE "$(WELCOME_TITLE)"
!define MUI_WELCOMEPAGE_TEXT "$(WELCOME_TEXT)"
!define MUI_FINISHPAGE_TITLE "$(FINISH_TITLE)"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
; devkitPro et mGBA ne sont pas embarques : ce sont des cases a cocher qui les
; telechargent (cf. SecDevkitpro, SecMgba). Si elles sont decochees, ou si le
; telechargement echoue, la page de fin le rappelle avec le lien.
!define MUI_FINISHPAGE_TEXT "$(FINISH_TEXT)"
!define MUI_FINISHPAGE_LINK "$(FINISH_LINK)"
!define MUI_FINISHPAGE_LINK_LOCATION "https://devkitpro.org/wiki/Getting_Started"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; La premiere langue declaree est celle par defaut.
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "English"

LangString WELCOME_TITLE ${LANG_FRENCH}  "Installation de ${APP_NAME}"
LangString WELCOME_TITLE ${LANG_ENGLISH} "Installing ${APP_NAME}"
LangString WELCOME_TEXT ${LANG_FRENCH}  "Cet assistant va installer ${APP_NAME} ${VERSION} sur votre ordinateur.$\r$\n$\r$\nFermez ${APP_NAME} s'il est ouvert, puis cliquez sur Suivant."
LangString WELCOME_TEXT ${LANG_ENGLISH} "This wizard will install ${APP_NAME} ${VERSION} on your computer.$\r$\n$\r$\nClose ${APP_NAME} if it is open, then click Next."
LangString FINISH_TITLE ${LANG_FRENCH}  "${APP_NAME} est installe"
LangString FINISH_TITLE ${LANG_ENGLISH} "${APP_NAME} is installed"
LangString FINISH_TEXT ${LANG_FRENCH}  "${APP_NAME} est installe.$\r$\n$\r$\nSi vous avez choisi devkitPro, son assistant continue dans sa propre fenetre : terminez-le (GBA Development coche) avant de fabriquer une ROM. Les outils manquants sont aussi signales dans les reglages de ${APP_NAME}."
LangString FINISH_TEXT ${LANG_ENGLISH} "${APP_NAME} is installed.$\r$\n$\r$\nIf you chose devkitPro, its wizard continues in its own window: finish it (GBA Development ticked) before building a ROM. Missing tools are also reported in ${APP_NAME}'s settings."
LangString FINISH_LINK ${LANG_FRENCH}  "Installer devkitPro (necessaire pour fabriquer des ROMs)"
LangString FINISH_LINK ${LANG_ENGLISH} "Install devkitPro (required to build ROMs)"
LangString MSG_APP_RUNNING ${LANG_FRENCH}  "${APP_NAME} est en cours d'execution. Fermez-le, puis cliquez sur Reessayer."
LangString MSG_APP_RUNNING ${LANG_ENGLISH} "${APP_NAME} is running. Close it, then click Retry."


; Mise a jour par-dessus une installation existante : on retire les fichiers de la
; version precedente AVANT de copier la nouvelle. Sans cela, un fichier renomme ou
; supprime d'une version a l'autre (module, DLL) resterait la, et une distribution
; standalone melangerait deux versions.
;
; Garde-fous :
;  - rien n'est touche si $INSTDIR ne contient pas l'executable attendu (meme
;    regle que la desinstallation : on ne fait pas de RMDir /r sur un dossier
;    qu'on ne reconnait pas) ;
;  - plugins\ est CONSERVE : c'est la que l'utilisateur depose les siens, et les
;    plugins livres y sont de toute facon recopies par la suite ;
;  - projets et configuration vivent hors de $INSTDIR (BackstageProjects, %APPDATA%).
Function CleanPreviousInstall
  Push $0
  Push $1
  IfFileExists "$INSTDIR\${APP_EXE}" 0 clean_done

  ; L'executable est verrouille tant que l'application tourne.
  clean_retry:
    ClearErrors
    FileOpen $0 "$INSTDIR\${APP_EXE}" a
    IfErrors clean_locked 0
    FileClose $0
    Goto clean_purge
  clean_locked:
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(MSG_APP_RUNNING)" IDRETRY clean_retry
    Abort

  clean_purge:
  FindFirst $0 $1 "$INSTDIR\*.*"
  clean_loop:
    StrCmp $1 "" clean_end
    StrCmp $1 "." clean_next
    StrCmp $1 ".." clean_next
    StrCmp $1 "plugins" clean_next
    IfFileExists "$INSTDIR\$1\*.*" clean_isdir 0
      Delete "$INSTDIR\$1"
      Goto clean_next
    clean_isdir:
      RMDir /r "$INSTDIR\$1"
    clean_next:
    FindNext $0 $1
    Goto clean_loop
  clean_end:
  FindClose $0

  clean_done:
  Pop $1
  Pop $0
FunctionEnd


Section "${APP_NAME}" SecApp
  SectionIn RO

  Call CleanPreviousInstall
  SetOutPath "$INSTDIR"
  File /r "${SRCDIR}\*"

  WriteRegStr HKCU "Software\${APP_KEY}" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Entree "Applications et fonctionnalites" (par utilisateur -> HKCU)
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${APP_EXE}"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1

  ; Taille affichee dans la liste des programmes installes
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"

  ; --- Association du fichier de projet (.project) ---
  ; Par utilisateur : HKCU\Software\Classes est la vue HKCR propre a
  ; l'utilisateur, coherente avec une installation sans elevation. Un ProgID
  ; dedie porte l'icone et la commande d'ouverture ; l'exe ouvre le fichier
  ; passe en "%1" (main.py accepte ce chemin en argument positionnel).
  WriteRegStr HKCU "Software\Classes\.project" "" "${APP_KEY}.Project"
  WriteRegStr HKCU "Software\Classes\${APP_KEY}.Project" "" "${APP_NAME} Project"
  WriteRegStr HKCU "Software\Classes\${APP_KEY}.Project\DefaultIcon" "" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKCU "Software\Classes\${APP_KEY}.Project\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'

  ; Prevenir le shell que les associations ont change (icone et appli a jour
  ; sans deconnexion). SHCNE_ASSOCCHANGED=0x08000000, SHCNF_IDLIST=0.
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"   "$INSTDIR\Uninstall.exe"
SectionEnd


Section /o "Raccourci sur le Bureau" SecDesktop
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd


; --- Outils externes : telecharges au moment de l'installation ---
;
; Ni devkitPro ni mGBA ne sont embarques : le premier est un telechargeur de
; paquets (il a besoin d'Internet de toute facon), le second pese 16 Mo et n'est
; pas le notre. On recupere l'installateur OFFICIEL, on verifie son empreinte
; SHA-256 (epinglee ci-dessus : mGBA n'est pas signe, l'empreinte est alors la
; seule garantie), puis on le lance SANS attendre sa fin : attendre figerait la
; fenetre de l'installateur le temps de l'assistant devkitPro. L'application
; redetecte ses outils au demarrage, avant un build et au retour de focus.
;
; Jamais en mode silencieux (/S, la CI) : pas de reseau, pas d'assistant.
; Un echec ne fait pas echouer l'installation de Backstage : on le dit, et les
; liens restent dans les reglages.
!define TOOLS_DIR "$TEMP\BackstageSetup"

!define DEVKITPRO_URL  "https://github.com/devkitPro/installer/releases/download/v3.0.3/devkitProUpdater-3.0.3.exe"
!define DEVKITPRO_FILE "devkitProUpdater-3.0.3.exe"
!define DEVKITPRO_SHA  "038a99dc84f1ca0b52e9e0e074a94a3b0672e6d7bf0988563f0ab0812dcbb38d"

!define MGBA_URL       "https://github.com/mgba-emu/mgba/releases/download/0.10.5/mGBA-0.10.5-win64-installer.exe"
!define MGBA_FILE      "mGBA-0.10.5-win64-installer.exe"
!define MGBA_SHA       "edd0454b8fe69f20dc2f0b47f2cfc32a14e3848550762ffbb3d782e649669c6b"

; Telecharge URL vers $TEMP\BackstageSetup\FILE et compare le SHA-256. Laisse
; "0" dans $0 si le fichier est la et conforme. Le chemin est resolu par
; PowerShell ($env:TEMP) et non injecte : un nom d'utilisateur peut contenir une
; apostrophe.
!macro FetchVerified URL FILE SHA
  CreateDirectory "${TOOLS_DIR}"
  nsExec::Exec `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$ErrorActionPreference='Stop'; $$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $$f=Join-Path $$env:TEMP 'BackstageSetup\${FILE}'; Invoke-WebRequest -UseBasicParsing -Uri '${URL}' -OutFile $$f; if ((Get-FileHash -Algorithm SHA256 $$f).Hash -ne '${SHA}') { Remove-Item $$f; exit 2 }"`
  Pop $0
!macroend

Section "devkitPro (GBA)" SecDevkitpro
  IfSilent devkitpro_done
  DetailPrint "$(MSG_DOWNLOADING) devkitPro"
  !insertmacro FetchVerified "${DEVKITPRO_URL}" "${DEVKITPRO_FILE}" "${DEVKITPRO_SHA}"
  StrCmp $0 "0" 0 devkitpro_failed
  ; Eleve (UAC) : il s'installe dans C:\devkitPro. Son assistant propose GBA
  ; Development, a cocher puis a suivre dans sa propre fenetre.
  DetailPrint "$(MSG_LAUNCHING) devkitPro"
  ExecShell "runas" "${TOOLS_DIR}\${DEVKITPRO_FILE}"
  Goto devkitpro_done
  devkitpro_failed:
    MessageBox MB_OK|MB_ICONEXCLAMATION "devkitPro : $(MSG_DOWNLOAD_FAILED)"
  devkitpro_done:
SectionEnd

Section "mGBA" SecMgba
  IfSilent mgba_done
  DetailPrint "$(MSG_DOWNLOADING) mGBA"
  !insertmacro FetchVerified "${MGBA_URL}" "${MGBA_FILE}" "${MGBA_SHA}"
  StrCmp $0 "0" 0 mgba_failed
  ; Silencieux, dans %LOCALAPPDATA%\mGBA : un des emplacements que l'application
  ; connait deja (Toolchain, _MGBA_WIN_DEFAULTS).
  DetailPrint "$(MSG_LAUNCHING) mGBA"
  ExecShell "open" "${TOOLS_DIR}\${MGBA_FILE}" '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER /DIR="$LOCALAPPDATA\mGBA"' SW_HIDE
  Goto mgba_done
  mgba_failed:
    MessageBox MB_OK|MB_ICONEXCLAMATION "mGBA : $(MSG_DOWNLOAD_FAILED)"
  mgba_done:
SectionEnd


; Un outil deja present n'est pas propose par defaut : la case est decochee, pas
; masquee, au cas ou l'utilisateur voudrait quand meme le (re)installer.
Function .onInit
  ReadEnvStr $0 DEVKITPRO
  StrCmp $0 "" 0 devkitpro_present
  IfFileExists "C:\devkitPro\devkitARM\bin\arm-none-eabi-gcc.exe" devkitpro_present devkitpro_check_done
  devkitpro_present:
    !insertmacro UnselectSection ${SecDevkitpro}
  devkitpro_check_done:
  IfFileExists "$LOCALAPPDATA\mGBA\mGBA.exe" mgba_present 0
  IfFileExists "$PROGRAMFILES64\mGBA\mGBA.exe" mgba_present mgba_check_done
  mgba_present:
    !insertmacro UnselectSection ${SecMgba}
  mgba_check_done:
FunctionEnd


LangString DESC_SecApp     ${LANG_FRENCH}  "L'editeur et ses fichiers."
LangString DESC_SecApp     ${LANG_ENGLISH} "The editor and its files."
LangString DESC_SecDesktop ${LANG_FRENCH}  "Ajouter une icone sur le Bureau."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Add a shortcut on the Desktop."
LangString DESC_SecDevkitpro ${LANG_FRENCH}  "Telecharge et lance l'installateur officiel de devkitPro (necessaire pour fabriquer des ROMs). Dans son assistant, cochez GBA Development. Internet requis."
LangString DESC_SecDevkitpro ${LANG_ENGLISH} "Downloads and runs the official devkitPro installer (required to build ROMs). In its wizard, tick GBA Development. Internet required."
LangString DESC_SecMgba    ${LANG_FRENCH}  "Telecharge et installe l'emulateur mGBA, qui ouvre la ROM depuis l'editeur. Internet requis."
LangString DESC_SecMgba    ${LANG_ENGLISH} "Downloads and installs the mGBA emulator, which opens the ROM from the editor. Internet required."
LangString MSG_DOWNLOADING ${LANG_FRENCH}  "Telechargement de"
LangString MSG_DOWNLOADING ${LANG_ENGLISH} "Downloading"
LangString MSG_LAUNCHING   ${LANG_FRENCH}  "Lancement de l'installateur de"
LangString MSG_LAUNCHING   ${LANG_ENGLISH} "Starting the installer of"
LangString MSG_DOWNLOAD_FAILED ${LANG_FRENCH}  "le telechargement a echoue (connexion absente ou fichier inattendu). ${APP_NAME} est installe quand meme ; les liens pour installer cet outil sont dans les reglages de ${APP_NAME}."
LangString MSG_DOWNLOAD_FAILED ${LANG_ENGLISH} "the download failed (no connection or unexpected file). ${APP_NAME} is installed anyway; the links to install this tool are in ${APP_NAME}'s settings."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp}       $(DESC_SecApp)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop}   $(DESC_SecDesktop)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDevkitpro} $(DESC_SecDevkitpro)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMgba}      $(DESC_SecMgba)
!insertmacro MUI_FUNCTION_DESCRIPTION_END


Section "Uninstall"
  ; Garde-fou : $INSTDIR vient du registre ou d'une saisie utilisateur, et
  ; on s'apprete a faire un RMDir /r dessus. On ne touche a rien si le
  ; dossier ne contient pas l'executable attendu.
  IfFileExists "$INSTDIR\${APP_EXE}" proceed 0
    MessageBox MB_ICONSTOP "Dossier d'installation inattendu : $INSTDIR$\n$\nDesinstallation annulee."
    Abort
  proceed:

  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  RMDir /r "$INSTDIR"

  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\${APP_KEY}"

  ; Defaire l'association .project posee a l'installation.
  DeleteRegKey HKCU "Software\Classes\${APP_KEY}.Project"
  ; `.project` est aussi l'extension d'autres outils (fichier de projet Eclipse) :
  ; on ne supprime la cle que si l'association est encore la notre.
  ReadRegStr $0 HKCU "Software\Classes\.project" ""
  StrCmp $0 "${APP_KEY}.Project" 0 +2
    DeleteRegKey HKCU "Software\Classes\.project"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

  ; Volontairement conserves : les projets de l'utilisateur
  ; (%USERPROFILE%\BackstageProjects) et sa configuration toolchain
  ; (%APPDATA%\Backstage). Une desinstallation ne doit pas detruire le
  ; travail de l'utilisateur ni ses chemins devkitPro/mGBA.
SectionEnd
