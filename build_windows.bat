@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo  WhatsApp Bulk Messenger - Windows Standalone Build Script
echo =====================================================================
echo.

:: 1. Check Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not found in system PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    exit /b 1
)

echo [1/4] Checking Python environment...
python --version
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to query Python version.
    exit /b 1
)

:: 2. Verify / Install PyInstaller
echo.
echo [2/4] Verifying PyInstaller...
python -c "import PyInstaller" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo PyInstaller not found. Installing now...
    python -m pip install --upgrade pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)
python -c "import PyInstaller; print(f'PyInstaller version: {PyInstaller.__version__}')"

:: 3. Run Test Suite before building
echo.
echo [3/4] Running automated test suite before compilation...
python -m unittest discover tests
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Tests failed! Aborting build to ensure executable stability.
    exit /b 1
)
echo [OK] All tests passed cleanly.

:: 4. Build Standalone Executable with PyInstaller
echo.
echo [4/4] Compiling standalone executable via WhatsAppBulkMessenger.spec...
python -m PyInstaller WhatsAppBulkMessenger.spec --noconfirm --clean
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] PyInstaller compilation failed! Check output log above.
    exit /b %ERRORLEVEL%
)

echo.
echo =====================================================================
echo  BUILD SUCCESSFUL!
echo =====================================================================
echo  Executable location:
echo    dist\WhatsAppBulkMessenger\WhatsAppBulkMessenger.exe
echo.
echo  Application data and mutable files will reside safely in:
echo    %%LOCALAPPDATA%%\WhatsAppBulkMessenger\
echo =====================================================================
echo.

exit /b 0

