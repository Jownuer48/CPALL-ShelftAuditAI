@echo off
cd /d C:\Users\ASUS\ShelfAuditAI\backend

call .venv\Scripts\activate.bat

set RABBITMQ_HOST=localhost
set RABBITMQ_PORT=5672
set SHELF_QUEUE_NAME=shelf_audit_queue

python worker.py

pause
