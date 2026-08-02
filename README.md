# 悅來餐廳 語音訂位客服(Pipecat + Gemini Live + Function Calling)

用 [Pipecat](https://github.com/pipecat-ai/pipecat) 搭建的**會做事的語音助理**:在瀏覽器用麥克風打「電話」給悅來餐廳的訂位專員「小悅」,用說的完成**查空位、訂位、查詢、改期、取消**。所有異動透過 Gemini Live 的 **function calling** 真實寫入 SQLite 資料庫,並可在店員管理後台即時看到。

本專案基於同層的 [`Pipecat-interview-coach`](../Pipecat-interview-coach)(語音模擬面試官)改造;那個專案展示「角色塑造」,這個專案展示「工具呼叫做事」。

## 它怎麼「做事」?

```
你說「我想訂明天晚上七點,四個人」
  → Gemini Live 判斷需要查詢,發出工具呼叫 check_availability("2026-07-20", "19:00", 4)
  → Python 真的去查 SQLite → 回傳結果給模型
  → 小悅:「明天晚上七點還有位子喔,請問怎麼稱呼?方便留個電話嗎?」
  → 確認後呼叫 create_booking(...) → 資料庫多一筆訂位
  → 店員後台 (http://localhost:7861/admin) 兩秒內就會顯示這筆訂位
```

五個工具(`server/bot-concierge.py` 內的 direct functions,實作在 `server/booking_db.py`):

| 工具 | 功能 |
|---|---|
| `check_availability` | 查某日某時段是否有位;滿位回傳替代時段 |
| `create_booking` | 建立訂位(覆誦確認後才呼叫) |
| `find_bookings` | 用電話號碼查有效訂位 |
| `update_booking` | 改期/改時段/改人數(先驗新時段容量) |
| `cancel_booking` | 取消訂位,容量釋出 |

營業規則:午餐 11:00–13:30、晚餐 17:00–20:30(30 分鐘一時段),每時段 20 人。

## 架構

```
瀏覽器 client (5173)  ←WebRTC→  bot server (7860, Pipecat + Gemini Live)
                                     │ function calling
                                     ▼
                              booking_db.py ←→ server/data/bookings.db (SQLite)
                                     ▲
店員瀏覽器  ←HTTP→  admin server (7861, FastAPI /admin + /api/bookings)
```

## 環境需求

- **Windows**(批次檔為 Windows 寫的)
- **Python 3.11+** 與 [**uv**](https://docs.astral.sh/uv/)
- **Node.js 18+**
- **Google Gemini API Key**:<https://aistudio.google.com/apikey>

## 設定與安裝

1. `server/.env` 填入 `GOOGLE_API_KEY=你的金鑰`(**勿進版控**)。
2. 安裝依賴:

   ```powershell
   cd server
   uv sync
   cd ..\client
   npm install
   ```

## 執行

```powershell
.\start.bat
```

會開三個視窗:

- **訂位專線網頁** → <http://localhost:5173>(按「撥打訂位專線」開始)
- **店員管理後台** → <http://localhost:7861/admin>(即時看訂位進資料庫)
- bot 後端 API → <http://localhost:7860>

建議把訂位網頁與管理後台並排開,語音訂完位立刻看到資料出現。停止:`.\stop.bat`。

首次啟動會自動建立 `server/data/bookings.db` 並塞入幾筆示範訂位。想重置資料,關掉服務後刪除該檔即可。

## 測試

訂位資料層有完整單元測試(容量、滿位、改期、取消釋出容量等):

```powershell
cd server
uv run pytest
```

## 試用劇本建議

1. 「我想訂明天晚上七點,四個人」→ 走完訂位流程,聽小悅覆誦確認。
2. 到管理後台看新訂位出現。
3. 「我想查一下我的訂位」→ 報電話號碼。
4. 「幫我改到八點」→ 後台同步更新。
5. 「取消好了」→ 後台顯示已取消。
6. 試試客滿情境:同時段訂到滿,再訂一次聽小悅推薦替代時段。

## 想調整?

- **人設/流程/規則話術**:`server/bot-concierge.py` 的 `build_system_instruction()`。
- **營業時段/容量**:`server/booking_db.py` 頂部常數。
- **聲音**:`voice="Kore"` 可換 Aoede、Charon、Fenrir、Puck。

## 延伸教學

從電話訂位、交換機架構到這個專案的完整程式碼解析：[docs/tutorial/語音客服系統教學.md](docs/tutorial/語音客服系統教學.md)

## ⚠️ 安全性提醒

`server/.env` 含真實 API key,`.gitignore` 需排除 `.env`;管理後台無身分驗證,僅供本機 demo。
