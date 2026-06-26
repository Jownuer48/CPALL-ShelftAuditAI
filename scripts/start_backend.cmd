@echo off
cd /d C:\Users\ASUS\ShelfAuditAI\backend

call .venv\Scripts\activate.bat

set RABBITMQ_HOST=localhost
set RABBITMQ_PORT=5672
set SHELF_QUEUE_NAME=shelf_audit_queue

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
