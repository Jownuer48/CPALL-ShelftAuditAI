@echo off
setlocal

cd /d "%~dp0.."

set "PYTHON_EXE=%CD%\backend\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Python virtual environment not found: %PYTHON_EXE%
    echo Run: py -3.11 -m venv backend\.venv
    pause
    exit /b 1
)

set "CUDA_VISIBLE_DEVICES=-1"
set "YOLO_CONFIG_DIR=%TEMP%\ultralytics"
set "SHELF_AUDIT_ANALYSIS_MODE=sku110k_planogram"
if not defined DATABASE_URL set "DATABASE_URL=postgresql+psycopg2://shelf_user:shelf_password@localhost:5432/shelf_audit"

"%PYTHON_EXE%" -m streamlit run dashboard\app.py

pause
