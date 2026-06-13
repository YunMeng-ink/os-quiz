@echo off
echo Starting OS Quiz System...
start http://localhost:8080
echo Press Ctrl+C to stop.
D:/Miniforge/envs/coding/python.exe -m http.server 8080
