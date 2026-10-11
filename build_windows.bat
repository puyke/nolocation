@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "INSTALL=%LOCALAPPDATA%\Programs\NoLocation"
echo Building NoLocation (this can take a few minutes)...
python -m pip install --upgrade pyinstaller pymobiledevice3 pywebview || goto :err
python -m PyInstaller --noconfirm --clean --onedir --windowed --uac-admin --name NoLocation --icon assets\nolocation.ico ^
  --add-data "nolocation\ui;ui" ^
  --collect-all pymobiledevice3 --collect-submodules pymobiledevice3 --collect-all pytun_pmd3 ^
  --collect-all webview --collect-all pythonnet --collect-all clr_loader ^
  nolocation\main.py || goto :err

echo Installing to %INSTALL%
if exist "%INSTALL%" rmdir /s /q "%INSTALL%"
mkdir "%INSTALL%"
robocopy "dist\NoLocation" "%INSTALL%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :err
copy /y "assets\nolocation.ico" "%INSTALL%\nolocation.ico" >nul

powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\NoLocation.lnk'); $s.TargetPath='%INSTALL%\NoLocation.exe'; $s.WorkingDirectory='%INSTALL%'; $s.IconLocation='%INSTALL%\nolocation.ico'; $s.Save()"
echo.
echo Done! NoLocation was installed to: %INSTALL%
echo A desktop shortcut was created. You can delete this source folder now.
pause
exit /b 0
:err
echo.
echo Build failed, check the messages above.
pause
exit /b 1
