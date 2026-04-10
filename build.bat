@echo off
:: ╔══════════════════════════════════════════════════════════════╗
:: ║   GameBooster v2.1 — Build szkript                          ║
:: ║   Egyetlen .bat fájl, ami mindent elvégez                   ║
:: ╚══════════════════════════════════════════════════════════════╝
:: Használat: Dupla klikk a build.bat-ra, vagy:
::   build.bat           → teljes build (clean + install + compile)
::   build.bat --fast    → csak újrafordít (clean nélkül)
::   build.bat --clean   → csak töröl

setlocal EnableDelayedExpansion
set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist\GameBooster"
set "BUILD_DIR=%PROJECT_DIR%build"
set "VENV_DIR=%PROJECT_DIR%.venv"
set "EXE_PATH=%DIST_DIR%\GameBooster.exe"

cd /d "%PROJECT_DIR%"

:: Fejléc
echo.
echo  ══════════════════════════════════════════════════
echo   ⚡  GameBooster v2.1 -- Build
echo  ══════════════════════════════════════════════════
echo.

:: Argumentum kezelés
set "DO_CLEAN=1"
set "DO_INSTALL=1"
if "%1"=="--fast"  set "DO_CLEAN=0" & set "DO_INSTALL=0"
if "%1"=="--clean" goto :CLEAN_ONLY

:: ── 1. Python ellenőrzés ──────────────────────────────────────
echo [1/6] Python ellenőrzés...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ❌ Python nem található!
    echo     Telepítsd: https://python.org/downloads
    echo     Fontos: pipáld be az "Add to PATH" opciót!
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  ✓ %PY_VER%

:: ── 2. Virtuális környezet ───────────────────────────────────
echo.
echo [2/6] Virtuális környezet...
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo  Létrehozás: .venv
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  ❌ venv létrehozás sikertelen
        pause & exit /b 1
    )
)
call "%VENV_DIR%\Scripts\activate.bat"
echo  ✓ .venv aktív

:: ── 3. Függőségek telepítése ─────────────────────────────────
echo.
echo [3/6] Függőségek telepítése...
if "%DO_INSTALL%"=="1" (
    pip install --quiet --upgrade pip
    pip install --quiet customtkinter psutil pyinstaller
    if errorlevel 1 (
        echo  ❌ pip install sikertelen
        pause & exit /b 1
    )
    echo  ✓ customtkinter, psutil, pyinstaller telepítve
) else (
    echo  ⏩ Kihagyva (--fast mód)
)

:: ── 4. Régi build törlése ────────────────────────────────────
echo.
echo [4/6] Régi build törlése...
if "%DO_CLEAN%"=="1" (
    if exist "%BUILD_DIR%" (
        rmdir /s /q "%BUILD_DIR%"
        echo  ✓ build\ törölve
    )
    if exist "%DIST_DIR%" (
        rmdir /s /q "%DIST_DIR%"
        echo  ✓ dist\GameBooster\ törölve
    )
) else (
    echo  ⏩ Kihagyva (--fast mód)
)

:: ── 5. PyInstaller fordítás ───────────────────────────────────
echo.
echo [5/6] PyInstaller fordítás (ez 1-3 percet vesz igénybe)...
echo  A folyamat közben sok figyelmeztetés jelenik meg — ez normális.
echo.

pyinstaller GameBooster.spec --noconfirm --clean

if errorlevel 1 (
    echo.
    echo  ❌ PyInstaller fordítás sikertelen!
    echo     Nézd meg a fenti hibaüzenetet.
    echo     Segítség: BUILD_GUIDE.md
    pause & exit /b 1
)

:: ── 6. Ellenőrzés ────────────────────────────────────────────
echo.
echo [6/6] Eredmény ellenőrzése...

if not exist "%EXE_PATH%" (
    echo  ❌ GameBooster.exe nem jött létre!
    echo     Elvárt hely: %EXE_PATH%
    pause & exit /b 1
)

:: Fájl méret megjelenítése
for %%f in ("%EXE_PATH%") do set EXE_SIZE=%%~zf
set /a EXE_MB=%EXE_SIZE% / 1048576

:: Dist mappa mérete
set DIST_SIZE=0
for /r "%DIST_DIR%" %%f in (*) do set /a DIST_SIZE+= %%~zf / 1048576

echo  ✓ GameBooster.exe: %EXE_MB% MB
echo  ✓ Teljes csomag:   %DIST_SIZE% MB
echo  ✓ Helye: %DIST_DIR%

:: ── Kész ─────────────────────────────────────────────────────
echo.
echo  ══════════════════════════════════════════════════
echo   ✅ Build sikeres!
echo  ══════════════════════════════════════════════════
echo.
echo  Az exe helye:
echo   %EXE_PATH%
echo.
echo  Terjesztéshez az egész mappát add át:
echo   %DIST_DIR%\
echo.
echo  ⚠  A GameBooster.exe mellé kerülnek a DLL-ek és
echo     egyéb fájlok — ezek mind szükségesek!
echo     Csak az egész mappát lehet terjeszteni.
echo.

:: Opcionálisan megnyitjuk az explorert
choice /c YN /m "Megnyitod a dist\GameBooster\ mappát?"
if errorlevel 2 goto :END
explorer "%DIST_DIR%"

goto :END

:: ── Csak törlés ──────────────────────────────────────────────
:CLEAN_ONLY
echo  🧹 Régi build fájlok törlése...
if exist "%BUILD_DIR%" ( rmdir /s /q "%BUILD_DIR%" & echo  ✓ build\ törölve )
if exist "%DIST_DIR%"  ( rmdir /s /q "%DIST_DIR%"  & echo  ✓ dist\GameBooster\ törölve )
if exist "__pycache__" ( rmdir /s /q "__pycache__" )
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
echo  ✓ Kész
goto :END

:END
endlocal
