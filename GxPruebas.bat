@echo off
rem Abre la interfaz grafica de GxPruebas en el navegador. Cerrar esta ventana apaga el servidor y los motores.
title GxPruebas
cd /d "%~dp0"
python gxpruebas.py ui %*
if errorlevel 1 pause
