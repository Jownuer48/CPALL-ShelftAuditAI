@echo off
title ShelfAuditAI Launcher
setlocal

cd /d "%~dp0"

echo ==========================================
echo   CPALL ShelfAuditAI - Start All Services
echo ==========================================
echo.

REM ===== Environment =====
set "YOLO_CONFIG_DIR=%TEMP%\ultralytics"
set "SHELF_AUDIT_ANALYSIS_MODE=sku110k_planogram"

echo Analysis Mode: %SHELF_AUDIT_ANALYSIS_MODE%
echo Project Path : %cd%
echo.

REM ===== Start RabbitMQ =====
echo [1/4] Checking RabbitMQ...

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
echo [2/4] Starting Backend...
start "ShelfAuditAI Backend" /D "%~dp0" cmd /k "call scripts\start_backend.cmd"

timeout /t 2 /nobreak >nul

REM ===== Start Worker =====
echo [3/4] Starting Worker...
start "ShelfAuditAI Worker" /D "%~dp0" cmd /k "call scripts\start_worker.cmd"

timeout /t 2 /nobreak >nul

REM ===== Start Dashboard =====
echo [4/4] Starting Dashboard...
start "ShelfAuditAI Dashboard" /D "%~dp0" cmd /k "call scripts\start_dashboard.cmd"

timeout /t 5 /nobreak >nul

REM ===== Open Browser =====
echo Opening browser...
start "" "http://localhost:8000/docs"
start "" "http://localhost:8501"

echo.
echo ==========================================
echo   Started:
echo   - RabbitMQ
echo   - Backend API
echo   - Worker
echo   - Streamlit Dashboard
echo ==========================================
echo.
echo Swagger   : http://localhost:8000/docs
echo Dashboard : http://localhost:8501
echo RabbitMQ  : http://localhost:15672
echo.
pause
