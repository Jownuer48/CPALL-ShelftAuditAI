@echo off
cd /d C:\Users\ASUS\ShelfAuditAI\dashboard

call ..\backend\.venv\Scripts\activate.bat

streamlit run app.py

pause
