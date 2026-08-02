@echo off
setlocal
chcp 65001 >nul
rem ============================================================
rem  悅來餐廳 語音訂位客服 - 一鍵啟動 bot + admin + client
rem  各自開一個新視窗執行，關掉視窗即停止該服務
rem ============================================================

set "ROOT=%~dp0"

echo.
echo [1/3] 啟動 bot server (Pipecat / Gemini Live)  -^> http://localhost:7860
start "Restaurant Bot Server" cmd /k "cd /d "%ROOT%server" && set "PYTHONUTF8=1" && uv run bot-concierge.py"

echo [2/3] 啟動 admin server (訂位管理後台)         -^> http://localhost:7861/admin
start "Restaurant Admin Server" cmd /k "cd /d "%ROOT%server" && set "PYTHONUTF8=1" && uv run admin_server.py"

echo [3/3] 啟動 client (Vite)                       -^> http://localhost:5173
start "Restaurant Client" cmd /k "cd /d "%ROOT%client" && npm run dev"

echo.
echo 三個服務已在各自的視窗啟動。
echo   - 訂位專線網頁：http://localhost:5173
echo   - 店員管理後台：http://localhost:7861/admin
echo   - bot 後端 API：http://localhost:7860
echo 要停止服務，直接關掉對應的視窗或執行 stop.bat。
echo.
endlocal
