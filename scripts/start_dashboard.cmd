@echo off
cd /d "%~dp0..\dashboard"

call "%~dp0..\backend\.venv\Scripts\activate.bat"

streamlit run app.py

pause