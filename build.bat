@echo off
REM 打包小蓝 AI 桌宠
pip install pyinstaller
pyinstaller -F -w -n AIPet --exclude-module onnxruntime main.py
echo.
echo 打包完成：dist\AIPet.exe
echo 请将 avatar.png、emotions\ 与 exe 放同目录运行。
pause
