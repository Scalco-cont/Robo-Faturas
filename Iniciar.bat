@echo off
title Robo de Cartao Empresarial
cd /d "%~dp0"

echo Instalando dependencias (so na primeira vez, pode demorar um pouco)...
pip install -r requirements.txt >nul 2>&1

echo.
echo Abrindo o site em http://localhost:5000 ...
start "" http://localhost:5000
python app.py

pause
