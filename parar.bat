@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "data\jarvis.pid" (echo [Sarah] Nao esta rodando. & exit /b 0)
set /p PID=<"data\jarvis.pid"
taskkill /PID %PID% /T /F >nul 2>&1 && echo [Sarah] Encerrado (PID %PID%). || echo [Sarah] Processo %PID% ja nao existia.
del "data\jarvis.pid" >nul 2>&1
