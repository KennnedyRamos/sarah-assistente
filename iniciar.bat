@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Sarah

if not exist ".venv\Scripts\python.exe" (
  echo [Sarah] Primeira execucao: criando o ambiente Python em .venv ...
  py -3.11 -m venv .venv || (echo [ERRO] Python 3.11 nao encontrado. Instale em python.org e tente de novo. & pause & exit /b 1)
)

echo [Sarah] Conferindo dependencias...
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 echo [Aviso] Nao consegui instalar ou atualizar dependencias ^(sem internet?^). Tentando iniciar assim mesmo.

set PORT=
for /f "delims=" %%P in ('.venv\Scripts\python.exe -c "from jarvis import config; print(config.PORT)"') do set PORT=%%P
if "%PORT%"=="" (echo [ERRO] Nao consegui ler a configuracao. Confira o arquivo .env. & pause & exit /b 1)

if exist "data\jarvis.pid" (
  set /p OLDPID=<"data\jarvis.pid"
  call :check_running
  if not errorlevel 1 (echo [Sarah] Ja esta rodando ^(talvez em segundo plano^): abrindo a pagina. & start "" http://127.0.0.1:%PORT% & exit /b 0)
  del "data\jarvis.pid" >nul 2>&1
)

curl.exe -s -o nul http://127.0.0.1:11434/api/version
if errorlevel 1 (
  echo [Sarah] Ollama nao respondeu. Abrindo o Ollama...
  start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
  "%SystemRoot%\System32\timeout.exe" /t 5 >nul
)

if not exist "data\models\kokoro\voices-v1.0.bin" (
  choice /C SN /T 20 /D N /M "[Sarah] Baixar os modelos de voz agora (~600 MB, so uma vez)? Sem resposta em 20 s = Nao"
  if not errorlevel 2 .venv\Scripts\python.exe -m jarvis.voice
)

.venv\Scripts\python.exe -m jarvis.setpass --if-missing || (pause & exit /b 1)

echo [Sarah] Iniciando em http://127.0.0.1:%PORT%  (feche esta janela ou use parar.bat para encerrar)
if not defined JARVIS_NO_BROWSER start "" http://127.0.0.1:%PORT%
.venv\Scripts\python.exe -m jarvis
if errorlevel 1 (echo [ERRO] A Sarah encerrou com erro. Veja data\logs\jarvis.log & pause)
exit /b

:check_running
rem caminho completo: no PATH do Git Bash, "find" seria o do Linux
tasklist /FI "PID eq %OLDPID%" /NH | "%SystemRoot%\System32\find.exe" "%OLDPID%" >nul
exit /b %errorlevel%
