@echo off
chcp 65001 >nul
cd /d "%~dp0Agent"
if exist "setup_workspace.py" python -u setup_workspace.py --dry-run >nul 2>&1
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',5000);$c.Close();exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto open
start "" /min python -u start.py
set /a n=0
:wait
timeout /t 1 >nul
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',5000);$c.Close();exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto open
set /a n+=1
if %n% lss 25 goto wait
:open
start "" http://127.0.0.1:5000/
exit /b
