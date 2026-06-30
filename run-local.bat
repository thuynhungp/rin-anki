@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

python -m streamlit run app.py --server.address localhost --server.port 8501

if errorlevel 1 (
    echo.
    echo Khong the khoi dong Rin Anki. Hay kiem tra dependencies da duoc cai:
    echo pip install -r requirements.txt
    echo.
    pause
)
