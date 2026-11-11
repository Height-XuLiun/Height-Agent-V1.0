@echo off
chcp 65001 >nul
set LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Height Agent.lnk
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');$s.TargetPath='%~dp0启动.bat';$s.WorkingDirectory='%~dp0';$s.IconLocation='%~dp0Agent\src\ui\icons\icon-192.png';$s.Save()"
echo 已加入开机启动。下次开机自动起服务，点桌面图标直接打开。
pause
