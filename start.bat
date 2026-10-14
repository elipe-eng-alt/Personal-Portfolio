@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
	py -3 server.py
	goto :eof
)
python server.py
