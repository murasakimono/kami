@echo off
rem Kami native messaging host baslaticisi. Tarayici bunu calistirir; stdout'a SADECE host yazar.
"%~dp0..\.venv\Scripts\python.exe" -u -I "%~dp0host.py" %*
