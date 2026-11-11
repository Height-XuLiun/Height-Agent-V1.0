@echo off
chcp 65001 >nul
cd /d "%~dp0Agent"
python -u setup_workspace.py
pause
