@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
rem ============================================================
rem  悅來餐廳 語音訂位客服 - 停止 bot + admin + client
rem  依連接埠 (7860 / 7861 / 5173) 找出佔用行程，連同子行程一起結束
rem ============================================================

set "FOUND="

echo.
echo 停止 bot server (port 7860) ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":7860" ^| findstr "LISTENING"') do (
    echo   - 結束 PID %%p
    taskkill /F /T /PID %%p >nul 2>&1
    set "FOUND=1"
)

echo 停止 admin server (port 7861) ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":7861" ^| findstr "LISTENING"') do (
    echo   - 結束 PID %%p
    taskkill /F /T /PID %%p >nul 2>&1
    set "FOUND=1"
)

echo 停止 client (port 5173) ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo   - 結束 PID %%p
    taskkill /F /T /PID %%p >nul 2>&1
    set "FOUND=1"
)

echo.
if defined FOUND (
    echo 已停止所有服務。
) else (
    echo 找不到在執行的服務 ^(port 7860 / 7861 / 5173 都沒有監聽^)。
)
echo.
endlocal
