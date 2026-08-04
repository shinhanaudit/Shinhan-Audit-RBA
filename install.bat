@echo off
REM 더블클릭으로 설치를 실행하기 위한 진입점입니다.
REM install.ps1을 대신 더블클릭하면 보안 정책 때문에 메모장으로 열리거나 실행이 막힐 수 있어
REM 이 배치 파일을 통해 실행 정책을 이번 실행에 한해서만 우회합니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
