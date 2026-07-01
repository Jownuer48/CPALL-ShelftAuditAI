@echo off
title ShelfAuditAI Launcher
setlocal

cd /d "%~dp0"

echo ==========================================
echo   CPALL ShelfAuditAI - Start All Services
echo ==========================================
echo.

REM ===== Environment =====
set "PYTHON_EXE=%CD%\backend\.venv\Scripts\python.exe"
set "CUDA_VISIBLE_DEVICES=-1"
set "YOLO_CONFIG_DIR=%TEMP%\ultralytics"
set "SHELF_AUDIT_ANALYSIS_MODE=sku110k_planogram"
if not defined DATABASE_URL set "DATABASE_URL=postgresql+psycopg2://shelf_user:shelf_password@localhost:5432/shelf_audit"

echo Analysis Mode: %SHELF_AUDIT_ANALYSIS_MODE%
echo Database URL : %DATABASE_URL%
echo Python      : %PYTHON_EXE%
echo Project Path : %cd%
echo.

REM ===== Runtime Check =====
if not exist "%PYTHON_EXE%" (
    echo Python virtual environment not found: %PYTHON_EXE%
    echo Run: py -3.11 -m venv backend\.venv
    pause
    exit /b 1
)

echo Checking Python dependencies...
"%PYTHON_EXE%" scripts\check_runtime_env.py --require-startup
if errorlevel 1 (
    echo.
    echo Missing Python dependencies. Run: backend\.venv\Scripts\pip.exe install -r backend\requirements.txt
    pause
    exit /b 1
)
echo.

REM ===== Docker =====
echo Checking Docker...

where docker >nul 2>&1
if errorlevel 1 (
    echo Docker not found. Please open Docker Desktop first.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop is not running. Please open Docker Desktop first.
    pause
    exit /b 1
)

REM ===== Start PostgreSQL =====
echo [1/5] Starting PostgreSQL...
docker compose up -d postgres

echo Waiting for PostgreSQL...
timeout /t 5 /nobreak >nul

REM ===== Start RabbitMQ =====
echo [2/5] Checking RabbitMQ...

docker container inspect shelf-rabbitmq >nul 2>&1
if errorlevel 1 (
    echo RabbitMQ container not found. Starting with docker compose...
    docker compose up -d rabbitmq
) else (
    echo RabbitMQ container found. Starting existing container...
    docker start shelf-rabbitmq >nul 2>&1
)

echo Waiting for RabbitMQ...
timeout /t 5 /nobreak >nul

REM ===== Start Backend =====
echo [3/5] Starting Backend...
start "ShelfAuditAI Backend" /D "%~dp0" cmd /k "call scripts\start_backend.cmd"

timeout /t 2 /nobreak >nul

REM ===== Start Worker =====
echo [4/5] Starting Worker...
start "ShelfAuditAI Worker" /D "%~dp0" cmd /k "call scripts\start_worker.cmd"

timeout /t 2 /nobreak >nul

REM ===== Start Dashboard =====
echo [5/5] Starting Dashboard...
start "ShelfAuditAI Dashboard" /D "%~dp0" cmd /k "call scripts\start_dashboard.cmd"

timeout /t 5 /nobreak >nul

REM ===== Open Browser =====
echo Opening browser...
start "" "http://localhost:8000/docs"
start "" "http://localhost:8501"

echo.
echo ==========================================
echo   Started:
echo   - PostgreSQL
echo   - RabbitMQ
echo   - Backend API
echo   - Worker
echo   - Streamlit Dashboard
echo ==========================================
echo.
echo Swagger   : http://localhost:8000/docs
echo Dashboard : http://localhost:8501
echo RabbitMQ  : http://localhost:15672
echo Postgres  : localhost:5432 / shelf_audit
echo.
pause
