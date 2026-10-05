@echo off
echo ========================================================
echo   Telegram Bot Token Studio - Launching Web Application
echo ========================================================
echo.
echo Starting FastAPI Web Server at http://127.0.0.1:8000 ...
start http://127.0.0.1:8000
python server.py --host 127.0.0.1 --port 8000
pause
