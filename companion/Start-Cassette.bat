@echo off
rem Starts the Cassette companion in the system tray (no window).
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0cassette.py"
