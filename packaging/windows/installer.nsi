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
; devkitPro n'est PAS installe par cet installateur (il ne l'embarque pas) :
; sans lui, impossible de fabriquer une ROM. On le dit ici, a la fin, avec le lien.
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
LangString FINISH_TEXT ${LANG_FRENCH}  "${APP_NAME} est installe.$\r$\n$\r$\nPour fabriquer des ROMs, il faut aussi devkitPro et l'emulateur mGBA (non fournis) : les liens sont dans les reglages de ${APP_NAME}."
LangString FINISH_TEXT ${LANG_ENGLISH} "${APP_NAME} is installed.$\r$\n$\r$\nBuilding ROMs also needs devkitPro and the mGBA emulator (not included): the links are in ${APP_NAME}'s settings."
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


LangString DESC_SecApp     ${LANG_FRENCH}  "L'editeur et ses fichiers."
LangString DESC_SecApp     ${LANG_ENGLISH} "The editor and its files."
LangString DESC_SecDesktop ${LANG_FRENCH}  "Ajouter une icone sur le Bureau."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Add a shortcut on the Desktop."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp}     $(DESC_SecApp)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
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
